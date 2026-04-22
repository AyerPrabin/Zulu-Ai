# zulu_pc.py — ZULU PC Control Module v1.0
import os, re, json, time, shutil, ctypes, datetime, subprocess, webbrowser, threading
from zulu_core import zlog, ZMEM, ZSTATE, ZBUS

# ─────────────────────────────────────────────────────────────────────────────
# 📂 PATHS
# ─────────────────────────────────────────────────────────────────────────────
SCREENSHOTS_DIR = r"D:\AI_Agency_Work\Screenshots"
REMEMBER_FILE   = r"D:\AI_Agency_Work\System_Logs\zulu_remember.json"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(REMEMBER_FILE), exist_ok=True)

# Resolve Windows env vars for user-specific paths
_LA = os.environ.get("LOCALAPPDATA",  r"C:\Users\User\AppData\Local")
_AP = os.environ.get("APPDATA",       r"C:\Users\User\AppData\Roaming")

# ─────────────────────────────────────────────────────────────────────────────
# 🗺️ APP MAP — name → executable
#   Add your own apps here. Values can be:
#     - just "calc.exe"  (anything on PATH)
#     - full path string
# ─────────────────────────────────────────────────────────────────────────────
APP_MAP = {
    # Browsers
    "chrome"       : r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "google chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "firefox"      : r"C:\Program Files\Mozilla Firefox\firefox.exe",
    "edge"         : rf"{_LA}\Microsoft\Edge\Application\msedge.exe",

    # Code editors
    "vscode"       : rf"{_LA}\Programs\Microsoft VS Code\Code.exe",
    "vs code"      : rf"{_LA}\Programs\Microsoft VS Code\Code.exe",
    "code"         : rf"{_LA}\Programs\Microsoft VS Code\Code.exe",
    "pycharm"      : r"C:\Program Files\JetBrains\PyCharm Community Edition 2024.3\bin\pycharm64.exe",
    "notepad"      : "notepad.exe",
    "notepad++"    : r"C:\Program Files\Notepad++\notepad++.exe",

    # Media
    "spotify"      : rf"{_AP}\Spotify\Spotify.exe",
    "vlc"          : r"C:\Program Files\VideoLAN\VLC\vlc.exe",

    # Comms
    "discord"      : rf"{_LA}\Discord\Update.exe",
    "telegram"     : rf"{_AP}\Telegram Desktop\Telegram.exe",
    "whatsapp"     : rf"{_LA}\WhatsApp\WhatsApp.exe",

    # Windows built-ins
    "calculator"   : "calc.exe",
    "calc"         : "calc.exe",
    "paint"        : "mspaint.exe",
    "explorer"     : "explorer.exe",
    "file explorer": "explorer.exe",
    "task manager" : "taskmgr.exe",
    "taskmgr"      : "taskmgr.exe",
    "cmd"          : "cmd.exe",
    "terminal"     : "wt.exe",
    "powershell"   : "powershell.exe",
    "snipping tool": "SnippingTool.exe",

    # Office
    "word"         : r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
    "excel"        : r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
    "powerpoint"   : r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",

    # Games / streaming
    "steam"        : r"C:\Program Files (x86)\Steam\steam.exe",
    "obs"          : r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
}

# Process names for close_app (what psutil sees)
_PROC_MAP = {
    "chrome": "chrome", "google chrome": "chrome",
    "firefox": "firefox", "edge": "msedge",
    "vscode": "code", "vs code": "code", "code": "code",
    "pycharm": "pycharm64", "notepad": "notepad", "notepad++": "notepad++",
    "spotify": "spotify", "vlc": "vlc",
    "discord": "discord", "telegram": "telegram",
    "calculator": "calculatorapp", "calc": "calculatorapp",
    "paint": "mspaint", "explorer": "explorer",
    "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
    "steam": "steam", "obs": "obs64",
}

# ─────────────────────────────────────────────────────────────────────────────
# 🔧 OPTIONAL IMPORT GUARDS
# ─────────────────────────────────────────────────────────────────────────────
try:
    import pyautogui
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False

try:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    PYCAW_OK = True
except ImportError:
    PYCAW_OK = False

try:
    import screen_brightness_control as _sbc
    SBC_OK = True
except ImportError:
    SBC_OK = False

try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False


# ─────────────────────────────────────────────────────────────────────────────
# 🖥️  1. APP CONTROL
# ─────────────────────────────────────────────────────────────────────────────

def open_app(name: str) -> str:
    """Open an application by name. Fuzzy-matches APP_MAP."""
    key = name.lower().strip()

    # Exact match first, then substring match
    path = APP_MAP.get(key)
    if not path:
        for k, v in APP_MAP.items():
            if key in k or k in key:
                path = v
                break

    if not path:
        return (f"❌ App not found: '{name}'\n"
                f"   Add it to APP_MAP in zulu_pc.py")

    try:
        # If it's a full path, check it exists
        parts = path.split()
        exe   = parts[0]
        args  = parts[1:]
        if os.path.isabs(exe) and not os.path.isfile(exe):
            # Try os.startfile as fallback (handles UWP apps like Calculator)
            os.startfile(exe) if os.path.exists(exe) else subprocess.Popen(path, shell=True)
        elif os.path.isfile(exe):
            subprocess.Popen([exe] + args, shell=False,
                             creationflags=subprocess.DETACHED_PROCESS)
        else:
            subprocess.Popen(path, shell=True)
        zlog("pc", f"Opened: {name}")
        return f"✅ Opening {name.title()}..."
    except Exception as e:
        zlog("pc", f"open_app error [{name}]: {e}", "ERROR")
        return f"❌ Failed to open {name}: {e}"


def close_app(name: str) -> str:
    """Terminate a running process by name."""
    if not PSUTIL_OK:
        return "❌ psutil not installed — run: pip install psutil"

    key      = name.lower().strip().replace(".exe", "")
    proc_key = _PROC_MAP.get(key, key)
    killed   = []

    for proc in psutil.process_iter(["name", "pid"]):
        try:
            pn = proc.info["name"].lower().replace(".exe", "")
            if proc_key in pn or pn in proc_key:
                proc.terminate()
                killed.append(proc.info["name"])
        except Exception:
            pass

    if killed:
        zlog("pc", f"Closed processes: {list(set(killed))}")
        return f"✅ Closed: {', '.join(set(killed))}"
    return f"❌ No running process found for: '{name}'"


# ─────────────────────────────────────────────────────────────────────────────
# 🔊  2. VOLUME CONTROL
# ─────────────────────────────────────────────────────────────────────────────

def _get_vol_iface():
    devices   = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return interface.QueryInterface(IAudioEndpointVolume)


def _ps_vol_key(key: int):
    """Send a virtual key via PowerShell WScript (fallback when pycaw missing)."""
    subprocess.run(
        ["powershell", "-c",
         f"(New-Object -ComObject WScript.Shell).SendKeys([char]{key})"],
        timeout=3, capture_output=True
    )


def volume_up(pct: int = 10) -> str:
    if PYCAW_OK:
        try:
            v   = _get_vol_iface()
            cur = v.GetMasterVolumeLevelScalar()
            v.SetMasterVolumeLevelScalar(min(1.0, cur + pct / 100), None)
            return f"🔊 Volume: {int(min(1.0, cur + pct/100) * 100)}%"
        except Exception as e:
            return f"❌ Volume error: {e}"
    _ps_vol_key(175)  # VK_VOLUME_UP
    return f"🔊 Volume up (+{pct})"


def volume_down(pct: int = 10) -> str:
    if PYCAW_OK:
        try:
            v   = _get_vol_iface()
            cur = v.GetMasterVolumeLevelScalar()
            v.SetMasterVolumeLevelScalar(max(0.0, cur - pct / 100), None)
            return f"🔊 Volume: {int(max(0.0, cur - pct/100) * 100)}%"
        except Exception as e:
            return f"❌ Volume error: {e}"
    _ps_vol_key(174)  # VK_VOLUME_DOWN
    return f"🔊 Volume down (-{pct})"


