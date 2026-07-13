#!/usr/bin/env python3
"""JARVIS — real-time voice + chat assistant with automations, powered by Google Gemini.

Run:

    python main.py            # launch the desktop GUI (native window) — default
    python main.py --cli      # legacy terminal (voice/text) assistant
    python main.py --server   # web server only (no GUI window)
"""
from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]
    if "--cli" in args:
        from jarvis.assistant import Assistant
        Assistant().run()
        return
    if "--server" in args:
        from server import run_server
        run_server()
        return
    # Default: launch the desktop GUI (native window wrapping the web HUD).
    from gui import launch
    launch()


if __name__ == "__main__":
    main()
