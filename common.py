"""Shared helpers: find the Claude desktop data folder, the signed-in account, and whether the app is running."""
import glob, json, os, subprocess, sys

WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"
NO_WINDOW = 0x08000000 if WINDOWS else 0  # CREATE_NO_WINDOW


def cli_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def cli_global_config():
    """~/.claude.json (or $CLAUDE_CONFIG_DIR/.claude.json)."""
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        return os.path.join(os.environ["CLAUDE_CONFIG_DIR"], ".claude.json")
    return os.path.join(os.path.expanduser("~"), ".claude.json")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(p, obj):
    tmp = p + ".tmp-migrate"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def find_app_data(override=None):
    """The desktop app folder that holds claude-code-sessions/."""
    if override:
        if not os.path.isdir(os.path.join(override, "claude-code-sessions")):
            sys.exit(f"No claude-code-sessions folder in {override}")
        return override
    home = os.path.expanduser("~")
    cands = []
    if WINDOWS:
        la, ra = os.environ.get("LOCALAPPDATA", ""), os.environ.get("APPDATA", "")
        cands += glob.glob(os.path.join(la, "Claude-Data", "claude_*"))  # Microsoft Store / MSIX install
        cands += [os.path.join(ra, "Claude"), os.path.join(la, "Claude")]
    elif MAC:
        cands += [os.path.join(home, "Library", "Application Support", "Claude")]
    else:
        cands += [os.path.join(home, ".config", "Claude")]
    found = [c for c in cands if os.path.isdir(os.path.join(c, "claude-code-sessions"))]
    if not found:
        sys.exit("Could not find the Claude desktop data folder (one containing claude-code-sessions). "
                 "Pass --app-data <folder>.")
    found.sort(key=lambda c: os.path.getmtime(os.path.join(c, "claude-code-sessions")), reverse=True)
    return found[0]


def signed_in_account():
    """(accountUuid, organizationUuid, displayName) of whoever Claude Code is signed in as."""
    try:
        a = load(cli_global_config()).get("oauthAccount", {}) or {}
        return a.get("accountUuid"), a.get("organizationUuid"), a.get("displayName")
    except Exception:
        return None, None, None


def desktop_running():
    """True while the Claude desktop app (not a Claude Code CLI) is running."""
    if os.environ.get("MIGRATE_SANDBOX_TEST") == "1":
        return False
    if WINDOWS:
        ps = ("@(Get-Process claude -ErrorAction SilentlyContinue | "
              "Where-Object { $_.Path -and $_.Path -notmatch 'claude-code' }).Count")
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, creationflags=NO_WINDOW).stdout.strip()
        return out not in ("", "0")
    if MAC:
        return subprocess.run(["pgrep", "-f", "Claude.app/Contents/MacOS/Claude"], capture_output=True).returncode == 0
    return subprocess.run(["pgrep", "-if", "claude-desktop|/Claude "], capture_output=True).returncode == 0


def pid_alive(pid):
    if WINDOWS:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                             creationflags=NO_WINDOW).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def relaunch_command():
    """A command line that reopens the desktop app, captured while it is still running."""
    if WINDOWS:
        ps = "(Get-StartApps | Where-Object { $_.Name -eq 'Claude' } | Select-Object -First 1).AppID"
        appid = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                               creationflags=NO_WINDOW).stdout.strip()
        if appid:
            return f'explorer.exe "shell:AppsFolder\\{appid}"'
        ps = ("(Get-Process claude -ErrorAction SilentlyContinue | "
              "Where-Object { $_.Path -and $_.Path -notmatch 'claude-code' } | Select-Object -First 1).Path")
        exe = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                             creationflags=NO_WINDOW).stdout.strip()
        return f'"{exe}"' if exe else ""
    if MAC:
        return "open -a Claude"
    return ""


def spawn_detached(argv):
    """Start a process that survives the Claude app quitting (the app kills its own child processes)."""
    if WINDOWS:
        exe = argv[0]
        pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.basename(exe).lower() == "python.exe" and os.path.exists(pyw):
            argv = [pyw] + argv[1:]
        # Go through a hidden PowerShell: WMI cannot start Microsoft Store "app execution alias" Pythons directly.
        import base64
        q = lambda s: "'" + str(s).replace("'", "''") + "'"
        inner = "& " + " ".join(q(a) for a in argv)
        enc = base64.b64encode(inner.encode("utf-16-le")).decode()
        cmdline = f"powershell.exe -NoProfile -WindowStyle Hidden -EncodedCommand {enc}"
        env = dict(os.environ, MIGRATE_CMDLINE=cmdline)
        # Win32_Process.Create runs the process outside the app's job object, so it is not killed on quit.
        ps = ("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
              "-Arguments @{CommandLine=$env:MIGRATE_CMDLINE}; $r.ReturnValue; $r.ProcessId")
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                             env=env, creationflags=NO_WINDOW).stdout.split()
        if not out or out[0] != "0":
            sys.exit("Could not start the background waiter: " + " ".join(out))
        return int(out[1])
    p = subprocess.Popen(["nohup"] + argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    return p.pid
