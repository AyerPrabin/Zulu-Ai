# zulu_voice.py — ZULU Voice Engine v1.0
import re
import time
import queue
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
# Wake words — Google STT sometimes mishears "ZULU" as these variants
WAKE_WORDS = [
    "hey zulu", "hey julia", "hey julio", "hey juliet",
    "hey zoo", "zulu", "hey sue",
]

# How long to wait for a command after wake word (seconds)
COMMAND_TIMEOUT = 8

# How loud the mic has to be to count as speech (raise if too sensitive)
ENERGY_THRESHOLD = 350

# Speak replies aloud?  Set False to only show in console.
TTS_ENABLED = True

# Speech rate (words per minute). pyttsx3 default is ~200, 170 sounds natural.
TTS_RATE = 170

# Voice reply max length in chars before truncating for speech
TTS_MAX_CHARS = 400


# ─────────────────────────────────────────────────────────────────────────────
# 🔊  TEXT-TO-SPEECH
# ─────────────────────────────────────────────────────────────────────────────
_tts_engine = None
_tts_lock   = threading.Lock()


def _init_tts():
    global _tts_engine
    if not PYTTSX3_OK:
        zlog("voice", "pyttsx3 not installed — TTS disabled (run: pip install pyttsx3)", "WARN")
        return
    try:
        _tts_engine = pyttsx3.init()
        _tts_engine.setProperty("rate",   TTS_RATE)
        _tts_engine.setProperty("volume", 0.92)
        # Prefer Microsoft Zira (female) or David (male) if available
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
    """Strip emojis, markdown, URLs and shorten for TTS."""
    # Remove emoji / non-ASCII symbols
    clean = re.sub(r'[^\x00-\x7F]+', '', text)
    # Remove markdown
    clean = re.sub(r'[*_`#\[\]\(\)~]', '', clean)
    # Remove URLs
    clean = re.sub(r'https?://\S+', 'link', clean)
    # Collapse whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()
    # Truncate
    if len(clean) > TTS_MAX_CHARS:
        clean = clean[:TTS_MAX_CHARS] + "."
    return clean


