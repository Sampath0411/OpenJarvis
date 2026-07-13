"""System automations — open apps, control volume, screenshots, process info,
window control, shutdown, and restart."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import webbrowser

from .registry import tool

IS_WIN = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"


# ── open applications ────────────────────────────────
# Friendly name -> how to launch it per-OS.
APP_ALIASES = {
    "notepad": {"win": "notepad", "mac": "TextEdit", "linux": "gedit"},
    "calculator": {"win": "calc", "mac": "Calculator", "linux": "gnome-calculator"},
    "browser": {"win": "start chrome", "mac": "Safari", "linux": "xdg-open https://google.com"},
    "chrome": {"win": "start chrome", "mac": "Google Chrome", "linux": "google-chrome"},
    "explorer": {"win": "explorer", "mac": "Finder", "linux": "xdg-open ."},
    "cmd": {"win": "start cmd", "mac": "Terminal", "linux": "x-terminal-emulator"},
    "vscode": {"win": "code", "mac": "Visual Studio Code", "linux": "code"},
    "settings": {"win": "start ms-settings:", "mac": "System Settings", "linux": "gnome-control-center"},
    "spotify": {"win": "start spotify:", "mac": "Spotify", "linux": "spotify"},
}


@tool(
    name="open_app",
    description=(
        "Open a desktop application by name (e.g. notepad, calculator, vscode, spotify). "
        "PREFER 'smart_open' over this for any free-form 'open X' request — smart_open "
        "figures out whether X is a file, folder, or app and dispatches the right way. "
        "Use this tool only when the user explicitly says 'launch' or 'start' an app by name."
    ),
    parameters={
        "type": "object",
        "properties": {
            "app": {"type": "string", "description": "Application name or alias."}
        },
        "required": ["app"],
    },
)
def open_app(app: str) -> str:
    key = app.strip().lower()
    mapping = APP_ALIASES.get(key)
    try:
        if mapping:
            cmd = mapping["win"] if IS_WIN else mapping["mac"] if IS_MAC else mapping["linux"]
            if IS_MAC and not cmd.startswith(("open", "xdg")):
                subprocess.Popen(["open", "-a", cmd])
            else:
                subprocess.Popen(cmd, shell=True)
        else:
            # unknown -> try to launch raw name
            if IS_WIN:
                subprocess.Popen(f"start {app}", shell=True)
            elif IS_MAC:
                subprocess.Popen(["open", "-a", app])
            else:
                subprocess.Popen([app])
        return f"Opened {app}."
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't open {app}: {exc}"


@tool(
    name="run_command",
    description=(
        "Run a shell command on the user's machine and return its output. "
        "Use ONLY for safe, read-ish commands the user explicitly asked for."
    ),
    requires_approval=True,
    destructive=True,
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to run."}
        },
        "required": ["command"],
    },
)
def run_command(command: str) -> str:
    try:
        out = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        result = (out.stdout or "") + (out.stderr or "")
        return result.strip()[:2000] or f"(exit {out.returncode}, no output)"
    except subprocess.TimeoutExpired:
        return "Command timed out after 30s."
    except Exception as exc:  # noqa: BLE001
        return f"Command failed: {exc}"


@tool(
    name="set_volume",
    description="Set or mute system volume. level is 0-100, or use action 'mute'/'unmute'.",
    parameters={
        "type": "object",
        "properties": {
            "level": {"type": "integer", "description": "Volume 0-100.", "minimum": 0, "maximum": 100},
            "action": {"type": "string", "enum": ["set", "mute", "unmute"]},
        },
    },
)
def set_volume(level: int | None = None, action: str = "set") -> str:
    try:
        if IS_MAC:
            if action == "mute":
                os.system("osascript -e 'set volume output muted true'")
                return "Muted."
            if action == "unmute":
                os.system("osascript -e 'set volume output muted false'")
                return "Unmuted."
            lvl = max(0, min(100, level or 50))
            os.system(f"osascript -e 'set volume output volume {lvl}'")
            return f"Volume set to {lvl}%."
        if IS_WIN:
            if shutil.which("nircmd"):
                if action == "mute":
                    os.system("nircmd mutesysvolume 1")
                    return "Muted."
                if action == "unmute":
                    os.system("nircmd mutesysvolume 0")
                    return "Unmuted."
                lvl = max(0, min(100, level or 50))
                os.system(f"nircmd setsysvolume {int(lvl/100*65535)}")
                return f"Volume set to {lvl}%."
            return "Install nircmd for precise Windows volume control."
        return "Volume control not implemented for this OS."
    except Exception as exc:  # noqa: BLE001
        return f"Volume control failed: {exc}"


@tool(
    name="take_screenshot",
    description="Capture the screen and save it to a file. Returns the saved path.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Optional output path (.png)."}
        },
    },
)
def take_screenshot(path: str | None = None) -> str:
    try:
        import pyautogui
    except ImportError:
        return "pyautogui is not installed. Run: pip install pyautogui"
    out = path or os.path.join(os.path.expanduser("~"), "jarvis_screenshot.png")
    try:
        # pyautogui.screenshot() needs Pillow and a real display; both can
        # raise on headless / Pillow-less setups — surface a friendly message
        # instead of crashing the dispatcher.
        pyautogui.screenshot().save(out)
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't capture the screen: {exc}"
    return f"Screenshot saved to {out}"


@tool(
    name="system_info",
    description="Report CPU, memory, disk and battery status of the machine.",
)
def system_info() -> str:
    try:
        import psutil
    except ImportError:
        return "psutil is not installed. Run: pip install psutil"
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    lines = [
        f"CPU: {cpu:.0f}%",
        f"RAM: {mem.percent:.0f}% ({mem.used // 2**20} / {mem.total // 2**20} MB)",
        f"Disk: {disk.percent:.0f}% used ({disk.free // 2**30} GB free)",
    ]
    batt = getattr(psutil, "sensors_battery", lambda: None)()
    if batt:
        plug = "charging" if batt.power_plugged else "on battery"
        lines.append(f"Battery: {batt.percent:.0f}% ({plug})")
    return " | ".join(lines)


# ── window control (Windows-first via pygetwindow) ─
def _windows():
    """Return all visible windows. Returns [] if pygetwindow missing or unsupported."""
    try:
        import pygetwindow as gw
    except ImportError:
        return []
    try:
        wins = gw.getAllWindows()
        return [w for w in wins if w.title and w.title.strip()]
    except Exception:  # noqa: BLE001
        return []


def _find_window(title: str):
    matches = [w for w in _windows() if title.lower() in w.title.lower()]
    return matches


@tool(
    name="list_windows",
    description="List all open windows by title.",
)
def list_windows() -> str:
    wins = _windows()
    if not wins:
        return "No windows detected (pygetwindow not installed or no display)."
    return "\n".join(f"- {w.title}" for w in wins[:50])


@tool(
    name="minimize_window",
    description="Minimize a window that matches the given title substring.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Substring of the window title to match."}
        },
        "required": ["title"],
    },
)
def minimize_window(title: str) -> str:
    matches = _find_window(title)
    if not matches:
        return f"No window matching '{title}'."
    try:
        matches[0].minimize()
        return f"Minimized '{matches[0].title}'."
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't minimize: {exc}"


@tool(
    name="maximize_window",
    description="Maximize a window that matches the given title substring.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Substring of the window title to match."}
        },
        "required": ["title"],
    },
)
def maximize_window(title: str) -> str:
    matches = _find_window(title)
    if not matches:
        return f"No window matching '{title}'."
    try:
        matches[0].maximize()
        return f"Maximized '{matches[0].title}'."
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't maximize: {exc}"


@tool(
    name="focus_window",
    description="Bring a window matching the title substring to the front.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Substring of the window title to match."}
        },
        "required": ["title"],
    },
)
def focus_window(title: str) -> str:
    matches = _find_window(title)
    if not matches:
        return f"No window matching '{title}'."
    try:
        matches[0].activate()
        return f"Focused '{matches[0].title}'."
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't focus: {exc}"


@tool(
    name="close_window",
    description="Close a window that matches the given title substring. Destructive — requires user approval.",
    requires_approval=True,
    destructive=True,
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Substring of the window title to match."}
        },
        "required": ["title"],
    },
)
def close_window(title: str) -> str:
    matches = _find_window(title)
    if not matches:
        return f"No window matching '{title}'."
    try:
        matches[0].close()
        return f"Closed '{matches[0].title}'."
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't close: {exc}"


# ── shutdown / restart ──────────────────────────────
@tool(
    name="shutdown_pc",
    description="Shut down the computer after a delay (in seconds). Destructive — requires user approval.",
    requires_approval=True,
    destructive=True,
    parameters={
        "type": "object",
        "properties": {
            "delay_seconds": {"type": "integer", "description": "Delay in seconds before shutdown.", "default": 30}
        },
    },
)
def shutdown_pc(delay_seconds: int = 30) -> str:
    try:
        if IS_WIN:
            os.system(f"shutdown /s /t {max(0, int(delay_seconds))}")
            return f"Shutdown scheduled in {delay_seconds}s. Run 'shutdown /a' to abort."
        if IS_MAC:
            os.system(f"sudo shutdown -h +{int(delay_seconds)//60 or 1}")
            return f"Mac shutdown scheduled in {delay_seconds}s."
        os.system(f"shutdown -h +{int(delay_seconds)//60 or 1}")
        return f"Linux shutdown scheduled."
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't schedule shutdown: {exc}"


@tool(
    name="restart_pc",
    description="Restart the computer after a delay (in seconds). Destructive — requires user approval.",
    requires_approval=True,
    destructive=True,
    parameters={
        "type": "object",
        "properties": {
            "delay_seconds": {"type": "integer", "description": "Delay in seconds before restart.", "default": 30}
        },
    },
)
def restart_pc(delay_seconds: int = 30) -> str:
    try:
        if IS_WIN:
            os.system(f"shutdown /r /t {max(0, int(delay_seconds))}")
            return f"Restart scheduled in {delay_seconds}s. Run 'shutdown /a' to abort."
        if IS_MAC:
            os.system(f"sudo shutdown -r +{int(delay_seconds)//60 or 1}")
            return f"Mac restart scheduled in {delay_seconds}s."
        os.system(f"shutdown -r +{int(delay_seconds)//60 or 1}")
        return f"Linux restart scheduled."
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't schedule restart: {exc}"


@tool(
    name="cancel_shutdown",
    description="Cancel a previously scheduled shutdown or restart.",
)
def cancel_shutdown() -> str:
    try:
        if IS_WIN:
            os.system("shutdown /a")
            return "Shutdown cancelled (if one was scheduled)."
        if IS_MAC:
            os.system("sudo killall shutdown")
            return "Shutdown cancelled."
        os.system("shutdown -c")
        return "Shutdown cancelled."
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't cancel: {exc}"
