"""Long-term memory automations — let JARVIS remember/recall facts across sessions."""
from __future__ import annotations

from .. import facts
from .registry import tool


@tool(
    name="remember_fact",
    description=(
        "Store a durable fact about the user for future sessions "
        "(e.g. 'My sister's birthday is 4 March', 'I use VS Code')."
    ),
    parameters={
        "type": "object",
        "properties": {"fact": {"type": "string"}},
        "required": ["fact"],
    },
)
def remember_fact(fact: str) -> str:
    count = facts.add_fact(fact)
    return f"Got it — I'll remember that. ({count} facts stored)"


@tool(
    name="recall_facts",
    description="Recall stored facts about the user, optionally filtered by a keyword.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Optional keyword filter."}},
    },
)
def recall_facts(query: str = "") -> str:
    items = facts.search_facts(query) if query else [f["text"] for f in facts.all_facts()]
    if not items:
        return "I don't have anything stored on that yet."
    return "Here's what I remember:\n" + "\n".join(f"- {t}" for t in items)


@tool(
    name="forget_fact",
    description="Forget stored facts matching a keyword.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)
def forget_fact(query: str) -> str:
    n = facts.forget(query)
    return f"Removed {n} matching fact(s)." if n else "Nothing matched — nothing removed."
