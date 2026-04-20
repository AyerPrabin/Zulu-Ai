
# ═══════════════════════════════════════════════════════════════════
# BOARDROOM ENGINE — CORE BRAIN PATCH
# ═══════════════════════════════════════════════════════════════════

# ── STEP 1 : ADD AT TOP ──────────────────────────────────────────
from zulu_core import ZMEM, ZSTATE, ZBUS, zlog

# ── STEP 2 : REPLACE remember_task() calls ───────────────────────
# OLD: remember_task(command, task_type, final)
# NEW:
ZMEM.remember_task(user_type, command, task_type, final, brain_used=str(bid))

# ── STEP 3 : AFTER TASK COMPLETES SUCCESSFULLY ───────────────────
# (after report_to_boss Done line)
ZBUS.emit("task_done", {
    "user"   : user_type,
    "task"   : command,
    "result" : final[:200],
    "elapsed": elapsed,
    "brain"  : str(bid),
    "mode"   : task_type,
})

# ── STEP 3b : IN except block ────────────────────────────────────
ZBUS.emit("task_failed", {
    "user" : user_type,
    "task" : command,
    "error": str(ex)[:100],
})

# ── STEP 4 : RESPONSE CACHE (speed boost) ────────────────────────
# At START of launch_boardroom(), before running crew:
cached = ZMEM.get_cached(command)
if cached:
    report_to_boss(f"⚡ (cached)\n\n{cached}", user_type)
    return

# After getting result — cache it:
ZMEM.cache_response(command, final)

# ── STEP 5 : SMART MEMORY CONTEXT ────────────────────────────────
# Replace get_memory_context() with:
def get_memory_context() -> str:
    return ZMEM.get_task_context(last_n=10)

# ── STEP 6 : WA HEALTH AWARENESS ─────────────────────────────────
# After tone_msg is built, add:
if not ZSTATE.get("wa_healthy"):
    tone_msg += " Keep reply under 2 sentences — WA is struggling."
