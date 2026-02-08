"""Command registry for TUI slash commands."""

from collections.abc import Callable


class CommandRegistry:
    """Registry for slash commands.

    Commands are registered with a name (e.g., "/help"), a handler callable,
    and a description. The handler receives the argument string (everything
    after the command name, stripped).
    """

    def __init__(self) -> None:
        self._commands: dict[str, tuple[Callable[[str], object], str, bool]] = {}

    def register(
        self,
        name: str,
        handler: Callable[[str], object],
        description: str,
        *,
        threaded: bool = False,
    ) -> None:
        """Register a slash command."""
        self._commands[name] = (handler, description, threaded)

    def list_commands(self) -> list[tuple[str, str]]:
        """Return list of (name, description) tuples, sorted by name."""
        return sorted((name, desc) for name, (_handler, desc, _threaded) in self._commands.items())

    def resolve(self, text: str) -> tuple[Callable[[str], object], str, bool] | None:
        """Resolve a command string to (handler, args, threaded) without executing."""
        text = text.strip()
        parts = text.split(maxsplit=1)
        if not parts:
            return None
        cmd_name = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        if cmd_name not in self._commands:
            return None
        handler, _desc, threaded = self._commands[cmd_name]
        return handler, args, threaded

    def dispatch(self, text: str) -> bool:
        """Dispatch a command string. Returns True if command was found."""
        result = self.resolve(text)
        if result is None:
            return False
        handler, args, _threaded = result
        handler(args)
        return True

    def is_command(self, text: str) -> bool:
        """Check if text looks like a slash command."""
        return text.strip().startswith("/")

    def completions(self, prefix: str) -> list[tuple[str, str]]:
        """Return matching commands for auto-complete."""
        prefix = prefix.strip()
        return sorted(
            (name, desc)
            for name, (_handler, desc, _threaded) in self._commands.items()
            if name.startswith(prefix)
        )
