# 🤖 JARVIS Agent Upgrade — Architecture

Turning JARVIS from a *reactive tool-caller* into a *true autonomous agent*.
It can now **plan**, **execute multi-step goals**, **reflect**, **retry on failure**,
and **run background loops** that report via Telegram.

---

## 1. What changes (mental model)

| Before | After |
|--------|-------|
| "jarvis, open youtube" → 1 tool call | "plan my evening: book a table, order dessert" → 4-5 tool calls in sequence |
| No memory of outcomes | `reflection` decides retry vs abort |
| Only responds when you type | `scheduler` wakes every N min, runs goals, DMs you results |
| Tools fire once | Executor handles **dependencies** + **retries** |

## 2. Module map (`jarvis/agent/`)

```
jarvis/agent/
├── goals.py        # persistent goal store (~/.jarvis/goals.json)
├── planner.py      # Goal text → ordered plan of tool steps (LLM)
├── executor.py     # Runs steps, handles deps + retries, streams progress
├── reflection.py    # Evaluates result → success | retry | abort | replan
├── scheduler.py     # Background loop: poll goals, run due ones, Telegram reports
└── __init__.py    # Agent orchestrator (planner→executor→reflection loop)
```

## 3. Data model

```python
Goal = {
  "id": "g_xxx",
  "title": "Plan my evening",
  "status": "pending|running|done|failed|paused",
  "priority": 1-5,
  "cron": "*/30 * * * *" | None,   # None = run-once
  "steps": [Step],
  "created_at", "last_run", "next_run",
  "history": [ {ts, status, summary, steps_done} ],
  "max_retries": 2,
}

Step = {
  "tool": "open_website",
  "args": {"url": "..."},
  "depends_on": [step_index],   # optional
  "status": "pending|running|done|failed|skipped",
  "result": "...",
  "attempts": 0,
}
```

## 4. Agent loop (per goal)

```
plan    → LLM breaks title into ordered tool steps
execute → executor runs each (retry up to N, respect deps)
reflect → did it succeed? if no and retries left → replan/retry
report  → scheduler DMs summary to Telegram + logs to history
```

## 5. Planner prompt (key part)

> You are JARVIS's planner. Given a GOAL, output JSON:
> `{ "steps": [ {"tool": "...", "args": {...}, "depends_on": [i]} ] }`
> Only use tools from the provided registry. Chain deps where output feeds input
> (e.g. search_restaurants → get_menu → add_to_cart).

## 6. Scheduler (autonomy)

- Runs as a daemon thread inside `server.py` (already a Flask app, so it's alive).
- Every `POLL_SECONDS` (default 60): loads due goals, runs them, reports.
- One-off goals run once then flip to `done`.
- Cron goals (e.g. `*/30`) re-run forever and DM you on change.
- Telegram report format:
  ```
  🤖 Goal "Plan my evening" → ✅ Done
  • book_table → ✅
  • order_dessert → ✅
  Total: 2/2 steps · 14s
  ```

## 7. Safety

- Destructive tools (shutdown, delete, send_whatsapp) still hit the **approval gate**.
- Autonomous runs respect `owner_trust` — if off, agent pauses for approval.
- Every goal run is logged to `goals.json` history (auditable).

## 8. New tools exposed to planner

All 72 existing tools are available. Plus agent-internal:
- `agent_create_goal(title, cron?)` — spawn a sub-goal
- `agent_list_goals()` — introspect
- `agent_pause_goal(id)` / `agent_resume_goal(id)`

## 9. UX surface

- **HUD:** new "Goals" panel — list, create, pause, view history.
- **Telegram:** `/goal <text>` to create, `/goals` to list, `/pause <id>`, `/run <id>`.
- **CLI:** `goal "..."`, `goals`, `run <id>`.

## 10. Files to add

| File | Lines (est) | Purpose |
|------|--------------|---------|
| `jarvis/agent/goals.py` | ~140 | Goal CRUD + persistence |
| `jarvis/agent/planner.py` | ~120 | LLM goal→plan |
| `jarvis/agent/executor.py` | ~160 | Step runner + retries + deps |
| `jarvis/agent/reflection.py` | ~90 | Outcome evaluator |
| `jarvis/agent/scheduler.py` | ~130 | Background loop + Telegram |
| `jarvis/agent/__init__.py` | ~80 | Orchestrator |

Plus edits to `server.py`, `telegram_bot.py`, `hud.js`, `index.html`, `hud.css`.
