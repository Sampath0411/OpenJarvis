"""Owner-aware automations — answer questions about Sampath from the
hardcoded `jarvis.owner` dict. The LLM may still call these to be sure
it gives a complete, accurate answer (vs. relying on the system-prompt
injection, which can be lossy under context compression)."""
from __future__ import annotations

from .. import owner
from .registry import tool


@tool(
    name="who_am_i",
    description=(
        "Return a summary of the user's identity (name, education, laptop, "
        "contact). Use when the user asks 'who am I', 'what do you know about me', "
        "'remind me of my details'."
    ),
)
def who_am_i() -> str:
    p = owner.OWNER
    return (
        f"You're {p['name']} — preferred name *{p['preferred_name']}*.\n"
        f"{p['education']}\n"
        f"Laptop: {p['laptop']}\n"
        f"Email: {p['email']}  |  Phone: {p['phone']}"
    )


@tool(
    name="my_projects",
    description=(
        "List the user's active projects with one-line descriptions. Use when "
        "the user asks 'what am I building', 'list my projects', 'what's "
        "EventFlow', etc."
    ),
)
def my_projects() -> str:
    items = owner.OWNER["active_projects"]
    lines = [f"• *{p['name']}* — {p['desc']}" for p in items]
    return "Your active projects:\n" + "\n".join(lines)


@tool(
    name="my_contacts",
    description=(
        "Return the user's social handles and editing tool. Use when the user "
        "asks for their socials, content handles, or 'what's my Instagram'."
    ),
)
def my_contacts() -> str:
    p = owner.OWNER
    lines = [f"• {k.replace('_', ' ').title()}: {v}"
             for k, v in p["socials"].items()]
    return (
        f"Email: {p['email']}\n"
        f"Phone: {p['phone']}\n"
        f"Editing tool: {p['editing_tool']}\n"
        f"Socials:\n" + "\n".join(lines)
    )
