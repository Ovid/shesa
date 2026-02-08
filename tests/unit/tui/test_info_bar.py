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