def set_volume(level: int) -> str:
    if not PYCAW_OK:
        return "❌ pycaw not installed — run: pip install pycaw comtypes"
    try:
        v = _get_vol_iface()
        v.SetMasterVolumeLevelScalar(max(0, min(100, level)) / 100, None)
        return f"🔊 Volume set to {level}%"
    except Exception as e:
        return f"❌ Volume error: {e}"


def toggle_mute() -> str:
    if PYCAW_OK:
        try:
            v      = _get_vol_iface()
            muted  = v.GetMute()
            v.SetMute(not muted, None)
            return "🔇 Muted" if not muted else "🔊 Unmuted"
        except Exception as e:
            return f"❌ Mute error: {e}"
    _ps_vol_key(173)  # VK_VOLUME_MUTE
    return "🔇 Volume toggled mute"


def get_volume() -> str:
    if not PYCAW_OK:
        return "❌ pycaw not installed"
    try:
        v     = _get_vol_iface()
        level = int(v.GetMasterVolumeLevelScalar() * 100)
        muted = v.GetMute()
        return f"🔊 Volume: {level}%{'  🔇 (muted)' if muted else ''}"
    except Exception as e:
        return f"❌ Volume error: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# 🔒  3. SYSTEM CONTROL
# ─────────────────────────────────────────────────────────────────────────────

def lock_screen() -> str:
    try:
        ctypes.windll.user32.LockWorkStation()
        zlog("pc", "Screen locked")
        return "🔒 Screen locked."
    except Exception as e:
        return f"❌ Lock error: {e}"


def sleep_pc() -> str:
    try:
        # SetSuspendState(Suspend=False, Force=False, DisableWakeEvent=False)
        subprocess.Popen(
            ["powershell", "-c",
             "Add-Type -Assembly System.Windows.Forms; "
             "[System.Windows.Forms.Application]::SetSuspendState('Suspend',$false,$false)"],
            shell=False
        )
        zlog("pc", "Sleep initiated")
        return "😴 Going to sleep..."
    except Exception as e:
        return f"❌ Sleep error: {e}"


def shutdown_pc(delay_secs: int = 60) -> str:
    try:
        subprocess.run(["shutdown", "/s", "/t", str(delay_secs)], check=True)
        zlog("pc", f"Shutdown in {delay_secs}s")
        return (f"💻 Shutdown in {delay_secs}s.\n"
                f"Send ZULU CANCEL SHUTDOWN to abort.")
    except Exception as e:
        return f"❌ Shutdown error: {e}"


def cancel_shutdown() -> str:
    try:
        subprocess.run(["shutdown", "/a"], check=True)
        return "✅ Shutdown cancelled."
    except Exception as e:
        return f"❌ Cancel error: {e}"


def restart_pc(delay_secs: int = 60) -> str:
    try:
        subprocess.run(["shutdown", "/r", "/t", str(delay_secs)], check=True)
        return f"🔄 Restarting in {delay_secs}s."
    except Exception as e:
        return f"❌ Restart error: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# ☀️  4. BRIGHTNESS
# ─────────────────────────────────────────────────────────────────────────────

def set_brightness(level: int) -> str:
    if not SBC_OK:
        return "❌ Not installed — run: pip install screen-brightness-control"
    try:
        _sbc.set_brightness(max(0, min(100, level)))
        return f"☀️ Brightness: {level}%"
    except Exception as e:
        return f"❌ Brightness error: {e}"


def get_brightness() -> str:
    if not SBC_OK:
        return "❌ screen-brightness-control not installed"
    try:
        b = _sbc.get_brightness(display=0)
        val = b[0] if isinstance(b, list) else b
        return f"☀️ Current brightness: {val}%"
    except Exception as e:
        return f"❌ Brightness error: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# 📸  5. SCREENSHOT
# ─────────────────────────────────────────────────────────────────────────────

