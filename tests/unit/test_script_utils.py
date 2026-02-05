"""Tests for script_utils shared utilities."""

import re
import sys
from pathlib import Path

import pytest

from shesha.rlm.trace import StepType, TokenUsage, Trace


class TestThinkingSpinner:
    """Tests for ThinkingSpinner class."""

    def test_start_sets_running(self) -> None:
        """Start should set _running to True and create thread."""
        from examples.script_utils import ThinkingSpinner

        spinner = ThinkingSpinner()
        assert not spinner._running
        assert spinner._thread is None

        spinner.start()
        assert spinner._running
        assert spinner._thread is not None
        assert spinner._thread.is_alive()

        spinner.stop()

    def test_stop_clears_running(self) -> None:
        """Stop should set _running to False."""
        from examples.script_utils import ThinkingSpinner

        spinner = ThinkingSpinner()
        spinner.start()
        spinner.stop()

        assert not spinner._running


class TestFormatProgress:
    """Tests for format_progress function."""

    def test_format_with_elapsed(self) -> None:
        """Format progress with elapsed time."""
        from examples.script_utils import format_progress

        result = format_progress(StepType.CODE_GENERATED, 0, "code", elapsed_seconds=1.5)
        assert "[1.5s]" in result
        assert "[Iteration 1]" in result
        assert "Generating code" in result

    def test_format_without_elapsed(self) -> None:
        """Format progress without elapsed time."""
        from examples.script_utils import format_progress

        result = format_progress(StepType.FINAL_ANSWER, 2, "answer")
        assert "[Iteration 3]" in result
        assert "Final answer" in result


class TestFormatThoughtTime:
    """Tests for format_thought_time function."""

    def test_singular_second(self) -> None:
        """One second should use singular form."""
        from examples.script_utils import format_thought_time

        result = format_thought_time(1.2)
        assert result == "[Thought for 1 second]"

    def test_plural_seconds(self) -> None:
        """Multiple seconds should use plural form."""
        from examples.script_utils import format_thought_time

        result = format_thought_time(5.7)
        assert result == "[Thought for 6 seconds]"


class TestFormatStats:
    """Tests for format_stats function."""

    def test_format_stats_output(self) -> None:
        """Format stats should include all metrics."""
        from examples.script_utils import format_stats

        token_usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
        trace = Trace(steps=[])

        result = format_stats(2.5, token_usage, trace)
        assert "Execution time: 2.50s" in result
        assert "Tokens: 150" in result
        assert "prompt: 100" in result
        assert "completion: 50" in result
        assert "Trace steps: 0" in result


class TestFormatHistoryPrefix:
    """Tests for format_history_prefix function."""

    def test_empty_history(self) -> None:
        """Empty history returns empty string."""
        from examples.script_utils import format_history_prefix

        assert format_history_prefix([]) == ""

    def test_single_exchange(self) -> None:
        """Single exchange formats correctly."""
        from examples.script_utils import format_history_prefix

        history = [("What is X?", "X is Y.")]
        result = format_history_prefix(history)
        assert "Previous conversation:" in result
        assert "Q1: What is X?" in result
        assert "A1: X is Y." in result
        assert "Current question:" in result


class TestIsExitCommand:
    """Tests for is_exit_command function."""

    def test_quit_is_exit(self) -> None:
        """'quit' should be recognized as exit."""
        from examples.script_utils import is_exit_command

        assert is_exit_command("quit")
        assert is_exit_command("QUIT")
        assert is_exit_command("Quit")

    def test_exit_is_exit(self) -> None:
        """'exit' should be recognized as exit."""
        from examples.script_utils import is_exit_command

        assert is_exit_command("exit")
        assert is_exit_command("EXIT")

    def test_other_not_exit(self) -> None:
        """Other inputs should not be exit commands."""
        from examples.script_utils import is_exit_command

        assert not is_exit_command("hello")
        assert not is_exit_command("question")


