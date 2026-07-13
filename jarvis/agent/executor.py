"""Step executor — runs a goal's plan against the live tool registry.

Handles:
- dependency ordering (depends_on)
- retries up to goal.max_retries
- capturing each step's result for dependent steps
- approval-gated tools (pauses if destructive + owner_trust off)
"""
from __future__ import annotations

import time
from typing import Any, Callable

from jarvis.automations.registry import REGISTRY


class Executor:
    def __init__(
        self,
        dispatch: Callable[[str, dict], str],
        requires_approval: Callable[[str], bool],
        approver: Callable[[str, dict], tuple[bool, str]] | None = None,
    ) -> None:
        """
        dispatch(name, args) -> str          : run a tool, return result text
        requires_approval(name) -> bool      : is this tool approval-gated?
        approver(name, args) -> (ok, result) : optional human-in-loop
        """
        self.dispatch = dispatch
        self.requires_approval = requires_approval
        self.approver = approver

    def run(
        self,
        steps: list[dict[str, Any]],
        on_progress: Callable[[int, str, str], None] | None = None,
        max_retries: int = 2,
    ) -> dict[str, Any]:
        """Execute steps in dependency order. Returns run summary."""
        results: dict[int, str] = {}
        order = self._topo_order(steps)
        done = 0
        total = len(steps)
        failed_indices: list[int] = []

        for idx in order:
            step = steps[idx]
            tool = step["tool"]
            args = dict(step.get("args", {}))

            # Inject upstream results where a step needs them
            args = self._inject_deps(args, step, results)

            step["status"] = "running"
            if on_progress:
                on_progress(idx, tool, "running")

            # Approval gate
            if self.requires_approval(tool) and self.approver is not None:
                ok, verdict = self.approver(tool, args)
                if not ok:
                    step["status"] = "skipped"
                    step["result"] = f"denied: {verdict}"
                    failed_indices.append(idx)
                    if on_progress:
                        on_progress(idx, tool, "skipped")
                    continue

            # Retry loop
            attempt = 0
            last_err = ""
            while attempt <= max_retries:
                attempt += 1
                step["attempts"] = attempt
                try:
                    res = self.dispatch(tool, args)
                    step["result"] = str(res)[:500]
                    step["status"] = "done"
                    results[idx] = step["result"]
                    done += 1
                    if on_progress:
                        on_progress(idx, tool, "done")
                    break
                except Exception as exc:  # noqa: BLE001
                    last_err = str(exc)
                    time.sleep(0.5 * attempt)  # backoff
            else:
                step["status"] = "failed"
                step["result"] = f"failed after {max_retries+1} tries: {last_err}"[:500]
                failed_indices.append(idx)
                if on_progress:
                    on_progress(idx, tool, "failed")

        return {
            "done": done,
            "total": total,
            "failed": failed_indices,
            "results": results,
            "success": len(failed_indices) == 0,
        }

    def _topo_order(self, steps: list[dict]) -> list[int]:
        """Return step indices in dependency-satisfied order (Kahn-ish)."""
        n = len(steps)
        indeg = [0] * n
        adj: list[list[int]] = [[] for _ in range(n)]
        for i, s in enumerate(steps):
            for dep in s.get("depends_on", []):
                if isinstance(dep, int) and 0 <= dep < n and dep != i:
                    indeg[i] += 1
                    adj[dep].append(i)
        # BFS layered order
        queue = [i for i in range(n) if indeg[i] == 0]
        order: list[int] = []
        seen = set()
        while queue:
            i = queue.pop(0)
            if i in seen:
                continue
            seen.add(i)
            order.append(i)
            for j in adj[i]:
                indeg[j] -= 1
                if indeg[j] == 0:
                    queue.append(j)
        # append any leftover (cycles → just run in index order)
        for i in range(n):
            if i not in seen:
                order.append(i)
        return order

    def _inject_deps(
        self, args: dict, step: dict, results: dict[int, str]
    ) -> dict:
        """If a step's arg is literally '{step_N.result}', substitute it."""
        deps = step.get("depends_on", [])
        new = dict(args)
        for k, v in args.items():
            if isinstance(v, str) and v.startswith("{step_") and v.endswith(".result}"):
                try:
                    ref = int(v.strip("{}").split(".")[0].split("_")[1])
                    if ref in results:
                        new[k] = results[ref]
                except Exception:
                    pass
        # also let a step reference previous result via special key
        if "_use_prev_result" in new and deps:
            prev = deps[-1]
            if prev in results:
                new["_prev"] = results[prev]
            del new["_use_prev_result"]
        return new
