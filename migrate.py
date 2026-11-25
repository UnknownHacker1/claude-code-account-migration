"""Move the Claude desktop Code-tab sidebar from the old account to the new one.

Chats themselves (~/.claude/projects) are shared by every account on the machine and
are not touched. This re-files the account-bound layer: the session list (titles,
fork / parent / child links, model, effort, permission mode, archive state), groups,
sidebar sections, stars, cowork sessions and scheduled-task records, and points old
chats at the new account's connector IDs.

Dry run by default. Nothing changes until you pass --apply.

    python migrate.py                          # dry run
    python migrate.py --apply                  # Claude desktop must be fully quit
    python migrate.py --apply --when-closed    # arm it, then quit Claude; runs, logs, reopens Claude
    python migrate.py --remap-connectors --apply [--when-closed]   # after reconnecting connectors
    python migrate.py --rollback <backup folder>
"""
import argparse, json, os, shutil, subprocess, sys, time
from common import (desktop_running, find_app_data, load, pid_alive, relaunch_command, save,
                    signed_in_account, spawn_detached)

HERE = os.path.dirname(os.path.abspath(__file__))
ACCOUNT_ONLY = {"account-plugins-sent.json"}  # belongs to the account, not to chats
SERVER_DECIDED = ("Gate", "ultrathinkAvailable", "chicagoChoice")  # the server decides these; never copy


def session_ids(folder):
    if not os.path.isdir(folder):
        return set()
    return {f[:-5] for f in os.listdir(folder) if f.startswith("local_") and f.endswith(".json")}


def find_new_ids(app, old_acct, args):
    if args.new_account and args.new_org:
        return args.new_account, args.new_org, "command line"
    a, o, _ = signed_in_account()
    if a and a != old_acct and o:
        return a, o, "signed-in account (~/.claude.json)"
    try:
        last = load(os.path.join(app, "config.json")).get("lastKnownAccountUuid")
        d = os.path.join(app, "claude-code-sessions", last or "")
        if last and last != old_acct and os.path.isdir(d) and len(os.listdir(d)) == 1:
            return last, os.listdir(d)[0], "desktop config.json lastKnownAccountUuid"
    except Exception:
        pass
    return None, None, None


def rekey(obj, pairs, stats, path=""):
    """Copy every preference entry keyed by the old account/org to the new key."""
    if not isinstance(obj, dict):
        return
    for k in list(obj.keys()):
        v = obj[k]
        k2 = k
        for a, b in pairs:
            k2 = k2.replace(a, b)
        if k2 != k and not any(s in path + "/" + k for s in SERVER_DECIDED):
            if k2 in obj and "dframe-group-scopes" in path and isinstance(obj[k2], dict):
                new = obj[k2]  # merge groups made in the new account with the old ones
                ids = {g["id"] for g in new.get("groups", [])}
                new.setdefault("groups", []).extend(g for g in v.get("groups", []) if g["id"] not in ids)
                new.setdefault("assignments", {}).update(v.get("assignments", {}))
            else:
                obj[k2] = json.loads(json.dumps(v))
            stats.append(path + "/" + k2)
        if isinstance(v, dict):
            rekey(v, pairs, stats, path + "/" + k)


def copy_sessions(src, dst, apply, log):
    copied = skipped = 0
    if apply:
        os.makedirs(dst, exist_ok=True)
    for f in sorted(os.listdir(src)):
        s, d = os.path.join(src, f), os.path.join(dst, f)
        if f in ACCOUNT_ONLY:
            continue
        if os.path.isdir(s):
            if apply:
                if not os.path.exists(d):
                    log.append(d)
                shutil.copytree(s, d, dirs_exist_ok=True)
            continue
        if f == "scheduled-tasks.json" and os.path.exists(d):
            if apply:  # merge task lists by id
                old, new = load(s), load(d)
                have = {t["id"] for t in new.get("scheduledTasks", [])}
                new.setdefault("scheduledTasks", []).extend(t for t in old.get("scheduledTasks", []) if t["id"] not in have)
                save(d, new)
            continue
        if os.path.exists(d):
            skipped += 1
            continue
        if apply:
            shutil.copy2(s, d)
            log.append(d)
        copied += 1
    return copied, skipped


