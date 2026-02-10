"""Tests for the repo example."""

from examples.repo import parse_args


class TestArgumentParsing:
    """Test CLI argument parsing."""

    def test_parse_args_no_repo(self) -> None:
        """Default args have no repo specified."""
        args = parse_args([])
        assert args.repo is None

    def test_parse_args_model_default_none(self) -> None:
        """--model defaults to None so env var is used."""
        args = parse_args([])
        assert args.model is None

    def test_parse_args_model_flag(self) -> None:
        """--model flag sets model name."""
        args = parse_args(["--model", "gpt-4o"])
        assert args.model == "gpt-4o"

    def test_parse_args_model_with_repo(self) -> None:
        """--model works alongside positional repo arg."""
        args = parse_args(["https://github.com/org/repo", "--model", "claude-sonnet-4-20250514"])
        assert args.repo == "https://github.com/org/repo"
        assert args.model == "claude-sonnet-4-20250514"
