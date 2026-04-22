# zulu_core.py — ZULU Central Nervous System v13.2
import datetime
import json
import os
import threading
import time
from zulu_core import zlog, ZMEM, ZSTATE, ZBUS
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
