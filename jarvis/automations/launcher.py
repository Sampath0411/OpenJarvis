"""App/tab launcher using the Windows search (Win+S) flow the user prefers."""
from __future__ import annotations

import os
import platform
import subprocess
import time
import webbrowser
from pathlib import Path

from .registry import tool

IS_WIN = platform.system() == "Windows"


# ── smart-open: a single entry point that figures out what the user means ─
# Words that, when present, force "open the file in the user's default app"
# (or "open the folder in File Explorer" when the request is about a folder).
_APP_LIKE_TOKENS = {
    "app", "application", "program", "software", "tool", "launcher", "exe",
}
_BROWSER_TOKENS = {
    "browser", "chrome", "firefox", "edge", "safari", "internet",
}
# If the user says any of these, they want the folder opened in Explorer,
# not a file inside it.
_EXPLORER_TOKENS = {
    "explorer", "file explorer", "files app", "show in folder",
    "open folder", "show folder", "this pc",
}
# Known Windows user-profile folder keywords → resolved to special paths.
_KNOWN_FOLDERS = {
    "desktop": Path.home() / "Desktop",
    "documents": Path.home() / "Documents",
    "downloads": Path.home() / "Downloads",
    "videos": Path.home() / "Videos",
    "pictures": Path.home() / "Pictures",
    "music": Path.home() / "Music",
    "home": Path.home(),
    "user": Path.home(),
    "this pc": Path("C:\\"),
    "c drive": Path("C:\\"),
    "d drive": Path("D:\\") if (Path("D:\\")).exists() else None,
    "e drive": Path("E:\\") if (Path("E:\\")).exists() else None,
}


def _strip_explorer_hints(text: str) -> str:
    """Remove the words that the user uses to indicate 'open in File Explorer'.

    So 'open videos in file explorer' becomes 'videos' before we look it up.
    """
    out = text
    for hint in _EXPLORER_TOKENS:
        out = out.replace(hint, " ")
    return " ".join(out.split())


def _has_any(text: str, words: set[str]) -> bool:
    t = text.lower()
    return any(w in t.split() or w in t for w in words)


def _find_file(query: str, max_search_seconds: float = 6.0) -> Path | None:
    """Search common locations for a file/folder matching `query` by name.

    Returns the first match, or None. Limited by time (not depth) so we
    don't lock up on huge drives.
    """
    if not query:
        return None
    # Strip extensions the user might have included to widen the search.
    q = query.strip().strip("'\"")
    # Build the candidate name: try the query as-is, then with each common
    # extension appended if it doesn't have one.
    exts = [""]  # already has extension
    if "." not in q:
        exts += [".txt", ".md", ".docx", ".pdf", ".png", ".jpg", ".jpeg",
                 ".mp4", ".mp3", ".xlsx", ".csv", ".py", ".json", ".html",
                 ".log"]
    candidates: list[str] = []
    for e in exts:
        candidates.append(q + e)
        candidates.append(q.lower() + e)
        candidates.append(q.upper() + e)

    # Search roots: desktop, documents, downloads, current dir, home, jarvis_workspace.
    roots = []
    for k in ("Desktop", "Documents", "Downloads", "Videos", "Pictures"):
        p = Path.home() / k
        if p.exists():
            roots.append(p)
    roots.append(Path.cwd())
    roots.append(Path.home())
    workspace = Path.home() / "jarvis_workspace"
    if workspace.exists():
        roots.append(workspace)

    q_lower = q.lower()
    deadline = time.time() + max_search_seconds
    for root in roots:
        try:
            for child in root.rglob("*"):
                if time.time() > deadline:
                    return None
                name = child.name
                nl = name.lower()
                if nl == q_lower or nl == (q + ".txt") or nl.startswith(q_lower + "."):
                    return child
                # also accept the query as a substring for short queries.
                if len(q_lower) >= 3 and q_lower in nl:
                    return child
        except (PermissionError, OSError):
            continue
    return None


def _open_path(p: Path) -> str:
    """Open a file or folder using the OS default handler."""
    try:
        if IS_WIN:
            # os.startfile is the Windows-native "double-click" handler.
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return f"Opened {p}"
    except Exception as exc:  # noqa: BLE001
        return f"Found {p} but couldn't open it: {exc}"


def _launch_app(name: str) -> str:
    """Launch a known application. Falls back to Win+S for unknown names."""
    # If the user said "open chrome", they want Chrome — not a web search.
    if name.lower() in _BROWSER_TOKENS:
        try:
            if IS_WIN:
                subprocess.Popen("start chrome", shell=True)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", "-a", "Google Chrome"])
            else:
                subprocess.Popen(["google-chrome"])
            return f"Launched Chrome."
        except Exception as exc:  # noqa: BLE001
            return f"Couldn't launch Chrome: {exc}"

    # Generic: use os.startfile with a URI for known UWP/uri apps, else shell.
    try:
        if IS_WIN:
            subprocess.Popen(f"start {name}", shell=True)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-a", name])
        else:
            subprocess.Popen([name])
        return f"Launched {name}."
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't launch {name}: {exc}"


