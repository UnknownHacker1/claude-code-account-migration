"""Snapshot everything account-bound in Claude Code / the Claude desktop app.

Run this while still signed in to the OLD account. It only reads live data.

    python pack.py                       # writes ./pack and NEXT_PROMPT.txt (connectors via Composio)
    python pack.py --native-connectors   # same, but the prompt reconnects normal connectors

Never copied: .credentials.json and OAuth token caches.
"""
import argparse, json, os, shutil, sys, time
from common import cli_dir, cli_global_config, find_app_data, load, signed_in_account

HERE = os.path.dirname(os.path.abspath(__file__))
SECRET_FILES = {".credentials.json"}


def copytree(src, dst):
    if not os.path.exists(src):
        return 0
    n = 0
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        os.makedirs(os.path.join(dst, rel), exist_ok=True)
        for f in files:
            if f in SECRET_FILES:
                continue
            try:
                shutil.copy2(os.path.join(root, f), os.path.join(dst, rel, f))
                n += 1
            except OSError as e:
                print("  skip", os.path.join(root, f), e)
    return n


def copyfile(src, dst):
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        return 1
    return 0


BUILT_IN_HOSTS = ("api.anthropic.com", "claudemcpcontent.com")


def write_next_prompt(out, native):
    """Fill prompts/new_account.txt with this machine's paths and app list -> NEXT_PROMPT.txt."""
    p = lambda name: open(os.path.join(HERE, "prompts", name), encoding="utf-8").read()
    conns = load(os.path.join(out, "connectors-to-reconnect.json"))
    apps = [n for n, i in sorted(conns.items(), key=lambda kv: kv[0].lower())
            if n.lower() != "composio" and not any(h in (i.get("url") or "") for h in BUILT_IN_HOSTS)]
    apps_txt = "\n".join("   - " + a for a in apps) or "   (none found; ask me which apps I use)"
    if native:
        bg = "- Connectors: I'll reconnect my normal connectors one by one."
        part2, only = p("part2_native.txt"), ""
    else:
        bg = ("- Connectors: I want ALL my connectors to go through Composio, set up brand new from scratch. "
              "No separate Gmail / Drive / Slack connectors in Claude: one Composio connector, then one Composio "
              "connection per app account, each with a clear alias.")
        part2, only = p("part2_composio.txt"), " --only-connectors Composio"
    text = p("new_account.txt").replace("{{PART2}}", part2.strip())
    text = (text.replace("{{CONNECTOR_BACKGROUND}}", bg).replace("{{ONLY}}", only)
                .replace("{{APPS}}", apps_txt).replace("{{KIT}}", HERE))
    dst = os.path.join(HERE, "NEXT_PROMPT.txt")
    open(dst, "w", encoding="utf-8").write(text)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--native-connectors", action="store_true",
                    help="reconnect normal connectors instead of moving everything to Composio")
    ap.add_argument("--prompt-only", action="store_true", help="only rewrite NEXT_PROMPT.txt from the existing pack")
    ap.add_argument("--app-data", help="Claude desktop data folder (auto-detected)")
    ap.add_argument("--account", help="old account UUID (default: whoever is signed in now)")
    ap.add_argument("--org", help="old organization UUID")
    ap.add_argument("--force", action="store_true", help="re-pack even if the signed-in account changed")
    args = ap.parse_args()
    out = os.path.join(HERE, "pack")
    if args.prompt_only:
        print("Wrote", write_next_prompt(out, args.native_connectors))
        return

    app = find_app_data(args.app_data)
    cli = cli_dir()
    acct, org, name = signed_in_account()
    acct, org = args.account or acct, args.org or org
    if not acct or not org:
        sys.exit("Could not tell which account is signed in. Pass --account and --org "
                 "(they are the two folder names under claude-code-sessions).")
    if not os.path.isdir(os.path.join(app, "claude-code-sessions", acct, org)):
        sys.exit(f"No session folder for account {acct} / org {org} in {app}")

    old_man = os.path.join(out, "MANIFEST.json")
    if os.path.exists(old_man) and not args.force:
        prev = load(old_man)
        if prev.get("old_account_uuid") != acct:
            sys.exit("The signed-in account is not the one in the existing pack. You have probably already "
                     "switched accounts, and re-packing now would record the NEW account as the old one. "
                     "Keep the existing pack. (Use --force only if you really mean it.)")
    if os.path.exists(out):
        shutil.move(out, out + "-old-" + time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(out)
    counts = {}

    # 1. Desktop app: per-account sidebar layer (every account ever used here, as a backup)
    counts["desktop_session_files"] = copytree(os.path.join(app, "claude-code-sessions"),
                                               os.path.join(out, "desktop", "claude-code-sessions"))
    counts["cowork_files"] = copytree(os.path.join(app, "local-agent-mode-sessions"),
                                      os.path.join(out, "desktop", "local-agent-mode-sessions"))
    counts["side_session_notes"] = copytree(os.path.join(app, "side-session-notes"),
                                            os.path.join(out, "desktop", "side-session-notes"))
    for f in ["claude_desktop_config.json", "ccd-session-presets.json", "git-worktrees.json", "ssh_configs.json",
              "mcp-user-tool-toggles.json", "remote-control-state.json", "window-state.json"]:
        copyfile(os.path.join(app, f), os.path.join(out, "desktop", f))
    cfgp = os.path.join(app, "config.json")
    if os.path.exists(cfgp):
        cfg = {k: v for k, v in load(cfgp).items() if not k.startswith("oauth:")}
        json.dump(cfg, open(os.path.join(out, "desktop", "config.no-secrets.json"), "w", encoding="utf-8"), indent=2)

    # 2. Claude Code CLI config (shared by all accounts, but small and worth a backup)
    copyfile(os.path.join(cli, "settings.json"), os.path.join(out, "cli", "settings.json"))
    copyfile(cli_global_config(), os.path.join(out, "cli", "claude.json"))
    for d in ["skills", "scheduled-tasks", "plugins", "backups", "agents", "commands"]:
        counts["cli_" + d] = copytree(os.path.join(cli, d), os.path.join(out, "cli", d))
    mem = 0
    projects = os.path.join(cli, "projects")
    for p in (os.listdir(projects) if os.path.isdir(projects) else []):
        mem += copytree(os.path.join(projects, p, "memory"), os.path.join(out, "cli", "memory", p))
    counts["memory_files"] = mem

    # 3. Transcript inventory. Transcripts are shared by every account and stay in place.
    inv = []
    for p in sorted(os.listdir(projects)) if os.path.isdir(projects) else []:
        d = os.path.join(projects, p)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith(".jsonl"):
                    st = os.stat(os.path.join(d, f))
                    inv.append({"project": p, "file": f, "bytes": st.st_size, "mtime": int(st.st_mtime)})
    json.dump(inv, open(os.path.join(out, "transcripts-inventory.json"), "w"), indent=1)
    counts["transcripts"] = len(inv)
    counts["transcripts_gb"] = round(sum(i["bytes"] for i in inv) / 1e9, 2)

    # 4. The old account's chats: index, integrity, connectors
    sdir = os.path.join(app, "claude-code-sessions", acct, org)
    tx = {i["file"][:-6] for i in inv}
    sessions, missing, connectors = [], [], {}
    for f in sorted(os.listdir(sdir)):
        if not (f.startswith("local_") and f.endswith(".json")):
            continue
        try:
            j = load(os.path.join(sdir, f))
        except Exception as e:
            print("  unreadable", f, e)
            continue
        cli_id = j.get("cliSessionId")
        sessions.append({"id": j.get("sessionId"), "title": j.get("title"), "archived": j.get("isArchived"),
                         "cwd": j.get("cwd"), "cliSessionId": cli_id, "forkedFrom": j.get("forkedFromSessionId"),
                         "spawnedFrom": j.get("spawnedFrom"), "displayParent": j.get("displayParentSessionId")})
        if cli_id and cli_id not in tx:
            missing.append({"id": j.get("sessionId"), "title": j.get("title"), "cliSessionId": cli_id})
        for s in j.get("remoteMcpServersConfig") or []:
            if isinstance(s, dict) and s.get("name"):
                c = connectors.setdefault(s["name"], {"uuid": s.get("uuid"), "url": s.get("url"), "sessions": 0})
                c["sessions"] += 1
    json.dump(sessions, open(os.path.join(out, "sessions-index.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump(connectors, open(os.path.join(out, "connectors-to-reconnect.json"), "w", encoding="utf-8"), indent=1)

    manifest = {
        "packed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "old_account_uuid": acct, "old_org_uuid": org, "old_display_name": name,
        "app_data": app, "cli_dir": cli, "counts": counts,
        "sessions_in_old_account": len(sessions),
        "with_fork_parent": sum(1 for s in sessions if s["forkedFrom"]),
        "with_spawn_parent": sum(1 for s in sessions if s["spawnedFrom"]),
        "sessions_without_transcript_file": missing,
        "connectors": sorted(connectors),
    }
    json.dump(manifest, open(old_man, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(json.dumps({k: v for k, v in manifest.items() if k != "sessions_without_transcript_file"}, indent=2))
    print("chats without a transcript file (already, before migrating):", len(missing))
    print("\nPack written to", out)
    nxt = write_next_prompt(out, args.native_connectors)
    print("Next prompt (paste it into Claude after you log in to the new account):", nxt)


if __name__ == "__main__":
    main()
