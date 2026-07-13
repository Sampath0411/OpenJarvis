"""Owner identity — replace with YOUR details.

This is the baked-in identity your JARVIS assistant knows about you.
Edit the OWNER dict below, then restart the server.
"""
from __future__ import annotations

from typing import Any

OWNER: dict[str, Any] = {
    "name": "Your Name",
    "preferred_name": "Your Name",
    "email": "you@example.com",
    "phone": "+xx-xxxxxxxxxx",

    "education": (
        "Your education details (e.g., 'B.Tech CSE at XYZ University')."
    ),

    "laptop": (
        "Your laptop specs (e.g., 'Dell XPS running Windows 11')."
    ),

    "interests": [
        "your interests, e.g. coding, photography, music",
    ],

    "personality_notes": (
        "A short note about yourself so JARVIS knows how to talk to you."
    ),

    "active_projects": [
        {
            "name": "Project 1",
            "desc": "Short description.",
        },
        {
            "name": "Project 2",
            "desc": "Short description.",
        },
    ],

    "socials": {
        "platform": "@handle",
    },

    "editing_tool": "",

    "goals": [
        "Your goals (e.g., learning, building, internships).",
    ],
}


def owner_text() -> str:
    """Plain-text block for injecting into JARVIS's system prompt."""
    p = OWNER
    projects = "\n".join(
        f"  - {proj['name']} - {proj['desc']}"
        for proj in p["active_projects"]
    )
    socials = "\n".join(f"  - {k}: {v}" for k, v in p["socials"].items())
    goals = "\n".join(f"  - {g}" for g in p["goals"])
    interests = "\n".join(f"  - {i}" for i in p["interests"])

    return (
        f"Name: {p['name']} (preferred: {p['preferred_name']})\n"
        f"Email: {p['email']}  |  Phone: {p['phone']}\n"
        f"Education: {p['education']}\n"
        f"Laptop: {p['laptop']}\n"
        f"\nInterests:\n{interests}\n"
        f"\nPersonality notes:\n  {p['personality_notes']}\n"
        f"\nActive projects:\n{projects}\n"
        f"\nSocial handles:\n{socials}\n"
        f"Editing tool: {p['editing_tool']}\n"
        f"\nCurrent goals:\n{goals}"
    )


def owner_dict() -> dict:
    return OWNER
