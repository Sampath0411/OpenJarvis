"""Conversation memory — rolling window, disk persistence, recall injection, and daily logging.

Holds:
- A rolling window of the last N turns.
- A pending-calls registry for tools that need user approval before execution.
- A hook for injecting recall context (long-term facts + past session summaries)
  into the system prompt when the user query looks like a recall.
- Daily conversation logging to a dated file for persistent history.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from . import recall

HISTORY_DIR = Path.home() / ".jarvis"
HISTORY_FILE = HISTORY_DIR / "history.json"
# Daily conversation logs directory
DAILY_LOGS_DIR = HISTORY_DIR / "daily_logs"


class Memory:
    def __init__(self, system_prompt: str, max_turns: int = 20) -> None:
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        # Tools called by the model that need user approval before dispatch.
        # Maps call_id -> {name, args, raw_assistant_msg}
        self._pending: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    # ── system prompt ────────────────────────────────
    def refresh_system_prompt(self, base: str) -> None:
        """Update message[0] with a new base system prompt (e.g. after persona change)."""
        self.system_prompt = base
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = base

    # ── message ops ──────────────────────────────────
    def add(self, role: str, content: str | None = None, **extra: Any) -> None:
        msg: dict[str, Any] = {"role": role}
        if content is not None:
            msg["content"] = content
        msg.update(extra)
        with self._lock:
            self.messages.append(msg)
            self._trim_locked()
            # Log to daily file
            if content:
                self.log_daily(role, content)

    def add_raw(self, msg: dict[str, Any]) -> None:
        with self._lock:
            self.messages.append(msg)
            self._trim_locked()
            # Log to daily file if it has content
            if msg.get("content") and msg.get("role"):
                self.log_daily(msg["role"], msg["content"])

    def add_with_recall(self, role: str, content: str, base_prompt: str) -> None:
        """Add a user message and, if the query triggers recall, inject context
        into the system prompt."""
        msg: dict[str, Any] = {"role": role, "content": content}
        with self._lock:
            # Recall context is valid only for the turn that triggered it.
            # Reset the system prompt to the clean base every turn first, so
            # stale context from a previous recall never lingers into later,
            # unrelated turns.
            if self.messages and self.messages[0].get("role") == "system":
                self.messages[0] = {"role": "system", "content": base_prompt}
            self.messages.append(msg)
            # Log to daily file
            self.log_daily(role, content)
            if role == "user" and recall.is_recall_query(content):
                context = recall.build_context(content)
                if context:
                    # Append context to the system prompt for this turn only.
                    self.messages[0] = {
                        "role": "system",
                        "content": f"{base_prompt}\n\n{context}",
                    }
            self._trim_locked()

    def _trim_locked(self) -> None:
        """Caller must hold self._lock. Keep system prompt + last N turns,
        but never split a tool_call/tool pair."""
        if len(self.messages) <= 1 + self.max_turns * 2:
            return
        head = self.messages[:1]
        tail = self.messages[-self.max_turns * 2:]
        while tail and tail[0].get("role") == "tool":
            tail = tail[1:]
        self.messages = head + tail

    def _trim(self) -> None:
        # Kept for backward compat — delegates to the locked version.
        with self._lock:
            self._trim_locked()

    def as_list(self) -> list[dict[str, Any]]:
        # Return a *copy* so callers iterating while another thread mutates
        # don't see a torn list.
        with self._lock:
            return list(self.messages)

    def _get_daily_log_path(self) -> Path:
        """Get the path for today's conversation log file."""
        DAILY_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        return DAILY_LOGS_DIR / f"conversation_{today}.md"

    def _log_to_daily_file(self, role: str, content: str) -> None:
        """Append a message to today's daily conversation log."""
        log_path = self._get_daily_log_path()
        timestamp = datetime.now().strftime("%H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n[{timestamp}] {role.upper()}: {content}")

    def log_daily(self, role: str, content: str) -> None:
        """Log a message to the daily conversation file."""
        try:
            self._log_to_daily_file(role, content)
        except Exception:
            pass  # Don't let logging failures break the main flow

    def last_user_text(self) -> str:
        with self._lock:
            for m in reversed(self.messages):
                if m.get("role") == "user" and m.get("content"):
                    return str(m["content"])
        return ""

    def set_last_assistant(self, text: str) -> None:
        """Persist the final streamed reply onto the most recent assistant
        message. Locates the assistant message explicitly (don't assume it's
        messages[-1] — the last entry may be a tool result) and takes the
        lock so it can't race the other surface sharing this memory."""
        with self._lock:
            for m in reversed(self.messages):
                if m.get("role") == "assistant":
                    m["content"] = text
                    return
            # No assistant message to update — append one.
            self.messages.append({"role": "assistant", "content": text})
            self._trim_locked()

    # ── pending approval calls ───────────────────────
    def store_pending(self, call_id: str, name: str, args: dict, raw_call: dict) -> None:
        with self._lock:
            self._pending[call_id] = {
                "name": name,
                "args": args,
                "raw_call": raw_call,
            }

    def take_pending(self, call_id: str) -> dict | None:
        with self._lock:
            return self._pending.pop(call_id, None)

    def list_pending(self) -> list[dict]:
        with self._lock:
            return [
                {"id": cid, "name": v["name"], "args": v["args"]}
                for cid, v in self._pending.items()
            ]

    # ── persistence ──────────────────────────────────
    def save(self) -> None:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"saved_at": datetime.now().isoformat(), "messages": self.messages}
        HISTORY_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def load(self) -> bool:
        if not HISTORY_FILE.exists():
            return False
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            msgs = data.get("messages", [])
            if not isinstance(msgs, list):
                return False
            if msgs and isinstance(msgs[0], dict) and msgs[0].get("role") == "system":
                msgs[0]["content"] = self.system_prompt
            with self._lock:
                self.messages = msgs or self.messages
            return True
        except (json.JSONDecodeError, OSError, AttributeError, TypeError, ValueError):
            # Corrupt / hand-edited history should fall back to a clean start,
            # never crash startup.
            return False

    def reset(self) -> None:
        """Clear messages and pending calls."""
        with self._lock:
            self.messages = [{"role": "system", "content": self.system_prompt}]
            self._pending.clear()
