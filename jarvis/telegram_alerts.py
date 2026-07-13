"""AlertHub — tiny pub-sub for proactive notifications.

Decouples producers (watchdog, tool dispatcher) from consumers (Telegram bot,
web UI, future push channels) so threads don't block each other.
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Callable


class AlertHub:
    def __init__(self, maxlen: int = 50) -> None:
        self._subscribers: list[Callable[[str], None]] = []
        self._queue: deque[str] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def subscribe(self, fn: Callable[[str], None]) -> Callable[[], None]:
        """Register a callback for live pushes. Returns an unsubscribe fn."""
        with self._lock:
            self._subscribers.append(fn)

        def _unsub() -> None:
            with self._lock:
                if fn in self._subscribers:
                    self._subscribers.remove(fn)
        return _unsub

    def broadcast(self, text: str) -> None:
        """Queue an alert and notify all live subscribers."""
        with self._lock:
            self._queue.append(text)
            subs = list(self._subscribers)
        for fn in subs:
            try:
                fn(text)
            except Exception:  # noqa: BLE001
                # A misbehaving subscriber must not break the others.
                pass

    def drain(self) -> list[str]:
        """Return and clear the queued alerts (for polling consumers)."""
        with self._lock:
            out = list(self._queue)
            self._queue.clear()
        return out

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


HUB = AlertHub()
