"""Central configuration — loads from .env with sane defaults."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(ENV_PATH)

# Gemini models tried (in order) if the primary model errors out.
# Gemini 3 Flash is Google's free, unlimited tier as of 2026 — listed first.
# The 2.x models remain as fallbacks in case 3 Flash has a temporary outage
# or doesn't support a specific capability (vision, etc.) on this account.
# Fast/cheap models first (most quota headroom), heavier ones last as a
# final resort — bogus/unavailable entries just 404 and get skipped, so
# it's safe to list generously.
FALLBACK_MODELS = [
    "gemini-3-flash-preview",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-flash-latest",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-2.5-flash-lite",
    "gemini-pro-latest",
    "gemini-2.5-pro",  # smartest, lowest free quota — last resort
]
# Vision: Gemini is natively multimodal — one model covers text + images.
VISION_MODELS = [
    "gemini-3-flash-preview",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-pro-latest",
]

# Base URL for the Google AI Studio (Gemini) REST API.
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _b(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    # Primary Gemini API key (Google AI Studio).
    api_key: str = field(default_factory=lambda: os.getenv("JARVIS_GEMINI_KEY", ""))
    # Backup Gemini API keys — auto-used in order when earlier keys hit a
    # rate/quota limit. BACKUP is the 2nd key, BACKUP2 the 3rd, and so on.
    api_key_backup: str = field(
        default_factory=lambda: os.getenv("JARVIS_GEMINI_KEY_BACKUP", "")
    )
    api_key_backup2: str = field(
        default_factory=lambda: os.getenv("JARVIS_GEMINI_KEY_BACKUP2", "")
    )
    api_key_backup3: str = field(
        default_factory=lambda: os.getenv("JARVIS_GEMINI_KEY_BACKUP3", "")
    )
    # Overflow pool: paste any number of extra Gemini keys here, separated by
    # commas / spaces / newlines. All of them join the auto-rotation pool, so
    # you rarely hit "limit reached". Filled from Settings → Extra Gemini keys.
    extra_keys: str = field(
        default_factory=lambda: os.getenv("JARVIS_GEMINI_KEYS", "")
    )
    model: str = field(
        default_factory=lambda: os.getenv("JARVIS_MODEL", "gemini-3-flash-preview")
    )

    name: str = field(default_factory=lambda: os.getenv("JARVIS_NAME", "JARVIS"))
    wake_word: str = field(default_factory=lambda: os.getenv("JARVIS_WAKE_WORD", "jarvis").lower())

    voice_enabled: bool = field(default_factory=lambda: _b("JARVIS_VOICE", True))
    stt_enabled: bool = field(default_factory=lambda: _b("JARVIS_STT", True))
    # Double-clap desktop trigger (listens on the mic in the background).
    clap_enabled: bool = field(default_factory=lambda: _b("JARVIS_CLAP", True))
    # Full-trust / owner mode: when True, JARVIS runs every tool immediately
    # with no ✅/❌ approval prompt — even shutdown/restart/delete. Toggle off
    # in Settings to restore confirmations.
    owner_trust: bool = field(default_factory=lambda: _b("JARVIS_OWNER_TRUST", True))
    # Read this PC's Windows notifications: exposes read_notifications and
    # runs a background watcher that announces new ones via the AlertHub.
    notify_read_enabled: bool = field(default_factory=lambda: _b("JARVIS_NOTIFY_READ", True))

    # personality / UX
    persona: str = field(default_factory=lambda: os.getenv("JARVIS_PERSONA", "jarvis"))
    language: str = field(default_factory=lambda: os.getenv("JARVIS_LANG", "en"))
    theme: str = field(default_factory=lambda: os.getenv("JARVIS_THEME", "arc"))

    # mobile / LAN access PIN (empty = LAN disabled, localhost only)
    pin: str = field(default_factory=lambda: os.getenv("JARVIS_PIN", ""))

    # Telegram bot (empty token = bot disabled, even if enabled=True)
    telegram_token: str = field(default_factory=lambda: os.getenv("JARVIS_TELEGRAM_TOKEN", ""))
    telegram_enabled: bool = field(default_factory=lambda: _b("JARVIS_TELEGRAM_ENABLED", False))

    @property
    def has_key(self) -> bool:
        return bool(self.api_key) and "xxxx" not in self.api_key

    def has_backup_key(self) -> bool:
        return bool(self.api_key_backup) and "xxxx" not in self.api_key_backup

    @staticmethod
    def _valid_key(key: str) -> bool:
        return bool(key) and "xxxx" not in key

    def all_keys(self) -> list[str]:
        """Return every usable Gemini key in priority order, de-duplicated.

        Sources, in order:
          1. primary + the 3 named backups,
          2. JARVIS_GEMINI_KEY_BACKUP4, BACKUP5, … (scanned until a gap),
          3. the `extra_keys` overflow pool (comma/space/newline separated),
             from JARVIS_GEMINI_KEYS / Settings.
        More keys → the auto-rotation almost never runs out.
        """
        candidates: list[str] = [
            self.api_key, self.api_key_backup,
            self.api_key_backup2, self.api_key_backup3,
        ]
        # Numbered overflow env vars BACKUP4..BACKUP49 (stop after 3 misses).
        misses = 0
        for i in range(4, 50):
            v = os.getenv(f"JARVIS_GEMINI_KEY_BACKUP{i}", "")
            if v:
                candidates.append(v)
                misses = 0
            else:
                misses += 1
                if misses >= 3:
                    break
        # Free-form pool: split on comma / whitespace / newline.
        for tok in re.split(r"[,\s]+", self.extra_keys or ""):
            if tok:
                candidates.append(tok)

        out: list[str] = []
        for key in candidates:
            key = key.strip()
            if self._valid_key(key) and key not in out:
                out.append(key)
        return out

    def validate(self) -> None:
        if not self.has_key:
            raise SystemExit(
                "\n[config] JARVIS_GEMINI_KEY is missing or still the placeholder.\n"
                "  1. Copy .env.example to .env\n"
                "  2. Paste your key from https://aistudio.google.com/apikey\n"
            )

    def update(self, **kwargs) -> None:
        """Set any fields at runtime (from the UI) and persist known ones to .env."""
        persist = kwargs.pop("persist", True)
        for key, val in kwargs.items():
            if val is None:
                continue
            if hasattr(self, key):
                setattr(self, key, val.strip() if isinstance(val, str) else val)
        if persist:
            self._save_env()

    def _save_env(self) -> None:
        """Write current settings back to .env, preserving unknown lines and
        inline comments (e.g. 'KEY=value # note' stays 'KEY=newvalue # note')."""
        mapping = {
            "JARVIS_GEMINI_KEY": self.api_key,
            "JARVIS_GEMINI_KEY_BACKUP": self.api_key_backup,
            "JARVIS_GEMINI_KEY_BACKUP2": self.api_key_backup2,
            "JARVIS_GEMINI_KEY_BACKUP3": self.api_key_backup3,
            "JARVIS_GEMINI_KEYS": self.extra_keys,
            "JARVIS_MODEL": self.model,
            "JARVIS_PERSONA": self.persona,
            "JARVIS_LANG": self.language,
            "JARVIS_THEME": self.theme,
            "JARVIS_PIN": self.pin,
            "JARVIS_TELEGRAM_TOKEN": self.telegram_token,
            "JARVIS_TELEGRAM_ENABLED": "1" if self.telegram_enabled else "0",
            "JARVIS_CLAP": "1" if self.clap_enabled else "0",
            "JARVIS_OWNER_TRUST": "1" if self.owner_trust else "0",
            "JARVIS_NOTIFY_READ": "1" if self.notify_read_enabled else "0",
        }
        seen: set[str] = set()
        lines: list[str] = []
        if ENV_PATH.exists():
            for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
                stripped = line.lstrip()
                # Preserve comments and blank lines as-is.
                if not stripped or stripped.startswith("#"):
                    lines.append(line)
                    continue
                if "=" not in line:
                    lines.append(line)
                    continue
                key, _, rest = line.partition("=")
                key = key.strip()
                if key in mapping:
                    # Preserve any inline comment after the value.
                    inline_comment = ""
                    hash_idx = rest.find(" #")
                    if hash_idx != -1:
                        inline_comment = " " + rest[hash_idx + 1:].rstrip()
                    lines.append(f"{key}={mapping[key]}{inline_comment}")
                    seen.add(key)
                else:
                    lines.append(line)
        for key, val in mapping.items():
            if key not in seen:
                lines.append(f"{key}={val}")
        ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


CONFIG = Config()
