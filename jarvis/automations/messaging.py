"""Messaging automations — WhatsApp (more channels later)."""
from __future__ import annotations

import os
import re
import time
import urllib.parse
import webbrowser

from .. import contacts
from .registry import tool


def _looks_like_phone(s: str) -> bool:
    """True if `s` is (almost certainly) a phone number rather than a name:
    only digits, spaces, dashes, parens and an optional leading '+', with at
    least 10 digits once stripped. Names contain letters and won't match."""
    if re.search(r"[A-Za-z]", s):
        return False
    return len(re.sub(r"[^\d]", "", s)) >= 10


def _open_whatsapp_chat(phone: str, message: str) -> bool:
    """Open the given chat directly in the WhatsApp *desktop* app via its
    registered `whatsapp://` URI handler, prefilled with the message.

    Returns True if the desktop app was launched, False if it isn't
    installed/registered (caller should fall back to wa.me in the browser).
    """
    uri = f"whatsapp://send?phone={phone}&text={urllib.parse.quote(message)}"
    try:
        os.startfile(uri)  # noqa: S606 — Windows-only, resolves via registry
        return True
    except OSError:
        return False


def _find_whatsapp_window(timeout: float = 8.0):
    """Poll for the WhatsApp desktop window and return it once it appears."""
    import pygetwindow as gw
    deadline = time.time() + timeout
    while time.time() < deadline:
        for title in gw.getAllTitles():
            if "whatsapp" in title.lower():
                matches = gw.getWindowsWithTitle(title)
                if matches:
                    return matches[0]
        time.sleep(0.3)
    return None


def _type_text(text: str) -> None:
    """Type text into whatever has focus. Uses the clipboard so non-ASCII
    (emoji, Telugu/Hindi, etc.) survives — pyautogui.write() can't send
    characters outside its keyboard mapping."""
    import pyautogui
    try:
        import pyperclip
        pyperclip.copy(text)
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)  # let the app finish registering the paste
    except Exception:  # noqa: BLE001
        pyautogui.write(text, interval=0.02)


def _click_compose_box(win) -> None:
    """Click directly into the message compose box (bottom strip of the
    conversation pane) before typing. Selecting a chat from search doesn't
    always leave keyboard focus in the compose field — if focus is
    elsewhere, paste/typing silently lands in the wrong control and Enter
    has nothing real to send. A direct click removes that ambiguity."""
    import pyautogui
    try:
        x = win.left + win.width // 2
        y = win.top + win.height - 40  # compose box hugs the bottom edge
        pyautogui.click(x, y)
        time.sleep(0.2)
    except Exception:  # noqa: BLE001
        pass


def _raw_enter_keypress() -> None:
    """Inject Enter via the low-level Win32 keybd_event API instead of
    pyautogui's SendInput wrapper. Some Microsoft Store / UWP apps (WhatsApp
    Desktop included) run sandboxed and can silently drop certain synthetic
    SendInput events while still accepting real hardware-style key events —
    keybd_event goes through the older, lower-level injection path and gets
    through in cases where SendInput-based Enter presses are swallowed."""
    import ctypes
    VK_RETURN = 0x0D
    KEYEVENTF_KEYUP = 0x0002
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_RETURN, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)


def _click_send_button(win) -> None:
    """Backup: click WhatsApp Desktop's send button (bottom-right corner of
    the compose bar) so sending doesn't depend on a keyboard event at all.
    The button only renders once the compose box has text, so this is only
    useful as a follow-up after typing."""
    import pyautogui
    try:
        x = win.left + win.width - 30
        y = win.top + win.height - 40
        pyautogui.click(x, y)
    except Exception:  # noqa: BLE001
        pass


def _send_compose_box(win=None) -> None:
    """Submit whatever's in the message box. Waits 4s after typing so the
    app has fully registered the pasted text before Enter is sent (sending
    Enter too soon after a paste is a common reason it gets ignored), then
    tries three independent mechanisms so it doesn't hinge on any one of
    them actually reaching the app: a normal Enter keypress, a low-level
    raw Enter injection, and a direct click on the send button."""
    import pyautogui
    time.sleep(4.0)
    pyautogui.press("enter")
    time.sleep(0.3)
    try:
        _raw_enter_keypress()
    except Exception:  # noqa: BLE001
        pass
    if win is not None:
        time.sleep(0.2)
        _click_send_button(win)


def _launch_app_via_search(app_name: str) -> None:
    """Open any app through Windows Search: Win+S, wait 1s, type the app name,
    wait 1s, Enter. No global hotkeys — this is the one way JARVIS launches
    apps for automations, so it works no matter what shortcuts exist."""
    import pyautogui
    pyautogui.hotkey("win", "s")
    time.sleep(1.0)
    pyautogui.write(app_name, interval=0.05)
    time.sleep(1.0)
    pyautogui.press("enter")


