"""File automations — create, read, append, list, move, delete files anywhere.

Two layers:
- Sandboxed (existing): ~/jarvis_workspace, for casual notes.
- Anywhere: any path the user explicitly requests, subject to a denylist of
  system directories (C:\\Windows, C:\\Program Files, etc.) for safety.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .registry import tool

# All file ops are sandboxed to ~/jarvis_workspace to avoid accidents.
WORKSPACE = Path.home() / "jarvis_workspace"
WORKSPACE.mkdir(parents=True, exist_ok=True)


def _safe(path: str) -> Path:
    p = (WORKSPACE / path).resolve()
    if WORKSPACE.resolve() not in p.parents and p != WORKSPACE.resolve():
        raise ValueError("Path escapes the JARVIS workspace.")
    return p


# ── system directory denylist for anywhere-ops ──────
def _is_blocked(path: str) -> bool:
    """True if the path is in a protected system directory."""
    try:
        p = Path(path).resolve()
    except OSError:
        # Malformed path — let the caller's own error handling surface a
        # friendly message rather than crashing here.
        return False
    blocked = [
        Path("C:/Windows"),
        Path("C:/Windows/System32"),
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
        Path("C:/ProgramData"),
        Path("/System"),
        Path("/usr"),
        Path("/bin"),
        Path("/sbin"),
        Path("/etc"),
    ]
    for b in blocked:
        try:
            if p == b or b in p.parents:
                return True
        except OSError:
            continue
    return False


@tool(
    name="write_file",
    description="Create or overwrite a text file in the JARVIS workspace (~/jarvis_workspace).",
    parameters={
        "type": "object",
        "properties": {
            "filename": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["filename", "content"],
    },
)
def write_file(filename: str, content: str) -> str:
    try:
        p = _safe(filename)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} chars to {p}"
    except (ValueError, OSError) as exc:
        return f"Couldn't write {filename}: {exc}"


@tool(
    name="append_file",
    description="Append text to a file in the JARVIS workspace (creates it if missing).",
    parameters={
        "type": "object",
        "properties": {
            "filename": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["filename", "content"],
    },
)
def append_file(filename: str, content: str) -> str:
    try:
        p = _safe(filename)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(content)
        return f"Appended to {p}"
    except (ValueError, OSError) as exc:
        return f"Couldn't append to {filename}: {exc}"


@tool(
    name="read_file",
    description="Read a text file from the JARVIS workspace.",
    parameters={
        "type": "object",
        "properties": {"filename": {"type": "string"}},
        "required": ["filename"],
    },
)
def read_file(filename: str) -> str:
    try:
        p = _safe(filename)
        if not p.exists():
            return f"{filename} does not exist."
        return p.read_text(encoding="utf-8")[:4000]
    except (ValueError, OSError) as exc:
        return f"Couldn't read {filename}: {exc}"


@tool(
    name="list_files",
    description="List files in the JARVIS workspace.",
)
def list_files() -> str:
    try:
        items = [str(p.relative_to(WORKSPACE)) for p in WORKSPACE.rglob("*") if p.is_file()]
        return "\n".join(items) if items else "Workspace is empty."
    except OSError as exc:
        return f"Couldn't list the workspace: {exc}"


# ── anywhere file operations (free by default; delete still requires approval) ─
@tool(
    name="write_file_anywhere",
    description=(
        "Create or overwrite a text file at any path the user has access to. "
        "Refuses to write inside protected system directories."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Full path to the file, e.g. C:\\Users\\sampa\\Desktop\\notes.txt"},
            "content": {"type": "string", "description": "The text to write."},
        },
        "required": ["path", "content"],
    },
)
def write_file_anywhere(path: str, content: str) -> str:
    if _is_blocked(path):
        return f"Refused: '{path}' is in a protected system directory."
    p = Path(path).expanduser()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} chars to {p}"
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't write {p}: {exc}"


@tool(
    name="append_file_anywhere",
    description=(
        "Append text to any file the user has access to. Refuses to write "
        "inside protected system directories."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Full path to the file."},
            "content": {"type": "string", "description": "Text to append."},
        },
        "required": ["path", "content"],
    },
)
def append_file_anywhere(path: str, content: str) -> str:
    if _is_blocked(path):
        return f"Refused: '{path}' is in a protected system directory."
    p = Path(path).expanduser()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(content)
        return f"Appended to {p}"
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't append to {p}: {exc}"


@tool(
    name="read_file_anywhere",
    description="Read a text file from any path the user has access to.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Full path to the file."},
        },
        "required": ["path"],
    },
)
def read_file_anywhere(path: str) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"{path} does not exist."
    try:
        return p.read_text(encoding="utf-8", errors="ignore")[:4000]
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't read {p}: {exc}"


@tool(
    name="delete_file",
    description="Delete a file or directory at any path. Destructive — requires approval.",
    requires_approval=True,
    destructive=True,
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Full path to delete."},
        },
        "required": ["path"],
    },
)
def delete_file(path: str) -> str:
    if _is_blocked(path):
        return f"Refused: '{path}' is in a protected system directory."
    p = Path(path).expanduser()
    if not p.exists():
        return f"{path} does not exist."
    try:
        if p.is_dir():
            shutil.rmtree(p)
            return f"Deleted directory {p}"
        p.unlink()
        return f"Deleted file {p}"
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't delete {p}: {exc}"


@tool(
    name="move_file",
    description=(
        "Move a file or directory to a new path. Refuses to touch protected "
        "system directories."
    ),
    parameters={
        "type": "object",
        "properties": {
            "src": {"type": "string", "description": "Source path."},
            "dst": {"type": "string", "description": "Destination path."},
        },
        "required": ["src", "dst"],
    },
)
def move_file(src: str, dst: str) -> str:
    if _is_blocked(src) or _is_blocked(dst):
        return "Refused: source or destination is in a protected system directory."
    s, d = Path(src).expanduser(), Path(dst).expanduser()
    if not s.exists():
        return f"{src} does not exist."
    try:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s), str(d))
        return f"Moved {s} → {d}"
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't move: {exc}"


@tool(
    name="copy_file",
    description="Copy a file or directory to a new path. Non-destructive.",
    parameters={
        "type": "object",
        "properties": {
            "src": {"type": "string", "description": "Source path."},
            "dst": {"type": "string", "description": "Destination path."},
        },
        "required": ["src", "dst"],
    },
)
def copy_file(src: str, dst: str) -> str:
    if _is_blocked(src) or _is_blocked(dst):
        return "Refused: source or destination is in a protected system directory."
    s, d = Path(src).expanduser(), Path(dst).expanduser()
    if not s.exists():
        return f"{src} does not exist."
    try:
        d.parent.mkdir(parents=True, exist_ok=True)
        if s.is_dir():
            shutil.copytree(str(s), str(d))
        else:
            shutil.copy2(str(s), str(d))
        return f"Copied {s} → {d}"
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't copy: {exc}"


@tool(
    name="rename_file",
    description=(
        "Rename a file or directory in place. Refuses to touch protected "
        "system directories."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file/directory."},
            "new_name": {"type": "string", "description": "New name (just the name, not a full path)."},
        },
        "required": ["path", "new_name"],
    },
)
def rename_file(path: str, new_name: str) -> str:
    if _is_blocked(path):
        return f"Refused: '{path}' is in a protected system directory."
    # `new_name` must be a bare name — reject separators / traversal so it can't
    # escape the parent dir into a protected location (move/copy already check
    # their destinations; rename must too).
    if new_name in ("", ".", "..") or "/" in new_name or "\\" in new_name:
        return "Refused: new_name must be a plain file name, not a path."
    p = Path(path).expanduser()
    if not p.exists():
        return f"{path} does not exist."
    new_path = p.parent / new_name
    if _is_blocked(str(new_path)):
        return f"Refused: '{new_path}' is in a protected system directory."
    try:
        p.rename(new_path)
        return f"Renamed {p} → {new_path}"
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't rename: {exc}"


@tool(
    name="list_anywhere",
    description="List files in a directory (one level deep).",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory to list, e.g. C:\\Users\\sampa\\Desktop"},
            "pattern": {"type": "string", "description": "Optional glob pattern, e.g. '*.py'", "default": "*"},
        },
        "required": ["path"],
    },
)
def list_anywhere(path: str, pattern: str = "*") -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"{path} does not exist."
    if not p.is_dir():
        return f"{path} is not a directory."
    try:
        entries = sorted(p.glob(pattern))
        if not entries:
            return f"No matches in {p}"
        return "\n".join(f"{'📁' if e.is_dir() else '📄'} {e.name}" for e in entries[:200])
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't list {p}: {exc}"


@tool(
    name="mkdir_anywhere",
    description=(
        "Create a directory (and any missing parent directories) at any "
        "path the user has access to. Refuses to create directories inside "
        "protected system paths."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Full path of the directory to create, e.g. D:\\projects\\mything."}
        },
        "required": ["path"],
    },
)
def mkdir_anywhere(path: str) -> str:
    if _is_blocked(path):
        return f"Refused: '{path}' is in a protected system directory."
    p = Path(path).expanduser()
    try:
        p.mkdir(parents=True, exist_ok=True)
        return f"Created {p}"
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't create {p}: {exc}"


@tool(
    name="search_files_recursive",
    description="Recursively search a directory tree for filenames matching a substring.",
    parameters={
        "type": "object",
        "properties": {
            "root": {"type": "string", "description": "Directory to search in."},
            "query": {"type": "string", "description": "Substring to match filenames against."},
            "max_results": {"type": "integer", "description": "Max results to return.", "default": 30},
        },
        "required": ["root", "query"],
    },
)
def search_files_recursive(root: str, query: str, max_results: int = 30) -> str:
    p = Path(root).expanduser()
    if not p.exists():
        return f"{root} does not exist."
    if not p.is_dir():
        return f"{root} is not a directory."
    q = query.lower()
    hits: list[Path] = []
    try:
        for child in p.rglob("*"):
            if q in child.name.lower():
                hits.append(child)
                if len(hits) >= max_results:
                    break
    except Exception as exc:  # noqa: BLE001
        return f"Search failed: {exc}"
    if not hits:
        return f"No files matching '{query}' under {p}."
    return "\n".join(str(h) for h in hits)
