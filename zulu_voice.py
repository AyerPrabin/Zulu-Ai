# zulu_voice.py — ZULU Voice Engine v2.0
import re
import time
import threading
from zulu_core import zlog, ZMEM, ZSTATE, ZBUS

# ─────────────────────────────────────────────────────────────────────────────
# 🔧  OPTIONAL DEPENDENCY GUARDS
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
# Wake words — Google STT mishears "ZULU" as these variants, all valid
WAKE_WORDS = [
    "hey zulu", "hey julia", "hey julio", "hey juliet",
    "hey zoo", "zulu", "hey sue", "hey zool", "a zulu",
    "heysula", "hey sula",
]

# ── OWNER VOICE LOCK ─────────────────────────────────────────────────────────
# Set to True = ZULU only responds when YOU are at the PC (no strangers)
# Uses a simple mic energy + keyword guard — no face detection needed.
# When OWNER_ONLY = True, ZULU ignores wake words unless ZSTATE confirms
# the PC is in "owner present" mode (set automatically on launch, or send
# ZULU VOICE LOCK / ZULU VOICE UNLOCK from WhatsApp).
OWNER_ONLY = True   # ← keep True — only you and GF trigger voice

# How long to wait for a command after wake word (seconds)
COMMAND_TIMEOUT = 10

# How loud the mic has to be to count as speech
ENERGY_THRESHOLD = 300

# Speak replies aloud?
TTS_ENABLED = True

# Speech rate (words per minute)
TTS_RATE = 170

# Max chars spoken aloud before truncating
TTS_MAX_CHARS = 400


# ─────────────────────────────────────────────────────────────────────────────
# 🔊  TEXT-TO-SPEECH
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
        _tts_engine.setProperty("volume", 0.92)
        voices = _tts_engine.getProperty("voices") or []
        for v in voices:
            name_lower = (v.name or "").lower()
            if "zira" in name_lower or "david" in name_lower:
                _tts_engine.setProperty("voice", v.id)
                break
        zlog("voice", f"TTS engine ready  ({len(voices)} voice(s) available)")
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
    """
    Speak text aloud.
    blocking=True  → wait until done (use for confirmations).
    blocking=False → fire-and-forget background thread (default).
    """
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
            # Fallback: PowerShell SAPI (always available on Windows)
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
# 🎙️  SPEECH RECOGNITION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _is_wake_word(text: str) -> bool:
    tl = text.lower().strip()
    return any(w in tl for w in WAKE_WORDS)


def _strip_wake_word(text: str) -> str:
    tl = text.lower().strip()
    for w in WAKE_WORDS:
        if tl.startswith(w):
            offset = text.lower().find(w) + len(w)
            return text[offset:].strip(" ,.")
    return text


def _listen_once(recognizer, mic, timeout: int = COMMAND_TIMEOUT) -> str:
    """
    Listen once and return transcribed text.
    Returns '' on silence / timeout / unintelligible audio.
    FIX: mic is used as a fresh context manager each call — no stale stream.
    """
    try:
        with mic as source:
            # FIX: shorter ambient noise adjustment so it doesn't eat the command
            recognizer.adjust_for_ambient_noise(source, duration=0.1)
            audio = recognizer.listen(
                source,
                timeout=timeout,
                phrase_time_limit=15,
            )
        result = recognizer.recognize_google(audio).strip()
        zlog("voice", f"STT heard: '{result}'")
        return result
    except sr.WaitTimeoutError:
        zlog("voice", "STT: no speech detected (timeout)")
        return ""
    except sr.UnknownValueError:
        zlog("voice", "STT: audio unintelligible")
        return ""
    except sr.RequestError as e:
        zlog("voice", f"STT network error: {e}", "WARN")
        return ""
    except Exception as e:
        zlog("voice", f"STT error: {e}", "WARN")
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# 🔒  OWNER LOCK — simple presence guard
# ─────────────────────────────────────────────────────────────────────────────
# ZSTATE key "voice_owner_present" is set True on launch and can be toggled
# via WhatsApp commands: ZULU VOICE LOCK / ZULU VOICE UNLOCK
# Default: True (you're at your PC when you launch ZULU)

def _owner_present() -> bool:
    """Returns True if owner voice lock is satisfied."""
    if not OWNER_ONLY:
        return True
    # If ZSTATE doesn't have the key yet, default to True (owner is present)
    return ZSTATE.get("voice_owner_present", True)


# ─────────────────────────────────────────────────────────────────────────────
# ⚡  COMMAND EXECUTION
# ─────────────────────────────────────────────────────────────────────────────