def _open_whatsapp_chat_by_name(name: str):
    """Open WhatsApp desktop via Windows Search, search the name in its in-app
    chat search, and open the first result. Returns the WhatsApp window focused
    on that chat, or None if the app never came up. Shared by the message- and
    file-send workflows so 'search the person, then send' behaves the same.

    Deliberately paced so nothing runs together: launch WhatsApp and wait 3s,
    then search the person and wait 3s, then open the chat."""
    import pyautogui

    # 1. Launch WhatsApp through Windows Search, then wait 3s for it to come up.
    _launch_app_via_search("whatsapp")
    time.sleep(3.0)
    win = _find_whatsapp_window(timeout=8.0)
    if not win:
        return None
    try:
        win.activate()
    except Exception:  # noqa: BLE001
        pass
    time.sleep(0.8)

    # 2. Open the in-app chat search (Ctrl+F), clear any stray text, type the
    #    person's name, and wait 3s for results to populate.
    pyautogui.hotkey("ctrl", "f")
    time.sleep(0.6)
    pyautogui.hotkey("ctrl", "a")   # select whatever's in the search box…
    pyautogui.press("delete")       # …and clear it, so the name types clean
    time.sleep(0.2)
    _type_text(name)
    time.sleep(3.0)  # let search results fully populate after typing the name

    # 3. Open the top match (equivalent to clicking the person).
    pyautogui.press("down")
    pyautogui.press("enter")
    time.sleep(0.8)
    return win


def _set_clipboard_files(paths: list[str]) -> None:
    """Put file path(s) on the Windows clipboard as CF_HDROP, so they can be
    pasted (Ctrl+V) into apps that accept file drops — WhatsApp Desktop treats
    such a paste exactly like attaching the file."""
    import struct

    import win32clipboard  # from pywin32
    import win32con

    # DROPFILES header: pFiles offset (20), POINT(0,0), fNC=0, fWide=1 (unicode).
    header = struct.pack("<Iiiii", 20, 0, 0, 0, 1)
    joined = "\0".join(os.path.abspath(p) for p in paths) + "\0\0"
    payload = header + joined.encode("utf-16-le")

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_HDROP, payload)
    finally:
        win32clipboard.CloseClipboard()


def _send_via_desktop_search(contact_name: str, message: str) -> str:
    """Full UI workflow: launch WhatsApp -> search contact -> open chat ->
    type message -> send. Used when the whatsapp:// deep link doesn't land us
    in the app (not installed, or opened the browser instead)."""
    win = _open_whatsapp_chat_by_name(contact_name)
    if not win:
        return ""  # caller falls back further
    # Don't trust that focus landed in the compose box — click it explicitly.
    _click_compose_box(win)
    _type_text(message)
    _send_compose_box(win)
    return f"Opened WhatsApp, found {contact_name}'s chat, and sent: {message!r}"


@tool(
    name="send_whatsapp",
    description=(
        "Send a WhatsApp message to ANYONE via the WhatsApp desktop app — the "
        "person does NOT need to be a saved JARVIS contact. Accepts either a "
        "name/alias OR a phone number:\n"
        "• A saved contact name/alias uses its stored number (fast deep link).\n"
        "• A raw phone number (10+ digits, e.g. '919876543210' or "
        "'+91 98765 43210') opens that chat directly via the whatsapp:// link.\n"
        "• Any other name is searched inside WhatsApp's own chat search and the "
        "top match is opened — works for anyone already in the user's WhatsApp.\n"
        "Always uses the desktop app, never the browser. Requires user approval."
    ),
    requires_approval=True,
    destructive=True,
    parameters={
        "type": "object",
        "properties": {
            "contact": {"type": "string", "description": (
                "Who to message: a saved name/alias (e.g. 'akka', 'mom'), any "
                "name to search in WhatsApp (e.g. 'Ravi'), or a phone number.")},
            "message": {"type": "string", "description": "The message to send."},
        },
        "required": ["contact", "message"],
    },
)
def send_whatsapp(contact: str, message: str) -> str:
    # Resolve the target to a phone number (fast deep-link path) or a name to
    # search inside WhatsApp. A saved JARVIS contact is a convenience, not a
    # requirement — any name or number the user's WhatsApp knows will work.
    phone = ""
    search_name = ""

    c = contacts.lookup(contact)
    if c and c.get("phone_e164"):
        if "whatsapp" in c.get("apps", ["whatsapp"]):
            phone = c["phone_e164"]
            search_name = c["name"]
        else:
            return f"{c['name']} is not enabled for WhatsApp."
    elif _looks_like_phone(contact):
        try:
            phone = contacts._normalize_phone(contact)
        except ValueError as exc:
            return str(exc)
    else:
        # Not saved and not a number → treat the raw input as a name to search.
        search_name = contact

    # Fast path: we have a number → try the whatsapp:// deep link first.
    if phone:
        _open_whatsapp_chat(phone, message)
        win = _find_whatsapp_window(timeout=4.0)
        if win:
            try:
                win.activate()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.8)
            try:
                _click_compose_box(win)
                _send_compose_box(win)
                who = search_name or f"+{phone}"
                return f"Sent WhatsApp message to {who}: {message!r}"
            except ImportError:
                return "Opened WhatsApp with the message pre-filled. Press Enter to send."
            except Exception as exc:  # noqa: BLE001
                return f"Opened WhatsApp but couldn't press Enter: {exc}"
        # Deep link didn't land in the app. If we also have a name, fall through
        # to the in-app search workflow; otherwise fall back to WhatsApp Web.
        if not search_name:
            url = f"https://wa.me/{phone}?text={urllib.parse.quote(message)}"
            webbrowser.open(url)
            time.sleep(2.5)
            try:
                _send_compose_box()
            except Exception:  # noqa: BLE001
                return "Opened WhatsApp Web with the message pre-filled. Press Enter to send."
            return f"Sent WhatsApp message to +{phone} via WhatsApp Web: {message!r}"

    # Name path (no number, or deep link failed): full Win+S → search → chat
    # → type → send workflow, the same one send_whatsapp_file uses.
    try:
        result = _send_via_desktop_search(search_name, message)
        if result:
            return result
    except Exception as exc:  # noqa: BLE001
        return f"WhatsApp desktop automation failed: {exc}. Is the app installed?"

    return (f"Couldn't open WhatsApp to message {search_name!r}. "
            "Is WhatsApp Desktop installed?")


