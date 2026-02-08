"""Tests for main SheshaTUI app."""

from unittest.mock import MagicMock

from shesha.tui.app import SheshaTUI
from shesha.tui.widgets.completion_popup import CompletionPopup
from shesha.tui.widgets.info_bar import InfoBar
from shesha.tui.widgets.input_area import InputArea
from shesha.tui.widgets.output_area import OutputArea


class TestSheshaTUIComposition:
    """Tests for SheshaTUI app layout."""

    async def test_app_has_four_widgets(self) -> None:
        """App composes output area, info bar, completion popup, and input area."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            assert pilot.app.query_one(OutputArea)
            assert pilot.app.query_one(InfoBar)
            assert pilot.app.query_one(CompletionPopup)
            assert pilot.app.query_one(InputArea)

    async def test_builtin_commands_registered(self) -> None:
        """Built-in commands are registered on startup."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            commands = pilot.app._command_registry.list_commands()
            names = [name for name, _desc in commands]
            assert "/help" in names
            assert "/quit" in names
            assert "/write" in names
            assert "/markdown" in names
            assert "/theme" in names

    async def test_register_custom_command(self) -> None:
        """Custom commands can be registered before run."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        app.register_command("/custom", lambda args: None, "Custom command")
        async with app.run_test() as pilot:
            commands = pilot.app._command_registry.list_commands()
            names = [name for name, _desc in commands]
            assert "/custom" in names

    async def test_help_command_shows_output(self) -> None:
        """The /help command adds a message to the output area."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "/help"
            # First enter accepts the completion
            await pilot.press("enter")
            await pilot.pause()
            # Second enter submits the command
            await pilot.press("enter")
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            # Should have at least one system message with command list
            statics = output.query("Static")
            assert len(statics) > 0


class TestCompletionIntegration:
    """Tests for slash command auto-complete in SheshaTUI."""

    async def test_typing_slash_shows_completion_popup(self) -> None:
        """Typing '/' shows the completion popup with all commands."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            popup = pilot.app.query_one(CompletionPopup)
            # Initially hidden
            assert popup.is_visible is False
            # Type a slash
            input_area.text = "/"
            await pilot.pause()
            assert popup.is_visible is True
            assert input_area.completion_active is True

    async def test_completion_popup_filters_as_typing(self) -> None:
        """Popup filters to matching commands as user types."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            popup = pilot.app.query_one(CompletionPopup)
            # Type '/he' — only /help should match
            input_area.text = "/he"
            await pilot.pause()
            assert popup.is_visible is True
            assert popup.selected_value == "/help"

    async def test_completion_accept_fills_input(self) -> None:
        """Accepting a completion fills the input with the command."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            popup = pilot.app.query_one(CompletionPopup)
            # Show completions
            input_area.text = "/he"
            await pilot.pause()
            assert popup.selected_value == "/help"
            # Accept
            await pilot.press("enter")
            await pilot.pause()
            assert input_area.text == "/help "
            assert popup.is_visible is False
            assert input_area.completion_active is False

    async def test_completion_popup_hidden_for_non_slash_text(self) -> None:
        """Popup stays hidden for non-slash text."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            popup = pilot.app.query_one(CompletionPopup)
            input_area.text = "hello"
            await pilot.pause()
            assert popup.is_visible is False


class TestFocusToggle:
    """Tests for Tab focus toggling between InputArea and OutputArea."""

    async def test_tab_moves_focus_to_output_area(self) -> None:
        """Tab from InputArea moves focus to OutputArea."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            # InputArea has focus on startup
            assert pilot.app.query_one(InputArea).has_focus
            await pilot.press("tab")
            await pilot.pause()
            assert pilot.app.query_one(OutputArea).has_focus

    async def test_tab_moves_focus_back_to_input_area(self) -> None:
        """Tab from OutputArea moves focus back to InputArea."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            # Move to OutputArea first
            await pilot.press("tab")
            await pilot.pause()
            assert pilot.app.query_one(OutputArea).has_focus
            # Tab again goes back to InputArea
            await pilot.press("tab")
            await pilot.pause()
            assert pilot.app.query_one(InputArea).has_focus

    async def test_input_area_has_focus_on_startup(self) -> None:
        """InputArea has focus when app starts."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            assert pilot.app.query_one(InputArea).has_focus
