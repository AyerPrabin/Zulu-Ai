import os
# ─────────────────────────────────────────────────────────────────────────────
# 🛡️ AUTHORIZED USERS
# ─────────────────────────────────────────────────────────────────────────────
AUTHORIZED_USERS = {
    "BOSS": {"NAME": "You",              "PHONE": "773818"},
    "GF"  : {"NAME": "Chutiya Plus 🤡", "PHONE": "6454018"}
}

# ⚡ MASTER TRIGGERS
TRIGGER_WORD = "ZULU"
OFF_CMD      = "ZULU OFF"

# 📂 D-DRIVE PATHS
BASE_DIR     = r"D:\AI_Agency_Work"
PROJECTS_DIR = os.path.join(BASE_DIR, "Projects")
LOGS_DIR     = os.path.join(BASE_DIR, "System_Logs")
STATE_FILE   = os.path.join(LOGS_DIR, "state.json")

for folder in [PROJECTS_DIR, LOGS_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# ─────────────────────────────────────────────────────────────────────────────
# 🔑 API KEYS (REMOVED - USING LOCAL OLLAMA ONLY)
# ─────────────────────────────────────────────────────────────────────────────
API_KEYS = {
    # All API keys removed — using Ollama locally (no API costs, no internet needed)
}

print("✅ Configuration verified. Using LOCAL OLLAMA only (no API keys needed).")


# ===============================================================================
# ██  🧠 ZULU CORE                                             ██
# ██  (originally: zulu_core.py                                    ██
# ===============================================================================

# zulu_core.py — ZULU Central Nervous System v13.2
import datetime
import json
import os
import threading
import time
# ─────────────────────────────────────────────────────────────────────────────
# 📂 PATHS
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR    = r"D:\AI_Agency_Work"
LOGS_DIR    = os.path.join(BASE_DIR, "System_Logs")
CORE_FILE   = os.path.join(LOGS_DIR, "zulu_core.json")   # persisted brain
UNIFIED_LOG = os.path.join(LOGS_DIR, "zulu_unified.log") # one log for all

os.makedirs(LOGS_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# 🔒 THREAD SAFETY
# ─────────────────────────────────────────────────────────────────────────────
_lock_mem   = threading.Lock()
_lock_state = threading.Lock()
_lock_bus   = threading.Lock()
_lock_log   = threading.Lock()

# ─────────────────────────────────────────────────────────────────────────────
# 📝 UNIFIED LOGGER — zlog(source, msg)
# Every module calls: zlog("tray", "scan complete")
# ─────────────────────────────────────────────────────────────────────────────
def zlog(source: str, msg: str, level: str = "INFO"):
    """Write to unified log — all modules share one log file."""
    ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level:<5}] [{source:<12}] {msg}\n"
    with _lock_log:
        try:
            with open(UNIFIED_LOG, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass
    print(f" 📋 {line.strip()}")

# ─────────────────────────────────────────────────────────────────────────────
# 🧠 ZMEM — Shared Persistent Memory
# Survives restarts. Any module can read/write.
# Structure:
#   tasks[]         → task history (last 100)
#   convo_context{} → last message per user (for conversation continuity)
#   patterns{}      → learned patterns (task types, peak hours, etc.)
#   brain_scores{}  → self-learning scores (mirror from brain_manager)
#   wa_events[]     → WA health events
#   pipelines[]     → scheduled pipelines
# ─────────────────────────────────────────────────────────────────────────────
_MEM_DEFAULTS = {
    "tasks"        : [],
    "convo_context": {},
    "patterns"     : {},
    "brain_scores" : {},
    "wa_events"    : [],
    "pipelines"    : [],
    "unknown_users": {},
    "muted_contacts": [],
    "response_cache": {},
    "last_saved"   : "",
}

class _SharedMemory:
    """Thread-safe shared memory — persists to JSON every 30s."""

    def __init__(self):
        self._data = dict(_MEM_DEFAULTS)
        self._dirty = False
        self._load()
        self._start_autosave()

    def _load(self):
        try:
            if os.path.exists(CORE_FILE):
                with open(CORE_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                with _lock_mem:
                    for k, v in _MEM_DEFAULTS.items():
                        self._data[k] = saved.get(k, v)
                zlog("core", f"Memory loaded — {len(self._data['tasks'])} tasks, "
                             f"{len(self._data['wa_events'])} WA events")
        except Exception as e:
            zlog("core", f"Memory load error: {e}", "WARN")

    def save(self):
        try:
            with _lock_mem:
                self._data["last_saved"] = datetime.datetime.now().isoformat()
                payload = json.dumps(self._data, indent=2, default=str)
            with open(CORE_FILE, "w", encoding="utf-8") as f:
                f.write(payload)
            self._dirty = False
        except Exception as e:
            zlog("core", f"Memory save error: {e}", "ERROR")

    def _start_autosave(self):
        def _loop():
            while True:
                time.sleep(30)
                if self._dirty:
                    self.save()
        t = threading.Thread(target=_loop, daemon=True)
        t.name = "ZuluCoreSave"
        t.start()

    # ── Public API ──────────────────────────────────────────────────────────

    def get(self, key, default=None):
        with _lock_mem:
            return self._data.get(key, default)

    def set(self, key, value):
        with _lock_mem:
            self._data[key] = value
            self._dirty = True

    def append(self, key, item, max_len=100):
        """Append to a list key, capped at max_len."""
        with _lock_mem:
            lst = self._data.get(key, [])
            lst.append(item)
            self._data[key] = lst[-max_len:]
            self._dirty = True

    # ── Task memory ─────────────────────────────────────────────────────────

    def remember_task(self, user: str, task: str, task_type: str,
                      result_summary: str, brain_used: str = ""):
        entry = {
            "ts"        : datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "user"      : user,
            "task"      : task,
            "type"      : task_type,
            "result"    : result_summary[:200],
            "brain"     : brain_used,
        }
        self.append("tasks", entry, max_len=100)
        
        # Neural Archive Integration (Tier 2)
        try:
            import zulu_neural
            archive_text = f"Task: {task}\nResult: {result_summary}"
            meta = {"user": user, "type": task_type, "brain": brain_used, "ts": entry["ts"]}
            # Run in a background thread to avoid blocking main workflow
            threading.Thread(target=zulu_neural.archive_context, args=(archive_text, meta), daemon=True).start()
        except Exception as e:
            zlog("core", f"Failed to archive to neural memory: {e}", "WARN")

        # Update patterns — track task type frequency
        pats = self._data.get("patterns", {})
        hour = datetime.datetime.now().hour
        pats.setdefault("task_types",  {}).setdefault(task_type, 0)
        pats["task_types"][task_type] += 1
        pats.setdefault("peak_hours",  {}).setdefault(str(hour), 0)
        pats["peak_hours"][str(hour)] += 1
        with _lock_mem:
            self._data["patterns"] = pats
            self._dirty = True
        zlog("core", f"Task remembered: [{user}] {task[:60]}")

    def get_task_context(self, last_n: int = 10) -> str:
        tasks = self.get("tasks", [])[-last_n:]
        if not tasks:
            return "No previous tasks."
        lines = ["📝 Task history:"]
        for t in tasks:
            lines.append(f"  [{t['ts']}] {t['type'].upper()}: {t['task'][:60]}")
        return "\n".join(lines)

    # ── Conversation context ─────────────────────────────────────────────────

    def set_convo(self, chat_name: str, msg: str, reply: str = ""):
        with _lock_mem:
            self._data["convo_context"][chat_name] = {
                "last_msg"  : msg[:200],
                "last_reply": reply[:200],
                "ts"        : datetime.datetime.now().isoformat(),
            }
            self._dirty = True

    def get_convo(self, chat_name: str) -> dict:
        return self.get("convo_context", {}).get(chat_name, {})

    # ── Response cache ───────────────────────────────────────────────────────

    def cache_response(self, query: str, response: str):
        """Cache response for identical repeated queries (24h TTL)."""
        cache = self.get("response_cache", {})
        cache[query[:100]] = {
            "response": response[:500],
            "ts"      : datetime.datetime.now().isoformat(),
        }
        # Keep cache small — max 50 entries
        if len(cache) > 50:
            oldest = sorted(cache.items(), key=lambda x: x[1]["ts"])
            for k, _ in oldest[:10]:
                del cache[k]
        self.set("response_cache", cache)

    def get_cached(self, query: str) -> str | None:
        """Returns cached response if less than 24h old, else None."""
        cache = self.get("response_cache", {})
        entry = cache.get(query[:100])
        if not entry:
            return None
        try:
            ts  = datetime.datetime.fromisoformat(entry["ts"])
            age = (datetime.datetime.now() - ts).total_seconds()
            if age < 86400:   # 24h
                return entry["response"]
        except Exception:
            pass
        return None

    # ── Mute list ─────────────────────────────────────────────────────────

    def mute(self, contact: str):
        lst = self.get("muted_contacts", [])
        if contact not in lst:
            lst.append(contact)
            self.set("muted_contacts", lst)
            zlog("core", f"Muted: {contact}")

    def unmute(self, contact: str):
        lst = self.get("muted_contacts", [])
        if contact in lst:
            lst.remove(contact)
            self.set("muted_contacts", lst)
            zlog("core", f"Unmuted: {contact}")

    def is_muted(self, contact: str) -> bool:
        return contact in self.get("muted_contacts", [])

    # ── Patterns report ──────────────────────────────────────────────────────

    def get_patterns_report(self) -> str:
        pats = self.get("patterns", {})
        if not pats:
            return "🔍 No patterns learned yet — run some tasks first!"
        lines = ["🔍 ZULU Learned Patterns",
                 f"📅 {datetime.datetime.now().strftime('%d %b %Y %H:%M')}",
                 "─" * 35]
        task_types = pats.get("task_types", {})
        if task_types:
            lines.append("\n📊 Task type breakdown:")
            total = sum(task_types.values())
            for t, n in sorted(task_types.items(), key=lambda x: -x[1]):
                pct = int(n / total * 100)
                bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
                lines.append(f"  {t:<10} {bar} {pct}% ({n}x)")
        peak_hours = pats.get("peak_hours", {})
        if peak_hours:
            busiest = max(peak_hours.items(), key=lambda x: int(x[1]))
            lines.append(f"\n⏰ Busiest hour: {busiest[0]}:00 ({busiest[1]} tasks)")
        lines.append("─" * 35)
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 📡 ZSTATE — Live Runtime State
# In-memory only (not persisted — resets on restart intentionally)
# Any module can read/write via ZSTATE.get() / ZSTATE.set()
# ─────────────────────────────────────────────────────────────────────────────
class _SharedState:
    """Live runtime state — shared across all modules."""

    _DEFAULTS = {
        "is_active"         : True,
        "presence_mode"     : "always",
        "activated_users"   : [],
        "current_task"      : None,      # {"user", "task", "started_at"}
        "task_running"      : False,
        "wa_healthy"        : True,
        "wa_restart_count"  : 0,
        "brains_online"     : 0,
        "last_scan_ts"      : None,
        "last_reply_ts"     : None,
        "gaming_mode"       : False,
        "lockdown"          : False,     # ZULU LOCKDOWN mode
        "boss_chat"         : None,
        "startup_ts"        : datetime.datetime.now().isoformat(),
        "version"           : "v13.2",
    }

    def __init__(self):
        self._data = dict(self._DEFAULTS)

    def get(self, key, default=None):
        with _lock_state:
            return self._data.get(key, default)

    def set(self, key, value):
        with _lock_state:
            self._data[key] = value

    def start_task(self, user: str, task: str):
        with _lock_state:
            self._data["task_running"] = True
            self._data["current_task"] = {
                "user"      : user,
                "task"      : task[:100],
                "started_at": datetime.datetime.now().isoformat(),
            }
        zlog("core", f"Task started: [{user}] {task[:60]}")

    def end_task(self, result_summary: str = ""):
        with _lock_state:
            self._data["task_running"] = False
            if self._data["current_task"]:
                self._data["current_task"]["ended_at"] = datetime.datetime.now().isoformat()
                self._data["current_task"]["result"]   = result_summary[:100]
        zlog("core", f"Task ended: {result_summary[:60]}")

    def get_mind_report(self) -> str:
        """ZULU MIND command — full live state snapshot."""
        with _lock_state:
            d = dict(self._data)
        ts_up  = d.get("startup_ts", "")[:16]
        lines  = [
            "🧠 ZULU MIND — Live State",
            f"📅 {datetime.datetime.now().strftime('%d %b %Y %H:%M')}",
            "─" * 35,
            f"  Version      : {d['version']}",
            f"  Active        : {'✅' if d['is_active'] else '❌'}",
            f"  Presence      : {d['presence_mode']}",
            f"  Gaming mode   : {'🎮 YES' if d['gaming_mode'] else '❌ no'}",
            f"  Lockdown      : {'🔒 YES' if d['lockdown'] else '✅ no'}",
            f"  WA healthy    : {'✅' if d['wa_healthy'] else '⚠️ NO'}",
            f"  WA restarts   : {d['wa_restart_count']}",
            f"  Brains online : {d['brains_online']}",
            f"  Task running  : {'⚙️ YES' if d['task_running'] else '💤 idle'}",
        ]
        ct = d.get("current_task")
        if ct and d["task_running"]:
            lines.append(f"  Current task  : [{ct['user']}] {ct['task'][:50]}")
        lines += [
            f"  Started       : {ts_up}",
            f"  Activated     : {', '.join(d['activated_users']) or 'none'}",
            "─" * 35,
        ]
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 📢 ZBUS — Event Bus
# Publish: ZBUS.emit("task_done", {"user": "BOSS", "task": "..."})
# Subscribe: ZBUS.on("task_done", my_handler_func)
# Any module can listen to any event — fully decoupled
# ─────────────────────────────────────────────────────────────────────────────
class _EventBus:
    """Simple pub/sub event bus — connects all modules without tight coupling."""

    def __init__(self):
        self._handlers: dict[str, list] = {}

    def on(self, event: str, handler):
        """Subscribe to an event. handler(data) will be called on emit."""
        with _lock_bus:
            self._handlers.setdefault(event, []).append(handler)

    def off(self, event: str, handler):
        """Unsubscribe a handler from an event."""
        with _lock_bus:
            handlers = self._handlers.get(event, [])
            if handler in handlers:
                handlers.remove(handler)

    def emit(self, event: str, data: dict = None):
        """Publish an event. All subscribers are called in background threads."""
        data = data or {}
        data["_event"] = event
        data["_ts"]    = datetime.datetime.now().isoformat()
        zlog("bus", f"→ {event} | {str(data)[:80]}")
        with _lock_bus:
            handlers = list(self._handlers.get(event, []))
            # Also call wildcard handlers
            handlers += list(self._handlers.get("*", []))
        for h in handlers:
            try:
                threading.Thread(target=h, args=(data,), daemon=True).start()
            except Exception as e:
                zlog("bus", f"Handler error [{event}]: {e}", "ERROR")

    def emit_sync(self, event: str, data: dict = None):
        """Synchronous emit — waits for all handlers to complete."""
        data = data or {}
        data["_event"] = event
        data["_ts"]    = datetime.datetime.now().isoformat()
        with _lock_bus:
            handlers = list(self._handlers.get(event, []))
            handlers += list(self._handlers.get("*", []))
        for h in handlers:
            try:
                h(data)
            except Exception as e:
                zlog("bus", f"Sync handler error [{event}]: {e}", "ERROR")


# ─────────────────────────────────────────────────────────────────────────────
# 🌐 SINGLETON INSTANCES — import these everywhere
# ─────────────────────────────────────────────────────────────────────────────
ZMEM   = _SharedMemory()   # 🧠 shared persistent memory
ZSTATE = _SharedState()    # 📡 live runtime state
ZBUS   = _EventBus()       # 📢 event bus

# ─────────────────────────────────────────────────────────────────────────────
# 🔗 PRE-WIRED BUS EVENTS (standard event names all modules use)
# ─────────────────────────────────────────────────────────────────────────────
# Tray emits:
#   "scan_complete"   → {"chats": n, "new_messages": n}
#   "task_received"   → {"user": str, "task": str, "user_type": str}
#   "wa_disconnect"   → {"reason": str, "restart_count": n}
#   "wa_reconnected"  → {"restart_count": n}
#   "gaming_start"    → {}
#   "gaming_end"      → {}
#   "zulu_shutdown"   → {}
#
# Boardroom emits:
#   "task_started"    → {"user": str, "task": str, "mode": str, "brain": str}
#   "task_done"       → {"user": str, "task": str, "result": str, "elapsed": str}
#   "task_failed"     → {"user": str, "task": str, "error": str}
#   "brain_used"      → {"brain_id": str, "role": str, "success": bool}
#
# Brain manager emits:
#   "brain_offline"   → {"brain_id": str, "reason": str, "retry_in": str}
#   "brain_restored"  → {"brain_id": str}
#   "quota_hit"       → {"brain_id": str, "used": n, "limit": n}
#
# Dashboard (app.py) emits:
#   "dashboard_cmd"   → {"command": str, "token": str}
#   "dashboard_login" → {"ts": str}
# ─────────────────────────────────────────────────────────────────────────────

# ── Built-in listeners that auto-update shared state ─────────────────────────

def _on_task_received(data):
    ZSTATE.start_task(data.get("user","?"), data.get("task","?"))

def _on_task_done(data):
    ZSTATE.end_task(data.get("result",""))
    ZMEM.remember_task(
        user         = data.get("user","?"),
        task         = data.get("task","?"),
        task_type    = data.get("mode","normal"),
        result_summary = data.get("result",""),
        brain_used   = data.get("brain",""),
    )

def _on_wa_disconnect(data):
    ZSTATE.set("wa_healthy", False)
    ZSTATE.set("wa_restart_count", data.get("restart_count", 0))
    ZMEM.append("wa_events", {
        "ts"    : data.get("_ts",""),
        "reason": data.get("reason","unknown"),
        "action": "disconnect",
    }, max_len=100)

def _on_wa_reconnected(data):
    ZSTATE.set("wa_healthy", True)

def _on_brain_offline(data):
    online = max(0, ZSTATE.get("brains_online", 0) - 1)
    ZSTATE.set("brains_online", online)

def _on_brain_restored(data):
    ZSTATE.set("brains_online", ZSTATE.get("brains_online", 0) + 1)

def _on_gaming_start(_):
    ZSTATE.set("gaming_mode", True)

def _on_gaming_end(_):
    ZSTATE.set("gaming_mode", False)

ZBUS.on("task_received",  _on_task_received)
ZBUS.on("task_done",      _on_task_done)
ZBUS.on("wa_disconnect",  _on_wa_disconnect)
ZBUS.on("wa_reconnected", _on_wa_reconnected)
ZBUS.on("brain_offline",  _on_brain_offline)
ZBUS.on("brain_restored", _on_brain_restored)
ZBUS.on("gaming_start",   _on_gaming_start)
ZBUS.on("gaming_end",     _on_gaming_end)

# ─────────────────────────────────────────────────────────────────────────────
# 🚀 INIT REPORT
# ─────────────────────────────────────────────────────────────────────────────
zlog("core", "=" * 50)
zlog("core", "🧠 ZULU Core Brain v13.2 initialised")
zlog("core", f"   Memory  : {len(ZMEM.get('tasks', []))} tasks loaded")
zlog("core", f"   Log     : {UNIFIED_LOG}")
zlog("core", f"   Core    : {CORE_FILE}")
zlog("core", "=" * 50)

if __name__ == "__main__":
    print(ZSTATE.get_mind_report())
    print()
    print(ZMEM.get_patterns_report())


# ===============================================================================
# ██  🤖 BRAIN MANAGER                                         ██
# ██  (originally: brain_manager.py                                ██
# ===============================================================================

# brain_manager.py — ZULU Brain Manager v13.4  (FREE TIER FINAL)
# Fix 1: Cerebras model → cerebras/llama-3.3-70b-instruct  (was missing -instruct, caused 404)
# Fix 2: SambaNova model → sambanova/Meta-Llama-3.3-70B-Instruct  (added provider prefix)
# Fix 3: GEMINI_PRO kept in registry but disabled (online=False) — requires paid billing
# Fix 4: GEMINI      → gemini/gemini-2.5-flash       (free tier workhorse)
# Fix 5: GEMINI_LITE → gemini/gemini-2.5-flash-lite  (free tier ultra-fast)
# Fix 6: ROLE_BRAIN  → 100% free tier, no Pro dependency
# [merged] from zulu_core import ZMEM, ZSTATE, ZBUS, zlog
import time
import datetime
import json
import os
import requests
# [merged] from agency_config import API_KEYS

# ─────────────────────────────────────────────────────────────────────────────
# 🧠 BRAIN REGISTRY (OLLAMA ONLY - LOCAL LLM)
# ─────────────────────────────────────────────────────────────────────────────
# Ollama runs locally on your machine. No API keys, no rate limits, no costs.
# Download models from: https://ollama.ai
# Start Ollama with: ollama serve
# Pull models: ollama pull llama2, ollama pull mistral, ollama pull neural-chat, etc.
# ─────────────────────────────────────────────────────────────────────────────

BRAINS = {
    "OLLAMA_NEURAL": {
        "label"       : "Ollama Neural-Chat 🏠",
        "model"       : "neural-chat",  # Fast, good for chat
        "api_key"     : "ollama",
        "base_url"    : "http://localhost:11434/v1",
        "online"      : True,
        "offline_until": 0,
        "cooldown_secs": 0,
        "daily_limit" : 999999,
        "used_today"  : 0,
        "reset_date"  : "",
    },
    "OLLAMA_MISTRAL": {
        "label"       : "Ollama Mistral 7B 🏠",
        "model"       : "mistral",  # Great for code & reasoning
        "api_key"     : "ollama",
        "base_url"    : "http://localhost:11434/v1",
        "online"      : True,
        "offline_until": 0,
        "cooldown_secs": 0,
        "daily_limit" : 999999,
        "used_today"  : 0,
        "reset_date"  : "",
    },
    "OLLAMA_LLAMA2": {
        "label"       : "Ollama Llama 2 70B 🏠",
        "model"       : "llama2",  # Powerful, good reasoning
        "api_key"     : "ollama",
        "base_url"    : "http://localhost:11434/v1",
        "online"      : True,
        "offline_until": 0,
        "cooldown_secs": 0,
        "daily_limit" : 999999,
        "used_today"  : 0,
        "reset_date"  : "",
    },
    "OLLAMA_CODELLAMA": {
        "label"       : "Ollama Code Llama 💻",
        "model"       : "codellama",  # Best for coding tasks
        "api_key"     : "ollama",
        "base_url"    : "http://localhost:11434/v1",
        "online"      : True,
        "offline_until": 0,
        "cooldown_secs": 0,
        "daily_limit" : 999999,
        "used_today"  : 0,
        "reset_date"  : "",
    },
}

# Priority order — try these in order
PRIORITY = [
    "OLLAMA_MISTRAL",    # Best all-rounder on local hardware
    "OLLAMA_NEURAL",     # Fast, good for quick responses
    "OLLAMA_CODELLAMA",  # Best for coding tasks
    "OLLAMA_LLAMA2",     # Powerful but slower
]

# Role → preferred brain
ROLE_BRAIN = {
    "scribe"   : "OLLAMA_NEURAL",      # Fast responses
    "worker"   : "OLLAMA_MISTRAL",     # Good all-arounder
    "tech"     : "OLLAMA_CODELLAMA",   # Code tasks
    "visionary": "OLLAMA_MISTRAL",     # Reasoning
    "reviewer" : "OLLAMA_NEURAL",      # Quick reviews
}

# ─────────────────────────────────────────────────────────────────────────────
# 💾 USAGE COUNTER  (persisted to JSON so it survives restarts)
# ─────────────────────────────────────────────────────────────────────────────
USAGE_FILE = r"D:\AI_Agency_Work\System_Logs\brain_usage.json"

def _load_usage():
    try:
        if os.path.exists(USAGE_FILE):
            with open(USAGE_FILE, "r") as f:
                data = json.load(f)
            today = datetime.date.today().isoformat()
            for bid, b in BRAINS.items():
                saved = data.get(bid, {})
                if saved.get("reset_date") == today:
                    b["used_today"]  = saved.get("used_today", 0)
                    b["reset_date"]  = today
                else:
                    b["used_today"]  = 0
                    b["reset_date"]  = today
    except Exception as e:
        print(f" ⚠️ _load_usage error: {e}")

def _save_usage():
    try:
        os.makedirs(os.path.dirname(USAGE_FILE), exist_ok=True)
        data = {bid: {"used_today": b["used_today"], "reset_date": b["reset_date"]}
                for bid, b in BRAINS.items()}
        with open(USAGE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f" ⚠️ _save_usage error: {e}")

def record_usage(brain_id, count=1):
    b     = BRAINS[brain_id]
    today = datetime.date.today().isoformat()
    if b.get("reset_date") != today:
        b["used_today"] = 0
        b["reset_date"] = today
    b["used_today"] += count
    _save_usage()
    online_count = sum(1 for b in BRAINS.values() if b["online"])
    ZSTATE.set("brains_online", online_count)
    if b["used_today"] >= b["daily_limit"]:
        mark_offline(brain_id, reason="daily limit reached")

def get_usage_bar(brain_id):
    b     = BRAINS[brain_id]
    limit = b["daily_limit"]
    used  = b["used_today"]
    if limit >= 999999:
        return f"{used} used (unlimited)"
    pct    = min(used / limit, 1.0)
    filled = int(pct * 10)
    bar    = "█" * filled + "░" * (10 - filled)
    return f"{bar} {used}/{limit}"

# ─────────────────────────────────────────────────────────────────────────────
# 🔴 MARK OFFLINE  (exponential backoff)
# ─────────────────────────────────────────────────────────────────────────────
_fail_counts = {}

def mark_offline(brain_id, reason="quota/error"):
    b     = BRAINS[brain_id]
    b["online"] = False
    _fail_counts[brain_id] = _fail_counts.get(brain_id, 0) + 1
    fails = _fail_counts[brain_id]
    backoff_steps = [60, 120, 300, 600, 1800]
    wait  = backoff_steps[min(fails - 1, len(backoff_steps) - 1)]
    wait  = max(wait, b["cooldown_secs"]) if fails >= len(backoff_steps) else wait
    b["offline_until"] = time.time() + wait
    mins  = wait // 60
    secs  = wait % 60
    time_str = f"{mins}m {secs}s" if mins else f"{secs}s"
    # After: b["offline_until"] = time.time() + wait
    # REPLACE the print() line with:
    zlog("brain", f"🔴 [{b['label']}] OFFLINE — {reason}. Retry in {time_str} (fail #{fails})")
    ZBUS.emit("brain_offline", {"brain_id": brain_id, "reason": reason, "retry_in": time_str})
    return f"⚠️ {b['label']} offline ({reason}). Switched to backup."

# ─────────────────────────────────────────────────────────────────────────────
# 🟢 AUTO RESTORE
# ─────────────────────────────────────────────────────────────────────────────
def auto_restore():
    for bid, b in BRAINS.items():
        if not b["online"] and b["offline_until"] > 0 and time.time() > b["offline_until"]:
            b["online"] = True
            _fail_counts[bid] = 0
            # REPLACE the print() line with:
            zlog("brain", f"🟢 [{b['label']}] RESTORED")
            ZBUS.emit("brain_restored", {"brain_id": bid})

# ─────────────────────────────────────────────────────────────────────────────
# 🧬 SELF-LEARNING ENGINE
# ─────────────────────────────────────────────────────────────────────────────
# Every time ZULU completes a task it logs: which brain was used, task type,
# success/failure, and response quality (auto-scored 0-10 by word count proxy).
# get_best_brain() uses the learned scores to prefer brains that have historically
# performed best for a given role/task type.
# ─────────────────────────────────────────────────────────────────────────────

LEARN_FILE = r"D:\AI_Agency_Work\System_Logs\zulu_learning.json"

_learn_data = {
    # brain_id → { role → { "wins": n, "fails": n, "score_sum": float } }
}

def _load_learn():
    global _learn_data
    try:
        if os.path.exists(LEARN_FILE):
            with open(LEARN_FILE, "r", encoding="utf-8") as f:
                _learn_data = json.load(f)
    except Exception as e:
        print(f" ⚠️ _load_learn error: {e}")
        _learn_data = {}

def _save_learn():
    try:
        os.makedirs(os.path.dirname(LEARN_FILE), exist_ok=True)
        with open(LEARN_FILE, "w", encoding="utf-8") as f:
            json.dump(_learn_data, f, indent=2)
    except Exception as e:
        print(f" ⚠️ _save_learn error: {e}")

def record_outcome(brain_id: str, role: str, success: bool, response_text: str = ""):
    """
    Call this after every brain task completes.
    success = True if no exception and response was non-empty.
    response_text = the actual reply (used to auto-score quality by length).
    """
    if brain_id not in _learn_data:
        _learn_data[brain_id] = {}
    role_key = role or "general"
    if role_key not in _learn_data[brain_id]:
        _learn_data[brain_id][role_key] = {"wins": 0, "fails": 0, "score_sum": 0.0}

    entry = _learn_data[brain_id][role_key]
    if success:
        entry["wins"] += 1
        # Quality score: 0-10 based on response length (proxy for detail)
        words = len(response_text.split()) if response_text else 0
        quality = min(words / 50, 1.0) * 10   # 50+ words = full score
        entry["score_sum"] += quality
    else:
        entry["fails"] += 1

    _save_learn()
    print(f" 🧬 [learn] {brain_id} | role:{role_key} | {'✅ win' if success else '❌ fail'}")

def get_learned_score(brain_id: str, role: str) -> float:
    """
    Returns a learned performance score 0.0 – 10.0 for a brain+role combo.
    Higher = historically better. New brains start at 5.0 (neutral).
    """
    role_key = role or "general"
    entry = _learn_data.get(brain_id, {}).get(role_key)
    if not entry:
        return 5.0  # neutral — no data yet
    total = entry["wins"] + entry["fails"]
    if total == 0:
        return 5.0
    win_rate  = entry["wins"] / total           # 0.0 – 1.0
    avg_score = entry["score_sum"] / max(entry["wins"], 1)  # 0.0 – 10.0
    # Blend: 60% win rate + 40% quality score
    return round((win_rate * 10 * 0.6) + (avg_score * 0.4), 2)

def get_learn_report() -> str:
    """Returns a human-readable self-learning summary for ZULU LEARN command."""
    if not _learn_data:
        return "🧬 ZULU hasn't learned anything yet. Run some tasks first!"
    lines = ["🧬 ZULU Self-Learning Report",
             f"📅 {datetime.datetime.now().strftime('%d %b %Y %H:%M')}",
             "─" * 38]
    for bid in PRIORITY:
        if bid not in _learn_data:
            continue
        b_label = BRAINS[bid]["label"]
        lines.append(f"\n🧠 {b_label}")
        for role_key, entry in _learn_data[bid].items():
            total  = entry["wins"] + entry["fails"]
            if total == 0:
                continue
            score  = get_learned_score(bid, role_key)
            bar    = "★" * int(score) + "☆" * (10 - int(score))
            lines.append(f"  [{role_key}] {bar} {score:.1f}/10 "
                         f"(✅{entry['wins']} ❌{entry['fails']} / {total} tasks)")
    lines.append("─" * 38)
    return "\n".join(lines)

# ─────────────────────────────────────────────────────────────────────────────
# 🎯 GET BEST BRAIN  (role-aware + self-learning score boost)
# ─────────────────────────────────────────────────────────────────────────────
def get_best_brain(exclude_ids=None, role=None):
    """
    role: "scribe" | "worker" | "tech" | "visionary" | "reviewer" | None
    1. Tries role-preferred brain first (from ROLE_BRAIN config)
    2. Then re-ranks remaining online brains by learned score for this role
    3. Falls back to plain PRIORITY if no learning data
    """
    auto_restore()
    exclude_ids = exclude_ids or []

    # Step 1 — try role-preferred brain first
    if role and role in ROLE_BRAIN:
        preferred = ROLE_BRAIN[role]
        if preferred not in exclude_ids and BRAINS[preferred]["online"]:
            return preferred, BRAINS[preferred]

    # Step 2 — rank all online brains by learned score for this role
    candidates = [
        (bid, BRAINS[bid], get_learned_score(bid, role or "general"))
        for bid in PRIORITY
        if bid not in exclude_ids and BRAINS[bid]["online"]
    ]

    if candidates:
        # Sort: highest learned score first
        candidates.sort(key=lambda x: x[2], reverse=True)
        bid, brain, score = candidates[0]
        if score > 5.0:  # only use learned ranking if we have meaningful data
            return bid, brain
        # No meaningful data — fall back to plain PRIORITY order
        return candidates[0][0], candidates[0][1]

    return None, None

# ─────────────────────────────────────────────────────────────────────────────
# 📊 STATUS REPORT  (with fuel gauge)
# ─────────────────────────────────────────────────────────────────────────────
def get_status_report():
    auto_restore()
    lines = ["🛰️ ZULU Brain Status Report",
             f"📅 {datetime.datetime.now().strftime('%d %b %Y %H:%M')}",
             "─" * 35]
    for bid in PRIORITY:
        b   = BRAINS[bid]
        bar = get_usage_bar(bid)
        lrn = get_learned_score(bid, "general")
        if b["online"]:
            lines.append(f" 🟢 {b['label']}  [learn:{lrn:.1f}/10]")
            lines.append(f"    Quota: {bar}")
        else:
            secs_left = max(0, int(b["offline_until"] - time.time()))
            mins      = secs_left // 60
            secs      = secs_left % 60
            time_str  = f"{mins}m {secs}s" if mins else f"{secs}s"
            lines.append(f" 🔴 {b['label']} — back in {time_str}  [learn:{lrn:.1f}/10]")
            lines.append(f"    Quota: {bar}")
    lines.append("─" * 35)
    online_count = sum(1 for b in BRAINS.values() if b["online"])
    lines.append(f" ✅ {online_count}/{len(BRAINS)} brains online")
    return "\n".join(lines)

# ─────────────────────────────────────────────────────────────────────────────
# 🔍 PING FUNCTION (OLLAMA ONLY)
# ─────────────────────────────────────────────────────────────────────────────
def ping_ollama():
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except:
        return False

def get_ollama_status():
    """Get detailed Ollama status - available models, health, etc."""
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            data = r.json()
            models = data.get("models", [])
            if models:
                model_names = [m.get("name", "unknown") for m in models]
                return True, model_names
            return True, []
        return False, []
    except:
        return False, []

def check_all_pings():
    print("🔍 Checking Ollama connection...")
    ollama_ok, models = get_ollama_status()
    if ollama_ok:
        print(f" 🟢 Ollama is running at http://localhost:11434")
        print(f" 📦 Available models: {', '.join(models) if models else 'none (pull some models first)'}")
        for bid in BRAINS:
            BRAINS[bid]["online"] = True
            _fail_counts[bid] = 0
    else:
        print(f" 🔴 Ollama is NOT running!")
        print(f"    ❌ Cannot connect to http://localhost:11434")
        print(f"    💡 Fix: Start Ollama with: ollama serve")
        print(f"    📁 Models directory: D:\\AI_Agency_Work\\ollama_models")
        for bid in BRAINS:
            BRAINS[bid]["online"] = False
    return {"OLLAMA": ollama_ok}

# ─────────────────────────────────────────────────────────────────────────────
# 🔁 SAFE CALL WITH EXPONENTIAL RETRY
# ─────────────────────────────────────────────────────────────────────────────
def safe_brain_call(func, brain_id, max_retries=3, role=None):
    """
    Wraps any brain call with exponential backoff retry.
    On success: records outcome to self-learning engine.
    On quota error: waits 10s → 30s → 60s, then marks offline.
    """
    wait_times   = [10, 30, 60]
    quota_words  = ["quota", "rate limit", "429", "exceeded", "overloaded",
                    "too many requests", "limit reached", "tokens",
                    "resource_exhausted", "rateLimitExceeded"]
    for attempt in range(max_retries):
        try:
            result = func()
            record_usage(brain_id)
            record_outcome(brain_id, role or "general", success=True,
                           response_text=str(result) if result else "")
            # ✅ Fix: reset fail counter on success so backoff resets properly
            _fail_counts[brain_id] = 0
            return result
        except Exception as e:
            err = str(e).lower()
            if any(w in err for w in quota_words):
                wait = wait_times[min(attempt, len(wait_times) - 1)]
                print(f" ⏳ [{BRAINS[brain_id]['label']}] quota hit "
                      f"(attempt {attempt+1}/{max_retries}) — waiting {wait}s...")
                time.sleep(wait)
                if attempt == max_retries - 1:
                    mark_offline(brain_id, reason=str(e)[:60])
                    record_outcome(brain_id, role or "general", success=False)
            else:
                record_outcome(brain_id, role or "general", success=False)
                raise
    return None

# ─────────────────────────────────────────────────────────────────────────────
# 🚀 INIT
# ─────────────────────────────────────────────────────────────────────────────
_load_usage()   # load persisted usage counters on import
_load_learn()   # load self-learning data on import

if __name__ == "__main__":
    check_all_pings()
    print()
    print(get_status_report())
    print()
    print(get_learn_report())


# ===============================================================================
# ██  💼 BOARDROOM ENGINE                                      ██
# ██  (originally: boardroom_engine.py                             ██
# ===============================================================================

# boardroom_engine.py — ZULU BOARDROOM v13.0 FINAL
# 💰 Crypto | 🔁 Pipelines | 🌍 30-Lang | 📦 Reports | 🧠 Self-Learning | 📁 Organiser

# [merged] from zulu_core import ZMEM, ZSTATE, ZBUS, zlog
import os, re, time, json, subprocess, datetime, smtplib, ctypes, requests
from collections import Counter
import win32gui, win32con, win32clipboard
import pyautogui
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pywinauto import Desktop
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import BaseTool
# [merged] from agency_config import PROJECTS_DIR
# [merged] from brain_manager import BRAINS, ROLE_BRAIN, get_best_brain, mark_offline
# [merged]                        get_status_report, auto_restore, record_usage, safe_brain_call, get_usage_bar

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

class BrowserAgentTool(BaseTool):
    name: str = "browser_agent"
    description: str = "Browser Bot: Open browser, navigate, click, and scrape text. Format: 'url|||click_text|||headless(true/false)'. Example: 'https://example.com|||Search|||true'. Leave click_text empty if not needed: 'https://site.com||||||true'. BOSS only."
    def _run(self, input_str: str) -> str:
        user = get_current_user()
        audit(user, "browser_agent", input_str[:80], has_permission(user, "search"))
        if not has_permission(user, "search"):
            return permission_denied_msg("use browser", user)
        try:
            parts = input_str.split("|||")
            url = parts[0].strip() if len(parts) > 0 else ""
            click_text = parts[1].strip() if len(parts) > 1 else ""
            headless = parts[2].strip() if len(parts) > 2 else "true"
            
            # Run in a separate subprocess so Playwright's async/sync loop doesn't crash the main Tray/Flask event loop.
            import subprocess, json
            browser_script = os.path.join(BASE_DIR, "zulu_browser.py")
            result = subprocess.run(
                ["python", browser_script, url, click_text, headless],
                capture_output=True, text=True, timeout=90
            )
            
            try:
                data = json.loads(result.stdout)
                if data.get("status") == "success":
                    return f"Scraped Data:\n{data.get('data', '')}"
                else:
                    return f"Browser Error: {data.get('message', '')}"
            except json.JSONDecodeError:
                return f"Browser output parsing failed. Output: {result.stdout[:500]} Err: {result.stderr[:500]}"
                
        except subprocess.TimeoutExpired:
            return "Browser request timed out after 90 seconds."
        except Exception as e:
            return f"Browser execution error: {e}"

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
browser_tool    = BrowserAgentTool()

BOSS_ALL_TOOLS   = [write_tool, read_tool, list_tool, run_tool, open_tool,
                    search_tool, email_tool, reminder_tool, memory_tool, screenshot_tool, browser_tool]
BOSS_READ_TOOLS  = [read_tool, list_tool, search_tool, memory_tool, browser_tool]
BOSS_QUICK_TOOLS = [search_tool, memory_tool, reminder_tool, email_tool, screenshot_tool, browser_tool]
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
    """Build LLM object for CrewAI — handles Ollama OpenAI-compatible API."""
    b = BRAINS[brain_id]
    
    # Ollama uses OpenAI-compatible API
    # Model names must match: ollama pull neural-chat, ollama pull mistral, etc.
    kwargs = dict(
        model=b["model"],              # e.g. "neural-chat", "mistral", "llama2"
        base_url=b["base_url"],        # http://localhost:11434/v1
        api_key="ollama",              # Ollama doesn't require a real API key
    )
    
    zlog("brain", f"Building LLM for [{b['label']}] model={b['model']}")
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


# ===============================================================================
# ██  🖥️  ZULU PC                                             ██
# ██  (originally: zulu_pc.py                                      ██
# ===============================================================================

# zulu_pc.py — ZULU PC Control Module v1.0
import os, re, json, time, shutil, ctypes, datetime, subprocess, webbrowser, threading
# [merged] from zulu_core import zlog, ZMEM, ZSTATE, ZBUS

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


# ===============================================================================
# ██  🎙️  ZULU VOICE                                          ██
# ██  (originally: zulu_voice.py                                   ██
# ===============================================================================

# zulu_voice.py — ZULU Voice Engine v3.0  (Nepali-accent optimised)
# ─────────────────────────────────────────────────────────────────────────────
#  KEY CHANGES vs v2.0
#  1. Google STT now uses language="en-IN"  (South-Asian / Nepali accent model)
#  2. show_all=True  → reads ALL Google alternatives, not just top-1
#  3. 3× more wake-word variants covering Nepali phonetics (j/z swap, vowel shifts)
#  4. difflib fuzzy matcher — catches near-misses like "hey julu", "hey zolo"
#  5. Energy threshold lowered to 200, pause_threshold to 0.6
#  6. Ambient noise calibration extended to 1.0 s on startup
#  7. Command listen loop retries twice before giving up
#  8. All other modules (core/PC/boardroom) unchanged — drop-in replacement
# ─────────────────────────────────────────────────────────────────────────────
import re
import time
import threading
import difflib
# [merged] from zulu_core import zlog, ZMEM, ZSTATE, ZBUS

# ─────────────────────────────────────────────────────────────────────────────
# 🔧 OPTIONAL DEPENDENCY GUARDS
# ─────────────────────────────────────────────────────────────────────────────
try:
    import speech_recognition as sr
    SR_OK = True
except ImportError:
    SR_OK = False

try:
    import pyttsx3
    PYTTSX3_OK = True
except ImportError:
    PYTTSX3_OK = False


# ─────────────────────────────────────────────────────────────────────────────
# ⚙️  CONFIG
# ─────────────────────────────────────────────────────────────────────────────

# ── Google STT language ──────────────────────────────────────────────────────
# "en-IN" = English (India) — closest available model to Nepali accent.
# Google does not have "en-NP" yet.  en-IN handles the z→j shift,
# retroflex consonants, and vowel colouring far better than plain "en-US".
STT_LANGUAGE = "en-IN"

# ── Wake-word list (Nepali-accent expanded) ──────────────────────────────────
# Nepali accent patterns accounted for:
#   z → j/zh/s  ("zulu" → "julu", "sulu", "zhulu")
#   oo → u/ew   ("zulu" → "zoloo", "zewloo")
#   h drop      ("hey" → "ay", "ey")
#   "hey" → "a" or silent
WAKE_WORDS = [
    # Standard
    "zulu", "hey zulu", "a zulu", "ok zulu",
    # j/zh shift (very common Nepali pattern)
    "julu",  "hey julu",  "a julu",
    "jhulu", "hey jhulu",
    "julio", "hey julio",
    # s-shift
    "sulu",  "hey sulu",  "a sulu",
    # vowel variants
    "zoloo", "zolo",  "hey zolo",
    "juloo", "jooloo","hey jooloo",
    "zewlu", "hey zewlu",
    # "julia" / "julia" misread
    "julia", "hey julia", "hey juliet",
    # "zoo" variants
    "hey zoo", "hey zool", "hey zulu please",
    # "sula", "sulla"
    "sula", "hey sula", "sulla", "hey sulla",
    # h-dropped "ey" forms
    "ey zulu", "ey julu", "ey sulu",
    # common misreads of South-Asian accent
    "xulu", "hey xulu",
]

FUZZY_WAKE_THRESHOLD = 0.72   # 0–1; lower = more permissive
FUZZY_CANDIDATES     = ["zulu", "julu", "sulu", "hey zulu", "hey julu"]

OWNER_ONLY       = True
COMMAND_TIMEOUT  = 12         # seconds to wait for command after wake word
COMMAND_RETRIES  = 2          # retry listen this many times before giving up
ENERGY_THRESHOLD = 200        # lower = picks up quieter/softer speech
NOISE_CALIBRATE_S = 1.0       # calibrate ambient noise for this long on startup
TTS_ENABLED      = True
TTS_RATE         = 165
TTS_MAX_CHARS    = 400


# ─────────────────────────────────────────────────────────────────────────────
# 🔊 TEXT-TO-SPEECH
# ─────────────────────────────────────────────────────────────────────────────
_tts_engine = None
_tts_lock   = threading.Lock()


def _init_tts():
    global _tts_engine
    if not PYTTSX3_OK:
        zlog("voice", "pyttsx3 not installed — TTS disabled (pip install pyttsx3)", "WARN")
        return
    try:
        _tts_engine = pyttsx3.init()
        _tts_engine.setProperty("rate",   TTS_RATE)
        _tts_engine.setProperty("volume", 0.95)
        voices = _tts_engine.getProperty("voices") or []
        for v in voices:
            name_lower = (v.name or "").lower()
            if "zira" in name_lower or "david" in name_lower:
                _tts_engine.setProperty("voice", v.id)
                break
        zlog("voice", f"TTS engine ready ({len(voices)} voice(s) available)")
    except Exception as e:
        zlog("voice", f"TTS init error: {e}", "WARN")
        _tts_engine = None


def _clean_for_speech(text: str) -> str:
    clean = re.sub(r'[^\x00-\x7F]+', '', text)
    clean = re.sub(r'[*_`#\[\]\(\)~]', '', clean)
    clean = re.sub(r'https?://\S+', 'link', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    if len(clean) > TTS_MAX_CHARS:
        clean = clean[:TTS_MAX_CHARS] + "."
    return clean


def speak(text: str, blocking: bool = False):
    """Speak text aloud. blocking=True → wait until done."""
    if not TTS_ENABLED:
        zlog("voice", f"[TTS] {text[:80]}")
        return

    clean = _clean_for_speech(text)
    if not clean:
        return

    def _do():
        with _tts_lock:
            if _tts_engine:
                try:
                    _tts_engine.say(clean)
                    _tts_engine.runAndWait()
                    return
                except Exception as e:
                    zlog("voice", f"pyttsx3 speak error: {e}", "WARN")
            # Fallback: PowerShell SAPI
            try:
                import subprocess
                safe = clean.replace('"', "'")
                ps = (
                    f'Add-Type -AssemblyName System.Speech; '
                    f'$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
                    f'$s.Rate = 1; '
                    f'$s.Speak("{safe}");'
                )
                subprocess.run(["powershell", "-c", ps],
                               timeout=30, capture_output=True)
            except Exception as e2:
                zlog("voice", f"SAPI fallback error: {e2}", "WARN")

    if blocking:
        _do()
    else:
        threading.Thread(target=_do, daemon=True, name="ZuluTTS").start()


# ─────────────────────────────────────────────────────────────────────────────
# 🎙️ SPEECH RECOGNITION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _recognize_all_alternatives(recognizer, audio) -> list[str]:
    """
    Returns ALL Google transcription alternatives (not just top-1).
    This is critical for accented speech — the correct word often sits
    at alternative #2 or #3 rather than the top result.
    Falls back to top-1 if show_all is unsupported.
    """
    results = []
    try:
        raw = recognizer.recognize_google(
            audio,
            language  = STT_LANGUAGE,
            show_all  = True,            # ← get every hypothesis
        )
        if raw and isinstance(raw, dict):
            for alt in raw.get("alternative", []):
                t = alt.get("transcript", "").strip()
                if t:
                    results.append(t.lower())
        elif raw and isinstance(raw, str):
            results.append(raw.lower().strip())
    except sr.UnknownValueError:
        pass
    except sr.RequestError as e:
        zlog("voice", f"STT network error: {e}", "WARN")
    except Exception as e:
        zlog("voice", f"STT error: {e}", "WARN")
    return results


def _fuzzy_is_wake(text: str) -> bool:
    """
    Fuzzy match: catches e.g. "hey julo" matching "hey julu".
    Uses difflib sequence ratio — quick and dependency-free.
    """
    tl = text.lower().strip()
    for candidate in FUZZY_CANDIDATES:
        ratio = difflib.SequenceMatcher(None, tl, candidate).ratio()
        if ratio >= FUZZY_WAKE_THRESHOLD:
            zlog("voice", f"Fuzzy wake match: '{tl}' ≈ '{candidate}' ({ratio:.2f})")
            return True
    return False


def _is_wake_word(text: str) -> bool:
    """
    Exact match against expanded wake-word list, then fuzzy fallback.
    """
    tl = text.lower().strip()
    # Exact / substring match
    if any(w in tl for w in WAKE_WORDS):
        return True
    # Fuzzy match
    return _fuzzy_is_wake(tl)


def _is_wake_in_any(alternatives: list[str]) -> tuple[bool, str]:
    """
    Check ALL recognition alternatives for a wake word.
    Returns (found, matched_text).
    """
    for alt in alternatives:
        if _is_wake_word(alt):
            return True, alt
    return False, ""


def _strip_wake_word(text: str) -> str:
    tl = text.lower().strip()
    for w in sorted(WAKE_WORDS, key=len, reverse=True):   # longest first
        if tl.startswith(w):
            offset = text.lower().find(w) + len(w)
            return text[offset:].strip(" ,.")
    return text


def _listen_once(recognizer, mic, timeout: int = COMMAND_TIMEOUT) -> str:
    """
    Listen once, return best transcript.
    Uses en-IN language model and reads all alternatives.
    """
    try:
        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio = recognizer.listen(
                source,
                timeout         = timeout,
                phrase_time_limit = 15,
            )
        alts = _recognize_all_alternatives(recognizer, audio)
        if alts:
            zlog("voice", f"STT alternatives: {alts[:4]}")
            return alts[0]   # top result (already best with en-IN)
        return ""
    except sr.WaitTimeoutError:
        zlog("voice", "STT: no speech (timeout)")
        return ""
    except Exception as e:
        zlog("voice", f"STT listen error: {e}", "WARN")
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# 🔒 OWNER LOCK
# ─────────────────────────────────────────────────────────────────────────────

def _owner_present() -> bool:
    if not OWNER_ONLY:
        return True
    return ZSTATE.get("voice_owner_present", True)


# ─────────────────────────────────────────────────────────────────────────────
# ⚡ COMMAND EXECUTION
# ─────────────────────────────────────────────────────────────────────────────

def _execute(command: str):
    """
    Routes voice command → PC control (instant) or boardroom (AI).
    Runs in background thread — never blocks the listen loop.
    """
    user_type = "BOSS"
    zlog("voice", f"Executing: '{command}'")

    # ── 1. PC control first (instant) ────────────────────────────────────────
    try:
        # [merged — handle_pc_command available directly]
        handled, response = handle_pc_command(command, user_type)
        if handled:
            zlog("voice", f"PC handled: {response[:60]}")
            speak(response, blocking=True)
            return
    except ImportError:
        zlog("voice", "zulu_pc not found — skipping PC commands", "WARN")
    except Exception as e:
        zlog("voice", f"PC command error: {e}", "WARN")

    # ── 2. AI path via boardroom ──────────────────────────────────────────────
    speak("On it.", blocking=True)

    try:
        # [merged — launch_boardroom available directly]

        _capture = []

        def _grab(data):
            r = data.get("result", "")
            if r and str(r).strip().lower() not in ("none", ""):
                _capture.append(str(r))
            ZBUS.off("task_done", _grab)

        ZBUS.on("task_done", _grab)
        launch_boardroom(command, user_type)
        time.sleep(0.5)

        if _capture:
            speak(_capture[-1], blocking=True)
        else:
            speak("Done.")

    except ImportError:
        zlog("voice", "boardroom_engine not found", "WARN")
        speak("Boardroom not available.")
    except Exception as e:
        zlog("voice", f"Boardroom error: {e}", "ERROR")
        speak("Something went wrong.")


# ─────────────────────────────────────────────────────────────────────────────
# 🔄 MAIN VOICE LOOP
# ─────────────────────────────────────────────────────────────────────────────
_voice_active = False
_is_listening = False
_stop_event   = threading.Event()


def _voice_loop():
    global _voice_active, _is_listening

    if not SR_OK:
        zlog("voice",
             "speech_recognition not installed.\n"
             "Run: pip install SpeechRecognition pyaudio\n"
             "If pyaudio fails on Windows: pip install pipwin && pipwin install pyaudio",
             "ERROR")
        return

    recognizer = sr.Recognizer()
    recognizer.energy_threshold         = ENERGY_THRESHOLD   # 200 (was 300)
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold          = 0.6                # 0.6 (was 0.8) — quicker end-of-speech

    try:
        mic = sr.Microphone()
    except OSError as e:
        zlog("voice", f"Microphone not available: {e}", "ERROR")
        return
    except Exception as e:
        zlog("voice", f"Mic init error: {e}", "ERROR")
        return

    # ── Extended startup calibration (1 s) ───────────────────────────────────
    zlog("voice", f"Calibrating ambient noise for {NOISE_CALIBRATE_S}s …")
    try:
        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=NOISE_CALIBRATE_S)
        zlog("voice", f"Energy threshold after calibration: {recognizer.energy_threshold:.0f}")
    except Exception as e:
        zlog("voice", f"Calibration error: {e}", "WARN")

    _voice_active = True
    ZSTATE.set("voice_owner_present", True)
    zlog("voice", f"🎙️  Voice engine started (lang={STT_LANGUAGE}) — say 'Hey ZULU'")
    speak("ZULU voice engine ready. Say Hey Zulu.", blocking=True)

    while not _stop_event.is_set():
        _is_listening = False
        try:
            # ── Phase 1: Passive listen for wake word ─────────────────────────
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.2)
                try:
                    audio = recognizer.listen(
                        source,
                        timeout           = 4,
                        phrase_time_limit = 5,
                    )
                except sr.WaitTimeoutError:
                    continue

            # Get ALL alternatives (critical for accent)
            alternatives = _recognize_all_alternatives(recognizer, audio)
            if not alternatives:
                continue

            zlog("voice", f"Heard (passive): {alternatives[:3]}")

            # Check wake word in any alternative
            woke, matched_text = _is_wake_in_any(alternatives)
            if not woke:
                continue

            # ── Phase 2: Wake word detected ───────────────────────────────────
            zlog("voice", f"Wake word detected via: '{matched_text}'")

            if not _owner_present():
                zlog("voice", "Owner lock active — wake word ignored")
                continue

            _is_listening = True
            ZBUS.emit("voice_wake", {"text": matched_text})

            # Check if command was already in the same utterance
            command = _strip_wake_word(matched_text)

            if not command or len(command) < 3:
                # Ask for command — then retry COMMAND_RETRIES times if unclear
                speak("Yes?", blocking=True)
                time.sleep(0.15)

                command = ""
                for attempt in range(COMMAND_RETRIES):
                    command = _listen_once(recognizer, mic, timeout=COMMAND_TIMEOUT)
                    if command and len(command) >= 3:
                        break
                    if attempt < COMMAND_RETRIES - 1:
                        speak("Sorry, say that again.", blocking=True)
                        time.sleep(0.1)

            if not command or len(command) < 3:
                speak("I didn't catch that. Say Hey Zulu again.", blocking=True)
                _is_listening = False
                continue

            # ── Phase 3: Execute ──────────────────────────────────────────────
            zlog("voice", f"Voice command: '{command}'")
            threading.Thread(
                target=_execute,
                args=(command,),
                daemon=True,
                name="ZuluVoiceExec",
            ).start()

            time.sleep(1.5)   # cooldown — prevents re-triggering on TTS audio

        except Exception as e:
            if not _stop_event.is_set():
                zlog("voice", f"Voice loop error: {e}", "WARN")
            time.sleep(1)
        finally:
            _is_listening = False

    _voice_active = False
    zlog("voice", "Voice engine stopped.")


# ─────────────────────────────────────────────────────────────────────────────
# 🚀 PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────
_voice_thread: threading.Thread | None = None


def start_voice_engine() -> bool:
    global _voice_thread

    if not SR_OK:
        print("❌ speech_recognition not installed.")
        print("   Run: pip install SpeechRecognition pyaudio")
        print("   If pyaudio fails on Windows: pip install pipwin && pipwin install pyaudio")
        return False

    if _voice_thread is not None and _voice_thread.is_alive():
        zlog("voice", "Voice engine already running — skipping duplicate start")
        return True

    _init_tts()
    _stop_event.clear()

    _voice_thread = threading.Thread(
        target=_voice_loop,
        daemon=True,
        name="ZuluVoiceLoop",
    )
    _voice_thread.start()
    zlog("voice", "Voice engine thread launched")
    return True


def stop_voice_engine():
    _stop_event.set()
    zlog("voice", "Stop signal sent to voice engine")


def lock_voice():
    """ZULU VOICE LOCK — strangers can't trigger voice."""
    ZSTATE.set("voice_owner_present", False)
    zlog("voice", "Voice LOCKED")


def unlock_voice():
    """ZULU VOICE UNLOCK — voice responds again."""
    ZSTATE.set("voice_owner_present", True)
    zlog("voice", "Voice UNLOCKED")


def voice_status() -> str:
    if not SR_OK:
        return "❌ Voice: speech_recognition not installed"
    running = _voice_thread is not None and _voice_thread.is_alive()
    state   = "🔴 ACTIVE" if _is_listening else "⚪ standby"
    locked  = "  🔒 LOCKED" if not _owner_present() else ""
    lang    = f"  🌐 {STT_LANGUAGE}"
    return f"🎙️  Voice: {'RUNNING' if running else 'STOPPED'} | {state}{lang}{locked}"


# ─────────────────────────────────────────────────────────────────────────────
# 🧪 STANDALONE TEST
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 58)
    print("🎙️  ZULU Voice Engine v3.0 — Nepali-Accent Edition")
    print("=" * 58)
    print()
    print(f"  speech_recognition : {'✅' if SR_OK else '❌  pip install SpeechRecognition pyaudio'}")
    print(f"  pyttsx3            : {'✅' if PYTTSX3_OK else '❌  pip install pyttsx3'}")
    print(f"  STT language       : {STT_LANGUAGE}  (en-IN = South Asian accent model)")
    print(f"  Wake words         : {len(WAKE_WORDS)} variants loaded")
    print(f"  Fuzzy threshold    : {FUZZY_WAKE_THRESHOLD}")
    print()

    if not SR_OK:
        print("Install missing deps and re-run.")
        raise SystemExit(1)

    if start_voice_engine():
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            stop_voice_engine()
            print("\n👋 Voice engine stopped.")


