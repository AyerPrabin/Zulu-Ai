# zulu_tray.py — ZULU SENTINEL v13.6  (10 instant commands added)
from zulu_core import ZMEM, ZSTATE, ZBUS, zlog
import time, os, re, uuid, json, datetime, threading, subprocess, ctypes
import win32gui, win32con, win32clipboard, win32api
import win32process
import pyautogui
from pywinauto import Desktop

try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False

try:
    import pythoncom
except Exception:
    pythoncom = None

try:
    import pystray
    from PIL import Image, ImageDraw
    PYSTRAY_OK = True
except Exception:
    PYSTRAY_OK = False

try:
    import requests as _requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

from boardroom_engine import launch_boardroom, set_boss_chat, build_llm
from brain_manager import get_status_report as _get_status_report_raw, check_all_pings, auto_restore, mark_offline, get_learn_report

def get_status_report():
    """Safe wrapper — catches ZeroDivisionError from brain_manager.get_usage_bar
    when a brain has limit=0 (e.g. unconfigured or quota-reset brain)."""
    try:
        return _get_status_report_raw()
    except ZeroDivisionError:
        return ("⚠️ ZULU Brain Status\n"
                "─────────────────────\n"
                "One or more AI brains has a zero usage limit (not yet configured).\n"
                "Run ZULU PING to re-check, or review brain_manager.py brain configs.")
    except Exception as _e:
        return f"⚠️ Status report error: {_e}"
from agency_config import TRIGGER_WORD, OFF_CMD

pyautogui.FAILSAFE = False

# ─────────────────────────────────────────────────────────────────────────────
# ⚙️ CONFIG
# ─────────────────────────────────────────────────────────────────────────────
MONITORED_CHATS = {
    "773818"     : "BOSS",
    "6454018"    : "GF",
    "Chutiya Plus": "GF",
    "Chutiya"    : "GF",
    "Mummy"      : "FAMILY",
}

MASTER_CODE        = "zulu2006"
WA_LEFT            = 100
WA_TOP             = 100
WA_WIDTH           = 1100
WA_HEIGHT          = 750
REQUESTS_LOG       = r"D:\AI_Agency_Work\System_Logs\unknown_requests.txt"
IDLE_TIMEOUT       = 120
ACTIVATION_TIMEOUT = 1800

# PRESENCE_MODE lives in ZSTATE — "always" or "auto"
PRESENCE_IDLE = 300

# Dashboard live push URL
DASHBOARD_URL  = "http://localhost:5050/api/push"
DASHBOARD_PUSH = True

# ─────────────────────────────────────────────────────────────────────────────
# 🔒 THREADING LOCKS
# ─────────────────────────────────────────────────────────────────────────────
_lock_seen      = threading.Lock()
_lock_webview2  = threading.Lock()
_lock_presence  = threading.Lock()
_lock_boardroom = threading.Lock()

# ─────────────────────────────────────────────────────────────────────────────
# 🌐 STATE — lives in ZSTATE (shared brain)
# ─────────────────────────────────────────────────────────────────────────────
ZSTATE.set("is_active",     True)
ZSTATE.set("presence_mode", "always")

last_seen_msgs   = {}
user_sessions    = {}
activated_users  = {}
elevated_users   = set()
_first_scan_done = False   # silent first scan

# ─────────────────────────────────────────────────────────────────────────────
# 📡 LIVE DASHBOARD PUSH  (non-blocking fire-and-forget)
# ─────────────────────────────────────────────────────────────────────────────
def push_event(event_type: str, data: dict):
    if not DASHBOARD_PUSH or not REQUESTS_OK:
        return
    payload = {
        "type": event_type,
        "ts"  : datetime.datetime.now().strftime("%H:%M:%S"),
        "data": data
    }
    def _send():
        try:
            _requests.post(DASHBOARD_URL, json=payload, timeout=1.5)
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()

# ─────────────────────────────────────────────────────────────────────────────
# 🎮 GAMING MODE
# ─────────────────────────────────────────────────────────────────────────────
GAME_KEYWORDS = [
    "game","steam","epic","valorant","minecraft","fortnite","roblox",
    "league","csgo","cs2","gta","warzone","apex","overwatch","fifa",
    "elden","cyberpunk","unity","unreal",
]
_gaming_mode   = False
_message_queue = []

def _is_fullscreen_game():
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return False
        rect = win32gui.GetWindowRect(hwnd)
        sw   = win32api.GetSystemMetrics(0)
        sh   = win32api.GetSystemMetrics(1)
        if not (rect[0] <= 0 and rect[1] <= 0 and rect[2] >= sw and rect[3] >= sh):
            return False
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if PSUTIL_OK:
            try:
                name = psutil.Process(pid).name().lower()
                return any(k in name for k in GAME_KEYWORDS)
            except Exception:
                pass
        title = win32gui.GetWindowText(hwnd).lower()
        return any(k in title for k in GAME_KEYWORDS)
    except Exception:
        return False

def check_gaming_mode():
    global _gaming_mode
    was = _gaming_mode
    _gaming_mode = _is_fullscreen_game()
    if _gaming_mode and not was:
        ZBUS.emit("gaming_start", {})
        push_event("gaming", {"state": "on"})
        print("🎮 GAMING MODE ON — messages queuing...")
    elif not _gaming_mode and was:
        ZBUS.emit("gaming_end", {})
        push_event("gaming", {"state": "off", "queued": len(_message_queue)})
        print(f"🎮 GAMING MODE OFF — flushing {len(_message_queue)} queued msg(s)")
        flush_game_queue()
    return _gaming_mode

def flush_game_queue():
    """Flush messages queued during gaming mode."""
    hwnd = win32gui.FindWindow(None, "WhatsApp")
    if not hwnd:
        return
    try:
        app = Desktop(backend="uia").window(handle=hwnd)
        while _message_queue:
            name, msg, utype = _message_queue.pop(0)
            if open_chat(app, hwnd, name):
                if utype in ("BOSS", "GF"):
                    process_boss_message(hwnd, msg, utype, name)
                else:
                    handle_unknown_user(hwnd, name, msg)
    except Exception as e:
        print(f" ⚠️ flush_game_queue error: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# 🪟 CACHED MSGBOX  (4-strategy learning from find_msgbox.py)
# ─────────────────────────────────────────────────────────────────────────────
_cached_msgbox = None

def learn_msgbox(hwnd):
    global _cached_msgbox
    # Strategy 1 — Edit UIA
    try:
        app   = Desktop(backend="uia").window(handle=hwnd)
        edits = app.descendants(control_type="Edit")
        for e in edits:
            try:
                if not e.is_visible() or not e.is_enabled():
                    continue
                r  = e.rectangle()
                w  = r.right - r.left
                h  = r.bottom - r.top
                cx = r.left + w // 2
                cy = r.top  + h // 2
                if w > 200 and h < 60 and cx > 600:
                    _cached_msgbox = (cx, cy)
                    print(f" ✅ [learn_msgbox] Strategy 1 (Edit UIA) → ({cx}, {cy})")
                    return _cached_msgbox
            except Exception:
                continue
    except Exception:
        pass
    # Strategy 2 — Document UIA
    try:
        app  = Desktop(backend="uia").window(handle=hwnd)
        docs = app.descendants(control_type="Document")
        for d in docs:
            try:
                if not d.is_visible() or not d.is_enabled():
                    continue
                r  = d.rectangle()
                w  = r.right - r.left
                h  = r.bottom - r.top
                cx = r.left + w // 2
                cy = r.top  + h // 2
                if w > 200 and h < 60 and cx > 600:
                    _cached_msgbox = (cx, cy)
                    print(f" ✅ [learn_msgbox] Strategy 2 (Document UIA) → ({cx}, {cy})")
                    return _cached_msgbox
            except Exception:
                continue
    except Exception:
        pass
    # Strategy 3 — 92% height
    try:
        rect   = win32gui.GetWindowRect(hwnd)
        cx     = rect[0] + (rect[2] - rect[0]) // 2
        cy     = rect[1] + int((rect[3] - rect[1]) * 0.92)
        _cached_msgbox = (cx, cy)
        print(f" ⚠️ [learn_msgbox] Strategy 3 (92%) → ({cx}, {cy})")
        return _cached_msgbox
    except Exception:
        pass
    # Strategy 4 — Hard offset fallback
    rect = win32gui.GetWindowRect(hwnd)
    cx   = rect[0] + 857
    cy   = rect[1] + 693
    _cached_msgbox = (cx, cy)
    print(f" ⚠️ [learn_msgbox] Strategy 4 (fallback) → ({cx}, {cy})")
    return _cached_msgbox

def get_msgbox_center(hwnd):
    global _cached_msgbox
    if _cached_msgbox:
        return _cached_msgbox
    return learn_msgbox(hwnd)

def reset_msgbox_cache():
    global _cached_msgbox
    _cached_msgbox = None
    print(" 🔄 Msgbox cache cleared — will re-scan next send.")

# ─────────────────────────────────────────────────────────────────────────────
# 🔑 ACTIVATION HELPERS  (Boss/GF 30-min session)
# ─────────────────────────────────────────────────────────────────────────────
def activate_user(chat_name):
    activated_users[chat_name] = time.time()
    push_event("activation", {"chat": chat_name, "state": "activated"})
    print(f" 🔑 ACTIVATED: [{chat_name}]")

def deactivate_user(chat_name):
    activated_users.pop(chat_name, None)
    push_event("activation", {"chat": chat_name, "state": "deactivated"})
    print(f" 🔒 DEACTIVATED: [{chat_name}]")

def is_activated(chat_name):
    if chat_name not in activated_users:
        return False
    if (time.time() - activated_users[chat_name]) > ACTIVATION_TIMEOUT:
        deactivate_user(chat_name)
        return False
    return True

def touch_activation(chat_name):
    if chat_name in activated_users:
        activated_users[chat_name] = time.time()

# ─────────────────────────────────────────────────────────────────────────────
# 🔓 MASTER CODE ELEVATION  (unknown → BOSS for session)
# ─────────────────────────────────────────────────────────────────────────────
def elevate_to_boss(chat_name):
    elevated_users.add(chat_name)
    activate_user(chat_name)
    push_event("elevation", {"chat": chat_name})
    print(f" 🔓 ELEVATED TO BOSS: [{chat_name}]")

def is_elevated(chat_name):
    return chat_name in elevated_users

# ─────────────────────────────────────────────────────────────────────────────
# 🪪 UNKNOWN USER SESSION
# ─────────────────────────────────────────────────────────────────────────────
def get_session(chat_name):
    if chat_name not in user_sessions:
        user_sessions[chat_name] = {
            "id"           : "ZLU-" + uuid.uuid4().hex[:6].upper(),
            "introduced"   : False,
            "last_activity": time.time(),
        }
    return user_sessions[chat_name]

def touch_session(chat_name):
    get_session(chat_name)["last_activity"] = time.time()

def is_session_expired(chat_name):
    if chat_name not in user_sessions:
        return False
    return (time.time() - user_sessions[chat_name]["last_activity"]) > IDLE_TIMEOUT

# ─────────────────────────────────────────────────────────────────────────────
# 🪟 WINDOW HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def bring_visible(hwnd):
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOP,
                          WA_LEFT, WA_TOP, WA_WIDTH, WA_HEIGHT,
                          win32con.SWP_SHOWWINDOW)
    time.sleep(0.05)   # SPEED: was 0.2 — Win32 doesn't need 200ms to process

