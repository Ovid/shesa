"""Tests for TUI command registry."""

from shesha.tui.commands import CommandRegistry


class TestCommandRegistry:
    """Tests for CommandRegistry."""

    def test_register_and_list(self) -> None:
        """Registered commands appear in list."""
        registry = CommandRegistry()
        registry.register("/help", lambda _: None, "Show help")
        commands = registry.list_commands()
        assert len(commands) == 1
        assert commands[0] == ("/help", "Show help")

    def test_dispatch_calls_handler(self) -> None:
        """Dispatch calls the correct handler."""
        called_with: list[str] = []
        registry = CommandRegistry()
        registry.register("/echo", lambda args: called_with.append(args), "Echo args")
        registry.dispatch("/echo hello world")
        assert called_with == ["hello world"]

    def test_dispatch_no_args(self) -> None:
        """Dispatch with no args passes empty string."""
        called_with: list[str] = []
        registry = CommandRegistry()
        registry.register("/help", lambda args: called_with.append(args), "Help")
        registry.dispatch("/help")
        assert called_with == [""]

    def test_dispatch_unknown_command_returns_false(self) -> None:
        """Dispatch returns False for unknown commands."""
        registry = CommandRegistry()
        result = registry.dispatch("/unknown")
        assert result is False

    def test_dispatch_known_command_returns_true(self) -> None:
        """Dispatch returns True for known commands."""
        registry = CommandRegistry()
        registry.register("/help", lambda args: None, "Help")
        result = registry.dispatch("/help")
        assert result is True

    def test_is_command_with_slash(self) -> None:
        """Strings starting with / are commands."""
        registry = CommandRegistry()
        assert registry.is_command("/help") is True

    def test_is_command_without_slash(self) -> None:
        """Regular text is not a command."""
        registry = CommandRegistry()
        assert registry.is_command("hello") is False

    def test_is_command_with_leading_whitespace(self) -> None:
        """Leading whitespace before / is still a command."""
        registry = CommandRegistry()
        assert registry.is_command("  /help") is True

    def test_completions_empty_prefix(self) -> None:
        """Completions with just / returns all commands."""
        registry = CommandRegistry()
        registry.register("/help", lambda _: None, "Help")
        registry.register("/write", lambda _: None, "Write")
        completions = registry.completions("/")
        assert set(completions) == {("/help", "Help"), ("/write", "Write")}

    def test_completions_partial_prefix(self) -> None:
        """Completions filters by prefix."""
        registry = CommandRegistry()
        registry.register("/help", lambda _: None, "Help")
        registry.register("/write", lambda _: None, "Write")
        completions = registry.completions("/he")
        assert completions == [("/help", "Help")]

    def test_dispatch_strips_leading_whitespace(self) -> None:
        """Dispatch handles leading whitespace before /."""
        called: list[bool] = []
        registry = CommandRegistry()
        registry.register("/help", lambda args: called.append(True), "Help")
        result = registry.dispatch("  /help")
        assert result is True
        assert called == [True]
