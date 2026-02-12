"""Tests for the arXiv explorer CLI script."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[2] / "examples"))


class TestParseArgs:
    """Tests for argument parsing."""

    def test_defaults(self) -> None:
        from arxiv_explorer import parse_args

        args = parse_args([])
        assert args.model is None
        assert args.data_dir is None
        assert args.topic is None

    def test_model_flag(self) -> None:
        from arxiv_explorer import parse_args

        args = parse_args(["--model", "claude-sonnet-4-20250514"])
        assert args.model == "claude-sonnet-4-20250514"

    def test_data_dir_flag(self) -> None:
        from arxiv_explorer import parse_args

        args = parse_args(["--data-dir", "/tmp/test"])
        assert args.data_dir == "/tmp/test"

    def test_topic_flag(self) -> None:
        from arxiv_explorer import parse_args

        args = parse_args(["--topic", "my-topic"])
        assert args.topic == "my-topic"


class TestParseSearchFlags:
    """Tests for _parse_search_flags helper."""

    def test_no_flags_returns_query_unchanged(self) -> None:
        from arxiv_explorer import _parse_search_flags

        query, kwargs = _parse_search_flags("quantum computing")
        assert query == "quantum computing"
        assert kwargs == {}

    def test_author_flag_single_word(self) -> None:
        from arxiv_explorer import _parse_search_flags

        query, kwargs = _parse_search_flags("--author Smith transformers")
        assert kwargs["author"] == "Smith"
        assert "Smith" not in query
        assert "transformers" in query

    def test_author_flag_quoted(self) -> None:
        from arxiv_explorer import _parse_search_flags

        query, kwargs = _parse_search_flags('--author "del maestro" quantum')
        assert kwargs["author"] == "del maestro"
        assert "quantum" in query

    def test_category_flag(self) -> None:
        from arxiv_explorer import _parse_search_flags

        query, kwargs = _parse_search_flags("--cat cs.AI language models")
        assert kwargs["category"] == "cs.AI"
        assert "language models" in query

    def test_recent_flag(self) -> None:
        from arxiv_explorer import _parse_search_flags

        query, kwargs = _parse_search_flags("--recent 7 transformers")
        assert kwargs["recent_days"] == 7
        assert "transformers" in query

    def test_sort_flag(self) -> None:
        from arxiv_explorer import _parse_search_flags

        query, kwargs = _parse_search_flags("--sort date quantum")
        assert kwargs["sort_by"] == "date"
        assert "quantum" in query

    def test_multiple_flags(self) -> None:
        from arxiv_explorer import _parse_search_flags

        query, kwargs = _parse_search_flags("--cat cs.AI --recent 7 --sort date transformers")
        assert kwargs["category"] == "cs.AI"
        assert kwargs["recent_days"] == 7
        assert kwargs["sort_by"] == "date"
        assert "transformers" in query

    def test_empty_string(self) -> None:
        from arxiv_explorer import _parse_search_flags

        query, kwargs = _parse_search_flags("")
        assert query == ""
        assert kwargs == {}


class TestMainFunction:
    """Tests for the main() entry point."""

    @patch("sys.argv", ["arxiv"])
    @patch("arxiv_explorer.create_app")
    @patch("arxiv_explorer.TopicManager")
    @patch("arxiv_explorer.PaperCache")
    @patch("arxiv_explorer.ArxivSearcher")
    @patch("arxiv_explorer.Shesha")
    @patch("arxiv_explorer.SheshaConfig")
    @patch("arxiv_explorer.FilesystemStorage")
    def test_main_creates_app_and_runs(
        self,
        mock_storage: MagicMock,
        mock_config: MagicMock,
        mock_shesha: MagicMock,
        mock_searcher: MagicMock,
        mock_cache: MagicMock,
        mock_topic_mgr: MagicMock,
        mock_create_app: MagicMock,
    ) -> None:
        from arxiv_explorer import main

        mock_config.load.return_value = MagicMock(storage_path="/tmp/test", model="gpt-4o")
        mock_storage.return_value = MagicMock()
        mock_storage.return_value.list_projects.return_value = []
        mock_tui = MagicMock()
        mock_create_app.return_value = mock_tui
        main()
        mock_create_app.assert_called_once()
        mock_tui.run.assert_called_once()

    @patch("sys.argv", ["arxiv", "--topic", "quantum"])
    @patch("arxiv_explorer.create_app")
    @patch("arxiv_explorer.TopicManager")
    @patch("arxiv_explorer.PaperCache")
    @patch("arxiv_explorer.ArxivSearcher")
    @patch("arxiv_explorer.Shesha")
    @patch("arxiv_explorer.SheshaConfig")
    @patch("arxiv_explorer.FilesystemStorage")
    def test_main_topic_not_found_passes_warning(
        self,
        mock_storage: MagicMock,
        mock_config: MagicMock,
        mock_shesha: MagicMock,
        mock_searcher: MagicMock,
        mock_cache: MagicMock,
        mock_topic_mgr: MagicMock,
        mock_create_app: MagicMock,
    ) -> None:
        from arxiv_explorer import main

        mock_config.load.return_value = MagicMock(storage_path="/tmp/test", model="gpt-4o")
        mock_storage.return_value = MagicMock()
        mock_storage.return_value.list_projects.return_value = []
        mock_topic_mgr.return_value.resolve.return_value = None
        mock_tui = MagicMock()
        mock_create_app.return_value = mock_tui
        main()
        call_kwargs = mock_create_app.call_args
        assert "not found" in call_kwargs.kwargs.get("startup_warning", "")
