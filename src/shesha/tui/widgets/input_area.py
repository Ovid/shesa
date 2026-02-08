"""Input area widget with multiline support."""

import re

from textual import events
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

    async def _on_key(self, event: events.Key) -> None:
        """Handle key events."""
        if event.key == "enter":
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
        await super()._on_key(event)

    class QueryCancelled(Message):
        """Posted when user double-escapes to cancel a query."""
