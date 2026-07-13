#!/usr/bin/env python3
"""JARVIS Desktop GUI — wraps the web HUD in a native window.

All the glassmorphism, arc reactor animations, system stats, chat, goals,
modals, and themes work exactly as they do in the browser — just in a
frameless desktop window with a custom title bar.

Usage:
    python gui.py              # launch the desktop app
    python gui.py --no-server  # attach to an already-running server
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

# Make sure we can import jarvis modules.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

HOST = "127.0.0.1"
PORT = 5000


# ── Flask server thread ──────────────────────────────────
_server_thread: threading.Thread | None = None
_server_started = threading.Event()


def _start_server() -> None:
    """Boot the Flask server in a background thread."""
    from server import app as _flask_app
    # Silence the normal startup prints; the GUI shows its own boot sequence.
    import logging as _logging
    _log = _logging.getLogger("werkzeug")
    _log.setLevel(_logging.ERROR)

    _flask_app.run(
        host=HOST, port=PORT,
        debug=False, threaded=True,
        use_reloader=False,
    )


def _boot_server() -> None:
    global _server_thread
    if _server_thread and _server_thread.is_alive():
        return
    _server_thread = threading.Thread(
        target=_start_server, daemon=True,
        name="jarvis-flask",
    )
    _server_thread.start()
    # Wait for the server to start responding.
    import requests as _req
    for _ in range(60):
        try:
            r = _req.get(f"http://{HOST}:{PORT}/api/status", timeout=2)
            if r.ok:
                _server_started.set()
                return
        except Exception:
            pass
        time.sleep(0.5)
    print("[gui] Flask server did not start in time.")
    sys.exit(1)


# ── GUI window ───────────────────────────────────────────
def launch(no_server: bool = False) -> None:
    """Open the JARVIS HUD in a native desktop window."""
    if not no_server:
        _boot_server()
    else:
        _server_started.set()

    _server_started.wait(timeout=15)

    try:
        import webview as _wv
    except ImportError:
        print("pywebview is required for the GUI. Install: pip install pywebview")
        print("Or run: python server.py  (web server without GUI)")
        sys.exit(1)

    # Window creation — frameless but resizable, with the HUD in full effect.
    window = _wv.create_window(
        title="J.A.R.V.I.S",
        url=f"http://{HOST}:{PORT}",
        width=1280,
        height=800,
        min_size=(900, 600),
        resizable=True,
        fullscreen=False,
        text_select=True,
        # Use Edge/Chromium on Windows — best canvas/gl performance.
        easy_drag=False,
    )

    # Block until the window is closed.
    _wv.start(
        debug=False,
        http_server=False,  # Flask is our server
        private_mode=False,
    )


# ── entry point ──────────────────────────────────────────
def main() -> None:
    args = [a.lower() for a in sys.argv[1:]]
    launch(no_server="--no-server" in args)


if __name__ == "__main__":
    main()
