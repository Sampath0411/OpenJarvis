# 🤖 JARVIS — Real-Time AI Assistant

A voice + chat personal assistant in Python that **talks with you** and **runs real
automations** on your machine. Powered by [Google Gemini](https://aistudio.google.com/apikey)
via a single API key, with proper **tool-calling** so the AI decides when to open apps,
search the web, take notes, check the weather, control your system, and more.

```
You ▸ jarvis, what's the weather in Visakhapatnam and open youtube
  ⚙ running get_weather(city='Visakhapatnam')
  ⚙ running play_youtube(query='...')
JARVIS ▸ It's 31°C and sunny in Visakhapatnam. YouTube is open for you.
```

---

## ✨ Features

- **Real-time chat** — natural conversation with memory that persists between sessions.
- **Voice in & out** — speak to it (mic → speech-to-text) and it replies aloud (TTS).
  Falls back to text automatically if no mic/speakers.
- **Tool-calling automations** — the model calls real Python functions:
  | Category | Tools |
  |----------|-------|
  | System   | `open_app`, `run_command`, `set_volume`, `take_screenshot`, `system_info` |
  | Web      | `open_website`, `web_search`, `play_youtube`, `get_weather`, `wikipedia` |
  | Files    | `write_file`, `read_file`, `append_file`, `list_files` (sandboxed) |
  | Utility  | `get_datetime`, `add_note`, `read_notes`, `set_reminder`, `calculate` |
- **Model-agnostic** — swap models in `.env` (GPT-4o-mini, Gemini Flash, Llama 3.3, Grok…).
- **Extensible** — add a new automation in ~10 lines with one decorator.

---

## 📁 Project structure

```
Jarvis/
├── main.py                 # entry point → python main.py
├── config.py               # loads .env settings
├── requirements.txt
├── .env.example            # copy to .env and add your key
└── jarvis/
    ├── assistant.py        # interactive loop (UI, input mode, commands)
    ├── brain.py            # Gemini client + tool-calling loop
    ├── voice.py            # speech-to-text + text-to-speech (optional)
    ├── memory.py           # rolling conversation memory + disk persistence
    └── automations/
        ├── registry.py     # @tool decorator + dispatch
        ├── system.py       # open apps, volume, screenshots, shell
        ├── web.py          # search, weather, wikipedia, youtube
        ├── files.py        # sandboxed file ops
        └── utils.py        # time, notes, reminders, math
```

---

## 🖥️ Two ways to use it

**1. Web HUD (the interface)** — animated Iron Man HUD in your browser, with live clock,
weather, and system/mobile indicators. This is JARVIS's single front-end:
```bash
pip install -r requirements.txt
python main.py            # boots the HUD and opens http://127.0.0.1:5000
# python main.py --no-browser   # HUD without auto-opening the browser
```
`python server.py` runs the exact same thing. Set an access PIN in Settings to reach it from
your phone over the same Wi-Fi (a QR code is shown for quick pairing).

**2. Terminal (CLI)** — classic voice/text loop in the console, kept as a fallback:
```bash
python main.py --cli
```

---

## 🆕 What's inside (v2)

- **Streaming replies** — text appears token-by-token as the model thinks (SSE).
- **Barge-in** — tap 🎙 (or press `Esc`) to cut JARVIS off mid-sentence and speak.
- **Multi-language** — English / Hindi / Telugu for both understanding and spoken replies.
- **Personas** — JARVIS (formal), FRIDAY (casual), COACH (study coach) — switch in Settings.
- **Long-term memory** — "remember my sister's birthday is 4 March" persists across sessions
  (`~/.jarvis/facts.json`), and is fed back into every conversation.
- **Vision** — drag-drop, paste, or 🖼 attach an image; JARVIS describes/acts on it
  (free vision model first, paid fallback). Great for your photography work.
- **RAG over your files** — "summarize my notes", "find X in my resume" scans your
  workspace/Documents/Desktop/Downloads.
- **Media & power** — play/pause, next/prev, brightness, lock, sleep.
- **Win+S launcher** — "open chrome / vscode / settings" runs the Win+S → type → Enter flow
  you asked for. Plus quick tabs (Internshala, Instagram, GitHub…).
- **System watchdog** — pops toast alerts for low battery / high CPU / full RAM (i3-friendly).
- **Themes** — Arc (cyan), Mark III (gold-red), Ultron (red), Stealth (mono).
- **Command palette** — `Ctrl+K` for quick actions.
- **Draggable panels**, **chat export** (Markdown), **model fallback** (auto-switch on error).
- **Mobile control** — set an access PIN, open the shown LAN URL on your phone (same Wi-Fi).
- **Telegram bot** — control the laptop from *anywhere* via Telegram, with full AI chat,
  quick-action menu, approval flow for destructive tools, and proactive watchdog alerts.
- **Single-AI brain** — Gemini drives every tool call (screenshot, open_app, run_command…).
  Streamed tokens *are* the final reply — no second pass. Falls back across
  smaller Gemini models automatically on rate-limit, and rotates to a
  backup key when the primary is exhausted.
- **Personal identity baked in** — JARVIS starts every session already knowing who you are
  (name, education, projects, socials, contact). See `jarvis/owner.py`.
- **Files anywhere** — write, append, copy, move, rename, mkdir, list, read on any path
  the OS lets you touch. Delete still requires approval.
- **Create anything** — Markdown, HTML, CSV, JSON, YAML, XML, TXT, code files (Python, JS, TS,
  Go, Rust, Java, C++, …), **PDF, DOCX, XLSX, PPTX** (all from Markdown-lite), and
  **images** generated from a text prompt via Gemini 2.5 Flash Image.
- **Run code** — `run_python` (approval-gated) executes a Python snippet in a 10s
  sandbox, returns stdout/stderr.

## 🎨 The web HUD

`python main.py` opens the HUD at `http://127.0.0.1:5000` (and auto-launches your browser).

- **Arc reactor** — a live canvas animation that spins faster and glows brighter while JARVIS is
  thinking or speaking.
- **Boot sequence**, animated ring gauges (CPU / RAM), and a status cluster (ONLINE / MODEL / TOOLS).
- **Live indicators** — clock + date, current weather, and battery / network / CPU / RAM pills,
  visible on desktop and mobile layouts.
- **Round icon buttons** — settings, command palette, QR pairing, contacts, session memory, mic,
  vision, and send, rendered as crisp inline SVG icons (no emoji, fully theme-colored).
- **Settings modal** — paste API key (saved to `.env`), pick a model/persona/language/theme,
  set a mobile PIN, toggle voice.
- **Voice** — the mic button uses your browser's speech recognition; replies are spoken via speech
  synthesis. No `pyaudio` needed for the web UI.
- **Approval flow** — destructive tools (shutdown, delete, send_whatsapp) trigger an approval card.
- Tool calls show as glowing **chips** under each reply so you can see what JARVIS actually did.
- **Telegram** — the same brain and memory are reachable from your phone via the Telegram bot.

---

## 🚀 Setup (CLI voice extras)

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

> **Microphone (optional, for voice input).** `pyaudio` needs system audio libs:
> - **Windows:** `pip install pyaudio` (or `pip install pipwin && pipwin install pyaudio`)
> - **macOS:** `brew install portaudio && pip install pyaudio`
> - **Linux:** `sudo apt install portaudio19-dev && pip install pyaudio`
>
> Skip this if you only want to type — set `JARVIS_STT=0` in `.env`.

### 2. Add your Gemini key
```bash
cp .env.example .env      # Windows: copy .env.example .env
```
Then edit `.env` and paste your key from <https://aistudio.google.com/apikey>.
You can also add a second key as `JARVIS_GEMINI_KEY_BACKUP` for automatic
rotation when the primary key hits its rate limit.

### 3. Run
```bash
python main.py
```

---

## ⚙️ Configuration (`.env`)

| Variable | Default | Meaning |
|----------|---------|---------|
| `JARVIS_GEMINI_KEY` | — | **Required.** Your Gemini API key. |
| `JARVIS_GEMINI_KEY_BACKUP` | — | Optional. Used automatically when the primary is rate-limited. |
| `JARVIS_MODEL` | `gemini-2.0-flash` | Any Gemini model id (e.g. `gemini-2.0-flash`, `gemini-2.5-flash`). |
| `JARVIS_VOICE` | `1` | `1` = speak replies aloud, `0` = text only. |
| `JARVIS_STT`   | `1` | `1` = listen via mic, `0` = type input. |
| `JARVIS_NAME`  | `JARVIS` | Assistant name/personality. |
| `JARVIS_WAKE_WORD` | `jarvis` | Optional wake word. |

**In-session commands:** `exit`, `reset` (clear memory), `text` / `voice` (switch input mode).

---

## 🤖 Telegram bot (control the laptop from anywhere)

Run JARVIS on your PC and DM it from any phone on any network — same AI
brain, same automations, with an inline keyboard and proactive alerts.

### 1. Create the bot

1. Open Telegram, message [@BotFather](https://t.me/BotFather).
2. Send `/newbot`, follow the prompts, copy the **token**.

### 2. Configure JARVIS

Edit `.env` (set `JARVIS_PIN` first if you haven't — Telegram reuses it):

```env
JARVIS_PIN=5252
JARVIS_TELEGRAM_ENABLED=1
JARVIS_TELEGRAM_TOKEN=123456:ABC-DEF...
```

Install the dependency and restart:

```bash
pip install -r requirements.txt   # adds python-telegram-bot
python server.py
```

You should see `[telegram] bot started` in the startup output.

### 3. Link your chat

1. Open your bot in Telegram.
2. Send `/start` — it'll ask for the PIN.
3. Send `/start 5252` (or whatever your PIN is). The PIN message is
   deleted for safety. You now see the main menu.

### Features

- **Quick-action menu** — `📸 Screenshot · 🖥 System · 🔋 Battery · 💻 CPU/RAM ·
  🌐 Open URL · 📂 Files · 🔊 Volume · 🪟 Windows · ⏻ Shutdown · 🔄 Restart`.
- **Commands** — `/me`, `/myprojects`, `/screenshot`, `/battery`, `/windows`,
  `/volume 50`, `/open chrome`, `/cancel_shutdown`, `/reset`, `/help`.
- **File ops** — `/file write <path>` (then attach a file), `/file write_text <path> <content>`,
  `/file append <path>`, `/file mkdir <path>`, `/file list [path]`, `/file read <path>`,
  `/file delete <path>` (asks for approval). Files work *anywhere* your OS user can write.
- **Free chat** — any non-command text is sent to JARVIS's brain, so you
  can ask "open YouTube and search lo-fi" or "summarize my notes".
- **Screenshots come back as photos** — the bot detects
  `Screenshot saved to …` and sends the file.
- **Approval flow** — destructive tools (shutdown, restart, delete file)
  show a ✅ / ❌ inline keyboard. Approve from anywhere.
- **Proactive alerts** — low battery / high CPU / full RAM alerts get
  DMed automatically (forwarded from the same watchdog the web UI uses).
- **Shared memory** — Telegram conversation and web/CLI share the same
  Memory, so context carries between devices.
- **Single-AI replies** — Gemini handles both the tool-calling and the final
  wording. Falls back across smaller Gemini models automatically.
- **Multi-user** — multiple Telegram accounts can be linked (each
  sends `/start <PIN>`). Revoke by deleting
  `~/.jarvis/telegram_authorized.json`.

### Disable

Set `JARVIS_TELEGRAM_ENABLED=0` in `.env` and restart. The Flask server
keeps running normally.

---

## 🧩 Add your own automation

Drop a function in any file under `jarvis/automations/` (or a new one):

```python
from .registry import tool

@tool(
    name="lock_screen",
    description="Lock the computer screen.",
)
def lock_screen() -> str:
    import os, platform
    if platform.system() == "Windows":
        os.system("rundll32.exe user32.dll,LockWorkStation")
    return "Screen locked."
```

Import it in `jarvis/automations/__init__.py` and JARVIS can now call it — no other
wiring needed. The model reads the `description` to decide when to use it.

---

## 🔒 Safety notes

- File tools are **sandboxed** to `~/jarvis_workspace`.
- `run_command` executes shell commands — the model is told to be cautious, but treat it
  like giving the AI a terminal. Remove that tool from `automations/__init__.py` if you
  want a locked-down build.
- Your `.env` (API key) is git-ignored.

---

Built by **Sampath Satya Saran** · powered by Google Gemini.
