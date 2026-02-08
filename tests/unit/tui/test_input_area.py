"""Tests for input area widget."""

from textual.app import App, ComposeResult

from shesha.tui.widgets.input_area import InputArea, InputSubmitted


class InputAreaApp(App[None]):
    """Minimal app for testing InputArea."""

    submitted_texts: list[str]
    completion_messages: list[object]
    history_messages: list[str]

    def __init__(self) -> None:
        super().__init__()
        self.submitted_texts = []
        self.completion_messages = []
        self.history_messages = []

    def compose(self) -> ComposeResult:
        yield InputArea()

    def on_input_submitted(self, event: InputSubmitted) -> None:
        self.submitted_texts.append(event.text)

    def on_input_area_completion_navigate(self, event: InputArea.CompletionNavigate) -> None:
        self.completion_messages.append(("navigate", event.direction))

    def on_input_area_completion_accept(self, event: InputArea.CompletionAccept) -> None:
        self.completion_messages.append(("accept",))

    def on_input_area_completion_dismiss(self, event: InputArea.CompletionDismiss) -> None:
        self.completion_messages.append(("dismiss",))

    def on_input_area_focus_toggle(self, event: InputArea.FocusToggle) -> None:
        self.completion_messages.append(("focus_toggle",))

    def on_input_area_history_navigate(self, event: InputArea.HistoryNavigate) -> None:
        self.history_messages.append(event.direction)


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

    async def test_tab_posts_accept_when_completion_active(self) -> None:
        """Tab posts CompletionAccept when completion is active."""
        async with InputAreaApp().run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.completion_active = True
            input_area.text = "/he"
            await pilot.press("tab")
            assert ("accept",) in pilot.app.completion_messages

    async def test_down_posts_navigate_next_when_completion_active(self) -> None:
        """Down arrow posts CompletionNavigate('next') when completion is active."""
        async with InputAreaApp().run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.completion_active = True
            input_area.text = "/he"
            await pilot.press("down")
            assert ("navigate", "next") in pilot.app.completion_messages

    async def test_up_posts_navigate_prev_when_completion_active(self) -> None:
        """Up arrow posts CompletionNavigate('prev') when completion is active."""
        async with InputAreaApp().run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.completion_active = True
            input_area.text = "/he"
            await pilot.press("up")
            assert ("navigate", "prev") in pilot.app.completion_messages

    async def test_enter_posts_accept_when_completion_active(self) -> None:
        """Enter posts CompletionAccept when completion is active."""
        async with InputAreaApp().run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.completion_active = True
            input_area.text = "/he"
            await pilot.press("enter")
            assert ("accept",) in pilot.app.completion_messages
            # Should NOT have submitted the text
            assert pilot.app.submitted_texts == []

    async def test_escape_posts_dismiss_when_completion_active(self) -> None:
        """Escape posts CompletionDismiss when completion is active."""
        async with InputAreaApp().run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.completion_active = True
            input_area.text = "/he"
            await pilot.press("escape")
            assert ("dismiss",) in pilot.app.completion_messages
            # Should NOT have cleared the text
            assert input_area.text == "/he"

    async def test_enter_submits_normally_when_completion_inactive(self) -> None:
        """Enter submits text normally when completion is not active."""
        async with InputAreaApp().run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "hello"
            await pilot.press("enter")
            assert pilot.app.submitted_texts == ["hello"]
            assert pilot.app.completion_messages == []

    async def test_tab_posts_focus_toggle_when_completion_inactive(self) -> None:
        """Tab posts FocusToggle when completion is not active."""
        async with InputAreaApp().run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.completion_active = False
            await pilot.press("tab")
            assert ("focus_toggle",) in pilot.app.completion_messages

    async def test_up_posts_history_prev_when_completion_inactive(self) -> None:
        """Up arrow posts HistoryNavigate('prev') when completion is not active."""
        async with InputAreaApp().run_test() as pilot:
            await pilot.press("up")
            assert "prev" in pilot.app.history_messages

    async def test_down_posts_history_next_when_completion_inactive(self) -> None:
        """Down arrow posts HistoryNavigate('next') when completion is not active."""
        async with InputAreaApp().run_test() as pilot:
            await pilot.press("down")
            assert "next" in pilot.app.history_messages
