# TUI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Textual-based TUI for Shesha's interactive examples, replacing plain input()/print() loops with a 3-pane Claude Code-style interface.

**Architecture:** A `shesha.tui` package provides a `SheshaTUI` Textual App with three widgets (output area, info bar, input area) and a command registry. Examples configure and launch the TUI after their setup phase. Textual is an optional `[tui]` dependency.

**Tech Stack:** Textual (TUI framework), Rich (markdown rendering, pulled in by Textual), Python 3.11+

**Design doc:** `docs/plans/2026-02-08-tui-design.md`

---

### Task 1: Add Textual dependency and create package skeleton

**Files:**
- Modify: `pyproject.toml` (add `[tui]` optional dependency)
- Create: `src/shesha/tui/__init__.py`
- Create: `src/shesha/tui/app.py`
- Create: `src/shesha/tui/commands.py`
- Create: `src/shesha/tui/widgets/__init__.py`
- Create: `src/shesha/tui/widgets/output_area.py`
- Create: `src/shesha/tui/widgets/info_bar.py`
- Create: `src/shesha/tui/widgets/input_area.py`
- Create: `tests/unit/tui/__init__.py`
- Create: `tests/unit/tui/test_commands.py`

**Step 1: Add `textual` to pyproject.toml**

In `pyproject.toml`, add after the `dev` optional dependencies:

```toml
tui = [
    "textual>=1.0",
]
```

Also add `"textual>=1.0"` to the `dev` list so tests can import it.

**Step 2: Install the new dependency**

Run: `pip install -e ".[dev]"`

**Step 3: Create empty package files**

Create the directory structure with minimal placeholder content:

`src/shesha/tui/__init__.py`:
```python
"""Textual-based TUI for Shesha interactive examples."""
```

`src/shesha/tui/app.py`:
```python
"""Main Textual application for Shesha TUI."""
```

`src/shesha/tui/commands.py`:
```python
"""Command registry for TUI slash commands."""
```

`src/shesha/tui/widgets/__init__.py`:
```python
"""TUI widgets for Shesha."""
```

`src/shesha/tui/widgets/output_area.py`:
```python
"""Scrolling output area widget."""
```

`src/shesha/tui/widgets/info_bar.py`:
```python
"""Status info bar widget."""
```

`src/shesha/tui/widgets/input_area.py`:
```python
"""Input area widget with multiline support."""
```

`tests/unit/tui/__init__.py`: empty file.

**Step 4: Run `make all` to verify nothing broke**

Run: `make all`
Expected: 824 tests pass, no lint/type errors.

**Step 5: Commit**

```bash
git add pyproject.toml src/shesha/tui/ tests/unit/tui/
git commit -m "feat: add tui package skeleton and textual dependency"
```

---

### Task 2: Command registry

**Files:**
- Modify: `src/shesha/tui/commands.py`
- Create: `tests/unit/tui/test_commands.py`

The command registry stores slash commands and dispatches them. This is a pure data structure with no Textual dependency, so it's easy to test in isolation.

**Step 1: Write failing tests**

`tests/unit/tui/test_commands.py`:
```python
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
        called = []
        registry = CommandRegistry()
        registry.register("/help", lambda args: called.append(True), "Help")
        result = registry.dispatch("  /help")
        assert result is True
        assert called == [True]
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/tui/test_commands.py -v`
Expected: FAIL — `CommandRegistry` doesn't exist yet.

**Step 3: Implement CommandRegistry**

`src/shesha/tui/commands.py`:
```python
"""Command registry for TUI slash commands."""

from collections.abc import Callable


class CommandRegistry:
    """Registry for slash commands.

    Commands are registered with a name (e.g., "/help"), a handler callable,
    and a description. The handler receives the argument string (everything
    after the command name, stripped).
    """

    def __init__(self) -> None:
        self._commands: dict[str, tuple[Callable[[str], object], str]] = {}

    def register(
        self, name: str, handler: Callable[[str], object], description: str
    ) -> None:
        """Register a slash command."""
        self._commands[name] = (handler, description)

    def list_commands(self) -> list[tuple[str, str]]:
        """Return list of (name, description) tuples, sorted by name."""
        return sorted((name, desc) for name, (_handler, desc) in self._commands.items())

    def dispatch(self, text: str) -> bool:
        """Dispatch a command string. Returns True if command was found."""
        text = text.strip()
        parts = text.split(maxsplit=1)
        if not parts:
            return False
        cmd_name = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        if cmd_name not in self._commands:
            return False
        handler, _ = self._commands[cmd_name]
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
            for name, (_handler, desc) in self._commands.items()
            if name.startswith(prefix)
        )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/tui/test_commands.py -v`
Expected: All pass.

**Step 5: Run `make all`**

Run: `make all`
Expected: All 824+ tests pass, no lint/type errors.

**Step 6: Commit**

```bash
git add src/shesha/tui/commands.py tests/unit/tui/test_commands.py
git commit -m "feat: add TUI command registry with dispatch and auto-complete"
```

---

### Task 3: Info bar widget

**Files:**
- Modify: `src/shesha/tui/widgets/info_bar.py`
- Create: `tests/unit/tui/test_info_bar.py`

The info bar is a 2-line Textual Static widget showing project name, token usage, and current phase. It exposes methods to update state that the app calls from progress callbacks and after queries complete.

**Step 1: Write failing tests**

`tests/unit/tui/test_info_bar.py`:
```python
"""Tests for TUI info bar widget."""

from shesha.tui.widgets.info_bar import InfoBarState


class TestInfoBarState:
    """Tests for InfoBarState data model (no Textual dependency)."""

    def test_initial_state(self) -> None:
        """Initial state shows project name and zero tokens."""
        state = InfoBarState(project_name="barsoom")
        line1, line2 = state.render_lines()
        assert "barsoom" in line1
        assert "0" in line1
        assert "Ready" in line2

    def test_update_tokens(self) -> None:
        """Token counts update after set_tokens."""
        state = InfoBarState(project_name="test")
        state.set_tokens(prompt=1000, completion=200)
        line1, _ = state.render_lines()
        assert "1,200" in line1
        assert "1,000" in line1
        assert "200" in line1

    def test_set_phase_thinking(self) -> None:
        """Phase shows Thinking with elapsed time."""
        state = InfoBarState(project_name="test")
        state.set_thinking(elapsed=0.5)
        _, line2 = state.render_lines()
        assert "0.5s" in line2
        assert "Thinking" in line2

    def test_set_phase_progress(self) -> None:
        """Phase shows iteration and step name."""
        state = InfoBarState(project_name="test")
        state.set_progress(elapsed=13.7, iteration=3, step="Sub-LLM query")
        _, line2 = state.render_lines()
        assert "13.7s" in line2
        assert "Iteration 3" in line2
        assert "Sub-LLM query" in line2

    def test_set_phase_done(self) -> None:
        """Phase shows Done with iteration count."""
        state = InfoBarState(project_name="test")
        state.set_done(elapsed=52.3, iterations=3)
        _, line2 = state.render_lines()
        assert "52.3s" in line2
        assert "Done" in line2
        assert "3" in line2

    def test_set_phase_cancelled(self) -> None:
        """Phase shows Cancelled."""
        state = InfoBarState(project_name="test")
        state.set_cancelled()
        _, line2 = state.render_lines()
        assert "Cancelled" in line2

    def test_reset_to_ready(self) -> None:
        """Reset returns to Ready state."""
        state = InfoBarState(project_name="test")
        state.set_thinking(elapsed=1.0)
        state.reset()
        _, line2 = state.render_lines()
        assert "Ready" in line2
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/tui/test_info_bar.py -v`
Expected: FAIL — `InfoBarState` doesn't exist yet.

