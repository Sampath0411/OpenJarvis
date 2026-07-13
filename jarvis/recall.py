"""Hybrid recall — combine long-term facts and relevant past sessions.

Called by brain.py when the user query looks like a recall request
("do you remember", "what did we discuss", "last time I..."). The result
is injected as a system message into the next model request.
"""
from __future__ import annotations

import re

from . import facts, sessions

RECALL_TRIGGERS = re.compile(
    r"\b("
    r"remember|recall|forgot|forget|"
    r"last time|earlier|yesterday|previously|before|"
    r"what did we|we discussed|we talked|"
    r"do you know|"
    r"my (?:name|birthday|sister|brother|mom|dad|akka|friend|project|resume)|"
    r"i (?:told|said|mentioned)"
    r")\b",
    re.IGNORECASE,
)


def is_recall_query(text: str) -> bool:
    """Return True if the user is asking JARVIS to recall something."""
    return bool(RECALL_TRIGGERS.search(text or ""))


def build_context(query: str, k_sessions: int = 3) -> str:
    """Build a recall context block for the system prompt."""
    parts: list[str] = []

    # Long-term facts (always included — they're cheap and useful).
    facts_text = facts.facts_text()
    if facts_text.strip():
        parts.append("Long-term facts about the user:\n" + facts_text)

    # Past sessions (only if query looks like a recall OR we always include top-k for context).
    relevant = sessions.search(query, k=k_sessions) if query else sessions.all_summaries()[-k_sessions:]
    if relevant:
        parts.append(sessions.format_for_prompt(relevant))

    return "\n\n".join(parts)


def has_context(text: str) -> bool:
    """True if there is anything meaningful to recall."""
    return bool(facts.all_facts() or sessions.all_summaries())
