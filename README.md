# claude-code-account-migration

Switching to a new Claude account on the same computer? This moves your whole Claude Code
desktop sidebar across: every chat, title, group, section, star, and fork / parent / child
link. It also sets up your connectors cleanly on the new account, through Composio by default.

You don't run anything by hand. You paste one prompt into Claude, and Claude walks you
through it one small step at a time.

Unofficial. Not made by or affiliated with Anthropic. It reads and writes the desktop app's
local files, which can change between app versions. Every change is backed up and can be undone.

## Start here (2 prompts, 1 log-out)

### Step 1: on your OLD account

1. Open the Claude app, go to the **Code** tab, and start a new chat.
2. Copy everything in [`prompts/start_on_old_account.txt`](prompts/start_on_old_account.txt), paste it in, and send.
3. Follow along. Claude will:
   - download this tool,
   - ask how you want your connectors (Composio or normal ones),
   - take a read-only snapshot of your sidebar (`pack/`),
   - write **`NEXT_PROMPT.txt`**, a second prompt filled in with your paths and your apps,
   - tell you how to log out and log in with the new account.

### Step 2: switch accounts

Log out of the Claude app, then log in with the new account. Your sidebar looks empty. That's expected.

### Step 3: on your NEW account

1. Code tab, new chat.
2. Open `NEXT_PROMPT.txt` (in the tool's folder), copy all of it, paste it in, and send.
3. Follow along. Claude will:
   - check what's coming back,
   - arm the migration and have you **quit Claude once** (tray icon > Quit). It runs while the
     app is closed, then the app reopens by itself with your old sidebar,
   - set up connectors: add the single Composio connector, then connect each of your apps
     (Gmail, Drive, Slack, ...) one at a time, each account with a clear alias. It ends with a
     table of everything connected,
   - have you quit once more so old chats point at the new Composio connector,
   - get the terminal `claude` CLI signed in to the new account.

That's it.

## Why this is needed

| | Where | Tied to the account? |
|---|---|---|
| Chat transcripts, subagents, memory, skills, settings | `~/.claude/` | No. Every account on the computer shares it. |
| The sidebar: chat list, titles, groups, sections, stars, fork links, cowork sessions | Desktop app data: `claude-code-sessions/<account>/<org>/`, plus prefs keyed by `<account>/<org>` | **Yes** |

Your chats never leave the disk, but the new account can't see them in the sidebar. This tool
re-files the sidebar layer under the new account. Fork and parent links are stored inside
each chat's own file, so the whole tree comes across unchanged.

## Why Composio for connectors

Connector sign-ins belong to the old account and can't be copied, so they need setting up
again anyway. Instead of 15+ separate connectors, you add **one** connector (Composio) and
connect each app account inside it with an alias like `personal` or `work`. Several accounts
per app work fine (two Gmails, two Slacks). Run `python pack.py --native-connectors`
instead if you'd rather reconnect normal connectors one by one.

## Requirements

- Python 3.8+ (Claude installs it with you if it's missing)
- The Claude desktop app with the Code tab
- **Tested on Windows**, including the Microsoft Store build. The macOS / Linux paths are best
  guesses; pass `--app-data <folder>` if auto-detection fails, and please open an issue.

## Commands (what the prompts run for you)

```
python pack.py [--native-connectors]   # OLD account: read-only snapshot + NEXT_PROMPT.txt
python migrate.py                      # NEW account: dry run, shows exactly what would change
python migrate.py --apply --when-closed --only-connectors Composio
                                       # waits for Claude to quit, migrates, logs, reopens Claude
python migrate.py --remap-connectors --apply --when-closed --only-connectors Composio
                                       # after Composio is connected: point old chats at it
python migrate.py --rollback restore-backups/<timestamp>
```

The result of each run is in `pack/last-run.log`. `pack.py` refuses to run again once you've
switched, so the new account can't be recorded as the old one by mistake.

## What it changes

- Copies `claude-code-sessions/<old>/<old-org>/*` into the new account's folder. It never
  overwrites, and skips account-only files. Merges `scheduled-tasks.json` by task id.
- Copies cowork sessions (`local-agent-mode-sessions/<old>/<old-org>/*`).
- In `claude_desktop_config.json`, copies every preference keyed by the old account / org
  (groups, sidebar sections, per-account toggles) to the new key. It merges groups if the new
  account already has some, and skips server-decided gates.
- Swaps old connector IDs for the new account's in the migrated chats, matched by connector
  name (only Composio, with `--only-connectors Composio`).
- Never touches `.credentials.json`, OAuth tokens, transcripts, or the old account's folder.
  Signing back in to the old account still shows everything.

## What can't move

Anything on Anthropic's servers under the old account: claude.ai web chats and Projects,
published Artifacts, cloud sessions and routines, the org plugin catalog, usage history, and
Remote Control pairing.

## Files

| File | What |
|---|---|
| `prompts/start_on_old_account.txt` | Prompt 1: paste on the old account |
| `prompts/new_account.txt` + `part2_*.txt` | Template that `pack.py` fills in as `NEXT_PROMPT.txt` |
| `pack.py` | Snapshot + writes `NEXT_PROMPT.txt` |
| `migrate.py` | The migration (dry run by default) |
| `common.py` | Path discovery, app-running check, the background waiter |

## License

MIT