def windows_search_open(query: str) -> str:
    """Last-resort opener: drive the Windows Search box (Win+S → type → Enter)
    to open whatever `query` names. Falls back to a direct app launch when the
    UI-automation path isn't available (no pyautogui, or non-Windows)."""
    if not IS_WIN:
        return _launch_app(query)
    try:
        import pyautogui
    except Exception:  # noqa: BLE001
        return _launch_app(query)
    try:
        pyautogui.hotkey("win", "s")
        time.sleep(1.0)
        pyautogui.write(query, interval=0.03)
        time.sleep(1.0)
        pyautogui.press("enter")
        return f"Searched Windows for {query!r} and opened the top result."
    except Exception:  # noqa: BLE001
        return _launch_app(query)


@tool(
    name="smart_open",
    description=(
        "Open a file, folder, or application from a free-form user request like "
        "'open leave.txt', 'open videos in file explorer', 'open chrome', "
        "'show my downloads in file explorer', or 'open settings'. "
        "This tool figures out what the user wants and dispatches accordingly: "
        "it searches the filesystem for files/folders, opens known folders like "
        "Videos/Documents/Desktop in File Explorer, launches known apps directly, "
        "and falls back to Windows search (Win+S) only when nothing else matches."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "What to open. Examples: 'leave.txt', 'videos in file explorer', "
                    "'chrome', 'my resume', 'downloads in explorer'."
                ),
            }
        },
        "required": ["query"],
    },
)
def smart_open(query: str) -> str:
    """The one-stop 'open X' tool. Resolves intent and dispatches."""
    if not query or not query.strip():
        return "Tell me what to open (e.g. 'leave.txt', 'chrome', 'videos in file explorer')."

    raw = query.strip()
    lower = raw.lower()

    # 1. Does the user explicitly want File Explorer? ("videos in file explorer")
    wants_explorer = bool(_EXPLORER_TOKENS & set(lower.replace(",", " ").split()))
    if not wants_explorer:
        # also check substrings
        for hint in _EXPLORER_TOKENS:
            if hint in lower:
                wants_explorer = True
                break

    if wants_explorer:
        target = _strip_explorer_hints(raw).strip()
        # First, check the known-folder table.
        for k, p in _KNOWN_FOLDERS.items():
            if p and k in target.lower() and p.exists():
                if IS_WIN:
                    try:
                        subprocess.Popen(f'explorer "{p}"', shell=True)
                        return f"Opened {p} in File Explorer."
                    except Exception as exc:  # noqa: BLE001
                        return _open_path(p)
                return _open_path(p)
        # Otherwise search for a folder by name.
        # Try a fast file lookup; the result might be a directory.
        hit = _find_file(target, max_search_seconds=4.0)
        if hit and hit.is_dir():
            if IS_WIN:
                try:
                    subprocess.Popen(f'explorer "{hit}"', shell=True)
                    return f"Opened {hit} in File Explorer."
                except Exception:  # noqa: BLE001
                    pass
            return _open_path(hit)
        if hit and hit.is_file():
            # The user said "in file explorer" but we found a file — open
            # its parent folder with the file selected.
            if IS_WIN:
                try:
                    subprocess.Popen(f'explorer /select,"{hit}"', shell=True)
                    return f"Opened {hit.parent} in File Explorer with {hit.name} selected."
                except Exception:  # noqa: BLE001
                    pass
            return _open_path(hit.parent)
        # Last resort: hand the (cleaned) query to Windows Explorer directly.
        if IS_WIN:
            try:
                subprocess.Popen(f'explorer "{target}"', shell=True)
                return f"Asked Explorer to open {target}."
            except Exception as exc:  # noqa: BLE001
                return f"Couldn't open in Explorer: {exc}"
        return _open_path(Path(target))

    # 2. Does the query look like a file path or a known file (has an
    #    extension and we can find it on disk)?
    looks_like_file = "." in Path(raw).name and not _has_any(raw, _APP_LIKE_TOKENS)
    if looks_like_file:
        # First, treat the query as a path directly. Normalize slashes for
        # Windows so the path works both for `Path.exists()` and
        # `os.startfile`.
        try:
            direct = Path(raw).expanduser()
            if IS_WIN:
                direct = Path(os.path.normpath(str(direct)))
            direct = direct.resolve() if direct.parent.exists() else direct
        except (OSError, ValueError):
            direct = Path(raw).expanduser()
        if direct.exists():
            return _open_path(direct)
        # Otherwise search the filesystem by name.
        hit = _find_file(raw, max_search_seconds=6.0)
        if hit and hit.is_file():
            return _open_path(hit)
        if hit and hit.is_dir():
            return _open_path(hit)
        return f"Couldn't find a file named '{raw}' on Desktop, Documents, or Downloads."

    # 3. Does the query name a known folder (Videos, Desktop, Downloads…)?
    #    Single-word keys match on whole words (so "user" ≠ "username");
    #    multiword keys ("this pc", "c drive") match as substrings, since
    #    they can never be a single element of split().
    _folder_words = lower.split()
    for k, p in _KNOWN_FOLDERS.items():
        if not (p and p.exists()):
            continue
        matched = (k in lower) if " " in k else (k in _folder_words)
        if matched:
            if IS_WIN:
                try:
                    subprocess.Popen(f'explorer "{p}"', shell=True)
                    return f"Opened {p} in File Explorer."
                except Exception:  # noqa: BLE001
                    pass
            return _open_path(p)

    # 4. Maybe it's a known app the user just calls by name (chrome, vscode…).
    APP_ALIASES = {
        "notepad": "notepad",
        "calculator": "calc",
        "calc": "calc",
        "vscode": "code",
        "vs code": "code",
        "code": "code",
        "spotify": "spotify",
        "settings": "ms-settings:",
        "file explorer": "explorer",
        "explorer": "explorer",
        "cmd": "cmd",
        "terminal": "wt",
        "powershell": "powershell",
        "task manager": "taskmgr",
        "paint": "mspaint",
    }
    # Match the two-word alias first ("vs code", "file explorer", "task
    # manager") before falling back to the first word — otherwise multiword
    # aliases are unreachable because split()[0] never equals them.
    _app_words = lower.split()
    two_words = " ".join(_app_words[:2]) if len(_app_words) >= 2 else ""
    first_word = _app_words[0] if _app_words else ""
    alias_key = two_words if two_words in APP_ALIASES else (
        first_word if first_word in APP_ALIASES else ""
    )
    if alias_key:
        target = APP_ALIASES[alias_key]
        try:
            if IS_WIN:
                if target.endswith(":"):
                    # URI scheme (ms-settings:, etc.)
                    subprocess.Popen(f"start {target}", shell=True)
                else:
                    subprocess.Popen(f"start {target}", shell=True)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", "-a", target])
            else:
                subprocess.Popen([target])
            return f"Launched {alias_key}."
        except Exception as exc:  # noqa: BLE001
            return f"Couldn't launch {alias_key}: {exc}"

    # 5. Search for a folder by name (e.g. "open projects" → my projects folder).
    if not _has_any(raw, _APP_LIKE_TOKENS):
        hit = _find_file(raw, max_search_seconds=4.0)
        if hit and hit.is_dir():
            return _open_path(hit)
        if hit and hit.is_file():
            return _open_path(hit)

    # 6. Final fallback: ask Windows search to do it. (Better than nothing.)
    return windows_search_open(raw)