**Step 3: Implement InfoBarState**

`src/shesha/tui/widgets/info_bar.py`:
```python
"""Status info bar widget."""

from dataclasses import dataclass, field


@dataclass
class InfoBarState:
    """Data model for the info bar, independent of Textual.

    Tracks project name, token counts, and current phase.
    The render_lines() method produces the two display lines.
    """

    project_name: str
    _prompt_tokens: int = field(default=0, init=False)
    _completion_tokens: int = field(default=0, init=False)
    _phase_line: str = field(default="Ready", init=False)

    def set_tokens(self, prompt: int, completion: int) -> None:
        """Update cumulative token counts."""
        self._prompt_tokens = prompt
        self._completion_tokens = completion

    def set_thinking(self, elapsed: float) -> None:
        """Set phase to Thinking with elapsed time."""
        self._phase_line = f"[{elapsed:.1f}s] Thinking..."

    def set_progress(self, elapsed: float, iteration: int, step: str) -> None:
        """Set phase to a specific iteration/step."""
        self._phase_line = f"[{elapsed:.1f}s] [Iteration {iteration}] {step}"

    def set_done(self, elapsed: float, iterations: int) -> None:
        """Set phase to Done."""
        self._phase_line = f"[{elapsed:.1f}s] Done ({iterations} iterations)"

    def set_cancelled(self) -> None:
        """Set phase to Cancelled."""
        self._phase_line = "Cancelled"

    def reset(self) -> None:
        """Reset phase to Ready."""
        self._phase_line = "Ready"

    def render_lines(self) -> tuple[str, str]:
        """Render the two info bar lines."""
        total = self._prompt_tokens + self._completion_tokens
        line1 = (
            f"Project: {self.project_name} \u2502 "
            f"Tokens: {total:,} (prompt: {self._prompt_tokens:,}, "
            f"comp: {self._completion_tokens:,})"
        )
        line2 = f"Phase: {self._phase_line}"
        return line1, line2
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/tui/test_info_bar.py -v`
Expected: All pass.

**Step 5: Run `make all`**

Run: `make all`
Expected: All tests pass, no lint/type errors.

**Step 6: Commit**

```bash
git add src/shesha/tui/widgets/info_bar.py tests/unit/tui/test_info_bar.py
git commit -m "feat: add info bar state model with token and phase tracking"
```

---

### Task 4: Input history

**Files:**
- Create: `src/shesha/tui/history.py`
- Create: `tests/unit/tui/test_history.py`

A simple in-memory history list that supports up/down navigation. Pure Python, no Textual dependency.

**Step 1: Write failing tests**

`tests/unit/tui/test_history.py`:
```python
"""Tests for TUI input history."""

from shesha.tui.history import InputHistory


class TestInputHistory:
    """Tests for InputHistory."""

    def test_empty_history_previous_returns_none(self) -> None:
        """Previous on empty history returns None."""
        h = InputHistory()
        assert h.previous() is None

    def test_empty_history_next_returns_none(self) -> None:
        """Next on empty history returns None."""
        h = InputHistory()
        assert h.next() is None

    def test_add_and_previous(self) -> None:
        """Can retrieve last entry with previous()."""
        h = InputHistory()
        h.add("hello")
        assert h.previous() == "hello"

    def test_multiple_entries_navigation(self) -> None:
        """Previous walks backward, next walks forward."""
        h = InputHistory()
        h.add("first")
        h.add("second")
        h.add("third")
        assert h.previous() == "third"
        assert h.previous() == "second"
        assert h.previous() == "first"
        assert h.previous() is None  # at start, stays put
        assert h.next() == "second"
        assert h.next() == "third"
        assert h.next() is None  # back to current (empty)

    def test_add_resets_position(self) -> None:
        """Adding an entry resets navigation to end."""
        h = InputHistory()
        h.add("first")
        h.add("second")
        h.previous()  # "second"
        h.previous()  # "first"
        h.add("third")
        assert h.previous() == "third"

    def test_duplicate_consecutive_not_added(self) -> None:
        """Consecutive duplicates are not added."""
        h = InputHistory()
        h.add("hello")
        h.add("hello")
        assert h.previous() == "hello"
        assert h.previous() is None  # only one entry
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/tui/test_history.py -v`
Expected: FAIL — `InputHistory` doesn't exist yet.

**Step 3: Implement InputHistory**

`src/shesha/tui/history.py`:
```python
"""Input history for TUI prompt."""


class InputHistory:
    """In-memory input history with up/down navigation.

    Entries are stored in order of addition. Navigation uses an internal
    cursor that starts past the end (current input). previous() moves
    backward, next() moves forward.
    """

    def __init__(self) -> None:
        self._entries: list[str] = []
        self._cursor: int = 0

    def add(self, entry: str) -> None:
        """Add an entry to history. Skips consecutive duplicates."""
        if self._entries and self._entries[-1] == entry:
            self._cursor = len(self._entries)
            return
        self._entries.append(entry)
        self._cursor = len(self._entries)

    def previous(self) -> str | None:
        """Move cursor back and return entry, or None if at start."""
        if self._cursor <= 0:
            return None
        self._cursor -= 1
        return self._entries[self._cursor]

    def next(self) -> str | None:
        """Move cursor forward and return entry, or None if at end."""
        if self._cursor >= len(self._entries) - 1:
            self._cursor = len(self._entries)
            return None
        self._cursor += 1
        return self._entries[self._cursor]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/tui/test_history.py -v`
Expected: All pass.

**Step 5: Run `make all`**

Run: `make all`
Expected: All tests pass.

**Step 6: Commit**

```bash
git add src/shesha/tui/history.py tests/unit/tui/test_history.py
git commit -m "feat: add input history with up/down navigation"
```

