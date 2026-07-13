"""Voice I/O — speech-to-text (mic) and text-to-speech, both optional.

Everything degrades gracefully: if a dependency or device is missing, JARVIS
falls back to typed input / printed output instead of crashing.
"""
from __future__ import annotations

from config import CONFIG


class Voice:
    def __init__(self) -> None:
        self.tts_engine = None
        self.recognizer = None
        self.mic = None
        self._init_tts()
        self._init_stt()

    # ── text to speech ───────────────────────────────
    def _init_tts(self) -> None:
        if not CONFIG.voice_enabled:
            return
        try:
            import pyttsx3

            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty("rate", 180)
            # Prefer a clearer/male voice if available.
            for v in self.tts_engine.getProperty("voices"):
                if any(k in v.name.lower() for k in ("david", "mark", "daniel", "alex")):
                    self.tts_engine.setProperty("voice", v.id)
                    break
        except Exception as exc:  # noqa: BLE001
            print(f"[voice] TTS unavailable ({exc}); using text output.")
            self.tts_engine = None

    def speak(self, text: str) -> None:
        if not text:
            return
        if self.tts_engine:
            try:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
                return
            except Exception:  # noqa: BLE001
                pass  # fall through to print
        # No TTS engine (or it just failed) — print instead, as the module
        # docstring promises ("printed output instead of crashing").
        print(f"[JARVIS] {text}")

    # ── speech to text ───────────────────────────────
    def _init_stt(self) -> None:
        if not CONFIG.stt_enabled:
            return
        try:
            import speech_recognition as sr

            self.recognizer = sr.Recognizer()
            self.recognizer.pause_threshold = 0.8
            self.mic = sr.Microphone()
            with self.mic as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.6)
        except Exception as exc:  # noqa: BLE001
            print(f"[voice] Microphone/STT unavailable ({exc}); using typed input.")
            self.recognizer = None
            self.mic = None

    @property
    def can_listen(self) -> bool:
        return self.recognizer is not None and self.mic is not None

    def listen(self, timeout: int = 8, phrase_limit: int = 15) -> str | None:
        """Capture one utterance and return recognized text, or None on failure."""
        if not self.can_listen:
            return None
        import speech_recognition as sr

        try:
            with self.mic as source:
                audio = self.recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=phrase_limit
                )
        except sr.WaitTimeoutError:
            return None
        except Exception:  # noqa: BLE001
            return None

        try:
            return self.recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return None
        except sr.RequestError:
            # No internet for Google STT — try offline whisper if present.
            try:
                return self.recognizer.recognize_whisper(audio, model="base")
            except Exception:  # noqa: BLE001
                return None