@tool(
    name="send_whatsapp_file",
    description=(
        "Send one or more files to ANYONE on WhatsApp via the desktop app. "
        "Workflow: opens WhatsApp, searches the given person's name in the "
        "in-app chat search, opens their chat, attaches the file(s) by pasting "
        "them, adds an optional caption, and sends. The person does NOT need to "
        "be a saved JARVIS contact — any name in the user's WhatsApp works. "
        "Use absolute file paths."
    ),
    requires_approval=True,
    destructive=True,
    parameters={
        "type": "object",
        "properties": {
            "person": {"type": "string",
                        "description": "Name to search in WhatsApp (e.g. 'Ravi', 'Mom')."},
            "files": {"type": "array", "items": {"type": "string"},
                       "description": "Absolute path(s) to the file(s) to send."},
            "caption": {"type": "string",
                         "description": "Optional caption/message to send with the file(s)."},
        },
        "required": ["person", "files"],
    },
)
def send_whatsapp_file(person: str, files, caption: str = "") -> str:
    # Accept either a single path string or a list of paths.
    raw = [files] if isinstance(files, str) else list(files or [])
    if not raw:
        return "No file given to send. Tell me which file to send."

    resolved: list[str] = []
    missing: list[str] = []
    for f in raw:
        p = os.path.abspath(os.path.expanduser(os.path.expandvars(str(f))))
        (resolved if os.path.isfile(p) else missing).append(p)
    if missing:
        return "These file(s) don't exist: " + ", ".join(missing)

    win = _open_whatsapp_chat_by_name(person)
    if not win:
        return (f"Couldn't open WhatsApp to send to {person}. "
                "Is WhatsApp Desktop installed?")

    _click_compose_box(win)
    try:
        _set_clipboard_files(resolved)
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't stage the file(s) on the clipboard: {exc}"

    import pyautogui
    pyautogui.hotkey("ctrl", "v")
    time.sleep(2.5)  # let WhatsApp build the attachment preview
    if caption:
        _type_text(caption)
        time.sleep(0.3)
    # The attachment preview sends on Enter; try both paths like _send_compose_box.
    pyautogui.press("enter")
    time.sleep(0.3)
    try:
        _raw_enter_keypress()
    except Exception:  # noqa: BLE001
        pass

    names = ", ".join(os.path.basename(p) for p in resolved)
    tail = f" with caption {caption!r}" if caption else ""
    return f"Sent {names} to {person} on WhatsApp{tail}."


@tool(
    name="list_contacts",
    description="List all saved contacts.",
)
def list_contacts() -> str:
    items = contacts.list_all()
    if not items:
        return "No contacts saved. Add one with: /contact add <name> <phone> [aliases...]"
    lines = []
    for c in items:
        aliases = ", ".join(c.get("aliases", []))
        apps = ", ".join(c.get("apps", []))
        lines.append(
            f"- {c['name']} (+{c['phone_e164']})  aliases=[{aliases}]  apps=[{apps}]"
        )
    return "\n".join(lines)


@tool(
    name="find_contact",
    description="Look up a contact by name or alias.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Name or alias to search."},
        },
        "required": ["query"],
    },
)
def find_contact(query: str) -> str:
    c = contacts.lookup(query)
    if not c:
        return f"No contact matching '{query}'."
    aliases = ", ".join(c.get("aliases", [])) or "(none)"
    return f"{c['name']} (+{c['phone_e164']})  aliases=[{aliases}]"