---

### Task 5: Conversation session (history + formatting)

**Files:**
- Create: `src/shesha/tui/session.py`
- Create: `tests/unit/tui/test_session.py`

The session manages conversation history, context formatting for follow-up questions, history size warnings, and transcript writing. This absorbs logic from `script_utils.py`.

**Step 1: Write failing tests**

`tests/unit/tui/test_session.py`:
```python
"""Tests for TUI conversation session."""

from unittest.mock import patch

from shesha.tui.session import ConversationSession


class TestConversationSession:
    """Tests for ConversationSession."""

    def test_empty_session(self) -> None:
        """New session has no exchanges."""
        session = ConversationSession(project_name="test")
        assert session.exchange_count == 0
        assert session.format_history_prefix() == ""

    def test_add_exchange(self) -> None:
        """Adding an exchange increments count."""
        session = ConversationSession(project_name="test")
        session.add_exchange("question", "answer", "stats")
        assert session.exchange_count == 1

    def test_format_history_prefix(self) -> None:
        """History prefix formats previous Q&A."""
        session = ConversationSession(project_name="test")
        session.add_exchange("Who is X?", "X is Y.", "stats")
        prefix = session.format_history_prefix()
        assert "Q1: Who is X?" in prefix
        assert "A1: X is Y." in prefix
        assert "Current question:" in prefix

    def test_should_warn_by_exchanges(self) -> None:
        """Warns when exchange count exceeds threshold."""
        session = ConversationSession(project_name="test", warn_exchanges=2)
        session.add_exchange("q1", "a1", "s1")
        assert session.should_warn_history_size() is False
        session.add_exchange("q2", "a2", "s2")
        assert session.should_warn_history_size() is True

    def test_should_warn_by_chars(self) -> None:
        """Warns when total chars exceed threshold."""
        session = ConversationSession(project_name="test", warn_chars=20)
        session.add_exchange("short", "short", "s")
        assert session.should_warn_history_size() is False
        session.add_exchange("a" * 20, "b" * 20, "s")
        assert session.should_warn_history_size() is True

    def test_clear_history(self) -> None:
        """Clear removes all exchanges."""
        session = ConversationSession(project_name="test")
        session.add_exchange("q", "a", "s")
        session.clear_history()
        assert session.exchange_count == 0
        assert session.format_history_prefix() == ""

    def test_format_transcript(self) -> None:
        """Transcript includes project name and exchanges."""
        session = ConversationSession(project_name="barsoom")
        session.add_exchange("Who is X?", "X is Y.", "---\nTime: 1s")
        transcript = session.format_transcript()
        assert "barsoom" in transcript
        assert "Who is X?" in transcript
        assert "X is Y." in transcript

    def test_write_transcript(self, tmp_path: object) -> None:
        """Write transcript creates file."""
        import os
        from pathlib import Path

        tmp = Path(str(tmp_path))
        session = ConversationSession(project_name="test")
        session.add_exchange("q", "a", "s")
        path = session.write_transcript(str(tmp / "out.md"))
        assert Path(path).exists()
        content = Path(path).read_text()
        assert "test" in content

    def test_write_transcript_auto_filename(self, tmp_path: object) -> None:
        """Write transcript with None filename auto-generates name."""
        import os
        from pathlib import Path

        tmp = Path(str(tmp_path))
        os.chdir(tmp)
        session = ConversationSession(project_name="test")
        session.add_exchange("q", "a", "s")
        path = session.write_transcript(None)
        assert "session-" in path
        assert path.endswith(".md")
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/tui/test_session.py -v`
Expected: FAIL — `ConversationSession` doesn't exist yet.

**Step 3: Implement ConversationSession**

`src/shesha/tui/session.py`:
```python
"""Conversation session for TUI."""

from datetime import datetime
from pathlib import Path


class ConversationSession:
    """Manages conversation history, context formatting, and transcript export.

    Args:
        project_name: Name of the project for transcript metadata.
        warn_exchanges: Warn when exchange count reaches this threshold.
        warn_chars: Warn when total chars reach this threshold.
    """

    def __init__(
        self,
        project_name: str,
        warn_exchanges: int = 10,
        warn_chars: int = 50_000,
    ) -> None:
        self.project_name = project_name
        self._warn_exchanges = warn_exchanges
        self._warn_chars = warn_chars
        self._history: list[tuple[str, str, str]] = []

    @property
    def exchange_count(self) -> int:
        """Number of exchanges in history."""
        return len(self._history)

    def add_exchange(self, question: str, answer: str, stats: str) -> None:
        """Add a Q&A exchange to history."""
        self._history.append((question, answer, stats))

    def clear_history(self) -> None:
        """Clear all history."""
        self._history.clear()

    def format_history_prefix(self) -> str:
        """Format history as context prefix for follow-up questions."""
        if not self._history:
            return ""
        lines = ["Previous conversation:"]
        for i, (q, a, _stats) in enumerate(self._history, 1):
            lines.append(f"Q{i}: {q}")
            lines.append(f"A{i}: {a}")
            lines.append("")
        lines.append("Current question:")
        return "\n".join(lines)

    def should_warn_history_size(self) -> bool:
        """Check if history is large enough to warrant a warning."""
        if len(self._history) >= self._warn_exchanges:
            return True
        total_chars = sum(len(q) + len(a) for q, a, _s in self._history)
        return total_chars >= self._warn_chars

    def format_transcript(self) -> str:
        """Format history as a markdown transcript."""
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# Session Transcript",
            "",
            f"- **Date:** {date_str}",
            f"- **Project:** {self.project_name}",
            f"- **Exchanges:** {len(self._history)}",
            "",
            "---",
        ]
        for question, answer, stats in self._history:
            lines.extend(["", f"**User:** {question}", "", answer, "", stats, "", "---"])
        return "\n".join(lines)

    def write_transcript(self, filename: str | None) -> str:
        """Write transcript to file. Auto-generates name if None."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
            filename = f"session-{timestamp}.md"
        filepath = Path(filename)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(self.format_transcript())
        return str(filepath)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/tui/test_session.py -v`
Expected: All pass.

**Step 5: Run `make all`**

Run: `make all`
Expected: All tests pass.

**Step 6: Commit**

```bash
git add src/shesha/tui/session.py tests/unit/tui/test_session.py
git commit -m "feat: add conversation session with history and transcript export"
```

---

### Task 6: Step type to display name mapping

**Files:**
- Create: `src/shesha/tui/progress.py`
- Create: `tests/unit/tui/test_progress.py`

A helper that maps `StepType` enum values to human-readable step names for the info bar. This absorbs the mapping from `script_utils.format_progress`.