def wake_whatsapp():
    print("📢 Waking WhatsApp...")
    os.system("start whatsapp://")
    time.sleep(3)

# ─────────────────────────────────────────────────────────────────────────────
# 📋 CLIPBOARD
# ─────────────────────────────────────────────────────────────────────────────
def set_clipboard(text):
    for _ in range(3):
        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            return True
        except Exception:
            time.sleep(0.2)
    return False

# ─────────────────────────────────────────────────────────────────────────────
# 📤 SEND REPLY
# FIX 3: AllowSetForegroundWindow(-1) ensures Windows grants focus from any
#         thread before SetForegroundWindow — without it the call can silently
#         fail and the click lands on whatever was in front.
# ─────────────────────────────────────────────────────────────────────────────
def _safe_set_foreground(hwnd):
    """Grant foreground permission then focus the window."""
    try:
        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # FIX 3
    except Exception:
        pass
    try:
        win32gui.BringWindowToTop(hwnd)
    except Exception:
        pass
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass

def send_reply(hwnd, message, retry_on_fail=True):
    try:
        if not set_clipboard(message):
            print(" ❌ Clipboard failed.")
            return False
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        _safe_set_foreground(hwnd)          # FIX 3: replaces bare SetForegroundWindow
        time.sleep(0.4)    # SPEED: was 1.0 — AllowSetForegroundWindow is near-instant
        cx, cy = get_msgbox_center(hwnd)
        pyautogui.moveTo(cx, cy, duration=0.1)
        pyautogui.click()
        time.sleep(0.15)   # SPEED: was 0.3
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.05)   # SPEED: was 0.1
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.15)   # SPEED: was 0.3
        pyautogui.press("enter")
        time.sleep(0.05)   # SPEED: was 0.2
        print(f" 📤 Sent: {message[:80]}")
        push_event("sent", {"preview": message[:120]})
        bring_visible(hwnd)
        return True
    except Exception as e:
        print(f" ❌ send_reply error: {e}")
        if retry_on_fail:
            print(" 🔄 Retrying with fresh msgbox scan...")
            reset_msgbox_cache()
            return send_reply(hwnd, message, retry_on_fail=False)
        return False

