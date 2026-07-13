"""Notification automations — read this PC's Windows notifications on demand."""
from __future__ import annotations

from .registry import tool
from .. import notifications


@tool(
    name="read_notifications",
    description=(
        "Read this PC's recent Windows notifications (app, title, text, time). "
        "Use when the user asks what notifications they have, or to check for "
        "messages/alerts from apps like WhatsApp, Gmail, or Teams."
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer",
                       "description": "How many recent notifications to return (default 10).",
                       "minimum": 1, "maximum": 50},
        },
    },
)
def read_notifications(limit: int = 10) -> str:
    items = notifications.read_notifications(limit=limit)
    if not items:
        return ("No readable notifications found. (Windows may have cleared them, "
                "or none have text content.)")
    lines = [f"Your {len(items)} most recent notification(s):"]
    for n in items:
        lines.append(f"• {notifications.format_line(n)}")
    return "\n".join(lines)
