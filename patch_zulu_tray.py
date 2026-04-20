
# ═══════════════════════════════════════════════════════════════════
# ZULU TRAY — CORE BRAIN PATCH
# Paste relevant sections into zulu_tray.py as directed
# ═══════════════════════════════════════════════════════════════════

# ── STEP 1 : ADD AT TOP (after existing imports) ─────────────────
from zulu_core import ZMEM, ZSTATE, ZBUS, zlog

# ── STEP 2 : REPLACE GLOBALS ─────────────────────────────────────
# OLD: is_active = True          → ZSTATE.set("is_active", True)
# OLD: is_active = False         → ZSTATE.set("is_active", False)
# OLD: if is_active:             → if ZSTATE.get("is_active"):
# OLD: PRESENCE_MODE = "always"  → ZSTATE.set("presence_mode", "always")
# OLD: PRESENCE_MODE = "auto"    → ZSTATE.set("presence_mode", "auto")
# OLD: if PRESENCE_MODE == "x":  → if ZSTATE.get("presence_mode") == "x":
# OLD: _gaming_mode = True       → ZBUS.emit("gaming_start", {})
# OLD: _gaming_mode = False      → ZBUS.emit("gaming_end", {})
# OLD: if _gaming_mode:          → if ZSTATE.get("gaming_mode"):

# ── STEP 3 : AFTER TASK DISPATCHED TO BOARDROOM ──────────────────
ZBUS.emit("task_received", {
    "user"      : chat_name,
    "task"      : command,
    "user_type" : user_type,
})

# ── STEP 4 : WA DISCONNECT DETECTED ─────────────────────────────
ZBUS.emit("wa_disconnect", {
    "reason"        : "WA window not found",
    "restart_count" : _wa_restart_count,
})

# ── STEP 4b : WA RECONNECTED ─────────────────────────────────────
ZBUS.emit("wa_reconnected", {
    "restart_count" : _wa_restart_count,
})

# ── STEP 5 : GAMING MODE ─────────────────────────────────────────
# When gaming starts:
ZBUS.emit("gaming_start", {})
# When gaming ends:
ZBUS.emit("gaming_end", {})

# ── STEP 6 : NEW COMMANDS (add to command parser) ────────────────

# ZULU MIND
if upper == "ZULU MIND":
    report_to_boss(ZSTATE.get_mind_report(), user_type)

elif upper == "ZULU PATTERNS":
    report_to_boss(ZMEM.get_patterns_report(), user_type)

elif upper.startswith("ZULU MUTE "):
    contact = upper.replace("ZULU MUTE ", "").strip()
    ZMEM.mute(contact)
    report_to_boss(f"🔇 {contact} muted.", user_type)

elif upper.startswith("ZULU UNMUTE "):
    contact = upper.replace("ZULU UNMUTE ", "").strip()
    ZMEM.unmute(contact)
    report_to_boss(f"🔔 {contact} unmuted.", user_type)

elif upper == "ZULU LOCKDOWN":
    ZSTATE.set("lockdown", True)
    report_to_boss("🔒 LOCKDOWN — only Boss & GF get through.", user_type)

elif upper == "ZULU UNLOCK":
    ZSTATE.set("lockdown", False)
    report_to_boss("✅ Lockdown lifted.", user_type)

# ── STEP 7 : UNKNOWN USER HANDLER — add at top ───────────────────
if ZMEM.is_muted(chat_name):
    return   # silently skip muted contacts

if ZSTATE.get("lockdown"):
    return   # block all unknowns in lockdown mode
