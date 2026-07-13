"""Contact store — for messaging tools (WhatsApp, SMS, etc.).

Persists to ~/.jarvis/contacts.json. Each contact has:
- name: display name (e.g. "Akka")
- phone_e164: phone number in international format (e.g. "919876543210")
- aliases: other names the user might use ("akka", "sis")
- apps: which messaging apps are enabled (default ["whatsapp"])
- created_at: when the contact was added
- updated_at: when the contact was last modified

Use lookup(query) to find a contact by name or alias.
Use search(query) for fuzzy matching.
Use add() to add/update contacts.
Use remove() to delete contacts.
Use list_all() to get all contacts.

All operations automatically persist to disk.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

CONTACTS_FILE = Path.home() / ".jarvis" / "contacts.json"


def _load() -> list[dict]:
    if not CONTACTS_FILE.exists():
        return []
    try:
        data = json.loads(CONTACTS_FILE.read_text(encoding="utf-8"))
        return data.get("contacts", [])
    except (json.JSONDecodeError, OSError):
        return []


def _save(items: list[dict]) -> None:
    CONTACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONTACTS_FILE.write_text(
        json.dumps({"contacts": items}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _normalize_phone(phone: str) -> str:
    """Strip spaces, dashes, parens; ensure + prefix is dropped (we use e164 without +)."""
    digits = re.sub(r"[^\d]", "", phone)
    # Ensure it's a valid Indian or international number (at least 10 digits)
    if len(digits) < 10:
        raise ValueError(f"Phone number too short: {phone!r} (needs at least 10 digits)")
    return digits


def add(name: str, phone: str, aliases: list[str] | None = None,
        apps: list[str] | None = None) -> dict:
    """Add or update a contact. Returns the saved contact."""
    items = _load()
    phone_clean = _normalize_phone(phone)

    # Update if name matches
    for c in items:
        if c.get("name", "").lower() == name.lower():
            c["phone_e164"] = phone_clean
            # Normalize new aliases the same way the create path does, then
            # merge de-duplicated (order-preserving) so lookup() matches them.
            new_aliases = [a.lower().strip() for a in (aliases or []) if a.strip()]
            c["aliases"] = list(dict.fromkeys(c.get("aliases", []) + new_aliases))
            c["apps"] = list(set(c.get("apps", []) + (apps or ["whatsapp"])))
            c["updated_at"] = datetime.now().isoformat(timespec="seconds")
            _save(items)
            return c

    new = {
        "name": name.strip(),
        "phone_e164": phone_clean,
        "aliases": [a.lower().strip() for a in (aliases or []) if a.strip()],
        "apps": list(apps or ["whatsapp"]),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    items.append(new)
    try:
        _save(items)
    except OSError as exc:
        raise OSError(f"Could not save contacts: {exc}") from exc
    return new


def remove(query: str) -> int:
    """Remove contacts matching name or alias. Returns number removed."""
    items = _load()
    q = query.lower().strip()
    kept = [
        c for c in items
        if q != c.get("name", "").lower() and q not in [a.lower() for a in c.get("aliases", [])]
    ]
    removed = len(items) - len(kept)
    if removed:
        try:
            _save(kept)
        except OSError as exc:
            raise OSError(f"Could not save contacts: {exc}") from exc
    return removed


def lookup(query: str) -> dict | None:
    """Find a contact by name, alias, or fuzzy match.

    Priority: exact name > exact alias > substring name > substring alias.
    """
    items = _load()
    q = query.lower().strip()
    if not q:
        return None

    # exact name
    for c in items:
        if c.get("name", "").lower() == q:
            return c
    # exact alias
    for c in items:
        if q in [a.lower() for a in c.get("aliases", [])]:
            return c
    # substring name
    for c in items:
        if q in c.get("name", "").lower():
            return c
    # substring alias
    for c in items:
        if any(q in a.lower() for a in c.get("aliases", [])):
            return c
    return None


def list_all() -> list[dict]:
    return _load()


def backup_contacts() -> Path:
    """Create a timestamped backup of contacts. Returns the backup file path."""
    items = _load()
    if not items:
        return CONTACTS_FILE
    backup_dir = CONTACTS_FILE.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"contacts_backup_{timestamp}.json"
    backup_path.write_text(
        json.dumps({"contacts": items}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return backup_path


def restore_contacts(backup_path: Path | str) -> bool:
    """Restore contacts from a backup file. Returns True on success."""
    try:
        data = json.loads(Path(backup_path).read_text(encoding="utf-8"))
        items = data.get("contacts", [])
        _save(items)
        return True
    except (json.JSONDecodeError, OSError):
        return False


def export_to_text() -> str:
    """Export all contacts as a formatted text string."""
    items = _load()
    if not items:
        return "No contacts saved."
    lines = ["=== Contacts ===", ""]
    for c in sorted(items, key=lambda x: x.get("name", "").lower()):
        aliases = c.get("aliases", [])
        apps = c.get("apps", [])
        lines.append(f"Name: {c.get('name', 'Unknown')}")
        lines.append(f"Phone: +{c.get('phone_e164', 'N/A')}")
        if aliases:
            lines.append(f"Aliases: {', '.join(aliases)}")
        if apps:
            lines.append(f"Apps: {', '.join(apps)}")
        lines.append("")
    return "\n".join(lines)
