"""Reflection — after a goal runs, decide: success / retry / replan / abort.

Cheap heuristic (no LLM needed for the common cases) + optional
LLM-assisted verdict when the result is ambiguous.
"""
from __future__ import annotations

from typing import Any


def evaluate(
    summary: dict[str, Any],
    goal_title: str,
    brain=None,
) -> dict[str, Any]:
    """
    summary = executor.run() output: {done, total, failed[], success, results{}}
    Returns: {verdict: 'success'|'retry'|'replan'|'abort', reason: str}
    """
    done = summary.get("done", 0)
    total = summary.get("total", 0)
    failed = summary.get("failed", [])

    if total == 0:
        return {"verdict": "replan", "reason": "no steps were planned"}

    if summary.get("success"):
        return {"verdict": "success", "reason": f"{done}/{total} steps completed"}

    # Partial / full failure
    if not failed:
        return {"verdict": "success", "reason": f"{done}/{total} steps completed"}

    if len(failed) == total:
        # everything failed
        if brain is not None:
            return _llm_verdict(brain, goal_title, summary)
        return {
            "verdict": "abort",
            "reason": f"all {total} steps failed; no LLM to recover",
        }

    # some failed, some ok → retry the failed ones
    if brain is not None:
        v = _llm_verdict(brain, goal_title, summary)
        if v["verdict"] in ("retry", "replan", "abort"):
            return v
    return {
        "verdict": "retry",
        "reason": f"{len(failed)}/{total} steps failed; retrying them",
    }


def _llm_verdict(brain, goal_title: str, summary: dict) -> dict[str, Any]:
    """Ask the brain whether to retry / replan / abort."""
    prompt = (
        "You are JARVIS reflection. A goal ran with partial failure.\n"
        f"GOAL: {goal_title}\n"
        f"STEPS DONE: {summary.get('done')}/{summary.get('total')}\n"
        f"FAILED STEPS: {summary.get('failed')}\n"
        "Decide ONE: retry (run failed steps again), replan (goal needs "
        "different steps), or abort (not achievable).\n"
        'Respond ONLY JSON: {"verdict": "...", "reason": "..."}'
    )
    try:
        raw = brain.complete(prompt, max_tokens=200)
        import json
        import re
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            d = json.loads(m.group(0))
            v = d.get("verdict")
            if v in ("retry", "replan", "abort", "success"):
                return {"verdict": v, "reason": d.get("reason", "")}
    except Exception:
        pass
    return {"verdict": "retry", "reason": "LLM verdict unavailable; defaulting to retry"}


def should_retry(verdict: str) -> bool:
    return verdict in ("retry", "replan")
