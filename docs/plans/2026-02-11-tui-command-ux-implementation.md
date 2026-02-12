# TUI Command UX Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure arXiv Explorer TUI commands into git-style subcommands under `/topic`, improve discoverability with two-level autocomplete and better help output, and fix the completion popup truncation.

**Architecture:** Extend `CommandRegistry` with command group support (`register_group`/`register_subcommand`). Update the `SheshaTUI` completion logic to show subcommand completions after a group name + space. Restructure `arxiv_explorer.py` to use the new group API.

**Tech Stack:** Python 3.12+, Textual TUI framework, pytest with async tests

**Worktree:** `.worktrees/tui-command-ux` on branch `ovid/tui-command-ux`

**Important files:**
- `src/shesha/tui/commands.py` — CommandRegistry (66 lines)
- `src/shesha/tui/app.py` — SheshaTUI app (580 lines)
- `src/shesha/tui/widgets/completion_popup.py` — CompletionPopup (80 lines)
- `examples/arxiv_explorer.py` — arXiv explorer app (611 lines)
- `tests/examples/test_arxiv_tui.py` — TUI tests (743 lines)
- `tests/examples/test_arxiv.py` — CLI tests (166 lines, no changes needed)

**Pre-existing test failure:** `tests/unit/rlm/test_engine_pool_error_handling.py::TestDeadExecutorRecovery::test_fresh_executor_gets_llm_query_handler` — unrelated to this work (randomized boundary feature), ignore it.

---

## Task 1: Add command group registration to CommandRegistry

Add `register_group()` and `register_subcommand()` methods. A group is a command name (e.g., `/topic`) that has subcommands. When resolved without a subcommand, it returns a help handler. When resolved with a subcommand (e.g., `/topic switch foo`), it dispatches to the subcommand handler with remaining args.

**Files:**
- Test: `tests/unit/tui/test_commands.py` (create)
- Modify: `src/shesha/tui/commands.py`
- Create: `tests/unit/tui/__init__.py`

### Step 1: Create test directory and write failing tests

Create `tests/unit/tui/__init__.py` (empty) and `tests/unit/tui/test_commands.py` with these tests:

```python
"""Tests for CommandRegistry command group support."""

from shesha.tui.commands import CommandRegistry


class TestCommandGroupRegistration:
    """Tests for register_group and register_subcommand."""

    def test_register_group_appears_in_list_commands(self) -> None:
        """A registered group shows in list_commands with its description."""
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        commands = reg.list_commands()
        assert ("/topic", "Topic management") in commands

    def test_register_subcommand(self) -> None:
        """A subcommand can be registered under a group."""
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        called_with: list[str] = []
        reg.register_subcommand("/topic", "list", lambda args: called_with.append(args), "List all topics")
        # Subcommands should NOT appear in top-level list_commands
        names = [name for name, _ in reg.list_commands()]
        assert "/topic list" not in names

    def test_resolve_subcommand(self) -> None:
        """Resolving '/topic switch foo' returns the switch handler with args 'foo'."""
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        called_with: list[str] = []
        reg.register_subcommand("/topic", "switch", lambda args: called_with.append(args), "Switch topic")
        result = reg.resolve("/topic switch my-topic")
        assert result is not None
        handler, args, threaded = result
        handler(args)
        assert called_with == ["my-topic"]

    def test_resolve_subcommand_no_args(self) -> None:
        """Resolving '/topic list' with no extra args passes empty string."""
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        called_with: list[str] = []
        reg.register_subcommand("/topic", "list", lambda args: called_with.append(args), "List topics")
        result = reg.resolve("/topic list")
        assert result is not None
        handler, args, threaded = result
        handler(args)
        assert called_with == [""]

    def test_resolve_bare_group_returns_help_handler(self) -> None:
        """Resolving '/topic' (no subcommand) returns the group help handler."""
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        reg.register_subcommand("/topic", "list", lambda args: None, "List all topics")
        result = reg.resolve("/topic")
        assert result is not None
        handler, args, threaded = result
        # Bare group handler is auto-generated; args should be empty
        assert args == ""

    def test_resolve_unknown_subcommand_returns_help_handler(self) -> None:
        """Resolving '/topic bogus' returns the group help handler with original args."""
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        reg.register_subcommand("/topic", "list", lambda args: None, "List topics")
        result = reg.resolve("/topic bogus")
        assert result is not None
        handler, args, threaded = result
        # Falls back to group help handler, passing original args through
        assert args == "bogus"

    def test_subcommand_threaded_flag(self) -> None:
        """Subcommands can be registered as threaded."""
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        reg.register_subcommand("/topic", "add", lambda args: None, "Add papers", threaded=True)
        result = reg.resolve("/topic add 1 2 3")
        assert result is not None
        _handler, _args, threaded = result
        assert threaded is True

    def test_list_subcommands(self) -> None:
        """list_subcommands returns sorted subcommand (name, desc) tuples."""
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        reg.register_subcommand("/topic", "switch", lambda a: None, "Switch topic")
        reg.register_subcommand("/topic", "add", lambda a: None, "Add papers")
        reg.register_subcommand("/topic", "list", lambda a: None, "List topics")
        subs = reg.list_subcommands("/topic")
        names = [name for name, _ in subs]
        assert names == ["add", "list", "switch"]

    def test_list_subcommands_unknown_group(self) -> None:
        """list_subcommands returns empty list for unknown group."""
        reg = CommandRegistry()
        assert reg.list_subcommands("/bogus") == []


class TestCommandGroupCompletions:
    """Tests for two-level autocomplete with command groups."""

    def test_completions_top_level_includes_groups(self) -> None:
        """Typing '/' shows groups alongside regular commands."""
        reg = CommandRegistry()
        reg.register("/help", lambda a: None, "Show help")
        reg.register_group("/topic", "Topic management")
        completions = reg.completions("/")
        names = [name for name, _ in completions]
        assert "/help" in names
        assert "/topic" in names

    def test_completions_group_prefix_filters(self) -> None:
        """Typing '/to' narrows to '/topic'."""
        reg = CommandRegistry()
        reg.register("/help", lambda a: None, "Show help")
        reg.register_group("/topic", "Topic management")
        completions = reg.completions("/to")
        assert len(completions) == 1
        assert completions[0][0] == "/topic"

    def test_subcommand_completions(self) -> None:
        """subcommand_completions returns matching subcommands."""
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        reg.register_subcommand("/topic", "list", lambda a: None, "List topics")
        reg.register_subcommand("/topic", "switch", lambda a: None, "Switch topic")
        reg.register_subcommand("/topic", "create", lambda a: None, "Create topic")
        # All subcommands
        subs = reg.subcommand_completions("/topic", "")
        assert len(subs) == 3
        # Filtered
        subs = reg.subcommand_completions("/topic", "sw")
        assert len(subs) == 1
        assert subs[0][0] == "switch"

    def test_subcommand_completions_unknown_group(self) -> None:
        """subcommand_completions returns empty for unknown group."""
        reg = CommandRegistry()
        assert reg.subcommand_completions("/bogus", "") == []

    def test_is_group(self) -> None:
        """is_group returns True for registered groups, False otherwise."""
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        reg.register("/help", lambda a: None, "Help")
        assert reg.is_group("/topic") is True
        assert reg.is_group("/help") is False
        assert reg.is_group("/bogus") is False
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/unit/tui/test_commands.py -v`
Expected: FAIL — `register_group`, `register_subcommand`, `subcommand_completions`, `is_group`, `list_subcommands` don't exist yet.

