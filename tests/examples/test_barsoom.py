"""Tests for the barsoom example."""

import sys

from examples.barsoom import BOOKS, parse_args
from examples.script_utils import (
    HISTORY_WARN_CHARS,
    HISTORY_WARN_EXCHANGES,
    ThinkingSpinner,
    format_history_prefix,
    format_progress,
    format_stats,
    format_thought_time,
    is_exit_command,
    should_warn_history_size,
)
from shesha.rlm.trace import StepType, TokenUsage, Trace


class TestModuleImportSideEffects:
    """Test that module import doesn't have global side effects."""

    def test_import_does_not_install_urllib3_hook(self) -> None:
        """Importing barsoom should not install the urllib3 cleanup hook."""
        # Check that the current hook is not the urllib3 suppression hook
        # (pytest may have its own hook installed, which is fine)
        hook_name = getattr(sys.unraisablehook, "__name__", "")
        assert "urllib3" not in hook_name.lower()
        assert "suppress" not in hook_name.lower()


class TestArgumentParsing:
    """Test CLI argument parsing."""

    def test_parse_args_default(self) -> None:
        """Default args have setup=False and verbose=False."""
        args = parse_args([])
        assert args.setup is False
        assert args.verbose is False

    def test_parse_args_setup_flag(self) -> None:
        """--setup flag sets setup=True."""
        args = parse_args(["--setup"])
        assert args.setup is True

    def test_parse_args_verbose_flag(self) -> None:
        """--verbose flag sets verbose=True."""
        args = parse_args(["--verbose"])
        assert args.verbose is True

    def test_parse_args_both_flags(self) -> None:
        """Both flags can be combined."""
        args = parse_args(["--setup", "--verbose"])
        assert args.setup is True
        assert args.verbose is True


class TestBooksMapping:
    """Test the BOOKS constant."""

    def test_books_has_seven_entries(self) -> None:
        """BOOKS maps 7 filenames to titles."""
        assert len(BOOKS) == 7

    def test_books_filenames_match_pattern(self) -> None:
        """All filenames follow barsoom-N.txt pattern."""
        for filename in BOOKS:
            assert filename.startswith("barsoom-")
            assert filename.endswith(".txt")

    def test_books_has_princess_of_mars(self) -> None:
        """First book is A Princess of Mars."""
        assert BOOKS["barsoom-1.txt"] == "A Princess of Mars"


class TestInputHandling:
    """Test user input handling."""

    def test_is_exit_command_quit(self) -> None:
        """'quit' is an exit command."""
        assert is_exit_command("quit") is True

    def test_is_exit_command_exit(self) -> None:
        """'exit' is an exit command."""
        assert is_exit_command("exit") is True

    def test_is_exit_command_case_insensitive(self) -> None:
        """Exit commands are case-insensitive."""
        assert is_exit_command("QUIT") is True
        assert is_exit_command("Exit") is True
        assert is_exit_command("QuIt") is True

    def test_is_exit_command_normal_input(self) -> None:
        """Normal questions are not exit commands."""
        assert is_exit_command("Who is Dejah Thoris?") is False
        assert is_exit_command("") is False
        assert is_exit_command("quitter") is False


class TestVerboseOutput:
    """Test verbose stats formatting."""

    def test_format_stats_includes_execution_time(self) -> None:
        """format_stats includes execution time in seconds."""
        token_usage = TokenUsage(prompt_tokens=1000, completion_tokens=500)
        trace = Trace()
        output = format_stats(execution_time=12.345, token_usage=token_usage, trace=trace)
        assert "12.35s" in output or "12.34s" in output

    def test_format_stats_includes_token_counts(self) -> None:
        """format_stats includes token breakdown."""
        token_usage = TokenUsage(prompt_tokens=3200, completion_tokens=1321)
        trace = Trace()
        output = format_stats(execution_time=1.0, token_usage=token_usage, trace=trace)
        assert "4521" in output  # total
        assert "3200" in output  # prompt
        assert "1321" in output  # completion

    def test_format_stats_includes_trace_steps(self) -> None:
        """format_stats includes trace step count."""
        token_usage = TokenUsage()
        trace = Trace()
        trace.add_step(StepType.CODE_GENERATED, "code", iteration=1)
        trace.add_step(StepType.CODE_OUTPUT, "output", iteration=1)
        trace.add_step(StepType.FINAL_ANSWER, "answer", iteration=1)
        output = format_stats(execution_time=1.0, token_usage=token_usage, trace=trace)
        assert "3" in output

    def test_format_stats_starts_with_separator(self) -> None:
        """format_stats starts with a separator line."""
        token_usage = TokenUsage()
        trace = Trace()
        output = format_stats(execution_time=1.0, token_usage=token_usage, trace=trace)
        assert output.startswith("---")


class TestThinkingSpinner:
    """Test the animated thinking spinner."""

    def test_spinner_starts_and_stops(self) -> None:
        """Spinner can be started and stopped without errors."""
        spinner = ThinkingSpinner()
        spinner.start()
        spinner.stop()
        # Should not raise - no sleep needed since we're testing lifecycle, not output

    def test_spinner_stop_clears_line(self, capsys) -> None:
        """Spinner.stop() clears the thinking message."""
        spinner = ThinkingSpinner()
        spinner.start()
        spinner.stop()
        # stop() always prints "\r" to clear the line, regardless of thread timing
        captured = capsys.readouterr()
        assert "\r" in captured.out


