#!/usr/bin/env python3
"""JARVIS web server — serves the Iron Man HUD and bridges the browser to the brain.

Run:  python server.py     then open  http://127.0.0.1:5000
LAN/mobile access requires a PIN (set in Settings) for safety.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
import webbrowser
from datetime import datetime
from threading import Timer

import requests
from flask import Flask, Response, jsonify, request, send_from_directory

# Make console output UTF-8 safe (Windows terminals often default to cp1252).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

from config import CONFIG, GEMINI_BASE
from jarvis import contacts, facts, personas, sessions
from jarvis.automations import REGISTRY
from jarvis.brain import Brain
from jarvis.memory import Memory
from jarvis.watchdog import WATCHDOG

# Wire email credentials into the email_tool so the AI can send mail.
from jarvis.automations import email_tool as _email_tool  # noqa: E402

app = Flask(__name__, static_folder="static", template_folder="templates")


# ── system prompt (persona + language + long-term facts) ──
def current_system_prompt() -> str:
    return personas.build_system_prompt(
        CONFIG.persona, CONFIG.language, REGISTRY.names(), facts.facts_text()
    )


MEMORY = Memory(current_system_prompt())
# Resume the last local session so the web HUD, Telegram bot, and CLI all
# continue from the same ~/.jarvis/history.json store.
try:
    MEMORY.load()
except Exception as exc:  # noqa: BLE001
    print(f"[memory] could not load history: {exc}")
BRAIN = Brain(
    memory=MEMORY,
    tools_schema=REGISTRY.schemas(),
    dispatch=REGISTRY.dispatch,
    registry=REGISTRY,
)
# Wire Brain.see_screen into the registry.
BRAIN.bind_see_screen()

# Telegram bot (optional — only starts if enabled + token set).
TELEGRAM = None
try:
    from jarvis.telegram_bot import TelegramBot  # noqa: E402
    TELEGRAM = TelegramBot(BRAIN, MEMORY, REGISTRY, WATCHDOG)
except Exception as exc:  # noqa: BLE001
    print(f"[telegram] could not import bot: {exc}")

# ── Agent (autonomous planner/executor) ──────────────
from jarvis.agent import scheduler as AGENT_SCHEDULER  # noqa: E402
AGENT_SCHEDULER.set_brain(BRAIN)
if TELEGRAM is not None and TELEGRAM.is_running():
    AGENT_SCHEDULER.set_telegram_push(TELEGRAM.push_text)
AGENT_SCHEDULER.start()


def refresh_system_prompt() -> None:
    """Keep message[0] in sync with the latest persona/language/facts."""
    new_prompt = current_system_prompt()
    MEMORY.refresh_system_prompt(new_prompt)


# Track per-request "context" so approval resolution can resume streaming.
# Each entry: {key: state} where state is "idle" or the last user_text being processed.
_PENDING_USER: dict[str, str] = {}
_SESSION_KEY = "default"


# ── PIN gate for non-localhost (mobile) access ───────
LOCAL_ADDRS = {"127.0.0.1", "::1", "localhost"}


@app.before_request
def guard_remote():
    if request.path == "/" or request.path.startswith("/static") or request.path == "/favicon.ico":
        return None
    remote = (request.remote_addr or "").replace("::ffff:", "")
    if remote in LOCAL_ADDRS:
        return None
    if not CONFIG.pin:
        return jsonify({"error": "lan_disabled",
                        "reply": "Remote access is disabled. Set an access PIN on the host PC."}), 403
    supplied = request.headers.get("X-Jarvis-Pin") or request.args.get("pin")
    if supplied != CONFIG.pin:
        return jsonify({"error": "bad_pin", "reply": "Invalid or missing access PIN."}), 401
    return None


# ── routes ───────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


def _lan_url() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return f"http://{ip}:5000"
    except OSError:
        return ""


@app.route("/api/status")
def status():
    ak = CONFIG.api_key or ""
    am = f"{ak[:6]}...{ak[-4:]}" if len(ak) > 12 else ""
    return jsonify({
        "name": personas.PERSONAS.get(CONFIG.persona, {}).get("name", CONFIG.name),
        "model": CONFIG.model,
        "has_key": CONFIG.has_key,
        "api_key_masked": am,
        "persona": CONFIG.persona,
        "language": CONFIG.language,
        "theme": CONFIG.theme,
        "personas": {k: v["name"] for k, v in personas.PERSONAS.items()},
        "languages": personas.LANGUAGES,
        "tools": REGISTRY.names(),
        "tool_count": len(REGISTRY.names()),
        "tool_metadata": REGISTRY.metadata(),
        "pin_set": bool(CONFIG.pin),
        "lan_url": _lan_url() if CONFIG.pin else "",
        "email_configured": bool(_EMAIL_CONFIG.get("smtp_host")),
        "themes": ["arc", "mark3", "ultron", "stealth", "midnight", "amoled", "light"],
    })


@app.route("/api/config", methods=["POST"])
def set_config():
    data = request.get_json(force=True, silent=True) or {}
    CONFIG.update(
        api_key=data.get("api_key"),
        api_key_backup=data.get("api_key_backup"),
        api_key_backup2=data.get("api_key_backup2"),
        api_key_backup3=data.get("api_key_backup3"),
        model=data.get("model"),
        persona=data.get("persona"),
        language=data.get("language"),
        theme=data.get("theme"),
        pin=data.get("pin"),
        telegram_token=data.get("telegram_token"),
        telegram_enabled=data.get("telegram_enabled"),
        persist=data.get("persist", True),
    )
    refresh_system_prompt()
    return jsonify({
        "ok": True,
        "has_key": CONFIG.has_key,
        "has_backup_key": CONFIG.has_backup_key(),
        "key_count": len(CONFIG.all_keys()),
        "model": CONFIG.model,
        "persona": CONFIG.persona,
        "language": CONFIG.language,
        "pin_set": bool(CONFIG.pin),
        "lan_url": _lan_url() if CONFIG.pin else "",
        "telegram_enabled": bool(CONFIG.telegram_enabled and CONFIG.telegram_token),
    })


@app.route("/api/reset", methods=["POST"])
def reset():
    # Summarize the dropped conversation if it had substance.
    msgs = [m for m in MEMORY.messages if m.get("role") in ("user", "assistant") and m.get("content")]
    if len(msgs) >= 4:
        try:
            summary = BRAIN.summarize_session(msgs[-30:])
            if summary:
                sessions.add_summary(summary)
        except Exception:  # noqa: BLE001
            pass
    MEMORY.reset()
    refresh_system_prompt()
    return jsonify({"ok": True})


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    if not CONFIG.has_key:
        def no_key():
            yield _sse({"type": "error", "error": "no_key",
                        "text": "No API key set. Open settings and paste your Gemini API key."})
        return Response(no_key(), mimetype="text/event-stream")

    data = request.get_json(force=True, silent=True) or {}
    message = (data.get("message") or "").strip()
    refresh_system_prompt()
    # Reset pending state for a new turn.
    _PENDING_USER[_SESSION_KEY] = message

    def generate():
        if not message:
            yield _sse({"type": "done", "text": ""})
            return
        try:
            tokens: list[str] = []
            tool_results: list[dict] = []
            pending = False
            got_error = False
            for event in BRAIN.stream_ask(message):
                etype = event.get("type")
                if etype == "token":
                    tokens.append(event.get("text", ""))
                elif etype == "tool_done":
                    tool_results.append({
                        "name": event.get("name", ""),
                        "result": event.get("result", ""),
                    })
                elif etype == "approval_required":
                    pending = True
                elif etype == "error":
                    got_error = True
                # Stream all events through (HUD shows live tokens)
                yield _sse(event)
            if pending or got_error:
                # An error event (e.g. blocked/truncated reply) was already
                # sent above — don't follow it with a "done" that overwrites
                # the specific reason with a vague placeholder.
                return
            # The streamed tokens ARE the final reply — Gemini is the only
            # model in the loop. No second pass needed.
            raw = "".join(tokens).strip() or "(no reply from model)"
            # Update persisted memory to the final text.
            try:
                if BRAIN.memory.messages and BRAIN.memory.messages[-1].get("role") == "assistant":
                    BRAIN.memory.messages[-1]["content"] = raw
            except Exception:
                pass
            # Persist the rolling window to ~/.jarvis/history.json so the web
            # HUD, Telegram bot, and CLI all resume from the same local store.
            try:
                MEMORY.save()
            except Exception:
                pass
            yield _sse({"type": "done", "text": raw})
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            m = msg.lower()
            if "resource_exhausted" in m or "quota_exhausted" in m \
                    or ("429" in msg and ("quota" in m or "rate" in m)):
                user_text = (
                    "⏳ Both Gemini keys hit their rate limit. Wait a minute, "
                    "or set a different model in Settings (`gemini-2.5-flash`, "
                    "`gemini-2.0-flash-lite`)."
                )
            elif "401" in msg or "403" in msg or "api key" in m or "auth" in m:
                user_text = (
                    "🔑 Gemini rejected the API key. Open Settings and "
                    "re-paste your key from https://aistudio.google.com/apikey."
                )
            elif "404" in msg and "model" in m:
                user_text = (
                    "🚫 That Gemini model isn't available. Open Settings and "
                    "pick a different model."
                )
            elif "429" in msg or "rate" in m:
                user_text = "⏳ Rate-limited by Gemini. Try again in a few seconds."
            elif "timeout" in m or "timed out" in m:
                user_text = "⏱ Gemini timed out. Try again."
            elif "connection" in m or "network" in m:
                user_text = "📡 Network error — check your connection."
            else:
                user_text = f"Model error: {msg}"
            yield _sse({"type": "error", "text": user_text})

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/approve", methods=["POST"])
def approve():
    """Resolve a pending tool call (approve or deny), then resume streaming."""
    data = request.get_json(force=True, silent=True) or {}
    call_id = data.get("id")
    approved = bool(data.get("approve"))
    if not call_id:
        return jsonify({"error": "missing_id"}), 400

    result = BRAIN.resolve_approval(call_id, approved)
    if result is None:
        return jsonify({"error": "no_pending", "id": call_id}), 404

    if not approved:
        # No tools to run after denial; resume the model loop to get a response.
        def gen_denied():
            try:
                tokens: list[str] = []
                tool_results: list[dict] = []
                last_user = ""
                for m in reversed(BRAIN.memory.messages):
                    if m.get("role") == "user" and m.get("content"):
                        last_user = m["content"]
                        break
                for ev in BRAIN.continue_after_approval():
                    etype = ev.get("type")
                    if etype == "token":
                        tokens.append(ev.get("text", ""))
                    elif etype == "tool_done":
                        tool_results.append({
                            "name": ev.get("name", ""),
                            "result": ev.get("result", ""),
                        })
                    yield _sse(ev)
                raw = "".join(tokens).strip()
                if raw and last_user:
                    # The streamed tokens ARE the final reply — no second pass.
                    try:
                        if BRAIN.memory.messages and \
                                BRAIN.memory.messages[-1].get("role") == "assistant":
                            BRAIN.memory.messages[-1]["content"] = raw
                    except Exception:
                        pass
                    yield _sse({"type": "done", "text": raw})
            except Exception as exc:  # noqa: BLE001
                yield _sse({"type": "error", "text": f"Model error: {exc}"})
        return Response(gen_denied(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # Approved — the tool ran. Resume the loop to get the model's final response.
    def gen_resume():
        try:
            tokens: list[str] = []
            tool_results: list[dict] = []
            last_user = ""
            for m in reversed(BRAIN.memory.messages):
                if m.get("role") == "user" and m.get("content"):
                    last_user = m["content"]
                    break
            for ev in BRAIN.continue_after_approval():
                etype = ev.get("type")
                if etype == "token":
                    tokens.append(ev.get("text", ""))
                elif etype == "tool_done":
                    tool_results.append({
                        "name": ev.get("name", ""),
                        "result": ev.get("result", ""),
                    })
                yield _sse(ev)
            raw = "".join(tokens).strip()
            if raw and last_user:
                # The streamed tokens ARE the final reply — no second pass.
                try:
                    if BRAIN.memory.messages and \
                            BRAIN.memory.messages[-1].get("role") == "assistant":
                        BRAIN.memory.messages[-1]["content"] = raw
                except Exception:
                    pass
                yield _sse({"type": "done", "text": raw})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "text": f"Model error: {exc}"})
    return Response(gen_resume(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/vision", methods=["POST"])
def vision():
    if not CONFIG.has_key:
        return jsonify({"error": "no_key", "reply": "Set your API key first."}), 200
    data = request.get_json(force=True, silent=True) or {}
    image = data.get("image", "")
    text = data.get("message", "")
    if not image.startswith("data:image"):
        return jsonify({"error": "bad_image", "reply": "No valid image received."}), 200
    refresh_system_prompt()
    try:
        reply = BRAIN.vision(text, image)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": "vision", "reply": f"Vision failed: {exc}"}), 200
    return jsonify({"reply": reply})


@app.route("/api/see", methods=["POST"])
def see_screen():
    """On-demand screen capture + vision description."""
    if not CONFIG.has_key:
        return jsonify({"error": "no_key", "reply": "Set your API key first."}), 200
    data = request.get_json(force=True, silent=True) or {}
    question = (data.get("question") or "").strip()
    try:
        reply = BRAIN.see_screen(question)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": "see", "reply": f"Screen vision failed: {exc}"}), 200
    return jsonify({"reply": reply})


@app.route("/api/watchdog")
def watchdog_poll():
    return jsonify({"alerts": WATCHDOG.drain()})


# ── Gemini key check (no "credits" concept on the free tier) ─────
@app.route("/api/credits")
def credits():
    """Lightweight validity check against both configured Gemini keys.

    Gemini's free tier doesn't have a credits-balance concept, so we just
    ping a tiny model list call to confirm each key works. Returns the
    state of both keys so the HUD can warn the user.
    """
    keys = CONFIG.all_keys()
    if not keys:
        return jsonify({
            "available": False,
            "reason": "no_key",
            "message": (
                "No Gemini API key configured. Set JARVIS_GEMINI_KEY in .env. "
                "Get a free key at https://aistudio.google.com/apikey"
            ),
        })
    results = []
    available_any = False
    for i, key in enumerate(keys, start=1):
        try:
            resp = requests.get(
                f"{GEMINI_BASE}/gemini-2.0-flash",
                params={"key": key},
                timeout=5,
            )
            ok = resp.status_code == 200
            if ok:
                available_any = True
            results.append({
                "key_index": i,
                "ok": ok,
                "status": resp.status_code,
            })
        except Exception as exc:  # noqa: BLE001
            results.append({
                "key_index": i,
                "ok": False,
                "error": str(exc),
            })
    return jsonify({
        "available": available_any,
        "keys": results,
    })


# ── Telegram bot status ─────────────────────────────
@app.route("/api/telegram/status")
def telegram_status():
    if TELEGRAM is None:
        return jsonify({
            "available": False,
            "enabled": bool(CONFIG.telegram_enabled and CONFIG.telegram_token),
            "running": False,
            "authorized": 0,
            "reason": "python-telegram-bot not installed",
        })
    return jsonify({
        "available": True,
        "enabled": bool(CONFIG.telegram_enabled and CONFIG.telegram_token),
        "running": TELEGRAM.is_running(),
        "authorized": len(TELEGRAM.authorized_chat_ids()),
    })


@app.route("/api/backup", methods=["POST"])
def backup_memory():
    """Persist the local memory store and mirror a summary + files to the
    owner's Telegram chat(s). Local save always runs; the Telegram push needs
    the bot running with at least one authorized chat."""
    try:
        MEMORY.save()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"sent": False, "error": f"local save failed: {exc}"})
    if TELEGRAM is None or not TELEGRAM.is_running():
        return jsonify({"sent": False,
                        "error": "Telegram bot isn't running on the host."})
    if not TELEGRAM.authorized_chat_ids():
        return jsonify({"sent": False,
                        "error": "No authorized Telegram chat yet — DM the bot /start."})
    ok = TELEGRAM.request_memory_backup(reason="hud")
    return jsonify({"sent": bool(ok),
                    "error": None if ok else "Telegram backup could not be sent."})


# ── Agent: goals (autonomous planner/executor) ─────────
from jarvis.agent import goals as AGENT_GOALS  # noqa: E402


@app.route("/api/agent/status")
def agent_status():
    return jsonify(AGENT_SCHEDULER.status())


@app.route("/api/agent/goals", methods=["GET"])
def agent_goals_list():
    return jsonify({"goals": AGENT_GOALS.list_all()})


@app.route("/api/agent/goals", methods=["POST"])
def agent_goal_create():
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    cron = data.get("cron") or None
    priority = int(data.get("priority", 3))
    g = AGENT_GOALS.create(title, cron=cron, priority=priority)
    return jsonify(g)


@app.route("/api/agent/goals/<goal_id>/run", methods=["POST"])
def agent_goal_run(goal_id):
    res = AGENT_SCHEDULER.run_now(goal_id)
    return jsonify(res)


@app.route("/api/agent/goals/<goal_id>/pause", methods=["POST"])
def agent_goal_pause(goal_id):
    g = AGENT_GOALS.set_status(goal_id, "paused")
    if g is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(g)


@app.route("/api/agent/goals/<goal_id>/resume", methods=["POST"])
def agent_goal_resume(goal_id):
    g = AGENT_GOALS.set_status(goal_id, "pending")
    if g is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(g)


@app.route("/api/agent/goals/<goal_id>", methods=["DELETE"])
def agent_goal_delete(goal_id):
    ok = AGENT_GOALS.remove(goal_id)
    return jsonify({"ok": ok})


@app.route("/api/agent/tick", methods=["POST"])
def agent_tick():
    """Manually trigger a scheduler pass (for testing / manual control)."""
    results = AGENT_SCHEDULER.tick()
    return jsonify({"ran": len(results), "results": results})


# ── contacts CRUD ───────────────────────────────────
@app.route("/api/contacts", methods=["GET"])
def contacts_list():
    return jsonify({"contacts": contacts.list_all()})


@app.route("/api/contacts", methods=["POST"])
def contacts_add():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    aliases = data.get("aliases") or []
    apps = data.get("apps") or ["whatsapp"]
    if not name or not phone:
        return jsonify({"error": "name and phone required"}), 400
    try:
        c = contacts.add(name, phone, aliases, apps)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"contact": c})


@app.route("/api/contacts/<name>", methods=["DELETE"])
def contacts_delete(name):
    n = contacts.remove(name)
    return jsonify({"removed": n})


# ── sessions history ────────────────────────────────
@app.route("/api/sessions", methods=["GET"])
def sessions_list():
    limit = int(request.args.get("limit", 50))
    items = sessions.all_summaries()
    return jsonify({"sessions": items[-limit:][::-1]})


# ── QR code generator (LAN URL → PNG) ────────────────
@app.route("/api/qr")
def qr_code():
    """Return a PNG QR code for the given URL (defaults to the LAN URL).

    Optional query params:
      - url=<text>      override the encoded text (e.g. ?url=192.168.1.5:5000)
      - size=<int>      pixel size of the PNG (default 320, max 1024)
      - dark=<hex>      dark module color (default 0a0f14, themed cyan)
      - light=<hex>     light module color (default ffffff)
    """
    text = (request.args.get("url") or _lan_url() or "").strip()
    if not text:
        return jsonify({"error": "no_url", "reply": "No URL to encode."}), 400
    # If only an IP was given, prepend the scheme.
    if not text.startswith(("http://", "https://", "wifi:")):
        text = "http://" + text
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_M
    except ImportError:
        return jsonify({"error": "no_qr_lib",
                        "reply": "Install qrcode: pip install qrcode[pil]"}), 500
    size = min(1024, max(96, int(request.args.get("size", 320))))
    dark = (request.args.get("dark") or "#0a0f14").lstrip("#")
    light = (request.args.get("light") or "#ffffff").lstrip("#")
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#" + dark, back_color="#" + light).convert("RGB")
        from io import BytesIO
        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return Response(
            buf.getvalue(), mimetype="image/png",
            headers={
                "Cache-Control": "no-store",
                "X-Qr-Url": text,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": "qr_failed", "reply": f"QR failed: {exc}"}), 500


# ── live system telemetry ────────────────────────────
_net_prev = {"t": None, "sent": 0, "recv": 0}
# city → {"at": epoch, "data": {...}} — 10-min cache for /api/weather.
_WEATHER_CACHE: dict[str, dict] = {}


def _net_rates(psutil):
    n = psutil.net_io_counters()
    now = time.time()
    if _net_prev["t"] is None:
        rate = (0.0, 0.0)
    else:
        dt = max(1e-6, now - _net_prev["t"])
        rate = ((n.bytes_recv - _net_prev["recv"]) / dt, (n.bytes_sent - _net_prev["sent"]) / dt)
    _net_prev.update(t=now, sent=n.bytes_sent, recv=n.bytes_recv)
    return rate


@app.route("/api/system")
def system_stats():
    try:
        import platform as _pf

        import psutil
    except ImportError:
        return jsonify({"available": False})

    mem = psutil.virtual_memory()
    root = os.path.abspath(os.sep)
    try:
        disk = psutil.disk_usage(root)
    except OSError:
        disk = psutil.disk_usage("/")
    down, up = _net_rates(psutil)
    batt = getattr(psutil, "sensors_battery", lambda: None)()
    freq = psutil.cpu_freq()

    return jsonify({
        "available": True,
        "cpu": psutil.cpu_percent(),
        "cpu_cores": psutil.cpu_count(logical=True),
        "cpu_percore": psutil.cpu_percent(percpu=True),
        "cpu_freq": round(freq.current) if freq else 0,
        "ram": mem.percent,
        "ram_used": mem.used, "ram_total": mem.total,
        "disk": disk.percent, "disk_used": disk.used, "disk_total": disk.total,
        "net_down": down, "net_up": up,
        "battery": None if batt is None else round(batt.percent),
        "plugged": None if batt is None else bool(batt.power_plugged),
        "procs": len(psutil.pids()),
        "uptime": int(time.time() - psutil.boot_time()),
        "host": socket.gethostname(),
        "os": f"{_pf.system()} {_pf.release()}",
    })


@app.route("/api/weather")
def weather():
    """Current weather as structured JSON for the HUD. Wraps the same free
    wttr.in service the get_weather tool uses; city auto-detects by IP when
    omitted. Results are cached for 10 minutes so polling stays light."""
    city = (request.args.get("city") or "").strip()
    now = time.time()
    cached = _WEATHER_CACHE.get(city)
    if cached and now - cached["at"] < 600:
        return jsonify(cached["data"])
    data: dict = {"available": False}
    try:
        import urllib.parse as _up
        url = f"https://wttr.in/{_up.quote(city)}?format=j1"
        r = requests.get(url, timeout=8)
        if r.ok:
            j = r.json()
            cur = (j.get("current_condition") or [{}])[0]
            area = (j.get("nearest_area") or [{}])[0]
            name = ""
            if area.get("areaName"):
                name = area["areaName"][0].get("value", "")
            data = {
                "available": True,
                "city": city or name or "here",
                "temp_c": cur.get("temp_C"),
                "feels_c": cur.get("FeelsLikeC"),
                "humidity": cur.get("humidity"),
                "desc": (cur.get("weatherDesc") or [{}])[0].get("value", "").strip(),
                "code": cur.get("weatherCode", ""),
            }
    except Exception as exc:  # noqa: BLE001
        data = {"available": False, "error": str(exc)}
    _WEATHER_CACHE[city] = {"at": now, "data": data}
    return jsonify(data)


@app.route("/api/location", methods=["POST"])
def location():
    """Accept real-time lat/lon from the browser, reverse-geocode to a
    city, and return weather for THAT place. No API key needed
    (BigDataCloud free reverse-geocode + wttr.in)."""
    payload = request.get_json(silent=True) or {}
    lat = payload.get("lat")
    lon = payload.get("lon")
    if lat is None or lon is None:
        return jsonify({"available": False, "error": "missing lat/lon"}), 400
    now = time.time()
    city = ""
    try:
        import urllib.parse as _up
        geo = requests.get(
            f"https://api.bigdatacloud.net/data/reverse-geocode-client"
            f"?latitude={lat}&longitude={lon}&localityLanguage=en",
            timeout=8,
        )
        if geo.ok:
            g = geo.json()
            city = g.get("city") or g.get("locality") or g.get("principalSubdivision")
    except Exception:  # noqa: BLE001
        city = ""
    if not city:
        try:
            ip = requests.get("https://ipapi.co/json/", timeout=8).json()
            city = ip.get("city", "")
        except Exception:  # noqa: BLE001
            pass
    cached = _WEATHER_CACHE.get(city or "here")
    if cached and now - cached["at"] < 600:
        w = cached["data"]
    else:
        w = {"available": False}
        try:
            url = f"https://wttr.in/{_up.quote(city)}?format=j1"
            r = requests.get(url, timeout=8)
            if r.ok:
                j = r.json()
                cur = (j.get("current_condition") or [{}])[0]
                area = (j.get("nearest_area") or [{}])[0]
                name = (area.get("areaName") or [{}])[0].get("value", "") if area.get("areaName") else ""
                w = {
                    "available": True,
                    "city": city or name or "here",
                    "temp_c": cur.get("temp_C"),
                    "feels_c": cur.get("FeelsLikeC"),
                    "humidity": cur.get("humidity"),
                    "desc": (cur.get("weatherDesc") or [{}])[0].get("value", "").strip(),
                    "code": cur.get("weatherCode", ""),
                }
        except Exception as exc:  # noqa: BLE001
            w = {"available": False, "error": str(exc)}
        _WEATHER_CACHE[city or "here"] = {"at": now, "data": w}
    return jsonify({"available": True, "city": city or "here", "weather": w})


@app.route("/api/export")
def export():
    # PIN is read from the X-Jarvis-Pin header by the before_request guard
    # for remote callers; local callers skip the guard. We don't accept ?pin=...
    lines = [f"# JARVIS conversation — {datetime.now():%Y-%m-%d %H:%M}\n"]
    for m in MEMORY.messages:
        role = m.get("role")
        if role == "system":
            continue
        if role == "tool":
            lines.append(f"> ⚙ *{m.get('name')}* → {str(m.get('content'))[:200]}\n")
        elif role == "assistant" and m.get("content"):
            lines.append(f"**JARVIS:** {m['content']}\n")
        elif role == "user" and m.get("content"):
            lines.append(f"**You:** {m['content']}\n")
    md = "\n".join(lines)
    return Response(
        md, mimetype="text/markdown",
        headers={"Content-Disposition": "attachment; filename=jarvis_chat.md"},
    )


# ── File explorer ──────────────────────────────────────
_ALLOWED_FILE_ROOTS = [
    os.path.expanduser("~"),
]


@app.route("/api/files", methods=["GET", "POST"])
def file_explorer():
    """Browse, read, and upload files on the server.

    GET  /api/files?path=<path>        — list directory contents
    POST /api/files                    — read file content or create file
      body: { path, action: "read" | "write", content: "..." }
    """
    if request.method == "GET":
        raw = (request.args.get("path") or "").strip()
        # Handle ~ as home directory shortcut
        if raw in ("~", ""):
            path = os.path.expanduser("~")
        else:
            path = os.path.expanduser(raw)
        if not os.path.exists(path):
            return jsonify({"error": "not_found", "message": "Path does not exist"}), 404

        def _safe_path(p: str) -> bool:
            absp = os.path.abspath(p)
            for root in _ALLOWED_FILE_ROOTS:
                if absp.startswith(os.path.abspath(root)):
                    return True
            return False

        if not _safe_path(path):
            return jsonify({"error": "forbidden", "message": "Access denied"}), 403

        if os.path.isfile(path):
            try:
                size = os.path.getsize(path)
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read(100000)
                return jsonify({
                    "path": path,
                    "type": "file",
                    "size": size,
                    "content": content,
                    "truncated": size > 100000,
                })
            except Exception as exc:
                return jsonify({"error": "read_failed", "message": str(exc)}), 500

        try:
            entries = []
            for entry in sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower())):
                try:
                    st = entry.stat()
                    entries.append({
                        "name": entry.name,
                        "path": entry.path,
                        "is_dir": entry.is_dir(),
                        "size": st.st_size if not entry.is_dir() else 0,
                        "modified": st.st_mtime,
                    })
                except OSError:
                    continue
            return jsonify({
                "path": path,
                "type": "dir",
                "entries": entries,
                "parent": os.path.dirname(os.path.abspath(path)) if os.path.dirname(path) else None,
            })
        except OSError as exc:
            return jsonify({"error": "list_failed", "message": str(exc)}), 500

    # POST — read or write a file
    data = request.get_json(force=True, silent=True) or {}
    path = (data.get("path") or "").strip()
    action = data.get("action", "read")
    if not path:
        return jsonify({"error": "path_required"}), 400

    # Same safe-path check as GET (only allow home & workspace)
    absp = os.path.abspath(path)
    if not any(absp.startswith(os.path.abspath(r)) for r in _ALLOWED_FILE_ROOTS):
        return jsonify({"error": "forbidden", "message": "Access denied"}), 403

    if action == "read":
        if not os.path.isfile(path):
            return jsonify({"error": "not_found"}), 404
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read(500000)
            return jsonify({"path": path, "content": content, "truncated": len(content) >= 500000})
        except Exception as exc:
            return jsonify({"error": "read_failed", "message": str(exc)}), 500

    if action == "write":
        content = data.get("content", "")
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            return jsonify({"path": path, "saved": True, "size": len(content)})
        except Exception as exc:
            return jsonify({"error": "write_failed", "message": str(exc)}), 500

    return jsonify({"error": "unknown_action"}), 400


# ── Email integration ──────────────────────────────────
_EMAIL_CONFIG: dict = {}


def _load_email_from_env() -> None:
    """Load email config from .env so it persists across restarts."""
    email = os.getenv("JARVIS_EMAIL", "").strip()
    password = os.getenv("JARVIS_EMAIL_PASSWORD", "").strip()
    if email and password:
        _EMAIL_CONFIG.update({
            "email": email,
            "password": password,
            "smtp_host": os.getenv("JARVIS_SMTP_HOST", "smtp.gmail.com").strip(),
            "smtp_port": int(os.getenv("JARVIS_SMTP_PORT", "587")),
            "imap_host": os.getenv("JARVIS_IMAP_HOST", "imap.gmail.com").strip(),
            "imap_port": int(os.getenv("JARVIS_IMAP_PORT", "993")),
        })
        _email_tool.patch_credentials(_EMAIL_CONFIG)
        print(f"[email] configured for {email}")


_load_email_from_env()


@app.route("/api/email/config", methods=["GET", "POST"])
def email_config():
    if request.method == "GET":
        return jsonify({
            "configured": bool(_EMAIL_CONFIG.get("smtp_host")),
            "email": _EMAIL_CONFIG.get("email", ""),
            "smtp_host": _EMAIL_CONFIG.get("smtp_host", ""),
            "smtp_port": _EMAIL_CONFIG.get("smtp_port", 587),
            "imap_host": _EMAIL_CONFIG.get("imap_host", ""),
            "imap_port": _EMAIL_CONFIG.get("imap_port", 993),
        })
    data = request.get_json(force=True, silent=True) or {}
    if data.get("email"):
        _EMAIL_CONFIG["email"] = data["email"].strip()
    if data.get("password") and data["password"] != "********":
        _EMAIL_CONFIG["password"] = data["password"]
    if data.get("smtp_host"):
        _EMAIL_CONFIG["smtp_host"] = data["smtp_host"].strip()
    if data.get("smtp_port"):
        _EMAIL_CONFIG["smtp_port"] = int(data["smtp_port"])
    if data.get("imap_host"):
        _EMAIL_CONFIG["imap_host"] = data["imap_host"].strip()
    if data.get("imap_port"):
        _EMAIL_CONFIG["imap_port"] = int(data["imap_port"])
    if "clear" in data:
        _EMAIL_CONFIG.clear()
    # Keep the email_tool in sync whenever config changes.
    _email_tool.patch_credentials(_EMAIL_CONFIG)
    return jsonify({"ok": True, "configured": bool(_EMAIL_CONFIG.get("smtp_host"))})


@app.route("/api/email/send", methods=["POST"])
def email_send():
    if not _EMAIL_CONFIG.get("smtp_host") or not _EMAIL_CONFIG.get("email"):
        return jsonify({"error": "not_configured", "message": "Configure email in Settings first."}), 200
    data = request.get_json(force=True, silent=True) or {}
    to = (data.get("to") or "").strip()
    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()
    if not to or not subject:
        return jsonify({"error": "missing_fields", "message": "Recipient and subject required."}), 200
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body, "plain" if not data.get("html") else "html")
        msg["Subject"] = subject
        msg["From"] = _EMAIL_CONFIG["email"]
        msg["To"] = to
        with smtplib.SMTP(_EMAIL_CONFIG["smtp_host"], _EMAIL_CONFIG.get("smtp_port", 587)) as s:
            s.starttls()
            s.login(_EMAIL_CONFIG["email"], _EMAIL_CONFIG.get("password", ""))
            s.send_message(msg)
        return jsonify({"ok": True, "to": to, "subject": subject})
    except Exception as exc:
        return jsonify({"error": "send_failed", "message": str(exc)}), 200


@app.route("/api/email/inbox", methods=["GET"])
def email_inbox():
    if not _EMAIL_CONFIG.get("imap_host") or not _EMAIL_CONFIG.get("email"):
        return jsonify({"error": "not_configured", "inbox": []}), 200
    max_msgs = min(int(request.args.get("limit", 10)), 50)
    try:
        import imaplib
        import email as email_lib
        from email.header import decode_header
        m = imaplib.IMAP4_SSL(_EMAIL_CONFIG["imap_host"], _EMAIL_CONFIG.get("imap_port", 993))
        m.login(_EMAIL_CONFIG["email"], _EMAIL_CONFIG.get("password", ""))
        m.select("INBOX")
        _, data = m.search(None, "ALL")
        ids = data[0].split()[-max_msgs:] if data[0] else []
        messages = []
        for mid in reversed(ids):
            _, msg_data = m.fetch(mid, "(RFC822)")
            raw = email_lib.message_from_bytes(msg_data[0][1])
            subj = "".join(
                (decode_header(part)[0][0].decode(errors="replace") if isinstance(decode_header(part)[0][0], bytes)
                 else str(decode_header(part)[0][0]))
                for part in [raw["Subject"] or ""]
            )
            messages.append({
                "id": mid.decode(),
                "from": str(raw["From"] or ""),
                "subject": subj,
                "date": str(raw["Date"] or ""),
            })
        m.logout()
        return jsonify({"inbox": messages})
    except Exception as exc:
        return jsonify({"error": str(exc), "inbox": []}), 200


# ── Reminders ──────────────────────────────────────────
_REMINDERS: list[dict] = []
_REMINDER_ID = 0


@app.route("/api/reminders", methods=["GET"])
def reminders_list():
    return jsonify({"reminders": _REMINDERS})


@app.route("/api/reminders", methods=["POST"])
def reminders_create():
    global _REMINDER_ID
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    when = data.get("when")  # ISO datetime string or None for "now"
    if not text:
        return jsonify({"error": "text_required"}), 400
    _REMINDER_ID += 1
    rem = {
        "id": f"rem_{_REMINDER_ID}",
        "text": text,
        "when": when,
        "created": datetime.now().isoformat(),
        "done": False,
    }
    _REMINDERS.insert(0, rem)
    return jsonify({"reminder": rem})


@app.route("/api/reminders/<rem_id>/done", methods=["POST"])
def reminders_done(rem_id):
    for r in _REMINDERS:
        if r["id"] == rem_id:
            r["done"] = True
            return jsonify({"ok": True})
    return jsonify({"error": "not_found"}), 404


@app.route("/api/reminders/<rem_id>", methods=["DELETE"])
def reminders_delete(rem_id):
    global _REMINDERS
    _REMINDERS = [r for r in _REMINDERS if r["id"] != rem_id]
    return jsonify({"ok": True})


# ── Multi-chat tabs ────────────────────────────────────
_CHAT_TABS: dict[str, list[dict]] = {"default": []}


@app.route("/api/chat/tabs", methods=["GET"])
def chat_tabs_list():
    return jsonify({"tabs": list(_CHAT_TABS.keys()), "active": "default"})


@app.route("/api/chat/tabs/<tab_id>/messages", methods=["GET"])
def chat_tab_messages(tab_id):
    msgs = _CHAT_TABS.get(tab_id, [])
    return jsonify({"tab": tab_id, "messages": msgs})


@app.route("/api/chat/tabs/<tab_id>/save", methods=["POST"])
def chat_tab_save(tab_id):
    data = request.get_json(force=True, silent=True) or {}
    msgs = data.get("messages", [])
    _CHAT_TABS[tab_id] = msgs
    return jsonify({"ok": True, "tab": tab_id, "count": len(msgs)})


@app.route("/api/chat/tabs/<tab_id>/delete", methods=["DELETE"])
def chat_tab_delete(tab_id):
    if tab_id in _CHAT_TABS and tab_id != "default":
        del _CHAT_TABS[tab_id]
    return jsonify({"ok": True})


# ── Conversation search ────────────────────────────────
@app.route("/api/chat/search")
def chat_search():
    q = (request.args.get("q") or "").strip().lower()
    if not q or len(q) < 2:
        return jsonify({"results": []})
    results = []
    for m in MEMORY.messages:
        content = (m.get("content") or "")
        role = m.get("role", "")
        if role in ("user", "assistant") and q in content.lower():
            results.append({
                "role": role,
                "content": content[:500],
                "index": len(results),
            })
    return jsonify({"results": results[:50]})


# ── Plugin marketplace ─────────────────────────────────
@app.route("/api/plugins")
def plugins_list():
    """List all registered automations with enabled/disabled state."""
    meta = REGISTRY.metadata()
    disabled = set(REGISTRY.disabled()) if hasattr(REGISTRY, "disabled") else set()
    tools = []
    for name in sorted(meta.keys()):
        m = meta.get(name, {})
        tools.append({
            "name": name,
            "description": m.get("description", ""),
            "enabled": name not in disabled,
            "dangerous": m.get("destructive", False),
        })
    return jsonify({"plugins": tools})


@app.route("/api/plugins/<name>/toggle", methods=["POST"])
def plugin_toggle(name):
    data = request.get_json(force=True, silent=True) or {}
    enable = data.get("enable", True)
    if hasattr(REGISTRY, "set_enabled"):
        REGISTRY.set_enabled(name, enable)
        return jsonify({"ok": True, "name": name, "enabled": enable})
    return jsonify({"error": "not_supported"}), 200


@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _open_browser() -> None:
    webbrowser.open("http://127.0.0.1:5000")


def _check_gemini_keys() -> None:
    """Best-effort check of Gemini API key validity at startup.

    Warns the user if a key is missing or rejected — better than
    discovering it on the first chat message.
    """
    keys = CONFIG.all_keys()
    if not keys:
        print(
            "[gemini] ⚠ no API key configured. Set JARVIS_GEMINI_KEY "
            "(and JARVIS_GEMINI_KEY_BACKUP) in .env. Get free keys at "
            "https://aistudio.google.com/apikey"
        )
        return
    for i, key in enumerate(keys, start=1):
        label = f"key #{i}" if len(keys) > 1 else "key"
        try:
            resp = requests.get(
                f"{GEMINI_BASE}/gemini-2.0-flash",
                params={"key": key},
                timeout=5,
            )
            if resp.status_code == 200:
                print(f"[gemini] {label}: OK")
            elif resp.status_code in (400, 401, 403):
                print(
                    f"[gemini] {label}: rejected ({resp.status_code}). "
                    "Re-paste the key in Settings."
                )
            elif resp.status_code == 429:
                print(
                    f"[gemini] {label}: currently rate-limited. The Brain will "
                    "auto-fall back to the other key when this happens."
                )
            else:
                print(f"[gemini] {label}: status {resp.status_code}")
        except Exception as exc:  # noqa: BLE001
            # Never block startup on this.
            print(f"[gemini] {label}: check skipped ({exc})")


def run_server(open_browser: bool = False) -> None:
    """Boot the JARVIS web HUD: watchdog, Gemini key check, Telegram bot, then
    serve the Flask app on 0.0.0.0:5000. This is the single entry point for the
    whole assistant now that the desktop GUI is gone — `python main.py` and
    `python server.py` both land here."""
    WATCHDOG.start()
    # Watchdog now fans out to the AlertHub itself (see Watchdog._emit), so
    # subscribers like the Telegram bot get every alert at emit time. The
    # HUD keeps polling /api/watchdog for its own toast list — no shared
    # destructive drain() between the two consumers anymore.
    # Quick startup check of Gemini key validity.
    _check_gemini_keys()
    # Start the Telegram bot if configured.
    if TELEGRAM is not None:
        ok = TELEGRAM.start()
        if ok:
            print(f"[telegram] bot started (chat_id PIN-gated, token ends …"
                  f"{CONFIG.telegram_token[-6:]})")
        elif CONFIG.telegram_enabled:
            print("[telegram] enabled in config but failed to start (see above)")
    lan = _lan_url()
    print("\n  == JARVIS HUD ==")
    print("     Local :  http://127.0.0.1:5000")
    if lan:
        print(f"     LAN   :  {lan}   (needs access PIN - set it in Settings)")
    if TELEGRAM is not None and CONFIG.telegram_enabled and CONFIG.telegram_token:
        print("     TG    :  Telegram bot running — DM it /start to link")
    print()
    if open_browser:
        Timer(1.2, _open_browser).start()
    # On shutdown, persist the local store and mirror a final backup to
    # Telegram (best-effort — never blocks exit).
    import atexit

    def _on_shutdown() -> None:
        try:
            MEMORY.save()
        except Exception:  # noqa: BLE001
            pass
        if TELEGRAM is not None and TELEGRAM.is_running():
            try:
                TELEGRAM.request_memory_backup(reason="shutdown")
            except Exception:  # noqa: BLE001
                pass

    atexit.register(_on_shutdown)
    port = int(os.getenv("JARVIS_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
    print(f"JARVIS HUD running on http://127.0.0.1:{port}")


if __name__ == "__main__":
    run_server()