**Step 1: Write failing tests**

`tests/unit/tui/test_progress.py`:
```python
"""Tests for TUI progress helpers."""

from shesha.rlm.trace import StepType
from shesha.tui.progress import step_display_name


class TestStepDisplayName:
    """Tests for step_display_name."""

    def test_code_generated(self) -> None:
        assert step_display_name(StepType.CODE_GENERATED) == "Generating code"

    def test_code_output(self) -> None:
        assert step_display_name(StepType.CODE_OUTPUT) == "Executing code"

    def test_subcall_request(self) -> None:
        assert step_display_name(StepType.SUBCALL_REQUEST) == "Sub-LLM query"

    def test_subcall_response(self) -> None:
        assert step_display_name(StepType.SUBCALL_RESPONSE) == "Sub-LLM response"

    def test_final_answer(self) -> None:
        assert step_display_name(StepType.FINAL_ANSWER) == "Final answer"

    def test_error(self) -> None:
        assert step_display_name(StepType.ERROR) == "Error"

    def test_verification(self) -> None:
        assert step_display_name(StepType.VERIFICATION) == "Verification"

    def test_semantic_verification(self) -> None:
        assert step_display_name(StepType.SEMANTIC_VERIFICATION) == "Semantic verification"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/tui/test_progress.py -v`
Expected: FAIL.

**Step 3: Implement step_display_name**

`src/shesha/tui/progress.py`:
```python
"""Progress display helpers for TUI."""

from shesha.rlm.trace import StepType

_STEP_NAMES: dict[StepType, str] = {
    StepType.CODE_GENERATED: "Generating code",
    StepType.CODE_OUTPUT: "Executing code",
    StepType.SUBCALL_REQUEST: "Sub-LLM query",
    StepType.SUBCALL_RESPONSE: "Sub-LLM response",
    StepType.FINAL_ANSWER: "Final answer",
    StepType.ERROR: "Error",
    StepType.VERIFICATION: "Verification",
    StepType.SEMANTIC_VERIFICATION: "Semantic verification",
}


def step_display_name(step_type: StepType) -> str:
    """Get human-readable display name for a step type."""
    return _STEP_NAMES.get(step_type, step_type.value)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/tui/test_progress.py -v`
Expected: All pass.

**Step 5: Run `make all`**

Run: `make all`
Expected: All tests pass.

**Step 6: Commit**

```bash
git add src/shesha/tui/progress.py tests/unit/tui/test_progress.py
git commit -m "feat: add step type display name mapping for info bar"
```

---

### Task 7: Output area widget

**Files:**
- Modify: `src/shesha/tui/widgets/output_area.py`
- Create: `tests/unit/tui/test_output_area.py`

The output area is a Textual widget that displays conversation exchanges. It has a `markdown_enabled` toggle that controls whether responses render as markdown or plain text. We test the data model separately from the Textual rendering.

**Step 1: Write failing tests**

`tests/unit/tui/test_output_area.py`:
```python
"""Tests for output area widget."""

from textual.app import App, ComposeResult

from shesha.tui.widgets.output_area import OutputArea


class OutputAreaApp(App[None]):
    """Minimal app for testing OutputArea."""

    def compose(self) -> ComposeResult:
        yield OutputArea()


class TestOutputArea:
    """Tests for OutputArea widget."""

    async def test_add_user_message(self) -> None:
        """User messages are added to the output."""
        async with OutputAreaApp().run_test() as pilot:
            output = pilot.app.query_one(OutputArea)
            output.add_user_message("Hello world")
            # Check that content was added
            assert output.query("Static")  # At least one Static widget

    async def test_add_response_markdown_on(self) -> None:
        """Response with markdown enabled renders Markdown widget."""
        async with OutputAreaApp().run_test() as pilot:
            output = pilot.app.query_one(OutputArea)
            output.markdown_enabled = True
            output.add_response("**bold text**", thought_seconds=5.0)
            markdown_widgets = output.query("Markdown")
            assert len(markdown_widgets) > 0

    async def test_add_response_markdown_off(self) -> None:
        """Response with markdown disabled renders Static widget."""
        async with OutputAreaApp().run_test() as pilot:
            output = pilot.app.query_one(OutputArea)
            output.markdown_enabled = False
            output.add_response("**bold text**", thought_seconds=3.0)
            # Should have Static widgets but no Markdown
            static_widgets = output.query("Static")
            assert len(static_widgets) > 0

    async def test_toggle_markdown(self) -> None:
        """Toggling markdown flips the flag."""
        async with OutputAreaApp().run_test() as pilot:
            output = pilot.app.query_one(OutputArea)
            assert output.markdown_enabled is True  # default
            output.markdown_enabled = False
            assert output.markdown_enabled is False

    async def test_scroll_to_bottom_on_add(self) -> None:
        """Adding content scrolls to bottom."""
        async with OutputAreaApp().run_test() as pilot:
            output = pilot.app.query_one(OutputArea)
            for i in range(20):
                output.add_user_message(f"Message {i}")
            # After adding many messages, scroll position should be at bottom
            # (Textual handles this; we just verify no error)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/tui/test_output_area.py -v`
Expected: FAIL — `OutputArea` class doesn't have the required methods.

**Step 3: Implement OutputArea**

`src/shesha/tui/widgets/output_area.py`:
```python
"""Scrolling output area widget."""

from textual.containers import VerticalScroll
from textual.widgets import Markdown, Static


class OutputArea(VerticalScroll):
    """Scrolling container for conversation output.

    Displays user messages and LLM responses. Supports toggling
    between markdown rendering and plain text for responses.
    """

    DEFAULT_CSS = """
    OutputArea {
        height: 1fr;
        padding: 0 1;
    }
    OutputArea .user-message {
        color: $accent;
        margin-top: 1;
    }
    OutputArea .thought-time {
        color: $text-muted;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.markdown_enabled: bool = True

    def add_user_message(self, text: str) -> None:
        """Add a user message to the output."""
        widget = Static(f"> {text}", classes="user-message")
        self.mount(widget)
        self.scroll_end(animate=False)

    def add_response(self, text: str, thought_seconds: float) -> None:
        """Add an LLM response with thought time."""
        seconds = round(thought_seconds)
        unit = "second" if seconds == 1 else "seconds"
        time_widget = Static(
            f"[Thought for {seconds} {unit}]", classes="thought-time"
        )
        self.mount(time_widget)

        if self.markdown_enabled:
            response_widget = Markdown(text)
        else:
            response_widget = Static(text)
        self.mount(response_widget)
        self.scroll_end(animate=False)

    def add_system_message(self, text: str) -> None:
        """Add a system/info message to the output."""
        widget = Static(text, classes="system-message")
        self.mount(widget)
        self.scroll_end(animate=False)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/tui/test_output_area.py -v`