class TestProgressFormatting:
    """Test verbose progress formatting."""

    def test_format_progress_code_generated(self) -> None:
        """format_progress handles CODE_GENERATED step."""
        output = format_progress(StepType.CODE_GENERATED, iteration=0, content="code")
        assert "Iteration 1" in output or "iteration 1" in output.lower()
        assert "generating" in output.lower() or "code" in output.lower()

    def test_format_progress_code_output(self) -> None:
        """format_progress handles CODE_OUTPUT step."""
        output = format_progress(StepType.CODE_OUTPUT, iteration=0, content="output")
        assert "execut" in output.lower() or "output" in output.lower()

    def test_format_progress_subcall(self) -> None:
        """format_progress handles SUBCALL_REQUEST step."""
        output = format_progress(StepType.SUBCALL_REQUEST, iteration=0, content="query")
        assert "sub" in output.lower() or "llm" in output.lower()

    def test_format_progress_final(self) -> None:
        """format_progress handles FINAL_ANSWER step."""
        output = format_progress(StepType.FINAL_ANSWER, iteration=2, content="answer")
        assert "final" in output.lower() or "answer" in output.lower()

    def test_format_progress_shows_elapsed_time(self) -> None:
        """format_progress includes elapsed time when provided."""
        output = format_progress(
            StepType.CODE_GENERATED, iteration=0, content="code", elapsed_seconds=12.5
        )
        assert "12.5s" in output or "12.50s" in output

    def test_format_progress_without_elapsed_time(self) -> None:
        """format_progress works without elapsed time (backward compatible)."""
        output = format_progress(StepType.CODE_GENERATED, iteration=0, content="code")
        assert "[Iteration 1]" in output
        assert "s]" not in output.split("[Iteration")[0]  # No time before Iteration


class TestHistoryFormatting:
    """Test conversation history formatting."""

    def test_format_history_prefix_empty(self) -> None:
        """Empty history returns empty string."""
        result = format_history_prefix([])
        assert result == ""

    def test_format_history_prefix_single_exchange(self) -> None:
        """Single exchange formats correctly."""
        history = [("Who is Dejah Thoris?", "She is the Princess of Helium.", "")]
        result = format_history_prefix(history)

        assert "Previous conversation:" in result
        assert "Q1: Who is Dejah Thoris?" in result
        assert "A1: She is the Princess of Helium." in result
        assert "Current question:" in result

    def test_format_history_prefix_multiple_exchanges(self) -> None:
        """Multiple exchanges format with correct numbering."""
        history = [
            ("Question one?", "Answer one.", ""),
            ("Question two?", "Answer two.", ""),
            ("Question three?", "Answer three.", ""),
        ]
        result = format_history_prefix(history)

        assert "Q1: Question one?" in result
        assert "A1: Answer one." in result
        assert "Q2: Question two?" in result
        assert "A2: Answer two." in result
        assert "Q3: Question three?" in result
        assert "A3: Answer three." in result


class TestHistoryWarning:
    """Test conversation history size warnings."""

    def test_should_warn_at_exchange_limit(self) -> None:
        """Warn when exchange count reaches threshold."""
        # Just under limit - no warning
        history = [("q", "a", "") for _ in range(HISTORY_WARN_EXCHANGES - 1)]
        assert should_warn_history_size(history) is False

        # At limit - warn
        history.append(("q", "a", ""))
        assert should_warn_history_size(history) is True

    def test_should_warn_at_char_limit(self) -> None:
        """Warn when character count reaches threshold."""
        # Create history with large content but few exchanges
        large_answer = "x" * (HISTORY_WARN_CHARS - 100)
        history = [("short question", large_answer, "")]
        assert should_warn_history_size(history) is False

        # Add more to exceed limit
        history.append(("another", "x" * 200, ""))
        assert should_warn_history_size(history) is True

    def test_should_warn_empty_history(self) -> None:
        """Empty history should not warn."""
        assert should_warn_history_size([]) is False


class TestThoughtTimeFormatting:
    """Test elapsed thought time formatting."""

    def test_format_thought_time_integer_seconds(self) -> None:
        """Formats whole seconds without decimal."""
        result = format_thought_time(5.0)
        assert result == "[Thought for 5 seconds]"

    def test_format_thought_time_rounds_to_integer(self) -> None:
        """Rounds fractional seconds to nearest integer."""
        assert format_thought_time(5.4) == "[Thought for 5 seconds]"
        assert format_thought_time(5.6) == "[Thought for 6 seconds]"

    def test_format_thought_time_one_second(self) -> None:
        """Uses singular 'second' for 1 second."""
        result = format_thought_time(1.0)
        assert result == "[Thought for 1 second]"

    def test_format_thought_time_zero_seconds(self) -> None:
        """Handles zero seconds."""
        result = format_thought_time(0.4)
        assert result == "[Thought for 0 seconds]"


class TestWriteCommand:
    """Tests for write command in barsoom interactive loop."""

    def test_write_command_recognized(self) -> None:
        """Write command should not be treated as a query."""
        from examples.script_utils import is_write_command

        assert is_write_command("write")
        assert is_write_command("write session.md")
