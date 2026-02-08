"""Tests for the barsoom example."""

import sys

from examples.barsoom import BOOKS, parse_args


class TestModuleImportSideEffects:
    """Test that module import doesn't have global side effects."""

    def test_import_does_not_install_urllib3_hook(self) -> None:
        """Importing barsoom should not install the urllib3 cleanup hook."""
        # Check that the current hook is not the urllib3 suppression hook
        # (pytest may have its own hook installed, which is fine)
        hook_name = getattr(sys.unraisablehook, "__name__", "")
        assert "urllib3" not in hook_name.lower()
        assert "suppress" not in hook_name.lower()


class TestArgumentParsing:
    """Test CLI argument parsing."""

    def test_parse_args_default(self) -> None:
        """Default args have setup=False and no verbose flag."""
        args = parse_args([])
        assert args.setup is False

    def test_parse_args_setup_flag(self) -> None:
        """--setup flag sets setup=True."""
        args = parse_args(["--setup"])
        assert args.setup is True

    def test_parse_args_verify_default_none(self) -> None:
        """--verify defaults to None so config file settings are preserved."""
        args = parse_args([])
        assert args.verify is None

    def test_parse_args_verify_flag(self) -> None:
        """--verify flag sets verify=True."""
        args = parse_args(["--verify"])
        assert args.verify is True

    def test_parse_args_no_verbose_flag(self) -> None:
        """--verbose flag has been removed (TUI info bar replaces it)."""
        assert not hasattr(parse_args([]), "verbose")


class TestBooksMapping:
    """Test the BOOKS constant."""

    def test_books_has_seven_entries(self) -> None:
        """BOOKS maps 7 filenames to titles."""
        assert len(BOOKS) == 7

    def test_books_filenames_match_pattern(self) -> None:
        """All filenames follow barsoom-N.txt pattern."""
        for filename in BOOKS:
            assert filename.startswith("barsoom-")
            assert filename.endswith(".txt")

    def test_books_has_princess_of_mars(self) -> None:
        """First book is A Princess of Mars."""
        assert BOOKS["barsoom-1.txt"] == "A Princess of Mars"
