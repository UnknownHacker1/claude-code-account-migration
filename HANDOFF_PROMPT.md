# The handoff prompt

Paste this as the first message in a new Code-tab chat **after** you have signed in to the
new account. Replace `<KIT>` with the folder you cloned this repo into, the one that
holds `pack\` from step 1 of the README.

---

```
I just moved Claude Code from my old account to this one, on the same computer. My old
chats are still on disk, but the sidebar is tied to the account, so it's empty here. A kit
that fixes this is in <KIT>. Its pack\ folder was made while I was still on the old
account. Never run pack.py now: it would record this account as the old one.

Do this, step by step, and keep me posted in short messages:

1. Read <KIT>\README.md and <KIT>\pack\MANIFEST.json. Tell me how many chats, forks and
   connectors the old account had.
2. Dry run: python "<KIT>\migrate.py". Show me the summary. If it can't find the new
   account, tell me what it says and stop.
3. Look at the "not connected in the new account yet" line. Ask me if I want to connect
   those connectors first (claude.ai > Settings > Connectors). If I do, wait for me to say
   they're done, then rerun the dry run.
4. Arm it: python "<KIT>\migrate.py" --apply --when-closed
   Then tell me in one line to quit Claude completely (tray icon > Quit). It runs while
   Claude is closed, then reopens Claude by itself.
5. When I'm back in this chat, read <KIT>\pack\last-run.log and tell me the VERIFY lines
   and the RESULT line. If anything failed, show me the rollback command from the log, and
   don't run it unless I say so.
6. If any connectors were still missing, help me connect them. Then arm
   python "<KIT>\migrate.py" --remap-connectors --apply --when-closed
   and have me quit once more.

Rules: never touch .credentials.json. Never delete the old account's folder. Never run
--rollback unless I ask.
```