### Step 3: Implement command group support

Modify `src/shesha/tui/commands.py`. The new state is:

```python
"""Command registry for TUI slash commands."""

from collections.abc import Callable


class CommandRegistry:
    """Registry for slash commands with optional command groups.

    Commands are registered with a name (e.g., "/help"), a handler callable,
    and a description. The handler receives the argument string (everything
    after the command name, stripped).

    Command groups (e.g., "/topic") have subcommands (e.g., "list", "switch").
    When a group is invoked without a subcommand, the group's help handler runs.
    When invoked with an unknown subcommand, the help handler also runs.
    """

    def __init__(self) -> None:
        self._commands: dict[str, tuple[Callable[[str], object], str, bool]] = {}
        # Groups: group_name -> (description, help_handler, subcommands_dict)
        # subcommands_dict: subcommand_name -> (handler, description, threaded)
        self._groups: dict[str, tuple[str, Callable[[str], object], dict[str, tuple[Callable[[str], object], str, bool]]]] = {}

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

    def register_group(self, name: str, description: str) -> None:
        """Register a command group (e.g., '/topic').

        The group gets an auto-generated help handler that lists subcommands.
        """
        subcommands: dict[str, tuple[Callable[[str], object], str, bool]] = {}

        def help_handler(args: str) -> None:
            # This is a placeholder; the actual display is done by the caller
            # who reads list_subcommands(). We store it so resolve() can return it.
            pass

        self._groups[name] = (description, help_handler, subcommands)

    def set_group_help_handler(self, name: str, handler: Callable[[str], object]) -> None:
        """Set a custom help handler for a group (replaces auto-generated one)."""
        if name not in self._groups:
            return
        desc, _old_handler, subcommands = self._groups[name]
        self._groups[name] = (desc, handler, subcommands)

    def register_subcommand(
        self,
        group: str,
        subcommand: str,
        handler: Callable[[str], object],
        description: str,
        *,
        threaded: bool = False,
    ) -> None:
        """Register a subcommand under a group."""
        if group not in self._groups:
            raise ValueError(f"Unknown group: {group}")
        _desc, _help, subcommands = self._groups[group]
        subcommands[subcommand] = (handler, description, threaded)

    def list_commands(self) -> list[tuple[str, str]]:
        """Return list of (name, description) tuples, sorted by name.

        Groups appear as top-level entries; individual subcommands do not.
        """
        items: list[tuple[str, str]] = []
        for name, (_handler, desc, _threaded) in self._commands.items():
            items.append((name, desc))
        for name, (desc, _help, _subs) in self._groups.items():
            items.append((name, desc))
        return sorted(items)

    def list_subcommands(self, group: str) -> list[tuple[str, str]]:
        """Return sorted (subcommand_name, description) tuples for a group."""
        if group not in self._groups:
            return []
        _desc, _help, subcommands = self._groups[group]
        return sorted((name, desc) for name, (_handler, desc, _threaded) in subcommands.items())

    def is_group(self, name: str) -> bool:
        """Check if name is a registered command group."""
        return name in self._groups

    def resolve(self, text: str) -> tuple[Callable[[str], object], str, bool] | None:
        """Resolve a command string to (handler, args, threaded) without executing.

        For groups: '/topic switch foo' resolves to (switch_handler, 'foo', threaded).
        For bare groups: '/topic' resolves to (help_handler, '', False).
        For unknown subcommands: '/topic bogus' resolves to (help_handler, 'bogus', False).
        """
        text = text.strip()
        parts = text.split(maxsplit=1)
        if not parts:
            return None
        cmd_name = parts[0]
        args = parts[1] if len(parts) > 1 else ""

        # Check groups first
        if cmd_name in self._groups:
            _desc, help_handler, subcommands = self._groups[cmd_name]
            if not args:
                return help_handler, "", False
            sub_parts = args.split(maxsplit=1)
            sub_name = sub_parts[0]
            sub_args = sub_parts[1] if len(sub_parts) > 1 else ""
            if sub_name in subcommands:
                handler, _sub_desc, threaded = subcommands[sub_name]
                return handler, sub_args, threaded
            # Unknown subcommand — return help handler with original args
            return help_handler, args, False

        # Check regular commands
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
        """Return matching commands for auto-complete (top-level only)."""
        prefix = prefix.strip()
        items: list[tuple[str, str]] = []
        for name, (_handler, desc, _threaded) in self._commands.items():
            if name.startswith(prefix):
                items.append((name, desc))
        for name, (desc, _help, _subs) in self._groups.items():
            if name.startswith(prefix):
                items.append((name, desc))
        return sorted(items)

    def subcommand_completions(self, group: str, prefix: str) -> list[tuple[str, str]]:
        """Return matching subcommands for a group, filtered by prefix."""
        if group not in self._groups:
            return []
        _desc, _help, subcommands = self._groups[group]
        return sorted(
            (name, desc)
            for name, (_handler, desc, _threaded) in subcommands.items()
            if name.startswith(prefix)
        )
```

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/unit/tui/test_commands.py -v`
Expected: All PASS.

### Step 5: Commit

```bash
git add tests/unit/tui/__init__.py tests/unit/tui/test_commands.py src/shesha/tui/commands.py
git commit -m "feat: add command group support to CommandRegistry"
```

---

## Task 2: Fix CompletionPopup truncation

The CompletionPopup has `max-height: 8` in CSS. With 12+ commands, items get clipped. Increase the max-height so all commands are visible.

**Files:**
- Test: `tests/unit/tui/test_commands.py` (add test)
- Modify: `src/shesha/tui/widgets/completion_popup.py`

### Step 1: Write failing test

Add to `tests/unit/tui/test_commands.py`:

```python
class TestCompletionPopupHeight:
    """Tests for CompletionPopup displaying all items."""

    async def test_popup_max_height_fits_all_commands(self) -> None:
        """CompletionPopup max-height should accommodate at least 15 items."""
        from shesha.tui.widgets.completion_popup import CompletionPopup

        popup = CompletionPopup()
        # Check CSS allows enough height -- max-height should be >= 15
        css = popup.DEFAULT_CSS
        import re
        match = re.search(r"max-height:\s*(\d+)", css)
        assert match is not None
        max_height = int(match.group(1))
        assert max_height >= 15, f"max-height {max_height} too small for 15+ commands"
