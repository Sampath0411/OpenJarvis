"""Read this PC's Windows notifications.

Windows stores delivered toast notifications in a SQLite database:
    %LOCALAPPDATA%\\Microsoft\\Windows\\Notifications\\wpndatabase.db

The live file is locked (WAL), so we copy it to a temp file and read that.
Each row in `Notification` has a `Payload` (toast XML) and a `HandlerId` that
joins to `NotificationHandler.RecordId` → `PrimaryId` (the app's AUMID).

Two entry points:
- `read_notifications(limit, after_id)` — on-demand snapshot, newest first.
- `NotificationWatcher` — a daemon thread that announces NEW notifications via
  a sink callback (wired to the Watchdog so they hit the GUI footer + Telegram).

Everything here is best-effort: payload shapes vary and the DB can be missing
on non-Windows, so every path degrades to an empty list rather than raising.
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

_DB_PATH = os.path.expandvars(
    r"%LOCALAPPDATA%\Microsoft\Windows\Notifications\wpndatabase.db"
)

# FILETIME epoch: 100-nanosecond ticks since 1601-01-01 UTC.
_FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)

# A few AUMIDs worth prettifying; everything else is cleaned heuristically.
_APP_NAMES = {
    "whatsappdesktop": "WhatsApp",
    "telegram": "Telegram",
    "olk": "Outlook",
    "outlook": "Outlook",
    "teams": "Teams",
    "chrome": "Chrome",
    "msedge": "Edge",
    "spotify": "Spotify",
    "windowssecurity": "Windows Security",
    "windows.systemtoast.batterysaver": "Battery",
}

_TEXT_RE = re.compile(r"<text[^>]*>(.*?)</text>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _friendly_app(primary_id: str) -> str:
    """Turn an AUMID / handler id into a readable app name."""
    if not primary_id:
        return "System"
    pid = primary_id
    # Drop the "!App" entry-point suffix and the "_<publisherhash>" segment.
    pid = pid.split("!", 1)[0]
    pid = re.sub(r"_[a-z0-9]+$", "", pid, flags=re.I)
    low = pid.lower()
    for key, name in _APP_NAMES.items():
        if key in low:
            return name
    # Package family like "5319275A.WhatsAppDesktop" → take the last dotted part.
    tail = pid.split(".")[-1]
    # A bare .exe path or GUID → strip to something short.
    tail = tail.split("\\")[-1].split("/")[-1]
    tail = tail[:-4] if tail.lower().endswith(".exe") else tail
    return tail or "System"


def _unescape(s: str) -> str:
    return (
        s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        .replace("&quot;", '"').replace("&apos;", "'").replace("&#160;", " ")
        .strip()
    )


def _parse_payload(payload) -> tuple[str, str]:
    """Return (title, body) parsed from a toast payload. Either may be ''."""
    if payload is None:
        return "", ""
    if isinstance(payload, (bytes, bytearray)):
        text = payload.decode("utf-8", "ignore")
    else:
        text = str(payload)
    parts = [_unescape(_TAG_RE.sub("", m)) for m in _TEXT_RE.findall(text)]
    # Drop empties and unresolved resource placeholders (ms-resource://…),
    # which are machine strings, not something worth reading back.
    parts = [p for p in parts if p and not p.lower().startswith("ms-resource:")]
    # Collapse duplicate lines (some toasts repeat the same string in title+body).
    seen: list[str] = []
    for p in parts:
        if p not in seen:
            seen.append(p)
    parts = seen
    if not parts:
        return "", ""
    title = parts[0]
    body = " · ".join(parts[1:])
    return title, body


def _filetime_to_local(ft) -> datetime | None:
    try:
        dt = _FILETIME_EPOCH + timedelta(microseconds=int(ft) / 10)
        return dt.astimezone()  # → local timezone
    except Exception:  # noqa: BLE001
        return None


def _humanize(dt: datetime | None) -> str:
    if dt is None:
        return ""
    now = datetime.now(dt.tzinfo)
    secs = (now - dt).total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return dt.strftime("%b %d %H:%M")


def read_notifications(limit: int = 10, after_id: int | None = None) -> list[dict]:
    """Snapshot recent Windows notifications, newest first.

    Each item: {id, app, title, body, ts (datetime|None), when (str)}.
    `after_id` (if given) restricts results to Notification.Id > after_id —
    used by the live watcher to fetch only what's new.
    """
    if not os.path.exists(_DB_PATH):
        return []
    tmp = os.path.join(
        tempfile.gettempdir(), f"jarvis_wpn_{os.getpid()}.db"
    )
    try:
        shutil.copy2(_DB_PATH, tmp)
    except Exception:  # noqa: BLE001
        return []

    con = None
    try:
        con = sqlite3.connect("file:" + Path(tmp).as_posix() + "?mode=ro", uri=True)
        cur = con.cursor()
        where = "WHERE n.Payload IS NOT NULL"
        params: list = []
        if after_id is not None:
            where += " AND n.Id > ?"
            params.append(after_id)
        params.append(int(limit))
        cur.execute(
            f"""SELECT n.Id, n.Payload, n.ArrivalTime, h.PrimaryId
                FROM Notification n
                LEFT JOIN NotificationHandler h ON n.HandlerId = h.RecordId
                {where}
                ORDER BY n.ArrivalTime DESC
                LIMIT ?""",
            params,
        )
        rows = cur.fetchall()
    except Exception:  # noqa: BLE001
        return []
    finally:
        if con is not None:
            try:
                con.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            os.remove(tmp)
        except Exception:  # noqa: BLE001
            pass

    out: list[dict] = []
    for nid, payload, arrival, primary in rows:
        title, body = _parse_payload(payload)
        if not title and not body:
            continue  # data-only notification with nothing to show
        dt = _filetime_to_local(arrival)
        out.append({
            "id": nid,
            "app": _friendly_app(primary or ""),
            "title": title,
            "body": body,
            "ts": dt,
            "when": _humanize(dt),
        })
    return out


def format_line(n: dict) -> str:
    """One-line human summary of a notification dict."""
    bits = [n["app"]]
    text = " — ".join(p for p in (n.get("title"), n.get("body")) if p)
    if text:
        bits.append(text)
    line = ": ".join(bits) if len(bits) > 1 else bits[0]
    when = n.get("when")
    return f"{line} ({when})" if when else line


def _max_notification_id() -> int | None:
    """Highest Notification.Id currently in the DB (across ALL rows, including
    text-less/data notifications). Used to prime the watcher so the existing
    backlog isn't announced — must be MAX(Id), not the newest-by-arrival row,
    because Id and ArrivalTime don't perfectly correlate."""
    if not os.path.exists(_DB_PATH):
        return None
    tmp = os.path.join(tempfile.gettempdir(), f"jarvis_wpn_max_{os.getpid()}.db")
    try:
        shutil.copy2(_DB_PATH, tmp)
    except Exception:  # noqa: BLE001
        return None
    con = None
    try:
        con = sqlite3.connect("file:" + Path(tmp).as_posix() + "?mode=ro", uri=True)
        row = con.execute("SELECT MAX(Id) FROM Notification").fetchone()
        return int(row[0]) if row and row[0] is not None else None
    except Exception:  # noqa: BLE001
        return None
    finally:
        if con is not None:
            try:
                con.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            os.remove(tmp)
        except Exception:  # noqa: BLE001
            pass