# ===============================================================================
# ██  🔍 FIND MSGBOX                                           ██
# ██  (originally: find_msgbox.py                                  ██
# ===============================================================================

# Save as: find_exact_msgbox.py
# Run: python find_exact_msgbox.py

import time
import win32gui
import win32con
from pywinauto import Desktop

print("Opening WhatsApp and scanning in 3 seconds...")
print("Make sure a chat is OPEN in WhatsApp before running this!")
time.sleep(3)

hwnd = win32gui.FindWindow(None, "WhatsApp")
if not hwnd:
    print("❌ WhatsApp not found!")
    exit()

win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 100, 100, 1100, 750, win32con.SWP_SHOWWINDOW)
time.sleep(1)

rect = win32gui.GetWindowRect(hwnd)
print(f"Window rect: {rect}")
print(f"Window size: {rect[2]-rect[0]} x {rect[3]-rect[1]}")
print()

app = Desktop(backend="uia").window(handle=hwnd)
print("Scanning ALL controls...")
print()

for ctrl_type in ["Edit", "Document", "Text", "Custom"]:
    try:
        items = app.descendants(control_type=ctrl_type)
        for e in items:
            try:
                r = e.rectangle()
                w = r.right - r.left
                h = r.bottom - r.top
                cx = r.left + w // 2
                cy = r.top + h // 2
                print(f"  [{ctrl_type}] w={w} h={h} cx={cx} cy={cy} | visible={e.is_visible()} enabled={e.is_enabled()}")
            except:
                pass
    except:
        pass