def speak(text: str, blocking: bool = False):
    """
    Speak text aloud.
    blocking=True → wait until speech finishes (use for confirmations).
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
            # Fallback: PowerShell SAPI (Windows built-in, always available)
            try:
                import subprocess
                ps = (
                    f'Add-Type -AssemblyName System.Speech; '
                    f'$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
                    f'$s.Rate = 1; '
                    f'$s.Speak("{clean.replace(chr(34), chr(39))}");'
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
            remainder = tl[len(w):].strip(" ,.")
            # Restore original case for the remainder
            offset = text.lower().find(w) + len(w)
            return text[offset:].strip(" ,.")
    return text


def _listen(recognizer, mic, timeout: int = COMMAND_TIMEOUT) -> str:
    """
    Listen once and return transcribed text.
    Returns '' on silence / timeout / unintelligible audio.
    """
    try:
        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.2)
            audio = recognizer.listen(
                source,
                timeout=timeout,
                phrase_time_limit=15,
            )
        result = recognizer.recognize_google(audio).strip()
        zlog("voice", f"STT heard: '{result}'")
        return result
    except sr.WaitTimeoutError:
        return ""
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        zlog("voice", f"STT network error: {e}", "WARN")
        return ""
    except Exception as e:
        zlog("voice", f"STT error: {e}", "WARN")
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# ⚡  COMMAND EXECUTION
# ─────────────────────────────────────────────────────────────────────────────

def _execute(command: str):
    """
    Route a voice command to PC control (instant) or boardroom (AI).
    This always runs in a background thread — never blocks the listen loop.
    """
    user_type = "BOSS"

    try:
        from zulu_pc import handle_pc_command
        handled, response = handle_pc_command(command, user_type)
        if handled:
            zlog("voice", f"PC command: {response[:60]}")
            speak(response)
            return
    except ImportError:
        zlog("voice", "zulu_pc not found — only AI commands available", "WARN")

    # ── AI path via boardroom ─────────────────────────────────────────────────
    speak("On it.")

    try:
        from boardroom_engine import launch_boardroom

        # Capture the boardroom reply so we can also speak it
        _capture = []

        def _grab(data):
            r = data.get("result", "")
            if r and str(r).strip().lower() not in ("none", ""):
                _capture.append(str(r))
            # 🔧 FIX: Unregister listener after first fire to prevent accumulation
            ZBUS.off("task_done", _grab)

        ZBUS.on("task_done", _grab)

        # launch_boardroom is blocking — run it here (we're already in a thread)
        launch_boardroom(command, user_type)

        time.sleep(0.3)   # let task_done fire

        if _capture:
            speak(_capture[-1])
        else:
            speak("Done.")

    except Exception as e:
        zlog("voice", f"Boardroom error via voice: {e}", "ERROR")
        speak("Something went wrong.")


# ─────────────────────────────────────────────────────────────────────────────
# 🔄  MAIN VOICE LOOP
# ─────────────────────────────────────────────────────────────────────────────
_voice_active   = False   # True while loop is running
_is_listening   = False   # True during active command capture
_stop_event     = threading.Event()


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
    recognizer.energy_threshold        = ENERGY_THRESHOLD
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold         = 0.8

    try:
        mic = sr.Microphone()
    except OSError as e:
        zlog("voice", f"Microphone not available: {e}", "ERROR")
        return

    _voice_active = True
    zlog("voice", "🎙️  Voice engine started — say 'Hey ZULU' to activate")
    speak("ZULU voice engine ready. Say Hey Zulu.")

    while not _stop_event.is_set():
        try:
            # ── Phase 1: Passive background listen for wake word ────────────
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.2)
                try:
                    audio = recognizer.listen(
                        source,
                        timeout=4,
                        phrase_time_limit=4,
                    )
                except sr.WaitTimeoutError:
                    continue

            # Fast path — don't transcribe if audio is too short (< 0.5s)
            try:
                text = recognizer.recognize_google(audio).lower().strip()
            except Exception:
                continue

            if not _is_wake_word(text):
                continue

            # ── Phase 2: Wake word detected ─────────────────────────────────
            zlog("voice", f"Wake word detected in: '{text}'")
            _is_listening = True
            ZBUS.emit("voice_wake", {"text": text})

            # Extract inline command if any ("Hey ZULU open Chrome")
            command = _strip_wake_word(text)

            if not command or len(command) < 3:
                # No inline command — ask and listen for second utterance
                speak("Yes?")
                command = _listen(recognizer, mic, timeout=COMMAND_TIMEOUT)

            if not command:
                speak("I didn't catch that. Say Hey Zulu again.")
                _is_listening = False
                continue

            # ── Phase 3: Execute ─────────────────────────────────────────────
            zlog("voice", f"Executing voice command: '{command}'")
            threading.Thread(
                target=_execute,
                args=(command,),
                daemon=True,
                name="ZuluVoiceExec",
            ).start()

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
    Returns True if started successfully, False if dependencies missing.
    """
    global _voice_thread

    if not SR_OK:
        print("❌ speech_recognition not installed.")
        print("   Run: pip install SpeechRecognition pyaudio")
        print("   If pyaudio fails on Windows: pip install pipwin && pipwin install pyaudio")
        return False

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


def voice_status() -> str:
    """Return a one-line status string (for ZULU VOICE STATUS command)."""
    if not SR_OK:
        return "❌ Voice: speech_recognition not installed"
    running = _voice_thread is not None and _voice_thread.is_alive()
    state   = "🔴 ACTIVE (listening)" if _is_listening else "⚪ standby"
    return f"🎙️  Voice engine: {'RUNNING' if running else 'STOPPED'} | {state}"


# ─────────────────────────────────────────────────────────────────────────────
# 🧪  STANDALONE TEST
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("🎙️  ZULU Voice Engine v1.0 — Standalone Test")
    print("=" * 55)
    print()
    print("Dependencies check:")
    print(f"  speech_recognition : {'✅' if SR_OK else '❌  pip install SpeechRecognition pyaudio'}")
    print(f"  pyttsx3            : {'✅' if PYTTSX3_OK else '❌  pip install pyttsx3'}")
    print()

    if not SR_OK:
        print("Install missing dependencies and re-run.")
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
