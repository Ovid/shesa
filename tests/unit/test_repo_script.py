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

    def test_exit_command_returns_empty(self) -> None:
        """Typing 'exit' should return empty string to trigger exit."""
        from examples.repo import show_picker

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["project-a"]

        with patch("builtins.input", return_value="exit"):
            value, is_existing = show_picker(mock_shesha)

        assert value == ""
        assert is_existing is False

    def test_quit_command_returns_empty(self) -> None:
        """Typing 'quit' should return empty string to trigger exit."""
        from examples.repo import show_picker

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["project-a"]

        with patch("builtins.input", return_value="quit"):
            value, is_existing = show_picker(mock_shesha)

        assert value == ""
        assert is_existing is False

    def test_invalid_input_reprompts(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Invalid input like 'asdf' should show error and reprompt."""
        from examples.repo import show_picker

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["project-a"]

        # First input is invalid, second is valid exit
        inputs = iter(["asdf", "exit"])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            value, is_existing = show_picker(mock_shesha)

        captured = capsys.readouterr()
        assert "Invalid input" in captured.out
        assert value == ""  # Exited on second input

    def test_accepts_https_url(self) -> None:
        """HTTPS URLs should be accepted."""
        from examples.repo import show_picker

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["project-a"]

        with patch("builtins.input", return_value="https://github.com/org/repo"):
            value, is_existing = show_picker(mock_shesha)

        assert value == "https://github.com/org/repo"
        assert is_existing is False

    def test_accepts_ssh_url(self) -> None:
        """SSH URLs should be accepted."""
        from examples.repo import show_picker

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["project-a"]

        with patch("builtins.input", return_value="git@github.com:org/repo.git"):
            value, is_existing = show_picker(mock_shesha)

        assert value == "git@github.com:org/repo.git"
        assert is_existing is False

    def test_accepts_absolute_path(self) -> None:
        """Absolute paths should be accepted."""
        from examples.repo import show_picker

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["project-a"]

        with patch("builtins.input", return_value="/path/to/repo"):
            value, is_existing = show_picker(mock_shesha)

        assert value == "/path/to/repo"
        assert is_existing is False

    def test_accepts_home_path(self) -> None:
        """Paths starting with ~ should be accepted."""
        from examples.repo import show_picker

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["project-a"]

        with patch("builtins.input", return_value="~/projects/repo"):
            value, is_existing = show_picker(mock_shesha)

        assert value == "~/projects/repo"
        assert is_existing is False

    def test_accepts_relative_path(self) -> None:
        """Paths starting with ./ or ../ should be accepted."""
        from examples.repo import show_picker

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["project-a"]

        with patch("builtins.input", return_value="./local-repo"):
            value, is_existing = show_picker(mock_shesha)

        assert value == "./local-repo"
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
            run_interactive_loop(mock_project, verbose=False, project_name="test-project")

        captured = capsys.readouterr()
        assert "Goodbye!" in captured.out
        mock_project.query.assert_not_called()

    def test_exit_exits_loop(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Typing 'exit' should exit the loop."""
        from examples.repo import run_interactive_loop

        mock_project = MagicMock()

        with patch("builtins.input", return_value="exit"):
            run_interactive_loop(mock_project, verbose=False, project_name="test-project")

        captured = capsys.readouterr()
        assert "Goodbye!" in captured.out

    def test_empty_input_continues(self) -> None:
        """Empty input should continue loop without query."""
        from examples.repo import run_interactive_loop

        mock_project = MagicMock()

        # First empty, then quit
        with patch("builtins.input", side_effect=["", "quit"]):
            run_interactive_loop(mock_project, verbose=False, project_name="test-project")

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
            run_interactive_loop(mock_project, verbose=False, project_name="test-project")

        mock_project.query.assert_called_once()

    def test_help_shows_help_text(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Typing 'help' should show help text without querying."""
        from examples.repo import run_interactive_loop

        mock_project = MagicMock()

        with patch("builtins.input", side_effect=["help", "quit"]):
            run_interactive_loop(mock_project, verbose=False, project_name="test-project")

        captured = capsys.readouterr()
        assert "Commands:" in captured.out
        assert "help, ?" in captured.out
        assert "write" in captured.out
        assert "quit, exit" in captured.out
        mock_project.query.assert_not_called()

    def test_question_mark_shows_help_text(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Typing '?' should show help text without querying."""
        from examples.repo import run_interactive_loop

        mock_project = MagicMock()

        with patch("builtins.input", side_effect=["?", "quit"]):
            run_interactive_loop(mock_project, verbose=False, project_name="test-project")

        captured = capsys.readouterr()
        assert "Commands:" in captured.out
        mock_project.query.assert_not_called()


class TestMain:
    """Tests for main function."""

    def test_docker_not_running_exits_cleanly(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Docker not running should print clean error and exit."""
        import os
        import sys

        from examples.repo import main

        with patch.object(sys, "argv", ["repo.py", "https://github.com/test/repo"]):
            with patch.dict(os.environ, {"SHESHA_API_KEY": "test-key"}, clear=True):
                with patch("examples.repo.SheshaConfig"):
                    with patch(
                        "examples.repo.Shesha",
                        side_effect=RuntimeError(
                            "Docker is not running. Please start Docker Desktop and try again."
                        ),
                    ):
                        with pytest.raises(SystemExit) as exc_info:
                            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Docker" in captured.out
        assert "not running" in captured.out
        # Should NOT have traceback
        assert "Traceback" not in captured.out

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

    def test_picker_existing_project_checks_for_updates(self) -> None:
        """Selecting existing project via picker should check for updates."""
        import os
        import sys

        from examples.repo import main

        mock_result = MagicMock()
        mock_result.status = "unchanged"
        mock_result.files_ingested = 10
        mock_result.project = MagicMock()

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["existing-project"]
        mock_shesha.check_repo_for_updates.return_value = mock_result

        with patch.object(sys, "argv", ["repo.py"]):
            with patch.dict(os.environ, {"SHESHA_API_KEY": "test-key"}, clear=True):
                with patch("examples.repo.Shesha", return_value=mock_shesha):
                    with patch("examples.repo.SheshaConfig"):
                        with patch("builtins.input", side_effect=["1", "quit"]):
                            main()

        # Should check for updates when loading existing project
        mock_shesha.check_repo_for_updates.assert_called_once_with("existing-project")

    def test_picker_existing_project_with_update_flag_applies_updates(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Selecting existing project with --update should auto-apply updates."""
        import os
        import sys

        from examples.repo import main

        # First result has updates available
        mock_result = MagicMock()
        mock_result.status = "updates_available"
        mock_result.files_ingested = 10
        mock_result.project = MagicMock()
        mock_result.project.project_id = "existing-project"

        # After applying updates
        updated_result = MagicMock()
        updated_result.status = "created"
        updated_result.files_ingested = 15
        updated_result.project = mock_result.project
        mock_result.apply_updates.return_value = updated_result

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["existing-project"]
        mock_shesha.check_repo_for_updates.return_value = mock_result

        with patch.object(sys, "argv", ["repo.py", "--update"]):
            with patch.dict(os.environ, {"SHESHA_API_KEY": "test-key"}, clear=True):
                with patch("examples.repo.Shesha", return_value=mock_shesha):
                    with patch("examples.repo.SheshaConfig"):
                        with patch("builtins.input", side_effect=["1", "quit"]):
                            main()

        # Should apply updates when --update flag is set
        mock_result.apply_updates.assert_called_once()
        captured = capsys.readouterr()
        assert "Applying updates" in captured.out

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

    def test_show_picker_shows_missing_marker(self, capsys: pytest.CaptureFixture[str]) -> None:
        """show_picker marks projects with missing local repos."""
        from examples.repo import show_picker
        from shesha import ProjectInfo

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["remote-repo", "missing-local"]
        mock_shesha.get_project_info.side_effect = [
            ProjectInfo("remote-repo", "https://github.com/org/repo", False, True),
            ProjectInfo("missing-local", "/old/path", True, False),
        ]

        with patch("builtins.input", return_value="1"):
            show_picker(mock_shesha)

        captured = capsys.readouterr()
        assert "missing-local (missing - /old/path)" in captured.out

    def test_show_picker_handles_delete_command(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """show_picker handles 'd<N>' delete commands."""
        from examples.repo import show_picker
        from shesha import ProjectInfo

        mock_shesha = MagicMock()
        # First call: show list with 2 items, user enters 'd1'
        # Second call: show list with 1 item, user enters '1'
        mock_shesha.list_projects.side_effect = [
            ["project-a", "project-b"],
            ["project-b"],
        ]
        mock_shesha.get_project_info.side_effect = [
            ProjectInfo("project-a", "https://github.com/org/a", False, True),
            ProjectInfo("project-b", "https://github.com/org/b", False, True),
            # After deletion:
            ProjectInfo("project-b", "https://github.com/org/b", False, True),
        ]

        inputs = iter(["d1", "y", "1"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        result = show_picker(mock_shesha)

        mock_shesha.delete_project.assert_called_once_with("project-a")
        assert result == ("project-b", True)
        captured = capsys.readouterr()
        assert "Deleted 'project-a'" in captured.out

    def test_show_picker_delete_with_confirmation_no(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """show_picker cancels delete when user says no."""
        from examples.repo import show_picker
        from shesha import ProjectInfo

        mock_shesha = MagicMock()
        mock_shesha.list_projects.side_effect = [
            ["project-a"],
            ["project-a"],
        ]
        mock_shesha.get_project_info.return_value = ProjectInfo(
            "project-a", "https://github.com/org/a", False, True
        )

        inputs = iter(["d1", "n", "1"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        result = show_picker(mock_shesha)

        mock_shesha.delete_project.assert_not_called()
        assert result == ("project-a", True)

    def test_show_picker_delete_local_project_shows_correct_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """show_picker shows correct confirmation message for local projects."""
        from examples.repo import show_picker
        from shesha import ProjectInfo

        mock_shesha = MagicMock()
        mock_shesha.list_projects.side_effect = [
            ["local-project"],
            [],
        ]
        mock_shesha.get_project_info.return_value = ProjectInfo(
            "local-project", "/path/to/local", True, True
        )

        # Track all input prompts
        prompts: list[str] = []

        def mock_input(prompt: str) -> str:
            prompts.append(prompt)
            if "d<N>" in prompt:
                return "d1"
            return "y"

        monkeypatch.setattr("builtins.input", mock_input)

        # After deletion, no projects remain so returns None
        show_picker(mock_shesha)

        # Local projects shouldn't mention "cloned repository"
        confirmation_prompt = prompts[1]  # Second prompt is the confirmation
        assert "indexed data" in confirmation_prompt
        assert "cloned repository" not in confirmation_prompt

    def test_show_picker_delete_remote_project_shows_correct_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """show_picker shows correct confirmation message for remote projects."""
        from examples.repo import show_picker
        from shesha import ProjectInfo

        mock_shesha = MagicMock()
        mock_shesha.list_projects.side_effect = [
            ["remote-project"],
            [],
        ]
        mock_shesha.get_project_info.return_value = ProjectInfo(
            "remote-project", "https://github.com/org/repo", False, True
        )

        # Track all input prompts
        prompts: list[str] = []

        def mock_input(prompt: str) -> str:
            prompts.append(prompt)
            if "d<N>" in prompt:
                return "d1"
            return "y"

        monkeypatch.setattr("builtins.input", mock_input)

        show_picker(mock_shesha)

        # Remote projects should mention "cloned repository"
        confirmation_prompt = prompts[1]  # Second prompt is the confirmation
        assert "cloned repository" in confirmation_prompt

    def test_non_git_local_path_exits_cleanly(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Non-git local path should print clean error and exit."""
        import os
        import sys

        from examples.repo import main
        from shesha.exceptions import RepoIngestError

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = []
        mock_shesha.create_project_from_repo.side_effect = RepoIngestError(
            "/path/to/non-git",
            RuntimeError("'/path/to/non-git' is not a git repository"),
        )

        with patch.object(sys, "argv", ["repo.py", "/path/to/non-git"]):
            with patch.dict(os.environ, {"SHESHA_API_KEY": "test-key"}, clear=True):
                with patch("examples.repo.Shesha", return_value=mock_shesha):
                    with patch("examples.repo.SheshaConfig"):
                        with pytest.raises(SystemExit) as exc_info:
                            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "not a git repository" in captured.out
        # Should NOT have traceback
        assert "Traceback" not in captured.out
