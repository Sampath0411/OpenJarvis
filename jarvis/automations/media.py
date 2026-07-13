"""Media & power automations — play/pause, tracks, brightness, lock, sleep."""
from __future__ import annotations

import os
import platform
import subprocess

from .registry import tool

IS_WIN = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"


def _press(key: str) -> bool:
    try:
        import pyautogui
        pyautogui.press(key)
        return True
    except Exception:  # noqa: BLE001
        return False


@tool(
    name="media_control",
    description="Control media playback: play/pause, next track, or previous track.",
    parameters={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["playpause", "next", "previous"]}
        },
        "required": ["action"],
    },
)
def media_control(action: str) -> str:
    keymap = {"playpause": "playpause", "next": "nexttrack", "previous": "prevtrack"}
    key = keymap.get(action, "playpause")
    if _press(key):
        return f"Media: {action}."
    return "Install pyautogui for media keys (pip install pyautogui)."


def _get_brightness() -> int | None:
    """Read current brightness (0-100), best-effort across displays."""
    try:
        import screen_brightness_control as sbc
        vals = sbc.get_brightness()
        if isinstance(vals, (list, tuple)):
            vals = [v for v in vals if v is not None]
            return int(vals[0]) if vals else None
        return int(vals)
    except Exception:  # noqa: BLE001
        return None


def _apply_brightness(level: int) -> bool:
    """Set brightness via screen_brightness_control, PowerShell WMI as fallback."""
    try:
        import screen_brightness_control as sbc
        sbc.set_brightness(level)
        return True
    except Exception:  # noqa: BLE001
        pass
    if IS_WIN:
        try:
            ps = (
                f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)."
                f"WmiSetBrightness(1,{level})"
            )
            subprocess.run(["powershell", "-Command", ps], capture_output=True, timeout=10)
            return True
        except Exception:  # noqa: BLE001
            return False
    if IS_MAC:
        try:
            subprocess.run(["brightness", str(level / 100)], capture_output=True, timeout=10)
            return True
        except Exception:  # noqa: BLE001
            return False
    return False


@tool(
    name="set_brightness",
    description=(
        "Get or set the screen brightness. action 'set' with level 0-100, "
        "'up'/'down' to step by 10, or 'get' to read the current level."
    ),
    parameters={
        "type": "object",
        "properties": {
            "level": {"type": "integer", "minimum": 0, "maximum": 100,
                       "description": "Target brightness 0-100 (for action 'set')."},
            "action": {"type": "string", "enum": ["set", "up", "down", "get"]},
        },
    },
)
def set_brightness(level: int | None = None, action: str = "set") -> str:
    if action == "get":
        cur = _get_brightness()
        return f"Screen brightness is {cur}%." if cur is not None \
            else "Couldn't read the current brightness on this display."

    if action in ("up", "down"):
        cur = _get_brightness()
        if cur is None:
            return "Couldn't read the current brightness to adjust it."
        level = cur + 10 if action == "up" else cur - 10
    elif level is None:
        return "Tell me a brightness level (0-100)."

    level = max(0, min(100, int(level)))
    if _apply_brightness(level):
        return f"Brightness set to {level}%."
    return ("Brightness control failed — this display may not support software "
            "brightness (common on external monitors without DDC/CI).")


@tool(
    name="lock_screen",
    description="Lock the computer screen.",
)
def lock_screen() -> str:
    try:
        if IS_WIN:
            os.system("rundll32.exe user32.dll,LockWorkStation")
        elif IS_MAC:
            os.system("pmset displaysleepnow")
        else:
            os.system("xdg-screensaver lock")
        return "Screen locked."
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't lock: {exc}"


@tool(
    name="sleep_pc",
    description="Put the computer to sleep. Ask the user to confirm before calling.",
)
def sleep_pc() -> str:
    try:
        if IS_WIN:
            os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        elif IS_MAC:
            os.system("pmset sleepnow")
        else:
            os.system("systemctl suspend")
        return "Going to sleep."
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't sleep: {exc}"
