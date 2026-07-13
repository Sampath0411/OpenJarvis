"""Lightweight RAG — search & read your own text files (notes, resume, code).

Deliberately dependency-free (no vector DB) to stay light on a low-spec machine:
it does a fast keyword scan over a few safe folders and returns matching snippets
the model can summarise.
"""
from __future__ import annotations

from pathlib import Path

from .registry import tool

HOME = Path.home()
# Folders JARVIS is allowed to read from.
SAFE_ROOTS = [
    HOME / "jarvis_workspace",
    HOME / "Documents",
    HOME / "Desktop",
    HOME / "Downloads",
]
TEXT_EXT = {".txt", ".md", ".py", ".json", ".csv", ".log", ".html", ".js", ".css", ".ts"}
MAX_FILE_BYTES = 200_000


def _iter_files():
    for root in SAFE_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in TEXT_EXT:
                try:
                    if p.stat().st_size <= MAX_FILE_BYTES:
                        yield p
                except OSError:
                    continue


@tool(
    name="search_files",
    description=(
        "Search your text files (workspace, Documents, Desktop, Downloads) for a keyword and "
        "return matching snippets. Use for 'summarize my notes', 'find in my resume', etc."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 6},
        },
        "required": ["query"],
    },
)
def search_files(query: str, max_results: int = 6) -> str:
    q = query.lower()
    hits: list[str] = []
    for p in _iter_files():
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        low = text.lower()
        idx = low.find(q)
        if idx != -1:
            start = max(0, idx - 120)
            snippet = text[start : idx + 200].replace("\n", " ").strip()
            hits.append(f"📄 {p.name} ({p.parent}):\n…{snippet}…")
            if len(hits) >= max_results:
                break
    if not hits:
        return f"No files matched '{query}'."
    return "\n\n".join(hits)


@tool(
    name="read_document",
    description="Read a text file by name/partial name from your safe folders.",
    parameters={
        "type": "object",
        "properties": {"filename": {"type": "string"}},
        "required": ["filename"],
    },
)
def read_document(filename: str) -> str:
    needle = filename.lower()
    for p in _iter_files():
        if needle in p.name.lower():
            try:
                return f"📄 {p}\n\n" + p.read_text(encoding="utf-8", errors="ignore")[:4000]
            except OSError as exc:
                return f"Couldn't read {p.name}: {exc}"
    return f"No file named like '{filename}' found in your safe folders."
