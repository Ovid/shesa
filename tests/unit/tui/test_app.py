"""Tests for main SheshaTUI app."""

from unittest.mock import MagicMock

from shesha.tui.app import SheshaTUI
from shesha.tui.widgets.info_bar import InfoBar
from shesha.tui.widgets.input_area import InputArea
from shesha.tui.widgets.output_area import OutputArea


class TestSheshaTUIComposition:
    """Tests for SheshaTUI app layout."""

    async def test_app_has_three_widgets(self) -> None:
        """App composes output area, info bar, and input area."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            assert pilot.app.query_one(OutputArea)
            assert pilot.app.query_one(InfoBar)
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
            await pilot.press("enter")
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            # Should have at least one system message with command list
            statics = output.query("Static")
            assert len(statics) > 0
