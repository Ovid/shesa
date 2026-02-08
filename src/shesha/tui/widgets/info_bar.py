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