def remap_connectors(new_dir, migrated_ids, old_connectors, apply, src=None):
    """Swap old connector UUIDs for the new account's ones, matched by connector name."""
    new_map = {}
    for sid in session_ids(new_dir) - migrated_ids:
        try:
            for s in load(os.path.join(new_dir, sid + ".json")).get("remoteMcpServersConfig") or []:
                if s.get("name") and s.get("uuid"):
                    new_map[s["name"]] = s["uuid"]
        except Exception:
            pass
    pairs = {i["uuid"]: new_map[n] for n, i in old_connectors.items()
             if n in new_map and i.get("uuid") and new_map[n] != i["uuid"]}
    missing = sorted(n for n in old_connectors if n not in new_map)
    changed = 0
    for sid in migrated_ids if pairs else []:
        p = os.path.join(new_dir, sid + ".json")
        if not os.path.exists(p):
            if apply or not src:
                continue
            p = os.path.join(src, sid + ".json")  # dry run: count against the not-yet-copied file
        t = open(p, encoding="utf-8").read()
        t2 = t
        for a, b in pairs.items():
            t2 = t2.replace(a, b)
        if t2 != t:
            changed += 1
            if apply:
                open(p, "w", encoding="utf-8").write(t2)
    print(f"Connectors: {len(pairs)} remapped to the new account, {changed} chats updated")
    if not new_map:
        print("   (no chat from the new account found yet, so its connector IDs are unknown)")
    print("   not connected in the new account yet:", ", ".join(missing) or "none")
    return missing


def verify(new_dir, old_ids, pack):
    ids = session_ids(new_dir)
    present = old_ids & ids
    idx = load(os.path.join(pack, "sessions-index.json"))
    broken = [(s["id"], k, s[k]) for s in idx for k in ("forkedFrom", "displayParent")
              if s.get(k) and str(s[k]).startswith("local_") and s[k] not in ids]
    print(f"\nVERIFY  chats present in the new account: {len(present)}/{len(old_ids)}")
    print(f"        fork / parent links pointing at a missing chat: {len(broken)}")
    for b in broken[:10]:
        print("        broken:", b)
    return len(present) == len(old_ids) and not broken


def arm_waiter(args, argv):
    """Start a background process that waits for Claude to quit, runs this, logs, and reopens Claude."""
    relaunch = "" if args.no_relaunch else relaunch_command()
    log = os.path.join(args.pack, "last-run.log")
    child = [sys.executable, os.path.abspath(__file__)] + [a for a in argv if a != "--when-closed"]
    child += ["--pack", args.pack, "--_waiter", "--_log", log]
    if args.app_data:
        child += ["--app-data", os.path.abspath(args.app_data)]
    if relaunch:
        child += ["--_relaunch", relaunch]
    pid = spawn_detached(child)
    print(f"Armed (background pid {pid}). Now quit Claude completely: tray icon > Quit.")
    print("The migration runs as soon as Claude is closed" + (", then Claude reopens by itself." if relaunch else "."))
    print("Result log:", log)


