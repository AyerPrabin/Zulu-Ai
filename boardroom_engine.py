# boardroom_engine.py — ZULU BOARDROOM v13.0 FINAL
# 💰 Crypto | 🔁 Pipelines | 🌍 30-Lang | 📦 Reports | 🧠 Self-Learning | 📁 Organiser

from zulu_core import ZMEM, ZSTATE, ZBUS, zlog
import os, re, time, json, subprocess, datetime, smtplib, ctypes, requests
from collections import Counter
import win32gui, win32con, win32clipboard
import pyautogui
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pywinauto import Desktop
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import BaseTool
from agency_config import PROJECTS_DIR
from brain_manager import (
    BRAINS, ROLE_BRAIN, get_best_brain, mark_offline,
    get_status_report, auto_restore, record_usage, safe_brain_call, get_usage_bar
)
def get_memory_context() -> str:
    return ZMEM.get_task_context(last_n=10)
try:
    import langdetect
    LANGDETECT_OK = True
except ImportError:
    LANGDETECT_OK = False

pyautogui.FAILSAFE = False

WA_LEFT = 100
WA_TOP = 100
WA_WIDTH = 1100
WA_HEIGHT = 750
BASE_DIR = r"D:\AI_Agency_Work"
LOGS_DIR = os.path.join(BASE_DIR, "System_Logs")
MEMORY_FILE = os.path.join(LOGS_DIR, "zulu_memory.json")
SCHEDULE_FILE = os.path.join(LOGS_DIR, "zulu_schedule.json")
AUDIT_LOG = os.path.join(LOGS_DIR, "zulu_audit.log")
PROJECTS_LOG = os.path.join(LOGS_DIR, "zulu_projects.json")
BACKUP_DIR = os.path.join(LOGS_DIR, "backups")
EMAIL_ADDRESS = "ayerprabin95@gmail.com"
EMAIL_PASSWORD = ""
ALLOWED_READ = [BASE_DIR]
ALLOWED_WRITE = [PROJECTS_DIR]

PERMISSIONS = {
    "BOSS": {"email": True, "write_file": True, "run_python": True,
             "screenshot": True, "open_file": True, "reminder": True,
             "search": True, "read_file": True, "list": True},
    "GF":   {"email": False, "write_file": False, "run_python": False,
             "screenshot": False, "open_file": False, "reminder": True,
             "search": True, "read_file": False, "list": False},
}

QUOTA_WORDS = ["quota", "rate limit", "429", "exceeded", "overloaded",
               "too many requests", "limit reached", "tokens",
               "resource_exhausted", "ratelimitexceeded"]
BACKOFF_SECS = [10, 30, 60]
# ─────────────────────────────────────────────────────────────────────────────
# 🌐 LIVE SEARCH + ANSWER VERIFIER
# ─────────────────────────────────────────────────────────────────────────────
LIVE_SEARCH_TRIGGERS = [
    "who is", "who's", "current", "latest", "today", "right now",
    "news", "breaking", "update", "recent", "recently", "live",
    "price", "score", "weather", "rate", "stock", "crypto",
    "president", "prime minister", "ceo", "governor", "minister",
    "2025", "2026", "this year", "this month", "this week"
]

CODE_HINTS = [
    "code", "python", "html", "css", "javascript", "js", "bug", "debug",
    "script", "app", "api", "program", "function", "class", "sql", "react"
]

FILE_HINTS = [
    "create file", "write file", "save file", "open file", "read file",
    "folder", "project", ".py", ".html", ".txt", ".json", ".csv"
]

EMAIL_HINTS = [
    "email", "send email", "mail this", "gmail"
]

REMINDER_HINTS = [
    "remind me", "set reminder", "alert me", "reminder"
]

SEARCH_HINTS = [
    "search", "look up", "find online", "google", "duckduckgo", "web"
]

def needs_live_search(command: str) -> bool:
    c = command.lower().strip()
    return any(k in c for k in LIVE_SEARCH_TRIGGERS)

def detect_task_family(command: str) -> str:
    c = command.lower().strip()

    if any(k in c for k in REMINDER_HINTS):
        return "reminder"
    if any(k in c for k in EMAIL_HINTS):
        return "email"
    if any(k in c for k in CODE_HINTS):
        return "coding"
    if any(k in c for k in FILE_HINTS):
        return "file_task"
    if any(k in c for k in SEARCH_HINTS):
        return "search"
    if needs_live_search(c):
        return "current_question"
    return "general_question"

def live_search(query: str, max_results: int = 5) -> str:
    try:
        url = f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}&format=json&no_redirect=1&no_html=1"
        resp = requests.get(url, timeout=8)
        data = resp.json()
        results = []

        abstract = (data.get("AbstractText") or "").strip()
        if abstract:
            results.append(abstract[:400])

        for item in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(item, dict):
                txt = (item.get("Text") or "").strip()
                if txt:
                    results.append(txt[:250])

        if results:
            return "LIVE WEB FACTS:\n" + "\n".join(f"- {r}" for r in results[:max_results])
    except Exception as e:
        zlog("boardroom", f"live_search api error: {e}", "WARN")

    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = f"https://lite.duckduckgo.com/lite/?q={requests.utils.quote(query)}"
        resp = requests.get(url, headers=headers, timeout=8)
        html = resp.text
        snippets = re.findall(r'<a[^>]*class="result-link"[^>]*>(.*?)</a>', html, re.S)
        cleaned = [re.sub(r"<.*?>", "", s).strip() for s in snippets if s.strip()]
        if cleaned:
            return "LIVE WEB FACTS:\n" + "\n".join(f"- {r}" for r in cleaned[:max_results])
    except Exception as e:
        zlog("boardroom", f"live_search fallback error: {e}", "WARN")

    return ""

def verify_answer_live(command: str, draft_answer: str, user_type: str = "BOSS") -> str:
    if not draft_answer or not str(draft_answer).strip():
        return draft_answer

    live_ctx = live_search(command) if needs_live_search(command) else ""
    if not live_ctx:
        return draft_answer

    try:
        used = []
        verifier, v_id = make_agent(
            "Verifier",
            "Check whether the answer is correct as of today using the supplied live facts. Fix outdated claims. Keep the final answer concise and plain text.",
            "You are ZULU's fact-check verifier. Prefer live facts over stale model memory. Return only the final WhatsApp-ready answer.",
            tools=[],
            used_brains=used,
            brain_role="scribe",
        )

        t1 = Task(
            description=trim_context(
                f"User asked: '{command}'\n\n"
                f"Draft answer:\n{draft_answer}\n\n"
                f"{live_ctx}\n\n"
                "Task:\n"
                "1. Check if the draft is still correct today.\n"
                "2. If outdated or uncertain, correct it using the live facts.\n"
                "3. Output plain text only, max 4 sentences.\n"
                "4. Prefix with '✅ Verified:' if confirmed/corrected from live facts.\n"
            ),
            expected_output="Plain text WhatsApp reply, fact-checked for today.",
            agent=verifier,
        )

        crew = Crew(agents=[verifier], tasks=[t1], process=Process.sequential, verbose=True)
        result, errors = safe_kickoff(crew, {verifier: v_id}, user_type)
        if result and str(result).strip():
            return str(result).strip()[:700]
    except Exception as e:
        print(f" verify_answer_live error: {e}")
    return draft_answer

