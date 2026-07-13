# 🤖 JARVIS — Now an Autonomous Agent

**Upgrade complete.** JARVIS went from a *reactive tool-caller* to a
**true agent**: it plans goals into multi-step tool sequences, executes them
with dependency ordering + retries, reflects on outcomes, and runs
**autonomous background loops** that report to Telegram.

---

## What was added

| File | Lines | Role |
|------|-------|------|
| `jarvis/agent/goals.py` | 180 | Persistent goal store (`~/.jarvis/goals.json`) |
| `jarvis/agent/planner.py` | 110 | Goal text → ordered tool plan (via Gemini) |
| `jarvis/agent/executor.py` | 175 | Step runner: deps + retries + approval gate |
| `jarvis/agent/reflection.py` | 80 | Outcome → success / retry / replan / abort |
| `jarvis/agent/scheduler.py` | 100 | Background daemon + Telegram reports |
| `jarvis/agent/__init__.py` | 150 | Orchestrator (plan → execute → reflect) |
| `brain.py` | +34 | `complete()` one-shot JSON method for planner |
| `server.py` | +7 routes | `/api/agent/*` + boot scheduler |
| `telegram_bot.py` | +5 cmds | `/goal` `/goals` `/run` `/pause` `/agent` |
| `templates/index.html` | +15 | Goals panel |
| `static/js/hud.js` | +100 | Goals panel logic |
| `static/css/hud.css` | +38 | Goals panel styling |
| `test_diagnostic.py` | +55 | 12 agent tests |

**Total: ~960 new lines across 13 files.**

---

## How it works (agent loop)

```
You:  "plan my evening — book a table, order dessert"
  │
  ▼
PLANNER    →  [book_table, order_dessert]  (Gemini, JSON)
  │
  ▼
EXECUTOR   →  runs each step, respects depends_on, retries ×N
  │
  ▼
REFLECTION →  all done? → success : retry / replan / abort
  │
  ▼
SCHEDULER →  logs to goals.json + DMs you on Telegram
```

---

## New capabilities

1. **Multi-step planning** — one sentence → 1-6 tool calls in sequence.
2. **Dependency chaining** — step B waits for step A's result (topological order).
3. **Retry + backoff** — failed steps retried up to `max_retries` (default 2).
4. **Reflection** — LLM decides retry vs abort when partial failure.
5. **Autonomous scheduler** — daemon thread, polls every 60s, runs due goals.
6. **Cron goals** — `*/30 * * * *` re-runs forever, DMs on change.
7. **Telegram reports** — every goal run summarized to your phone.
8. **Persistence** — goals survive restarts in `~/.jarvis/goals.json`.
9. **Safety** — destructive tools still hit the approval gate; respects `owner_trust`.
10. **Auditable** — every run logged to goal history (last 20 kept).

---

## How to use it

### HUD (web)
1. Open JARVIS at http://127.0.0.1:5000
2. Scroll to **AGENT GOALS** panel
3. Type a goal → **+ CREATE** → it plans & runs instantly
4. Watch status: ⏳ pending → 🔄 running → ✅ done
5. **▶ RUN** / **⏸ PAUSE** / **✕ DELETE** per goal

### Telegram
```
/goal book a table for 2 at a Chinese place tonight
/goals          → list all goals + status
/run <goal_id>  → run now
/pause <goal_id> → pause a cron goal
/agent          → scheduler status (running? due count?)
```

### CLI / code
```python
from jarvis.agent import Agent
agent = Agent(brain=BRAIN)
agent.run_goal("g_abc123")

# or one-shot:
from jarvis.agent import create_and_run
create_and_run("summarize my last 3 chats and note action items")
```

### API
```
POST /api/agent/goals        {title, cron?, priority?}
GET  /api/agent/goals
POST /api/agent/goals/<id>/run
POST /api/agent/goals/<id>/pause
POST /api/agent/goals/<id>/resume
DELETE /api/agent/goals/<id>
POST /api/agent/tick          (manual scheduler pass)
GET  /api/agent/status
```

---

## Verification

```
✅ All .py files parse cleanly (syntax check)
✅ Agent package imports OK
✅ 12/12 agent unit tests pass (offline, no API key):
   - goal CRUD + persistence
   - planner validation (drops unknown tools)
   - executor (deps + order + dispatch)
   - reflection verdicts (success / retry / abort)
   - scheduler lifecycle (start / status / stop)
✅ 7 agent routes wired in server.py
✅ 5 agent commands registered in telegram_bot.py
✅ HUD Goals panel (HTML + JS + CSS)
```

---

## Notes / next steps

- **Planner + reflection need a Gemini key** (the LLM step). The
  executor/reflection heuristic + scheduler work fully offline.
- The planner currently emits steps; richer planning (sub-goals,
  parallel branches) is a natural v2.
- To enable autonomous Telegram reports: set `JARVIS_TELEGRAM_TOKEN`
  + `/start` the bot, then the scheduler auto-pushes via `push_text`.
- Run the full suite: `python test_diagnostic.py` (needs server up
  for the HTTP half; agent section runs standalone).

Built on top of your existing 72-tool JARVIS. 🤖
