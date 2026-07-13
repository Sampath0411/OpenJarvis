"""Autonomous scheduler — the "agent daemon".

Runs as a background thread inside server.py (which is already alive as
a Flask app). Every POLL_SECONDS it:
  1. pulls due goals (one-off `pending` + cron `next_run` reached)
  2. runs each through the Agent orchestrator
  3. reports results to Telegram (if bot running + authorized)
  4. avoids overlapping runs of the same goal

Also exposes a manual `run_now(goal_id)` and `tick()` for tests.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from . import goals as _goals
from . import Agent

POLL_SECONDS = 60
_running = False
_thread: threading.Thread | None = None
_lock = threading.Lock()
_busy: set[str] = set()
_telegram_push: Callable[[str], None] | None = None
_brain = None


def set_telegram_push(fn: Callable[[str], None]) -> None:
    global _telegram_push
    _telegram_push = fn


def set_brain(brain) -> None:
    global _brain
    _brain = brain


def _make_agent() -> Agent:
    def reporter(msg: str) -> None:
        if _telegram_push:
            try:
                _telegram_push(msg)
            except Exception:
                pass

    return Agent(
        brain=_brain,
        on_report=reporter,
    )


def tick() -> list[dict[str, Any]]:
    """Run all currently-due goals once. Returns list of run results."""
    due = _goals.due_now()
    results = []
    for g in due:
        gid = g["id"]
        with _lock:
            if gid in _busy:
                continue
            _busy.add(gid)
        try:
            agent = _make_agent()
            res = agent.run_goal(gid)
            results.append({"goal_id": gid, **res})
        except Exception as exc:  # noqa: BLE001
            _goals.log_run(gid, "failed", f"scheduler error: {exc}", 0, 0, 0)
            results.append({"goal_id": gid, "ok": False, "error": str(exc)})
        finally:
            with _lock:
                _busy.discard(gid)
    return results


def run_now(goal_id: str) -> dict[str, Any]:
    agent = _make_agent()
    return agent.run_goal(goal_id)


def _loop() -> None:
    while _running:
        try:
            tick()
        except Exception:  # noqa: BLE001
            pass
        # sleep in small slices so we can stop promptly
        for _ in range(POLL_SECONDS):
            if not _running:
                return
            time.sleep(1)


def start() -> None:
    global _running, _thread
    with _lock:
        if _running:
            return
        _running = True
    _thread = threading.Thread(target=_loop, name="jarvis-agent", daemon=True)
    _thread.start()


def stop() -> None:
    global _running
    with _lock:
        _running = False


def is_running() -> bool:
    return _running


def status() -> dict[str, Any]:
    return {
        "running": _running,
        "due": len(_goals.due_now()),
        "total_goals": _goals.count(),
        "busy": list(_busy),
    }
