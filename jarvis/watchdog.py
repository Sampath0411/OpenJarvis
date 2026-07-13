"""System watchdog — background monitor that raises alerts for battery/CPU.

Runs in a daemon thread and keeps a small list of recent alerts the web UI polls.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime

from .telegram_alerts import HUB

# Severity → icon for the alert card shown in the HUD and pushed to Telegram.
_LEVEL_ICON = {"warn": "🟡", "crit": "🔴"}


class Watchdog:
    def __init__(self, interval: int = 20) -> None:
        self.interval = interval
        self.alerts: deque[dict] = deque(maxlen=20)
        self._seen: set[str] = set()          # de-dupe within a session
        self._thread: threading.Thread | None = None
        self._running = False
        # Guards self.alerts against the drain()/_emit() race.
        self._lock = threading.Lock()

    def start(self) -> None:
        try:
            import psutil  # noqa: F401
        except ImportError:
            return  # silently disabled if psutil missing
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the background loop to exit on the next iteration."""
        self._running = False

    def is_alive(self) -> bool:
        """True if the watchdog thread is currently running."""
        return self._running and self._thread is not None and self._thread.is_alive()

    def _emit(self, key: str, level: str, message: str) -> None:
        if key in self._seen:
            return
        self._seen.add(key)
        with self._lock:
            self.alerts.append(
                {"level": level, "message": message,
                 "ts": datetime.now().strftime("%H:%M")}
            )
        # Fan out to every subscriber (Telegram push, future channels) at
        # emit time — separate from the HUD's destructive drain(), so the two
        # consumers no longer steal alerts from each other.
        try:
            icon = _LEVEL_ICON.get(level, "🔵")
            HUB.broadcast(f"{icon} {message}")
        except Exception:  # noqa: BLE001
            pass

    def _clear_seen(self, key: str) -> None:
        self._seen.discard(key)

    def push(self, message: str, level: str = "info") -> None:
        """Inject an external alert (e.g. a PC notification) into the same
        stream the watchdog uses — lands in the HUD/GUI footer via drain()
        and is pushed to Telegram via the AlertHub. No de-dupe: the caller
        owns uniqueness."""
        with self._lock:
            self.alerts.append(
                {"level": level, "message": message,
                 "ts": datetime.now().strftime("%H:%M")}
            )
        try:
            HUB.broadcast(message)
        except Exception:  # noqa: BLE001
            pass

    def _loop(self) -> None:
        import psutil

        while self._running:
            try:
                # battery
                batt = getattr(psutil, "sensors_battery", lambda: None)()
                if batt is not None:
                    if not batt.power_plugged and batt.percent <= 20:
                        self._emit("batt_low", "warn", f"Battery low: {batt.percent:.0f}%. Plug in soon, sir.")
                    else:
                        self._clear_seen("batt_low")
                    if not batt.power_plugged and batt.percent <= 10:
                        self._emit("batt_crit", "crit", f"Battery critical: {batt.percent:.0f}%!")
                    else:
                        self._clear_seen("batt_crit")

                # RAM (only fires once, never clears — user can see CPU/RAM in sidebar UI)
                mem = psutil.virtual_memory()
                if mem.percent >= 90:
                    self._emit("ram_high", "warn", f"Memory almost full: {mem.percent:.0f}%.")
                elif mem.percent < 80:
                    self._clear_seen("ram_high")
            except Exception:  # noqa: BLE001
                pass
            time.sleep(self.interval)

    def drain(self) -> list[dict]:
        """Return and clear pending alerts (called by the UI poll).

        Atomic under the lock so an alert appended between the read and the
        clear isn't silently dropped.
        """
        with self._lock:
            out = list(self.alerts)
            self.alerts.clear()
        return out


WATCHDOG = Watchdog()
