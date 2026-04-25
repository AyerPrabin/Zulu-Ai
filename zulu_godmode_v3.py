# =============================================================================
# ███████╗██╗   ██╗██╗     ██╗   ██╗     ██████╗  ██████╗ ██████╗
# ╚════██║██║   ██║██║     ██║   ██║    ██╔════╝ ██╔═══██╗██╔══██╗
#     ██╔╝██║   ██║██║     ██║   ██║    ██║  ███╗██║   ██║██║  ██║
#    ██╔╝ ██║   ██║██║     ██║   ██║    ██║   ██║██║   ██║██║  ██║
#    ██║  ╚██████╔╝███████╗╚██████╔╝    ╚██████╔╝╚██████╔╝██████╔╝
#    ╚═╝   ╚═════╝ ╚══════╝ ╚═════╝      ╚═════╝  ╚═════╝ ╚═════╝
#
#  🧠 ZULU GOD MODE v3.0 — ALL IN ONE
#  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TIER 2  ▸ Neural Archive   — ChromaDB Vector Memory (RAG)
#  TIER 3  ▸ Browser Bot      — Playwright autonomous web agent
#  TIER 5  ▸ Swarm Mode       — Parallel multi-agent execution
#  DUAL    ▸ Reply Engine     — Desktop toast + WhatsApp reply
#  LOCK    ▸ Auth code        — zulu2006
#  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Author : Prabin Ayer
#  File   : zulu_godmode_v3.py   (standalone, imports from existing modules)
# =============================================================================

import os, re, json, time, datetime, threading, hashlib, subprocess
import requests
from typing import Optional

# ── auth gate ─────────────────────────────────────────────────────────────────
GOD_MODE_CODE = "zulu2006"
_GM_UNLOCKED  = False

def unlock_godmode(code: str) -> bool:
    global _GM_UNLOCKED
    if code.strip() == GOD_MODE_CODE:
        _GM_UNLOCKED = True
        _gm_log("🔓 GOD MODE UNLOCKED")
        return True
    _gm_log("🔒 Wrong code — access denied", "WARN")
    return False

def _require_auth():
    if not _GM_UNLOCKED:
        raise PermissionError("🔒 GOD MODE LOCKED — send 'ZULU GODMODE zulu2006' first")

# ── local logger (works even if zulu_core not imported yet) ───────────────────
def _gm_log(msg: str, level: str = "INFO"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level:<5}] [godmode   ] {msg}")
    try:
        from zulu_core import zlog
        zlog("godmode", msg, level)
    except Exception:
        pass

# ── paths ──────────────────────────────────────────────────────────────────────
BASE_DIR      = r"D:\AI_Agency_Work"
LOGS_DIR      = os.path.join(BASE_DIR, "System_Logs")
SCREENSHOTS   = os.path.join(BASE_DIR, "Screenshots")
CHROMA_DIR    = os.path.join(BASE_DIR, "neural_archive")
BROWSER_CACHE = os.path.join(LOGS_DIR,  "browser_cache.json")
PREDICT_FILE  = os.path.join(LOGS_DIR,  "predict_engine.json")

for _d in [LOGS_DIR, SCREENSHOTS, CHROMA_DIR]:
    os.makedirs(_d, exist_ok=True)

# ── optional deps check ───────────────────────────────────────────────────────
def _check_deps():
    missing = []
    try:
        import chromadb
    except ImportError:
        missing.append("chromadb  (pip install chromadb)")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        missing.append("playwright  (pip install playwright && playwright install chromium)")
    try:
        from crewai import Agent
    except ImportError:
        missing.append("crewai  (pip install crewai)")
    if missing:
        _gm_log("Missing deps — some tiers disabled:", "WARN")
        for m in missing:
            _gm_log(f"  ❌ {m}", "WARN")
    else:
        _gm_log("✅ All God Mode deps present")

_check_deps()


# =============================================================================
# ██  TIER 2 — NEURAL ARCHIVE  (ChromaDB RAG)                             ██
# =============================================================================

try:
    import chromadb
    _chroma_client     = chromadb.PersistentClient(path=CHROMA_DIR)
    _chroma_collection = _chroma_client.get_or_create_collection(
        name="zulu_neural",
        metadata={"hnsw:space": "cosine"},
    )
    NEURAL_OK = True
    _gm_log(f"🧠 Neural Archive ready — {_chroma_collection.count()} memories stored")