class TestIsHelpCommand:
    """Tests for is_help_command function."""

    def test_help_is_help(self) -> None:
        """'help' should be recognized as help command."""
        from examples.script_utils import is_help_command

        assert is_help_command("help")
        assert is_help_command("HELP")
        assert is_help_command("Help")

    def test_question_mark_is_help(self) -> None:
        """'?' should be recognized as help command."""
        from examples.script_utils import is_help_command

        assert is_help_command("?")

    def test_other_not_help(self) -> None:
        """Other inputs should not be help commands."""
        from examples.script_utils import is_help_command

        assert not is_help_command("hello")
        assert not is_help_command("help me")
        assert not is_help_command("??")


class TestShouldWarnHistorySize:
    """Tests for should_warn_history_size function."""

    def test_small_history_no_warning(self) -> None:
        """Small history should not trigger warning."""
        from examples.script_utils import should_warn_history_size

        history = [("q", "a") for _ in range(5)]
        assert not should_warn_history_size(history)

    def test_many_exchanges_warns(self) -> None:
        """10+ exchanges should trigger warning."""
        from examples.script_utils import should_warn_history_size

        history = [("q", "a") for _ in range(10)]
        assert should_warn_history_size(history)

    def test_large_chars_warns(self) -> None:
        """50k+ chars should trigger warning."""
        from examples.script_utils import should_warn_history_size

        # Create history with large content (50k+ chars total)
        large_text = "x" * 50000
        history = [("q", large_text)]
        assert should_warn_history_size(history)


class TestInstallUrllib3CleanupHook:
    """Tests for install_urllib3_cleanup_hook function."""

    def test_hook_installed(self) -> None:
        """Hook should be installed on sys.unraisablehook."""
        from examples.script_utils import install_urllib3_cleanup_hook

        original = sys.unraisablehook
        install_urllib3_cleanup_hook()

        # Hook should be changed
        assert sys.unraisablehook != original

        # Restore original
        sys.unraisablehook = original


class TestIsWriteCommand:
    """Tests for is_write_command function."""

    def test_write_alone_is_write_command(self) -> None:
        """'write' by itself should be recognized."""
        from examples.script_utils import is_write_command

        assert is_write_command("write")
        assert is_write_command("WRITE")
        assert is_write_command("Write")

    def test_write_with_filename_is_write_command(self) -> None:
        """'write <filename>' should be recognized."""
        from examples.script_utils import is_write_command

        assert is_write_command("write myfile.md")
        assert is_write_command("write path/to/file.md")
        assert is_write_command("WRITE session.md")

    def test_other_not_write_command(self) -> None:
        """Other inputs should not be write commands."""
        from examples.script_utils import is_write_command

        assert not is_write_command("hello")
        assert not is_write_command("writeup")
        assert not is_write_command("rewrite")
        assert not is_write_command("")

    def test_write_with_special_whitespace(self) -> None:
        """Write command should handle tabs and unicode spaces."""
        from examples.script_utils import is_write_command

        # Tab between write and filename
        assert is_write_command("write\ttest.md")
        # Non-breaking space (U+00A0)
        assert is_write_command("write\u00a0test.md")
        # Em space (U+2003)
        assert is_write_command("write\u2003test.md")


class TestParseWriteCommand:
    """Tests for parse_write_command function."""

    def test_write_alone_returns_none(self) -> None:
        """'write' by itself returns None (auto-generate filename)."""
        from examples.script_utils import parse_write_command

        assert parse_write_command("write") is None
        assert parse_write_command("WRITE") is None

    def test_write_with_filename_returns_filename(self) -> None:
        """'write <filename>' returns the filename."""
        from examples.script_utils import parse_write_command

        assert parse_write_command("write myfile.md") == "myfile.md"
        assert parse_write_command("write path/to/file.md") == "path/to/file.md"

    def test_strips_whitespace_from_filename(self) -> None:
        """Whitespace around filename should be stripped."""
        from examples.script_utils import parse_write_command

        assert parse_write_command("write   myfile.md   ") == "myfile.md"
        assert parse_write_command("WRITE    session.md") == "session.md"

    def test_adds_md_extension_if_missing(self) -> None:
        """Add .md extension if not present."""
        from examples.script_utils import parse_write_command

        assert parse_write_command("write myfile") == "myfile.md"
        assert parse_write_command("write path/to/file") == "path/to/file.md"

    def test_preserves_md_extension(self) -> None:
        """Don't double-add .md extension."""
        from examples.script_utils import parse_write_command

        assert parse_write_command("write myfile.md") == "myfile.md"
        assert parse_write_command("write FILE.MD") == "FILE.MD"