Expected: All pass.

**Step 5: Run `make all`**

Run: `make all`
Expected: All tests pass.

**Step 6: Commit**

```bash
git add src/shesha/tui/widgets/output_area.py tests/unit/tui/test_output_area.py
git commit -m "feat: add output area widget with markdown toggle"
```

---

### Task 8: Info bar Textual widget

**Files:**
- Modify: `src/shesha/tui/widgets/info_bar.py`
- Create: `tests/unit/tui/test_info_bar_widget.py`

Wrap the `InfoBarState` from Task 3 in a Textual `Static` widget that re-renders when state changes.

**Step 1: Write failing tests**

`tests/unit/tui/test_info_bar_widget.py`:
```python
"""Tests for info bar Textual widget."""

from textual.app import App, ComposeResult

from shesha.tui.widgets.info_bar import InfoBar


class InfoBarApp(App[None]):
    """Minimal app for testing InfoBar."""

    def compose(self) -> ComposeResult:
        yield InfoBar(project_name="test-project")


class TestInfoBarWidget:
    """Tests for InfoBar Textual widget."""

    async def test_initial_render(self) -> None:
        """Info bar renders with project name on startup."""
        async with InfoBarApp().run_test() as pilot:
            bar = pilot.app.query_one(InfoBar)
            text = bar.renderable
            assert "test-project" in str(text)

    async def test_update_tokens(self) -> None:
        """Updating tokens refreshes the display."""
        async with InfoBarApp().run_test() as pilot:
            bar = pilot.app.query_one(InfoBar)
            bar.update_tokens(prompt=5000, completion=1000)
            text = str(bar.renderable)
            assert "6,000" in text
            assert "5,000" in text

    async def test_update_phase(self) -> None:
        """Updating phase refreshes the display."""
        async with InfoBarApp().run_test() as pilot:
            bar = pilot.app.query_one(InfoBar)
            bar.update_progress(elapsed=5.2, iteration=2, step="Generating code")
            text = str(bar.renderable)
            assert "5.2s" in text
            assert "Iteration 2" in text
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/tui/test_info_bar_widget.py -v`
Expected: FAIL — `InfoBar` widget class doesn't exist yet.

**Step 3: Add InfoBar widget to info_bar.py**

Append to `src/shesha/tui/widgets/info_bar.py`:
```python
# Add these imports at top:
from textual.widgets import Static

# Add after InfoBarState class:

class InfoBar(Static):
    """Textual widget displaying the info bar.

    Two-line status bar showing project info, token counts, and phase.
    """

    DEFAULT_CSS = """
    InfoBar {
        height: 2;
        padding: 0 1;
        border-top: solid $accent;
        border-bottom: solid $accent;
    }
    """

    def __init__(self, project_name: str) -> None:
        super().__init__("")
        self._state = InfoBarState(project_name=project_name)
        self._refresh_content()

    def _refresh_content(self) -> None:
        """Re-render from state."""
        line1, line2 = self._state.render_lines()
        self.update(f"{line1}\n{line2}")

    def update_tokens(self, prompt: int, completion: int) -> None:
        """Update token display."""
        self._state.set_tokens(prompt, completion)
        self._refresh_content()

    def update_thinking(self, elapsed: float) -> None:
        """Show thinking state."""
        self._state.set_thinking(elapsed)
        self._refresh_content()

    def update_progress(self, elapsed: float, iteration: int, step: str) -> None:
        """Show progress state."""
        self._state.set_progress(elapsed, iteration, step)
        self._refresh_content()

    def update_done(self, elapsed: float, iterations: int) -> None:
        """Show done state."""
        self._state.set_done(elapsed, iterations)
        self._refresh_content()

    def update_cancelled(self) -> None:
        """Show cancelled state."""
        self._state.set_cancelled()
        self._refresh_content()

    def reset_phase(self) -> None:
        """Reset to ready state."""
        self._state.reset()
        self._refresh_content()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/tui/test_info_bar_widget.py -v`
Expected: All pass.

**Step 5: Run `make all`**

Run: `make all`
Expected: All tests pass.

**Step 6: Commit**

```bash
git add src/shesha/tui/widgets/info_bar.py tests/unit/tui/test_info_bar_widget.py
git commit -m "feat: add info bar Textual widget wrapping InfoBarState"
```

---

### Task 9: Input area widget

**Files:**
- Modify: `src/shesha/tui/widgets/input_area.py`
- Create: `tests/unit/tui/test_input_area.py`

The input area handles: Enter to submit, Shift+Enter for newline, trailing `\` continuation, Up/Down for history, Escape behavior, and paste detection. It posts a custom Textual message when the user submits.

**Step 1: Write failing tests**

`tests/unit/tui/test_input_area.py`:
```python
"""Tests for input area widget."""

from textual.app import App, ComposeResult
from textual.events import Key

from shesha.tui.widgets.input_area import InputArea, InputSubmitted


class InputAreaApp(App[None]):
    """Minimal app for testing InputArea."""

    submitted_texts: list[str]

    def __init__(self) -> None:
        super().__init__()
        self.submitted_texts = []

    def compose(self) -> ComposeResult:
        yield InputArea()

    def on_input_submitted(self, event: InputSubmitted) -> None:
        self.submitted_texts.append(event.text)


class TestInputArea:
    """Tests for InputArea widget."""

    async def test_submit_on_enter(self) -> None:
        """Enter key submits the input text."""
        async with InputAreaApp().run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "hello"
            await pilot.press("enter")
            assert pilot.app.submitted_texts == ["hello"]

    async def test_input_cleared_after_submit(self) -> None:
        """Input is cleared after submission."""
        async with InputAreaApp().run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "hello"
            await pilot.press("enter")
            assert input_area.text == ""

    async def test_empty_input_not_submitted(self) -> None:
        """Empty input is not submitted."""
        async with InputAreaApp().run_test() as pilot:
            await pilot.press("enter")
            assert pilot.app.submitted_texts == []

    async def test_trailing_backslash_stripped(self) -> None:
        """Trailing backslash is stripped from submitted text."""
        async with InputAreaApp().run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            # Simulate multiline text with trailing backslash
            input_area.text = "line one \\\nline two"
            await pilot.press("enter")
            assert "line one" in pilot.app.submitted_texts[0]
            assert "\\" not in pilot.app.submitted_texts[0]
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/tui/test_input_area.py -v`
Expected: FAIL.

**Step 3: Implement InputArea**

`src/shesha/tui/widgets/input_area.py`:
```python
"""Input area widget with multiline support."""

import re

from textual.message import Message
from textual.widgets import TextArea