except Exception as _ne:
    NEURAL_OK = False
    _chroma_collection = None
    _gm_log(f"Neural Archive unavailable: {_ne}", "WARN")

_neural_lock = threading.Lock()


def _get_embedding(text: str) -> Optional[list]:
    """Generate embedding via local Ollama nomic-embed-text."""
    try:
        r = requests.post(
            "http://localhost:11434/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": text[:3000]},
            timeout=10,
        )
        return r.json().get("embedding")
    except Exception as e:
        _gm_log(f"Embedding error: {e}", "WARN")
        return None


def archive_context(text: str, metadata: dict = None) -> bool:
    """
    TIER 2: Vectorize and store text in ChromaDB.
    metadata = {"user": str, "type": str, "ts": str, ...}
    Returns True on success.
    """
    if not NEURAL_OK:
        return False
    emb = _get_embedding(text)
    if not emb:
        return False
    uid  = hashlib.md5((text + datetime.datetime.now().isoformat()).encode()).hexdigest()
    meta = metadata or {}
    meta.setdefault("ts",   datetime.datetime.now().isoformat())
    meta.setdefault("type", "task")
    with _neural_lock:
        try:
            _chroma_collection.upsert(
                ids=[uid],
                embeddings=[emb],
                documents=[text[:2000]],
                metadatas=[meta],
            )
            _gm_log(f"📚 Archived memory [{meta['type']}]: {text[:60]}")
            return True
        except Exception as e:
            _gm_log(f"Archive upsert error: {e}", "ERROR")
            return False


def query_memory(query_text: str, n_results: int = 3) -> str:
    """
    TIER 2: RAG — retrieve top-N most semantically relevant memories.
    Returns formatted string ready to inject into agent prompt.
    """
    if not NEURAL_OK:
        return ""
    emb = _get_embedding(query_text)
    if not emb:
        return ""
    with _neural_lock:
        try:
            res  = _chroma_collection.query(
                query_embeddings=[emb],
                n_results=min(n_results, _chroma_collection.count() or 1),
            )
            docs = res.get("documents", [[]])[0]
            metas = res.get("metadatas", [[]])[0]
            if not docs:
                return ""
            parts = ["🧠 Relevant memories from Neural Archive:"]
            for i, (doc, meta) in enumerate(zip(docs, metas), 1):
                ts = meta.get("ts", "")[:16]
                tp = meta.get("type", "?")
                parts.append(f"  [{i}] [{ts}] ({tp}) {doc[:200]}")
            return "\n".join(parts)
        except Exception as e:
            _gm_log(f"Query memory error: {e}", "ERROR")
            return ""


def neural_stats() -> str:
    """Return Neural Archive stats string."""
    if not NEURAL_OK:
        return "❌ Neural Archive offline (chromadb not installed)"
    try:
        count = _chroma_collection.count()
        return (
            f"🧠 Neural Archive Stats\n"
            f"  Stored memories : {count}\n"
            f"  Vector DB path  : {CHROMA_DIR}\n"
            f"  Embed model     : nomic-embed-text (Ollama)\n"
            f"  Status          : {'🟢 Online' if NEURAL_OK else '🔴 Offline'}"
        )
    except Exception as e:
        return f"Neural stats error: {e}"


# =============================================================================
# ██  TIER 3 — BROWSER BOT  (Playwright autonomous agent)                 ██
# =============================================================================

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False

_browser_lock = threading.Lock()


