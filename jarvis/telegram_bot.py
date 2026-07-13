"""Telegram bot adapter for JARVIS.

Exposes the same Brain + REGISTRY the web/CLI use, but driven by Telegram
messages. Designed to run as a background thread inside `server.py`.

Auth: a user DMs the bot, sends `/start`, then sends the JARVIS_PIN
configured on the host. The bot stores their chat_id in
~/.jarvis/telegram_authorized.json and only that chat_id can interact
afterwards.

Features:
- `/start`, `/menu`, `/help` — onboarding + command list.
- Inline keyboard: Screenshot, System, Battery, CPU/RAM, Open URL,
  Volume, Shutdown, Restart, Chat.
- Text commands: /screenshot, /battery, /status, /windows, /volume,
  /open, /cancel_shutdown, /reset.
- Free-form chat: anything else goes through `Brain.ask(...)` and replies
  with the model's text. Tool results that reference files (e.g.
  "Screenshot saved to /path/...png") are sent as Telegram photos/documents.
- Approval flow: when a tool requires approval, the bot sends the user an
  inline ✅/❌ keyboard. Approve / Deny resumes the streaming Brain.
- Push notifications: subscribes to the shared AlertHub. Watchdog alerts
  forwarded from `server.py` get DMed to all authorized chat_ids.

Threading:
- The bot's network loop runs in its own thread (Application).
- One per-chat lock (`_chat_locks`) serializes chat access for that user.
- A separate `_memory_lock` guards shared MEMORY edits against the web UI.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Callable

from config import CONFIG
from . import contacts, facts, sessions
from .telegram_alerts import HUB
# Authorized chat_ids (set once a user sends the correct JARVIS_PIN).
AUTH_PATH = Path.home() / ".jarvis" / "telegram_authorized.json"

# Telegram API limits
MAX_MESSAGE = 4000        # leave headroom under the 4096 cap
CALLBACK_ANSWER = "..."   # what to show when answering an inline button
APPROVE_TTL = 300         # seconds before a pending approval expires

# Lazy import — only fail if user actually enables the bot.
_ptb = None
_ptb_err: Exception | None = None


def _load_ptb():
    global _ptb, _ptb_err
    if _ptb is not None or _ptb_err is not None:
        return _ptb
    try:
        from telegram import (
            InlineKeyboardButton,
            InlineKeyboardMarkup,
            KeyboardButton,
            ReplyKeyboardMarkup,
            Update,
        )
        from telegram.ext import (
            Application,
            ApplicationBuilder,
            CallbackQueryHandler,
            CommandHandler,
            ContextTypes,
            MessageHandler,
            filters,
        )
        _ptb = {
            "InlineKeyboardButton": InlineKeyboardButton,
            "InlineKeyboardMarkup": InlineKeyboardMarkup,
            "KeyboardButton": KeyboardButton,
            "ReplyKeyboardMarkup": ReplyKeyboardMarkup,
            "Update": Update,
            "Application": Application,
            "ApplicationBuilder": ApplicationBuilder,
            "CallbackQueryHandler": CallbackQueryHandler,
            "CommandHandler": CommandHandler,
            "ContextTypes": ContextTypes,
            "MessageHandler": MessageHandler,
            "filters": filters,
        }
    except Exception as exc:  # noqa: BLE001
        _ptb_err = exc
    return _ptb


# ── main menu (inline) ────────────────────────────────
def _main_menu(ptb: dict) -> Any:
    return ptb["InlineKeyboardMarkup"]([
        [
            ptb["InlineKeyboardButton"]("📸 Screenshot", callback_data="act:screenshot"),
            ptb["InlineKeyboardButton"]("🖥 System", callback_data="act:system"),
        ],
        [
            ptb["InlineKeyboardButton"]("🔋 Battery", callback_data="act:battery"),
            ptb["InlineKeyboardButton"]("💻 CPU/RAM", callback_data="act:cpuram"),
        ],
        [
            ptb["InlineKeyboardButton"]("🌐 Open URL", callback_data="act:openurl"),
            ptb["InlineKeyboardButton"]("📂 Files", callback_data="act:files"),
        ],
        [
            ptb["InlineKeyboardButton"]("🔊 Volume", callback_data="act:volume"),
            ptb["InlineKeyboardButton"]("🪟 Windows", callback_data="act:windows"),
        ],
        [
            ptb["InlineKeyboardButton"]("⏻ Shutdown", callback_data="act:shutdown"),
            ptb["InlineKeyboardButton"]("🔄 Restart", callback_data="act:restart"),
        ],
        [
            ptb["InlineKeyboardButton"]("🔁 Reset memory", callback_data="act:reset"),
            ptb["InlineKeyboardButton"]("❌ Cancel shutdown", callback_data="act:cancelshutdown"),
        ],
        [
            ptb["InlineKeyboardButton"]("🪪 About you", callback_data="act:me"),
            ptb["InlineKeyboardButton"]("📦 Projects", callback_data="act:myprojects"),
        ],
    ])


def _files_submenu(ptb: dict) -> Any:
    return ptb["InlineKeyboardMarkup"]([
        [
            ptb["InlineKeyboardButton"]("✏️ Write file", callback_data="file:write"),
            ptb["InlineKeyboardButton"]("➕ Append", callback_data="file:append"),
        ],
        [
            ptb["InlineKeyboardButton"]("📂 mkdir", callback_data="file:mkdir"),
            ptb["InlineKeyboardButton"]("📋 List dir", callback_data="file:list"),
        ],
        [
            ptb["InlineKeyboardButton"]("👀 Read", callback_data="file:read"),
            ptb["InlineKeyboardButton"]("🗑 Delete", callback_data="file:delete"),
        ],
        [ptb["InlineKeyboardButton"]("« Back to menu", callback_data="act:menu")],
    ])


HELP_TEXT = """\
*JARVIS Telegram bot* 🤖

*Quick menu* — tap /menu for buttons.

*Commands*
• /start — link this chat (send the JARVIS_PIN after)
• /menu — show the quick-action keyboard
• /me — your identity summary (name, education, laptop, contact)
• /myprojects — list of active projects
• /contacts — list all saved contacts
• /daily_log [YYYY-MM-DD] — view today's (or specified date's) conversation log
• /status — CPU, RAM, battery, uptime, hostname
• /screenshot — take + send a screenshot
• /battery — battery % + plugged status
• /windows — list open window titles
• /volume <0-100|mute|unmute> — system volume
• /open <app> — open an app
• /cancel_shutdown — cancel a scheduled shutdown
• /weather [city] — current weather (auto-detects your city if omitted)
• /time — host date + time, plus quick weather
• /reset — back up + summarize, then clear conversation memory
• /backup — DM a session summary + your local memory files
• /file <write|append|mkdir|list|read|delete|write_text> <path> [content…]
  — file ops on any path the OS lets you touch
• /help — this message

*Free chat* — anything that isn't a command is sent to JARVIS's brain
(the same one the web/CLI use), so you can ask "open chrome and search
for recipes" or "summarize my notes". Destructive actions ask for
approval with ✅ / ❌ buttons before running.

