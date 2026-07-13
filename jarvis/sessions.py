"""Session summary store — keeps one-paragraph notes about past conversations.

When a conversation is reset (or the rolling window drops old turns), we ask
the model to summarize what was discussed and store it here. The recall module
uses these summaries to inject relevant past context into new conversations.

Persists to ~/jarvis/sessions.json as a list of {ts, summary, keywords?}.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

SESSIONS_FILE = Path.home() / ".jarvis" / "sessions.json"
STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "in", "on", "at", "by", "for", "with", "as", "i", "you",
    "we", "they", "he", "she", "it", "this", "that", "and", "or", "but",
    "if", "then", "so", "do", "did", "does", "have", "has", "had", "can",
    "could", "would", "should", "will", "shall", "may", "might", "must",
    "not", "no", "yes", "ok", "okay", "thanks", "thank", "please", "sir",
}


def _load() -> list[dict]:
    if not SESSIONS_FILE.exists():
        return []
    try:
        return json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(items: list[dict]) -> None:
    SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSIONS_FILE.write_text(
        json.dumps(items, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _keywords(text: str, k: int = 8) -> list[str]:
    """Cheap keyword extraction for retrieval."""
    words = re.findall(r"[a-z]{3,}", text.lower())
    seen: set[str] = set()
    out: list[str] = []
    for w in words:
        if w in STOPWORDS or w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= k:
            break
    return out


def add_summary(summary: str) -> dict:
    """Store a session summary. Returns the saved entry."""
    items = _load()
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "summary": summary.strip(),
        "keywords": _keywords(summary),
    }
    items.append(entry)
    # Cap at 100 entries to avoid unbounded growth.
    if len(items) > 100:
        items = items[-100:]
    _save(items)
    return entry


def all_summaries() -> list[dict]:
    """Return all session summaries, oldest first."""
    return _load()


def search(query: str, k: int = 3) -> list[dict]:
    """Return the k most relevant session summaries for a query.

    Scoring: count of overlapping keywords (case-insensitive). Ties broken by recency.
    """
    items = _load()
    if not items:
        return []
    q_words = set(re.findall(r"[a-z]{3,}", query.lower())) - STOPWORDS
    if not q_words:
        # No useful words → return most recent k.
        return items[-k:][::-1]

    scored: list[tuple[int, int, dict]] = []
    for i, entry in enumerate(items):
        entry_words = set(entry.get("keywords", [])) | set(
            re.findall(r"[a-z]{3,}", entry.get("summary", "").lower())
        )
        overlap = len(q_words & entry_words)
        if overlap > 0:
            # higher index = more recent; weight recency slightly
            scored.append((overlap, i, entry))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [entry for _, _, entry in scored[:k]]


def format_for_prompt(entries: Iterable[dict]) -> str:
    """Format a list of session entries for the system prompt."""
    entries = list(entries)
    if not entries:
        return ""
    lines = ["Past conversations you may recall:"]
    for e in entries:
        lines.append(f"- [{e.get('ts', '?')}] {e.get('summary', '')}")
    return "\n".join(lines)