def take_screenshot(filename: str = None) -> str:
    """
    Takes a full screenshot, saves to SCREENSHOTS_DIR.
    Returns the saved file path, or an error string starting with '❌'.
    """
    if not PYAUTOGUI_OK:
        return "❌ pyautogui not installed"
    try:
        os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
        if not filename:
            ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{ts}.png"
        path = os.path.join(SCREENSHOTS_DIR, filename)
        pyautogui.FAILSAFE = False
        img  = pyautogui.screenshot()
        img.save(path)
        size = os.path.getsize(path) // 1024
        zlog("pc", f"Screenshot saved: {path} ({size}KB)")
        return path
    except Exception as e:
        zlog("pc", f"Screenshot error: {e}", "ERROR")
        return f"❌ Screenshot error: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# 🌐  6. BROWSER CONTROL
# ─────────────────────────────────────────────────────────────────────────────

def open_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    zlog("pc", f"Opened URL: {url}")
    return f"🌐 Opened: {url}"


def google_search(query: str) -> str:
    import urllib.parse
    url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
    webbrowser.open(url)
    return f"🔍 Googling: {query}"


def youtube_search(query: str) -> str:
    import urllib.parse
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    webbrowser.open(url)
    return f"▶️ YouTube: {query}"


def youtube_play(query: str) -> str:
    """Open YouTube and search — user presses play on first result."""
    return youtube_search(query)


# ─────────────────────────────────────────────────────────────────────────────
# 📋  7. CLIPBOARD
# ─────────────────────────────────────────────────────────────────────────────

def read_clipboard() -> str:
    """Returns clipboard text content, max 2000 chars."""
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
        if not data or not data.strip():
            return "📋 Clipboard is empty."
        return data.strip()[:2000]
    except Exception as e:
        return f"❌ Clipboard read error: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# 📁  8. SMART FILE OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

# Folders to skip when searching (speed + safety)
_SKIP_DIRS = {
    "windows", "$recycle.bin", "system volume information",
    "program files", "program files (x86)", "programdata",
    ".git", "__pycache__", "node_modules", "venv", ".venv",
}


def find_file(name: str, search_dir: str = r"D:\\", max_results: int = 8) -> str:
    """Recursively search for files matching name (case-insensitive)."""
    name_lower = name.lower()
    found      = []

    try:
        for root, dirs, files in os.walk(search_dir):
            # Prune skip dirs in-place (fast)
            dirs[:] = [d for d in dirs
                       if d.lower() not in _SKIP_DIRS and not d.startswith(".")]
            for f in files:
                if name_lower in f.lower():
                    found.append(os.path.join(root, f))
                    if len(found) >= max_results:
                        break
            if len(found) >= max_results:
                break
    except PermissionError:
        pass
    except Exception as e:
        return f"❌ Search error: {e}"

    if not found:
        return f"❌ '{name}' not found under {search_dir}"

    lines = [f"🔍 Found {len(found)} file(s) for '{name}':"]
    for p in found:
        lines.append(f"  📄 {p}")
    if len(found) == max_results:
        lines.append(f"  (showing first {max_results} — be more specific to narrow down)")
    return "\n".join(lines)


def open_file(path: str) -> str:
    """Open a file with its default application."""
    if not os.path.exists(path):
        return f"❌ File not found: {path}"
    try:
        os.startfile(path)
        return f"📂 Opened: {os.path.basename(path)}"
    except Exception as e:
        return f"❌ Open error: {e}"


def read_file_summary(path: str, max_chars: int = 1000) -> str:
    """Read a text file and return its content (truncated)."""
    if not os.path.exists(path):
        return f"❌ File not found: {path}"
    ext = os.path.splitext(path)[1].lower()
    readable_exts = {".txt", ".py", ".js", ".ts", ".html", ".css", ".json",
                     ".csv", ".md", ".log", ".xml", ".yaml", ".yml", ".ini", ".cfg"}
    if ext not in readable_exts:
        return f"❌ Can't read binary file ({ext}). Open it with: ZULU OPEN FILE {path}"
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        size    = len(content)
        preview = content[:max_chars]
        suffix  = f"\n\n...{size - max_chars} more characters" if size > max_chars else ""
        return f"📄 {os.path.basename(path)} ({size} chars):\n\n{preview}{suffix}"
    except Exception as e:
        return f"❌ Read error: {e}"