# ─────────────────────────────────────────────────────────────────────────────
# 💾 LOG UNKNOWN REQUEST
# ─────────────────────────────────────────────────────────────────────────────
def save_unknown_request(chat_name, message, session_id, answered=False):
    try:
        os.makedirs(os.path.dirname(REQUESTS_LOG), exist_ok=True)
        ts     = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "✅ ANSWERED" if answered else "📥 SAVED"
        entry  = (f"\n{chr(9472)*50}\n"
                  f"🕐 {ts} | 🪪 {session_id} | {status}\n"
                  f"👤 From    : {chat_name}\n"
                  f"💬 Message : {message}\n"
                  f"{chr(9472)*50}\n")
        with open(REQUESTS_LOG, "a", encoding="utf-8") as f:
            f.write(entry)
        push_event("unknown_msg", {
            "chat"    : chat_name,
            "msg"     : message[:100],
            "answered": answered,
            "ref"     : session_id
        })
    except Exception as e:
        print(f" ⚠️ save_unknown_request error: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# 🤖 HANDLE UNKNOWN USER  (AI receptionist + master code check)
# ─────────────────────────────────────────────────────────────────────────────
def handle_unknown_user(hwnd, chat_name, message):
    # ── Mute + lockdown guard ─────────────────────────────────────────────
    if ZMEM.is_muted(chat_name):
        print(f" 🔇 [{chat_name}] is muted — skipping silently.")
        return
    if ZSTATE.get("lockdown"):
        print(f" 🔒 Lockdown active — blocking [{chat_name}].")
        return

    session    = get_session(chat_name)
    session_id = session["id"]
    msg_lower  = message.lower().strip()
    footer     = f"\n\n🪪 Ref: {session_id}"
    touch_session(chat_name)

    # ── Master code check ──────────────────────────────────────────────────
    if MASTER_CODE.lower() in msg_lower:
        elevate_to_boss(chat_name)
        send_reply(hwnd,
            "🔓 Access granted. Welcome!\n"
            "You now have full BOSS access.\n"
            "Send ZULU to get started. 🛰️")
        save_unknown_request(chat_name, f"[MASTER CODE USED] {message}", session_id)
        return

    # ── First contact greeting ─────────────────────────────────────────────
    if not session["introduced"]:
        session["introduced"] = True
        send_reply(hwnd,
            f"👋 Hello! I'm ZULU, an AI assistant.\n"
            f"The person you're trying to reach is busy.\n"
            f"I can answer questions or pass on your message. 😊\n"
            f"How can I help you?{footer}")
        save_unknown_request(chat_name, f"[FIRST CONTACT] {message}", session_id)
        return

    # ── Availability question ──────────────────────────────────────────────
    question_words = ["what", "how", "why", "when", "where", "who", "can you",
                      "tell me", "explain", "help", "please", "need",
                      "looking for", "want", "would like",
                      "give me", "show me", "can you", "could you"]

    if any(w in msg_lower for w in question_words):
        from boardroom_engine import run_easy_flow
        try:
            # result uses your brain_manager fallbacks (Cerebras/Gemini/SambaNova)
            result, errors = run_easy_flow(message, "UNKNOWN")
            if result:
                answer = str(result).strip()[:400]
                send_reply(hwnd, f"🤖 {answer}{footer}")
                save_unknown_request(chat_name, message, session_id, answered=True)
                return
        except Exception as e:
            print(f" ⚠️ Unknown AI answer failed: {e}")

    # ── AI-powered answer ──────────────────────────────────────────────────
    question_words = ["what", "how", "why", "when", "where", "who", "can you",
                      "tell me", "explain", "help", "please", "need",
                      "looking for", "want", "would like",
                      "give me","show me","can you","could you"]
    if any(w in msg_lower for w in question_words):
        auto_restore()
        from brain_manager import get_best_brain
        bid, _ = get_best_brain()
        if bid:
            try:
                from crewai import Agent, Task, Crew, Process
                llm   = build_llm(bid)
                agent = Agent(
                    role     = "Friendly AI Assistant",
                    goal     = "Answer helpfully. Never mention any boss, owner, or internal system.",
                    backstory= "You are ZULU, a WhatsApp AI assistant. Plain text only, max 3 sentences.",
                    llm=llm, verbose=False)
                task  = Task(
                    description   = f"Answer this clearly and briefly: '{message}'",
                    expected_output="Short plain-text answer, max 3 sentences.",
                    agent=agent)
                crew   = Crew(agents=[agent], tasks=[task],
                              process=Process.sequential, verbose=False)
                answer = str(crew.kickoff()).strip()[:400]
                send_reply(hwnd, f"🤖 {answer}{footer}")
                save_unknown_request(chat_name, message, session_id, answered=True)
                return
            except Exception as e:
                print(f" ⚠️ Unknown AI answer failed: {e}")

    # ── Default acknowledge ────────────────────────────────────────────────
    send_reply(hwnd, f"👍 Got it! Message noted.\nThey'll get back to you soon. 😊{footer}")
    save_unknown_request(chat_name, message, session_id)

# ─────────────────────────────────────────────────────────────────────────────
# ⏰ IDLE TIMEOUT  (goodbye to silent unknown users)
# ─────────────────────────────────────────────────────────────────────────────
def check_idle_timeouts(app, hwnd):
    expired = [n for n in list(user_sessions)
               if user_sessions[n].get("introduced") and is_session_expired(n)]
    for name in expired:
        sid = user_sessions[name]["id"]
        print(f" ⏰ Session expired [{name}] — sending goodbye")
        if open_chat(app, hwnd, name):
            send_reply(hwnd,
                f"😊 You've gone quiet — no problem!\n"
                f"I'm going offline now. Message again anytime. 👋\n\n🪪 Ref: {sid}")
        del user_sessions[name]
        last_seen_msgs.pop(name, None)

# ─────────────────────────────────────────────────────────────────────────────
# 🗂️ SIDEBAR HELPERS  (wa_inspector.py rich DataItem strategy)
# ─────────────────────────────────────────────────────────────────────────────
def parse_dataitem(raw):
    m = re.search(r'\b\d{1,2}:\d{2}\b', raw)
    if m:
        return raw[:m.start()].strip(), raw[m.end():].strip()
    return raw.strip(), ""

def parse_dataitem_rich(item):
    """wa_inspector.py strategy: walk child Text controls for richer parsing."""
    try:
        texts = []
        for c in item.descendants(control_type="Text"):
            t = c.window_text().strip()
            if t:
                texts.append(t)
        if len(texts) >= 2:
            return texts[0], texts[-1]
        elif len(texts) == 1:
            return texts[0], ""
    except Exception:
        pass
    return parse_dataitem(item.window_text().strip())

def detect_user_type(name):
    for fragment, utype in MONITORED_CHATS.items():
        if fragment.lower() in name.lower():
            return utype
    return "UNKNOWN"

def get_sidebar_chats(app, n=12):
    chats, seen = [], set()
    try:
        for item in app.descendants(control_type="DataItem"):
            if len(chats) >= n:
                break
            raw = item.window_text().strip()
            if not raw:
                continue
            name, last_msg = parse_dataitem_rich(item)
            if not name or name in seen:
                continue
            seen.add(name)
            utype = detect_user_type(name)
            if utype == "BOSS":
                set_boss_chat(name)
            chats.append({"name": name, "last_msg": last_msg,
                          "user_type": utype, "item": item})
    except Exception as e:
        print(f" ⚠️ sidebar error: {e}")
    return chats

# ─────────────────────────────────────────────────────────────────────────────
# 🖱️ OPEN CHAT
# ─────────────────────────────────────────────────────────────────────────────
def open_chat(app, hwnd, chat_name):
    try:
        seen = set()
        for item in app.descendants(control_type="DataItem"):
            raw = item.window_text().strip()
            if not raw:
                continue
            name, _ = parse_dataitem_rich(item)
            if name in seen:
                continue
            seen.add(name)
            if chat_name.lower() in name.lower():
                item.click_input()
                time.sleep(0.6)    # SPEED: was 1.0 — chat loads fast enough
                _safe_set_foreground(hwnd)  # FIX 3: use safe focus helper
                time.sleep(0.1)    # SPEED: was 0.3
                print(f" 🖱️ Opened: '{name}'")
                return True
        print(f" ⚠️ Chat not found: '{chat_name}'")
        return False
    except Exception as e:
        print(f" ⚠️ open_chat error: {e}")
        return False

# ─────────────────────────────────────────────────────────────────────────────
# 🧠 PROCESS BOSS / GF / ELEVATED MESSAGE
# ─────────────────────────────────────────────────────────────────────────────
def process_boss_message(hwnd, msg, user_type, chat_name):
    upper = msg.upper().strip()

    # ── Loop guard: ignore empty + boardroom echo text ───────────────────
    if not msg or not msg.strip():
        return

    # FIX 4 + FIX 5: Extended _loop_triggers to catch boardroom's own replies
    # that start with "ZULU" (e.g. "ZULU online, Boss." / "ZULU at your service")
    # and other boardroom output patterns — prevents ZULU processing its own msgs.
    _loop_triggers = [
        # Error echoes
        "Error:", "model_not_found", "LLM Call Failed",
        "Error code: 404",
        # Boardroom ack/status messages ZULU sends
        "🛰️ Zulu Ack:", "🙏 Zulu Ack:",
        # Boardroom greeting lines (start with ZULU — would re-trigger)
        "ZULU online, Boss",
        "ZULU at your service",
        "ZULU back online",
        "ZULU going offline",
        # Boardroom result lines
        "Done! ",
        "Done (backup brain)",
        "⚡ (cached)",
        # Boardroom error/status lines
        "All AI brains offline",
        "All brains exhausted",
        "All backups failed",
        "⚠️ AI brain quota hit",
        # Brain status reports
        "🛰️ ZULU Brain Status",
        "🧠 ZULU MIND",
    ]
    if any(t in msg for t in _loop_triggers):
        return

    # ── 🖥️ PC CONTROL ROUTER (zulu_pc.py) — instant commands ────────────────
    # Screenshot, volume, lock screen, brightness, open/close apps, etc.
    # Runs FIRST so PC commands never hit the AI (faster, cheaper)
    try:
        from zulu_pc import handle_pc_command
        _cmd = msg.strip()[len("ZULU "):] if upper.startswith("ZULU ") else msg.strip()
        pc_handled, pc_response = handle_pc_command(_cmd, user_type)
        if pc_handled:
            send_reply(hwnd, pc_response)
            ZMEM.remember_task(user_type, msg[:60], "pc_command", pc_response[:80])
            return
    except ImportError:
        pass  # zulu_pc not available
    except Exception as _pce:
        zlog("tray", f"PC command error: {_pce}", "WARN")

    # ── Always-on commands ─────────────────────────────────────────────────
    if "ZULU OFF" in upper:
        ZSTATE.set("is_active", False)
        deactivate_user(chat_name)
        send_reply(hwnd, "🫡 ZULU going offline. Send ZULU ON to wake me.")
        return

    if "ZULU ON" in upper and not ZSTATE.get("is_active"):
        ZSTATE.set("is_active", True)
        activate_user(chat_name)
        send_reply(hwnd, "🛰️ ZULU back online. Ready for orders!")
        return

    if "ZULU STATUS" in upper:
        auto_restore()
        send_reply(hwnd, get_status_report())
        return

    if upper == "ZULU PING":
        send_reply(hwnd, "🔍 Pinging all AI brains...")
        check_all_pings()
        send_reply(hwnd, get_status_report())
        return

    if "ZULU HELP" in upper:
        send_reply(hwnd,
            "🛡️ ZULU Commands:\n"
            " ZULU [task] → run AI task\n"
            " ZULU STATUS → brain health\n"
            " ZULU PING → live brain check\n"
            " ZULU MIND → full system state\n"
            " ZULU PATTERNS → usage patterns\n"
            " ZULU MEMORY → last 10 tasks\n"
            " ZULU BRIEFING → daily summary\n"
            " ZULU CRYPTO BTC → live price\n"
            " ZULU ALERT BTC ABOVE 70000\n"
            " ZULU REPORT week/today/month\n"
            " ZULU MISTAKES → error log\n"
            " ZULU LEARN → self-learning report\n"
            " ZULU ORGANISE DRY → preview\n"
            " ZULU ORGANISE → sort files\n"
            " ZULU PIPELINES → run due\n"
            " ZULU PIPELINE name|sched|steps\n"
            " ZULU MUTE [name] → mute contact\n"
            " ZULU UNMUTE [name] → unmute\n"
            " ZULU LOCKDOWN → block unknowns\n"
            " ZULU UNLOCK → lift lockdown\n"
            " ZULU INBOX → unknown messages\n"
            " ZULU OFF/ON → sleep / wake\n"
            " ZULU SCAN → re-learn msgbox\n"
            "─── ⚡ Instant Tools ───\n"
            " ZULU JOKE → random joke\n"
            " ZULU QUOTE → motivational quote\n"
            " ZULU DICE → roll a die\n"
            " ZULU FLIP → heads or tails\n"
            " ZULU CALC 25*12 → calculator\n"
            " ZULU TIME Dubai → city time\n"
            " ZULU PING google.com → site up?\n"
            " ZULU TRANSLATE hi TO Spanish\n"
            " ZULU NOTE buy milk → save note\n"
            " ZULU NOTE → view notes\n"
            " ZULU COUNTDOWN 25 Dec 2026\n"
            " ZULU REMIND DAILY 8am drink water\n"
            " ZULU HELP → this menu")
        return

    if "ZULU INBOX" in upper:
        try:
            if os.path.exists(REQUESTS_LOG):
                with open(REQUESTS_LOG, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                lines   = content.split("\n")
                preview = "\n".join(lines[-30:]) if len(lines) > 30 else content
                send_reply(hwnd, f"📬 Inbox (last entries):\n\n{preview[:450]}")
            else:
                send_reply(hwnd, "📭 No unknown user messages yet.")
        except Exception as e:
            send_reply(hwnd, f"⚠️ Inbox error: {e}")
        return

    if "ZULU SCAN" in upper:
        reset_msgbox_cache()
        hwnd2 = win32gui.FindWindow(None, "WhatsApp")
        if hwnd2:
            cx, cy = learn_msgbox(hwnd2)
            send_reply(hwnd, f"🎯 Msgbox re-scanned → ({cx}, {cy})")
        return

    # ── v13 commands ───────────────────────────────────────────────────────
    if upper.startswith("ZULU CRYPTO"):
        from boardroom_engine import get_crypto_price
        sym = upper.replace("ZULU CRYPTO", "").strip() or "BTC"
        send_reply(hwnd, get_crypto_price(sym))
        return

    if upper.startswith("ZULU ALERT"):
        from boardroom_engine import add_price_alert
        parts = upper.replace("ZULU ALERT", "").strip().split()
        if len(parts) >= 3:
            try:
                send_reply(hwnd, add_price_alert(parts[0], float(parts[2]), parts[1].lower()))
            except Exception as e:
                send_reply(hwnd, f"Alert error: {e}. Format: ZULU ALERT BTC ABOVE 70000")
        else:
            send_reply(hwnd, "Format: ZULU ALERT BTC ABOVE 70000")
        return

    if upper.startswith("ZULU REPORT"):
        from boardroom_engine import get_project_status_report
        period = msg.strip()[len("ZULU REPORT"):].strip().lower() or "week"
        send_reply(hwnd, get_project_status_report(period))
        return

    if "ZULU MISTAKES" in upper:
        from boardroom_engine import get_mistake_patterns
        send_reply(hwnd, get_mistake_patterns())
        return

    if "ZULU LEARN" in upper:
        send_reply(hwnd, get_learn_report())
        return

    # ── ZULU FILES / FILES TODAY / FILES YESTERDAY ──────────────────────────
    if "ZULU FILES" in upper:
        import glob, datetime as _dt
        proj_dir   = r"D:\AI_Agency_Work\Projects"
        all_files  = glob.glob(os.path.join(proj_dir, "**", "*"), recursive=True)
        all_files  = [f for f in all_files if os.path.isfile(f)]
        today      = _dt.date.today()
        yesterday  = today - _dt.timedelta(days=1)
        def _fdate(f):
            return _dt.date.fromtimestamp(os.path.getmtime(f))
        if "TODAY" in upper:
            files = [f for f in all_files if _fdate(f) == today]
            label = "today"
        elif "YESTERDAY" in upper:
            files = [f for f in all_files if _fdate(f) == yesterday]
            label = "yesterday"
        else:
            files = all_files
            label = "all"
        if not files:
            send_reply(hwnd, f"📂 No files found ({label}).")
        else:
            lines = [f"📂 ZULU Files ({label}) — {len(files)} file(s):"]
            for f in sorted(files, key=os.path.getmtime, reverse=True)[:20]:
                lines.append(f"  • {os.path.basename(f)}  [{_fdate(f)}]")
            if len(files) > 20:
                lines.append(f"  ...and {len(files)-20} more")
            send_reply(hwnd, "\n".join(lines))
        return

    # ── ZULU UNDO ──────────────────────────────────────────────────────────
    if "ZULU UNDO" in upper:
        backup_dir = r"D:\AI_Agency_Work\System_Logs\backups"
        if not os.path.exists(backup_dir):
            send_reply(hwnd, "❌ No backup folder found.")
            return
        backups = sorted(
            [f for f in os.listdir(backup_dir) if os.path.isfile(os.path.join(backup_dir, f))],
            key=lambda x: os.path.getmtime(os.path.join(backup_dir, x)),
            reverse=True
        )
        if not backups:
            send_reply(hwnd, "❌ No backups found to restore.")
            return
        latest    = backups[0]
        src       = os.path.join(backup_dir, latest)
        orig_name = latest.replace(".bak", "").replace("_backup", "")
        dest      = os.path.join(r"D:\AI_Agency_Work\Projects", orig_name)
        try:
            import shutil as _sh
            _sh.copy2(src, dest)
            send_reply(hwnd, f"↩️ ZULU UNDO: Restored\n  {orig_name}\n  From: {src}")
        except Exception as e:
            send_reply(hwnd, f"❌ Undo failed: {e}")
        return

    # ── ZULU AUDIT ──────────────────────────────────────────────────────────
    if "ZULU AUDIT" in upper:
        audit_file = r"D:\AI_Agency_Work\System_Logs\audit.log"
        if not os.path.exists(audit_file):
            send_reply(hwnd, "📋 No audit log found yet.")
            return
        with open(audit_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        last15 = lines[-15:]
        send_reply(hwnd, "📋 ZULU Audit (last 15):\n" + "".join(last15).strip())
        return

    # ── ZULU MEMORY ──────────────────────────────────────────────────────────
    if "ZULU MEMORY" in upper:
        send_reply(hwnd, ZMEM.get_task_context(last_n=10))
        return

    # ── ZULU RETRY ──────────────────────────────────────────────────────────
    if "ZULU RETRY" in upper:
        retry_file = r"D:\AI_Agency_Work\System_Logs\retry_queue.json"
        if not os.path.exists(retry_file):
            send_reply(hwnd, "🔁 No failed tasks in retry queue.")
            return
        with open(retry_file, "r", encoding="utf-8") as f:
            queue = json.load(f)
        if not queue:
            send_reply(hwnd, "🔁 Retry queue is empty — nothing to re-run.")
            return
        send_reply(hwnd, f"🔁 Re-running {len(queue)} queued task(s)...")
        for item in queue:
            try:
                launch_boardroom(item.get("task", ""), user_type=item.get("user", "BOSS"))
            except Exception as e:
                print(f" ⚠️ retry error: {e}")
        with open(retry_file, "w", encoding="utf-8") as f:
            json.dump([], f)
        send_reply(hwnd, "✅ Retry queue flushed.")
        return

    # ── ZULU CLEAR INBOX ──────────────────────────────────────────────────
    if "ZULU CLEAR INBOX" in upper:
        inbox_file = r"D:\AI_Agency_Work\System_Logs\unknown_requests.txt"
        try:
            with open(inbox_file, "w", encoding="utf-8") as f:
                f.write("")
            send_reply(hwnd, "🗑️ ZULU inbox cleared.")
        except Exception as e:
            send_reply(hwnd, f"❌ Clear inbox failed: {e}")
        return

    # ── ZULU RESTART WA ──────────────────────────────────────────────────
    if "ZULU RESTART WA" in upper:
        send_reply(hwnd, "🔄 Restarting WhatsApp now...")
        def _do_restart():
            time.sleep(1)
            _restart_whatsapp()
        threading.Thread(target=_do_restart, daemon=True).start()
        return

    # ── ZULU TAKE OVER ──────────────────────────────────────────────────
    if "ZULU TAKE OVER" in upper:
        ZSTATE.set("presence_mode", "always")
        send_reply(hwnd, "👁️ ZULU TAKE OVER: Presence mode set to ALWAYS.\nWhatsApp will stay visible.")
        return

    # ── ZULU STAND BY / ZULU AUTO ──────────────────────────────────────
    if "ZULU STAND BY" in upper or "ZULU AUTO" in upper:
        ZSTATE.set("presence_mode", "auto")
        send_reply(hwnd, "🤖 ZULU AUTO: Presence mode set to AUTO.\nZULU will detect idle vs active.")
        return

    # ── ZULU PRESENCE ──────────────────────────────────────────────────
    if "ZULU PRESENCE" in upper:
        mode = ZSTATE.get("presence_mode")
        send_reply(hwnd, f"👁️ ZULU Presence\n  Mode: {mode}\n  Status: Active")
        return

    # ── ZULU BRIEFING ──────────────────────────────────────────────────────
    if "ZULU BRIEFING" in upper:
        status         = get_status_report()
        task_lines_str = ZMEM.get_task_context(last_n=5)
        wa_data        = _load_wa_health()
        wa_events      = len(wa_data.get("events", []))
        wa_restarts    = wa_data.get("total_restarts", 0)
        briefing       = (
            f"📋 ZULU Daily Briefing\n"
            f"{'─'*30}\n"
            f"{status}\n\n"
            f"{task_lines_str}\n\n"
            f"📡 WA Health:\n"
            f"  Events logged: {wa_events}\n"
            f"  Total restarts: {wa_restarts}"
        )
        send_reply(hwnd, briefing)
        return

    if upper.startswith("ZULU ORGANISE"):
        from boardroom_engine import organise_projects_folder
        dry = "DRY" in upper
        send_reply(hwnd, organise_projects_folder(dry_run=dry))
        return

    if upper.startswith("ZULU PIPELINE "):
        from boardroom_engine import add_pipeline
        rest  = msg.strip()[len("ZULU PIPELINE"):].strip()
        parts = rest.split("|")
        if len(parts) >= 3:
            steps = [s.strip() for s in parts[2].split(";") if s.strip()]
            send_reply(hwnd, add_pipeline(parts[0].strip(), parts[1].strip(), steps))
        else:
            send_reply(hwnd, "Format: ZULU PIPELINE name|daily 08:00|step1;step2")
        return

    if "ZULU PIPELINES" in upper:
        from boardroom_engine import check_pipelines
        reports = check_pipelines(user_type)
        send_reply(hwnd, "\n\n".join(reports) if reports else "No pipelines due now.")
        return

    # ── v13.3 Core Brain commands ──────────────────────────────────────────
    if upper == "ZULU MIND":
        send_reply(hwnd, ZSTATE.get_mind_report())
        return

    if upper == "ZULU PATTERNS":
        send_reply(hwnd, ZMEM.get_patterns_report())
        return

    if upper.startswith("ZULU MUTE "):
        contact = msg.strip()[len("ZULU MUTE "):].strip()
        ZMEM.mute(contact)
        send_reply(hwnd, f"🔇 {contact} muted.")
        return

    if upper.startswith("ZULU UNMUTE "):
        contact = msg.strip()[len("ZULU UNMUTE "):].strip()
        ZMEM.unmute(contact)
        send_reply(hwnd, f"🔔 {contact} unmuted.")
        return

    if upper == "ZULU LOCKDOWN":
        ZSTATE.set("lockdown", True)
        send_reply(hwnd, "🔒 LOCKDOWN — only Boss & GF get through.")
        return

    if upper == "ZULU UNLOCK":
        ZSTATE.set("lockdown", False)
        send_reply(hwnd, "✅ Lockdown lifted.")
        return

    # ── ⚡ INSTANT COMMANDS v13.6 — Pure Python, zero AI, instant response ──────
    # These work without activation and need no AI brain.

    # 1. ZULU JOKE
    if upper == "ZULU JOKE":
        import random as _r
        _jokes = [
            "Why don't scientists trust atoms? Because they make up everything! 😄",
            "I told my wife she was drawing her eyebrows too high. She looked surprised. 😂",
            "Why did the scarecrow win an award? He was outstanding in his field! 🌾",
            "I'm reading a book about anti-gravity. It's impossible to put down! 📚",
            "Why don't eggs tell jokes? They'd crack each other up! 🥚",
            "What do you call fake spaghetti? An impasta! 🍝",
            "Why did the bicycle fall over? Because it was two-tired! 🚲",
            "What do you call a sleeping dinosaur? A dino-snore! 🦕",
            "I used to hate facial hair, but then it grew on me. 😁",
            "What do you call cheese that isn't yours? Nacho cheese! 🧀",
            "Why can't you give Elsa a balloon? She'll let it go! 🎈",
            "What's brown and sticky? A stick! 🌿",
        ]
        send_reply(hwnd, f"😂 {_r.choice(_jokes)}")
        return

    # 2. ZULU QUOTE
    if upper == "ZULU QUOTE":
        import random as _r
        _quotes = [
            {"text": "The only way to do great work is to love what you do.", "author": "Steve Jobs"},
            {"text": "In the middle of every difficulty lies opportunity.", "author": "Albert Einstein"},
            {"text": "It does not matter how slowly you go as long as you do not stop.", "author": "Confucius"},
            {"text": "Life is what happens when you're busy making other plans.", "author": "John Lennon"},
            {"text": "The future belongs to those who believe in the beauty of their dreams.", "author": "Eleanor Roosevelt"},
            {"text": "You miss 100% of the shots you don't take.", "author": "Wayne Gretzky"},
            {"text": "I have not failed. I've just found 10,000 ways that won't work.", "author": "Thomas Edison"},
            {"text": "The best time to plant a tree was 20 years ago. The second best time is now.", "author": "Chinese Proverb"},
            {"text": "Strive not to be a success, but rather to be of value.", "author": "Albert Einstein"},
            {"text": "Spread love everywhere you go. Let no one ever come to you without leaving happier.", "author": "Mother Teresa"},
            {"text": "When you reach the end of your rope, tie a knot in it and hang on.", "author": "Franklin D. Roosevelt"},
            {"text": "The only impossible journey is the one you never begin.", "author": "Tony Robbins"},
        ]
        q = _r.choice(_quotes)
        send_reply(hwnd, f"💡 \"{q['text']}\"\n  — {q['author']}")
        return

    # 3. ZULU DICE
    if upper == "ZULU DICE":
        import random as _r
        n = _r.randint(1, 6)
        faces = ["", "⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
        send_reply(hwnd, f"🎲 You rolled: {faces[n]}  ({n})")
        return

    # 4. ZULU FLIP
    if upper == "ZULU FLIP":
        import random as _r
        send_reply(hwnd, f"🪙 {_r.choice(['Heads! 🪙', 'Tails! 🔵'])}")
        return

    # 5. ZULU CALC [expression]
    if upper.startswith("ZULU CALC"):
        expr = msg.strip()[len("ZULU CALC"):].strip()
        if not expr:
            send_reply(hwnd, "🔢 Format: ZULU CALC 250 * 12")
            return
        if re.match(r'^[\d\s\+\-\*\/\.\(\)\%]+$', expr):
            try:
                result = eval(expr)   # safe — whitelist ensures only digits & math ops
                send_reply(hwnd, f"🔢 {expr} = {result}")
            except Exception as e:
                send_reply(hwnd, f"❌ Calc error: {e}")
        else:
            send_reply(hwnd, "❌ Only digits and + - * / ( ) % allowed.")
        return

    # 6. ZULU TIME [city]
    if upper.startswith("ZULU TIME"):
        city_input = msg.strip()[len("ZULU TIME"):].strip()
        _tz_map = {
            "london": "Europe/London",        "uk": "Europe/London",
            "new york": "America/New_York",   "ny": "America/New_York",   "nyc": "America/New_York",
            "los angeles": "America/Los_Angeles", "la": "America/Los_Angeles",
            "chicago": "America/Chicago",
            "toronto": "America/Toronto",     "canada": "America/Toronto",
            "dubai": "Asia/Dubai",            "uae": "Asia/Dubai",
            "mumbai": "Asia/Kolkata",         "delhi": "Asia/Kolkata",
            "india": "Asia/Kolkata",          "kolkata": "Asia/Kolkata",
            "tokyo": "Asia/Tokyo",            "japan": "Asia/Tokyo",
            "beijing": "Asia/Shanghai",       "shanghai": "Asia/Shanghai",
            "china": "Asia/Shanghai",
            "sydney": "Australia/Sydney",     "australia": "Australia/Sydney",
            "paris": "Europe/Paris",          "france": "Europe/Paris",
            "berlin": "Europe/Berlin",        "germany": "Europe/Berlin",
            "moscow": "Europe/Moscow",        "russia": "Europe/Moscow",
            "singapore": "Asia/Singapore",
            "bangkok": "Asia/Bangkok",        "thailand": "Asia/Bangkok",
            "karachi": "Asia/Karachi",        "pakistan": "Asia/Karachi",
            "lahore": "Asia/Karachi",
            "istanbul": "Europe/Istanbul",    "turkey": "Europe/Istanbul",
            "cairo": "Africa/Cairo",          "egypt": "Africa/Cairo",
            "nairobi": "Africa/Nairobi",      "kenya": "Africa/Nairobi",
            "dhaka": "Asia/Dhaka",            "bangladesh": "Asia/Dhaka",
            "riyadh": "Asia/Riyadh",          "saudi": "Asia/Riyadh",
            "tehran": "Asia/Tehran",          "iran": "Asia/Tehran",
            "hong kong": "Asia/Hong_Kong",    "hongkong": "Asia/Hong_Kong",
            "seoul": "Asia/Seoul",            "korea": "Asia/Seoul",
            "jakarta": "Asia/Jakarta",        "indonesia": "Asia/Jakarta",
            "lagos": "Africa/Lagos",          "nigeria": "Africa/Lagos",
            "johannesburg": "Africa/Johannesburg", "south africa": "Africa/Johannesburg",
            "utc": "UTC",                     "gmt": "UTC",
        }
        city_key = city_input.lower().strip()
        tz_name = _tz_map.get(city_key)
        if not tz_name and city_input:
            for k, v in _tz_map.items():
                if city_key in k or k in city_key:
                    tz_name = v
                    break
        if tz_name:
            try:
                from zoneinfo import ZoneInfo
                now_tz = datetime.datetime.now(ZoneInfo(tz_name))
                send_reply(hwnd, f"🕐 {city_input}: {now_tz.strftime('%H:%M')}  ({now_tz.strftime('%a, %d %b %Y')})  [{tz_name}]")
            except Exception as e:
                send_reply(hwnd, f"❌ Time error: {e}")
        elif not city_input:
            now_local = datetime.datetime.now()
            send_reply(hwnd, f"🕐 Local: {now_local.strftime('%H:%M')}  ({now_local.strftime('%a, %d %b %Y')})")
        else:
            send_reply(hwnd, f"❌ City not found: '{city_input}'\nTry: London, Dubai, Tokyo, New York, Mumbai, Paris...")
        return

    # 7. ZULU PING [website]  (website reachability — brain ping is exact "ZULU PING" above)
    if upper.startswith("ZULU PING "):
        site = msg.strip()[len("ZULU PING"):].strip()
        if not site.startswith("http"):
            site = "https://" + site
        try:
            if REQUESTS_OK:
                r = _requests.get(site, timeout=8, allow_redirects=True)
                code = r.status_code
                if code < 400:
                    send_reply(hwnd, f"🌐 ✅ {site}  is UP  (HTTP {code})")
                else:
                    send_reply(hwnd, f"🌐 ⚠️ {site}  returned HTTP {code}")
            else:
                send_reply(hwnd, "❌ requests module not available.")
        except Exception as e:
            send_reply(hwnd, f"🌐 ❌ {site}  is DOWN\n{str(e)[:100]}")
        return

    # 8. ZULU TRANSLATE [text] TO [language]
    if upper.startswith("ZULU TRANSLATE"):
        raw = msg.strip()[len("ZULU TRANSLATE"):].strip()
        _lang_codes = {
            "spanish": "es", "french": "fr",  "german": "de",   "italian": "it",
            "portuguese": "pt", "arabic": "ar", "hindi": "hi",  "urdu": "ur",
            "chinese": "zh",  "japanese": "ja", "korean": "ko", "russian": "ru",
            "turkish": "tr",  "dutch": "nl",    "polish": "pl", "swedish": "sv",
            "greek": "el",    "hebrew": "he",   "thai": "th",   "vietnamese": "vi",
            "indonesian": "id", "malay": "ms",  "bengali": "bn","punjabi": "pa",
            "gujarati": "gu", "marathi": "mr",  "tamil": "ta",  "telugu": "te",
            "nepali": "ne",
        }
        tl = "es"   # default to Spanish
        text_to_translate = raw
        to_match = re.search(r'\bto\s+(\w+)\s*$', raw, re.IGNORECASE)
        if to_match:
            lang_word = to_match.group(1).lower()
            tl = _lang_codes.get(lang_word, lang_word[:2])
            text_to_translate = raw[:to_match.start()].strip()
        if not text_to_translate:
            send_reply(hwnd, "Format: ZULU TRANSLATE Hello how are you TO Spanish")
            return
        try:
            if REQUESTS_OK:
                import urllib.parse
                encoded = urllib.parse.quote(text_to_translate)
                url = (f"https://translate.googleapis.com/translate_a/single"
                       f"?client=gtx&sl=auto&tl={tl}&dt=t&q={encoded}")
                resp = _requests.get(url, timeout=8)
                data = resp.json()
                translated = "".join(part[0] for part in data[0] if part[0])
                send_reply(hwnd, f"🔤 {translated}")
            else:
                send_reply(hwnd, "❌ requests module not available.")
        except Exception as e:
            send_reply(hwnd, f"❌ Translate error: {e}")
        return

    # 9. ZULU NOTE [text]  — save / view notes
    if upper.startswith("ZULU NOTE"):
        note_text = msg.strip()[len("ZULU NOTE"):].strip()
        _notes_file = r"D:\AI_Agency_Work\System_Logs\zulu_notes.txt"
        if not note_text:
            try:
                if os.path.exists(_notes_file):
                    with open(_notes_file, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                    if content:
                        lines   = content.split("\n")
                        preview = "\n".join(lines[-15:]) if len(lines) > 15 else content
                        send_reply(hwnd, f"📝 Your notes:\n\n{preview[:450]}")
                    else:
                        send_reply(hwnd, "📝 No notes saved yet.")
                else:
                    send_reply(hwnd, "📝 No notes saved yet.")
            except Exception as e:
                send_reply(hwnd, f"❌ Notes error: {e}")
            return
        try:
            os.makedirs(os.path.dirname(_notes_file), exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            with open(_notes_file, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {note_text}\n")
            send_reply(hwnd, f"📝 Note saved ✅")
        except Exception as e:
            send_reply(hwnd, f"❌ Note save error: {e}")
        return

    # 10. ZULU COUNTDOWN [date]
    if upper.startswith("ZULU COUNTDOWN"):
        date_str = msg.strip()[len("ZULU COUNTDOWN"):].strip()
        if not date_str:
            send_reply(hwnd, "Format: ZULU COUNTDOWN 25 Dec 2026")
            return
        _fmt_list = ["%d %b %Y", "%d %B %Y", "%Y-%m-%d",
                     "%d/%m/%Y", "%d-%m-%Y", "%b %d %Y", "%B %d %Y"]
        target = None
        for fmt in _fmt_list:
            try:
                target = datetime.datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue
        if target is None:
            send_reply(hwnd, f"❌ Couldn't parse: '{date_str}'\nTry: 25 Dec 2026  or  2026-12-25")
            return
        today = datetime.date.today()
        delta = (target - today).days
        if delta > 0:
            send_reply(hwnd, f"⏳ {delta} days until {target.strftime('%d %b %Y')} 🗓️")
        elif delta == 0:
            send_reply(hwnd, f"🎉 {target.strftime('%d %b %Y')} is TODAY!")
        else:
            send_reply(hwnd, f"📅 {target.strftime('%d %b %Y')} was {abs(delta)} days ago.")
        return

    # 11. ZULU REMIND DAILY [time] [message]
    if upper.startswith("ZULU REMIND DAILY"):
        _daily_file = r"D:\AI_Agency_Work\System_Logs\zulu_daily_reminders.json"
        rest = msg.strip()[len("ZULU REMIND DAILY"):].strip()
        m_time = re.match(r'^(\d{1,2}(?::\d{2})?(?:am|pm)?)\s+(.+)$', rest, re.IGNORECASE)
        if not m_time:
            send_reply(hwnd, "Format: ZULU REMIND DAILY 8am drink water\nOr: ZULU REMIND DAILY 08:00 take medicine")
            return
        time_raw    = m_time.group(1).lower()
        remind_msg  = m_time.group(2).strip()
        try:
            if "am" in time_raw or "pm" in time_raw:
                fmt = "%I:%M%p" if ":" in time_raw else "%I%p"
                t   = datetime.datetime.strptime(time_raw.upper(), fmt)
            else:
                parts_t = time_raw.split(":")
                t = datetime.datetime.combine(
                    datetime.date.today(),
                    datetime.time(int(parts_t[0]), int(parts_t[1]) if len(parts_t) > 1 else 0)
                )
            remind_hhmm = t.strftime("%H:%M")
        except Exception:
            send_reply(hwnd, f"❌ Couldn't parse time '{time_raw}'. Try: 8am  or  08:00")
            return
        try:
            os.makedirs(os.path.dirname(_daily_file), exist_ok=True)
            reminders = []
            if os.path.exists(_daily_file):
                with open(_daily_file, "r", encoding="utf-8") as f:
                    reminders = json.load(f)
            reminders.append({"message": remind_msg, "time": remind_hhmm, "last_fired": ""})
            with open(_daily_file, "w", encoding="utf-8") as f:
                json.dump(reminders, f, indent=2)
            send_reply(hwnd, f"🔔 Daily reminder set ✅\n  '{remind_msg}'  at  {remind_hhmm}  every day")
        except Exception as e:
            send_reply(hwnd, f"❌ Daily reminder error: {e}")
        return

    # ── Active guard ───────────────────────────────────────────────────────
    if not ZSTATE.get("is_active"):
        return

    # ── Activation + task dispatch ─────────────────────────────────────────
    has_trigger = TRIGGER_WORD in upper
    user_active = is_activated(chat_name)

    if has_trigger:
        activate_user(chat_name)
        task = msg.strip()
        if task.upper().startswith(TRIGGER_WORD):
            task = task[len(TRIGGER_WORD):].strip().lstrip("-").strip()
    elif user_active:
        task = msg.strip()
        touch_activation(chat_name)
    else:
        print(f" 🔕 Ignored [{chat_name}] — not activated, no trigger")
        push_event("ignored", {"chat": chat_name, "msg": msg[:60]})
        return

    if not task:
        send_reply(hwnd,
            "🙏 Sure Ma'am — what would you like me to do?" if user_type == "GF"
            else "🛰️ Sure Boss — what task do you want me to do?")
        return

    push_event("task", {"chat": chat_name, "user_type": user_type, "task": task[:100]})
    ZBUS.emit("task_received", {
        "user"     : chat_name,
        "task"     : task,
        "user_type": user_type,
    })
    send_reply(hwnd,
        "🙏 Zulu Ack: Got it Ma'am. Working on it... 🤖" if user_type == "GF"
        else "🛰️ Zulu Ack: Got it Boss. Working on it... 🤖")
    print(f" 🔥 TASK [{chat_name}] | {user_type} | '{task}'")

    # FIX 2: Tell boardroom which chat to reply to BEFORE launching.
    #         Previously boardroom always used the last BOSS chat name, so GF
    #         tasks had their results sent to Boss's chat instead of GF's.
    set_boss_chat(chat_name)

    with _lock_boardroom:
        # FIX: Run boardroom in a background thread so the scanner doesn't freeze!
        threading.Thread(target=launch_boardroom, args=(task, user_type), daemon=True).start()

# ─────────────────────────────────────────────────────────────────────────────
# ── OWN_PREFIXES — blocks ALL ZULU outgoing messages from being re-processed
# FIX 4: Added boardroom reply prefixes ("ZULU online, Boss.", "Done! " etc.)
#         so the scan loop never treats our own WA messages as new commands.
# ─────────────────────────────────────────────────────────────────────────────
OWN_PREFIXES = (
    # Tray direct replies
    "🫡", "🛰️", "🙏", "👋 Hello! I'm ZULU",
    "🤖 ", "📝 Got it", "📬", "📭",
    "😊 You've gone", "😊 The person",
    "👍 Got it", "🔍 Pinging", "🛡️ ZULU",
    "🔓 Access", "🎯 Msgbox", "⚠️", "✅",
    "Zulu Ack", "🔒", "🔑", "⏰", "🎮",
    "💰", "📦", "📡", "🧠", "📁", "🔁",
    # v13.6 Instant command replies
    "😂 ", "💡 \"",                     # joke, quote
    "🎲 ", "🪙 ",                        # dice, flip
    "🔢 ", "❌ ",                         # calc, errors
    "🕐 ", "🌐 ", "🔤 ",                  # time, ping, translate
    "📝 Note", "📝 Your notes", "📝 No notes",  # notes
    "⏳ ", "🗓️", "🎉 ",                  # countdown
    "🔔 Daily",                          # daily remind
    # Boardroom greeting lines (these start with bare "ZULU" — FIX 4)
    "ZULU online, Boss",
    "ZULU at your service",
    "ZULU back online",
    "ZULU going offline",
    # Boardroom result / status lines
    "Done! ",
    "Done (backup brain)",
    "⚡ (cached)",
    "All AI brains",
    "All brains exhausted",
    "All backups failed",
    "Task: ",
    "Mode: ",
    # You: prefix (WhatsApp Desktop shows own messages with this)
    "You:",
    "You: ",
)

# ─────────────────────────────────────────────────────────────────────────────
# 🔔 DAILY REMINDER CHECKER  (fires at matching HH:MM, once per day per entry)
# ─────────────────────────────────────────────────────────────────────────────
_DAILY_REM_FILE = r"D:\AI_Agency_Work\System_Logs\zulu_daily_reminders.json"

def check_daily_reminders(hwnd):
    """Called every scan cycle — fires reminders whose time matches now and haven't run today."""
    if not os.path.exists(_DAILY_REM_FILE):
        return
    try:
        with open(_DAILY_REM_FILE, "r", encoding="utf-8") as f:
            reminders = json.load(f)
        now_hhmm  = datetime.datetime.now().strftime("%H:%M")
        today_str = datetime.date.today().isoformat()
        changed   = False
        for r in reminders:
            if r.get("time") == now_hhmm and r.get("last_fired") != today_str:
                r["last_fired"] = today_str
                changed = True
                send_reply(hwnd, f"🔔 Daily Reminder: {r['message']}")
                print(f" 🔔 Daily reminder fired: {r['message']}")
        if changed:
            with open(_DAILY_REM_FILE, "w", encoding="utf-8") as f:
                json.dump(reminders, f, indent=2)
    except Exception as e:
        print(f" ⚠️ check_daily_reminders: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# 🖥️ SYSTEM TRAY ICON  (pystray — right-click to quit)
# ─────────────────────────────────────────────────────────────────────────────
def _make_tray_image():
    img  = Image.new("RGB", (64, 64), color=(15, 17, 19))
    draw = ImageDraw.Draw(img)
    draw.rectangle([8, 20, 56, 44], fill=(79, 152, 163))
    draw.text((14, 24), "ZU", fill=(255, 255, 255))
    return img

def _on_tray_quit(icon, item):
    icon.stop()
    os._exit(0)

def start_tray_icon():
    if not PYSTRAY_OK:
        return
    try:
        icon = pystray.Icon(
            "ZULU",
            _make_tray_image(),
            "ZULU Sentinel v13.4",
            menu=pystray.Menu(
                pystray.MenuItem("ZULU Sentinel v13.4 — Running", lambda i, it: None),
                pystray.MenuItem("Open Dashboard", lambda i, it: os.startfile("http://localhost:5050")),
                pystray.MenuItem("Quit ZULU", _on_tray_quit),
            )
        )
        tray_thread = threading.Thread(target=icon.run, daemon=True)
        tray_thread.start()
        print("🖥️ System tray icon started.")
    except Exception as e:
        print(f" ⚠️ Tray icon failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 📡 WHATSAPP CONNECTION HEALTH MONITOR  v13.4
# Layer 1 — UI text scan for disconnect strings
# Layer 2 — Sidebar empty 3x in a row → restart
# Layer 3 — Internet ping (FIX 1: guarded so no NameError if requests missing)
# Layer 4 — psutil process heartbeat
# ─────────────────────────────────────────────────────────────────────────────
WA_HEALTH_LOG      = r"D:\AI_Agency_Work\System_Logs\wa_health.json"
WA_DISCONNECT_STRS = [
    "connecting", "reconnecting", "waiting for network",
    "low battery or network", "no internet", "trying to reach whatsapp",
    "network issues", "phone not connected",
]
_wa_empty_count   = 0
_wa_restart_count = 0
_wa_last_ok_time  = time.time()
_wa_notified_boss = False

def _ping_internet():
    # FIX 1: Guard against NameError when requests is not installed.
    #         Previously _requests was used without checking REQUESTS_OK,
    #         causing a NameError crash on every WA health check cycle.
    if not REQUESTS_OK:
        return True   # can't check — assume internet is up
    try:
        r = _requests.get("https://www.google.com", timeout=3)
        return r.status_code == 200
    except Exception:
        return False

def _wa_process_alive():
    if not PSUTIL_OK:
        return True
    for p in psutil.process_iter(["name"]):
        try:
            if "whatsapp" in p.info["name"].lower():
                return True
        except Exception:
            pass
    return False

def _scan_wa_ui_for_disconnect(hwnd):
    """Layer 1: Scan all visible Text controls for reconnection strings."""
    try:
        app = Desktop(backend="uia").window(handle=hwnd)
        for ctrl in app.descendants(control_type="Text"):
            try:
                t = ctrl.window_text().strip().lower()
                for bad in WA_DISCONNECT_STRS:
                    if bad in t:
                        return True, t
            except Exception:
                pass
    except Exception:
        pass
    return False, ""

def _load_wa_health():
    try:
        if os.path.exists(WA_HEALTH_LOG):
            with open(WA_HEALTH_LOG, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"events": [], "total_restarts": 0}

def _save_wa_health(data):
    try:
        os.makedirs(os.path.dirname(WA_HEALTH_LOG), exist_ok=True)
        with open(WA_HEALTH_LOG, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f" ⚠️ _save_wa_health error: {e}")

def _log_wa_event(reason, action, success):
    data = _load_wa_health()
    ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hour = datetime.datetime.now().hour
    data["events"].append({
        "ts"     : ts,
        "hour"   : hour,
        "reason" : reason,
        "action" : action,
        "success": success,
    })
    if action == "restart":
        data["total_restarts"] = data.get("total_restarts", 0) + 1
    data["events"] = data["events"][-100:]
    _save_wa_health(data)
    push_event("wa_health", {
        "ts"     : ts,
        "reason" : reason,
        "action" : action,
        "success": success
    })

def _get_pattern_warning():
    """Self-learning: if same hour has 3+ disconnects, warn Boss."""
    data     = _load_wa_health()
    events   = data.get("events", [])
    if len(events) < 5:
        return ""
    hour_now = datetime.datetime.now().hour
    hits     = sum(1 for e in events if e.get("hour") == hour_now)
    if hits >= 3:
        return (f"⚠️ Pattern: WhatsApp drops {hits}x around "
                f"{hour_now:02d}:00 — check your connection then.")
    return ""

def _kill_whatsapp():
    if PSUTIL_OK:
        for p in psutil.process_iter(["name"]):
            try:
                if "whatsapp" in p.info["name"].lower():
                    p.kill()
            except Exception:
                pass
    os.system("taskkill /f /im WhatsApp.exe >nul 2>&1")

def _restart_whatsapp():
    print(" 🔄 Killing WhatsApp...")
    _kill_whatsapp()
    time.sleep(2)
    print(" 🚀 Relaunching WhatsApp...")
    os.system("start whatsapp://")
    time.sleep(4)
    return win32gui.FindWindow(None, "WhatsApp")

def _notify_boss_wa_fixed(hwnd, message):
    """Send reconnect result to Boss on WhatsApp (runs in background thread)."""
    time.sleep(1.5)
    try:
        app = Desktop(backend="uia").window(handle=hwnd)
        bring_visible(hwnd)
        for item in app.descendants(control_type="DataItem"):
            try:
                name, _ = parse_dataitem_rich(item)
                if detect_user_type(name) == "BOSS":
                    if open_chat(app, hwnd, name):
                        send_reply(hwnd, message)
                    break
            except Exception:
                pass
    except Exception as e:
        print(f" ⚠️ _notify_boss_wa_fixed error: {e}")

def check_wa_health(hwnd, app=None):
    """
    Call once per scan cycle BEFORE processing chats.
    Returns (hwnd, is_healthy) — hwnd may change after restart.
    """
    global _wa_empty_count, _wa_restart_count, _wa_last_ok_time, _wa_notified_boss

    # Layer 4 — process alive?
    if not _wa_process_alive():
        print(" 💀 WhatsApp process dead — relaunching...")
        _log_wa_event("process_dead", "restart", False)
        ZBUS.emit("wa_disconnect", {"reason": "process_dead", "restart_count": _wa_restart_count})
        hwnd = _restart_whatsapp()
        _wa_restart_count += 1
        return hwnd, False

    if not hwnd:
        return hwnd, False

    # Layer 3 — internet alive? Don't blame WA if net is down
    if not _ping_internet():
        print(" 🌐 No internet — waiting (not WA fault, skipping restart)")
        _log_wa_event("no_internet", "wait", True)
        push_event("wa_health", {"reason": "no_internet", "action": "wait"})
        return hwnd, False

    # Layer 1 — UI disconnect string scan
    disconnected, reason = _scan_wa_ui_for_disconnect(hwnd)
    if disconnected:
        print(f" 📡 WA disconnect detected: '{reason}'")
        _wa_restart_count += 1
        _log_wa_event(reason, "restart", False)
        ZBUS.emit("wa_disconnect", {
            "reason"       : reason,
            "restart_count": _wa_restart_count,
        })

        if _wa_restart_count <= 3:
            print(f" 🔄 Restart attempt {_wa_restart_count}/3...")
            new_hwnd   = _restart_whatsapp()
            still_bad, _ = _scan_wa_ui_for_disconnect(new_hwnd) if new_hwnd else (True, "")
            success    = not still_bad

            if success:
                _wa_restart_count = 0
                _wa_last_ok_time  = time.time()
                _wa_notified_boss = False
                pattern_warn      = _get_pattern_warning()
                msg = "✅ ZULU fixed WA disconnect — reconnected OK."
                if pattern_warn:
                    msg += "\n\n" + pattern_warn
                _log_wa_event(reason, "fixed", True)
                ZBUS.emit("wa_reconnected", {"restart_count": _wa_restart_count})
                print(" ✅ WA reconnected successfully.")
                threading.Thread(
                    target=_notify_boss_wa_fixed,
                    args=(new_hwnd, msg),
                    daemon=True
                ).start()
            else:
                _log_wa_event(reason, "restart_failed", False)

            return new_hwnd, success

        else:
            # 3 restarts failed — save alert + notify Boss
            if not _wa_notified_boss:
                _wa_notified_boss  = True
                data               = _load_wa_health()
                total              = data.get("total_restarts", 0)
                alert_lines = [
                    "🆘 Boss — WhatsApp keeps disconnecting!",
                    "ZULU tried 3 restarts — still not fixed.",
                    f"Reason: {reason}",
                    f"Total restarts this session: {total}",
                    "Please check your connection manually. 🙏",
                ]
                alert_msg  = "\n".join(alert_lines)
                _log_wa_event(reason, "gave_up", False)
                push_event("wa_alert", {"msg": alert_msg})
                alert_path = r"D:\AI_Agency_Work\System_Logs\wa_alert.txt"
                try:
                    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    with open(alert_path, "a", encoding="utf-8") as f:
                        f.write(f"\n{'='*50}\n{ts}\n{alert_msg}\n{'='*50}\n")
                    print(" 🆘 Alert saved to wa_alert.txt")
                except Exception:
                    pass
                threading.Thread(
                    target=_notify_boss_wa_fixed,
                    args=(hwnd, alert_msg),
                    daemon=True
                ).start()
            return hwnd, False

    # Layer 2 — sidebar empty 3 times in a row
    if app is not None:
        try:
            count = sum(1 for _ in app.descendants(control_type="DataItem"))
            if count == 0:
                _wa_empty_count += 1
                print(f" ⚠️ Sidebar empty ({_wa_empty_count}/3)")
                if _wa_empty_count >= 3:
                    _wa_empty_count   = 0
                    _wa_restart_count += 1
                    _log_wa_event("empty_sidebar_x3", "restart", False)
                    ZBUS.emit("wa_disconnect", {
                        "reason"       : "empty_sidebar_x3",
                        "restart_count": _wa_restart_count,
                    })
                    hwnd = _restart_whatsapp()
                    return hwnd, False
            else:
                _wa_empty_count   = 0
                _wa_restart_count = 0
                _wa_last_ok_time  = time.time()
                _wa_notified_boss = False
                if not ZSTATE.get("wa_healthy"):
                    ZBUS.emit("wa_reconnected", {"restart_count": 0})
        except Exception:
            pass

    return hwnd, True

# ─────────────────────────────────────────────────────────────────────────────
# 🔄 MAIN SCAN LOOP
# ─────────────────────────────────────────────────────────────────────────────
def scan_all_chats():
    global last_seen_msgs, _first_scan_done

    # Gaming mode check — pause ZULU if fullscreen game detected
    check_gaming_mode()
    if _gaming_mode:
        time.sleep(1.5)
        return

    hwnd = win32gui.FindWindow(None, "WhatsApp")
    if not hwnd:
        wake_whatsapp()
        hwnd = win32gui.FindWindow(None, "WhatsApp")
        if not hwnd:
            print("❌ WhatsApp not found.")
            return

    bring_visible(hwnd)
    get_msgbox_center(hwnd)

    # 📡 WA health check — must pass before processing any chats
    hwnd, wa_healthy = check_wa_health(hwnd)
    if not wa_healthy:
        print(' 📡 WA not healthy — skipping scan cycle')
        return

    if pythoncom:
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass

    try:
        app   = Desktop(backend="uia").window(handle=hwnd)
        chats = get_sidebar_chats(app, n=12)

        # Re-run Layer 2 sidebar check now that we have app object
        hwnd, wa_healthy = check_wa_health(hwnd, app=app)
        if not wa_healthy:
            return

        check_idle_timeouts(app, hwnd)

        is_active = ZSTATE.get("is_active")
        print(f"\n{'='*55}")
        print(f"📋 {len(chats)} chats | Active: {is_active} | "
              f"Activated: {list(activated_users.keys())}")

        # ── Silent first scan — seed without replying ─────────────────────
        if not _first_scan_done:
            with _lock_seen:
                for chat in chats:
                    last_seen_msgs[chat["name"]] = chat["last_msg"]
                    print(f" 🌱 [seed] [{chat['name']}] → seeded silently")
            _first_scan_done = True
            push_event("startup", {
                "chats"  : len(chats),
                "active" : is_active,
                "seeded" : [c["name"] for c in chats]
            })
            print(" ✅ First scan seeded — now watching for NEW messages only.")
            return

        # ── Normal processing from 2nd scan onwards ───────────────────────
        check_daily_reminders(hwnd)    # v13.6 — fires daily reminders if time matches
        scan_events = []
        for chat in chats:
            name      = chat["name"]
            last_msg  = chat["last_msg"]
            user_type = chat["user_type"]

            print(f" 👁️ [{name}] ({user_type}) | '{last_msg[:45]}'")
            scan_events.append({"chat": name, "type": user_type, "msg": last_msg[:45]})

            with _lock_seen:
                seen_val = last_seen_msgs.get(name, "")

            if last_msg == seen_val:
                continue

            # FIX 4: OWN_PREFIXES now includes boardroom reply starters
            if any(last_msg.startswith(p) for p in OWN_PREFIXES):
                with _lock_seen:
                    last_seen_msgs[name] = last_msg
                continue

            with _lock_seen:
                last_seen_msgs[name] = last_msg

            if not last_msg.strip():
                continue

            if user_type == "UNKNOWN" and is_elevated(name):
                if open_chat(app, hwnd, name):
                    process_boss_message(hwnd, last_msg, "BOSS", name)
            elif user_type in ("BOSS", "GF"):
                if open_chat(app, hwnd, name):
                    process_boss_message(hwnd, last_msg, user_type, name)
            elif user_type == "FAMILY":
                if open_chat(app, hwnd, name):
                    handle_unknown_user(hwnd, name, last_msg)
            elif user_type == "UNKNOWN":
                if open_chat(app, hwnd, name):
                    handle_unknown_user(hwnd, name, last_msg)

        push_event("scan", {
            "chats"    : len(chats),
            "active"   : ZSTATE.get("is_active"),
            "activated": list(activated_users.keys()),
            "events"   : scan_events
        })

    except Exception as e:
        print(f"⚠️ Scan error: {e}")
        push_event("error", {"msg": str(e)})
    finally:
        if pythoncom:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

# ─────────────────────────────────────────────────────────────────────────────
# 🚀 ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("🛡️ ZULU SENTINEL v13.6 — 10 Instant Commands Added")
    print("=" * 55)
    print(f" Trigger word  : {TRIGGER_WORD}")
    print(f" Off command   : {OFF_CMD}")
    print(f" Master code   : {MASTER_CODE}")
    print(f" Dashboard push: {DASHBOARD_PUSH} → {DASHBOARD_URL}")
    print(f" Presence mode : {ZSTATE.get('presence_mode')}")
    print()
    print(" BOSS / GF rules:")
    print(" → Send ZULU to activate for 30 min")
    print(" → After that, just send task directly")
    print(" → Inactivity 30 min resets activation")
    print(" → All commands always available")
    print()
    print(" Unknown user rules:")
    print(f" → Send '{MASTER_CODE}' → elevated to BOSS")
    print(" → Unique Ref ID per session")
    print(" → Goodbye after 2 min idle")
    print(f" → Logs saved to: {REQUESTS_LOG}")
    print()
    print(" v13.5 fixes:")
    print(" → FIX 1: _ping_internet NameError when requests not installed")
    print(" → FIX 2: GF reply now goes to GF's chat (not Boss's)")
    print(" → FIX 3: send_reply AllowSetForegroundWindow — reliable focus")
    print(" → FIX 4: OWN_PREFIXES extended — no more echo loop on own msgs")
    print(" → FIX 5: _loop_triggers extended — boardroom replies blocked")
    print(" → FIX 6: SPEED — bring_visible/send_reply/open_chat all faster")
    print("=" * 55)
    print()
    print("🔍 Startup brain check...")
    check_all_pings()
    print(get_status_report())
    print()

    start_tray_icon()

    while True:
        try:
            scan_all_chats()
        except KeyboardInterrupt:
            print("\n👋 ZULU shutting down.")
            push_event("shutdown", {})
            break
        except Exception as e:
            print(f"⚠️ Loop error: {e}")
            push_event("error", {"msg": str(e)})
        time.sleep(0.5)
# ═══════════════════════════════════════════════════════════════════════════════
# ZULU v14.0 — PATCH FILE
# Apply these changes to wire up zulu_pc.py and zulu_voice.py
# ═══════════════════════════════════════════════════════════════════════════════


# ───────────────────────────────────────────────────────────────────────────────
# PATCH 1 ── zulu_tray.py
# ───────────────────────────────────────────────────────────────────────────────

# ── Step 1: Add import near the top (after "from boardroom_engine import ...")
# ─────────────────────────────────────────────────────────────────────────────
"""
from zulu_pc import handle_pc_command
"""

# ── Step 2: Add split_message utility (paste just above send_reply)
# ─────────────────────────────────────────────────────────────────────────────
"""
# ─────────────────────────────────────────────────────────────────────────────
# ✂️  SPLIT LONG MESSAGES  (WhatsApp ~4096 char limit)
# Splits at sentence boundaries so messages read cleanly.
# ─────────────────────────────────────────────────────────────────────────────
def split_message(text: str, max_len: int = 3800) -> list[str]:
    if len(text) <= max_len:
        return [text]
    parts  = []
    while len(text) > max_len:
        cut = max_len
        # Try to cut at last sentence end before the limit
        for sep in ('\n\n', '\n', '. ', '! ', '? '):
            pos = text.rfind(sep, 0, max_len)
            if pos > max_len // 2:  # only cut here if it's past halfway
                cut = pos + len(sep)
                break
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        parts.append(text)
    return parts


def send_reply_long(hwnd, message: str, user_type: str = "BOSS"):
    \"\"\"
    Sends message in chunks if it exceeds WhatsApp's limit.
    Use this instead of send_reply() for AI-generated responses.
    \"\"\"
    chunks = split_message(message)
    if len(chunks) == 1:
        return send_reply(hwnd, message)
    # Prefix multi-part messages
    for i, chunk in enumerate(chunks, 1):
        header = f"({i}/{len(chunks)}) " if len(chunks) > 1 else ""
        send_reply(hwnd, header + chunk)
        if i < len(chunks):
            time.sleep(0.4)  # small pause between parts
    return True
"""

# ── Step 3: In process_boss_message, add PC command router as the FIRST check
#    after the loop-guard and always-on commands (ZULU OFF / ZULU ON / ZULU STATUS)
#    and BEFORE the activation check.
#    Find the block that starts "if 'ZULU OFF' in upper:" and add this block
#    AFTER the instant commands section (after ZULU COUNTDOWN etc.), BEFORE:
#    "# ── Activation required below this line ──"
# ─────────────────────────────────────────────────────────────────────────────
"""
    # ── 🖥️  PC CONTROL COMMANDS (zulu_pc.py) — zero AI, instant ───────────────
    # Screenshot, open/close apps, volume, lock screen, brightness,
    # browser, clipboard, file ops, remember/recall
    pc_handled, pc_response = handle_pc_command(
        msg.strip()[len("ZULU "):] if upper.startswith("ZULU ") else msg.strip(),
        user_type
    )
    if pc_handled:
        send_reply(hwnd, pc_response)
        ZMEM.remember_task(user_type, msg[:60], "pc_control", pc_response[:80])
        return

    # ── 🌐  ZULU GOOGLE / ZULU YOUTUBE ────────────────────────────────────────
    if upper.startswith("ZULU GOOGLE "):
        q = msg.strip()[len("ZULU GOOGLE "):].strip()
        from zulu_pc import google_search
        send_reply(hwnd, google_search(q))
        return

    if upper.startswith("ZULU YOUTUBE "):
        q = msg.strip()[len("ZULU YOUTUBE "):].strip()
        from zulu_pc import youtube_search
        send_reply(hwnd, youtube_search(q))
        return

    # ── 🎙️  ZULU VOICE STATUS ────────────────────────────────────────────────
    if "ZULU VOICE STATUS" in upper or "ZULU VOICE" == upper.strip():
        try:
            from zulu_voice import voice_status
            send_reply(hwnd, voice_status())
        except ImportError:
            send_reply(hwnd, "❌ zulu_voice.py not installed.")
        return

    if "ZULU VOICE ON" in upper:
        try:
            from zulu_voice import start_voice_engine
            ok = start_voice_engine()
            send_reply(hwnd, "🎙️ Voice engine started!" if ok else "❌ Voice engine failed — check dependencies.")
        except ImportError:
            send_reply(hwnd, "❌ zulu_voice.py not found.")
        return

    if "ZULU VOICE OFF" in upper:
        try:
            from zulu_voice import stop_voice_engine
            stop_voice_engine()
            send_reply(hwnd, "🔇 Voice engine stopped.")
        except ImportError:
            send_reply(hwnd, "❌ zulu_voice.py not found.")
        return
"""

# ── Step 4: Update the ZULU HELP message to add new commands
# ─────────────────────────────────────────────────────────────────────────────
#   Add these lines inside the send_reply in the ZULU HELP handler:
"""
            " ZULU OPEN Chrome → open app\n"
            " ZULU CLOSE Spotify → kill app\n"
            " ZULU SCREENSHOT → capture screen\n"
            " ZULU VOLUME UP/DOWN/50 → volume\n"
            " ZULU MUTE / UNMUTE → toggle mute\n"
            " ZULU LOCK SCREEN → lock PC\n"
            " ZULU SLEEP PC → sleep\n"
            " ZULU BRIGHTNESS 70 → set brightness\n"
            " ZULU GOOGLE [query] → open Google\n"
            " ZULU YOUTUBE [query] → YouTube search\n"
            " ZULU OPEN https://... → open URL\n"
            " ZULU CLIPBOARD → read clipboard\n"
            " ZULU FIND [filename] → search D:\\\n"
            " ZULU READ FILE [path] → read file\n"
            " ZULU ZIP [folder] → zip a folder\n"
            " ZULU REMEMBER [note] → save memory\n"
            " ZULU RECALL → view memories\n"
            " ZULU FORGET [keyword] → delete memory\n"
            " ZULU VOICE ON/OFF/STATUS → voice engine\n"
"""

# ── Step 5: Add Morning Briefing Scheduler
#    Paste this function near check_daily_reminders():
# ─────────────────────────────────────────────────────────────────────────────
"""
# ─────────────────────────────────────────────────────────────────────────────
# 🌅  AUTO MORNING BRIEFING  (fires once per day at MORNING_BRIEFING_TIME)
# ─────────────────────────────────────────────────────────────────────────────
MORNING_BRIEFING_TIME = "09:00"   # ← change to your preferred time
_morning_sent_date    = None       # tracks which date briefing was sent

def check_morning_briefing(hwnd):
    \"\"\"
    Call this from scan_all_chats() every scan cycle.
    Sends daily briefing to BOSS once per day at MORNING_BRIEFING_TIME.
    \"\"\"
    global _morning_sent_date

    now   = datetime.datetime.now()
    today = now.date()

    if _morning_sent_date == today:
        return   # already sent today

    if now.strftime("%H:%M") != MORNING_BRIEFING_TIME:
        return   # not time yet

    _morning_sent_date = today

    try:
        # Build the briefing (same as ZULU BRIEFING command)
        status         = get_status_report()
        task_lines_str = ZMEM.get_task_context(last_n=5)
        wa_data        = _load_wa_health()
        wa_events      = len(wa_data.get("events", []))
        wa_restarts    = wa_data.get("total_restarts", 0)

        # Pending reminders
        from boardroom_engine import get_reminder_count
        reminders = get_reminder_count()

        # Memories due today (anything remembered with 'today' keyword)
        from zulu_pc import recall_memories
        today_mems_raw = recall_memories("today")
        has_mems = "today" in today_mems_raw.lower()

        briefing = (
            f"☀️ Good morning! ZULU Daily Briefing\n"
            f"{'─'*30}\n"
            f"{status}\n\n"
            f"{task_lines_str}\n\n"
            f"📋 Reminders:\n{reminders}\n\n"
            f"📡 WA Health:\n"
            f"  Events logged: {wa_events}\n"
            f"  Total restarts: {wa_restarts}"
        )
        if has_mems:
            briefing += f"\n\n🧠 You have memories tagged 'today'!\nSend: ZULU RECALL today"

        # Open Boss's chat and send
        boss_chat = ZSTATE.get("boss_chat") or ""
        if boss_chat:
            app = Desktop(backend="uia").window(handle=hwnd)
            if open_chat(app, hwnd, boss_chat):
                send_reply(hwnd, briefing)
                zlog("tray", f"Morning briefing sent to {boss_chat}")
        else:
            zlog("tray", "Morning briefing: no boss chat known yet", "WARN")

    except Exception as e:
        zlog("tray", f"Morning briefing error: {e}", "ERROR")
"""

# ── Step 6: In scan_all_chats(), add morning briefing call
#    Find "check_daily_reminders(hwnd)" and add right below it:
# ─────────────────────────────────────────────────────────────────────────────
"""
        check_morning_briefing(hwnd)    # v14.0 — auto morning briefing at 09:00
"""

# ── Step 7: In __main__, wire voice engine (optional — add after check_all_pings)
# ─────────────────────────────────────────────────────────────────────────────
"""
    # ── Optional: auto-start voice engine on launch ──────────────────────────
    try:
        from zulu_voice import start_voice_engine
        if start_voice_engine():
            print("✅ Voice engine started — say 'Hey ZULU' to activate.")
        else:
            print("⚠️  Voice engine unavailable (install SpeechRecognition pyaudio pyttsx3)")
    except ImportError:
        print("⚠️  zulu_voice.py not found — voice disabled.")
"""

# ── Step 8: Add ZULU STATUS to the BOSS_CHAT state tracking in ZSTATE
#    In the block that sets boss chat from sidebar, add:
#    ZSTATE.set("boss_chat", name)   ← already in get_sidebar_chats(), you're good


# ───────────────────────────────────────────────────────────────────────────────
# PATCH 2 ── zulu_core.py
# Replace the append-only log writer with a rotating one.
# ───────────────────────────────────────────────────────────────────────────────

# Find this function in zulu_core.py:
"""
def zlog(source: str, msg: str, level: str = "INFO"):
    \"\"\"Write to unified log — all modules share one log file.\"\"\"
    ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level:<5}] [{source:<12}] {msg}\n"
    with _lock_log:
        try:
            with open(UNIFIED_LOG, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass
    print(f" 📋 {line.strip()}")
"""

# Replace the entire function with this:
"""
# Log rotation threshold — rename and start fresh when file exceeds this
LOG_MAX_BYTES = 5 * 1024 * 1024   # 5 MB


def _rotate_log_if_needed():
    \"\"\"If UNIFIED_LOG > LOG_MAX_BYTES, rotate it to a dated archive.\"\"\"
    try:
        if not os.path.exists(UNIFIED_LOG):
            return
        if os.path.getsize(UNIFIED_LOG) < LOG_MAX_BYTES:
            return
        ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        archive  = UNIFIED_LOG.replace(".log", f"_{ts}.log")
        os.rename(UNIFIED_LOG, archive)
        # Keep only last 5 archives — delete oldest
        import glob
        archives = sorted(
            glob.glob(UNIFIED_LOG.replace(".log", "_*.log")),
            key=os.path.getmtime
        )
        for old in archives[:-5]:
            try:
                os.remove(old)
            except Exception:
                pass
    except Exception:
        pass


def zlog(source: str, msg: str, level: str = "INFO"):
    \"\"\"Write to unified log — all modules share one log file. Auto-rotates at 5 MB.\"\"\"
    ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level:<5}] [{source:<12}] {msg}\n"
    with _lock_log:
        _rotate_log_if_needed()
        try:
            with open(UNIFIED_LOG, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass
    print(f" 📋 {line.strip()}")
"""


# ───────────────────────────────────────────────────────────────────────────────
# PATCH 3 ── boardroom_engine.py  (screenshot function + send_reply_long)
# ───────────────────────────────────────────────────────────────────────────────

# Find report_to_boss() in boardroom_engine.py.
# Replace all calls to report_to_boss() in launch_boardroom() with
# send_reply_long() for long AI responses. Specifically in these lines:
"""
# BEFORE:
            success = report_to_boss(final_msg, user_type)

# AFTER (add length guard):
            if len(final_msg) > 3800:
                # Import the long sender from tray if available
                try:
                    from zulu_tray import send_reply_long as _srl, _wa_hwnd
                    success = _srl(_wa_hwnd, final_msg, user_type)
                except Exception:
                    success = report_to_boss(final_msg[:3800], user_type)
            else:
                success = report_to_boss(final_msg, user_type)
"""


# ───────────────────────────────────────────────────────────────────────────────
# INSTALL CHECKLIST
# ───────────────────────────────────────────────────────────────────────────────
"""
Run these in your project venv:

  # Voice engine
  pip install SpeechRecognition pyttsx3

  # PyAudio (Windows — use pipwin if direct install fails)
  pip install pyaudio
  # OR:
  pip install pipwin && pipwin install pyaudio

  # Volume control (optional but recommended for precise % control)
  pip install pycaw comtypes

  # Brightness control (optional)
  pip install screen-brightness-control

  # Already installed in your project:
  # psutil ✅  pyautogui ✅  pywin32 ✅  pywinauto ✅
"""

# ───────────────────────────────────────────────────────────────────────────────
# FILE PLACEMENT
# ───────────────────────────────────────────────────────────────────────────────
"""
Place these files in the same folder as your other ZULU files:
  zulu_pc.py         ← new
  zulu_voice.py      ← new
  zulu_core.py       ← patched (log rotation)
  zulu_tray.py       ← patched (new commands + split_message + morning briefing)
  boardroom_engine.py ← optional patch for send_reply_long
  agency_config.py   ← no changes needed
  brain_manager.py   ← no changes needed
"""

# ───────────────────────────────────────────────────────────────────────────────
# NEW COMMANDS SUMMARY (send from WhatsApp to test)
# ───────────────────────────────────────────────────────────────────────────────
"""
🖥️  App Control:
  ZULU OPEN Chrome
  ZULU OPEN VS Code
  ZULU OPEN Spotify
  ZULU CLOSE Discord
  ZULU OPEN https://github.com

🔊  Volume:
  ZULU VOLUME UP
  ZULU VOLUME DOWN 20
  ZULU VOLUME 50         (set to 50%)
  ZULU MUTE / ZULU UNMUTE
  ZULU VOLUME            (check current level)

🔒  System:
  ZULU LOCK SCREEN
  ZULU SLEEP PC
  ZULU SHUTDOWN PC       (60s delay)
  ZULU CANCEL SHUTDOWN
  ZULU RESTART PC

☀️  Brightness:
  ZULU BRIGHTNESS 80
  ZULU BRIGHTNESS        (check current)

📸  Screenshot:
  ZULU SCREENSHOT
  (saves to D:\AI_Agency_Work\Screenshots\)

🌐  Browser:
  ZULU OPEN https://youtube.com
  ZULU GOOGLE latest Python tutorials
  ZULU YOUTUBE lofi music

📋  Clipboard:
  ZULU CLIPBOARD         (read clipboard)
  ZULU READ CLIPBOARD

📁  File ops:
  ZULU FIND budget.xlsx
  ZULU READ FILE D:\path\to\file.py
  ZULU OPEN FILE D:\path\to\file.py
  ZULU ZIP D:\AI_Agency_Work\Projects

🧠  Memory:
  ZULU REMEMBER Netflix password is hunter2
  ZULU RECALL
  ZULU RECALL password
  ZULU FORGET Netflix

🎙️  Voice:
  ZULU VOICE ON          (enable voice engine)
  ZULU VOICE OFF         (disable)
  ZULU VOICE STATUS      (check if running)
  (then say out loud: "Hey ZULU open Chrome")
"""