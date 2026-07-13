"""Utility automations — time, date, reminders, notes, simple math."""
from __future__ import annotations

import threading
import time as _time
from datetime import datetime
from pathlib import Path

from .registry import tool

NOTES_FILE = Path.home() / "jarvis_workspace" / "notes.txt"


@tool(
    name="get_datetime",
    description="Get the current date and time.",
)
def get_datetime() -> str:
    now = datetime.now()
    return now.strftime("%A, %d %B %Y — %I:%M %p")


@tool(
    name="add_note",
    description="Save a quick note for the user to a persistent notes file.",
    parameters={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
def add_note(text: str) -> str:
    NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with NOTES_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {text}\n")
    return "Noted."


@tool(
    name="read_notes",
    description="Read back all saved notes.",
)
def read_notes() -> str:
    if not NOTES_FILE.exists():
        return "You have no notes yet."
    return NOTES_FILE.read_text(encoding="utf-8")[:3000]


@tool(
    name="set_reminder",
    description="Set a reminder that prints/speaks after N seconds (non-blocking).",
    parameters={
        "type": "object",
        "properties": {
            "seconds": {"type": "integer", "description": "Delay in seconds."},
            "message": {"type": "string"},
        },
        "required": ["seconds", "message"],
    },
)
def set_reminder(seconds: int, message: str) -> str:
    def _fire() -> None:
        _time.sleep(max(1, seconds))
        print(f"\n\a[REMINDER] {message}\n")

    threading.Thread(target=_fire, daemon=True).start()
    mins = seconds / 60
    when = f"{mins:.0f} min" if mins >= 1 else f"{seconds} sec"
    return f"Reminder set for {when} from now: {message}"


@tool(
    name="calculate",
    description="Evaluate a basic arithmetic expression (e.g. '12*7 + 3').",
    parameters={
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    },
)
def calculate(expression: str) -> str:
    # Use simpleeval — it allows arithmetic, comparison, and a small whitelist
    # of safe functions, but blocks __import__, attribute access, etc.
    try:
        from simpleeval import SimpleEval
    except ImportError:
        return "simpleeval is not installed. Run: pip install simpleeval"
    se = SimpleEval()
    try:
        return str(se.eval(expression))
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't evaluate: {exc}"
