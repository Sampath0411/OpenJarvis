"""Goal → ordered plan of tool-calls, via the same Gemini brain JARVIS uses.

The planner is just a *prompt shape*: we ask the model to emit JSON
describing the steps, then validate it against the live tool registry.
"""
from __future__ import annotations

import json
import re
from typing import Any

from jarvis.automations.registry import REGISTRY

_PLANNER_PROMPT = """You are JARVIS's PLANNER module. Given a GOAL, break it into an \
ordered list of tool calls that achieve it.

RULES:
- ONLY use tools from the registry below.
- Each step is an object with: tool (string name), args (object), depends_on (array of step indices that must run first, or empty).
- depends_on is a list of 0-based step indices this step needs FIRST.
  Use it when one step's OUTPUT feeds another's INPUT
  (e.g. search_restaurants then get_restaurant_menu then add_to_cart).
- Keep it minimal: 1-6 steps. If the goal is a single action, 1 step.
- args must match the tool's declared parameters.

REGISTRY (name: description):
__REGISTRY__

GOAL: __GOAL__

Respond with ONLY valid JSON, no markdown, no commentary. Example shape:
{"steps": [ {"tool": "get_datetime", "args": {}, "depends_on": []} ]}"""


def _build_prompt(registry: str, goal: str) -> str:
    return (
        _PLANNER_PROMPT
        .replace("__REGISTRY__", registry)
        .replace("__GOAL__", goal)
    )


def _registry_block() -> str:
    out = []
    for schema in REGISTRY.schemas():
        fn = schema.get("function", {})
        name = fn.get("name", "?")
        desc = fn.get("description", "")
        out.append(f"- {name}: {desc}")
    return "\n".join(out)


def plan(goal: str, brain=None) -> list[dict[str, Any]]:
    """Return a list of step dicts. Falls back to a single generic step if
    the LLM is unavailable.

    If `brain` is provided (a JARVIS Brain instance), we use its
    `ask_raw` / completion path; otherwise we return a heuristic plan.
    """
    registry = _registry_block()
    prompt = _build_prompt(registry, goal)

    raw = None
    if brain is not None:
        try:
            raw = brain.complete(prompt, max_tokens=800)
        except Exception:
            raw = None

    if raw:
        steps = _extract_steps(raw)
        if steps:
            return _validate(steps)

    # Fallback: keyword heuristic that maps the goal to REAL tools.
    g = goal.lower()
    steps = []
    if any(w in g for w in ("time", "date", "clock", "today")):
        steps.append({"tool": "get_datetime", "args": {}, "depends_on": []})
    if any(w in g for w in ("weather", "temperature", "rain")):
        steps.append({"tool": "get_weather", "args": {"city": "Visakhapatnam"}, "depends_on": []})
    if any(w in g for w in ("note", "remember", "remind", "todo")):
        steps.append({"tool": "add_note", "args": {"text": goal}, "depends_on": []})
    if any(w in g for w in ("search", "find", "google", "look up")):
        steps.append({"tool": "web_search", "args": {"query": goal}, "depends_on": []})
    if steps:
        return _validate(steps)
    # Last resort: a single reasoning call through the chat brain.
    return [
        {
            "tool": "who_am_i",
            "args": {},
            "depends_on": [],
        }
    ]


def _extract_steps(raw: str) -> list[dict] | None:
    # Strip code fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    # Grab the first balanced JSON object
    m = re.search(r"\{[\s\S]*?\}", raw)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:
        return None
    steps = data.get("steps")
    if not isinstance(steps, list):
        return None
    return steps


def _validate(steps: list[dict]) -> list[dict]:
    """Keep only steps that reference real tools; assign clean indices."""
    valid: list[dict] = []
    for i, s in enumerate(steps):
        name = s.get("tool")
        if not isinstance(name, str) or name not in REGISTRY.names():
            continue  # drop unknown tools
        valid.append(
            {
                "tool": name,
                "args": s.get("args", {}) or {},
                "depends_on": s.get("depends_on", []) or [],
                "status": "pending",
                "result": "",
                "attempts": 0,
                "_idx": i,
            }
        )
    return valid
