"""Double-clap desktop trigger.

Listens to the default microphone in a background daemon thread and fires a
callback when it hears two claps in quick succession. A clap is a short, loud
amplitude transient, so we look for rising edges above an adaptive threshold
and require two of them inside a short time window.

Dependency: pyaudio (already needed for STT). If it's missing or no input
device is available, the listener disables itself quietly instead of crashing.

Detection is intentionally conservative (adaptive noise floor + re-arm gate +
cooldown) to keep speech and background noise from triggering it, but mic
hardware varies — tune the module constants if it's too eager or too deaf.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading
import time
import webbrowser
from typing import Callable

# audioop was removed in Python 3.13. Fall back to a numpy-based peak so the
# clap listener keeps working after a Python upgrade.
try:
    import audioop  # type: ignore

    def _peak_int16(data: bytes) -> int:
        return audioop.max(data, 2)
except ImportError:  # pragma: no cover - depends on Python version
    try:
        import numpy as _np

        def _peak_int16(data: bytes) -> int:
            if not data:
                return 0
            arr = _np.frombuffer(data, dtype=_np.int16)
            return int(_np.abs(arr).max()) if arr.size else 0
    except ImportError:
        # Pure-Python fallback — no dependencies
        import struct

        def _peak_int16(data: bytes) -> int:
            if not data:
                return 0
            count = len(data) // 2
            vals = struct.unpack(f"<{count}h", data[:count * 2])
            return max(abs(v) for v in vals)

IS_WIN = platform.system() == "Windows"

# ── audio stream ──────────────────────────────────────
_RATE = 44100
_CHUNK = 1024                 # ~23 ms per read at 44.1 kHz
_WIDTH = 2                    # int16

# ── detection tuning ──────────────────────────────────
_PEAK_MIN = 7000             # absolute int16 peak a clap must exceed
_REL_FACTOR = 5.0            # …or this many × the ambient noise floor
_GATE_LOW = 2500             # signal must fall below this to re-arm
_MIN_GAP = 0.08             # min seconds between the two claps
_MAX_GAP = 0.6              # max seconds between the two claps (balanced profile)
_COOLDOWN = 3.0             # min seconds between two *trigger* events
_AMBIENT_EMA = 0.05         # smoothing for the running noise floor


# ── the double-clap macro (hardcoded) ─────────────────
# Two claps: open these two URLs in Chrome, then open WhatsApp via Windows
# Search (no global hotkeys).
MACRO_URLS = [
    "https://kickbacks.ai/me",
    "https://connect.stripe.com/app/express",
]
# The app to open after the tabs (launched through Win+S, not a hotkey).
MACRO_APP = "whatsapp"

# Custom phrase to speak after double clap
CUSTOM_PHRASE = "daddy's Home, i am opening your tabs sir"

_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
]


def _chrome_exe() -> str | None:
    for p in _CHROME_PATHS:
        if os.path.exists(p):
            return p
    return shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("chromium")


def open_in_chrome(url: str) -> bool:
    """Open a URL specifically in Chrome. Returns True on success.

    Falls back: chrome.exe on disk → `start chrome` (App Paths registry) →
    default browser (so the link always opens, even if Chrome is absent).
    """
    exe = _chrome_exe()
    if exe:
        try:
            subprocess.Popen([exe, url])
            return True
        except Exception:  # noqa: BLE001
            pass
    if IS_WIN:
        try:
            subprocess.Popen(f'start chrome "{url}"', shell=True)
            return True
        except Exception:  # noqa: BLE001
            pass
    try:
        webbrowser.open(url)
        return True
    except Exception:  # noqa: BLE001
        return False


def _open_app_via_search(app_name: str) -> bool:
    """Open an app through Windows Search: Win+S, wait 1s, type the name,
    wait 1s, Enter. No global hotkeys."""
    try:
        import pyautogui
    except ImportError:
        return False
    try:
        pyautogui.hotkey("win", "s")
        time.sleep(1.0)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(1.0)
        pyautogui.press("enter")
        return True
    except Exception:  # noqa: BLE001
        return False


def run_macro() -> str:
    """Execute the double-clap macro. Returns a short status string."""
    import threading

    # Speak the custom phrase in a background thread
    def speak_phrase():
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.say(CUSTOM_PHRASE)
            engine.runAndWait()
        except Exception:
            pass

    # Start speaking in background
    threading.Thread(target=speak_phrase, daemon=True).start()

    # Open the tabs
    opened = 0
    for url in MACRO_URLS:
        if open_in_chrome(url):
            opened += 1
        time.sleep(0.4)  # stagger so Chrome batches the tabs cleanly
    # Open WhatsApp via Windows Search (no global hotkey).
    app_ok = _open_app_via_search(MACRO_APP)
    status = f"opened {opened}/{len(MACRO_URLS)} Chrome tab(s)"
    status += f"; opened {MACRO_APP} via search" if app_ok else "; app-open failed (pyautogui missing?)"
    status += f"; speaking: {CUSTOM_PHRASE}"
    return status


class ClapListener:
    def __init__(self, on_double_clap: Callable[[], None]) -> None:
        self._cb = on_double_clap
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> bool:
        """Spawn the listener thread. Returns True if it started."""
        if self._running:
            return True
        try:
            import pyaudio  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            print(f"[clap] disabled — pyaudio unavailable ({exc}).")
            return False
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="jarvis-clap",
        )
        self._thread.start()
        print("[clap] double-clap trigger listening")
        return True

    def stop(self) -> None:
        self._running = False

    def _fire(self) -> None:
        # Run the action off the audio loop so a slow browser launch can't
        # stall clap detection.
        threading.Thread(
            target=self._safe_cb, daemon=True, name="jarvis-clap-action",
        ).start()

    def _safe_cb(self) -> None:
        try:
            self._cb()
        except Exception as exc:  # noqa: BLE001
            print(f"[clap] action failed: {exc}")

    def _loop(self) -> None:
        import pyaudio
        pa = None
        stream = None
        try:
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16, channels=1, rate=_RATE,
                input=True, frames_per_buffer=_CHUNK,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[clap] disabled — couldn't open the mic ({exc}).")
            self._running = False
            if stream is not None:
                try:
                    stream.close()
                except Exception:  # noqa: BLE001
                    pass
            if pa is not None:
                try:
                    pa.terminate()
                except Exception:  # noqa: BLE001
                    pass
            return

        ambient = float(_GATE_LOW)
        armed = True
        pending_first = 0.0     # timestamp of first clap awaiting a partner
        last_fire = 0.0

        try:
            while self._running:
                try:
                    data = stream.read(_CHUNK, exception_on_overflow=False)
                except Exception:  # noqa: BLE001
                    time.sleep(0.05)
                    continue
                peak = _peak_int16(data)
                now = time.time()

                # Track the ambient noise floor while it's quiet.
                if peak < _GATE_LOW:
                    ambient = (1 - _AMBIENT_EMA) * ambient + _AMBIENT_EMA * peak

                thresh = max(_PEAK_MIN, ambient * _REL_FACTOR)

                if armed and peak > thresh:
                    # Clap onset (rising edge above threshold).
                    armed = False
                    if pending_first and _MIN_GAP <= (now - pending_first) <= _MAX_GAP:
                        if now - last_fire > _COOLDOWN:
                            last_fire = now
                            self._fire()
                        pending_first = 0.0
                    else:
                        pending_first = now
                elif not armed and peak < _GATE_LOW:
                    # Signal quieted — ready to detect the next edge.
                    armed = True

                # Forget a lone first clap that never got a partner.
                if pending_first and now - pending_first > _MAX_GAP:
                    pending_first = 0.0
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                pa.terminate()
            except Exception:  # noqa: BLE001
                pass
