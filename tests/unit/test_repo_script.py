"""Tests for repo.py script."""

from unittest.mock import MagicMock, patch

import pytest


class TestParseArgs:
    """Tests for parse_args function."""

    def test_no_args(self) -> None:
        """No args should work (for picker mode)."""
        from examples.repo import parse_args

        args = parse_args([])
        assert args.repo is None
        assert not args.update
        assert not args.verbose

    def test_repo_positional(self) -> None:
        """Repo URL should be captured as positional arg."""
        from examples.repo import parse_args

        args = parse_args(["https://github.com/user/repo"])
        assert args.repo == "https://github.com/user/repo"

    def test_local_path(self) -> None:
        """Local path should be captured."""
        from examples.repo import parse_args

        args = parse_args(["/path/to/repo"])
        assert args.repo == "/path/to/repo"

    def test_update_flag(self) -> None:
        """--update flag should be captured."""
        from examples.repo import parse_args

        args = parse_args(["https://github.com/user/repo", "--update"])
        assert args.update

    def test_verbose_flag(self) -> None:
        """--verbose flag should be captured."""
        from examples.repo import parse_args

        args = parse_args(["https://github.com/user/repo", "--verbose"])
        assert args.verbose


class TestShowPicker:
    """Tests for show_picker function."""

    def test_no_projects_returns_none(self) -> None:
        """No projects should prompt for URL, not show picker."""
        from examples.repo import show_picker

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = []

        # Should return None when no projects (prompt_for_repo handles that case)
        result = show_picker(mock_shesha)
        assert result is None

    def test_with_projects_shows_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Projects should be listed with numbers."""
        from examples.repo import show_picker

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["project-a", "project-b"]

        with patch("builtins.input", return_value="1"):
            value, is_existing = show_picker(mock_shesha)

        captured = capsys.readouterr()
        assert "1. project-a" in captured.out
        assert "2. project-b" in captured.out
        assert value == "project-a"
        assert is_existing is True

    def test_select_by_number(self) -> None:
        """Selecting a number returns corresponding project name with is_existing=True."""
        from examples.repo import show_picker

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["project-a", "project-b"]

        with patch("builtins.input", return_value="2"):
            value, is_existing = show_picker(mock_shesha)

        assert value == "project-b"
        assert is_existing is True

    def test_enter_new_url(self) -> None:
        """Entering a URL should return it with is_existing=False."""
        from examples.repo import show_picker

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["project-a"]

        with patch("builtins.input", return_value="https://github.com/new/repo"):
            value, is_existing = show_picker(mock_shesha)

        assert value == "https://github.com/new/repo"
        assert is_existing is False


class TestPromptForRepo:
    """Tests for prompt_for_repo function."""

    def test_returns_input(self) -> None:
        """Should return user input."""
        from examples.repo import prompt_for_repo

        with patch("builtins.input", return_value="https://github.com/user/repo"):
            result = prompt_for_repo()

        assert result == "https://github.com/user/repo"

    def test_strips_whitespace(self) -> None:
        """Should strip whitespace from input."""
        from examples.repo import prompt_for_repo

        with patch("builtins.input", return_value="  /path/to/repo  "):
            result = prompt_for_repo()

        assert result == "/path/to/repo"


class TestHandleUpdates:
    """Tests for handle_updates function."""

    def test_created_status_returns_same(self) -> None:
        """Status 'created' should return the same result."""
        from examples.repo import handle_updates

        mock_result = MagicMock()
        mock_result.status = "created"
        mock_result.files_ingested = 42

        result = handle_updates(mock_result, auto_update=False)
        assert result is mock_result

    def test_unchanged_status_returns_same(self) -> None:
        """Status 'unchanged' should return the same result."""
        from examples.repo import handle_updates

        mock_result = MagicMock()
        mock_result.status = "unchanged"

        result = handle_updates(mock_result, auto_update=False)
        assert result is mock_result

    def test_updates_available_auto_applies(self) -> None:
        """With --update flag, should auto-apply updates."""
        from examples.repo import handle_updates

        updated_result = MagicMock()
        mock_result = MagicMock()
        mock_result.status = "updates_available"
        mock_result.apply_updates.return_value = updated_result

        result = handle_updates(mock_result, auto_update=True)
        mock_result.apply_updates.assert_called_once()
        assert result is updated_result

    def test_updates_available_prompts_user_yes(self) -> None:
        """Without --update, should prompt and apply if 'y'."""
        from examples.repo import handle_updates

        updated_result = MagicMock()
        mock_result = MagicMock()
        mock_result.status = "updates_available"
        mock_result.project.project_id = "test-repo"
        mock_result.apply_updates.return_value = updated_result

        with patch("builtins.input", return_value="y"):
            result = handle_updates(mock_result, auto_update=False)

        mock_result.apply_updates.assert_called_once()
        assert result is updated_result

    def test_updates_available_prompts_user_no(self) -> None:
        """Without --update, should prompt and skip if 'n'."""
        from examples.repo import handle_updates

        mock_result = MagicMock()
        mock_result.status = "updates_available"
        mock_result.project.project_id = "test-repo"

        with patch("builtins.input", return_value="n"):
            result = handle_updates(mock_result, auto_update=False)

        mock_result.apply_updates.assert_not_called()
        assert result is mock_result


class TestRunInteractiveLoop:
    """Tests for run_interactive_loop function."""

    def test_quit_exits_loop(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Typing 'quit' should exit the loop."""
        from examples.repo import run_interactive_loop

        mock_project = MagicMock()

        with patch("builtins.input", return_value="quit"):
            run_interactive_loop(mock_project, verbose=False)

        captured = capsys.readouterr()
        assert "Goodbye!" in captured.out
        mock_project.query.assert_not_called()

    def test_exit_exits_loop(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Typing 'exit' should exit the loop."""
        from examples.repo import run_interactive_loop

        mock_project = MagicMock()

        with patch("builtins.input", return_value="exit"):
            run_interactive_loop(mock_project, verbose=False)

        captured = capsys.readouterr()
        assert "Goodbye!" in captured.out

    def test_empty_input_continues(self) -> None:
        """Empty input should continue loop without query."""
        from examples.repo import run_interactive_loop

        mock_project = MagicMock()

        # First empty, then quit
        with patch("builtins.input", side_effect=["", "quit"]):
            run_interactive_loop(mock_project, verbose=False)

        mock_project.query.assert_not_called()

    def test_query_is_made(self) -> None:
        """Questions should trigger project.query."""
        from examples.repo import run_interactive_loop

        mock_result = MagicMock()
        mock_result.answer = "The answer is 42"
        mock_result.execution_time = 1.5
        mock_result.token_usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        mock_result.trace = MagicMock(steps=[])

        mock_project = MagicMock()
        mock_project.query.return_value = mock_result

        with patch("builtins.input", side_effect=["What is X?", "quit"]):
            run_interactive_loop(mock_project, verbose=False)

        mock_project.query.assert_called_once()


class TestMain:
    """Tests for main function."""

    def test_no_api_key_exits(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Missing API key should print error and exit."""
        import os
        import sys

        from examples.repo import main

        # Mock sys.argv so parse_args doesn't see pytest's args
        with patch.object(sys, "argv", ["repo.py"]):
            with patch.dict(os.environ, {}, clear=True):
                with pytest.raises(SystemExit) as exc_info:
                    main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "SHESHA_API_KEY" in captured.out

    def test_picker_existing_project_uses_get_project(self) -> None:
        """Selecting existing project via picker should use get_project."""
        import os
        import sys

        from examples.repo import main

        mock_project = MagicMock()
        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["existing-project"]
        mock_shesha.get_project.return_value = mock_project

        with patch.object(sys, "argv", ["repo.py"]):
            with patch.dict(os.environ, {"SHESHA_API_KEY": "test-key"}, clear=True):
                with patch("examples.repo.Shesha", return_value=mock_shesha):
                    with patch("examples.repo.SheshaConfig"):
                        with patch("builtins.input", side_effect=["1", "quit"]):
                            main()

        # Should use get_project for existing project, NOT create_project_from_repo
        mock_shesha.get_project.assert_called_once_with("existing-project")
        mock_shesha.create_project_from_repo.assert_not_called()

    def test_picker_new_url_uses_create_project_from_repo(self) -> None:
        """Entering new URL via picker should use create_project_from_repo."""
        import os
        import sys

        from examples.repo import main

        mock_result = MagicMock()
        mock_result.status = "created"
        mock_result.files_ingested = 10
        mock_result.project = MagicMock()

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["existing-project"]
        mock_shesha.create_project_from_repo.return_value = mock_result

        with patch.object(sys, "argv", ["repo.py"]):
            with patch.dict(os.environ, {"SHESHA_API_KEY": "test-key"}, clear=True):
                with patch("examples.repo.Shesha", return_value=mock_shesha):
                    with patch("examples.repo.SheshaConfig"):
                        with patch(
                            "builtins.input",
                            side_effect=["https://github.com/new/repo", "quit"],
                        ):
                            main()

        # Should use create_project_from_repo for new URL, NOT get_project
        mock_shesha.create_project_from_repo.assert_called_once_with("https://github.com/new/repo")
        mock_shesha.get_project.assert_not_called()