```

### Step 2: Run test to verify it fails

Run: `python -m pytest tests/unit/tui/test_commands.py::TestCompletionPopupHeight -v`
Expected: FAIL — current max-height is 8.

### Step 3: Fix the CSS

In `src/shesha/tui/widgets/completion_popup.py`, change `max-height: 8` to `max-height: 20`:

```python
    DEFAULT_CSS = """
    CompletionPopup {
        height: auto;
        max-height: 20;
        display: none;
        border: solid $accent;
        padding: 0 1;
    }
    """
```

### Step 4: Run test to verify it passes

Run: `python -m pytest tests/unit/tui/test_commands.py::TestCompletionPopupHeight -v`
Expected: PASS.

### Step 5: Commit

```bash
git add src/shesha/tui/widgets/completion_popup.py tests/unit/tui/test_commands.py
git commit -m "fix: increase CompletionPopup max-height to show all commands"
```

---

## Task 3: Add two-level autocomplete to SheshaTUI

Modify `on_text_area_changed` in `src/shesha/tui/app.py` to show subcommand completions when the user types a group name followed by a space (e.g., `/topic `). Also update `on_input_area_completion_accept` to fill in the group + subcommand properly.

**Files:**
- Test: `tests/unit/tui/test_commands.py` (add tests)
- Modify: `src/shesha/tui/app.py`

### Step 1: Write failing tests

Add to `tests/unit/tui/test_commands.py`:

```python
from unittest.mock import MagicMock, patch