def run_waiter(args):
    log = open(args._log, "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    print("waiter started", time.strftime("%Y-%m-%d %H:%M:%S"))
    deadline = time.time() + 3600
    while time.time() < deadline:
        busy = pid_alive(args.wait_pid) if args.wait_pid else desktop_running()
        if not busy:
            break
        time.sleep(2)
    else:
        print("Gave up: Claude was not closed within an hour. Nothing changed.")
        return
    time.sleep(4)  # let the app finish writing files
    print("Claude closed, running", time.strftime("%H:%M:%S"))
    try:
        run(args)
    except SystemExit as e:
        print("STOPPED:", e)
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        if args._relaunch:
            print("reopening Claude")
            subprocess.Popen(args._relaunch, shell=True)
        print("done", time.strftime("%H:%M:%S"))


def run(args):
    pack = args.pack
    man = load(os.path.join(pack, "MANIFEST.json"))
    app = find_app_data(args.app_data or (man.get("app_data") if os.path.isdir(man.get("app_data", "")) else None))
    sess = os.path.join(app, "claude-code-sessions")
    desk_cfg = os.path.join(app, "claude_desktop_config.json")
    old_acct, old_org = man["old_account_uuid"], man["old_org_uuid"]

    if args.rollback:
        if desktop_running():
            sys.exit("Quit Claude completely first (tray icon > Quit).")
        shutil.copy2(os.path.join(args.rollback, "claude_desktop_config.json"), desk_cfg)
        for p in load(os.path.join(args.rollback, "copied-files.json")):
            if os.path.isdir(p):
                shutil.rmtree(p)
            elif os.path.exists(p):
                os.remove(p)
        print("Rolled back. The old account's folder was never touched.")
        return

    new_acct, new_org, how = find_new_ids(app, old_acct, args)
    print(f"app data    {app}")
    print(f"old account {old_acct} / org {old_org}")
    if not new_acct:
        sys.exit("No new account found. Sign in to the new account in the Claude app, open the Code tab, "
                 "start one chat, then run this again.")
    print(f"new account {new_acct} / org {new_org}   (found via {how})")
    if args.apply and not args.wait_pid and desktop_running():
        sys.exit("Claude is still running. Quit it completely (tray icon > Quit), or add --when-closed.")

    live_old = os.path.join(sess, old_acct, old_org)
    src = live_old if os.path.isdir(live_old) else os.path.join(pack, "desktop", "claude-code-sessions", old_acct, old_org)
    new_dir = os.path.join(sess, new_acct, new_org)
    old_ids = session_ids(src)
    conns = load(os.path.join(pack, "connectors-to-reconnect.json"))
    if args.only_connectors:
        keep = {c.strip().lower() for c in args.only_connectors.split(",")}
        conns = {n: i for n, i in conns.items() if n.lower() in keep}
    print(f"\n=== {'APPLY' if args.apply else 'DRY RUN'} ===")

    if args.remap_connectors:
        remap_connectors(new_dir, old_ids, conns, args.apply)
        return

    backup = os.path.join(HERE, "restore-backups", time.strftime("%Y%m%d-%H%M%S"))
    log = []
    if args.apply:
        os.makedirs(backup)
        shutil.copy2(desk_cfg, os.path.join(backup, "claude_desktop_config.json"))
        if os.path.isdir(new_dir):
            shutil.copytree(new_dir, os.path.join(backup, "new-account-sessions-before"))

    c, s = copy_sessions(src, new_dir, args.apply, log)
    print(f"Code chats: {c} to copy, {s} already there")

    cw_src = os.path.join(app, "local-agent-mode-sessions", old_acct, old_org)
    cw_dst = os.path.join(app, "local-agent-mode-sessions", new_acct, new_org)
    if os.path.isdir(cw_src):
        n = 0
        for f in os.listdir(cw_src):
            d = os.path.join(cw_dst, f)
            if not os.path.exists(d):
                n += 1
                if args.apply:
                    os.makedirs(cw_dst, exist_ok=True)
                    sf = os.path.join(cw_src, f)
                    (shutil.copytree if os.path.isdir(sf) else shutil.copy2)(sf, d)
                    log.append(d)
        print(f"Cowork entries: {n} to copy")

    cfg = load(desk_cfg)
    stats = []
    rekey(cfg.get("preferences", {}), [(old_acct, new_acct), (old_org, new_org)], stats, "preferences")
    print(f"Sidebar / preference entries re-keyed: {len(stats)}")
    for k in stats:
        print("   ", k)

    if args.apply:
        save(desk_cfg, cfg)
        json.dump(log, open(os.path.join(backup, "copied-files.json"), "w"), indent=1)
        remap_connectors(new_dir, old_ids, conns, True)
        ok = verify(new_dir, old_ids, pack)
        print(f"\nBackup + undo log: {backup}")
        print(f'Undo: python "{os.path.abspath(__file__)}" --rollback "{backup}"')
        print("RESULT:", "OK" if ok else "CHECK THE LINES ABOVE")
    else:
        remap_connectors(new_dir, old_ids, conns, False, src)
        print("\nDry run only. Add --apply (Claude fully quit) or --apply --when-closed.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--when-closed", action="store_true", help="wait in the background for Claude to quit, then run")
    ap.add_argument("--remap-connectors", action="store_true")
    ap.add_argument("--rollback")
    ap.add_argument("--pack", default=os.path.join(HERE, "pack"))
    ap.add_argument("--app-data")
    ap.add_argument("--new-account")
    ap.add_argument("--new-org")
    ap.add_argument("--only-connectors", help="comma list of connector names to carry over, e.g. Composio")
    ap.add_argument("--no-relaunch", action="store_true")
    ap.add_argument("--wait-pid", type=int, help=argparse.SUPPRESS)  # testing: wait for this pid instead
    ap.add_argument("--_waiter", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--_log", help=argparse.SUPPRESS)
    ap.add_argument("--_relaunch", help=argparse.SUPPRESS)
    args = ap.parse_args()
    args.pack = os.path.abspath(args.pack)
    if not os.path.exists(os.path.join(args.pack, "MANIFEST.json")):
        sys.exit(f"No pack at {args.pack}. Run pack.py while still signed in to the old account.")
    if args._waiter:
        run_waiter(args)
    elif args.when_closed:
        arm_waiter(args, sys.argv[1:])
    else:
        run(args)


if __name__ == "__main__":
    main()