# ===============================================================================
# ██  🔬 WA INSPECTOR                                          ██
# ██  (originally: wa_inspector.py                                 ██
# ===============================================================================

import win32gui
import win32con
from pywinauto import Desktop
import time

pyautogui_available = False
try:
    import pyautogui
    pyautogui_available = True
except ImportError:
    pass


def inspect_window(hwnd):
    rect             = win32gui.GetWindowRect(hwnd)
    left, top, right, bottom = rect
    print(f"\n📐 Window rect  : left={left} top={top} right={right} bottom={bottom}")
    print(f"   Size          : {right-left} x {bottom-top}\n")

    win32gui.ShowWindow(hwnd, 9)
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 100, 100, 1100, 750, win32con.SWP_SHOWWINDOW)
    time.sleep(1)

    app = Desktop(backend="uia").window(handle=hwnd)

    # ── DataItem chat rows ────────────────────────────────────────────────────
    items = app.descendants(control_type="DataItem")
    print(f"✅ Found {len(items)} DataItems (chat rows)")
    print("=" * 60)
    print("🔍 FIRST 15 DataItems:")
    print("=" * 60)

    for i, item in enumerate(items[:15]):
        try:
            title = item.window_text().strip()
            print(f"\n  ── DataItem [{i}] ──────────────────────────")
            print(f"     Title  : '{title[:80]}'")

            # Child Text elements
            children = item.descendants(control_type="Text")
            texts    = [c.window_text().strip() for c in children if c.window_text().strip()]
            print(f"     Texts  : {texts[:6]}")

            # Child Buttons
            btns     = item.descendants(control_type="Button")
            btn_txts = [b.window_text().strip() for b in btns if b.window_text().strip()]
            if btn_txts:
                print(f"     Buttons: {btn_txts[:4]}")

            # Rectangle
            try:
                r = item.rectangle()
                print(f"     Rect   : left={r.left} top={r.top} w={r.right-r.left} h={r.bottom-r.top}")
            except Exception:
                pass

        except Exception as e:
            print(f"  ⚠️ Error on DataItem [{i}]: {e}")

    # ── Edit controls (message boxes) ────────────────────────────────────────
    print("\n" + "=" * 60)
    print("🔍 ALL EDIT CONTROLS (potential message boxes):")
    print("=" * 60)
    try:
        edits = app.descendants(control_type="Edit")
        print(f"   Found {len(edits)} Edit controls\n")
        for i, e in enumerate(edits):
            try:
                r   = e.rectangle()
                w   = r.right  - r.left
                h   = r.bottom - r.top
                cx  = r.left   + w // 2
                cy  = r.top    + h // 2
                vis = e.is_visible()
                ena = e.is_enabled()
                txt = e.window_text()[:50]
                flag = " ← 🎯 LIKELY MSGBOX" if (vis and ena and w > 200 and h < 60 and cx > 600) else ""
                print(f"   Edit[{i}]: size={w}x{h} center=({cx},{cy}) "
                      f"vis={vis} ena={ena} text='{txt}'{flag}")
            except Exception as ex:
                print(f"   Edit[{i}]: error — {ex}")
    except Exception as ex:
        print(f"   ⚠️ Edit scan failed: {ex}")

    # ── Document controls ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("🔍 ALL DOCUMENT CONTROLS:")
    print("=" * 60)
    try:
        docs = app.descendants(control_type="Document")
        print(f"   Found {len(docs)} Document controls\n")
        for i, d in enumerate(docs):
            try:
                r   = d.rectangle()
                w   = r.right  - r.left
                h   = r.bottom - r.top
                cx  = r.left   + w // 2
                cy  = r.top    + h // 2
                vis = d.is_visible()
                ena = d.is_enabled()
                flag = " ← 🎯 LIKELY MSGBOX" if (vis and ena and w > 200 and h < 60 and cx > 600) else ""
                print(f"   Doc[{i}]: size={w}x{h} center=({cx},{cy}) "
                      f"vis={vis} ena={ena}{flag}")
            except Exception as ex:
                print(f"   Doc[{i}]: error — {ex}")
    except Exception as ex:
        print(f"   ⚠️ Document scan failed: {ex}")

    # ── Control type summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📊 CONTROL TYPE COUNTS (top-level descendants):")
    print("=" * 60)
    from collections import Counter
    try:
        all_ctrl = app.descendants()
        counts   = Counter(c.element_info.control_type for c in all_ctrl)
        for ctype, cnt in counts.most_common(15):
            print(f"   {ctype:<25} : {cnt}")
    except Exception as ex:
        print(f"   ⚠️ Count failed: {ex}")


