"""Tests for script_utils shared utilities."""


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
