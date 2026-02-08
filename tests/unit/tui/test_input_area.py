"""Tests for input area widget."""

from textual.app import App, ComposeResult

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
        """Trailing backslash continuation markers are stripped from submitted text."""
        async with InputAreaApp().run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            # Simulate multiline text with trailing backslash
            input_area.text = "line one \\\nline two"
            await pilot.press("enter")
            assert "line one" in pilot.app.submitted_texts[0]
            assert "\\" not in pilot.app.submitted_texts[0]
