"""Tests for multi_repo example script."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add examples to path for import
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "examples"))


def test_multi_repo_script_importable():
    """multi_repo.py can be imported."""
    import multi_repo

    assert hasattr(multi_repo, "main")


def test_multi_repo_has_parse_args():
    """multi_repo.py has argument parser."""
    import multi_repo

    assert hasattr(multi_repo, "parse_args")


class TestParseArgs:
    """Tests for parse_args function."""

    def test_repos_optional(self) -> None:
        """No args should work (for picker mode)."""
        from multi_repo import parse_args

        args = parse_args([])
        assert args.repos == []
        assert args.prd is None

    def test_repos_positional(self) -> None:
        """Repo URLs captured as positional args."""
        from multi_repo import parse_args

        args = parse_args(["https://github.com/org/a", "https://github.com/org/b"])
        assert args.repos == ["https://github.com/org/a", "https://github.com/org/b"]

    def test_prd_flag(self) -> None:
        """--prd flag captures file path."""
        from multi_repo import parse_args

        args = parse_args(["--prd", "spec.md"])
        assert args.prd == "spec.md"

    def test_prd_with_repos(self) -> None:
        """--prd works together with repos."""
        from multi_repo import parse_args

        args = parse_args(["repo1", "repo2", "--prd", "spec.md"])
        assert args.repos == ["repo1", "repo2"]
        assert args.prd == "spec.md"

    def test_verbose_flag(self) -> None:
        """--verbose flag should be captured."""
        from multi_repo import parse_args

        args = parse_args(["--verbose"])
        assert args.verbose


class TestReadPrd:
    """Tests for PRD reading logic."""

    def test_read_prd_from_file(self, tmp_path: Path) -> None:
        """--prd reads content from file."""
        from multi_repo import read_prd

        prd_file = tmp_path / "spec.md"
        prd_file.write_text("# Requirements\n\nDo the thing.")
        result = read_prd(str(prd_file))
        assert result == "# Requirements\n\nDo the thing."

    def test_read_prd_file_not_found(self) -> None:
        """--prd with non-existent file raises SystemExit."""
        from multi_repo import read_prd

        with pytest.raises(SystemExit):
            read_prd("/nonexistent/path.md")

    def test_read_prd_none_falls_back_to_stdin(self) -> None:
        """No --prd prompts for stdin input."""
        from multi_repo import read_prd

        with patch("multi_repo.read_multiline_input", return_value="PRD from stdin"):
            result = read_prd(None)
        assert result == "PRD from stdin"
