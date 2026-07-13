"""Agent orchestrator — ties planner → executor → reflection into a run loop.

This is the entry point the scheduler, HUD, Telegram, and CLI all call:
    from jarvis.agent import Agent
    Agent().run_goal(goal_id)
"""
from __future__ import annotations

import time
from typing import Any, Callable

from . import executor as _exec
from . import planner as _planner
from . import reflection as _reflection
from . import goals as _goals


class Agent:
    def __init__(
        self,
        brain=None,
        dispatch: Callable[[str, dict], str] | None = None,
        requires_approval: Callable[[str], bool] | None = None,
        approver: Callable[[str, dict], tuple[bool, str]] | None = None,
        on_progress: Callable | None = None,
        on_report: Callable[[str], None] | None = None,
    ) -> None:
        self.brain = brain
        self.dispatch = dispatch or self._default_dispatch
        self.requires_approval = requires_approval or (lambda _n: False)
        self.approver = approver
        self.on_progress = on_progress
        self.on_report = on_report

        self.executor = _exec.Executor(
            dispatch=self.dispatch,
            requires_approval=self.requires_approval,
            approver=self.approver,
        )

    # ---- default dispatch (used if none injected) ----
    def _default_dispatch(self, name: str, args: dict) -> str:
        from jarvis.automations.registry import REGISTRY
        return REGISTRY.dispatch(name, args)

    # ---- main entry ----
    def run_goal(self, goal_id: str) -> dict[str, Any]:
        goal = _goals.get(goal_id)
        if not goal:
            return {"ok": False, "error": "goal_not_found"}

        _goals.set_status(goal_id, "running")
        start = time.time()

        # 1. Plan (if not already planned)
        steps = goal.get("steps") or []
        if not steps:
            steps = _planner.plan(goal["title"], brain=self.brain)
            _goals.set_steps(goal_id, steps)
            goal = _goals.get(goal_id) or goal
            steps = goal.get("steps") or steps

        if not steps:
            _goals.set_status(goal_id, "failed")
            _goals.log_run(goal_id, "failed", "planner produced no steps", 0, 0, 0)
            self._report(goal, "❌ Failed", "planner produced no steps")
            return {"ok": False, "error": "no_plan"}

        # 2. Execute
        def _prog(idx, tool, status):
            if self.on_progress:
                self.on_progress(goal_id, idx, tool, status)

        summary = self.executor.run(
            steps,
            on_progress=_prog,
            max_retries=goal.get("max_retries", 2),
        )

        # 3. Reflect
        verdict = _reflection.evaluate(summary, goal["title"], brain=self.brain)

        elapsed = time.time() - start
        status_emoji = "✅" if verdict["verdict"] == "success" else "❌"

        if verdict["verdict"] == "success":
            _goals.set_status(goal_id, "done")
            _goals.log_run(
                goal_id, "done", verdict["reason"],
                summary["done"], summary["total"], elapsed,
            )
            self._report(
                goal, f"{status_emoji} Done",
                f"{summary['done']}/{summary['total']} steps · {elapsed:.0f}s",
            )
            return {"ok": True, "verdict": "success", "summary": summary}

        if verdict["verdict"] in ("retry", "replan") and goal.get("retries_left", goal.get("max_retries", 2)) > 0:
            # retry: reset all steps to pending so failed ones re-run
            remaining = steps[:]  # keep all steps
            for s in remaining:
                if s.get("status") in ("failed", "running"):
                    s["status"] = "pending"
                    s.pop("result", None)
                    s.pop("attempts", None)
            _goals.set_steps(goal_id, remaining if remaining else [])
            _goals.update(goal_id, retries_left=goal.get("retries_left", goal.get("max_retries", 2)) - 1)
            _goals.set_status(goal_id, "pending")
            _goals.log_run(
                goal_id, "retry", verdict["reason"],
                summary["done"], summary["total"], elapsed,
            )
            self._report(
                goal, "🔁 Retrying",
                f"{summary['done']}/{summary['total']} ok · {verdict['reason']}",
            )
            return {"ok": True, "verdict": "retry", "summary": summary}

        # abort
        _goals.set_status(goal_id, "failed")
        _goals.log_run(
            goal_id, "failed", verdict["reason"],
            summary["done"], summary["total"], elapsed,
        )
        self._report(goal, f"{status_emoji} Failed", verdict["reason"])
        return {"ok": False, "verdict": "abort", "summary": summary}

    def _report(self, goal: dict, headline: str, detail: str) -> None:
        if self.on_report:
            msg = (
                f"🤖 {headline}\n"
                f"  Goal: {goal['title']}\n"
                f"  {detail}"
            )
            self.on_report(msg)


# Convenience wrappers used by CLI / Telegram / HUD
def create_and_run(title: str, cron: str | None = None, brain=None) -> dict:
    goal = _goals.create(title, cron=cron)
    agent = Agent(brain=brain)
    return agent.run_goal(goal["id"])