if __name__ == "__main__":
    print("=" * 60)
    print("🛡️  ZULU WhatsApp UI Inspector v2")
    print("   Keep WhatsApp open with chat list visible!")
    print("=" * 60)

    hwnd = win32gui.FindWindow(None, "WhatsApp")
    if not hwnd:
        print("❌ WhatsApp not found! Open it first.")
        exit()

    inspect_window(hwnd)

    print("\n✅ Inspection complete!")
    print("📋 Paste this output to Perplexity to diagnose any issues.")
    print("=" * 60)


# ===============================================================================
# ██  🚀 ZULU TRAY (MAIN)                                      ██
# ██  (originally: zulu_tray.py                                    ██
# ===============================================================================

# zulu_tray.py — ZULU SENTINEL v13.6  (10 instant commands added)
# [merged] from zulu_core import ZMEM, ZSTATE, ZBUS, zlog
import time, os, re, uuid, json, datetime, threading, subprocess, ctypes
import win32gui, win32con, win32clipboard, win32api
import win32process
import pyautogui
from pywinauto import Desktop
# [merged] from zulu_voice import start_voice_engine
if start_voice_engine():
    print("✅ Voice engine started")

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

# [merged] from boardroom_engine import launch_boardroom, set_boss_chat, build_llm
# [merged] from brain_manager import get_status_report as _get_status_report_raw, check_all_pings, auto_restore, mark_offline, get_learn_report

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
# [merged] from agency_config import TRIGGER_WORD, OFF_CMD

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
# � HANDLE UNKNOWN USER  (PASSIVE ONLY - no auto-responses)
# Only logs messages, responds only to BOSS/GF
# Unknown users must first be approved by BOSS before ZULU responds
# ─────────────────────────────────────────────────────────────────────────────
def handle_unknown_user(hwnd, chat_name, message):
    """
    PASSIVE MODE: Do NOT respond to unknown users automatically.
    Only log their messages for BOSS review.
    
    When BOSS sends ZULU APPROVE [contact], then unknown user can send commands.
    """
    # ── Mute + lockdown guard ─────────────────────────────────────────────
    if ZMEM.is_muted(chat_name):
        print(f" 🔇 [{chat_name}] is muted — no response sent.")
        return
    
    if ZSTATE.get("lockdown"):
        print(f" 🔒 Lockdown active — [{chat_name}] ignored.")
        return

    session    = get_session(chat_name)
    session_id = session["id"]
    msg_lower  = message.lower().strip()
    
    touch_session(chat_name)

    # ── Master code check (secret activation) ──────────────────────────────
    if MASTER_CODE.lower() in msg_lower:
        elevate_to_boss(chat_name)
        send_reply(hwnd, "🔓 Access granted!")
        save_unknown_request(chat_name, f"[MASTER CODE] {message}", session_id, answered=True)
        zlog("tray", f"Unknown user [{chat_name}] used master code")
        return

    # ── ONLY LOG — don't respond ───────────────────────────────────────────
    print(f" 📝 [{chat_name}] {message[:60]}")
    save_unknown_request(chat_name, message, session_id, answered=False)
    zlog("tray", f"Unknown user logged: {chat_name} → {message[:60]}")

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
        # [merged — handle_pc_command available directly]
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
# [merged]         from boardroom_engine import get_crypto_price
        sym = upper.replace("ZULU CRYPTO", "").strip() or "BTC"
        send_reply(hwnd, get_crypto_price(sym))
        return

    if upper.startswith("ZULU ALERT"):
