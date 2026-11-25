# claude-code-account-migration

Move your Claude Code desktop history to a **new Claude account on the same computer**,
keeping the sidebar exactly as it was: every chat, title, group, sidebar section, star, and
fork / parent / child link, plus each chat's model, effort and permission mode.

Unofficial. Not made by or affiliated with Anthropic. It works by reading and writing the
desktop app's local files, which can change between app versions. Every write is backed up
and can be undone.

## Why you need it

When you sign in to Claude with a different account, the Code tab sidebar comes up empty,
even though all your chats are still on disk. There are two layers:

| Layer | Where | Tied to the account? |
|---|---|---|
| Chat transcripts, subagents, memory, skills, settings | `~/.claude/` | No. Every account on the machine shares it. |
| Sidebar: chat list, titles, groups, sections, stars, fork links, cowork sessions | desktop app data, under `claude-code-sessions/<account-id>/<org-id>/` and in `claude_desktop_config.json` keyed by `<account-id>/<org-id>` | **Yes** |

The transcripts don't need moving. This tool re-files the sidebar layer under the new
account's IDs, then points old chats at the new account's connector IDs, matched by name.

Fork and parent links (`forkedFromSessionId`, `spawnedFrom`, `displayParentSessionId`) are
stored inside each chat's own file as chat IDs, so copying the files keeps the whole tree intact.

## Requirements

- Python 3.8+ (standard library only)
- Claude desktop app with the Code tab. **Tested on Windows**, both the Microsoft Store
  build and the regular installer layout. The macOS / Linux paths are best guesses: pass
  `--app-data` if auto-detection fails, and please open an issue with what you find.

## Use it

### 1. While still signed in to the OLD account

```
git clone https://github.com/UnknownHacker1/claude-code-account-migration
cd claude-code-account-migration
python pack.py
```

This writes `pack/`, a read-only snapshot: the sidebar layer for every account ever used on
the machine, a backup of your CLI settings, skills and memory, an inventory of every
transcript, an index of every chat with its fork parent, and the list of connectors you use.
It never copies `.credentials.json` or OAuth token caches.

Transcripts are **not** copied (they can be many GB, and they stay where they are). If you
want a full backup anyway, copy `~/.claude/projects` yourself.

### 2. Switch accounts

In the Claude app, sign out and sign in with the new account. Open the Code tab.

### 3. Hand off to Claude (easiest)

Paste the prompt from [HANDOFF_PROMPT.md](HANDOFF_PROMPT.md) into a new chat, with `<KIT>`
replaced by the folder you cloned into. Claude runs the dry run, asks about connectors,
arms the migration, and has you quit the app once. The migration runs while the app is
closed, the app reopens by itself, and Claude reads you the result.

### 3b. Or by hand

```
python migrate.py                          # dry run: shows exactly what would change
python migrate.py --apply --when-closed    # arm it, then quit Claude (tray icon > Quit)
```

`--when-closed` starts a small background process that waits for the desktop app to exit,
runs the migration, writes `pack/last-run.log`, and reopens Claude. You can also quit Claude
yourself and run `python migrate.py --apply` from a normal terminal.

### 4. Connectors

Connector sign-ins (Gmail, Drive, Slack, ...) belong to the account and can't be copied.
Reconnect them in the new account (claude.ai > Settings > Connectors). `pack/connectors-to-reconnect.json`
lists the ones you used. If you connect them before step 3, the migration remaps them in the
same pass. If you connect them later, start one new chat, then run:

```
python migrate.py --remap-connectors --apply --when-closed
```

### 5. Terminal CLI

Run `claude`, then `/login` with the new account. `claude --resume` already shows the same
chats, because it reads the same `~/.claude`.

## Undo

Every `--apply` saves a backup and prints its rollback command:

```
python migrate.py --rollback restore-backups/<timestamp>
```

The old account's folder is never modified, so signing back in to the old account still
shows everything.

## What it changes

- Copies `claude-code-sessions/<old>/<old-org>/*` into the new account's folder (skipping
  any file that is already there, and skipping account-only files).
- Merges `scheduled-tasks.json` by task id.
- Copies cowork sessions (`local-agent-mode-sessions/<old>/<old-org>/*`).
- In `claude_desktop_config.json`, copies every preference keyed by the old account / org
  (groups, sidebar sections, per-account toggles) to the new key. It merges groups if the new
  account already has some. It skips server-decided gates such as permission-mode availability.
- Replaces old connector UUIDs with the new ones in the migrated chats, matched by connector name.

## What can't move

Anything stored on Anthropic's servers under the old account: claude.ai web chats and
Projects, published Artifacts, cloud sessions, cloud routines, org plugin catalog, usage
history, Remote Control pairing.

## Files

| File | What |
|---|---|
| `pack.py` | Snapshot (run on the old account). Refuses to re-pack after you switch, so the new account isn't recorded as the old one. |
| `migrate.py` | Migration. Dry run by default; `--apply`, `--when-closed`, `--remap-connectors`, `--rollback`. |
| `common.py` | Path discovery, app-running check, detached waiter. |
| `HANDOFF_PROMPT.md` | The prompt to paste into Claude on the new account. |

## License

MIT