class InputSubmitted(Message):
    """Posted when the user submits input."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class InputArea(TextArea):
    """Input widget for the TUI prompt.

    Enter submits, Shift+Enter inserts newline.
    Trailing backslashes on lines are treated as continuation markers
    and stripped before submission.
    """

    DEFAULT_CSS = """
    InputArea {
        height: auto;
        min-height: 1;
        max-height: 10;
        border-top: solid $accent;
    }
    """

    BINDINGS = []  # Override default TextArea bindings

    def __init__(self) -> None:
        super().__init__(language=None, show_line_numbers=False)
        self._query_in_progress = False

    @property
    def query_in_progress(self) -> bool:
        """Whether a query is currently running."""
        return self._query_in_progress

    @query_in_progress.setter
    def query_in_progress(self, value: bool) -> None:
        self._query_in_progress = value

    def _on_key(self, event: "Key") -> None:
        """Handle key events."""
        if event.key == "enter" and not event.shift:
            event.prevent_default()
            event.stop()
            text = self.text.strip()
            if not text:
                return
            # Strip trailing backslash continuation markers
            cleaned = re.sub(r"\\\n", "\n", text).rstrip("\\")
            self.post_message(InputSubmitted(cleaned))
            self.text = ""
            return

        if event.key == "escape":
            event.prevent_default()
            event.stop()
            if self.text:
                self.text = ""
            elif self._query_in_progress:
                self.post_message(InputArea.QueryCancelled())
            return

        # Let TextArea handle everything else (including shift+enter for newline)

    class QueryCancelled(Message):
        """Posted when user double-escapes to cancel a query."""
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/tui/test_input_area.py -v`
Expected: All pass.

**Step 5: Run `make all`**

Run: `make all`
Expected: All tests pass.

**Step 6: Commit**

```bash
git add src/shesha/tui/widgets/input_area.py tests/unit/tui/test_input_area.py
git commit -m "feat: add input area widget with submit, escape, and continuation"
```

---

### Task 10: Main SheshaTUI app

**Files:**
- Modify: `src/shesha/tui/app.py`
- Modify: `src/shesha/tui/__init__.py`
- Create: `tests/unit/tui/test_app.py`

The main Textual App that composes all three widgets, wires up the command registry with built-in commands, handles query execution in a worker thread, and manages the progress callback → info bar updates.

**Step 1: Write failing tests**

`tests/unit/tui/test_app.py`:
```python
"""Tests for main SheshaTUI app."""

from unittest.mock import MagicMock, patch

from shesha.tui.app import SheshaTUI
from shesha.tui.widgets.info_bar import InfoBar
from shesha.tui.widgets.input_area import InputArea
from shesha.tui.widgets.output_area import OutputArea


class TestSheshaTUIComposition:
    """Tests for SheshaTUI app layout."""

    async def test_app_has_three_widgets(self) -> None:
        """App composes output area, info bar, and input area."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            assert pilot.app.query_one(OutputArea)
            assert pilot.app.query_one(InfoBar)
            assert pilot.app.query_one(InputArea)

    async def test_builtin_commands_registered(self) -> None:
        """Built-in commands are registered on startup."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            commands = pilot.app._command_registry.list_commands()
            names = [name for name, _desc in commands]
            assert "/help" in names
            assert "/quit" in names
            assert "/write" in names
            assert "/markdown" in names
            assert "/theme" in names

    async def test_register_custom_command(self) -> None:
        """Custom commands can be registered before run."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        app.register_command("/custom", lambda args: None, "Custom command")
        async with app.run_test() as pilot:
            commands = pilot.app._command_registry.list_commands()
            names = [name for name, _desc in commands]
            assert "/custom" in names

    async def test_help_command_shows_output(self) -> None:
        """The /help command adds a message to the output area."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "/help"
            await pilot.press("enter")
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            # Should have at least one system message with command list
            statics = output.query("Static")
            assert len(statics) > 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/tui/test_app.py -v`
Expected: FAIL — `SheshaTUI` not yet implemented.

**Step 3: Implement SheshaTUI**

`src/shesha/tui/app.py`:
```python
"""Main Textual application for Shesha TUI."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.css.query import NoMatches

from shesha.rlm.trace import StepType
from shesha.tui.commands import CommandRegistry
from shesha.tui.history import InputHistory
from shesha.tui.progress import step_display_name
from shesha.tui.session import ConversationSession
from shesha.tui.widgets.info_bar import InfoBar
from shesha.tui.widgets.input_area import InputArea, InputSubmitted
from shesha.tui.widgets.output_area import OutputArea

if TYPE_CHECKING:
    from shesha.project import Project
    from shesha.rlm.engine import QueryResult


# Brand color matching the Shesha logo
SHESHA_TEAL = "#00bcd4"