*Stop the bot* — set `JARVIS_TELEGRAM_ENABLED=0` in `.env` and restart.
"""


# ── authorized chat_id persistence ────────────────────
def _load_authorized() -> dict[str, dict]:
    if not AUTH_PATH.exists():
        return {}
    try:
        return json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_authorized(auth: dict[str, dict]) -> None:
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTH_PATH.write_text(
        json.dumps(auth, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── main class ───────────────────────────────────────
class TelegramBot:
    def __init__(self, brain, memory, registry, watchdog) -> None:
        self.brain = brain
        self.memory = memory
        self.registry = registry
        self.watchdog = watchdog
        self._app: Any = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._unsub_alert: Callable[[], None] | None = None
        # Per-chat locks (so the same user can't fire two brain calls at once)
        self._chat_locks: dict[int, threading.Lock] = defaultdict(threading.Lock)
        # Protects the shared MEMORY against the web UI editing concurrently
        self._memory_lock = threading.Lock()
        # chat_id → call_id for a pending approval button
        self._pending_approvals: dict[int, str] = {}
        self._pending_at: dict[str, float] = {}
        # chat_id → (tool_name, tool_args) for button-driven approvals
        # (Shutdown/Restart/file-delete) that bypass the model and are
        # dispatched directly once approved.
        self._pending_button: dict[int, tuple[str, dict]] = {}
        # chat_id → (op, path) — set by /file write|append, consumed by
        # the next document upload
        self._pending_file: dict[int, tuple[str, str]] = {}
        # Outgoing notification queue (AlertHub → bot). Only used as a
        # fallback buffer for alerts that arrive before the bot's event
        # loop is up; _post_init flushes it.
        self._notify_queue: deque[str] = deque(maxlen=50)
        # The bot's asyncio loop, captured in _post_init so cross-thread
        # alert producers (the watchdog) can schedule delivery onto it.
        self._loop: asyncio.AbstractEventLoop | None = None
        # Track which chat_ids have been prompted with a "..." placeholder
        # we still need to edit.
        # One-shot flag so the conflict warning only prints once per run.
        self._conflict_warned = False

    # ── lifecycle ───────────────────────────────────
    def start(self) -> bool:
        """Spawn the bot thread. Returns True on success."""
        if self._running:
            return True
        if not (CONFIG.telegram_enabled and CONFIG.telegram_token):
            return False
        ptb = _load_ptb()
        if not ptb:
            print(
                f"[telegram] python-telegram-bot not installed "
                f"({_ptb_err}). Run: pip install python-telegram-bot"
            )
            return False

        try:
            self._app = (
                ptb["ApplicationBuilder"]()
                .token(CONFIG.telegram_token)
                .post_init(self._post_init)
                .build()
            )
            self._register_handlers(ptb)
            # Forward AlertHub broadcasts into our queue.
            self._unsub_alert = HUB.subscribe(self._on_alert)
        except Exception as exc:  # noqa: BLE001
            print(f"[telegram] failed to start: {exc}")
            return False

        self._running = True
        self._thread = threading.Thread(
            target=self._run_app, args=(ptb,), daemon=True,
            name="jarvis-telegram",
        )
        self._thread.start()
        # Drain the watchdog → AlertHub forwarding is set up by server.py.
        print("[telegram] bot thread started")
        return True

    def stop(self) -> None:
        self._running = False
        if self._unsub_alert:
            try:
                self._unsub_alert()
            except Exception:  # noqa: BLE001
                pass
            self._unsub_alert = None

    def _run_app(self, ptb: dict) -> None:
        try:
            self._app.run_polling(
                stop_signals=False,
                close_loop=False,
                drop_pending_updates=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[telegram] polling stopped: {exc}")

    async def _on_ptb_error(self, update, context) -> None:
        """Quiet handler for runtime errors (network blips, conflicts, bad updates).

        Without this, python-telegram-bot v22 logs the full traceback to stderr
        for every transient error. We log a short one-liner instead, and bump
        a counter the user can query via /status.
        """
        err = context.error
        msg = str(err) if err else "unknown"
        # Conflict means another instance is polling — surface once, don't spam.
        if "Conflict" in msg or "terminated by other getUpdates" in msg:
            if not self._conflict_warned:
                self._conflict_warned = True
                # Try to point the user at the offending PID.
                pid_hint = ""
                try:
                    import subprocess
                    out = subprocess.run(
                        ["powershell", "-NoProfile", "-Command",
                         "Get-NetTCPConnection -State Established "
                         "-RemotePort 443 -ErrorAction SilentlyContinue "
                         "| Where-Object { $_.RemoteAddress -like '149.154.*' } "
                         "| Select-Object -ExpandProperty OwningProcess -Unique"],
                        capture_output=True, text=True, timeout=3,
                    )
                    if out.stdout.strip():
                        pid_hint = f" (try: Stop-Process -Id {out.stdout.strip().splitlines()[0]} -Force)"
                except Exception:  # noqa: BLE001
                    pass
                print(
                    "[telegram] ⚠ another JARVIS instance is already polling "
                    f"this bot token.{pid_hint} Close the other server.py / "
                    "jarvis_telegram.py and this one will take over automatically."
                )
            return
        # Bad update from a user (parse error, wrong chat type, etc.) — just note it.
        if "BadRequest" in msg or "ParseError" in msg:
            print(f"[telegram] bad update: {msg[:120]}")
            return
        # Timed out / network — the bot auto-retries; nothing to do.
        if "TimedOut" in msg or "NetworkError" in msg:
            return
        # Anything else: log once, don't traceback-spam.
        print(f"[telegram] error: {msg[:200]}")

    def authorized_chat_ids(self) -> list[int]:
        return [int(k) for k in _load_authorized().keys()]

    def is_running(self) -> bool:
        return self._running and self._app is not None

    # ── alert hub bridge ────────────────────────────
    async def _post_init(self, app) -> None:
        """Runs once on the bot's event loop after startup.

        Captures the loop so `_on_alert` (called from the watchdog thread)
        can schedule delivery onto it, then flushes any alerts that queued
        before the loop was ready.
        """
        self._loop = asyncio.get_running_loop()
        queued = list(self._notify_queue)
        self._notify_queue.clear()
        for text in queued:
            await self._broadcast_alert(text)

    def _on_alert(self, text: str) -> None:
        """Called by AlertHub from an arbitrary thread (e.g. the watchdog).

        `send_message` must run on the bot's asyncio loop, so we hop threads
        via `run_coroutine_threadsafe`. If the loop isn't up yet, buffer the
        alert; `_post_init` flushes the buffer once it is.
        """
        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    self._broadcast_alert(text), loop,
                )
                return
            except Exception:  # noqa: BLE001
                pass
        self._notify_queue.append(text)

    async def _broadcast_alert(self, text: str) -> None:
        """Deliver a push alert to every authorized chat as a formatted card."""
        if not (self._app and self._app.bot):
            return
        body = _format_alert(text)
        for chat_id in self.authorized_chat_ids():
            for chunk in _split_message(body):
                try:
                    await self._app.bot.send_message(
                        chat_id=chat_id, text=chunk, parse_mode="Markdown",
                    )
                except Exception:  # noqa: BLE001
                    # Markdown may have broken parsing — retry as plain text
                    # so the alert still gets through.
                    try:
                        await self._app.bot.send_message(
                            chat_id=chat_id, text=chunk,
                        )
                    except Exception:  # noqa: BLE001
                        pass

    def push(self, text: str) -> None:
        """Synchronous push (for tests or external callers)."""
        HUB.broadcast(text)

    def request_memory_backup(self, reason: str = "auto") -> bool:
        """Thread-safe trigger for push_memory_backup from non-async callers
        (e.g. the server's atexit shutdown hook). Schedules the coroutine on
        the bot's asyncio loop and waits briefly for it to finish so a
        shutdown backup actually flushes before the process exits."""
        loop = self._loop
        if loop is None or not loop.is_running():
            return False
        try:
            fut = asyncio.run_coroutine_threadsafe(
                self.push_memory_backup(reason=reason), loop,
            )
            return bool(fut.result(timeout=15))
        except Exception:  # noqa: BLE001
            return False

    # ── handler registration ─────────────────────────
    def _register_handlers(self, ptb: dict) -> None:
        self._app.add_error_handler(self._on_ptb_error)
        self._app.add_handler(ptb["CommandHandler"]("start", self._cmd_start))
        self._app.add_handler(ptb["CommandHandler"]("menu", self._cmd_menu))
        self._app.add_handler(ptb["CommandHandler"]("help", self._cmd_help))
        self._app.add_handler(ptb["CommandHandler"]("me", self._cmd_me))
        self._app.add_handler(ptb["CommandHandler"]("myprojects", self._cmd_myprojects))
        self._app.add_handler(ptb["CommandHandler"]("status", self._cmd_status))
        self._app.add_handler(ptb["CommandHandler"]("screenshot", self._cmd_screenshot))
        self._app.add_handler(ptb["CommandHandler"]("battery", self._cmd_battery))
        self._app.add_handler(ptb["CommandHandler"]("windows", self._cmd_windows))
        self._app.add_handler(ptb["CommandHandler"]("volume", self._cmd_volume))
        self._app.add_handler(ptb["CommandHandler"]("open", self._cmd_open))
        self._app.add_handler(ptb["CommandHandler"](
            "cancel_shutdown", self._cmd_cancel_shutdown
        ))
        self._app.add_handler(ptb["CommandHandler"]("contacts", self._cmd_contacts))
        self._app.add_handler(ptb["CommandHandler"]("daily_log", self._cmd_daily_log))
        self._app.add_handler(ptb["CommandHandler"]("reset", self._cmd_reset))
        self._app.add_handler(ptb["CommandHandler"]("backup", self._cmd_backup))
        self._app.add_handler(ptb["CommandHandler"]("weather", self._cmd_weather))
        self._app.add_handler(ptb["CommandHandler"]("time", self._cmd_time))
        self._app.add_handler(ptb["CommandHandler"]("file", self._cmd_file))
        # ── Agent commands ──────────────────────────────
        self._app.add_handler(ptb["CommandHandler"]("goal", self._cmd_goal))
        self._app.add_handler(ptb["CommandHandler"]("goals", self._cmd_goals))
        self._app.add_handler(ptb["CommandHandler"]("run", self._cmd_run))
        self._app.add_handler(ptb["CommandHandler"]("pause", self._cmd_pause))
        self._app.add_handler(ptb["CommandHandler"]("agent", self._cmd_agent))
        # Documents (file uploads) — used by /file write/append to receive
        # the actual bytes from Telegram.
        # In python-telegram-bot v20+ the filter moved to filters.Document.ALL
        doc_filter = getattr(
            ptb["filters"], "DOCUMENT", None
        ) or getattr(ptb["filters"], "Document", None)
        if doc_filter is not None:
            doc_filter = doc_filter.ALL if hasattr(doc_filter, "ALL") else doc_filter
            self._app.add_handler(ptb["MessageHandler"](
                doc_filter, self._on_document
            ))
        self._app.add_handler(ptb["CallbackQueryHandler"](
            self._on_callback, pattern=r"^(act:|approve:|deny:)"
        ))
        self._app.add_handler(ptb["MessageHandler"](
            ptb["filters"].TEXT & ~ptb["filters"].COMMAND, self._on_text
        ))

    # ── helpers ──────────────────────────────────────
    def _is_authorized(self, chat_id: int) -> bool:
        return str(chat_id) in _load_authorized()

    async def _reply(self, update, text: str, **kwargs) -> None:
        """Send a (possibly long) text reply, splitting at 4000 chars.

        If a Markdown send fails (dynamic content like Windows paths or code
        frequently breaks Telegram's parser), retry the same chunk as plain
        text so a computed reply is never silently lost.
        """
        if not text:
            return
        for chunk in _split_message(text):
            try:
                await update.effective_chat.send_message(chunk, **kwargs)
            except Exception:  # noqa: BLE001
                if kwargs.get("parse_mode"):
                    plain = {k: v for k, v in kwargs.items() if k != "parse_mode"}
                    try:
                        await update.effective_chat.send_message(chunk, **plain)
                    except Exception:  # noqa: BLE001
                        pass

    async def _send_placeholder(self, update, text: str = "🤖 …"):
        msg = await update.effective_chat.send_message(text)
        return msg.message_id

    async def _edit_to(self, update, message_id: int, text: str) -> None:
        for chunk in _split_message(text):
            try:
                await update.effective_chat.edit_message_text(
                    chunk, message_id=message_id,
                )
            except Exception:  # noqa: BLE001
                # If edit fails (e.g. text didn't change, or message gone),
                # fall back to sending a new message.
                try:
                    await update.effective_chat.send_message(chunk)
                except Exception:  # noqa: BLE001
                    pass
            break  # editMessageText only takes the first chunk; send the rest

    def _maybe_attach_file(self, text: str, chat_id: int) -> str:
        """If the tool result references a file path we can send, attach it.

        Returns the cleaned text (with the file-path announcement stripped).
        Supported: 'Screenshot saved to <path>' and 'saved to <path>.png'.

        Note: this is a *sync* helper. It just locates the file and
        stashes the path. The actual async send happens in
        `await self._send_attached_file(...)` — call that from async
        handlers so we don't block the event loop on a network upload.
        """
        # Don't clobber an existing "write"/"append" pending op (file upload flow).
        existing = self._pending_file.get(chat_id)
        if existing and existing[0] in ("write", "append"):
            return text
        if not text:
            self._pending_file.pop(chat_id, None)
            return text
        m = re.search(r"(?:Screenshot saved to|Saved to)\s+(\S+\.(?:png|jpg|jpeg))",
                      text, flags=re.IGNORECASE)
        if not m:
            self._pending_file.pop(chat_id, None)
            return text
        path = m.group(1).strip(".,)")
        if not os.path.exists(path):
            self._pending_file.pop(chat_id, None)
            return text
        self._pending_file[chat_id] = (path, "photo")
        # Strip the announcement from the text reply.
        return re.sub(r"(?:Screenshot saved to|Saved to)\s+\S+\.(?:png|jpg|jpeg)[\.,]?",
                      "", text, count=1, flags=re.IGNORECASE).strip()

    async def _send_attached_file(self, chat_id: int) -> None:
        """If a file is pending for this chat, send it. Non-blocking.

        Uses `asyncio.to_thread` to run python-telegram-bot's sync
        `send_photo` off the event loop, then cleans up.
        """
        pending = self._pending_file.pop(chat_id, None)
        if not pending or not (self._app and self._app.bot):
            return
        path, kind = pending
        if not os.path.exists(path):
            return
        try:
            with open(path, "rb") as fh:
                if kind == "photo":
                    await self._app.bot.send_photo(chat_id=chat_id, photo=fh)
                else:
                    await self._app.bot.send_document(chat_id=chat_id, document=fh)
        except Exception as exc:  # noqa: BLE001
            # BadRequest on duplicate, network blip, etc. — don't crash.
            print(f"[telegram] send_file: {exc}")


    # ── command handlers ────────────────────────────
    async def _cmd_start(self, update, context) -> None:
        chat_id = update.effective_chat.id
        ptb = _load_ptb()
        # /start <PIN> form
        if context.args and len(context.args) == 1 and not self._is_authorized(chat_id):
            pin = context.args[0].strip()
            if not CONFIG.pin:
                await self._reply(
                    update,
                    "🔒 Remote access is disabled on the host. "
                    "Set `JARVIS_PIN` in the host's `.env` and restart.",
                )
                return
            if pin != CONFIG.pin:
                await self._reply(update, "❌ Wrong PIN. Try again or check the host config.")
                return
            auth = _load_authorized()
            user = update.effective_user
            auth[str(chat_id)] = {
                "username": user.username if user else "",
                "first_name": user.first_name if user else "",
                "linked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            _save_authorized(auth)
            # Try to delete the PIN message for safety (best effort).
            try:
                if update.message:
                    await update.message.delete()
            except Exception:  # noqa: BLE001
                pass
            await self._reply(
                update,
                f"✅ *Linked!* Welcome, {user.first_name or 'friend'}.\n\n"
                f"Host: `{CONFIG.name}` · model: `{CONFIG.model}`\n"
                f"You can now chat, run commands, or tap /menu.",
                reply_markup=_main_menu(ptb),
                parse_mode="Markdown",
            )
            return
        if self._is_authorized(chat_id):
            await self._reply(
                update, "Already linked. Tap a button or chat away!",
                reply_markup=_main_menu(ptb),
            )
            return
        await self._reply(
            update,
            "👋 Hi! I'm JARVIS, the laptop controller.\n\n"
            "To link this chat, send the access PIN that is set on the host PC\n"
            "(see `JARVIS_PIN` in the host's `.env`) like this:\n\n"
            "`/start 5252`\n\n"
            "💡 If the host has no PIN set, the bot will refuse to link.",
            parse_mode="Markdown",
        )

    async def _cmd_menu(self, update, context) -> None:
        if not self._gate(update):
            return
        await self._reply(update, "*Main menu* — tap a button.", parse_mode="Markdown",
                          reply_markup=_main_menu(_load_ptb()))

    async def _cmd_help(self, update, context) -> None:
        if not self._gate(update):
            return
        await self._reply(update, HELP_TEXT, parse_mode="Markdown")

    async def _cmd_me(self, update, context) -> None:
        if not self._gate(update):
            return
        result = self.registry.dispatch("who_am_i", {})
        await self._reply(update, f"🪪 *You*\n{result}", parse_mode="Markdown")

    async def _cmd_myprojects(self, update, context) -> None:
        if not self._gate(update):
            return
        result = self.registry.dispatch("my_projects", {})
        await self._reply(update, f"📦 *Active projects*\n{result}", parse_mode="Markdown")

    async def _cmd_file(self, update, context) -> None:
        if not self._gate(update):
            return
        args = context.args or []
        if not args:
            await self._reply(
                update,
                "📂 *File ops*\n\n"
                "Usage:\n"
                "• `/file write <path>` — then send the file as a document\n"
                "• `/file write_text <path> <content…>` — write text inline\n"
                "• `/file append <path>` — then send the file as a document\n"
                "• `/file append_text <path> <content…>`\n"
                "• `/file mkdir <path>`\n"
                "• `/file list <path>` — one level deep\n"
                "• `/file read <path>`\n"
                "• `/file delete <path>` — asks for approval\n\n"
                "Paths can be absolute or start with `~/` (your home dir). "
                "System directories (`C:\\Windows`, etc.) are refused.",
                parse_mode="Markdown", reply_markup=_files_submenu(_load_ptb()),
            )
            return
        sub = args[0].lower()
        rest = args[1:]
        if sub == "write":
            if not rest:
                await self._reply(
                    update,
                    "Send the path, then attach the file. Example:\n"
                    "`/file write C:\\Users\\sampa\\Desktop\\notes.txt`",
                )
                return
            target_path = " ".join(rest)
            self._pending_file[update.effective_chat.id] = ("write", target_path)
            await self._reply(
                update,
                f"📥 Send me the file you want to save to:\n`{target_path}`",
                parse_mode="Markdown",
            )
            return
        if sub == "append":
            if not rest:
                await self._reply(update, "Send the path, then attach the file.")
                return
            target_path = " ".join(rest)
            self._pending_file[update.effective_chat.id] = ("append", target_path)
            await self._reply(
                update,
                f"📥 Send me the file to append to:\n`{target_path}`",
                parse_mode="Markdown",
            )
            return
        if sub == "write_text":
            if len(rest) < 2:
                await self._reply(
                    update,
                    "Usage: `/file write_text <path> <content…>`",
                )
                return
            path = rest[0]
            content = " ".join(rest[1:])
            result = self.registry.dispatch(
                "write_file_anywhere", {"path": path, "content": content},
            )
            await self._reply(update, f"✏️ {result}")
            return
        if sub == "append_text":
            if len(rest) < 2:
                await self._reply(
                    update,
                    "Usage: `/file append_text <path> <content…>`",
                )
                return
            path = rest[0]
            content = " ".join(rest[1:])
            result = self.registry.dispatch(
                "append_file_anywhere", {"path": path, "content": content},
            )
            await self._reply(update, f"➕ {result}")
            return
        if sub == "mkdir":
            if not rest:
                await self._reply(update, "Usage: `/file mkdir <path>`")
                return
            path = " ".join(rest)
            result = self.registry.dispatch("mkdir_anywhere", {"path": path})
            await self._reply(update, f"📂 {result}")
            return
        if sub == "list":
            path = " ".join(rest) if rest else str(Path.home())
            result = self.registry.dispatch("list_anywhere", {"path": path})
            await self._reply(
                update, f"📋 *{path}*\n{result}", parse_mode="Markdown",
            )
            return
        if sub == "read":
            if not rest:
                await self._reply(update, "Usage: `/file read <path>`")
                return
            path = " ".join(rest)
            result = self.registry.dispatch(
                "read_file_anywhere", {"path": path},
            )
            if len(result) > 3500:
                result = result[:3500] + "\n…(truncated)"
            await self._reply(update, f"👀 *{path}*\n```\n{result}\n```",
                              parse_mode="Markdown")
            return
        if sub == "delete":
            if not rest:
                await self._reply(update, "Usage: `/file delete <path>`")
                return
            path = " ".join(rest)
            # Reuse the approval flow.
            await self._ask_brain(
                update, context,
                f"Delete {path} on the laptop.",
                force_approval=("delete_file", {"path": path}),
            )
            return
        await self._reply(
            update,
            f"Unknown subcommand: `{sub}`\n"
            "Try `write`, `write_text`, `append`, `append_text`, `mkdir`, "
            "`list`, `read`, `delete`.",
            parse_mode="Markdown",
        )

    async def _on_document(self, update, context) -> None:
        """Handle document uploads — used by `/file write` / `/file append`."""
        chat_id = update.effective_chat.id
        if not self._is_authorized(chat_id):
            return
        pending = self._pending_file.get(chat_id)
        if not pending:
            return
        op, target_path = pending
        self._pending_file.pop(chat_id, None)
        doc = update.message.document
        if not doc:
            return
        try:
            tg_file = await doc.get_file()
            data = await tg_file.download_as_bytearray()
            content = bytes(data).decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            await self._reply(update, f"Couldn't download the file: {exc}")
            return
        if op == "write":
            result = self.registry.dispatch(
                "write_file_anywhere",
                {"path": target_path, "content": content},
            )
        else:
            result = self.registry.dispatch(
                "append_file_anywhere",
                {"path": target_path, "content": content},
            )
        await self._reply(update, f"{'✏️' if op == 'write' else '➕'} {result}")

    async def _cmd_status(self, update, context) -> None:
        if not self._gate(update):
            return
        result = self.registry.dispatch("system_info", {})
        await self._reply(update, f"🖥 *System*\n{result}", parse_mode="Markdown")

    async def _cmd_screenshot(self, update, context) -> None:
        if not self._gate(update):
            return
        result = self.registry.dispatch("take_screenshot", {})
        path_m = re.search(r"(\S+\.png)", result)
        if path_m and os.path.exists(path_m.group(1)):
            try:
                with open(path_m.group(1), "rb") as f:
                    await update.effective_chat.send_photo(photo=f, caption="📸 Screenshot")
            except Exception as exc:  # noqa: BLE001
                await self._reply(update, f"📸 Screenshot saved, but couldn't send: {exc}\n{result}")
        else:
            await self._reply(update, f"📸 {result}")

    async def _cmd_battery(self, update, context) -> None:
        if not self._gate(update):
            return
        try:
            import psutil
            batt = psutil.sensors_battery()
            if batt is None:
                await self._reply(update, "🔋 No battery detected (desktop?).")
                return
            plug = "⚡ charging" if batt.power_plugged else "🔌 on battery"
            secs = getattr(batt, "secsleft", None)
            eta = ""
            if secs and secs not in (psutil.POWER_TIME_UNLIMITED,
                                     psutil.POWER_TIME_UNKNOWN) and not batt.power_plugged:
                h, m = divmod(int(secs) // 60, 60)
                eta = f" · ~{h}h {m}m left"
            await self._reply(update, f"🔋 *Battery*: {batt.percent:.0f}% · {plug}{eta}",
                              parse_mode="Markdown")
        except Exception as exc:  # noqa: BLE001
            await self._reply(update, f"Couldn't read battery: {exc}")

    async def _cmd_windows(self, update, context) -> None:
        if not self._gate(update):
            return
        result = self.registry.dispatch("list_windows", {})
        await self._reply(update, f"🪟 *Open windows*\n{result}" if "\n" in result else result,
                          parse_mode="Markdown")

    async def _cmd_volume(self, update, context) -> None:
        if not self._gate(update):
            return
        if not context.args:
            await self._reply(update, "Usage: /volume <0-100|mute|unmute>")
            return
        arg = context.args[0].lower()
        if arg in ("mute", "unmute"):
            result = self.registry.dispatch("set_volume", {"action": arg})
        else:
            try:
                level = max(0, min(100, int(arg)))
            except ValueError:
                await self._reply(update, "Volume must be 0-100, or 'mute'/'unmute'.")
                return
            result = self.registry.dispatch("set_volume", {"level": level, "action": "set"})
        await self._reply(update, f"🔊 {result}")

    async def _cmd_open(self, update, context) -> None:
        if not self._gate(update):
            return
        if not context.args:
            await self._reply(update, "Usage: /open <app>\nExamples: /open chrome, /open notepad")
            return
        app = " ".join(context.args)
        result = self.registry.dispatch("open_app", {"app": app})
        await self._reply(update, f"📦 {result}")

    async def _cmd_cancel_shutdown(self, update, context) -> None:
        if not self._gate(update):
            return
        result = self.registry.dispatch("cancel_shutdown", {})
        await self._reply(update, f"⏹ {result}")

    async def _cmd_contacts(self, update, context) -> None:
        if not self._gate(update):
            return
        items = contacts.list_all()
        if not items:
            await self._reply(update, "📞 *No contacts saved.*")
            return
        text = "*📞 Contacts*\n\n"
        for c in sorted(items, key=lambda x: x.get("name", "").lower()):
            aliases = ", ".join(c.get("aliases", []))
            text += f"👤 *{c.get('name', 'Unknown')}*\n"
            text += f"   📱 +{c.get('phone_e164', 'N/A')}\n"
            if aliases:
                text += f"   🔖 Aliases: {aliases}\n"
            text += "\n"
        await self._reply(update, text, parse_mode="Markdown")

    async def _cmd_daily_log(self, update, context) -> None:
        if not self._gate(update):
            return
        from pathlib import Path
        from datetime import datetime
        log_dir = Path.home() / ".jarvis" / "daily_logs"
        if not log_dir.exists():
            await self._reply(update, "📝 *No daily logs found.*")
            return

        # Get today's log by default, or allow specifying a date
        args = context.args or []
        if args:
            date_str = args[0]
            log_file = log_dir / f"conversation_{date_str}.md"
        else:
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = log_dir / f"conversation_{today}.md"

        if not log_file.exists():
            # List available logs
            logs = sorted(log_dir.glob("conversation_*.md"), reverse=True)
            if not logs:
                await self._reply(update, "📝 *No daily logs found.*")
                return
            text = "*📝 Available Daily Logs*\n\n"
            for l in logs[:10]:  # Show last 10
                date = l.stem.replace("conversation_", "")
                text += f"📄 `{date}`\n"
            text += "\nUse: `/daily_log YYYY-MM-DD` to view a specific day"
            await self._reply(update, text, parse_mode="Markdown")
            return

        # Read and send the log
        try:
            content = log_file.read_text(encoding="utf-8")
            if len(content) > 3500:
                content = content[:3500] + "\n\n…(truncated)"
            await self._reply(update, f"📝 *Daily Log - {log_file.stem}*\n\n```\n{content}\n```",
                              parse_mode="Markdown")
        except Exception as exc:
            await self._reply(update, f"⚠ Couldn't read log: {exc}")

    async def _cmd_reset(self, update, context) -> None:
        """Summarize the session (so nothing is lost to long-term recall),
        push a memory backup to Telegram, then clear the rolling window."""
        if not self._gate(update):
            return
        # Back up + summarize BEFORE clearing, so the summary reflects the
        # conversation we're about to wipe.
        try:
            await self.push_memory_backup(reason="reset")
        except Exception:  # noqa: BLE001
            pass
        with self._memory_lock:
            self.memory.reset()
            try:
                self.memory.save()
            except Exception:  # noqa: BLE001
                pass
        await self._reply(update, "🔁 *Memory cleared.* Fresh start, sir.",
                          parse_mode="Markdown")

    async def _cmd_backup(self, update, context) -> None:
        """On-demand: DM a session summary + the local memory files."""
        if not self._gate(update):
            return
        sent = await self.push_memory_backup(reason="manual",
                                             only_chat=update.effective_chat.id)
        if not sent:
            await self._reply(update, "🗄 Nothing to back up yet.")

    async def push_memory_backup(self, reason: str = "auto",
                                 only_chat: int | None = None) -> bool:
        """Mirror local memory to Telegram: a one-paragraph session summary
        plus the raw history.json and today's daily log as documents.

        `reason` tags the message; `only_chat` restricts delivery to one chat
        (used by /backup), otherwise every authorized chat receives it.
        Returns True if anything was sent. Off-device copy of the local store,
        readable from the phone — the local files remain the source of truth.
        """
        if not (self._app and self._app.bot):
            return False
        targets = ([only_chat] if only_chat is not None
                   else self.authorized_chat_ids())
        if not targets:
            return False

        # 1. Summary of the current rolling window (reuse the Brain summarizer).
        summary = ""
        try:
            msgs = [m for m in self.memory.as_list()
                    if m.get("role") in ("user", "assistant") and m.get("content")]
            if len(msgs) >= 2:
                summary = self.brain.summarize_session(msgs[-30:]) or ""
        except Exception:  # noqa: BLE001
            summary = ""

        # 2. Files to attach: canonical history + today's daily log.
        from datetime import datetime
        base = Path.home() / ".jarvis"
        files = [base / "history.json"]
        today_log = base / "daily_logs" / f"conversation_{datetime.now():%Y-%m-%d}.md"
        if today_log.exists():
            files.append(today_log)

        header = f"🗄 *Memory backup* ({reason})"
        if summary:
            header += f"\n\n_{summary}_"

        sent_any = False
        for chat_id in targets:
            try:
                await self._app.bot.send_message(
                    chat_id=chat_id, text=header, parse_mode="Markdown")
                sent_any = True
            except Exception:  # noqa: BLE001
                try:
                    await self._app.bot.send_message(chat_id=chat_id, text=header)
                    sent_any = True
                except Exception:  # noqa: BLE001
                    continue
            for fp in files:
                if not fp.exists():
                    continue
                try:
                    with open(fp, "rb") as fh:
                        await self._app.bot.send_document(
                            chat_id=chat_id, document=fh, filename=fp.name,
                        )
                except Exception as exc:  # noqa: BLE001
                    print(f"[telegram] backup send_document: {exc}")
        return sent_any

    async def _cmd_weather(self, update, context) -> None:
        """Current weather for a city (or auto-detected by IP). Uses the same
        free wttr.in service as the get_weather tool."""
        if not self._gate(update):
            return
        from .automations.web import get_weather
        city = " ".join(context.args or []).strip()
        try:
            report = await asyncio.to_thread(get_weather, city)
        except Exception as exc:  # noqa: BLE001
            report = f"Couldn't fetch weather: {exc}"
        await self._reply(update, f"🌦 {report}")

    async def _cmd_time(self, update, context) -> None:
        """Date + time on the host, plus quick weather."""
        if not self._gate(update):
            return
        from datetime import datetime
        now = datetime.now()
        lines = [
            f"🕐 *{now:%I:%M:%S %p}*",
            f"📅 {now:%A, %d %B %Y}",
        ]
        from .automations.web import get_weather
        try:
            lines.append(f"🌦 {await asyncio.to_thread(get_weather, '')}")
        except Exception:  # noqa: BLE001
            pass
        await self._reply(update, "\n".join(lines), parse_mode="Markdown")

    # ── Agent commands ──────────────────────────────
    async def _cmd_goal(self, update, context) -> None:
        """/goal <text> — create + auto-run an autonomous goal."""
        if not self._gate(update):
            return
        args = (context.args or [])
        title = " ".join(args).strip()
        if not title:
            await self._reply(
                update,
                "🤖 Usage: `/goal book a table for 2 at a Chinese place tonight`\n"
                "Creates a goal and the agent plans + runs it.",
                parse_mode="Markdown",
            )
            return
        from .agent import goals as AG
        from .agent import scheduler as SCH
        g = AG.create(title)
        await self._reply(update, f"🤖 Goal created: `{g['id']}` — planning & running…", parse_mode="Markdown")
        try:
            res = await asyncio.to_thread(SCH.run_now, g["id"])
            verdict = res.get("verdict", "unknown")
            icon = "✅" if verdict == "success" else "❌"
            await self._reply(update, f"🤖 {icon} Goal done: {verdict}")
        except Exception as exc:  # noqa: BLE001
            await self._reply(update, f"🤖 Goal queued but run failed: {exc}")

    async def _cmd_goals(self, update, context) -> None:
        """/goals — list all goals + status."""
        if not self._gate(update):
            return
        from .agent import goals as AG
        gs = AG.list_all()
        if not gs:
            await self._reply(update, "🤖 No goals yet. Use `/goal <text>` to create one.")
            return
        lines = ["🤖 *Goals*"]
        for g in gs[-12:]:
            icon = {"done": "✅", "running": "🔄", "failed": "❌",
                     "paused": "⏸", "pending": "⏳"}.get(g["status"], "•")
            cron = f" (cron: {g['cron']})" if g.get("cron") else ""
            lines.append(f"{icon} `{g['id']}` — {g['title']}{cron}")
        await self._reply(update, "\n".join(lines), parse_mode="Markdown")

    async def _cmd_run(self, update, context) -> None:
        """/run <goal_id> — manually run a goal now."""
        if not self._gate(update):
            return
        args = context.args or []
        gid = args[0] if args else ""
        if not gid:
            await self._reply(update, "🤖 Usage: `/run <goal_id>`", parse_mode="Markdown")
            return
        from .agent import scheduler as SCH
        from .agent import goals as AG
        if not AG.get(gid):
            await self._reply(update, f"🤖 No goal `{gid}`")
            return
        await self._reply(update, f"🤖 Running `{gid}`…", parse_mode="Markdown")
        try:
            res = await asyncio.to_thread(SCH.run_now, gid)
            await self._reply(update, f"🤖 Verdict: {res.get('verdict', '?')}")
        except Exception as exc:  # noqa: BLE001
            await self._reply(update, f"🤖 Run failed: {exc}")

    async def _cmd_pause(self, update, context) -> None:
        """/pause <goal_id> — pause a (cron) goal."""
        if not self._gate(update):
            return
        args = context.args or []
        gid = args[0] if args else ""
        if not gid:
            await self._reply(update, "🤖 Usage: `/pause <goal_id>`", parse_mode="Markdown")
            return
        from .agent import goals as AG
        g = AG.set_status(gid, "paused")
        if g is None:
            await self._reply(update, f"🤖 No goal `{gid}`")
        else:
            await self._reply(update, f"🤖 Paused `{gid}`")

    async def _cmd_agent(self, update, context) -> None:
        """/agent — scheduler status + due count."""
        if not self._gate(update):
            return
        from .agent import scheduler as SCH
        st = SCH.status()
        await self._reply(
            update,
            "🤖 *Agent scheduler*\n"
            f"  Running: {'yes' if st['running'] else 'no'}\n"
            f"  Total goals: {st['total_goals']}\n"
            f"  Due now: {st['due']}\n"
            f"  Busy: {', '.join(st['busy']) or 'none'}",
            parse_mode="Markdown",
        )

    # ── inline button handler ───────────────────────
    async def _on_callback(self, update, context) -> None:
        query = update.callback_query
        await query.answer(CALLBACK_ANSWER)
        chat_id = update.effective_chat.id
        if not self._is_authorized(chat_id):
            await self._reply(update, "🔒 Not authorized. /start to begin.")
            return
        data = query.data or ""
        if data.startswith("approve:") or data.startswith("deny:"):
            await self._resolve_approval(update, context, data)
            return
        if data.startswith("file:"):
            await self._dispatch_file(update, context, data.split(":", 1)[1])
            return
        # action: — quick-action buttons
        action = data.split(":", 1)[1] if data.startswith("act:") else ""
        await self._dispatch_action(update, context, action)

    async def _dispatch_file(self, update, context, sub: str) -> None:
        ptb = _load_ptb()
        if sub == "write":
            await self._reply(
                update,
                "Send the path, then attach the file:\n"
                "`/file write C:\\Users\\sampa\\Desktop\\notes.txt`",
                parse_mode="Markdown",
            )
            return
        if sub == "append":
            await self._reply(
                update,
                "Send the path, then attach the file:\n"
                "`/file append C:\\Users\\sampa\\Documents\\log.txt`",
                parse_mode="Markdown",
            )
            return
        if sub == "mkdir":
            await self._reply(
                update,
                "Send the path:\n`/file mkdir D:\\projects\\newthing`",
                parse_mode="Markdown",
            )
            return
        if sub == "list":
            await self._reply(
                update,
                "Send the path (or just `/file list` for your home):\n"
                "`/file list C:\\Users\\sampa\\Desktop`",
                parse_mode="Markdown",
            )
            return
        if sub == "read":
            await self._reply(
                update,
                "Send the path:\n`/file read C:\\Users\\sampa\\Desktop\\notes.txt`",
                parse_mode="Markdown",
            )
            return
        if sub == "delete":
            await self._reply(
                update,
                "Send the path (delete will ask for approval):\n"
                "`/file delete C:\\Users\\sampa\\Desktop\\old.txt`",
                parse_mode="Markdown",
            )
            return
        # default: show the submenu
        await self._reply(
            update, "📂 *File ops* — pick one:", parse_mode="Markdown",
            reply_markup=_files_submenu(ptb),
        )

    async def _dispatch_action(self, update, context, action: str) -> None:
        if action == "screenshot":
            await self._cmd_screenshot(update, context)
        elif action == "system":
            await self._cmd_status(update, context)
        elif action == "battery":
            await self._cmd_battery(update, context)
        elif action == "cpuram":
            try:
                import psutil
                cpu = psutil.cpu_percent(interval=0.6)
                mem = psutil.virtual_memory()
                text = (
                    f"💻 *CPU*: {cpu:.0f}%\n"
                    f"🧠 *RAM*: {mem.percent:.0f}% "
                    f"({mem.used // 2**20} / {mem.total // 2**20} MB)"
                )
                await self._reply(update, text, parse_mode="Markdown")
            except Exception as exc:  # noqa: BLE001
                await self._reply(update, f"Couldn't read CPU/RAM: {exc}")
        elif action == "openurl":
            await self._reply(
                update,
                "Send me a URL or a site name to open. "
                "Example: `open youtube` or `open https://google.com`",
                parse_mode="Markdown",
            )
        elif action == "files":
            await self._reply(
                update,
                "Just ask in plain text — e.g. \"list files in notes\" or "
                "\"read my todo.txt\". JARVIS can search the workspace, "
                "Documents, Desktop, and Downloads.",
            )
        elif action == "volume":
            await self._cmd_volume(
                update, _fake_context("volume", ["50"], context)
            )
        elif action == "windows":
            await self._cmd_windows(update, context)
        elif action == "shutdown":
            await self._ask_brain(
                update, context,
                "Shut down the computer in 30 seconds.",
                force_approval=("shutdown_pc", {"delay_seconds": 30}),
            )
        elif action == "restart":
            await self._ask_brain(
                update, context,
                "Restart the computer in 30 seconds.",
                force_approval=("restart_pc", {"delay_seconds": 30}),
            )
        elif action == "reset":
            await self._cmd_reset(update, context)
        elif action == "cancelshutdown":
            await self._cmd_cancel_shutdown(update, context)
        elif action == "me":
            await self._cmd_me(update, context)
        elif action == "myprojects":
            await self._cmd_myprojects(update, context)
        elif action == "menu":
            await self._cmd_menu(update, context)
        else:
            # "files" or anything we don't have a sub-handler for → show
            # the files submenu.
            await self._reply(
                update, "📂 *File ops* — pick one:", parse_mode="Markdown",
                reply_markup=_files_submenu(_load_ptb()),
            )

    # ── free-text chat → Brain ───────────────────────
    async def _on_text(self, update, context) -> None:
        chat_id = update.effective_chat.id
        if not self._gate(update):
            return
        text = update.message.text or ""
        if not text.strip():
            return
        await self._ask_brain(update, context, text)

    async def _ask_brain(
        self, update, context, user_text: str,
        force_approval: tuple[str, dict] | None = None,
    ) -> None:
        """Run the brain on `user_text` and reply.

        If `force_approval` is set, the bot pre-stages that tool call for
        approval without asking the LLM. Useful for buttons like
        Shutdown/Restart.
        """
        chat_id = update.effective_chat.id
        # Non-blocking busy check: acquiring a threading.Lock with `with`
        # would block the *whole* asyncio event loop (all chats) if this
        # chat already has a call in flight — that reads as "no reply at
        # all" to other users. Try instead, and tell the user we're busy.
        lock = self._chat_locks[chat_id]
        if not lock.acquire(blocking=False):
            await self._reply(update, "⏳ Still working on your last message — one sec, sir.")
            return
        typing_task = asyncio.ensure_future(self._typing_loop(update))
        try:
            placeholder_id = await _safe_send(
                update.effective_chat, "🤖 thinking…"
            )
            if not placeholder_id:
                return
            try:
                await self._react(update.message, "🤔")
                with self._memory_lock:
                    self.memory.add("user", user_text)
                    # Log to daily file
                    self.memory.log_daily("user", user_text)
                # If the user asked for shutdown/restart via a button, we
                # run that tool directly so we can show the approval UI
                # without depending on the model.
                if force_approval is not None:
                    tool_name, tool_args = force_approval
                    if self.registry.requires_approval(tool_name):
                        await self._prompt_approval(
                            update, context, tool_name, tool_args,
                            after_text=user_text,
                        )
                        return
                    # No approval needed (shouldn't happen for our two cases).
                    result = self.registry.dispatch(tool_name, tool_args)
                    with self._memory_lock:
                        self.memory.add("assistant", str(result))
                    await _safe_edit(
                        update.effective_chat, placeholder_id, str(result),
                    )
                    return

                # Normal chat path — Gemini drives tool-calling; we collect
                # the streamed tokens and show the final text to the user.
                # (The streamed text IS the final text — no second pass.)
                # `stream_ask` makes blocking HTTP calls, so consume it in a
                # worker thread — otherwise this network round-trip (which
                # can take 10-100s+ across model/key fallbacks) freezes the
                # single asyncio event loop and every other chat goes silent
                # until it finishes.
                final_text = ""
                pending: dict | None = None
                tokens: list[str] = []
                tool_results: list[dict] = []  # collected from tool_done events

                def _consume():
                    _tokens, _tools, _pending, _err = [], [], None, ""
                    for event in self.brain.stream_ask(user_text):
                        etype = event.get("type")
                        if etype == "token":
                            _tokens.append(event.get("text", ""))
                        elif etype == "tool_done":
                            _tools.append({
                                "name": event.get("name", ""),
                                "result": event.get("result", ""),
                            })
                        elif etype == "approval_required":
                            _pending = event
                            break
                        elif etype == "error":
                            _err = event.get("text", "Model error.")
                            break
                    return _tokens, _tools, _pending, _err

                tokens, tool_results, pending, err_text = await asyncio.to_thread(_consume)
                if pending is not None:
                    # Approval gate — show the prompt now.
                    preview = "".join(tokens).strip() or user_text
                    await _safe_edit(
                        update.effective_chat, placeholder_id, preview,
                    )
                    await self._prompt_approval(
                        update, context,
                        pending.get("name", ""), pending.get("args", {}),
                        call_id=pending.get("id"),
                    )
                    return
                raw_reply = "".join(tokens).strip()
                if not raw_reply:
                    # Use brain.py's specific reason (blocked/truncated/etc.)
                    # instead of a vague placeholder, if one was given.
                    raw_reply = err_text or "(no reply from model)"
                # The streamed tokens ARE the final reply. No second pass.
                final_text = raw_reply
                # Attach screenshots if any tool produced a file path.
                final_text = self._maybe_attach_file(final_text, chat_id)
                await _safe_edit(
                    update.effective_chat, placeholder_id, final_text,
                )
                await self._react(update.message, _emotion_emoji(final_text))
                await self._send_attached_file(chat_id)
            except Exception as exc:  # noqa: BLE001
                # Make common model-side errors human-readable.
                msg = str(exc)
                m = msg.lower()
                if "resource_exhausted" in m or "quota_exhausted" in m \
                        or ("429" in msg and ("quota" in m or "rate" in m)):
                    friendly = (
                        "⏳ Both Gemini keys hit their rate limit. "
                        "Wait a minute and try again, or set a different "
                        "model in Settings (`gemini-2.5-flash`, `gemini-2.0-flash-lite`)."
                    )
                elif "401" in msg or "403" in msg or "api key" in m or "auth" in m:
                    friendly = (
                        "🔑 Gemini rejected the API key. Open Settings in the "
                        "host GUI and re-paste your key from "
                        "https://aistudio.google.com/apikey."
                    )
                elif "404" in msg and "model" in m:
                    friendly = (
                        "🚫 That Gemini model isn't available. Open Settings "
                        "and pick a different model."
                    )
                elif "429" in msg or "rate" in m:
                    friendly = "⏳ Rate-limited by Gemini. Try again in a few seconds."
                elif "timeout" in m or "timed out" in m:
                    friendly = "⏱ Gemini timed out. Try again."
                elif "connection" in m or "network" in m:
                    friendly = "📡 Network error — check your connection."
                else:
                    friendly = f"⚠ Error: {msg}"
                await _safe_edit(
                    update.effective_chat, placeholder_id, friendly,
                )
                await self._react(update.message, "😢")
        finally:
            typing_task.cancel()
            # Persist the shared rolling memory to ~/.jarvis/history.json so
            # Telegram turns survive restarts and stay in sync with the web
            # HUD (both share this Memory instance). Best-effort — never let a
            # disk hiccup break the reply flow.
            try:
                self.memory.save()
            except Exception:  # noqa: BLE001
                pass
            lock.release()

    async def _typing_loop(self, update) -> None:
        """Keep Telegram's native 'typing…' indicator alive while the
        brain call is in flight, so the wait feels live instead of dead."""
        try:
            while True:
                try:
                    await update.effective_chat.send_action("typing")
                except Exception:  # noqa: BLE001
                    pass
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass

    async def _react(self, message, emoji: str) -> None:
        """Best-effort emoji reaction on a message (Bot API 7.0+).
        Silently no-ops on older clients/servers that don't support it."""
        if not emoji:
            return
        try:
            await message.set_reaction(emoji)
        except Exception:  # noqa: BLE001
            pass

    # ── approval flow ───────────────────────────────
    async def _prompt_approval(
        self, update, context, tool_name: str, tool_args: dict,
        call_id: str | None = None, after_text: str | None = None,
    ) -> None:
        chat_id = update.effective_chat.id
        meta = self.registry.metadata().get(tool_name, {})
        desc = meta.get("destructive", False)
        marker = "⚠️ *Destructive action*" if desc else "🔐 *Approval needed*"
        args_str = ", ".join(f"{k}={v!r}" for k, v in tool_args.items()) or "(no args)"
        ptb = _load_ptb()
        # Two approval sources:
        #  • Model-driven (call_id set) — resolved via the brain.
        #  • Button-driven (call_id None) — Shutdown/Restart/file-delete
        #    bypass the model, so we stage the tool locally under a sentinel
        #    call_id and dispatch it directly on approval.
        if call_id is None:
            self._pending_button[chat_id] = (tool_name, tool_args)
            self._pending_at[f"__btn__:{chat_id}"] = time.time()
            cid = "__btn__"
        else:
            self._pending_approvals[chat_id] = call_id
            self._pending_at[call_id] = time.time()
            cid = call_id
        keyboard = ptb["InlineKeyboardMarkup"]([
            [
                ptb["InlineKeyboardButton"](
                    "✅ Approve",
                    callback_data=f"approve:{tool_name}:{cid}",
                ),
                ptb["InlineKeyboardButton"](
                    "❌ Deny",
                    callback_data=f"deny:{tool_name}:{cid}",
                ),
            ]
        ])
        await self._reply(
            update,
            f"{marker}\n\nJARVIS wants to run: `{tool_name}({args_str})`\n\n"
            f"Approve or deny?",
            reply_markup=keyboard, parse_mode="Markdown",
        )

    async def _resolve_approval(self, update, context, data: str) -> None:
        chat_id = update.effective_chat.id
        # data: "approve:<tool>:<call_id>" or "deny:<tool>:<call_id>"
        try:
            _, _tool, _cid = data.split(":", 2)
        except ValueError:
            return
        approved = data.startswith("approve:")

        # Button-driven approvals (Shutdown/Restart/file-delete) — the tool
        # was staged locally and is dispatched directly, no brain round-trip.
        if _cid == "__btn__":
            pending = self._pending_button.pop(chat_id, None)
            staged_at = self._pending_at.pop(f"__btn__:{chat_id}", 0)
            if not pending:
                await self._reply(update, "No pending approval to resolve.")
                return
            if time.time() - staged_at > APPROVE_TTL:
                await self._reply(update, "That approval has expired.")
                return
            if not approved:
                await self._reply(update, "❌ Denied — nothing was run.")
                return
            tool_name, tool_args = pending
            placeholder_id = await _safe_send(update.effective_chat, "🤖 running…")
            try:
                result = await asyncio.to_thread(
                    self.registry.dispatch, tool_name, tool_args
                )
            except Exception as exc:  # noqa: BLE001
                result = f"⚠ Error: {exc}"
            await _safe_edit(
                update.effective_chat, placeholder_id, f"✅ {result}",
            )
            return

        call_id = self._pending_approvals.pop(chat_id, "") or _cid
        if not call_id:
            await self._reply(update, "No pending approval to resolve.")
            return
        # Expire stale approvals
        if time.time() - self._pending_at.get(call_id, 0) > APPROVE_TTL:
            await self._reply(update, "That approval has expired.")
            return
        # We're acting on this approval now — drop its expiry bookkeeping.
        self._pending_at.pop(call_id, None)
        placeholder_id = await _safe_send(
            update.effective_chat, "🤖 resuming…"
        )
        try:
            def _consume():
                # Hold the memory lock *inside* the worker thread, around the
                # brain calls that actually mutate memory — not across the
                # await on the event loop (which would block every other chat
                # for the whole 10-100s round-trip while guarding nothing).
                with self._memory_lock:
                    self.brain.resolve_approval(call_id, approved)
                    _tokens: list[str] = []
                    _tools: list[dict] = []
                    _err = ""
                    for event in self.brain.continue_after_approval():
                        etype = event.get("type")
                        if etype == "token":
                            _tokens.append(event.get("text", ""))
                        elif etype == "tool_done":
                            _tools.append({
                                "name": event.get("name", ""),
                                "result": event.get("result", ""),
                            })
                        elif etype == "error":
                            _err = event.get("text", "")
                return _tokens, _tools, _err

            # brain.continue_after_approval() makes blocking HTTP calls — run
            # it off the event loop, same reasoning as _ask_brain.
            tokens, tool_results, err_text = await asyncio.to_thread(_consume)
            raw_text = "".join(tokens).strip() or err_text or (
                "✅ Done." if approved else "❌ Denied."
            )
            # The streamed tokens ARE the final reply. No second pass.
            final_text = raw_text
            final_text = self._maybe_attach_file(final_text, chat_id)
            await _safe_edit(
                update.effective_chat, placeholder_id, final_text,
            )
            await self._send_attached_file(chat_id)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            m = msg.lower()
            if "resource_exhausted" in m or "quota_exhausted" in m \
                    or ("429" in msg and ("quota" in m or "rate" in m)):
                friendly = (
                    "⏳ Both Gemini keys hit their rate limit during the "
                    "approval follow-up. Try again in a minute."
                )
            elif "401" in msg or "403" in msg or "api key" in m or "auth" in m:
                friendly = (
                    "🔑 Gemini rejected the API key. Open Settings in the "
                    "host GUI and re-paste your key from "
                    "https://aistudio.google.com/apikey."
                )
            else:
                friendly = f"⚠ Error during approval: {msg}"
            await _safe_edit(
                update.effective_chat, placeholder_id, friendly,
            )

    # ── auth gate ───────────────────────────────────
    def _gate(self, update) -> bool:
        chat_id = update.effective_chat.id
        if self._is_authorized(chat_id):
            return True
        # Async reply: schedule via the bot's event loop.
        async def _deny():
            await self._reply(
                update,
                "🔒 Not authorized. Send `/start` and then your access PIN.",
            )
        # We can't await from a sync gate, so fire-and-forget.
        try:
            self._app.create_task(_deny())  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        return False


# ── small utility functions ───────────────────────────
def _format_alert(text: str) -> str:
    """Render a watchdog/system alert as a clean Telegram card.

    Producers broadcast a short line (optionally prefixed with a severity
    icon like 🟡/🔴). We drop any legacy 🐶 prefix and add a bold header so
    proactive pushes read as alerts, not stray chat messages.
    """
    body = (text or "").strip()
    body = re.sub(r"^🐶\s*", "", body)
    if not body:
        body = "Something needs your attention."
    return f"*⚠️ JARVIS alert*\n{body}"


def _split_message(text: str, limit: int = MAX_MESSAGE) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # Try to split on a paragraph boundary first
        cut = text.rfind("\n\n", 0, limit)
        if cut == -1:
            cut = text.rfind("\n", 0, limit)
        if cut == -1 or cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut == -1 or cut < limit // 2:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    return chunks


async def _safe_send(chat, text: str):
    # One retry on transient failures (network blip, Telegram 5xx) — without
    # this, a computed reply can be lost silently even though the model
    # answered successfully.
    for attempt in range(2):
        try:
            msg = await chat.send_message(text[:MAX_MESSAGE])
            return msg.message_id
        except Exception:  # noqa: BLE001
            if attempt == 0:
                await asyncio.sleep(0.8)
    return None


# Keyword buckets for a lightweight, dependency-free "emotion" read on the
# assistant's own final reply — used to pick a Telegram reaction emoji so
# JARVIS's mood in the chat matches what it just said (not just plain text).
_EMOTION_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("😂", ("lol", "haha", "funny", "hilarious", "😂", "🤣")),
    ("😭", ("so sorry", "terrible news", "failed completely", "heartbroken", "😭")),
    ("😢", ("sorry", "unfortunately", "sad", "failed", "error", "couldn't", "can't", "unable")),
    ("🎉", ("congrat", "done!", "success", "completed successfully", "finished", "🎉", "great news")),
    ("🔥", ("awesome", "amazing", "excellent", "fantastic", "impressive")),
    ("🤩", ("exciting", "can't wait", "thrilled", "love this")),
    ("👍", ("sure", "done", "okay", "sounds good", "got it", "on it")),
    ("🤔", ("hmm", "not sure", "let me think", "unclear", "ambiguous")),
]


def _emotion_emoji(text: str) -> str:
    """Pick a reaction emoji reflecting the tone of JARVIS's own reply."""
    if not text:
        return ""
    low = text.lower()
    for emoji, keywords in _EMOTION_RULES:
        if any(k in low for k in keywords):
            return emoji
    return "❤"


async def _safe_edit(chat, message_id: int | None, text: str) -> None:
    if not message_id:
        await _safe_send(chat, text)
        return
    chunks = _split_message(text)
    try:
        await chat.edit_message_text(chunks[0], message_id=message_id)
    except Exception:  # noqa: BLE001
        await _safe_send(chat, chunks[0])
    for extra in chunks[1:]:
        await _safe_send(chat, extra)


# Tiny shim for buttons that need to invoke a command with args
class _fake_context:
    def __init__(self, cmd: str, args: list[str], real) -> None:
        self.args = args
        self._cmd = cmd
        self._real = real

    def __getattr__(self, item):
        return getattr(self._real, item)