def zip_folder(folder_path: str, output_dir: str = None) -> str:
    """Zip a folder and save alongside it (or to output_dir)."""
    folder_path = folder_path.strip('"\'')
    if not os.path.isdir(folder_path):
        return f"❌ Folder not found: {folder_path}"
    try:
        out_dir = output_dir or os.path.dirname(os.path.abspath(folder_path))
        ts      = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base    = os.path.basename(folder_path.rstrip("\\/"))
        archive = os.path.join(out_dir, f"{base}_{ts}")
        shutil.make_archive(archive, "zip", folder_path)
        final = archive + ".zip"
        size  = os.path.getsize(final) // 1024
        return f"📦 Zipped → {final} ({size} KB)"
    except Exception as e:
        return f"❌ Zip error: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# 🧠  9. REMEMBER SYSTEM  (ZULU REMEMBER / ZULU RECALL / ZULU FORGET)
# ─────────────────────────────────────────────────────────────────────────────

def remember_this(note: str) -> str:
    """Persistently save a personal note."""
    try:
        data = []
        if os.path.exists(REMEMBER_FILE):
            with open(REMEMBER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        data.append({"ts": ts, "note": note})
        data = data[-500:]            # cap at 500 memories
        with open(REMEMBER_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        zlog("pc", f"Remembered: {note[:60]}")
        return f"🧠 Remembered ✅\n\"{note}\""
    except Exception as e:
        return f"❌ Remember error: {e}"


def recall_memories(query: str = "") -> str:
    """Retrieve memories, optionally filtered by keyword."""
    try:
        if not os.path.exists(REMEMBER_FILE):
            return "🧠 Nothing remembered yet. Use: ZULU REMEMBER [note]"
        with open(REMEMBER_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data:
            return "🧠 No memories stored yet."
        if query:
            q    = query.lower()
            data = [d for d in data if q in d["note"].lower()]
            if not data:
                return f"🧠 Nothing remembered about '{query}'."
        total = len(data)
        lines = [f"🧠 Memories ({total} stored):"]
        for d in data[-15:]:          # show most recent 15
            lines.append(f"  [{d['ts']}] {d['note']}")
        if total > 15:
            lines.append(f"  ...and {total - 15} older memories")
        return "\n".join(lines)[:700]
    except Exception as e:
        return f"❌ Recall error: {e}"


def forget_memory(query: str) -> str:
    """Delete memories matching a keyword."""
    try:
        if not os.path.exists(REMEMBER_FILE):
            return "🧠 Nothing to forget."
        with open(REMEMBER_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        q      = query.lower()
        before = len(data)
        data   = [d for d in data if q not in d["note"].lower()]
        removed = before - len(data)
        with open(REMEMBER_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return f"🧠 Forgot {removed} memor{'y' if removed == 1 else 'ies'} about '{query}'."
    except Exception as e:
        return f"❌ Forget error: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# 🧠  COMMAND ROUTER — handle_pc_command(command, user_type) → (bool, str)
#
#  Returns (handled, response).
#  Call BEFORE routing to launch_boardroom().
#  If handled=True → send response directly to WhatsApp (no AI needed).
# ─────────────────────────────────────────────────────────────────────────────

def handle_pc_command(command: str, user_type: str = "BOSS") -> tuple:
    """
    Fast, zero-AI command handler for PC control tasks.
    Returns: (handled: bool, response: str)
    """
    upper = command.upper().strip()
    raw   = command.strip()

    # ─────────────────────────────────────────────────────────────────────────
    # 📸 Screenshot
    # ─────────────────────────────────────────────────────────────────────────
    if re.search(r'\bSCREENSHOT\b|\bTAKE\s+SCREENSHOT\b|\bSNAP\s+(SCREEN|DESKTOP)\b', upper):
        path = take_screenshot()
        if path.startswith("❌"):
            return True, path
        return True, f"📸 Screenshot saved!\n📁 {path}"

    # ─────────────────────────────────────────────────────────────────────────
    # 🖥️  Open app / URL
    # ─────────────────────────────────────────────────────────────────────────
    m = re.match(r'(?:OPEN|LAUNCH|START)\s+(.+)', upper)
    if m:
        arg = raw[m.start(1):m.start(1) + len(m.group(1))].strip()
        # URL?
        if re.match(r'(https?://|www\.)\S+', arg, re.IGNORECASE):
            return True, open_url(arg)
        return True, open_app(arg)

    # ─────────────────────────────────────────────────────────────────────────
    # ❌  Close app
    # ─────────────────────────────────────────────────────────────────────────
    m = re.match(r'(?:CLOSE|KILL|QUIT|EXIT|STOP)\s+(.+)', upper)
    if m:
        arg = raw[m.start(1):m.start(1) + len(m.group(1))].strip()
        return True, close_app(arg)

    # ─────────────────────────────────────────────────────────────────────────
    # 🔊  Volume
    # ─────────────────────────────────────────────────────────────────────────
    if re.search(r'VOLUME\s+UP|TURN\s+(?:IT\s+)?UP|LOUDER', upper):
        pct = int(re.search(r'(\d+)', upper).group(1)) if re.search(r'\d+', upper) else 10
        return True, volume_up(pct)

    if re.search(r'VOLUME\s+DOWN|TURN\s+(?:IT\s+)?DOWN|QUIETER|LOWER\s+(?:THE\s+)?VOLUME', upper):
        pct = int(re.search(r'(\d+)', upper).group(1)) if re.search(r'\d+', upper) else 10
        return True, volume_down(pct)

    if re.search(r'\bMUTE\b|\bUNMUTE\b', upper) and "ZULU MUTE" not in upper and "ZULU UNMUTE" not in upper:
        return True, toggle_mute()

    m = re.search(r'SET\s+VOLUME\s+(?:TO\s+)?(\d+)|VOLUME\s+(\d+)\s*%?', upper)
    if m:
        lvl = int(m.group(1) or m.group(2))
        return True, set_volume(lvl)

    if upper.strip() in ("ZULU VOLUME", "VOLUME"):
        return True, get_volume()

    # ─────────────────────────────────────────────────────────────────────────
    # 🔒  Lock / Sleep / Shutdown
    # ─────────────────────────────────────────────────────────────────────────
    if re.search(r'\bLOCK\s+(SCREEN|PC|COMPUTER|IT)\b|\bLOCK\s+IT\b', upper):
        return True, lock_screen()

    if re.search(r'SLEEP\s+(PC|COMPUTER|THE\s+PC)|\bPUT\s+PC\s+TO\s+SLEEP\b', upper):
        return True, sleep_pc()

    if "CANCEL SHUTDOWN" in upper or "ABORT SHUTDOWN" in upper:
        return True, cancel_shutdown()

    if re.search(r'SHUTDOWN\s+(PC|COMPUTER|THE\s+PC)|\bSHUT\s+DOWN\s+(PC|COMPUTER)\b', upper):
        m2 = re.search(r'IN\s+(\d+)', upper)
        return True, shutdown_pc(int(m2.group(1)) if m2 else 60)

    if re.search(r'RESTART\s+(PC|COMPUTER|THE\s+PC)', upper):
        return True, restart_pc()

    # ─────────────────────────────────────────────────────────────────────────
    # ☀️  Brightness
    # ─────────────────────────────────────────────────────────────────────────
    m = re.search(r'(?:SET\s+)?BRIGHTNESS\s+(?:TO\s+)?(\d+)|BRIGHTNESS\s+(\d+)\s*%?', upper)
    if m:
        lvl = int(m.group(1) or m.group(2))
        return True, set_brightness(lvl)

    if upper.strip() in ("ZULU BRIGHTNESS", "BRIGHTNESS"):
        return True, get_brightness()

    # ─────────────────────────────────────────────────────────────────────────
    # 🌐  Browser
    # ─────────────────────────────────────────────────────────────────────────
    if re.search(r'\bOPEN\s+(HTTPS?://|WWW\.)', upper):
        m = re.search(r'(https?://\S+|www\.\S+)', raw, re.IGNORECASE)
        if m:
            return True, open_url(m.group(1))

    m = re.search(r'(?:GOOGLE|SEARCH\s+(?:GOOGLE\s+)?(?:FOR\s+)?)\s+(.+)', upper)
    if m and "ZULU GOOGLE" not in upper[:11]:
        q = raw[m.start(1):m.start(1) + len(m.group(1))].strip()
        if q:
            return True, google_search(q)

    m = re.search(
        r'(?:SEARCH\s+YOUTUBE\s+(?:FOR\s+)?'
        r'|YOUTUBE\s+SEARCH\s+(?:FOR\s+)?'
        r'|PLAY\s+ON\s+YOUTUBE\s+)'
        r'(.+)', upper)
    if m:
        q = raw[m.start(1):m.start(1) + len(m.group(1))].strip()
        if q:
            return True, youtube_search(q)

    # ─────────────────────────────────────────────────────────────────────────
    # 📋  Clipboard
    # ─────────────────────────────────────────────────────────────────────────
    if re.search(r'READ\s+CLIPBOARD|WHAT.S\s+IN\s+(?:MY\s+)?CLIPBOARD|ZULU\s+CLIPBOARD', upper):
        content = read_clipboard()
        if content.startswith("❌") or content == "📋 Clipboard is empty.":
            return True, content
        return True, f"📋 Clipboard content:\n\n{content[:600]}"

    # ─────────────────────────────────────────────────────────────────────────
    # 📁  File ops
    # ─────────────────────────────────────────────────────────────────────────
    m = re.match(r'(?:ZULU\s+)?FIND\s+(.+)', upper)
    if m:
        fname = raw[m.start(1):m.start(1) + len(m.group(1))].strip()
        return True, find_file(fname)

    m = re.match(r'(?:ZULU\s+)?READ\s+FILE\s+(.+)', upper)
    if m:
        fpath = raw[m.start(1):m.start(1) + len(m.group(1))].strip().strip('"')
        return True, read_file_summary(fpath)

    m = re.match(r'(?:ZULU\s+)?OPEN\s+FILE\s+(.+)', upper)
    if m:
        fpath = raw[m.start(1):m.start(1) + len(m.group(1))].strip().strip('"')
        return True, open_file(fpath)

    m = re.match(r'(?:ZULU\s+)?ZIP\s+(.+)', upper)
    if m:
        folder = raw[m.start(1):m.start(1) + len(m.group(1))].strip()
        return True, zip_folder(folder)

    # ─────────────────────────────────────────────────────────────────────────
    # 🧠  Remember / Recall / Forget
    # ─────────────────────────────────────────────────────────────────────────
    m = re.match(r'(?:ZULU\s+)?REMEMBER\s+(.+)', upper)
    if m:
        note = raw[m.start(1):m.start(1) + len(m.group(1))].strip()
        return True, remember_this(note)

    if re.match(r'(?:ZULU\s+)?RECALL(\s+.+)?$', upper) or \
       re.match(r'(?:ZULU\s+)?WHAT\s+DID\s+I\s+REMEMBER(\s+.+)?$', upper) or \
       upper.strip() in ("ZULU MEMORIES", "MEMORIES", "ZULU RECALL"):
        query = ""
        m = re.search(r'(?:RECALL|REMEMBER|MEMORIES)\s+(.+)', upper)
        if m:
            query = raw[m.start(1):m.start(1) + len(m.group(1))].strip()
        return True, recall_memories(query)

    m = re.match(r'(?:ZULU\s+)?FORGET\s+(.+)', upper)
    if m:
        query = raw[m.start(1):m.start(1) + len(m.group(1))].strip()
        return True, forget_memory(query)

    # ─────────────────────────────────────────────────────────────────────────
    # Not a PC command — let boardroom handle it
    # ─────────────────────────────────────────────────────────────────────────
    return False, ""
