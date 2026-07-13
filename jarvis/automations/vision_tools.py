"""Screen vision tool — see what's on the user's screen.

The real implementation lives on `Brain.see_screen`, which needs the configured
vision models and the requests session. This module exposes a tool entry in the
registry; `Brain.bind_see_screen` replaces the placeholder function with the
real one at startup.
"""
from __future__ import annotations

from .registry import tool


def _placeholder(question: str = "") -> str:
    raise NotImplementedError(
        "see_screen is wired in server.py / assistant.py via Brain.bind_see_screen"
    )


@tool(
    name="see_screen",
    description=(
        "Take a screenshot of the current screen, send it to the vision model, "
        "and return a description. Use when the user asks 'what's on my screen', "
        "'what does this error say', 'look at this', etc."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "What to look for or describe."},
        },
    },
)
def see_screen(question: str = "") -> str:
    return _placeholder(question)