class TestTwoLevelAutocomplete:
    """Tests for two-level autocomplete in SheshaTUI."""

    async def test_group_space_shows_subcommand_completions(self) -> None:
        """Typing '/topic ' shows subcommand completions."""
        from shesha.tui import SheshaTUI
        from shesha.tui.widgets.completion_popup import CompletionPopup
        from shesha.tui.widgets.input_area import InputArea

        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        app._command_registry.register_group("/topic", "Topic management")
        app._command_registry.register_subcommand("/topic", "list", lambda a: None, "List topics")
        app._command_registry.register_subcommand("/topic", "switch", lambda a: None, "Switch topic")

        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "/topic "
            await pilot.pause()
            popup = pilot.app.query_one(CompletionPopup)
            assert popup.display is True
            rendered = str(popup.render())
            assert "list" in rendered
            assert "switch" in rendered

    async def test_group_space_prefix_filters_subcommands(self) -> None:
        """Typing '/topic sw' narrows to 'switch'."""
        from shesha.tui import SheshaTUI
        from shesha.tui.widgets.completion_popup import CompletionPopup
        from shesha.tui.widgets.input_area import InputArea

        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        app._command_registry.register_group("/topic", "Topic management")
        app._command_registry.register_subcommand("/topic", "list", lambda a: None, "List topics")
        app._command_registry.register_subcommand("/topic", "switch", lambda a: None, "Switch topic")

        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "/topic sw"
            await pilot.pause()
            popup = pilot.app.query_one(CompletionPopup)
            assert popup.display is True
            rendered = str(popup.render())
            assert "switch" in rendered
            assert "list" not in rendered

    async def test_subcommand_accept_fills_group_and_subcommand(self) -> None:
        """Accepting a subcommand completion fills '/topic switch '."""
        from shesha.tui import SheshaTUI
        from shesha.tui.widgets.completion_popup import CompletionPopup
        from shesha.tui.widgets.input_area import InputArea

        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        app._command_registry.register_group("/topic", "Topic management")
        app._command_registry.register_subcommand("/topic", "list", lambda a: None, "List topics")
        app._command_registry.register_subcommand("/topic", "switch", lambda a: None, "Switch topic")

        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "/topic "
            await pilot.pause()
            # Select "switch" (second item alphabetically after "list")
            popup = pilot.app.query_one(CompletionPopup)
            popup.select_next()  # Move from "list" to "switch"
            # Accept completion
            input_area.post_message(InputArea.CompletionAccept())
            await pilot.pause()
            assert input_area.text == "/topic switch "

    async def test_non_group_space_hides_popup(self) -> None:
        """Typing '/help ' (not a group) hides the popup."""
        from shesha.tui import SheshaTUI
        from shesha.tui.widgets.completion_popup import CompletionPopup
        from shesha.tui.widgets.input_area import InputArea

        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")

        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "/help "
            await pilot.pause()
            popup = pilot.app.query_one(CompletionPopup)
            assert popup.display is False
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/unit/tui/test_commands.py::TestTwoLevelAutocomplete -v`
Expected: FAIL — current logic hides popup when space is present.

### Step 3: Implement two-level autocomplete

Modify `src/shesha/tui/app.py`:

**a) `on_text_area_changed` (around line 165):** Replace the current method:

```python
    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Update completion popup when input text changes."""
        raw_text = self.query_one(InputArea).text
        text = raw_text.strip()

        if not text.startswith("/"):
            self._hide_completions()
            return

        # Two-level: check for group + subcommand completion
        if " " in raw_text:
            parts = text.split(maxsplit=1)
            group_name = parts[0]
            sub_prefix = parts[1] if len(parts) > 1 else ""
            if self._command_registry.is_group(group_name):
                matches = self._command_registry.subcommand_completions(group_name, sub_prefix)
                if matches:
                    self.query_one(CompletionPopup).show_items(matches)
                    self.query_one(InputArea).completion_active = True
                    self._completing_group = group_name
                    return
            self._hide_completions()
            return

        # Top-level: bare slash-prefixed token with no spaces
        matches = self._command_registry.completions(text)
        if matches:
            self.query_one(CompletionPopup).show_items(matches)
            self.query_one(InputArea).completion_active = True
            self._completing_group = None
            return
        self._hide_completions()
```

**b) Add `_completing_group` attribute** in `__init__` (around line 96, after `self._command_registry`):

```python
        self._completing_group: str | None = None  # Tracks active group for subcommand completion
```

**c) `on_input_area_completion_accept` (around line 186):** Update to handle subcommand completions:

```python
    def on_input_area_completion_accept(self, event: InputArea.CompletionAccept) -> None:
        """Handle completion acceptance."""
        value = self.query_one(CompletionPopup).selected_value
        group = self._completing_group
        self._hide_completions()
        if value:
            input_area = self.query_one(InputArea)
            if group is not None:
                filled = f"{group} {value} "
            else:
                filled = value + " "
            input_area.text = filled
            input_area.move_cursor((0, len(filled)))
```

**d) `_hide_completions`:** Reset `_completing_group`:

```python
    def _hide_completions(self) -> None:
        """Hide the completion popup and deactivate completion mode."""
        self.query_one(CompletionPopup).hide()
        self.query_one(InputArea).completion_active = False
        self._completing_group = None
```

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/unit/tui/test_commands.py -v`
Expected: All PASS.

### Step 5: Commit

```bash
git add src/shesha/tui/app.py tests/unit/tui/test_commands.py
git commit -m "feat: add two-level autocomplete for command groups"
```

---

## Task 4: Improve /help output with argument hints

Update the `/help` command to show usage hints (argument placeholders) for each command, and show groups with a "type /group for details" hint.

**Files:**
- Test: `tests/unit/tui/test_commands.py` (add test)
- Modify: `src/shesha/tui/commands.py` (add `usage` parameter)
- Modify: `src/shesha/tui/app.py` (`_cmd_help`, `_register_builtin_commands`)

### Step 1: Write failing tests

Add to `tests/unit/tui/test_commands.py`:

```python
class TestCommandUsageHints:
    """Tests for usage hints in command registration."""

    def test_register_with_usage(self) -> None:
        """Commands can be registered with a usage string."""
        reg = CommandRegistry()
        reg.register("/search", lambda a: None, "Search arXiv", usage="<query> [--author, ...]")
        commands = reg.list_commands()
        assert ("/search", "Search arXiv") in commands

    def test_list_commands_with_usage(self) -> None:
        """list_commands_with_usage returns (name, usage, description) tuples."""
        reg = CommandRegistry()
        reg.register("/search", lambda a: None, "Search arXiv", usage="<query> [--author, ...]")
        reg.register("/quit", lambda a: None, "Exit")
        reg.register_group("/topic", "Topic management")
        result = reg.list_commands_with_usage()
        # Should include usage hints where available
        search_entry = next(e for e in result if e[0] == "/search")
        assert search_entry == ("/search", "<query> [--author, ...]", "Search arXiv")
        quit_entry = next(e for e in result if e[0] == "/quit")
        assert quit_entry == ("/quit", "", "Exit")
        topic_entry = next(e for e in result if e[0] == "/topic")
        assert topic_entry == ("/topic", "<subcommand>", "Topic management")
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/unit/tui/test_commands.py::TestCommandUsageHints -v`
Expected: FAIL — `usage` parameter and `list_commands_with_usage` don't exist.

### Step 3: Implement usage hints

**a) `src/shesha/tui/commands.py`:** Update `register()` to accept optional `usage` parameter. Add `list_commands_with_usage()`.

Change `_commands` type to store usage:
```python
        self._commands: dict[str, tuple[Callable[[str], object], str, bool, str]] = {}
```

Update `register()`:
```python
    def register(
        self,
        name: str,
        handler: Callable[[str], object],
        description: str,
        *,
        threaded: bool = False,
        usage: str = "",
    ) -> None:
        """Register a slash command."""
        self._commands[name] = (handler, description, threaded, usage)
```

Update all methods that unpack `_commands` to handle the 4th element:
- `list_commands`: `for name, (_handler, desc, _threaded, _usage) in ...`
- `resolve`: `handler, _desc, threaded, _usage = self._commands[cmd_name]`
- `completions`: `for name, (_handler, desc, _threaded, _usage) in ...`

Add:
```python
    def list_commands_with_usage(self) -> list[tuple[str, str, str]]:
        """Return (name, usage, description) tuples for all top-level commands/groups."""
        items: list[tuple[str, str, str]] = []
        for name, (_handler, desc, _threaded, usage) in self._commands.items():
            items.append((name, usage, desc))
        for name, (desc, _help, _subs) in self._groups.items():
            items.append((name, "<subcommand>", desc))
        return sorted(items)
```

**b) `src/shesha/tui/app.py`:** Update `_cmd_help` to use `list_commands_with_usage`:

```python
    def _cmd_help(self, args: str) -> None:
        """Show help."""
        lines = ["Available commands:"]
        for name, usage, desc in self._command_registry.list_commands_with_usage():
            if usage:
                label = f"{name} {usage}"
            else:
                label = name
            lines.append(f"  {label:36s} {desc}")
        self.query_one(OutputArea).add_system_message("\n".join(lines))
```

Update `_register_builtin_commands` to include usage for `/write`:
```python
        self._command_registry.register(
            "/write", self._cmd_write, "Save session transcript", usage="[filename]"
        )
```

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/unit/tui/test_commands.py -v`
Expected: All PASS.

### Step 5: Run full test suite to check for regressions

Run: `python -m pytest tests/ -x -q --ignore=tests/unit/rlm/test_engine_pool_error_handling.py`
Expected: All PASS (minus the pre-existing failure we're ignoring).

### Step 6: Commit

```bash
git add src/shesha/tui/commands.py src/shesha/tui/app.py tests/unit/tui/test_commands.py
git commit -m "feat: add usage hints to commands and improve /help output"
```

---

## Task 5: Restructure arxiv_explorer.py — Topic subcommands

Split the monolithic `/topic` handler into individual subcommand handlers registered under a `/topic` command group. Absorb `/history` into `/topic list`, `/papers` into `/topic papers`, `/load` into `/topic add`. Rename `/check-citations` to `/check`.

**Files:**
- Modify: `tests/examples/test_arxiv_tui.py` (update tests for new command names)
- Modify: `examples/arxiv_explorer.py`

This is the largest task. The approach:
1. First update the tests to use new command names (they will fail).
2. Then update the implementation to make them pass.

### Step 1: Update tests for new command structure

In `tests/examples/test_arxiv_tui.py`, make these changes:

**TestTUICommands class:**

- `test_papers_no_topic_shows_error`: Change `/papers` to `/topic papers`
- `test_papers_lists_documents`: Change `/papers` to `/topic papers`
- `test_topic_bare_shows_current`: Change to test that bare `/topic` shows **usage help** (list of subcommands), not current topic
- `test_topic_creates_and_switches`: Change `/topic new-topic` to `/topic create new-topic`
- `test_topic_switch_existing`: Change `/topic quantum` to `/topic switch quantum`
- `test_topic_delete`: Change `/topic delete quantum` — stays same (but now resolved as subcommand)
- `test_topic_delete_current_resets_infobar`: Same command, stays same
- `test_topic_rename_calls_rename`: Change `/topic rename quantum qec` — stays same
- `test_topic_rename_updates_infobar`: Same
- `test_history_empty_shows_message`: Change `/history` to `/topic list`
- `test_history_lists_topics`: Change `/history` to `/topic list`
- Add new test: `test_topic_switch_by_number` — `/topic switch 1` switches to the first topic

**TestTUILoadCommand class:**
- `test_load_by_number_stores_document`: Change `/load 1` to `/topic add 1`
- `test_load_requires_topic`: Change `/load 1` to `/topic add 1`

**TestTUICheckCitations class:**
- `test_check_citations_runs_pipeline`: Change `/check-citations` to `/check`
- `test_check_citations_requires_topic`: Change `/check-citations` to `/check`

**Add new tests:**
- `test_old_commands_not_registered`: Verify `/load`, `/papers`, `/history`, `/check-citations` all resolve to `None`
- `test_topic_switch_not_found_shows_error`: `/topic switch nonexistent` when `resolve()` returns `None` shows error
- `test_topic_create_already_exists_shows_error`: `/topic create quantum` when topic already exists shows error

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/examples/test_arxiv_tui.py -v`
Expected: FAIL — new command names not registered yet.

### Step 3: Update arxiv_explorer.py

In `examples/arxiv_explorer.py`, inside `create_app()`:

**a) Replace the monolithic `_cmd_topic` with individual subcommand handlers:**

```python
    def _cmd_topic_help(args: str) -> None:
        """Show topic subcommand usage."""
        output = tui.query_one(OutputArea)
        lines = [
            "Topic management commands:",
            "  /topic list                  List all topics",
            "  /topic switch <name|#>       Switch to a topic (by name or number)",
            "  /topic create <name>         Create a new topic",
            "  /topic delete <name>         Delete a topic",
            "  /topic rename <old> <new>    Rename a topic",
            "  /topic papers                List papers in current topic",
            "  /topic add <#|arxiv-id>...   Add papers from search results or by ID",
        ]
        output.add_system_message("\n".join(lines))

    def _cmd_topic_list(args: str) -> None:
        """List all topics (absorbs /history)."""
        output = tui.query_one(OutputArea)
        topics = state.topic_mgr.list_topics()
        if not topics:
            output.add_system_message("No topics yet. Use /search and /topic add to get started.")
            return
        header = "| # | Topic | Created | Papers | Size |"
        sep = "|---|-------|---------|--------|------|"
        lines = [header, sep]
        for i, t in enumerate(topics, 1):
            created_str = t.created.strftime("%b %d, %Y")
            papers_word = "paper" if t.paper_count == 1 else "papers"
            marker = " **\\***" if t.project_id == state.current_topic else ""
            lines.append(
                f"| {i} | {t.name}{marker} | {created_str} "
                f"| {t.paper_count} {papers_word} | {t.formatted_size} |"
            )
        output.add_system_markdown("\n".join(lines))

    def _cmd_topic_switch(args: str) -> None:
        """Switch to an existing topic by name or number."""
        output = tui.query_one(OutputArea)
        args = args.strip()
        if not args:
            output.add_system_message("Usage: /topic switch <name|#>")
            return
        # Try numeric (from /topic list output)
        if args.isdigit():
            topics = state.topic_mgr.list_topics()
            idx = int(args) - 1
            if 0 <= idx < len(topics):
                t = topics[idx]
                state.current_topic = t.project_id
                docs = state.topic_mgr._storage.list_documents(t.project_id)
                tui._project = state.shesha.get_project(t.project_id)
                tui.query_one(InfoBar).update_project_name(t.name)
                output.add_system_message(f"Switched to topic: {t.name} ({len(docs)} papers)")
            else:
                output.add_system_message(f"Invalid topic number: {args}. Use /topic list to see topics.")
            return
        # Try by name
        project_id = state.topic_mgr.resolve(args)
        if project_id:
            state.current_topic = project_id
            docs = state.topic_mgr._storage.list_documents(project_id)
            tui._project = state.shesha.get_project(project_id)
            tui.query_one(InfoBar).update_project_name(args)
            output.add_system_message(f"Switched to topic: {args} ({len(docs)} papers)")
        else:
            output.add_system_message(
                f"Topic '{args}' not found. Use /topic list to see topics, or /topic create <name>."
            )

    def _cmd_topic_create(args: str) -> None:
        """Create a new topic and switch to it."""
        output = tui.query_one(OutputArea)
        args = args.strip()
        if not args:
            output.add_system_message("Usage: /topic create <name>")
            return
        # Check if topic already exists
        existing = state.topic_mgr.resolve(args)
        if existing:
            output.add_system_message(
                f"Topic '{args}' already exists. Use /topic switch {args} to switch to it."
            )
            return
        project_id = state.topic_mgr.create(args)
        state.current_topic = project_id
        tui._project = state.shesha.get_project(project_id)
        tui.query_one(InfoBar).update_project_name(args)
        output.add_system_message(f"Created topic: {args}")

    def _cmd_topic_delete(args: str) -> None:
        """Delete a topic."""
        output = tui.query_one(OutputArea)
        args = args.strip()
        if not args:
            output.add_system_message("Usage: /topic delete <name>")
            return
        try:
            state.topic_mgr.delete(args)
            output.add_system_message(f"Deleted topic: {args}")
            if state.current_topic and args in state.current_topic:
                state.current_topic = None
                tui.query_one(InfoBar).update_project_name("No topic")
        except ValueError as e:
            output.add_system_message(f"Error: {e}")

    def _cmd_topic_rename(args: str) -> None:
        """Rename a topic."""
        output = tui.query_one(OutputArea)
        parts = args.strip().split(maxsplit=1)
        if len(parts) < 2:
            output.add_system_message("Usage: /topic rename <old-name> <new-name>")
            return
        old_name, new_name = parts
        try:
            state.topic_mgr.rename(old_name, new_name)
            output.add_system_message(f"Renamed topic: {old_name} -> {new_name}")
            old_project_id = state.topic_mgr.resolve(new_name)
            if old_project_id == state.current_topic:
                tui.query_one(InfoBar).update_project_name(new_name)
        except ValueError as e:
            output.add_system_message(f"Error: {e}")

    def _cmd_topic_papers(args: str) -> None:
        """List papers in current topic (absorbs /papers)."""
        output = tui.query_one(OutputArea)
        if state.current_topic is None:
            output.add_system_message("No topic selected. Use /topic create <name> first.")
            return
        docs = state.topic_mgr._storage.list_documents(state.current_topic)
        if not docs:
            output.add_system_message("No papers loaded. Use /search and /topic add to add papers.")
            return
        info = state.topic_mgr.get_topic_info_by_project_id(state.current_topic)
        topic_name = info.name if info else state.current_topic
        lines = [f'**Papers in "{topic_name}":**\n']
        for i, doc_name in enumerate(docs, 1):
            meta = state.cache.get_meta(doc_name)
            if meta:
                lines.append(f'{i}. **[{meta.arxiv_id}]** "{meta.title}"')
                lines.append(f"   {meta.arxiv_url}\n")
            else:
                lines.append(f"{i}. {doc_name}")
        output.add_system_markdown("\n".join(lines))

    def _cmd_topic_add(args: str) -> None:
        """Add papers to current topic (absorbs /load). Threaded."""
        if state.current_topic is None:
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                "No topic selected. Use /topic create <name> first.",
            )
            return
        args = args.strip()
        if not args:
            if not state.last_search_results:
                tui.call_from_thread(
                    tui.query_one(OutputArea).add_system_message,
                    "No search results. Use /search first.",
                )
                return
            tokens = [str(i) for i in range(1, len(state.last_search_results) + 1)]
        else:
            tokens = args.split()
        tui.call_from_thread(tui.query_one(InfoBar).update_thinking, 0.0)
        loaded = 0
        for i, token in enumerate(tokens):
            if i > 0:
                time.sleep(3)
            meta: PaperMeta | None = None
            if token.isdigit():
                idx = int(token) - 1
                if 0 <= idx < len(state.last_search_results):
                    meta = state.last_search_results[idx]
                else:
                    tui.call_from_thread(
                        tui.query_one(OutputArea).add_system_message,
                        f"Invalid result number: {token}",
                    )
                    continue
            elif ARXIV_ID_RE.match(token):
                if state.cache.has(token):
                    meta = state.cache.get_meta(token)
                else:
                    meta = state.searcher.get_by_id(token)
                if meta is None:
                    tui.call_from_thread(
                        tui.query_one(OutputArea).add_system_message,
                        f"Paper not found: {token}",
                    )
                    continue
            else:
                tui.call_from_thread(
                    tui.query_one(OutputArea).add_system_message,
                    f"Invalid input: {token} (use a result number or arXiv ID like 2501.12345)",
                )
                continue
            updated_meta = download_paper(meta, state.cache)
            doc = to_parsed_document(updated_meta.arxiv_id, state.cache)
            state.topic_mgr._storage.store_document(state.current_topic, doc)
            loaded += 1
            source_label = updated_meta.source_type or "unknown"
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                f'Loaded [{updated_meta.arxiv_id}] "{updated_meta.title}" ({source_label})',
            )
        if loaded:
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                f"{loaded} paper(s) loaded into topic.",
            )
        tui.call_from_thread(tui.query_one(InfoBar).reset_phase)
```

**b) Update command registrations** (replace the old registration block at the end of `create_app()`):

```python
    # Register /topic command group
    tui.register_group("/topic", "Topic management")
    tui.register_subcommand("/topic", "list", _cmd_topic_list, "List all topics")
    tui.register_subcommand("/topic", "switch", _cmd_topic_switch, "Switch to a topic")
    tui.register_subcommand("/topic", "create", _cmd_topic_create, "Create a new topic")
    tui.register_subcommand("/topic", "delete", _cmd_topic_delete, "Delete a topic")
    tui.register_subcommand("/topic", "rename", _cmd_topic_rename, "Rename a topic")
    tui.register_subcommand("/topic", "papers", _cmd_topic_papers, "List papers in current topic")
    tui.register_subcommand(
        "/topic",
        "add",
        lambda args: _threaded_guard("add", _cmd_topic_add, args),
        "Add papers from search results",
        threaded=True,
    )
    # Set custom help handler for bare /topic
    tui._command_registry.set_group_help_handler("/topic", _cmd_topic_help)

    tui.register_command(
        "/search",
        lambda args: _threaded_guard("search", _cmd_search, args),
        "Search arXiv",
        threaded=True,
        usage="<query> [--author, --cat, --recent, --sort]",
    )
    tui.register_command(
        "/more",
        lambda args: _threaded_guard("more", _cmd_more, args),
        "Next page of search results",
        threaded=True,
    )
    tui.register_command(
        "/check",
        lambda args: _threaded_guard("check", _cmd_check_citations, args),
        "Verify citations",
        threaded=True,
        usage="[arxiv-id]",
    )
```

**c) Add `register_group` and `register_subcommand` methods to SheshaTUI.** In `src/shesha/tui/app.py`, add after `register_command`:

```python
    def register_group(self, name: str, description: str) -> None:
        """Register a command group."""
        self._command_registry.register_group(name, description)

    def register_subcommand(
        self,
        group: str,
        subcommand: str,
        handler: Callable[[str], object],
        description: str,
        *,
        threaded: bool = False,
    ) -> None:
        """Register a subcommand under a command group."""
        self._command_registry.register_subcommand(
            group, subcommand, handler, description, threaded=threaded
        )
```

**d) Update `register_command` to accept `usage`:**

```python
    def register_command(
        self,
        name: str,
        handler: Callable[[str], object],
        description: str,
        *,
        threaded: bool = False,
        usage: str = "",
    ) -> None:
        self._command_registry.register(name, handler, description, threaded=threaded, usage=usage)
```

**e) Remove old handlers** (`_cmd_papers`, `_cmd_topic`, `_cmd_history`) and old registrations (`/papers`, `/topic`, `/history`, `/load`, `/check-citations`).

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/examples/test_arxiv_tui.py -v`
Expected: All PASS.

### Step 5: Run full test suite

Run: `python -m pytest tests/ -x -q --ignore=tests/unit/rlm/test_engine_pool_error_handling.py`
Expected: All PASS.

### Step 6: Run linting and type checking

Run: `ruff check src tests examples && ruff format --check src tests examples && mypy src/shesha`
Expected: Clean.

### Step 7: Commit

```bash
git add examples/arxiv_explorer.py src/shesha/tui/app.py tests/examples/test_arxiv_tui.py
git commit -m "feat: restructure arXiv TUI commands into /topic subcommands

- /topic list, switch, create, delete, rename, papers, add
- /topic switch accepts name or number from list
- /check replaces /check-citations
- Remove /load, /papers, /history, /check-citations"
```

---

## Task 6: Final verification and cleanup

Run full CI checks to make sure everything is clean.

**Files:** No new files — verification only.

### Step 1: Run full test suite

Run: `python -m pytest tests/ -x -q --ignore=tests/unit/rlm/test_engine_pool_error_handling.py`
Expected: All PASS.

### Step 2: Run linting

Run: `ruff check src tests examples && ruff format --check src tests examples`
Expected: Clean.

### Step 3: Run type checking

Run: `mypy src/shesha`
Expected: Clean.

### Step 4: Verify the popup truncation fix manually

Spot-check: `CompletionPopup` CSS now has `max-height: 20`, which accommodates 8 top-level commands + border padding.

### Step 5: Review all changes

Run: `git diff ovid/arxiv..HEAD --stat` to see summary of all changes.