def browser_navigate(
    url: str,
    click_text: str = "",
    scrape_selector: str = "body",
    headless: bool = True,
    timeout_ms: int = 15000,
) -> dict:
    """
    TIER 3: Open browser → navigate → optionally click → scrape text.
    Returns {"status": "success"|"error", "data": str, "url": str}
    Runs synchronously but called from a thread to protect tray process.
    """
    if not PLAYWRIGHT_OK:
        return {"status": "error", "data": "Playwright not installed", "url": url}

    with _browser_lock:
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=headless,
                    args=["--no-sandbox", "--disable-gpu"],
                )
                ctx  = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    )
                )
                page = ctx.new_page()
                page.set_default_timeout(timeout_ms)

                _gm_log(f"🌐 Browser navigating → {url}")
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)

                if click_text:
                    try:
                        page.get_by_text(click_text, exact=False).first.click()
                        page.wait_for_timeout(2000)
                        _gm_log(f"🖱️  Clicked: '{click_text}'")
                    except Exception as ce:
                        _gm_log(f"Click failed ('{click_text}'): {ce}", "WARN")

                # Scrape
                try:
                    el = page.locator(scrape_selector).first
                    data = el.inner_text(timeout=5000)
                except Exception:
                    data = page.inner_text("body")

                final_url = page.url
                browser.close()

                data = re.sub(r'\s+', ' ', data).strip()[:4000]
                _gm_log(f"✅ Browser scraped {len(data)} chars from {final_url}")
                return {"status": "success", "data": data, "url": final_url}

        except Exception as e:
            _gm_log(f"Browser error: {e}", "ERROR")
            return {"status": "error", "data": str(e), "url": url}


def browser_task_async(
    url: str,
    click_text: str = "",
    callback=None,
    headless: bool = True,
) -> threading.Thread:
    """
    TIER 3: Run browser_navigate in a daemon thread.
    callback(result_dict) is called when done.
    Returns the thread so caller can join() if needed.
    """
    def _run():
        result = browser_navigate(url, click_text, headless=headless)
        if callback:
            try:
                callback(result)
            except Exception as e:
                _gm_log(f"Browser callback error: {e}", "WARN")

    t = threading.Thread(target=_run, daemon=True, name="ZuluBrowser")
    t.start()
    return t


def god_browser_search(query: str, site: str = "https://duckduckgo.com") -> str:
    """
    TIER 3: God Mode browser search — navigate to site, search query, scrape results.
    Use for: 'find cheapest flight', 'scrape live price', 'check website'.
    """
    _require_auth()
    if not PLAYWRIGHT_OK:
        return "❌ Playwright not installed. Run: pip install playwright && playwright install chromium"

    # Build search URL
    import urllib.parse
    if site == "https://duckduckgo.com":
        url = f"https://duckduckgo.com/?q={urllib.parse.quote(query)}&ia=web"
    else:
        url = site

    _gm_log(f"🔍 God Browser Search: '{query}'")
    result = browser_navigate(url, headless=True)
    if result["status"] == "success":
        data = result["data"][:1500]
        return f"🌐 Browser result for '{query}':\n{data}"
    return f"❌ Browser failed: {result['data']}"


# CrewAI Browser Tool ─────────────────────────────────────────────────────────
try:
    from crewai.tools import BaseTool

    class GodBrowserTool(BaseTool):
        """
        TIER 3 CrewAI Tool — autonomous browser agent.
        Input format: 'url|||click_text|||headless(true/false)'
        Examples:
          'https://google.com|||Python tutorial|||true'
          'https://coinmarketcap.com||||||true'
        """
        name: str        = "god_browser"
        description: str = (
            "God Mode Browser: navigate any URL, click elements, scrape data. "
            "Input: 'url|||click_text|||headless'. "
            "Use for live data, flight prices, site scraping, web research."
        )

        def _run(self, input_str: str) -> str:
            parts    = (input_str + "|||" * 3).split("|||")
            url      = parts[0].strip()
            click    = parts[1].strip()
            headless = parts[2].strip().lower() != "false"

            if not url.startswith(("http", "www")):
                url = "https://" + url

            result = browser_navigate(url, click_text=click, headless=headless)
            if result["status"] == "success":
                return f"Scraped from {result['url']}:\n{result['data'][:2000]}"
            return f"Browser error: {result['data']}"

    god_browser_tool = GodBrowserTool()
    _gm_log("🌐 GodBrowserTool (CrewAI) ready")

except ImportError:
    god_browser_tool = None
    _gm_log("CrewAI not installed — GodBrowserTool disabled", "WARN")


# =============================================================================
# ██  DUAL REPLY ENGINE  — Desktop toast + WhatsApp                       ██
# =============================================================================

