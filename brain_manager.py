# brain_manager.py — ZULU Brain Manager v13.4  (FREE TIER FINAL)
# Fix 1: Cerebras model → cerebras/llama-3.3-70b-instruct  (was missing -instruct, caused 404)
# Fix 2: SambaNova model → sambanova/Meta-Llama-3.3-70B-Instruct  (added provider prefix)
# Fix 3: GEMINI_PRO kept in registry but disabled (online=False) — requires paid billing
# Fix 4: GEMINI      → gemini/gemini-2.5-flash       (free tier workhorse)
# Fix 5: GEMINI_LITE → gemini/gemini-2.5-flash-lite  (free tier ultra-fast)
# Fix 6: ROLE_BRAIN  → 100% free tier, no Pro dependency
from zulu_core import ZMEM, ZSTATE, ZBUS, zlog
import time
import datetime
import json
import os
import requests
from agency_config import API_KEYS

# ─────────────────────────────────────────────────────────────────────────────
# 🧠 BRAIN REGISTRY
# ─────────────────────────────────────────────────────────────────────────────
BRAINS = {
    "SAMBANOVA": {
        "label"       : "LLaMA 70B ⚡",
        "model"       : "sambanova/Meta-Llama-3.3-70B-Instruct",   # FIX: added sambanova/ prefix
        "api_key"     : API_KEYS["SAMBANOVA"],
        "base_url"    : "https://api.sambanova.ai/v1",
        "online"      : True,
        "offline_until": 0,
        "cooldown_secs": 1800,
        "daily_limit" : 500,
        "used_today"  : 0,
        "reset_date"  : "",
    },
    "GEMINI_LITE": {
        "label"       : "Gemini 2.5 Flash-Lite 💡",
        "model"       : "gemini/gemini-2.5-flash-lite",   # FREE tier — high volume, fast
        "api_key"     : API_KEYS["GEMINI"],
        "online"      : True,
        "offline_until": 0,
        "cooldown_secs": 3600,
        "daily_limit" : 1000,
        "used_today"  : 0,
        "reset_date"  : "",
    },
    "GEMINI": {
        "label"       : "Gemini 2.5 Flash ✨",
        "model"       : "gemini/gemini-2.5-flash",        # FREE tier — strong reasoning, main workhorse
        "api_key"     : API_KEYS["GEMINI"],
        "online"      : True,
        "offline_until": 0,
        "cooldown_secs": 3600,
        "daily_limit" : 500,
        "used_today"  : 0,
        "reset_date"  : "",
    },
    # ── 🧠 Gemini 3.1 Pro Preview — PAID only, disabled until billing enabled ──
    "GEMINI_PRO": {
        "label"       : "Gemini 3.1 Pro 🧠",
        "model"       : "gemini/gemini-3.1-pro-preview",
        "api_key"     : API_KEYS["GEMINI"],
        "online"      : False,        # DISABLED — requires paid billing, not free tier
        "offline_until": 9999999999,  # permanently offline until you enable billing
        "cooldown_secs": 3600,
        "daily_limit" : 0,
        "used_today"  : 0,
        "reset_date"  : "",
    },
    "MISTRAL": {
        "label"       : "Codestral 💻",
        "model"       : "mistral/codestral-latest",
        "api_key"     : API_KEYS["MISTRAL"],
        "online"      : True,
        "offline_until": 0,
        "cooldown_secs": 60,
        "daily_limit" : 999999,
        "used_today"  : 0,
        "reset_date"  : "",
    },
    "OPENROUTER": {
        "label"       : "OpenRouter 🌐",
        "model"       : "meta-llama/llama-3.3-70b-instruct:free",
        "api_key"     : API_KEYS["OPENROUTER"],
        "base_url"    : "https://openrouter.ai/api/v1",
        "online"      : True,
        "offline_until": 0,
        "cooldown_secs": 3600,
        "daily_limit" : 999999,
        "used_today"  : 0,
        "reset_date"  : "",
    },
    # ── 🆓 OpenRouter FREE model variants ────────────────────────────────────
    "OR_LLAMA_FREE": {
        "label"       : "OR Llama-3.3-70B 🆓",
        "model"       : "meta-llama/llama-3.3-70b-instruct:free",
        "api_key"     : API_KEYS["OPENROUTER"],
        "base_url"    : "https://openrouter.ai/api/v1",
        "online"      : True,
        "offline_until": 0,
        "cooldown_secs": 300,
        "daily_limit" : 999999,   # free tier — no hard cap but rate limited
        "used_today"  : 0,
        "reset_date"  : "",
    },
    "OR_GEMMA_FREE": {
        "label"       : "OR Gemma-3-27B 🆓",
        "model"       : "google/gemma-3-27b-it:free",
        "api_key"     : API_KEYS["OPENROUTER"],
        "base_url"    : "https://openrouter.ai/api/v1",
        "online"      : True,
        "offline_until": 0,
        "cooldown_secs": 300,
        "daily_limit" : 999999,
        "used_today"  : 0,
        "reset_date"  : "",
    },
    "OR_MISTRAL_FREE": {
        "label"       : "OR Mistral-7B 🆓",
        "model"       : "mistralai/mistral-7b-instruct:free",
        "api_key"     : API_KEYS["OPENROUTER"],
        "base_url"    : "https://openrouter.ai/api/v1",
        "online"      : True,
        "offline_until": 0,
        "cooldown_secs": 300,
        "daily_limit" : 999999,
        "used_today"  : 0,
        "reset_date"  : "",
    },
    "CEREBRAS": {
        "label"       : "Cerebras ⚡🆓",
        "model"       : "cerebras/llama-3.3-70b-instruct",   # FIX: added -instruct (2026 API requires this)
        "api_key"     : API_KEYS["CEREBRAS"],
        "base_url"    : "https://api.cerebras.ai/v1",
        "online"      : True,
        "offline_until": 0,
        "cooldown_secs": 60,
        "daily_limit" : 999999,   # very generous free tier
        "used_today"  : 0,
        "reset_date"  : "",
    },
    "OLLAMA": {
        "label"       : "Ollama Local 🏠",
        "model"       : "ollama/llama3.2",
        "api_key"     : "ollama",
        "base_url"    : "http://localhost:11434/v1",
        "online"      : False,
        "offline_until": 0,
        "cooldown_secs": 0,
        "daily_limit" : 999999,
        "used_today"  : 0,
        "reset_date"  : "",
    },
}

