"""Long-term memory — a simple JSON facts store that survives across sessions."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

FACTS_FILE = Path.home() / ".jarvis" / "facts.json"


def _load() -> list[dict]:
    if not FACTS_FILE.exists():
        return []
    try:
        return json.loads(FACTS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(items: list[dict]) -> None:
    FACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    FACTS_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def add_fact(text: str) -> int:
    items = _load()
    # avoid exact duplicates
    if any(f["text"].strip().lower() == text.strip().lower() for f in items):
        return len(items)
    items.append({"text": text.strip(), "ts": datetime.now().isoformat(timespec="seconds")})
    _save(items)
    return len(items)


def all_facts() -> list[dict]:
    return _load()


def facts_text() -> str:
    """Bulleted string for injecting into the system prompt."""
    return "\n".join(f"- {f['text']}" for f in _load())


def search_facts(query: str) -> list[str]:
    q = query.lower()
    return [f["text"] for f in _load() if q in f["text"].lower()]


def forget(query: str) -> int:
    """Remove facts matching a substring. Returns number removed."""
    items = _load()
    q = query.lower()
    kept = [f for f in items if q not in f["text"].lower()]
    removed = len(items) - len(kept)
    if removed:
        _save(kept)
    return removed


def clear_all() -> None:
    _save([])
