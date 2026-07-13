"""Phone control over ADB Wi-Fi — send SMS, read notifications, device info.

Requires:
  - adb installed and in PATH (https://developer.android.com/tools/adb)
  - Phone connected on same Wi-Fi network
  - Phone has USB debugging enabled, then:
      adb tcpip 5555
      ad connect <phone-ip>:5555

One-time setup. After that, JARVIS can control the phone over Wi-Fi.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .registry import tool

ADB = "adb"


def _adb(varargs: str, timeout: int = 10) -> str:
    """Run an adb command and return stdout+stderr."""
    try:
        proc = subprocess.run(
            f"{ADB} {varargs}",
            capture_output=True, text=True, timeout=timeout,
            shell=True,
        )
    except subprocess.TimeoutExpired:
        return "adb command timed out."
    except FileNotFoundError:
        return "adb not found. Install Android Debug Bridge and add it to PATH."
    except Exception as exc:
        return f"adb error: {exc}"
    out = (proc.stdout or "") + (proc.stderr or "")
    return out.strip()


def _check_device() -> str | None:
    """Return None if a device is connected, otherwise an error string."""
    out = _adb("devices -l")
    if "unauthorized" in out:
        return "Phone is connected but unauthorized. Accept the USB debugging prompt on your phone."
    lines = [l for l in out.splitlines() if "device" in l and "devices" not in l]
    if not lines:
        return "No ADB devices connected. Connect phone via USB, run 'adb tcpip 5555', then 'adb connect <ip>:5555'."
    return None


@tool(
    name="adb_connect",
    description=(
        "Connect to an Android phone over Wi-Fi via ADB. "
        "Phone must already have USB debugging enabled and be on the same Wi-Fi. "
        "Run 'adb tcpip 5555' over USB once before first Wi-Fi connect."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ip": {"type": "string", "description": "Phone IP address on Wi-Fi (e.g. 192.168.1.5)."},
            "port": {"type": "string", "description": "Port (default 5555).", "default": "5555"},
        },
        "required": ["ip"],
    },
)
def adb_connect(ip: str, port: str = "5555") -> str:
    out = _adb(f"connect {ip}:{port}")
    if "connected" in out.lower():
        return f"✅ Connected to {ip}:{port}"
    return f"Connection result: {out[:300]}"


@tool(
    name="adb_device_info",
    description="Show connected Android device info — model, battery, IP, Android version.",
)
def adb_device_info() -> str:
    err = _check_device()
    if err:
        return err

    model = _adb("shell getprop ro.product.model")
    brand = _adb("shell getprop ro.product.brand")
    android_ver = _adb("shell getprop ro.build.version.release")
    battery = _adb("shell dumpsys battery | grep level")
    ip_wlan = _adb("shell ip -f inet addr show wlan0 2>/dev/null || echo ''")
    ip_wlan = ip_wlan or _adb("shell ifconfig wlan0 2>/dev/null | grep inet")

    lines = [
        f"📱 Model: {brand.strip()} {model.strip()}",
        f"🤖 Android: {android_ver.strip()}",
    ]
    batt_match = re.search(r"level:\s*(\d+)", battery)
    if batt_match:
        lines.append(f"🔋 Battery: {batt_match.group(1)}%")
    ip_match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", ip_wlan)
    if ip_match:
        lines.append(f"🌐 Wi-Fi IP: {ip_match.group(1)}")
    return "\n".join(lines)


@tool(
    name="adb_send_sms",
    description=(
        "Send an SMS message from the connected Android phone. "
        "Requires ADB Wi-Fi connection."
    ),
    parameters={
        "type": "object",
        "properties": {
            "phone_number": {"type": "string", "description": "Recipient phone number (with country code, e.g. +919291493225)."},
            "message": {"type": "string", "description": "SMS text content."},
        },
        "required": ["phone_number", "message"],
    },
)
def adb_send_sms(phone_number: str, message: str) -> str:
    err = _check_device()
    if err:
        return err

    # Use Android's service call or am start to send SMS
    # Method: am start -a android.intent.action.SENDTO -d sms:<number> --es sms_body "<text>"
    # Then tap send via input keyevent
    cleaned_num = re.sub(r"[^0-9+]", "", phone_number)
    escaped_msg = message.replace('"', '\\"').replace("'", "\\'")

    # Open SMS composer
    out = _adb(
        f'shell am start -a android.intent.action.SENDTO '
        f'-d sms:{cleaned_num} --es sms_body "{escaped_msg}" '
        f'--ez exit_on_sent true',
        timeout=5,
    )
    if "Error" in out and "java" not in out.lower():
        return f"Failed to open SMS app: {out[:200]}"

    # Wait for UI, then tap send button
    _adb("shell input keyevent 22", timeout=3)  # focus send button
    _adb("shell input keyevent 66", timeout=3)  # press enter/send

    return f"✅ SMS sent to {cleaned_num}"


@tool(
    name="adb_notifications",
    description=(
        "Read recent notifications from the connected Android phone. "
        "Requires ADB Wi-Fi connection. Returns the last N notifications."
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Max notifications to show (default 10).", "default": 10},
        },
        "required": [],
    },
)
def adb_notifications(limit: int = 10) -> str:
    err = _check_device()
    if err:
        return err

    out = _adb(f"shell dumpsys notification --noredact | grep -A 5 'NotificationRecord'", timeout=10)
    if not out:
        return "No notifications found or couldn't read them."

    # Parse notification blocks
    entries: list[str] = []
    current: list[str] = []
    for line in out.splitlines():
        if "NotificationRecord" in line:
            if current:
                entries.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        entries.append("\n".join(current))

    # Simplify: extract package + title + text
    results: list[str] = []
    for entry in entries[:limit]:
        pkg_match = re.search(r'packageName=([^\s,]+)', entry)
        title_match = re.search(r'titleText=([^\n]+)', entry)
        text_match = re.search(r'text=[\s\"]*([^\n\"]+)', entry)

        parts = []
        if pkg_match:
            parts.append(f"[{pkg_match.group(1)}]")
        if title_match:
            parts.append(f"📌 {title_match.group(1).strip()}")
        if text_match:
            parts.append(f"   {text_match.group(1).strip()[:120]}")

        if parts:
            results.append(" ".join(parts))

    if not results:
        return "No readable notifications found."
    return "\n".join(f"{i+1}. {r}" for i, r in enumerate(results))


@tool(
    name="adb_take_screenshot",
    description=(
        "Take a screenshot of the connected Android phone and save it locally. "
        "Requires ADB Wi-Fi connection."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Save path on PC (default: ~/jarvis_workspace/phone_screenshot.png)."},
        },
        "required": [],
    },
)
def adb_take_screenshot(path: str = "") -> str:
    err = _check_device()
    if err:
        return err

    out_path = Path(path).expanduser() if path else Path.home() / "jarvis_workspace" / "phone_screenshot.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    _adb("shell screencap -p /sdcard/screen.png")
    result = _adb(f"pull /sdcard/screen.png \"{out_path}\"")
    _adb("shell rm /sdcard/screen.png")

    if "error" in result.lower():
        return f"Screenshot failed: {result[:200]}"
    return f"✅ Phone screenshot saved to {out_path}"
