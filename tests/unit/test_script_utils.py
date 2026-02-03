"""Tests for script_utils shared utilities."""

import sys

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