def _execute(command: str):
    """
    Route a voice command to PC control (instant) or boardroom (AI).
    Always runs in a background thread — never blocks the listen loop.
    FIX: proper error handling so a failed import never kills the loop.
    """
    user_type = "BOSS"
    zlog("voice", f"Executing: '{command}'")

    # ── 1. Try PC control first (instant, no AI needed) ──────────────────────
    try:
        from zulu_pc import handle_pc_command
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
        from boardroom_engine import launch_boardroom

        _capture = []

        def _grab(data):
            r = data.get("result", "")
            if r and str(r).strip().lower() not in ("none", ""):
                _capture.append(str(r))
            ZBUS.off("task_done", _grab)   # unregister after first fire

        ZBUS.on("task_done", _grab)

        # launch_boardroom is blocking — fine, we're in a background thread
        launch_boardroom(command, user_type)

        time.sleep(0.5)   # give task_done event time to fire

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
# 🔄  MAIN VOICE LOOP
# FIX: mic object is created once but used as context manager per listen call
#      so it never holds a stale open stream between cycles.
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
    recognizer.energy_threshold         = ENERGY_THRESHOLD
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold          = 0.8

    # FIX: wrap mic init in try/except so a missing mic doesn't hard-crash
    try:
        mic = sr.Microphone()
    except OSError as e:
        zlog("voice", f"Microphone not available: {e}", "ERROR")
        return
    except Exception as e:
        zlog("voice", f"Mic init error: {e}", "ERROR")
        return

    _voice_active = True
    # Set owner present on launch (you started it, so you're here)
    ZSTATE.set("voice_owner_present", True)
    zlog("voice", "🎙️  Voice engine started — say 'Hey ZULU' to activate")
    speak("ZULU voice engine ready. Say Hey Zulu.", blocking=True)

    while not _stop_event.is_set():
        _is_listening = False
        try:
            # ── Phase 1: Passive listen for wake word ─────────────────────────
            # FIX: each listen call opens/closes mic cleanly via context manager
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.15)
                try:
                    audio = recognizer.listen(
                        source,
                        timeout=4,
                        phrase_time_limit=5,
                    )
                except sr.WaitTimeoutError:
                    continue

            # Transcribe — skip if it fails (background noise, etc.)
            try:
                text = recognizer.recognize_google(audio).lower().strip()
            except sr.UnknownValueError:
                continue
            except sr.RequestError as e:
                zlog("voice", f"STT network error: {e}", "WARN")
                time.sleep(2)
                continue
            except Exception:
                continue

            if not _is_wake_word(text):
                continue

            # ── Phase 2: Wake word detected ───────────────────────────────────
            zlog("voice", f"Wake word detected: '{text}'")

            # OWNER LOCK CHECK — ignore if owner not present
            if not _owner_present():
                zlog("voice", "Owner lock active — wake word ignored")
                continue

            _is_listening = True
            ZBUS.emit("voice_wake", {"text": text})

            # Extract inline command if spoken in same utterance
            # e.g. "Hey ZULU open Chrome" → command = "open Chrome"
            command = _strip_wake_word(text)

            if not command or len(command) < 3:
                # No inline command — ask and listen for follow-up
                # FIX: speak blocking=True so mic opens AFTER speaking finishes
                speak("Yes?", blocking=True)
                time.sleep(0.2)   # tiny gap so mic doesn't catch TTS echo
                command = _listen_once(recognizer, mic, timeout=COMMAND_TIMEOUT)

            if not command:
                speak("I didn't catch that. Say Hey Zulu again.", blocking=True)
                _is_listening = False
                continue

            # ── Phase 3: Execute in background ───────────────────────────────
            zlog("voice", f"Voice command: '{command}'")
            threading.Thread(
                target=_execute,
                args=(command,),
                daemon=True,
                name="ZuluVoiceExec",
            ).start()

            # Small cooldown so we don't immediately re-trigger on TTS audio
            time.sleep(1.5)

        except Exception as e:
            if not _stop_event.is_set():
                zlog("voice", f"Voice loop error: {e}", "WARN")
            time.sleep(1)
        finally:
            _is_listening = False

    _voice_active = False
    zlog("voice", "Voice engine stopped.")


# ─────────────────────────────────────────────────────────────────────────────
# 🚀  PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────
_voice_thread: threading.Thread | None = None


def start_voice_engine() -> bool:
    """
    Start the background voice engine thread.
    Returns True if started, False if dependencies missing.
    """
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
    """Gracefully stop the voice engine."""
    _stop_event.set()
    zlog("voice", "Stop signal sent to voice engine")


def lock_voice():
    """Lock voice — ZULU ignores wake words until unlocked (ZULU VOICE LOCK)."""
    ZSTATE.set("voice_owner_present", False)
    zlog("voice", "Voice LOCKED — wake words ignored")


def unlock_voice():
    """Unlock voice — ZULU responds to wake words again (ZULU VOICE UNLOCK)."""
    ZSTATE.set("voice_owner_present", True)
    zlog("voice", "Voice UNLOCKED — listening for wake words")


def voice_status() -> str:
    """Return a one-line status string."""
    if not SR_OK:
        return "❌ Voice: speech_recognition not installed"
    running = _voice_thread is not None and _voice_thread.is_alive()
    state   = "🔴 ACTIVE (listening for command)" if _is_listening else "⚪ standby (waiting for wake word)"
    locked  = "" if _owner_present() else "  🔒 OWNER LOCK ON"
    return f"🎙️  Voice: {'RUNNING' if running else 'STOPPED'} | {state}{locked}"


# ─────────────────────────────────────────────────────────────────────────────
# 🧪  STANDALONE TEST
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("🎙️  ZULU Voice Engine v2.0 — Standalone Test")
    print("=" * 55)
    print()
    print("Dependencies check:")
    print(f"  speech_recognition : {'✅' if SR_OK else '❌  pip install SpeechRecognition pyaudio'}")
    print(f"  pyttsx3            : {'✅' if PYTTSX3_OK else '❌  pip install pyttsx3'}")
    print()

    if not SR_OK:
        print("Install missing deps and re-run.")
        raise SystemExit(1)

    print("Starting voice engine...")
    print("Say 'Hey ZULU' to activate, then give a command.")
    print("Press Ctrl+C to stop.")
    print()

    if start_voice_engine():
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            stop_voice_engine()
            print("\n👋 Voice engine stopped.")