class SheshaTUI(App[None]):
    """Textual app for interactive Shesha Q&A sessions.

    Args:
        project: Shesha Project instance to query against.
        project_name: Display name for the project.
        analysis_context: Optional analysis text prepended to queries.
    """

    CSS = f"""
    Screen {{
        layout: vertical;
        border: solid {SHESHA_TEAL};
    }}
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(
        self,
        project: Project,
        project_name: str,
        analysis_context: str | None = None,
    ) -> None:
        super().__init__()
        self._project = project
        self._project_name = project_name
        self._analysis_context = analysis_context
        self._command_registry = CommandRegistry()
        self._input_history = InputHistory()
        self._session = ConversationSession(project_name=project_name)
        self._query_in_progress = False
        self._query_start_time = 0.0
        self._last_iteration = 0
        self._cumulative_prompt_tokens = 0
        self._cumulative_completion_tokens = 0
        self._timer_handle: object | None = None
        self._register_builtin_commands()

    def _register_builtin_commands(self) -> None:
        """Register the default slash commands."""
        self._command_registry.register("/help", self._cmd_help, "Show available commands")
        self._command_registry.register(
            "/write", self._cmd_write, "Save session transcript [filename]"
        )
        self._command_registry.register(
            "/markdown", self._cmd_markdown, "Toggle markdown rendering"
        )
        self._command_registry.register(
            "/theme", self._cmd_theme, "Toggle dark/light theme"
        )
        self._command_registry.register("/quit", self._cmd_quit, "Exit")

    def register_command(
        self, name: str, handler: Callable[[str], object], description: str
    ) -> None:
        """Register a custom slash command."""
        self._command_registry.register(name, handler, description)

    def compose(self) -> ComposeResult:
        """Create the 3-pane layout."""
        yield OutputArea()
        yield InfoBar(project_name=self._project_name)
        yield InputArea()

    def on_mount(self) -> None:
        """Focus the input area on startup."""
        try:
            self.query_one(InputArea).focus()
        except NoMatches:
            pass

    def on_input_submitted(self, event: InputSubmitted) -> None:
        """Handle user input submission."""
        text = event.text

        # Check if it's a command
        if self._command_registry.is_command(text):
            if not self._command_registry.dispatch(text):
                self.query_one(OutputArea).add_system_message(
                    f"Unknown command: {text.strip().split()[0]}"
                )
            return

        # It's a query — add to history and execute
        self._input_history.add(text)
        self.query_one(OutputArea).add_user_message(text)
        self._run_query(text)

    def _run_query(self, question: str) -> None:
        """Execute a query in a worker thread."""
        self._query_in_progress = True
        self.query_one(InputArea).query_in_progress = True
        self._query_start_time = time.time()
        self._last_iteration = 0

        # Start elapsed timer
        info_bar = self.query_one(InfoBar)
        info_bar.update_thinking(0.0)
        self._timer_handle = self.set_interval(0.1, self._tick_timer)

        # Build full question with context
        prefix = self._session.format_history_prefix()
        if self._analysis_context and prefix:
            full_question = f"{self._analysis_context}\n\n{prefix}{question}"
        elif self._analysis_context:
            full_question = f"{self._analysis_context}\n\n{question}"
        elif prefix:
            full_question = f"{prefix}{question}"
        else:
            full_question = question

        self.run_worker(
            self._execute_query(full_question, question),
            thread=True,
        )

    def _execute_query(
        self, full_question: str, display_question: str
    ) -> Callable[[], QueryResult | None]:
        """Return a callable that runs the query (for worker thread)."""

        def run() -> "QueryResult | None":
            try:
                result = self._project.query(
                    full_question,
                    on_progress=self._on_progress,
                )
                self.call_from_thread(self._on_query_complete, result, display_question)
                return result
            except Exception as exc:
                self.call_from_thread(self._on_query_error, str(exc))
                return None

        return run

    def _on_progress(self, step_type: StepType, iteration: int, content: str) -> None:
        """Progress callback from RLM engine (called from worker thread)."""
        elapsed = time.time() - self._query_start_time
        self._last_iteration = iteration + 1  # Convert 0-indexed to 1-indexed
        step_name = step_display_name(step_type)
        self.call_from_thread(
            self.query_one(InfoBar).update_progress,
            elapsed,
            self._last_iteration,
            step_name,
        )

    def _tick_timer(self) -> None:
        """Update elapsed time in info bar."""
        if not self._query_in_progress:
            return
        elapsed = time.time() - self._query_start_time
        info_bar = self.query_one(InfoBar)
        if self._last_iteration == 0:
            info_bar.update_thinking(elapsed)

    def _on_query_complete(self, result: "QueryResult", question: str) -> None:
        """Handle completed query (called on main thread)."""
        self._stop_query()

        # Update tokens
        self._cumulative_prompt_tokens += result.token_usage.prompt_tokens
        self._cumulative_completion_tokens += result.token_usage.completion_tokens
        info_bar = self.query_one(InfoBar)
        info_bar.update_tokens(
            self._cumulative_prompt_tokens, self._cumulative_completion_tokens
        )
        info_bar.update_done(result.execution_time, self._last_iteration)

        # Display response
        output = self.query_one(OutputArea)
        output.add_response(result.answer, result.execution_time)

        # Store in session
        total = result.token_usage.total_tokens
        stats = (
            f"---\n"
            f"Execution time: {result.execution_time:.2f}s\n"
            f"Tokens: {total} "
            f"(prompt: {result.token_usage.prompt_tokens}, "
            f"completion: {result.token_usage.completion_tokens})\n"
            f"Trace steps: {len(result.trace.steps)}"
        )
        self._session.add_exchange(question, result.answer, stats)

        # Reset to ready after brief delay
        self.set_timer(2.0, info_bar.reset_phase)

    def _on_query_error(self, error_msg: str) -> None:
        """Handle query error (called on main thread)."""
        self._stop_query()
        self.query_one(OutputArea).add_system_message(f"Error: {error_msg}")
        self.query_one(InfoBar).reset_phase()

    def _stop_query(self) -> None:
        """Clean up query state."""
        self._query_in_progress = False
        self.query_one(InputArea).query_in_progress = False
        if self._timer_handle is not None:
            self._timer_handle.stop()  # type: ignore[union-attr]
            self._timer_handle = None

    # --- Built-in command handlers ---

    def _cmd_help(self, args: str) -> None:
        """Show help."""
        lines = ["Available commands:"]
        for name, desc in self._command_registry.list_commands():
            lines.append(f"  {name:20s} {desc}")
        self.query_one(OutputArea).add_system_message("\n".join(lines))

    def _cmd_write(self, args: str) -> None:
        """Save session transcript."""
        if self._session.exchange_count == 0:
            self.query_one(OutputArea).add_system_message(
                "Nothing to save - no exchanges yet."
            )
            return
        filename = args.strip() or None
        if filename and not filename.lower().endswith(".md"):
            filename = filename + ".md"
        try:
            path = self._session.write_transcript(filename)
            self.query_one(OutputArea).add_system_message(
                f"Session saved to {path} ({self._session.exchange_count} exchanges)"
            )
        except OSError as e:
            self.query_one(OutputArea).add_system_message(f"Error saving: {e}")

    def _cmd_markdown(self, args: str) -> None:
        """Toggle markdown rendering."""
        output = self.query_one(OutputArea)
        output.markdown_enabled = not output.markdown_enabled
        state = "ON" if output.markdown_enabled else "OFF"
        output.add_system_message(f"Markdown rendering: {state}")

    def _cmd_theme(self, args: str) -> None:
        """Toggle dark/light theme."""
        self.dark = not self.dark
        theme = "dark" if self.dark else "light"
        self.query_one(OutputArea).add_system_message(f"Theme: {theme}")

    def _cmd_quit(self, args: str) -> None:
        """Exit the app."""
        self.exit()
```

Update `src/shesha/tui/__init__.py`:
```python
"""Textual-based TUI for Shesha interactive examples."""

from shesha.tui.app import SheshaTUI

__all__ = ["SheshaTUI"]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/tui/test_app.py -v`
Expected: All pass.

**Step 5: Run `make all`**

Run: `make all`
Expected: All tests pass, lint/type checks clean.

**Step 6: Commit**

```bash
git add src/shesha/tui/app.py src/shesha/tui/__init__.py tests/unit/tui/test_app.py
git commit -m "feat: add SheshaTUI main app with 3-pane layout and command dispatch"
```

---

### Task 11: Integrate TUI into barsoom.py

**Files:**
- Modify: `examples/barsoom.py`
- Modify: `tests/examples/test_barsoom.py`

Replace the interactive loop in `barsoom.py` with `SheshaTUI`. The setup/args/project-loading code stays. The `--verbose` flag is removed since the info bar replaces it. Commands change to `/` prefix.

**Step 1: Update test expectations**

In `tests/examples/test_barsoom.py`, update:
- Remove `test_parse_args_verbose_flag` and `test_parse_args_both_flags` (no more `--verbose`)
- Update help text expectations to use `/` prefix commands
- Add test that barsoom.py imports SheshaTUI

**Step 2: Run tests to verify they fail**

Run: `pytest tests/examples/test_barsoom.py -v`
Expected: Some tests fail due to changed code.

**Step 3: Update barsoom.py**

Key changes:
- Remove `--verbose` argument
- Remove the `while True` interactive loop
- After project setup, create `SheshaTUI(project=project, project_name=PROJECT_NAME)` and call `tui.run()`
- Keep non-interactive `--prompt` mode as-is (it doesn't use the TUI)
- Remove imports that are no longer needed (`ThinkingSpinner`, `format_progress`, etc.)

**Step 4: Run tests to verify they pass**

Run: `pytest tests/examples/test_barsoom.py -v`
Expected: All pass.

**Step 5: Run `make all`**

Run: `make all`
Expected: All tests pass.

**Step 6: Commit**

```bash
git add examples/barsoom.py tests/examples/test_barsoom.py
git commit -m "feat: integrate TUI into barsoom example, remove --verbose"
```

---

### Task 12: Integrate TUI into repo.py

**Files:**
- Modify: `examples/repo.py`
- Modify: `tests/unit/test_repo_script.py`

Replace the interactive loop in `repo.py` with `SheshaTUI`. Register `/analysis` and `/analyze` as custom commands. The setup/picker/update code stays.

**Step 1: Update test expectations**

In `tests/unit/test_repo_script.py`, update:
- Remove verbose-related tests
- Update help text expectations
- Add test that repo.py registers `/analysis` and `/analyze` commands

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_repo_script.py -v`
Expected: Some tests fail.

**Step 3: Update repo.py**

Key changes:
- Remove `--verbose` argument
- Remove `run_interactive_loop` function
- After setup, create `SheshaTUI` and register custom commands:
  ```python
  tui = SheshaTUI(project=project, project_name=project.project_id, analysis_context=analysis_context)

  def handle_analysis(args: str) -> None:
      analysis = shesha.get_analysis(project.project_id)
      if analysis is None:
          tui.query_one(OutputArea).add_system_message("No analysis. Use /analyze to generate.")
      else:
          tui.query_one(OutputArea).add_system_message(format_analysis_for_display(analysis))

  def handle_analyze(args: str) -> None:
      tui.query_one(OutputArea).add_system_message("Generating analysis...")
      try:
          shesha.generate_analysis(project.project_id)
          tui.query_one(OutputArea).add_system_message("Analysis complete. Use /analysis to view.")
      except Exception as e:
          tui.query_one(OutputArea).add_system_message(f"Error: {e}")

  tui.register_command("/analysis", handle_analysis, "Show codebase analysis")
  tui.register_command("/analyze", handle_analyze, "Generate/regenerate analysis")
  tui.run()
  ```
- Remove imports that are no longer needed

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_repo_script.py -v`
Expected: All pass.

**Step 5: Run `make all`**

Run: `make all`
Expected: All tests pass.

**Step 6: Commit**

```bash
git add examples/repo.py tests/unit/test_repo_script.py
git commit -m "feat: integrate TUI into repo example with /analysis and /analyze commands"
```

---

### Task 13: Clean up script_utils.py

**Files:**
- Modify: `examples/script_utils.py`
- Modify: `tests/unit/test_script_utils.py`

Remove functions that have been absorbed by the TUI. Keep only the pre-TUI utilities.

**Step 1: Update tests**

Remove test classes for absorbed functions:
- `TestThinkingSpinner`
- `TestFormatProgress`
- `TestFormatThoughtTime`
- `TestFormatStats`
- `TestFormatHistoryPrefix`
- `TestIsExitCommand`, `TestIsHelpCommand`, `TestIsWriteCommand`, `TestIsAnalysisCommand`, `TestIsRegenerateCommand`
- `TestParseWriteCommand`
- `TestShouldWarnHistorySize`

Keep tests for retained functions.

**Step 2: Run tests to verify state**

Run: `pytest tests/unit/test_script_utils.py -v`

**Step 3: Remove absorbed functions from script_utils.py**

Remove:
- `ThinkingSpinner` class
- `format_progress`
- `format_thought_time`
- `format_stats`
- `format_history_prefix`
- `is_exit_command`, `is_help_command`, `is_write_command`, `is_analysis_command`, `is_regenerate_command`
- `parse_write_command`
- `should_warn_history_size`
- `HISTORY_WARN_CHARS`, `HISTORY_WARN_EXCHANGES` constants

Keep:
- `install_urllib3_cleanup_hook`
- `format_analysis_for_display`
- `format_analysis_as_context`
- `format_verified_output`
- `format_session_transcript`
- `write_session`
- `generate_session_filename`

**Step 4: Run `make all`**

Run: `make all`
Expected: All tests pass.

**Step 5: Commit**

```bash
git add examples/script_utils.py tests/unit/test_script_utils.py
git commit -m "refactor: remove TUI-absorbed functions from script_utils"
```

---

### Task 14: Update CHANGELOG.md and pyproject.toml

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add changelog entries**

Under `## [Unreleased]`:

```markdown
### Added

- Interactive TUI (Text User Interface) for `barsoom.py` and `repo.py` examples, inspired by Claude Code's interface. Features: 3-pane layout (scrolling output, live info bar, input area), markdown rendering toggle, slash commands with auto-complete, input history, dark/light theme toggle, real-time progress display replacing `--verbose` flag. Install with `pip install shesha[tui]`.

### Changed

- Example commands now require `/` prefix (e.g., `/help`, `/write`, `/quit`) instead of bare words
- `--verbose` flag removed from `barsoom.py` and `repo.py` (info bar shows progress by default)

### Removed

- `ThinkingSpinner` and verbose formatting functions from `script_utils.py` (absorbed into TUI)
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: update changelog for TUI feature"
```

---

### Task 15: Final verification

**Step 1: Run full test suite**

Run: `make all`
Expected: All tests pass, no lint/type errors.

**Step 2: Manual smoke test (if Docker available)**

Run: `pip install -e ".[tui]" && python examples/barsoom.py`
Expected: TUI launches with 3-pane layout, `/help` works, `/quit` exits cleanly.

**Step 3: Verify no regressions**

Run: `pytest -v --tb=short`
Expected: All tests green.