class NotificationWatcher:
    """Poll the notification DB and announce NEW toasts via a sink callback.

    `sink(message)` is called for each new notification (wired to
    Watchdog.push so it reaches the GUI footer + Telegram). Only notifications
    that arrive AFTER the watcher starts are announced — the existing backlog
    is skipped so you're not spammed at launch.
    """

    def __init__(self, sink: Callable[[str], None] | None = None,
                 interval: int = 6) -> None:
        self._sink = sink
        self.interval = interval
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_id: int | None = None

    def start(self) -> bool:
        if self._running:
            return True
        if not os.path.exists(_DB_PATH):
            print("[notify] no Windows notification database on this system.")
            return False
        # Prime to the current newest id so we skip the backlog.
        self._last_id = _max_notification_id()
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="jarvis-notify",
        )
        self._thread.start()
        print("[notify] watcher started")
        return True

    def stop(self) -> None:
        self._running = False

    def is_alive(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        while self._running:
            try:
                fresh = read_notifications(limit=20, after_id=self._last_id)
                # Announce oldest-first so order reads naturally.
                for n in reversed(fresh):
                    if self._last_id is None or n["id"] > self._last_id:
                        self._last_id = n["id"]
                        msg = f"🔔 {format_line(n)}"
                        print(f"[notify] {msg}")
                        if self._sink is not None:
                            try:
                                self._sink(msg)
                            except Exception:  # noqa: BLE001
                                pass
            except Exception:  # noqa: BLE001
                pass
            time.sleep(self.interval)
