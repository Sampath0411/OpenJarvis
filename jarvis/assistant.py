"""Assistant — the interactive loop that wires memory, brain, voice and automations."""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from config import CONFIG
from . import contacts, facts, personas, sessions
from .automations import REGISTRY
from .brain import Brain
from .memory import Memory
from .voice import Voice

console = Console()


def build_system_prompt() -> str:
    return personas.build_system_prompt(
        CONFIG.persona, CONFIG.language, REGISTRY.names(), facts.facts_text()
    )


class Assistant:
    def __init__(self) -> None:
        CONFIG.validate()
        self.memory = Memory(build_system_prompt())
        self.voice = Voice()
        self.brain = Brain(
            memory=self.memory,
            tools_schema=REGISTRY.schemas(),
            dispatch=REGISTRY.dispatch,
            on_tool=self._show_tool,
            registry=REGISTRY,
        )
        # Bind the real see_screen implementation (needs the configured vision models).
        self.brain.bind_see_screen()
        # voice input only if both enabled AND a mic actually initialised
        self.listening = CONFIG.stt_enabled and self.voice.can_listen
        self._base_prompt = self.memory.system_prompt

    # ── UI helpers ───────────────────────────────────
    def _show_tool(self, name: str, args: dict) -> None:
        meta = REGISTRY.metadata().get(name, {})
        marker = " ⚠" if meta.get("requires_approval") else ""
        arg_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
        console.print(
            f"  [dim]⚙ running[/dim] [cyan]{name}[/cyan]([dim]{arg_str}[/dim]){marker}"
        )

    def _say(self, text: str) -> None:
        console.print(Panel(text, title=f"[bold cyan]{CONFIG.name}[/bold cyan]", border_style="cyan"))
        if CONFIG.voice_enabled:
            self.voice.speak(text)

    def _banner(self) -> None:
        mode = "🎙 voice" if self.listening else "⌨ text"
        n_approval = sum(1 for m in REGISTRY.metadata().values() if m.get("requires_approval"))
        console.print(
            Panel.fit(
                f"[bold cyan]{CONFIG.name}[/bold cyan] online — model [green]{CONFIG.model}[/green]\n"
                f"Input mode: {mode}   |   {len(REGISTRY.names())} automations "
                f"({n_approval} require approval)\n"
                "Commands: [yellow]exit[/yellow] quit · [yellow]reset[/yellow] clear memory · "
                "[yellow]text[/yellow]/[yellow]voice[/yellow] switch input\n"
                "          [yellow]/contact add <name> <phone> [alias ...][/yellow] add contact\n"
                "          [yellow]/contacts[/yellow] list contacts",
                border_style="cyan",
            )
        )

    # ── contact command ──────────────────────────────
    def _handle_contact_cmd(self, parts: list[str]) -> bool:
        if not parts or parts[0] != "/contact":
            return False
        if len(parts) < 2:
            console.print("[yellow]Usage: /contact add <name> <phone> [alias ...][/yellow]")
            return True
        if parts[1] == "list":
            items = contacts.list_all()
            if not items:
                console.print("[dim]No contacts saved.[/dim]")
            else:
                for c in items:
                    aliases = ", ".join(c.get("aliases", []))
                    console.print(
                        f"  [cyan]{c['name']}[/cyan] (+{c['phone_e164']}) "
                        f"aliases=[{aliases}]"
                    )
            return True
        if parts[1] == "add":
            if len(parts) < 4:
                console.print("[yellow]Usage: /contact add <name> <phone> [alias ...][/yellow]")
                return True
            name, phone = parts[2], parts[3]
            aliases = parts[4:]
            try:
                c = contacts.add(name, phone, aliases)
            except ValueError as exc:
                console.print(f"[red]{exc}[/red]")
                return True
            console.print(f"[green]Saved[/green] {c['name']} (+{c['phone_e164']})")
            return True
        if parts[1] in ("remove", "rm", "delete"):
            if len(parts) < 3:
                console.print("[yellow]Usage: /contact remove <name>[/yellow]")
                return True
            n = contacts.remove(" ".join(parts[2:]))
            console.print(f"[green]Removed {n} contact(s).[/green]" if n else "[dim]No match.[/dim]")
            return True
        console.print(f"[yellow]Unknown /contact subcommand: {parts[1]}[/yellow]")
        return True

    # ── input ────────────────────────────────────────
    def _get_input(self) -> str | None:
        if self.listening:
            console.print("[dim]🎙 listening…[/dim]", end="\r")
            heard = self.voice.listen()
            if heard:
                console.print(f"[bold white]You:[/bold white] {heard}          ")
                return heard
            console.print("[dim](didn't catch that — type instead, or press Enter to retry)[/dim]")
            typed = console.input("[bold white]You:[/bold white] ").strip()
            return typed or None
        return console.input("[bold white]You:[/bold white] ").strip() or None

    # ── main loop ────────────────────────────────────
    def run(self) -> None:
        self.memory.load()
        self._banner()
        self._say(f"Hello Sampath. {CONFIG.name} is ready. How can I help?")

        while True:
            try:
                user = self._get_input()
            except (KeyboardInterrupt, EOFError):
                break
            if not user:
                continue

            low = user.lower().strip()
            if low in ("exit", "quit", "bye", "goodbye", "shutdown"):
                break
            if low == "reset":
                self._summarize_session()
                self.memory.reset()
                console.print("[yellow]Memory cleared.[/yellow]")
                continue
            if low == "text":
                self.listening = False
                console.print("[yellow]Switched to text input.[/yellow]")
                continue
            if low == "voice":
                if self.voice.can_listen:
                    self.listening = True
                    console.print("[yellow]Switched to voice input.[/yellow]")
                else:
                    console.print("[red]No microphone available.[/red]")
                continue
            if low in ("/contacts",):
                for c in contacts.list_all():
                    aliases = ", ".join(c.get("aliases", []))
                    console.print(f"  [cyan]{c['name']}[/cyan] (+{c['phone_e164']}) aliases=[{aliases}]")
                continue

            # /contact ... commands
            parts = user.split()
            if parts and parts[0] == "/contact":
                self._handle_contact_cmd(parts)
                continue

            # Add user message with potential recall injection
            self.memory.add_with_recall("user", user, self._base_prompt)

            try:
                reply = self.brain.ask(user)
            except Exception as exc:  # noqa: BLE001
                reply = f"Something went wrong talking to the model: {exc}"
            self._say(reply)

        self._summarize_session()
        self.memory.save()
        self._say("Goodbye. Shutting down.")

    def _summarize_session(self) -> None:
        """If the conversation has enough content, store a one-paragraph summary."""
        # Use the in-memory messages (excluding the system prompt).
        msgs = [m for m in self.memory.messages if m.get("role") in ("user", "assistant")]
        # Filter to messages with actual content.
        msgs = [m for m in msgs if m.get("content")]
        if len(msgs) < 4:
            return
        try:
            summary = self.brain.summarize_session(msgs[-30:])
            if summary:
                sessions.add_summary(summary)
        except Exception:  # noqa: BLE001
            pass