@tool(
    name="open_browser_tab",
    description="Open a website/tab directly in the default browser.",
    parameters={
        "type": "object",
        "properties": {
            "site": {"type": "string", "description": "URL or known site name (internshala, instagram, youtube, github, gmail)."}
        },
        "required": ["site"],
    },
)
def open_browser_tab(site: str) -> str:
    known = {
        "internshala": "https://internshala.com/internships/work-from-home-internships",
        "instagram": "https://www.instagram.com",
        "youtube": "https://www.youtube.com",
        "github": "https://github.com",
        "gmail": "https://mail.google.com",
        "chatgpt": "https://chat.openai.com",
    }
    url = known.get(site.strip().lower(), site.strip())
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url}"


# ── Download manager (yt-dlp) ───────────────────────


@tool(
    name="download_video",
    description=(
        "Download a YouTube video (or any supported URL) using yt-dlp. "
        "Saves to ~/jarvis_workspace/downloads/ by default. "
        "Supports videos, audio-only, and playlists."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Video/audio URL to download."},
            "format": {
                "type": "string",
                "enum": ["video", "audio"],
                "description": "'video' for mp4, 'audio' for mp3 (default video).",
                "default": "video",
            },
            "path": {"type": "string", "description": "Output folder (default ~/jarvis_workspace/downloads)."},
        },
        "required": ["url"],
    },
)
def download_video(url: str, format: str = "video", path: str = "") -> str:
    out_dir = Path(path).expanduser() if path else Path.home() / "jarvis_workspace" / "downloads"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Check if yt-dlp is installed
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, timeout=5)
    except FileNotFoundError:
        return "yt-dlp not installed. Run: pip install yt-dlp"
    except Exception:
        return "yt-dlp not installed. Run: pip install yt-dlp"

    cmd = [
        "yt-dlp",
        "-o", str(out_dir / "%(title)s.%(ext)s"),
        "--no-playlist",
        "--print", "after_move:filepath",
    ]
    if format == "audio":
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    else:
        cmd += ["-f", "best[height<=1080]"]

    cmd.append(url)

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,  # 10 min max
        )
    except subprocess.TimeoutExpired:
        return "Download timed out (10 min limit)."
    except Exception as exc:
        return f"Download failed: {exc}"

    if proc.returncode != 0:
        return f"Download error: {(proc.stderr or '')[:300]}"

    output = (proc.stdout or "").strip()
    if output:
        return f"✅ Downloaded: {output}"
    return f"✅ Download complete → {out_dir}"
