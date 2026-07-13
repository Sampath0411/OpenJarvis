"""A tiny tool registry.

Each automation is a plain Python function decorated with @tool(...). The decorator
records a JSON schema (OpenAI-compatible shape) plus the callable, so the Brain can
advertise them to the model and dispatch calls by name. The Brain then translates
this schema into Gemini's `function_declarations` format on the way out.

Approval flags:
- requires_approval=True → brain pauses and emits 'approval_required' SSE event before dispatch.
- destructive=True      → UI marks the tool chip red; logged for audit.
"""
from __future__ import annotations

from typing import Any, Callable


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}
        self._disabled: set[str] = set()

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        func: Callable[..., str],
        requires_approval: bool = False,
        destructive: bool = False,
    ) -> None:
        self._tools[name] = {
            "schema": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            },
            "func": func,
            "requires_approval": requires_approval,
            "destructive": destructive,
        }

    def schemas(self) -> list[dict[str, Any]]:
        return [t["schema"] for t in self._tools.values()]

    def names(self) -> list[str]:
        return [n for n in self._tools if n not in self._disabled]

    def disabled(self) -> list[str]:
        return list(self._disabled)

    def set_enabled(self, name: str, enabled: bool) -> None:
        if enabled:
            self._disabled.discard(name)
        else:
            self._disabled.add(name)

    def metadata(self) -> dict[str, dict[str, Any]]:
        """Return {name: {description, requires_approval, destructive}} for the UI."""
        return {
            name: {
                "description": t["schema"]["function"].get("description", ""),
                "requires_approval": t["requires_approval"],
                "destructive": t["destructive"],
            }
            for name, t in self._tools.items()
        }

    def requires_approval(self, name: str) -> bool:
        return bool(self._tools.get(name, {}).get("requires_approval", False))

    def dispatch(self, name: str, args: dict[str, Any]) -> str:
        if name not in self._tools:
            return f"Unknown tool: {name}"
        # Never let a tool raise out of dispatch — a single tool fault (bad
        # kwargs from the model, a NameError, an OS error) would otherwise
        # break the whole turn. Turn it into an error string the model can see
        # and recover from instead.
        try:
            return str(self._tools[name]["func"](**args))
        except TypeError as exc:
            # Almost always the model passed wrong/extra/missing arguments.
            return f"Tool '{name}' called with invalid arguments: {exc}"
        except Exception as exc:  # noqa: BLE001
            return f"Tool '{name}' failed: {exc}"

    def replace_func(self, name: str, func: Callable[..., str]) -> None:
        """Swap a tool's implementation at runtime (used for see_screen binding)."""
        if name in self._tools:
            self._tools[name]["func"] = func


REGISTRY = Registry()


def tool(
    name: str,
    description: str,
    parameters: dict[str, Any] | None = None,
    requires_approval: bool = False,
    destructive: bool = False,
):
    """Decorator: register a function as a callable automation.

    `parameters` is a JSON-Schema object. Default = no arguments.
    `requires_approval` and `destructive` flag tools that need user confirmation.
    """
    schema = parameters or {"type": "object", "properties": {}}

    def decorator(func: Callable[..., str]) -> Callable[..., str]:
        REGISTRY.register(
            name, description, schema, func,
            requires_approval=requires_approval,
            destructive=destructive,
        )
        return func

    return decorator
