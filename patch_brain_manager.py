
# ═══════════════════════════════════════════════════════════════════
# BRAIN MANAGER — CORE BRAIN PATCH
# ═══════════════════════════════════════════════════════════════════

# ── STEP 1 : ADD AT TOP ──────────────────────────────────────────
from zulu_core import ZMEM, ZSTATE, ZBUS, zlog

# ── STEP 2 : IN mark_offline() — after b["online"] = False ───────
ZBUS.emit("brain_offline", {
    "brain_id": brain_id,
    "reason"  : reason,
    "retry_in": time_str,
})

# ── STEP 3 : IN auto_restore() — after b["online"] = True ────────
ZBUS.emit("brain_restored", {"brain_id": bid})

# ── STEP 4 : IN record_usage() — at very end ─────────────────────
online_count = sum(1 for b in BRAINS.values() if b["online"])
ZSTATE.set("brains_online", online_count)

# ── STEP 5 : REPLACE print() WITH zlog() ─────────────────────────
# OLD: print(f" 🔴 [{b['label']}] OFFLINE — {reason}...")
# NEW: zlog("brain", f"🔴 [{b['label']}] OFFLINE — {reason}")
#
# OLD: print(f" 🟢 [{b['label']}] RESTORED...")
# NEW: zlog("brain", f"🟢 [{b['label']}] RESTORED")
