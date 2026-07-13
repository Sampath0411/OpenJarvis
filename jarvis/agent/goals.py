"""Persistent goal store for the JARVIS agent.

Goals live in ~/.jarvis/goals.json so they survive restarts and can be
introspected / created from the HUD, Telegram, or CLI.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

JARVIS_DIR = Path.home() / ".jarvis"
GOALS_PATH = JARVIS_DIR / "goals.json"

STATUS = ("pending", "running", "done", "failed", "paused")

_lock = threading.Lock()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _next_from_cron(cron: str | None) -> str | None:
    """Best-effort next-run calc. Supports '*/N * * * *' (every N min)
    and 'N * * * *' (every hour at minute N). Falls back to +30m."""
    if not cron:
        return None
    try:
        parts = cron.split()
        if len(parts) == 5 and parts[0].startswith("*/"):
            mins = int(parts[0][2:])
            nxt = datetime.now() + timedelta(minutes=mins)
            return nxt.isoformat(timespec="seconds")
    except Exception:
        pass
    return (datetime.now() + timedelta(minutes=30)).isoformat(timespec="seconds")


def _load() -> list[dict[str, Any]]:
    if not GOALS_PATH.exists():
        return []
    try:
        return json.loads(GOALS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(goals: list[dict[str, Any]]) -> None:
    JARVIS_DIR.mkdir(parents=True, exist_ok=True)
    GOALS_PATH.write_text(
        json.dumps(goals, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def create(
    title: str,
    cron: str | None = None,
    priority: int = 3,
    max_retries: int = 2,
    steps: list[dict] | None = None,
) -> dict[str, Any]:
    """Create a goal. If `steps` provided, goal is pre-planned."""
    goal: dict[str, Any] = {
        "id": "g_" + uuid.uuid4().hex[:8],
        "title": title,
        "status": "pending",
        "priority": max(1, min(5, priority)),
        "cron": cron,
        "max_retries": max_retries,
        "steps": steps or [],
        "created_at": _now(),
        "last_run": None,
        "next_run": _now() if not cron else _next_from_cron(cron),
        "history": [],
    }
    with _lock:
        goals = _load()
        goals.append(goal)
        _save(goals)
    return goal


def list_all() -> list[dict[str, Any]]:
    with _lock:
        return _load()


def get(goal_id: str) -> dict[str, Any] | None:
    with _lock:
        for g in _load():
            if g["id"] == goal_id:
                return g
    return None


def update(goal_id: str, **fields) -> dict[str, Any] | None:
    with _lock:
        goals = _load()
        for g in goals:
            if g["id"] == goal_id:
                g.update(fields)
                _save(goals)
                return g
    return None


def set_steps(goal_id: str, steps: list[dict]) -> dict[str, Any] | None:
    return update(goal_id, steps=steps, status="pending")


def set_status(goal_id: str, status: str) -> dict[str, Any] | None:
    if status not in STATUS:
        raise ValueError(f"bad status {status}")
    extra = {}
    if status == "done":
        # Get the actual goal to check if it's a cron goal (the old code
        # checked `not status == "cron"` which always evaluated True since
        # status is "done", never "cron" — that bug broke cron re-runs).
        goal = get(goal_id)
        if goal is None:
            return None
        if not goal.get("cron"):
            # one-off goals: clear next_run so they don't re-run
            extra["next_run"] = None
    return update(goal_id, status=status, **extra)


def log_run(
    goal_id: str,
    status: str,
    summary: str,
    steps_done: int,
    steps_total: int,
    seconds: float,
) -> None:
    with _lock:
        goals = _load()
        for g in goals:
            if g["id"] == goal_id:
                g["last_run"] = _now()
                g["history"].append(
                    {
                        "ts": _now(),
                        "status": status,
                        "summary": summary,
                        "steps_done": steps_done,
                        "steps_total": steps_total,
                        "seconds": round(seconds, 1),
                    }
                )
                # cap history to last 20 entries
                g["history"] = g["history"][-20:]
                if g.get("cron"):
                    g["next_run"] = _next_from_cron(g["cron"])
                _save(goals)
                return


def remove(goal_id: str) -> bool:
    with _lock:
        goals = _load()
        new = [g for g in goals if g["id"] != goal_id]
        if len(new) != len(goals):
            _save(new)
            return True
    return False


def due_now() -> list[dict[str, Any]]:
    """Return goals whose next_run <= now and aren't paused/done."""
    now = datetime.now()
    out = []
    with _lock:
        for g in _load():
            if g["status"] in ("paused", "running"):
                continue
            nr = g.get("next_run")
            if not nr:
                # one-off pending goal
                if g["status"] == "pending":
                    out.append(g)
                continue
            try:
                if datetime.fromisoformat(nr) <= now:
                    out.append(g)
            except Exception:
                continue
    # sort by priority (higher first)
    out.sort(key=lambda g: g.get("priority", 3), reverse=True)
    return out


def count() -> int:
    with _lock:
        return len(_load())