# Priority order — free OR models sit between OPENROUTER and OLLAMA
PRIORITY = [
    "SAMBANOVA", "GEMINI_LITE", "GEMINI", "GEMINI_PRO", "MISTRAL",
    "OPENROUTER",
    "OR_LLAMA_FREE", "OR_GEMMA_FREE", "OR_MISTRAL_FREE",
    "CEREBRAS",
    "OLLAMA"
]

# Role → preferred brain  (2026 Free Tier — Gemini 2.5 only, no billing required)
ROLE_BRAIN = {
    "scribe"   : "GEMINI_LITE",    # 2.5 Flash-Lite — fast, free, high-volume background tasks
    "worker"   : "GEMINI",         # 2.5 Flash — strong reasoning, handles all general tasks
    "tech"     : "GEMINI",         # 2.5 Flash instead of Pro — free tier safe
    "visionary": "GEMINI",         # 2.5 Flash instead of Pro — free tier safe
    "reviewer" : "GEMINI_LITE",    # save 2.5 Flash quota for primary worker tasks
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
# 🔍 PING FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────
def ping_gemini():
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEYS['GEMINI']}"
        r   = requests.get(url, timeout=5)
        return r.status_code == 200
    except:
        return False

def ping_sambanova():
    try:
        url = "https://api.sambanova.ai/v1/models"
        r   = requests.get(url, headers={"Authorization": f"Bearer {API_KEYS['SAMBANOVA']}"}, timeout=5)
        return r.status_code == 200
    except:
        return False

def ping_mistral():
    try:
        url = "https://api.mistral.ai/v1/models"
        r   = requests.get(url, headers={"Authorization": f"Bearer {API_KEYS['MISTRAL']}"}, timeout=5)
        return r.status_code == 200
    except:
        return False

def ping_openrouter():
    try:
        url = "https://openrouter.ai/api/v1/models"
        r   = requests.get(url, headers={"Authorization": f"Bearer {API_KEYS['OPENROUTER']}"}, timeout=5)
        return r.status_code == 200
    except:
        return False


def ping_cerebras():
    try:
        url = "https://api.cerebras.ai/v1/models"
        r   = requests.get(url, headers={"Authorization": f"Bearer {API_KEYS['CEREBRAS']}"}, timeout=5)
        return r.status_code == 200
    except:
        return False

def ping_ollama():
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except:
        return False

def check_all_pings():
    print("🔍 Pinging all AI brains...")
    or_ok = ping_openrouter()
    checks = {
        "GEMINI"        : ping_gemini(),
        "GEMINI_LITE"   : ping_gemini(),
        "GEMINI_PRO"    : ping_gemini(),   # same endpoint, key check only
        "SAMBANOVA"     : ping_sambanova(),
        "MISTRAL"       : ping_mistral(),
        "OPENROUTER"    : or_ok,
        "OR_LLAMA_FREE" : or_ok,   # same endpoint as OPENROUTER
        "OR_GEMMA_FREE" : or_ok,
        "OR_MISTRAL_FREE": or_ok,
        "CEREBRAS"      : ping_cerebras(),
        "OLLAMA"        : ping_ollama(),
    }
    for bid, ok in checks.items():
        b = BRAINS[bid]
        if ok:
            b["online"]      = True
            _fail_counts[bid] = 0
            print(f" 🟢 {b['label']} reachable")
        else:
            b["online"]        = False
            b["offline_until"] = time.time() + b["cooldown_secs"]
            print(f" 🔴 {b['label']} unreachable")
    return checks

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
