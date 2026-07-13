#!/usr/bin/env python3
"""JARVIS — real-time voice + chat assistant with automations, powered by Google Gemini.

The web HUD is the single interface. Run:

    python main.py            # launch the web HUD (opens the browser)
    python main.py --no-browser   # HUD without auto-opening the browser
    python main.py --cli          # legacy terminal (voice/text) assistant
"""
from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]
    if "--cli" in args:
        from jarvis.assistant import Assistant
        Assistant().run()
        return
    from server import run_server
    run_server(open_browser="--no-browser" not in args)


if __name__ == "__main__":
    main()
