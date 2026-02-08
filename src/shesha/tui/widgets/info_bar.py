"""Status info bar widget."""

from dataclasses import dataclass, field

from textual.widgets import Static


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
        """Set phase to Thinking with animated dots."""
        dots = int(elapsed * 3) % 3 + 1
        self._phase_line = f"[{elapsed:.1f}s] Thinking{'.' * dots}{' ' * (3 - dots)}"

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


class InfoBar(Static):
    """Textual widget displaying the info bar.

    Two-line status bar showing project info, token counts, and phase.
    """

    DEFAULT_CSS = """
    InfoBar {
        height: auto;
        padding: 0 1;
        border: solid $accent;
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