def _desktop_toast(title: str, message: str, duration_secs: int = 8):
    """
    Show a Windows 10/11 toast notification using PowerShell.
    No external libs needed — pure PowerShell BurntToast fallback to MessageBox.
    """
    # Method 1: Windows 10 Toast via PowerShell
    try:
        ps_script = (
            f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
            f"ContentType = WindowsRuntime] | Out-Null; "
            f"[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null; "
            f"$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
            f"[Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
            f"$xml.GetElementsByTagName('text')[0].AppendChild($xml.CreateTextNode('{title}')) | Out-Null; "
            f"$xml.GetElementsByTagName('text')[1].AppendChild($xml.CreateTextNode('{message[:100].replace(chr(39), '')}')) | Out-Null; "
            f"$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
            f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('ZULU AI').Show($toast)"
        )
        subprocess.run(
            ["powershell", "-c", ps_script],
            timeout=5, capture_output=True
        )
        return
    except Exception:
        pass

    # Method 2: Simple MessageBox fallback
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            f"{message[:300]}",
            f"🤖 ZULU — {title}",
            0x40 | 0x1000,   # Info icon + topmost
        )
    except Exception as e:
        _gm_log(f"Desktop toast error: {e}", "WARN")


def _whatsapp_reply(message: str, user_type: str = "BOSS") -> bool:
    """Send reply via WhatsApp using existing boardroom report_to_boss."""
    try:
        from boardroom_engine import report_to_boss
        return report_to_boss(message, user_type)
    except Exception as e:
        _gm_log(f"WhatsApp reply error: {e}", "WARN")
        return False


def dual_reply(
    message: str,
    user_type: str = "BOSS",
    title: str = "ZULU Response",
    whatsapp: bool = True,
    desktop: bool = True,
) -> dict:
    """
    GOD MODE dual reply:
      1. Desktop Windows toast notification (instant)
      2. WhatsApp message via existing automation
    Returns {"desktop": bool, "whatsapp": bool}
    """
    results = {"desktop": False, "whatsapp": False}

    if desktop:
        try:
            threading.Thread(
                target=_desktop_toast,
                args=(title, message),
                daemon=True,
                name="ZuluToast",
            ).start()
            results["desktop"] = True
            _gm_log(f"🖥️  Desktop toast sent: {message[:50]}")
        except Exception as e:
            _gm_log(f"Desktop reply error: {e}", "WARN")

    if whatsapp:
        try:
            wa_ok = _whatsapp_reply(message, user_type)
            results["whatsapp"] = wa_ok
            _gm_log(f"📱 WhatsApp reply {'✅' if wa_ok else '❌'}: {message[:50]}")
        except Exception as e:
            _gm_log(f"WhatsApp reply error: {e}", "WARN")

    return results


# =============================================================================
# ██  PREDICT ENGINE  — "Next Task" suggestion system                     ██
# =============================================================================

_predict_lock = threading.Lock()


def _load_predict_data() -> dict:
    try:
        if os.path.exists(PREDICT_FILE):
            with open(PREDICT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"pairs": [], "last_task": ""}