# [merged]         from boardroom_engine import add_price_alert
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
# [merged]         from boardroom_engine import get_project_status_report
        period = msg.strip()[len("ZULU REPORT"):].strip().lower() or "week"
        send_reply(hwnd, get_project_status_report(period))
        return

    if "ZULU MISTAKES" in upper:
# [merged]         from boardroom_engine import get_mistake_patterns
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
# [merged]         from boardroom_engine import organise_projects_folder
        dry = "DRY" in upper
        send_reply(hwnd, organise_projects_folder(dry_run=dry))
        return

    if upper.startswith("ZULU PIPELINE "):
# [merged]         from boardroom_engine import add_pipeline
        rest  = msg.strip()[len("ZULU PIPELINE"):].strip()
        parts = rest.split("|")
        if len(parts) >= 3:
            steps = [s.strip() for s in parts[2].split(";") if s.strip()]
            send_reply(hwnd, add_pipeline(parts[0].strip(), parts[1].strip(), steps))
        else:
            send_reply(hwnd, "Format: ZULU PIPELINE name|daily 08:00|step1;step2")
        return

    if "ZULU PIPELINES" in upper:
# [merged]         from boardroom_engine import check_pipelines
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
# [merged] from zulu_pc import handle_pc_command
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
# [merged]         from zulu_pc import google_search
        send_reply(hwnd, google_search(q))
        return

    if upper.startswith("ZULU YOUTUBE "):
        q = msg.strip()[len("ZULU YOUTUBE "):].strip()
# [merged]         from zulu_pc import youtube_search
        send_reply(hwnd, youtube_search(q))
        return

    # ── 🎙️  ZULU VOICE STATUS ────────────────────────────────────────────────
    if "ZULU VOICE STATUS" in upper or "ZULU VOICE" == upper.strip():
        try:
# [merged]             from zulu_voice import voice_status
            send_reply(hwnd, voice_status())
        except ImportError:
            send_reply(hwnd, "❌ zulu_voice.py not installed.")
        return

    if "ZULU VOICE ON" in upper:
        try:
# [merged]             from zulu_voice import start_voice_engine
            ok = start_voice_engine()
            send_reply(hwnd, "🎙️ Voice engine started!" if ok else "❌ Voice engine failed — check dependencies.")
        except ImportError:
            send_reply(hwnd, "❌ zulu_voice.py not found.")
        return

    if "ZULU VOICE OFF" in upper:
        try:
# [merged]             from zulu_voice import stop_voice_engine
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
# [merged]         from boardroom_engine import get_reminder_count
        reminders = get_reminder_count()

        # Memories due today (anything remembered with 'today' keyword)
# [merged]         from zulu_pc import recall_memories
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
# [merged]         from zulu_voice import start_voice_engine
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