class TestGenerateSessionFilename:
    """Tests for generate_session_filename function."""

    def test_filename_format(self) -> None:
        """Filename should match session-YYYY-MM-DD-HHMMSS.md pattern."""
        from examples.script_utils import generate_session_filename

        filename = generate_session_filename()
        pattern = r"^session-\d{4}-\d{2}-\d{2}-\d{6}\.md$"
        assert re.match(pattern, filename), f"'{filename}' doesn't match expected pattern"

    def test_filename_has_md_extension(self) -> None:
        """Filename should end with .md."""
        from examples.script_utils import generate_session_filename

        filename = generate_session_filename()
        assert filename.endswith(".md")

    def test_filename_starts_with_session(self) -> None:
        """Filename should start with 'session-'."""
        from examples.script_utils import generate_session_filename

        filename = generate_session_filename()
        assert filename.startswith("session-")


class TestFormatSessionTranscript:
    """Tests for format_session_transcript function."""

    def test_empty_history(self) -> None:
        """Empty history should still produce valid markdown with header."""
        from examples.script_utils import format_session_transcript

        result = format_session_transcript([], "test-project")
        assert "# Session Transcript" in result
        assert "**Project:** test-project" in result
        assert "**Exchanges:** 0" in result

    def test_single_exchange(self) -> None:
        """Single exchange should be formatted correctly."""
        from examples.script_utils import format_session_transcript

        history = [("What is X?", "X is a variable.")]
        result = format_session_transcript(history, "my-project")

        assert "# Session Transcript" in result
        assert "**Project:** my-project" in result
        assert "**Exchanges:** 1" in result
        assert "**User:** What is X?" in result
        assert "X is a variable." in result

    def test_multiple_exchanges(self) -> None:
        """Multiple exchanges should be separated by horizontal rules."""
        from examples.script_utils import format_session_transcript

        history = [("Q1?", "A1."), ("Q2?", "A2.")]
        result = format_session_transcript(history, "project")

        assert "**Exchanges:** 2" in result
        assert "**User:** Q1?" in result
        assert "A1." in result
        assert "**User:** Q2?" in result
        assert "A2." in result
        # Should have separators between exchanges
        assert result.count("---") >= 2

    def test_includes_date(self) -> None:
        """Transcript should include a date field."""
        from examples.script_utils import format_session_transcript

        result = format_session_transcript([], "project")
        assert "**Date:**" in result


class TestWriteSession:
    """Tests for write_session function."""

    def test_writes_file_to_specified_path(self, tmp_path: Path) -> None:
        """Should write transcript to specified filename."""
        from examples.script_utils import write_session

        history = [("Q?", "A.")]
        filepath = tmp_path / "test.md"

        result = write_session(history, "project", str(filepath))

        assert result == str(filepath)
        assert filepath.exists()
        content = filepath.read_text()
        assert "**User:** Q?" in content

    def test_auto_generates_filename(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should auto-generate filename when None provided."""
        from examples.script_utils import write_session

        # Change to tmp_path for the test
        monkeypatch.chdir(tmp_path)

        history = [("Q?", "A.")]
        result = write_session(history, "project", None)

        assert result.startswith("session-")
        assert result.endswith(".md")
        assert Path(result).exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create parent directories if they don't exist."""
        from examples.script_utils import write_session

        history = [("Q?", "A.")]
        filepath = tmp_path / "subdir" / "nested" / "test.md"

        write_session(history, "project", str(filepath))

        assert filepath.exists()

    def test_returns_path_written(self, tmp_path: Path) -> None:
        """Should return the path that was written to."""
        from examples.script_utils import write_session

        history = [("Q?", "A.")]
        filepath = tmp_path / "output.md"

        result = write_session(history, "project", str(filepath))

        assert result == str(filepath)