def _save_predict_data(data: dict):
    try:
        with open(PREDICT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        _gm_log(f"Predict save error: {e}", "WARN")


def record_task_for_predict(task: str):
    """
    After each task completes, record the (prev_task → current_task) pair.
    This builds a Markov-style transition table for prediction.
    """
    with _predict_lock:
        data = _load_predict_data()
        prev = data.get("last_task", "")
        if prev and prev != task:
            data["pairs"].append({"from": prev[:80], "to": task[:80]})
            data["pairs"] = data["pairs"][-500:]  # keep last 500 pairs
        data["last_task"] = task[:80]
        _save_predict_data(data)


def predict_next_task(current_task: str) -> str:
    """
    Predict what Boss will likely ask next based on past task sequences.
    Returns a human-readable suggestion string.
    """
    with _predict_lock:
        data = _load_predict_data()
    pairs = data.get("pairs", [])
    if not pairs:
        return ""

    ct = current_task.lower()
    # Find pairs where 'from' is similar to current task
    from collections import Counter
    candidates = []
    for p in pairs:
        if any(w in p["from"].lower() for w in ct.split() if len(w) > 3):
            candidates.append(p["to"])

    if not candidates:
        # fallback: just show most common next tasks globally
        all_to = [p["to"] for p in pairs]
        counter = Counter(all_to)
        if counter:
            top = counter.most_common(1)[0][0]
            return f"💡 Predicted next: {top}"
        return ""

    counter = Counter(candidates)
    top, count = counter.most_common(1)[0]
    if count >= 1:
        return f"💡 You usually follow this with: '{top}' — want me to do that too?"
    return ""


# =============================================================================
# ██  TIER 5 — SWARM MODE  (Parallel multi-agent CrewAI)                  ██
# =============================================================================

try:
    from crewai import Agent, Task, Crew, Process, LLM
    CREWAI_OK = True
except ImportError:
    CREWAI_OK = False
    _gm_log("CrewAI not installed — Swarm Mode disabled", "WARN")


class SwarmManager:
    """
    TIER 5 — God Mode Swarm.
    Spawns 5 parallel specialist agents:
      1. Orchestrator  — breaks task into sub-tasks
      2. Coder         — Python/code generation
      3. Designer      — HTML/CSS/frontend
      4. Researcher    — live web research (uses GodBrowserTool)
      5. QA Reviewer   — reviews and approves all output

    Uses Process.hierarchical with Ollama local brains.
    After completion fires predict_next_task() for Boss suggestion.
    """

    def __init__(self):
        self._lock = threading.Lock()

    def _build_llm(self) -> object:
        """Build LLM from best available Ollama brain."""
        if not CREWAI_OK:
            raise RuntimeError("CrewAI not installed")
        try:
            from brain_manager import get_best_brain, BRAINS
            bid, brain = get_best_brain()
            if not bid:
                raise RuntimeError("All brains offline")
            return LLM(
                model=brain["model"],
                base_url=brain["base_url"],
                api_key="ollama",
            )
        except ImportError:
            # fallback: direct Ollama
            return LLM(
                model="mistral",
                base_url="http://localhost:11434/v1",
                api_key="ollama",
            )

    def _make_agent(self, role, goal, backstory, tools=None) -> 'Agent':
        return Agent(
            role=role,
            goal=goal,
            backstory=backstory,
            llm=self._build_llm(),
            tools=tools or [],
            verbose=False,           # suppress per-agent spam
            max_iter=3,              # prevent infinite loops on local models
            allow_delegation=False,  # hierarchical handles delegation
        )

    def run(
        self,
        request: str,
        user_type: str = "BOSS",
        projects_dir: str = None,
    ) -> str:
        """
        TIER 5 main entry.
        Runs a full 5-agent swarm on 'request'.
        Returns final assembled result as string.
        """
        _require_auth()
        if not CREWAI_OK:
            return "❌ CrewAI not installed — Swarm Mode unavailable"

        _gm_log(f"🐝 SWARM launched for: '{request[:80]}'")
        projects_dir = projects_dir or r"D:\AI_Agency_Work\Projects"

        # Pull neural memory context
        mem_ctx = query_memory(request) or "No prior memories."

        try:
            tools = [god_browser_tool] if god_browser_tool else []

            # ── 5 agents ───────────────────────────────────────────────────
            orchestrator = self._make_agent(
                "Orchestrator",
                "Decompose the complex request into clear sub-tasks for each specialist.",
                f"Master planner. Context:\n{mem_ctx}\nBe concise. Output numbered sub-task list.",
            )
            coder = self._make_agent(
                "Coder",
                f"Write complete Python scripts. Save to {projects_dir}.",
                "Expert Python developer. Write full, working code. No placeholders.",
            )
            designer = self._make_agent(
                "Designer",
                f"Create complete HTML/CSS/JS files. Save to {projects_dir}.",
                "Expert frontend developer. Inline CSS+JS. Beautiful, responsive design.",
            )
            researcher = self._make_agent(
                "Researcher",
                "Search the web for up-to-date facts, APIs, examples, and data.",
                "Expert web researcher. Use god_browser tool for live data.",
                tools=tools,
            )
            qa = self._make_agent(
                "QA Reviewer",
                "Review all produced code and content. Find bugs, missing pieces, improvements.",
                "Senior QA engineer. Be specific about what passes and what needs fixing.",
            )

            # ── tasks ──────────────────────────────────────────────────────
            t_plan = Task(
                description=(
                    f"Request: '{request}'\n"
                    f"Memory Context:\n{mem_ctx}\n"
                    "Break this into sub-tasks for: Coder, Designer, Researcher. "
                    "List each sub-task clearly."
                ),
                expected_output="Numbered list of sub-tasks for each agent.",
                agent=orchestrator,
            )

            t_research = Task(
                description=(
                    f"Research task for: '{request}'\n"
                    "Find relevant APIs, examples, live data, or documentation. "
                    "Use god_browser to scrape if needed. Return key facts only."
                ),
                expected_output="Research findings, relevant URLs, key data points.",
                agent=researcher,
            )

            t_code = Task(
                description=(
                    f"Write Python code for: '{request}'\n"
                    f"Save to: {projects_dir}\n"
                    "Use research findings from Researcher. "
                    "Write complete, runnable code. Include error handling."
                ),
                expected_output=f"Complete Python file(s) saved to {projects_dir}.",
                agent=coder,
                context=[t_plan, t_research],
            )

            t_design = Task(
                description=(
                    f"Create HTML/CSS/JS frontend for: '{request}'\n"
                    f"Save to: {projects_dir}\n"
                    "Inline all CSS and JS. Make it visually clean and modern. "
                    "Include dark mode if appropriate."
                ),
                expected_output=f"Complete HTML file saved to {projects_dir}.",
                agent=designer,
                context=[t_plan],
            )

            t_qa = Task(
                description=(
                    f"Review ALL outputs produced for: '{request}'\n"
                    "Check: completeness, bugs, missing features, code quality. "
                    "Give a brief pass/fail verdict with specific fixes if needed. "
                    "Then write a final WhatsApp-ready 3-sentence summary for Boss."
                ),
                expected_output="QA verdict + short WhatsApp summary for Boss.",
                agent=qa,
                context=[t_code, t_design, t_research],
            )

            # ── crew ───────────────────────────────────────────────────────
            crew = Crew(
                agents=[orchestrator, coder, designer, researcher, qa],
                tasks=[t_plan, t_research, t_code, t_design, t_qa],
                process=Process.sequential,   # sequential on local to avoid OOM
                verbose=True,
                memory=False,
            )

            result = crew.kickoff()
            final  = str(result).strip() if result else "Swarm returned no output."

            # Archive to neural memory
            if NEURAL_OK:
                threading.Thread(
                    target=archive_context,
                    args=(f"Swarm task: {request}\nResult: {final}",
                          {"type": "swarm", "user": user_type}),
                    daemon=True,
                ).start()

            # Predict next task
            record_task_for_predict(request)
            prediction = predict_next_task(request)

            summary = final[:800]
            if prediction:
                summary += f"\n\n{prediction}"

            _gm_log(f"🐝 Swarm complete: {final[:80]}")
            return summary

        except Exception as e:
            err = f"❌ Swarm error: {e}"
            _gm_log(err, "ERROR")
            return err


# Global swarm instance
SWARM = SwarmManager()


# =============================================================================
# ██  GOD MODE COMMAND ROUTER                                             ██
# =============================================================================

# Commands that require the auth code
GOD_COMMANDS = [
    "GODMODE", "SWARM", "NEURAL", "BROWSER", "PREDICT", "GOD "
]


def handle_godmode_command(command: str, user_type: str = "BOSS") -> tuple:
    """
    Drop-in router — call BEFORE boardroom in your tray scan loop.
    Returns (handled: bool, response: str)

    Commands:
      ZULU GODMODE zulu2006       → unlock God Mode
      ZULU GOD STATUS             → show God Mode status
      ZULU GOD NEURAL STATS       → neural archive stats
      ZULU GOD SEARCH <query>     → browser search (Tier 3)
      ZULU SWARM <task>           → launch 5-agent swarm (Tier 5)
      ZULU GOD PREDICT            → show next task prediction
      ZULU GOD MEMORIES <query>   → search neural memories
    """
    upper = command.upper().strip()

    # ── Unlock ────────────────────────────────────────────────────────────────
    m = re.match(r'(?:ZULU\s+)?GODMODE\s+(\S+)', upper)
    if m:
        code = command.split()[-1].strip()
        if unlock_godmode(code):
            resp = (
                "🔓 *ZULU GOD MODE UNLOCKED* 🔓\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "  TIER 2 ▸ Neural Archive (RAG) — " + ("🟢 Online" if NEURAL_OK else "🔴 Offline") + "\n"
                "  TIER 3 ▸ Browser Bot (Playwright) — " + ("🟢 Online" if PLAYWRIGHT_OK else "🔴 Offline") + "\n"
                "  TIER 5 ▸ Swarm Mode (5 Agents) — " + ("🟢 Online" if CREWAI_OK else "🔴 Offline") + "\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "  Say 'ZULU SWARM build me a weather app' to launch Swarm.\n"
                "  Say 'ZULU GOD SEARCH <query>' for browser search.\n"
                "  Say 'ZULU GOD NEURAL STATS' for memory stats."
            )
        else:
            resp = "🔒 Wrong code. Try again."
        dual_reply(resp, user_type, title="God Mode Auth")
        return True, resp

    # All commands below require auth
    if not any(kw in upper for kw in GOD_COMMANDS):
        return False, ""

    if not _GM_UNLOCKED:
        resp = "🔒 GOD MODE LOCKED — send: ZULU GODMODE zulu2006"
        dual_reply(resp, user_type, title="God Mode Locked")
        return True, resp

    # ── Status ────────────────────────────────────────────────────────────────
    if re.search(r'GOD\s+STATUS', upper):
        mem_count = _chroma_collection.count() if NEURAL_OK else 0
        resp = (
            f"🤖 ZULU GOD MODE STATUS\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"  Neural Archive : {'🟢' if NEURAL_OK else '🔴'} ({mem_count} memories)\n"
            f"  Browser Bot    : {'🟢' if PLAYWRIGHT_OK else '🔴'}\n"
            f"  Swarm Mode     : {'🟢' if CREWAI_OK else '🔴'}\n"
            f"  Locked         : {'🔒' if not _GM_UNLOCKED else '🔓'}\n"
            f"  Time           : {datetime.datetime.now().strftime('%d %b %H:%M')}"
        )
        dual_reply(resp, user_type, title="God Status")
        return True, resp

    # ── Neural Stats ──────────────────────────────────────────────────────────
    if re.search(r'NEURAL\s+STATS', upper):
        resp = neural_stats()
        dual_reply(resp, user_type, title="Neural Archive")
        return True, resp

    # ── Neural Memory Search ──────────────────────────────────────────────────
    m = re.search(r'GOD\s+MEMORIES?\s+(.+)', upper)
    if m:
        query = command[m.start(1):m.start(1)+len(m.group(1))].strip()
        resp  = query_memory(query) or f"🧠 No memories found for '{query}'"
        dual_reply(resp, user_type, title="Neural Memory")
        return True, resp

    # ── Browser Search ────────────────────────────────────────────────────────
    m = re.search(r'GOD\s+SEARCH\s+(.+)', upper)
    if m:
        q    = command[m.start(1):m.start(1)+len(m.group(1))].strip()
        resp = god_browser_search(q)
        dual_reply(resp[:700], user_type, title="Browser Search")
        return True, resp

    # ── Swarm Mode ────────────────────────────────────────────────────────────
    m = re.search(r'SWARM\s+(.+)', upper)
    if m:
        task  = command[m.start(1):m.start(1)+len(m.group(1))].strip()
        dual_reply(
            f"🐝 SWARM LAUNCHED...\nWorking on: '{task}'\n5 agents activated. Results coming...",
            user_type, title="Swarm Mode"
        )

        def _run_swarm():
            result = SWARM.run(task, user_type)
            dual_reply(result[:700], user_type, title="Swarm Complete")

        threading.Thread(target=_run_swarm, daemon=True, name="ZuluSwarm").start()
        return True, f"🐝 Swarm launched for: {task}"

    # ── Predict ───────────────────────────────────────────────────────────────
    if re.search(r'GOD\s+PREDICT', upper):
        try:
            from zulu_core import ZMEM
            tasks = ZMEM.get("tasks", [])
            last  = tasks[-1]["task"] if tasks else ""
        except Exception:
            last = ""
        resp = predict_next_task(last) or "💡 Not enough data yet. Run more tasks first."
        dual_reply(resp, user_type, title="Predict Engine")
        return True, resp

    return False, ""


# =============================================================================
# ██  INTEGRATION HOOKS  — wire into existing ZULU systems                ██
# =============================================================================

def wire_into_zbus():
    """
    Call once at startup to wire God Mode into existing ZBUS event bus.
    Automatically archives every completed task into Neural Archive.
    """
    try:
        from zulu_core import ZBUS

        def _on_task_done(data):
            task   = data.get("task", "")
            result = data.get("result", "")
            user   = data.get("user", "?")
            mode   = data.get("mode", "task")
            # Archive to Neural Memory (background)
            threading.Thread(
                target=archive_context,
                args=(f"Task: {task}\nResult: {result}",
                      {"user": user, "type": mode, "ts": datetime.datetime.now().isoformat()}),
                daemon=True,
            ).start()
            # Record for predict engine
            record_task_for_predict(task)

        ZBUS.on("task_done", _on_task_done)
        _gm_log("✅ God Mode wired into ZBUS (auto-archive enabled)")
        return True
    except ImportError:
        _gm_log("zulu_core not found — manual wire required", "WARN")
        return False


def inject_neural_context(command: str) -> str:
    """
    Call this before building agent prompts.
    Returns relevant past memories to inject into context.
    """
    if not NEURAL_OK:
        return ""
    ctx = query_memory(command, n_results=3)
    return ctx


# =============================================================================
# ██  STARTUP BANNER                                                      ██
# =============================================================================

def print_godmode_banner():
    banner = """
╔══════════════════════════════════════════════════════╗
║   🤖  Z U L U   G O D   M O D E   v 3 . 0          ║
╠══════════════════════════════════════════════════════╣
║  TIER 2 ▸ Neural Archive (ChromaDB RAG)             ║
║  TIER 3 ▸ Browser Bot   (Playwright)                ║
║  TIER 5 ▸ Swarm Mode    (5 Parallel Agents)         ║
║  DUAL   ▸ Desktop + WhatsApp Reply Engine           ║
╠══════════════════════════════════════════════════════╣
║  Auth Code : zulu2006                               ║
║  Send      : ZULU GODMODE zulu2006                  ║
╚══════════════════════════════════════════════════════╝
"""
    print(banner)
    _gm_log(f"Neural: {'✅' if NEURAL_OK else '❌'}  "
            f"Browser: {'✅' if PLAYWRIGHT_OK else '❌'}  "
            f"Swarm: {'✅' if CREWAI_OK else '❌'}")


print_godmode_banner()
wire_into_zbus()


# =============================================================================
# ██  STANDALONE TEST / DEMO                                              ██
# =============================================================================

if __name__ == "__main__":
    print("\n=== ZULU GOD MODE v3 — SELF TEST ===")

    # Test auth
    print("\n[1] Auth test:")
    handled, resp = handle_godmode_command("ZULU GODMODE zulu2006")
    print(resp[:200])

    # Test neural archive
    print("\n[2] Neural Archive test:")
    ok = archive_context(
        "Boss asked me to build a weather app in Python using OpenWeatherMap API.",
        {"type": "test", "user": "BOSS"}
    )
    print(f"Archive: {'✅ success' if ok else '❌ failed (is Ollama running?)'} ")

    # Test query memory
    print("\n[3] Memory query test:")
    result = query_memory("weather app python")
    print(result[:300] if result else "No memories yet.")

    # Test predict
    print("\n[4] Predict Engine test:")
    record_task_for_predict("build weather app")
    record_task_for_predict("test the weather app")
    record_task_for_predict("build weather app")
    pred = predict_next_task("build weather app")
    print(pred or "Not enough data yet.")

    # Test dual reply (desktop only in test)
    print("\n[5] Dual Reply test (desktop toast):")
    res = dual_reply(
        "🤖 ZULU God Mode v3 is online and ready!",
        whatsapp=False,
        desktop=True,
        title="Test"
    )
    print(f"Desktop: {res['desktop']}  WhatsApp: {res['whatsapp']}")

    # Neural stats
    print("\n[6] Neural Stats:")
    print(neural_stats())

    print("\n✅ Self-test complete.")