def has_permission(user_type, action):
    return PERMISSIONS.get(user_type, {}).get(action, False)

def permission_denied_msg(action, user_type):
    return (f"Sorry Ma'am, not allowed to {action}." if user_type == "GF"
            else f"Permission denied: {action}")
BOSS_PIN = "2062"
_verified_numbers = set()

def is_verified(chat_name: str, user_type: str) -> bool:
    if user_type in ("BOSS", "GF"):
        return True
    return chat_name in _verified_numbers

def verify_pin(chat_name: str, pin_attempt: str) -> bool:
    if pin_attempt.strip() == BOSS_PIN:
        _verified_numbers.add(chat_name)
        return True
    return False

def audit(user_type, action, detail, allowed):
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{user_type}] [{'ALLOWED' if allowed else 'BLOCKED'}] {action}: {detail[:120]}\n")
    except Exception:
        pass

def log_project_file(filepath, command):
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        data = []
        if os.path.exists(PROJECTS_LOG):
            with open(PROJECTS_LOG, "r", encoding="utf-8") as f:
                data = json.load(f)
        data.append({"ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                     "file": filepath, "command": command[:100]})
        data = data[-200:]
        with open(PROJECTS_LOG, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f" project log: {e}")
def get_projects_report(date_filter: str = None) -> str:
    try:
        if not os.path.exists(PROJECTS_LOG):
            return "No files created yet."
        with open(PROJECTS_LOG, "r", encoding="utf-8") as f:
            data = json.load(f)
        if date_filter:
            today = datetime.date.today()
            yesterday = today - datetime.timedelta(days=1)
            if "today" in date_filter.lower():
                data = [d for d in data if d["ts"].startswith(str(today))]
            elif "yesterday" in date_filter.lower():
                data = [d for d in data if d["ts"].startswith(str(yesterday))]
        if not data:
            return f"No files found for '{date_filter}'." if date_filter else "No files created yet."
        lines = [f"Files created ({len(data)}):"]
        for item in data[-20:]:
            lines.append(f" [{item['ts']}] {os.path.basename(item['file'])} — {item['command']}")
        return "\n".join(lines)[:600]
    except Exception as e:
        return f"Projects error: {e}"

def undo_last_file() -> str:
    try:
        if not _last_written_file:
            return "No file to undo."
        if not os.path.exists(BACKUP_DIR):
            return "No backups found."
        fname = os.path.basename(_last_written_file)
        backups = sorted([b for b in os.listdir(BACKUP_DIR) if b.startswith(fname)], reverse=True)
        if not backups:
            return f"No backup found for {fname}."
        bpath = os.path.join(BACKUP_DIR, backups[0])
        with open(bpath, "r", encoding="utf-8") as f:
            content = f.read()
        with open(_last_written_file, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Restored {fname} from backup ({backups[0]})."

    except Exception as e:
        return f"Undo error: {e}"

RETRY_QUEUE_FILE = os.path.join(LOGS_DIR, "zulu_retry_queue.json")

def enqueue_retry(command: str, user_type: str):
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        q = []
        if os.path.exists(RETRY_QUEUE_FILE):
            with open(RETRY_QUEUE_FILE, "r", encoding="utf-8") as f:
                q = json.load(f)
        q.append({"ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                  "command": command, "user_type": user_type, "retries": 0})
        q = q[-20:]
        with open(RETRY_QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(q, f, indent=2)
        print(f" Enqueued retry: {command[:60]}")
    except Exception as e:
        print(f" retry queue error: {e}")

def flush_retry_queue():
    try:
        if not os.path.exists(RETRY_QUEUE_FILE):
            return
        with open(RETRY_QUEUE_FILE, "r", encoding="utf-8") as f:
            q = json.load(f)
        remaining = []
        for item in q:
            if item.get("retries", 0) >= 2:
                continue
            print(f" Retrying queued task: {item['command'][:60]}")
            try:
                launch_boardroom(item["command"], item.get("user_type", "BOSS"))
            except Exception as e:
                item["retries"] = item.get("retries", 0) + 1
                remaining.append(item)
                print(f" Retry failed: {e}")
        with open(RETRY_QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(remaining, f, indent=2)
    except Exception as e:
        print(f" flush_retry_queue: {e}")

def get_reminder_count() -> str:
    items = load_schedule()
    pending = [i for i in items if not i.get("done")]
    if not pending:
        return "No pending reminders."
    lines = [f"Pending reminders ({len(pending)}):"]
    for r in pending[:5]:
        lines.append(f" {r['remind_at']} — {r['message'][:60]}")
    return "\n".join(lines)

def get_daily_briefing(user_type: str = "BOSS") -> str:
    ts = datetime.datetime.now().strftime("%A, %d %b %Y %H:%M")
    mem = load_memory()
    recent_tasks = mem.get("tasks", [])[-5:]
    task_lines = "\n".join(f" [{t['ts'][11:16]}] {t['type'].upper()}: {t['command'][:50]}"
                            for t in recent_tasks) if recent_tasks else " None yet."
    reminders = get_reminder_count()
    status = get_status_report()
    briefing = (
        f"ZULU Daily Briefing — {ts}\n"
        f"{'='*35}\n"
        f"AI Status:\n{status}\n\n"
        f"Recent Tasks:\n{task_lines}\n\n"
        f"Reminders:\n{reminders}"
    )
    return briefing[:950]

_last_written_file = None

def backup_before_write(filepath):
    try:
        if not os.path.exists(filepath):
            return
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        bpath = os.path.join(BACKUP_DIR, f"{os.path.basename(filepath)}.{ts}.bak")
        with open(filepath, "r", encoding="utf-8", errors="ignore") as fin:
            with open(bpath, "w", encoding="utf-8") as fout:
                fout.write(fin.read())
    except Exception:
        pass

def get_audit_report(last_n: int = 10) -> str:
    try:
        if not os.path.exists(AUDIT_LOG):
            return "No audit log yet."
        with open(AUDIT_LOG, "r", encoding="utf-8") as f:
            lines = f.readlines()
        recent = lines[-last_n:]
        if not recent:
            return "Audit log is empty."
        return "Last actions:\n" + "".join(recent[-last_n:])[:600]
    except Exception as e:
        return f"Audit error: {e}"

def detect_language(text):
    if not LANGDETECT_OK:
        return "en"
    try:
        return langdetect.detect(text)
    except Exception:
        return "en"

def get_language_instruction(text, user_type):
    if user_type == "BOSS":
        return "Reply in English."
    lang = detect_language(text)
    # Extended South Asian + global language support (especially for Mum/GF)
    lang_names = {
        "hi": "Hindi",    "ur": "Urdu",       "pa": "Punjabi",   "bn": "Bengali",
        "gu": "Gujarati", "mr": "Marathi",     "ta": "Tamil",     "te": "Telugu",
        "kn": "Kannada",  "ml": "Malayalam",   "si": "Sinhala",   "ne": "Nepali",
        "es": "Spanish",  "fr": "French",      "ar": "Arabic",    "pt": "Portuguese",
        "de": "German",   "it": "Italian",     "ru": "Russian",   "ja": "Japanese",
        "zh-cn": "Chinese", "tr": "Turkish",   "ko": "Korean",    "nl": "Dutch",
        "pl": "Polish",   "ro": "Romanian",    "sv": "Swedish",   "da": "Danish",
    }
    if lang == "en":
        return "Reply in English."
    name = lang_names.get(lang, lang.upper())
    return (f"IMPORTANT: The person is messaging in {name}. "
            f"You MUST reply ONLY in {name}. Do NOT reply in English. "
            f"Be warm, friendly and easy to understand in {name}.")

MAX_CONTEXT_TOKENS = 1800  # ~7200 chars — safe limit per agent handoff

def trim_context(text, max_tokens=MAX_CONTEXT_TOKENS):
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return f"[...trimmed...]\n{text[-max_chars:]}"

_task_start_time = None

def start_timer():
    global _task_start_time
    _task_start_time = time.time()

def get_elapsed():
    if _task_start_time is None:
        return ""
    secs = int(time.time() - _task_start_time)
    return f"{secs//60}m {secs%60}s" if secs >= 60 else f"{secs}s"

def detect_tone(command):
    words = len(command.split())
    if words <= 4:
        return "short"
    if words >= 15:
        return "detailed"
    return "normal"

def tone_instruction(tone, user_type):
    if user_type == "GF":
        return "Be warm and friendly."
    if tone == "short":
        return "Boss is in a hurry. 1-2 sentences max."
    if tone == "detailed":
        return "Boss wants detail. Give thorough explanation."
    return "Normal concise reply."

_boss_chat_name = None
_current_user_type = "BOSS"
_current_command = ""

def set_boss_chat(name):
    global _boss_chat_name
    _boss_chat_name = name

def get_boss_chat():
    return _boss_chat_name or ""

def set_current_user(user_type):
    global _current_user_type
    _current_user_type = user_type

def get_current_user():
    return _current_user_type

def load_memory():
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"tasks": [], "preferences": {}, "patterns": []}

def save_memory(mem):
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(mem, f, indent=2)
    except Exception as e:
        print(f" memory save: {e}")

def get_memory_context():
    mem = load_memory()
    tasks = mem.get("tasks", [])[-10:]
    if not tasks:
        return "No previous tasks."
    lines = ["Boss task history:"]
    for t in tasks:
        lines.append(f" [{t['ts']}] {t['type'].upper()}: {t['command'][:80]}")
    return trim_context("\n".join(lines))

def load_schedule():
    try:
        if os.path.exists(SCHEDULE_FILE):
            with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def save_schedule(items):
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)
    except Exception as e:
        print(f" schedule save: {e}")

def add_reminder(message, remind_at):
    items = load_schedule()
    items.append({"id": len(items)+1, "message": message,
                  "remind_at": remind_at.strip(), "done": False})
    save_schedule(items)
    return f"Reminder set for {remind_at}: {message}"

def check_reminders():
    items = load_schedule()
    now = datetime.datetime.now().strftime("%H:%M")
    nowdt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    changed = False
    for item in items:
        if item["done"]:
            continue
        rt = item["remind_at"].strip()
        if rt == now or rt == nowdt:
            _windows_toast("ZULU Reminder", item["message"])
            item["done"] = True
            changed = True

def _windows_toast(title: str, message: str):
    try:
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# 💰 CRYPTO & STOCK TRACKER
# ─────────────────────────────────────────────────────────────────────────────
PRICE_ALERTS_FILE = os.path.join(LOGS_DIR, "zulu_price_alerts.json")

def load_price_alerts() -> list:
    try:
        if os.path.exists(PRICE_ALERTS_FILE):
            with open(PRICE_ALERTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def save_price_alerts(alerts: list):
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(PRICE_ALERTS_FILE, "w", encoding="utf-8") as f:
            json.dump(alerts, f, indent=2)
    except Exception as e:
        print(f"[price alerts save] {e}")

def get_crypto_price(symbol: str) -> str:
    """Fetch live crypto price from CoinGecko (free, no key)."""
    try:
        ids = {
            "btc":"bitcoin","eth":"ethereum","bnb":"binancecoin",
            "sol":"solana","xrp":"ripple","ada":"cardano",
            "doge":"dogecoin","dot":"polkadot","matic":"matic-network",
            "ltc":"litecoin","link":"chainlink","avax":"avalanche-2",
        }
        sym = symbol.lower().strip("$")
        coin_id = ids.get(sym, sym)
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd,gbp&include_24hr_change=true"
        r = requests.get(url, timeout=8)
        data = r.json()
        if coin_id in data:
            d = data[coin_id]
            usd = d.get("usd", "?")
            gbp = d.get("gbp", "?")
            chg = d.get("usd_24h_change", 0)
            arrow = "📈" if chg >= 0 else "📉"
            return f"{symbol.upper()}: ${usd:,.2f} / £{gbp:,.2f} {arrow} {chg:+.2f}% (24h)"
        return f"Could not find price for {symbol}"
    except Exception as e:
        return f"Price error: {e}"

def check_price_alerts() -> list:
    """Check all price alerts — return triggered ones."""
    alerts = load_price_alerts()
    triggered = []
    remaining = []
    for alert in alerts:
        try:
            price_str = get_crypto_price(alert["symbol"])
            # Parse current price
            import re as _re
            m = _re.search(r"\$([\d,]+\.?\d*)", price_str)
            if m:
                current = float(m.group(1).replace(",",""))
                target  = float(alert["target"])
                direction = alert.get("direction","above")
                hit = (direction == "above" and current >= target) or                       (direction == "below" and current <= target)
                if hit:
                    triggered.append(f"🚨 ALERT: {alert['symbol'].upper()} hit ${target:,.2f}! {price_str}")
                else:
                    remaining.append(alert)
            else:
                remaining.append(alert)
        except Exception:
            remaining.append(alert)
    if len(remaining) != len(alerts):
        save_price_alerts(remaining)
    return triggered

def add_price_alert(symbol: str, target: float, direction: str = "above") -> str:
    alerts = load_price_alerts()
    alerts.append({"symbol": symbol.upper(), "target": target, "direction": direction})
    save_price_alerts(alerts)
    return f"✅ Alert set: notify when {symbol.upper()} goes {direction} ${target:,.2f}"



# ─────────────────────────────────────────────────────────────────────────────
# 🔁 TASK PIPELINE BUILDER
# Build automated chains: "every day at 6pm: search news → email me → remind"
# ─────────────────────────────────────────────────────────────────────────────
PIPELINE_FILE = os.path.join(LOGS_DIR, "zulu_pipelines.json")

def load_pipelines() -> list:
    try:
        if os.path.exists(PIPELINE_FILE):
            with open(PIPELINE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def save_pipelines(pipes: list):
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(PIPELINE_FILE, "w", encoding="utf-8") as f:
            json.dump(pipes, f, indent=2)
    except Exception as e:
        print(f"[pipeline save] {e}")

def add_pipeline(name: str, schedule: str, steps: list) -> str:
    """
    Add a named pipeline.
    schedule: "daily HH:MM" | "weekly MON HH:MM" | "once HH:MM"
    steps: list of task strings e.g. ["search bitcoin news", "email me summary"]
    """
    pipes = load_pipelines()
    pipes.append({
        "name": name,
        "schedule": schedule,
        "steps": steps,
        "last_run": None,
        "enabled": True,
    })
    save_pipelines(pipes)
    return f"✅ Pipeline '{name}' created with {len(steps)} steps. Schedule: {schedule}"

def run_pipeline(pipe: dict, user_type: str = "BOSS") -> str:
    """Execute all steps of a pipeline sequentially."""
    results = []
    for i, step in enumerate(pipe.get("steps", []), 1):
        try:
            result, _ = run_easy_flow(step, user_type)
            summary = str(result).strip()[:200] if result else "no output"
            results.append(f"Step {i}: {step[:40]} → {summary[:80]}")
        except Exception as e:
            results.append(f"Step {i}: {step[:40]} → ERROR: {e}")
    return f"Pipeline '{pipe['name']}' done:\n" + "\n".join(results)

def check_pipelines(user_type: str = "BOSS") -> list:
    """Check which pipelines are due — run them and return reports."""
    pipes = load_pipelines()
    reports = []
    now = datetime.datetime.now()
    nowstr = now.strftime("%H:%M")
    changed = False
    for pipe in pipes:
        if not pipe.get("enabled", True):
            continue
        sched = pipe.get("schedule", "")
        due = False
        if sched.startswith("daily"):
            t = sched.split()[-1]
            last = pipe.get("last_run", "")
            today = now.strftime("%Y-%m-%d")
            if nowstr == t and not last.startswith(today):
                due = True
        if due:
            report = run_pipeline(pipe, user_type)
            reports.append(report)
            pipe["last_run"] = now.strftime("%Y-%m-%d %H:%M")
            changed = True
    if changed:
        save_pipelines(pipes)
    return reports



def get_project_status_report(period: str = "week") -> str:
    """Rich project status — file counts, types, sizes, recent files."""
    try:
        if not os.path.exists(PROJECTS_DIR):
            return "No projects folder found."
        now   = datetime.datetime.now()
        if period == "today":
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            cutoff = now - datetime.timedelta(days=7)
        elif period == "month":
            cutoff = now - datetime.timedelta(days=30)
        else:
            cutoff = datetime.datetime(2000, 1, 1)
        files = []
        for root, _, fnames in os.walk(PROJECTS_DIR):
            for fn in fnames:
                fp = os.path.join(root, fn)
                try:
                    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fp))
                    size  = os.path.getsize(fp)
                    if mtime >= cutoff:
                        files.append({"name": fn, "path": fp,
                                      "mtime": mtime, "size": size})
                except Exception:
                    pass
        if not files:
            return f"No files found for period: {period}."
        exts       = Counter(os.path.splitext(f["name"])[1].lower() or ".other"
                             for f in files)
        total_kb   = sum(f["size"] for f in files) / 1024
        recent     = sorted(files, key=lambda x: x["mtime"], reverse=True)[:5]
        lines = [f"📦 Project Status ({period}):"]
        lines.append(f"  Files: {len(files)}  |  Total size: {total_kb:.1f} KB")
        lines.append("  Types: " + ", ".join(f"{e}×{n}"
                      for e, n in exts.most_common(6)))
        lines.append("  Recent:")
        for f in recent:
            lines.append(f"  • {f['name']} — {f['mtime'].strftime('%d %b %H:%M')}")
        return "\n".join(lines)
    except Exception as e:
        return f"Project report error: {e}"



def remember_mistake(command: str, error: str, task_type: str = "unknown"):
    """Log a failed task so ZULU learns to avoid the same mistake."""
    mem = load_memory()
    if "mistakes" not in mem:
        mem["mistakes"] = []
    mem["mistakes"].append({
        "ts":      datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "command": command[:120],
        "error":   error[:200],
        "type":    task_type,
    })
    mem["mistakes"] = mem["mistakes"][-50:]   # keep last 50
    save_memory(mem)

def get_mistake_patterns() -> str:
    """Return recent mistake patterns for agents to learn from."""
    mem = load_memory()
    mistakes = mem.get("mistakes", [])[-10:]
    if not mistakes:
        return "No recorded mistakes yet."
    lines = ["Recent ZULU mistakes — avoid repeating these:"]
    for m in mistakes:
        lines.append(f"  [{m['ts']}] {m['type'].upper()}: {m['command'][:60]}"
                     f" → ERROR: {m['error'][:80]}")
    return "\n".join(lines)



# ─────────────────────────────────────────────────────────────────────────────
# 📁 FILE ORGANISER AGENT
# Auto-sorts D:\AgencyWork\Projects into subfolders by type
# ─────────────────────────────────────────────────────────────────────────────
FILE_TYPE_MAP = {
    "HTML"   : [".html", ".htm"],
    "Python" : [".py"],
    "Data"   : [".json", ".csv", ".xml", ".yaml", ".yml"],
    "Docs"   : [".txt", ".md", ".pdf", ".docx", ".doc"],
    "Images" : [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"],
    "Scripts": [".bat", ".sh", ".ps1"],
    "Logs"   : [".log"],
    "Other"  : [],
}

def organise_projects_folder(dry_run: bool = False) -> str:
    """
    Sort all loose files in PROJECTS_DIR into subfolders by type.
    dry_run=True  → report what WOULD happen without moving anything.
    """
    try:
        if not os.path.exists(PROJECTS_DIR):
            return "Projects folder not found."
        moved   = []
        skipped = []
        for fname in os.listdir(PROJECTS_DIR):
            src = os.path.join(PROJECTS_DIR, fname)
            if os.path.isdir(src):
                skipped.append(fname)
                continue
            ext = os.path.splitext(fname)[1].lower()
            folder_name = "Other"
            for cat, exts in FILE_TYPE_MAP.items():
                if ext in exts:
                    folder_name = cat
                    break
            dest_dir = os.path.join(PROJECTS_DIR, folder_name)
            dest     = os.path.join(dest_dir, fname)
            if not dry_run:
                os.makedirs(dest_dir, exist_ok=True)
                if not os.path.exists(dest):
                    os.rename(src, dest)
                    moved.append(f"{fname} → {folder_name}/")
                else:
                    skipped.append(fname + " (duplicate)")
            else:
                moved.append(f"{fname} → {folder_name}/")

        label = "DRY RUN — would move" if dry_run else "Moved"
        lines = [f"📁 File Organiser ({'dry run' if dry_run else 'done'}):"]
        lines.append(f"  {label}: {len(moved)} files")
        for m in moved[:20]:
            lines.append(f"  • {m}")
        if skipped:
            lines.append(f"  Skipped: {len(skipped)} (dirs/duplicates)")
        return "\n".join(lines)
    except Exception as e:
        return f"Organiser error: {e}"


class WriteFileTool(BaseTool):
    name: str = "write_file"
    description: str = "Write/create file. Format: 'filepath|||content'. BOSS only."
    def _run(self, input_str: str) -> str:
        global _last_written_file
        user = get_current_user()
        audit(user, "write_file", input_str[:80], has_permission(user, "write_file"))
        if not has_permission(user, "write_file"):
            return permission_denied_msg("create files", user)
        try:
            if "|||" not in input_str:
                return "Format: filepath|||content"
            filepath, content = input_str.split("|||", 1)
            filepath = filepath.strip()
            if not filepath.startswith(PROJECTS_DIR):
                filepath = os.path.join(PROJECTS_DIR, os.path.basename(filepath))
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            backup_before_write(filepath)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            _last_written_file = filepath
            log_project_file(filepath, _current_command)
            return f"Saved: {filepath}"
        except Exception as e:
            return f"Write error: {e}"

class ReadFileTool(BaseTool):
    name: str = "read_file"
    description: str = "Read file from D:\\AI_Agency_Work\\. BOSS only."
    def _run(self, filepath: str) -> str:
        user = get_current_user()
        audit(user, "read_file", filepath[:80], has_permission(user, "read_file"))
        if not has_permission(user, "read_file"):
            return permission_denied_msg("read files", user)
        try:
            filepath = filepath.strip()
            if not any(filepath.startswith(p) for p in ALLOWED_READ):
                return "Access denied."
            if not os.path.exists(filepath):
                return f"Not found: {filepath}"
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                return trim_context(f.read(), max_tokens=1000)
        except Exception as e:
            return f"Read error: {e}"

class ListFolderTool(BaseTool):
    name: str = "list_folder"
    description: str = "List files in D:\\AI_Agency_Work\\. BOSS only."
    def _run(self, folder: str) -> str:
        user = get_current_user()
        audit(user, "list_folder", folder[:80], has_permission(user, "list"))
        if not has_permission(user, "list"):
            return permission_denied_msg("list folders", user)
        try:
            folder = folder.strip()
            if not folder.startswith(BASE_DIR):
                return "Access denied."
            if not os.path.exists(folder):
                return f"Not found: {folder}"
            return "\n".join(os.listdir(folder)) or "(empty)"
        except Exception as e:
            return f"List error: {e}"

class RunPythonTool(BaseTool):
    name: str = "run_python"
    description: str = "Run a .py file in Projects folder. BOSS only."
    def _run(self, filepath: str) -> str:
        user = get_current_user()
        audit(user, "run_python", filepath[:80], has_permission(user, "run_python"))
        if not has_permission(user, "run_python"):
            return permission_denied_msg("run scripts", user)
        try:
            filepath = filepath.strip()
            if not filepath.startswith(PROJECTS_DIR) or not filepath.endswith(".py"):
                return "Only .py files in Projects folder."
            result = subprocess.run(["python", filepath], capture_output=True,
                                    text=True, timeout=30)
            out = result.stdout[-2000:] if result.stdout else ""
            err = result.stderr[-500:] if result.stderr else ""
            return f"Output:\n{out}\n{('Errors: '+err) if err else ''}"
        except subprocess.TimeoutExpired:
            return "Timed out (30s)."
        except Exception as e:
            return f"Run error: {e}"

class OpenFileTool(BaseTool):
    name: str = "open_file"
    description: str = "Open file in default app. BOSS only."
    def _run(self, filepath: str) -> str:
        user = get_current_user()
        audit(user, "open_file", filepath[:80], has_permission(user, "open_file"))
        if not has_permission(user, "open_file"):
            return permission_denied_msg("open files", user)
        try:
            filepath = filepath.strip()
            if not filepath.startswith(BASE_DIR):
                return "Access denied."
            if not os.path.exists(filepath):
                return f"Not found: {filepath}"
            os.startfile(filepath)
            return f"Opened: {filepath}"
        except Exception as e:
            return f"Open error: {e}"

class WebSearchTool(BaseTool):
    name: str = "web_search"
    description: str = "Search the web via DuckDuckGo. BOSS and GF."
    def _run(self, query: str) -> str:
        user = get_current_user()
        audit(user, "web_search", query[:80], has_permission(user, "search"))
        if not has_permission(user, "search"):
            return permission_denied_msg("search", user)
        try:
            url = f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}&format=json&no_redirect=1"
            resp = requests.get(url, timeout=8)
            data = resp.json()
            results = []
            if data.get("AbstractText"):
                results.append(data["AbstractText"][:500])
            for item in data.get("RelatedTopics", [])[:5]:
                if isinstance(item, dict) and item.get("Text"):
                    results.append(item["Text"][:200])
            return "\n".join(results) if results else f"No results for: {query}"
        except Exception as e:
            return f"Search error: {e}"

class TakeScreenshotTool(BaseTool):
    name: str = "take_screenshot"
    description: str = "Take a screenshot. BOSS only."
    def _run(self, filename: str) -> str:
        user = get_current_user()
        audit(user, "screenshot", filename[:80], has_permission(user, "screenshot"))
        if not has_permission(user, "screenshot"):
            return permission_denied_msg("take screenshots", user)
        try:
            filename = filename.strip()
            if not filename.endswith(".png"):
                filename += ".png"
            filepath = os.path.join(PROJECTS_DIR, filename)
            pyautogui.screenshot().save(filepath)
            log_project_file(filepath, "screenshot")
            return f"Screenshot: {filepath}"
        except Exception as e:
            return f"Screenshot error: {e}"

class SendEmailTool(BaseTool):
    name: str = "send_email"
    description: str = "Send email. Format: 'to|||subject|||body'. BOSS only."
    def _run(self, input_str: str) -> str:
        user = get_current_user()
        audit(user, "send_email", input_str[:80], has_permission(user, "email"))
        if not has_permission(user, "email"):
            return permission_denied_msg("send emails", user)
        if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
            return "Set EMAIL_ADDRESS + EMAIL_PASSWORD in boardroom_engine.py first."
        try:
            parts = input_str.split("|||")
            if len(parts) < 3:
                return "Format: to|||subject|||body"
            to, subject, body = parts[0].strip(), parts[1].strip(), parts[2].strip()
            msg = MIMEMultipart()
            msg["From"] = EMAIL_ADDRESS
            msg["To"] = to
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.sendmail(EMAIL_ADDRESS, to, msg.as_string())
            return f"Email sent to {to}"
        except Exception as e:
            return f"Email error: {e}"

class SetReminderTool(BaseTool):
    name: str = "set_reminder"
    description: str = "Set reminder. Format: 'HH:MM|||message'. BOSS and GF."
    def _run(self, input_str: str) -> str:
        user = get_current_user()
        audit(user, "set_reminder", input_str[:80], has_permission(user, "reminder"))
        if not has_permission(user, "reminder"):
            return permission_denied_msg("set reminders", user)
        try:
            if "|||" not in input_str:
                return "Format: HH:MM|||message"
            t, msg = input_str.split("|||", 1)
            return add_reminder(msg.strip(), t.strip())
        except Exception as e:
            return f"Reminder error: {e}"

class MemoryReadTool(BaseTool):
    name: str = "read_memory"
    description: str = "Read Boss task history."
    def _run(self, query: str) -> str:
        return get_memory_context()

write_tool      = WriteFileTool()
read_tool       = ReadFileTool()
list_tool       = ListFolderTool()
run_tool        = RunPythonTool()
open_tool       = OpenFileTool()
search_tool     = WebSearchTool()
screenshot_tool = TakeScreenshotTool()
email_tool      = SendEmailTool()
reminder_tool   = SetReminderTool()
memory_tool     = MemoryReadTool()

BOSS_ALL_TOOLS   = [write_tool, read_tool, list_tool, run_tool, open_tool,
                    search_tool, email_tool, reminder_tool, memory_tool, screenshot_tool]
BOSS_READ_TOOLS  = [read_tool, list_tool, search_tool, memory_tool]
BOSS_QUICK_TOOLS = [search_tool, memory_tool, reminder_tool, email_tool, screenshot_tool]
GF_TOOLS         = [search_tool, reminder_tool, memory_tool]

def get_tools_for_user(user_type, level="all"):
    if user_type == "BOSS":
        return {"read": BOSS_READ_TOOLS, "quick": BOSS_QUICK_TOOLS}.get(level, BOSS_ALL_TOOLS)
    if user_type == "GF":
        return GF_TOOLS
    return []

_cached_msgbox_be = None

def _learn_msgbox_be(hwnd):
    global _cached_msgbox_be
    try:
        app = Desktop(backend="uia").window(handle=hwnd)
        for ctype in ("Edit", "Document"):
            for e in app.descendants(control_type=ctype):
                try:
                    if not e.is_visible() or not e.is_enabled():
                        continue
                    r = e.rectangle()
                    w, h = r.right-r.left, r.bottom-r.top
                    cx, cy = r.left+w//2, r.top+h//2
                    if w > 200 and h < 60 and cx > 600:
                        _cached_msgbox_be = (cx, cy)
                        return _cached_msgbox_be
                except Exception:
                    continue
    except Exception:
        pass
    rect = win32gui.GetWindowRect(hwnd)
    _cached_msgbox_be = (rect[0]+857, rect[1]+693)
    return _cached_msgbox_be

def set_clipboard(text):
    for _ in range(3):
        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            return True
        except Exception:
            time.sleep(0.3)
    return False

def _safe_fg(hwnd):
    try:
        ctypes.windll.user32.AllowSetForegroundWindow(-1)
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

def _open_target_chat(hwnd, chat_name):
    if not chat_name:
        return True
    try:
        app = Desktop(backend="uia").window(handle=hwnd)
        seen = set()
        for item in app.descendants(control_type="DataItem"):
            raw = item.window_text().strip()
            if not raw or raw in seen:
                continue
            seen.add(raw)
            if chat_name.lower() in raw.lower():
                r = item.rectangle()
                cx = int((r.left + r.right) / 2)
                cy = int((r.top + r.bottom) / 2)
                _safe_fg(hwnd)
                time.sleep(0.3)
                pyautogui.click(cx, cy)
                time.sleep(1.8)
                return True
    except Exception as e:
        print(f" open_target_chat: {e}")
    return False

def report_to_boss(message, user_type="BOSS"):
    try:
        hwnd = win32gui.FindWindow(None, "WhatsApp")
        if not hwnd:
            print(" ❌ WhatsApp NOT FOUND. Please open WhatsApp first.")
            print(f" Message was: {message[:200]}")
            return False
        
        if not set_clipboard(message):
            print(" ❌ Failed to copy message to clipboard.")
            return False
        
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, WA_LEFT, WA_TOP,
                              WA_WIDTH, WA_HEIGHT, win32con.SWP_SHOWWINDOW)
        _safe_fg(hwnd)
        time.sleep(0.5)
        _open_target_chat(hwnd, get_boss_chat())
        
        if _cached_msgbox_be:
            cx, cy = _cached_msgbox_be
        else:
            cx, cy = _learn_msgbox_be(hwnd)
        
        pyautogui.moveTo(cx, cy, duration=0.15)
        pyautogui.click()
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)
        pyautogui.press("enter")
        time.sleep(0.1)
        print(f" ✅ [{user_type}] sent: {message[:80]}")
        return True
    except Exception as e:
        print(f" ❌ report_to_boss error: {e}")
        print(f" Message was: {message[:200]}")
        return False

def build_llm(brain_id):
    b = BRAINS[brain_id]
    kwargs = dict(model=b["model"], api_key=b["api_key"])
    if "base_url" in b:
        kwargs["base_url"] = b["base_url"]
    return LLM(**kwargs)

def make_agent(role, goal, backstory, tools=None, used_brains=None, brain_role=None):
    used_brains = used_brains or []
    bid, brain = get_best_brain(exclude_ids=used_brains, role=brain_role)
    if not bid:
        raise RuntimeError("ALL AI BRAINS OFFLINE")
    used_brains.append(bid)
    print(f" {role} -> [{brain['label']}]")
    return Agent(role=role, goal=goal, backstory=backstory,
                 llm=build_llm(bid), tools=tools or [], verbose=True), bid

def classify_task(command):
    c = command.lower().strip()
    family = detect_task_family(c)

    complex_patterns = [
        r"(make|create|build|write|generate|code|develop|design|setup)\s+.*(app|script|program|tool|html|website|page|file|bot|api|dashboard|form|system)",
        r"(html|css|javascript|python|code|script|program|debug|fix\s+bug|deploy|install)",
        r"(automat|build\s+me|create\s+me|make\s+me|write\s+me|give\s+me\s+a\s+(code|script|file|html))",
    ]
    easy_patterns = [
        r"(what|who|when|where|why|how)\s+(is|are|was|were|does|do|did|can|will)",
        r"(tell\s+me|show\s+me|give\s+me|find|search|look\s+up|explain|summarize|translate)",
        r"(news|weather|price|rate|latest|update|fact|joke|quote|define)",
        r"(remind\s+me|set\s+reminder|remind\s+at|alert\s+me)",
        r"(send\s+email|email\s+to)",
        r"(screenshot|take\s+a\s+pic|capture\s+screen)",
    ]

    if family == "coding" or family == "file_task":
        return {"family": family, "level": "complex"}

    if family in ("reminder", "email", "search", "current_question"):
        return {"family": family, "level": "easy"}

    for pat in complex_patterns:
        if re.search(pat, c):
            return {"family": family, "level": "complex"}

    for pat in easy_patterns:
        if re.search(pat, c):
            return {"family": family, "level": "easy"}

    mem = load_memory()
    for past in reversed(mem.get("tasks", [])[-20:]):
        if any(w in c for w in past["command"].lower().split() if len(w) > 4):
            return {"family": family, "level": past["type"]}

    return {"family": family, "level": "medium"}
def run_easy_flow(command, user_type):
    global _current_command
    _current_command = command
    mem_ctx = get_memory_context()
    tone_msg = tone_instruction(detect_tone(command), user_type)
    lang_msg = get_language_instruction(command, user_type)
    used = []
    tools = get_tools_for_user(user_type, "quick")
    live_ctx = live_search(command) if needs_live_search(command) else ""

    worker, w_id = make_agent(
        "Worker",
        f"Answer accurately and reply directly as WhatsApp message. {tone_msg} {lang_msg}",
        f"Smart ZULU assistant. {mem_ctx}\nPlain text. Max 3 sentences.",
        tools=tools, used_brains=used, brain_role="worker",
    )

    t1 = Task(
        description=trim_context(
            f"Request from {user_type}: '{command}'\n"
            f"Context:\n{mem_ctx}\n"
            f"{live_ctx}\n"
            "Use live facts if provided. Use web_search if still needed. "
            "Answer directly in plain text suitable for WhatsApp. No markdown."
        ),
        expected_output=f"Short WhatsApp reply in correct language. {lang_msg}",
        agent=worker,
    )

    crew = Crew(agents=[worker], tasks=[t1], process=Process.sequential, verbose=True)
    result, errors = safe_kickoff(crew, {worker: w_id}, user_type)

    if result:
        verified = verify_answer_live(command, str(result).strip(), user_type)
        return verified, errors
    return result, errors

def _is_quota_error(err_str):
    return any(w in err_str.lower() for w in QUOTA_WORDS)

def run_medium_flow(command, user_type):
    global _current_command
    _current_command = command
    mem_ctx = get_memory_context()
    tone_msg = tone_instruction(detect_tone(command), user_type)
    lang_msg = get_language_instruction(command, user_type)
    used = []
    tools = get_tools_for_user(user_type, "quick")
    live_ctx = live_search(command) if needs_live_search(command) else ""

    worker, w_id = make_agent(
        "Worker",
        f"Understand and answer fully. {tone_msg}",
        f"Smart ZULU assistant.\n{mem_ctx}",
        tools=tools, used_brains=used, brain_role="worker",
    )

    scribe, s_id = make_agent(
        "Scribe",
        f"Rewrite as clean WhatsApp message. {tone_msg} {lang_msg}",
        "WhatsApp writer. Plain text. Max 4 sentences. No markdown.",
        used_brains=used, brain_role="scribe",
    )

    t1 = Task(
        description=trim_context(
            f"Request from {user_type}: '{command}'\n{mem_ctx}\n{live_ctx}\n"
            "Use live facts if provided. Use tools if needed. Answer fully."
        ),
        expected_output="Accurate answer or action confirmation.",
        agent=worker,
    )

    t2 = Task(
        description=trim_context(
            f"Rewrite as WhatsApp for {user_type}. {tone_msg} {lang_msg} Plain text only."
        ),
        expected_output="Short WhatsApp reply.",
        agent=scribe,
    )

    crew = Crew(agents=[worker, scribe], tasks=[t1, t2], process=Process.sequential, verbose=True)
    result, errors = safe_kickoff(crew, {worker: w_id, scribe: s_id}, user_type)

    if result:
        verified = verify_answer_live(command, str(result).strip(), user_type)
        return verified, errors
    return result, errors

def _is_none_action_error(err_str):
    return "action" in err_str.lower() and ("don't exist" in err_str.lower() or "none" in err_str.lower())

def safe_kickoff(crew, agents_map, user_type="BOSS"):
    """
    Run crew.kickoff() with retry on quota errors.
    On each quota hit: mark that brain offline, notify Boss, then retry with next brain.
    On None-action error: catch cleanly and return None.
    """
    for attempt in range(3):
        try:
            result = crew.kickoff()
            if result is None or str(result).strip() in ("None", ""):
                raise ValueError("Agent returned None action")
            return result, []
        except Exception as e:
            err = str(e)
            if _is_none_action_error(err):
                print(f" Agent None-action error (attempt {attempt+1}) — retrying with cleaner task")
                if attempt == 2:
                    return None, ["Agent confused on this task — please rephrase."]
                time.sleep(2)
                continue
            if _is_quota_error(err):
                wait = BACKOFF_SECS[min(attempt, len(BACKOFF_SECS)-1)]
                offline_notes = []
                for bid in set(agents_map.values()):
                    note = mark_offline(bid, reason=err[:80])
                    offline_notes.append(note)
                    print(f" Brain offline: [{bid}]")
                notify = (
                    f"⚠️ AI brain quota hit (attempt {attempt+1}/3)\n"
                    + "\n".join(offline_notes)
                    + f"\nWaiting {wait}s then trying backup brain..."
                )
                try:
                    report_to_boss(notify, user_type)
                except Exception:
                    pass
                print(f" Quota hit — waiting {wait}s")
                time.sleep(wait)
                auto_restore()
                if attempt == 2:
                    return None, offline_notes
                continue
            raise
    return None, ["All 3 attempts failed."]




# ── COMPLEX FLOW (4 AI) ────────────────────────────────────────────────────────
def run_complex_flow(command, user_type, folder):
    global _current_command
    _current_command = command
    mem_ctx = get_memory_context()
    tone_msg = tone_instruction(detect_tone(command), user_type)
    lang_msg = get_language_instruction(command, user_type)
    used = []

    planner, p_id = make_agent(
        "Visionary",
        f"Understand intent and plan. {tone_msg} Avoid past mistakes: {get_mistake_patterns()[:300]}",
        f"Planner.\n{mem_ctx}\nInterpret intent even if informally worded.",
        tools=get_tools_for_user(user_type, "read"),
        used_brains=used, brain_role="visionary",
    )
    worker, w_id = make_agent(
        "Tech Lead",
        f"Execute plan. Write code/HTML. Save to {folder}. {tone_msg} "
        "Use write_file for every file. HTML = inline CSS+JS. open_file after saving.",
        "Technical executor. Full tool access.",
        tools=get_tools_for_user(user_type, "all"),
        used_brains=used, brain_role="tech",
    )
    reviewer, r_id = make_agent(
        "Reviewer",
        f"Read created files and verify quality. {tone_msg}",
        "Quality guardian. Check completeness and errors.",
        tools=get_tools_for_user(user_type, "read"),
        used_brains=used, brain_role="reviewer",
    )
    scribe, s_id = make_agent(
        "Scribe",
        f"Write WhatsApp reply. {tone_msg} {lang_msg}",
        "ZULU voice. Max 3 sentences. Plain text. Correct language.",
        used_brains=used, brain_role="scribe",
    )
    t1 = Task(
        description=trim_context(
            f"{user_type} said: '{command}'\nMemory:\n{mem_ctx}\n"
            f"Check {folder}. Plan what to build."
        ),
        expected_output="Clear plan: files and purpose.",
        agent=planner,
    )
    t2 = Task(
        description=trim_context(
            f"Execute plan for: '{command}'\nSave to: {folder}\n"
            "HTML: inline CSS+JS -> write_file -> open_file.\n"
            "Python: full script -> write_file. web_search for examples."
        ),
        expected_output="Files created. List of paths.",
        agent=worker,
    )
    t3 = Task(
        description=trim_context(f"Read files in {folder}. Verify complete and correct."),
        expected_output="Approved or corrections list.",
        agent=reviewer,
    )
    t4 = Task(
        description=trim_context(
            f"WhatsApp reply for {user_type}: what was done + file paths. "
            f"{tone_msg} {lang_msg} Plain text. Max 3 sentences."
        ),
        expected_output="Short WhatsApp message.",
        agent=scribe,
    )
    crew = Crew(agents=[planner, worker, reviewer, scribe],
                tasks=[t1, t2, t3, t4], process=Process.sequential, verbose=True)
    return safe_kickoff(crew, {planner: p_id, worker: w_id,
                                reviewer: r_id, scribe: s_id}, user_type)

# ── MAIN ENTRY POINT ──────────────────────────────────────────────────────────
def launch_boardroom(command, user_type="BOSS"):
    command = command.strip()
    cached = ZMEM.get_cached(command)
    if cached:
        report_to_boss(f"⚡ (cached)\n\n{cached}", user_type)
        return
    if not command:
        report_to_boss("Empty command. Try again.", user_type)
        return

    set_current_user(user_type)
    start_timer()
    check_reminders()
    auto_restore()

    bid, _ = get_best_brain()
    if not bid:
        report_to_boss(f"All AI brains offline.\n\n{get_status_report()}", user_type)
        return

    route = classify_task(command)
    task_family = route.get("family", "general_question")
    task_level = route.get("level", "medium")

    if user_type == "GF" and task_level == "complex":
        task_level = "medium"

    try:
        if task_family == "reminder":
            m = re.search(r"(\d{1,2}:\d{2})", command)
            if m:
                remind_at = m.group(1)
                msg = command.replace(remind_at, "").replace("|||", " ").strip(" ,-:")
                result = add_reminder(msg or "Reminder", remind_at)
            else:
                result = "Reminder format: remind me 18:30 call John"
            report_to_boss(result, user_type)
            ZMEM.remember_task(user_type, command, "easy", result)
            return

        if task_family == "search":
            live = live_search(command)
            result = live if live else search_tool._run(command)
            result = verify_answer_live(command, result, user_type)
            report_to_boss(result, user_type)
            ZMEM.remember_task(user_type, command, "easy", result)
            return

        if task_family == "current_question":
            live = live_search(command)
            if live:
                result, errors = run_easy_flow(f"{command}\n\n{live}", user_type)
            else:
                result, errors = run_easy_flow(command, user_type)
        elif task_level == "easy":
            result, errors = run_easy_flow(command, user_type)
        elif task_level == "medium":
            result, errors = run_medium_flow(command, user_type)
            # FALLBACK: if medium fails, try easy
            if not result:
                print(" Medium flow failed, trying easy flow fallback...")
                result, errors = run_easy_flow(command, user_type)
        else:
            folder = PROJECTS_DIR
            result, errors = run_complex_flow(command, user_type, folder)

        if result:
            final_msg = str(result).strip()
            if final_msg and final_msg.lower() != "none":
                success = report_to_boss(final_msg, user_type)
                if success:
                    ZMEM.remember_task(user_type, command, task_level, final_msg)
                    # 📡 Emit task completion event (picked up by zulu_voice, dashboard, etc.)
                    ZBUS.emit("task_done", {
                        "user": user_type,
                        "task": command,
                        "result": final_msg,
                        "mode": task_level
                    })
                else:
                    print(f" Failed to send message back to {user_type}. WhatsApp might not be open.")
            else:
                report_to_boss("No valid response generated. Please try again.", user_type)
                remember_mistake(command, "Empty/None response", task_level)
        else:
            err = "\n".join(errors) if errors else "Task failed. All AI brains may be offline."
            print(f" Error response: {err}")
            report_to_boss(f"❌ Error: {err}", user_type)
            remember_mistake(command, err, task_level)
            # 📡 Emit task failed event
            ZBUS.emit("task_failed", {
                "user": user_type,
                "task": command,
                "error": err
            })

    except Exception as e:
        err = str(e)
        remember_mistake(command, err, task_level)
        report_to_boss(f"Error: {err}", user_type)
        # 📡 Emit task failed event (exception)
        ZBUS.emit("task_failed", {
            "user": user_type,
            "task": command,
            "error": err
        })
