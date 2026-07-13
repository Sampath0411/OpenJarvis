"""Code intelligence — self-healing execution, code explanation, auto-documentation."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import requests

from config import CONFIG, GEMINI_BASE

from .registry import tool

WORKSPACE = Path.home() / "jarvis_workspace"


def _ask_gemini(prompt: str, model: str = "gemini-3-flash-preview") -> str:
    """Send a prompt to Gemini and return text response."""
    keys = CONFIG.all_keys()
    if not keys:
        return "No Gemini API key configured."
    url = f"{GEMINI_BASE}/{model}:generateContent"
    for key in keys:
        try:
            r = requests.post(
                url, params={"key": key}, timeout=30,
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096},
                },
            )
            if r.status_code == 200:
                data = r.json()
                parts = (data.get("candidates", [{}])[0]
                         .get("content", {}).get("parts", []))
                if parts:
                    return parts[0].get("text", "").strip()
            if r.status_code == 429:
                continue
            return f"API error {r.status_code}: {r.text[:200]}"
        except requests.RequestException as exc:
            return f"Network error: {exc}"
    return "All API keys exhausted or rate-limited."


# ── Self-healing code runner ─────────────────────────


@tool(
    name="run_self_healing",
    description=(
        "Run a Python file from disk and auto-fix it if it errors. "
        "JARVIS reads the error, asks Gemini for a fix, rewrites the file, "
        "and re-runs — up to 3 attempts. Returns the final output or the "
        "best error message if all attempts fail."
    ),
    requires_approval=True,
    destructive=True,
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Full path to the .py file to run and auto-fix."},
            "args": {"type": "string", "description": "Optional command-line arguments."},
            "max_attempts": {"type": "integer", "description": "Max fix-retry cycles (default 3).", "default": 3},
        },
        "required": ["path"],
    },
)
def run_self_healing(path: str, args: str = "", max_attempts: int = 3) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"File not found: {path}"
    if p.suffix.lower() != ".py":
        return f"Only .py files supported (got '{p.suffix}')"

    original = p.read_text(encoding="utf-8")
    attempt = 0
    last_output = ""

    while attempt < max_attempts:
        attempt += 1
        cmd = [sys.executable, str(p)]
        if args:
            cmd.extend(args.split())
        try:
            proc = subprocess.run(
                cmd, cwd=p.parent, capture_output=True, text=True,
                timeout=30, shell=False,
            )
        except subprocess.TimeoutExpired:
            return f"Attempt {attempt}: timed out after 30s."
        except Exception as exc:
            return f"Attempt {attempt}: execution error — {exc}"

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        last_output = stdout + (f"\n{stderr}" if stderr else "")

        if proc.returncode == 0:
            return (
                f"✅ Succeeded on attempt {attempt}.\n"
                f"Output:\n{last_output.strip()[:4000]}"
            )

        # Send error to Gemini for fixing
        fix_prompt = (
            f"The following Python script exited with code {proc.returncode}.\n"
            f"Error output:\n{stderr[:2000]}\n\n"
            f"Code:\n```python\n{p.read_text(encoding='utf-8')[:4000]}\n```\n\n"
            f"Fix the code. Reply with ONLY the corrected Python code, "
            f"no explanations, no markdown fences."
        )
        fixed = _ask_gemini(fix_prompt)
        if fixed.startswith("API error") or fixed.startswith("Network error"):
            return f"Attempt {attempt} failed — Gemini couldn't fix: {fixed}\n\nLast error:\n{stderr[:1000]}"

        # Clean Gemini's response — strip markdown fences if present
        fixed = fixed.strip()
        if fixed.startswith("```"):
            fixed = fixed.split("\n", 1)[-1] if "\n" in fixed else ""
        if fixed.endswith("```"):
            fixed = fixed.rsplit("```", 1)[0]
        fixed = fixed.strip()

        if not fixed:
            return f"Attempt {attempt}: Gemini returned empty fix.\nLast error:\n{stderr[:1000]}"

        p.write_text(fixed, encoding="utf-8")

    # All attempts exhausted
    return (
        f"❌ Failed after {max_attempts} attempts.\n"
        f"Last output:\n{last_output.strip()[:3000]}"
        f"\n\nOriginal code backed up — check ~/jarvis_workspace/"
    )


# ── Code explainer ──────────────────────────────────


@tool(
    name="explain_code",
    description=(
        "Read a code file and explain what it does in simple terms. "
        "Works with .py, .js, .ts, .html, .css, .java, .cpp, .go, .rs, "
        "and other common source files."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Full path to the source file."},
            "detail": {
                "type": "string",
                "enum": ["simple", "detailed"],
                "description": "'simple' = 2-3 sentence summary. 'detailed' = line-by-line breakdown.",
                "default": "simple",
            },
        },
        "required": ["path"],
    },
)
def explain_code(path: str, detail: str = "simple") -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"File not found: {path}"
    if not p.is_file():
        return f"Not a file: {path}"

    code = p.read_text(encoding="utf-8", errors="ignore")[:6000]
    ext = p.suffix.lower()

    detail_instr = (
        "Explain briefly in 2-3 sentences — what does this file do?"
        if detail == "simple"
        else "Give a detailed line-by-line explanation of what this code does."
    )

    lang = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".html": "HTML", ".css": "CSS",
        ".java": "Java", ".cpp": "C++", ".c": "C",
        ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
        ".php": "PHP", ".sh": "Shell", ".ps1": "PowerShell",
        ".sql": "SQL", ".md": "Markdown",
    }.get(ext, "code")

    prompt = (
        f"File: {p.name} ({lang}, {len(code)} chars)\n\n"
        f"```{lang.lower()}\n{code}\n```\n\n"
        f"{detail_instr}"
    )
    result = _ask_gemini(prompt)
    return f"📄 {p.name} ({lang})\n\n{result}"


# ── Auto-document projects ──────────────────────────


@tool(
    name="auto_document",
    description=(
        "Scan a project folder and generate a README.md for it. "
        "JARVIS reads all source files in the folder, understands what "
        "the project does, and writes a README.md inside it."
    ),
    parameters={
        "type": "object",
        "properties": {
            "folder": {"type": "string", "description": "Path to the project folder."},
            "overwrite": {
                "type": "boolean",
                "description": "Overwrite existing README.md if one exists (default false).",
                "default": False,
            },
        },
        "required": ["folder"],
    },
)
def auto_document(folder: str, overwrite: bool = False) -> str:
    root = Path(folder).expanduser()
    if not root.exists():
        return f"Folder not found: {folder}"
    if not root.is_dir():
        return f"Not a directory: {folder}"

    readme_path = root / "README.md"
    if readme_path.exists() and not overwrite:
        return f"README.md already exists at {readme_path}. Set overwrite=True to replace."

    # Gather project structure + contents
    source_exts = {".py", ".js", ".ts", ".html", ".css", ".java",
                    ".cpp", ".c", ".go", ".rs", ".rb", ".php", ".sh", ".sql", ".json", ".yaml", ".yml", ".toml", ".ini", ".md"}
    files: list[dict] = []
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.suffix.lower() in source_exts:
            if ".git" in f.parts or "__pycache__" in f.parts or ".venv" in f.parts:
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")[:3000]
                rel = f.relative_to(root)
                files.append({"path": str(rel), "content": content})
            except Exception:
                pass

    if not files:
        return f"No source files found in {folder}."

    structure = "\n".join(f"  📄 {f['path']} ({len(f['content'])} chars)" for f in files)
    contents_block = "\n\n".join(
        f"--- {f['path']} ---\n```\n{f['content']}\n```" for f in files[:10]
    )

    prompt = (
        f"Project folder: {root.name}\n"
        f"Files:\n{structure}\n\n"
        f"File contents:\n{contents_block[:8000]}\n\n"
        f"Write a README.md for this project. Include:\n"
        f"- Project name and short description\n"
        f"- Features\n"
        f"- How to set up / install\n"
        f"- How to use it\n"
        f"- Tech stack\n"
        f"Use clean Markdown."
    )

    readme = _ask_gemini(prompt)
    if readme.startswith("API error") or readme.startswith("Network error"):
        return f"Failed to generate README: {readme}"

    try:
        readme_path.write_text(readme, encoding="utf-8")
        return f"✅ README.md generated at {readme_path} ({len(readme)} chars)"
    except Exception as exc:
        return f"Couldn't write README: {exc}"
