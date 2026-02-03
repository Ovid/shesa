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
            result = show_picker(mock_shesha)

        captured = capsys.readouterr()
        assert "1. project-a" in captured.out
        assert "2. project-b" in captured.out
        assert result == "project-a"

    def test_select_by_number(self) -> None:
        """Selecting a number returns corresponding project name."""
        from examples.repo import show_picker

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["project-a", "project-b"]

        with patch("builtins.input", return_value="2"):
            result = show_picker(mock_shesha)

        assert result == "project-b"

    def test_enter_new_url(self) -> None:
        """Entering a URL should return it."""
        from examples.repo import show_picker

        mock_shesha = MagicMock()
        mock_shesha.list_projects.return_value = ["project-a"]

        with patch("builtins.input", return_value="https://github.com/new/repo"):
            result = show_picker(mock_shesha)

        assert result == "https://github.com/new/repo"


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
