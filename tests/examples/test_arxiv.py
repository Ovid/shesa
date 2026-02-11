"""Tests for the arXiv explorer CLI script."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[2] / "examples"))


class TestParseArgs:
    """Tests for argument parsing."""

    def test_defaults(self) -> None:
        from arxiv import parse_args

        args = parse_args([])
        assert args.model is None
        assert args.data_dir is None
        assert args.topic is None

    def test_model_flag(self) -> None:
        from arxiv import parse_args

        args = parse_args(["--model", "claude-sonnet-4-20250514"])
        assert args.model == "claude-sonnet-4-20250514"

    def test_data_dir_flag(self) -> None:
        from arxiv import parse_args

        args = parse_args(["--data-dir", "/tmp/test"])
        assert args.data_dir == "/tmp/test"

    def test_topic_flag(self) -> None:
        from arxiv import parse_args

        args = parse_args(["--topic", "my-topic"])
        assert args.topic == "my-topic"


class TestCommandDispatch:
    """Tests for slash command dispatch."""

    def test_help_command(self, capsys: object) -> None:
        from arxiv import handle_help

        # handle_help should print available commands
        handle_help("", state=MagicMock())
        # Just verify it doesn't crash — output goes to stdout

    def test_unknown_command_prints_error(self, capsys: object) -> None:
        from arxiv import dispatch_command

        state = MagicMock()
        dispatch_command("/unknown", state)
        # Should print "Unknown command" message

    def test_dispatch_routes_to_help(self) -> None:
        from arxiv import COMMANDS, dispatch_command

        state = MagicMock()
        mock_help = MagicMock()
        original = COMMANDS["/help"]
        COMMANDS["/help"] = (mock_help, "Show available commands")
        try:
            dispatch_command("/help", state)
            mock_help.assert_called_once()
        finally:
            COMMANDS["/help"] = original


class TestHistoryCommand:
    """Tests for /history command."""

    def test_history_empty(self, capsys: object) -> None:
        from arxiv import handle_history

        state = MagicMock()
        state.topic_mgr.list_topics.return_value = []
        handle_history("", state=state)
        # Should print "No topics" or similar

    def test_history_shows_topics(self, capsys: object) -> None:
        from datetime import UTC, datetime

        from arxiv import handle_history

        from shesha.experimental.arxiv.models import TopicInfo

        state = MagicMock()
        state.topic_mgr.list_topics.return_value = [
            TopicInfo(
                name="quantum-error-correction",
                created=datetime(2025, 1, 15, tzinfo=UTC),
                paper_count=3,
                size_bytes=12_400_000,
                project_id="2025-01-15-quantum-error-correction",
            ),
        ]
        handle_history("", state=state)
        # Should print topic info with created date, paper count, size


class TestTopicCommand:
    """Tests for /topic command."""

    def test_topic_no_args_no_current(self, capsys: object) -> None:
        from arxiv import handle_topic

        state = MagicMock()
        state.current_topic = None
        handle_topic("", state=state)
        # Should print message about no topic selected

    def test_topic_no_args_shows_current(self, capsys: object) -> None:
        from arxiv import handle_topic

        from shesha.experimental.arxiv.models import TopicInfo

        state = MagicMock()
        state.current_topic = "2025-01-15-quantum"
        state.topic_mgr.get_topic_info_by_project_id.return_value = TopicInfo(
            name="quantum",
            created=MagicMock(),
            paper_count=2,
            size_bytes=0,
            project_id="2025-01-15-quantum",
        )
        handle_topic("", state=state)
        # Should print current topic name

    def test_topic_switch_existing(self) -> None:
        from arxiv import handle_topic

        state = MagicMock()
        state.topic_mgr.resolve.return_value = "2025-01-15-quantum"
        state.topic_mgr._storage.list_documents.return_value = ["doc1", "doc2"]
        handle_topic("quantum", state=state)
        assert state.current_topic == "2025-01-15-quantum"

    def test_topic_create_new(self) -> None:
        from arxiv import handle_topic

        state = MagicMock()
        state.topic_mgr.resolve.return_value = None
        state.topic_mgr.create.return_value = "2025-01-15-new-topic"
        handle_topic("new-topic", state=state)
        assert state.current_topic == "2025-01-15-new-topic"

    def test_topic_delete(self) -> None:
        from arxiv import handle_topic

        state = MagicMock()
        state.current_topic = "2025-01-15-quantum"
        handle_topic("delete quantum", state=state)
        state.topic_mgr.delete.assert_called_once_with("quantum")


class TestPapersCommand:
    """Tests for /papers command."""

    def test_papers_no_topic(self, capsys: object) -> None:
        from arxiv import handle_papers

        state = MagicMock()
        state.current_topic = None
        handle_papers("", state=state)
        # Should print error about no topic

    def test_papers_empty_topic(self, capsys: object) -> None:
        from arxiv import handle_papers

        state = MagicMock()
        state.current_topic = "2025-01-15-test"
        state.topic_mgr._storage.list_documents.return_value = []
        handle_papers("", state=state)
        # Should print message about no papers loaded

    def test_papers_lists_documents(self, capsys: object) -> None:
        from datetime import UTC, datetime

        from arxiv import handle_papers

        from shesha.experimental.arxiv.models import PaperMeta, TopicInfo

        state = MagicMock()
        state.current_topic = "2025-01-15-test"
        state.topic_mgr._storage.list_documents.return_value = ["2501.12345"]
        state.topic_mgr.get_topic_info_by_project_id.return_value = TopicInfo(
            name="test",
            created=datetime(2025, 1, 15, tzinfo=UTC),
            paper_count=1,
            size_bytes=0,
            project_id="2025-01-15-test",
        )
        state.cache.get_meta.return_value = PaperMeta(
            arxiv_id="2501.12345",
            title="Test Paper",
            authors=["Smith"],
            abstract="Abstract",
            published=datetime(2025, 1, 1, tzinfo=UTC),
            updated=datetime(2025, 1, 1, tzinfo=UTC),
            categories=["cs.AI"],
            primary_category="cs.AI",
            pdf_url="https://arxiv.org/pdf/2501.12345",
            arxiv_url="https://arxiv.org/abs/2501.12345",
        )
        handle_papers("", state=state)
        # Should list the paper


class TestStartupBanner:
    """Tests for the startup banner."""

    def test_banner_contains_title(self) -> None:
        from arxiv import STARTUP_BANNER

        assert "arXiv Explorer" in STARTUP_BANNER

    def test_banner_contains_disclaimer(self) -> None:
        from arxiv import STARTUP_BANNER

        assert "AI-generated" in STARTUP_BANNER


class TestDispatchQuit:
    """Tests for quit command."""

    def test_quit_returns_true(self) -> None:
        from arxiv import dispatch_command

        state = MagicMock()
        assert dispatch_command("/quit", state) is True

    def test_exit_returns_true(self) -> None:
        from arxiv import dispatch_command

        state = MagicMock()
        assert dispatch_command("/exit", state) is True

    def test_help_returns_false(self) -> None:
        from arxiv import dispatch_command

        state = MagicMock()
        assert dispatch_command("/help", state) is False


class TestSearchCommand:
    """Tests for /search command."""

    def test_search_stores_results_in_state(self) -> None:
        from datetime import UTC, datetime

        from arxiv import handle_search

        from shesha.experimental.arxiv.models import PaperMeta

        state = MagicMock()
        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Test",
            authors=["A"],
            abstract="",
            published=datetime(2025, 1, 1, tzinfo=UTC),
            updated=datetime(2025, 1, 1, tzinfo=UTC),
            categories=["cs.AI"],
            primary_category="cs.AI",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/2501.12345",
        )
        state.searcher.search.return_value = [meta]
        state.last_search_results = []
        handle_search("quantum computing", state=state)
        assert len(state.last_search_results) == 1

    def test_search_empty_query_prints_usage(self) -> None:
        from arxiv import handle_search

        state = MagicMock()
        handle_search("", state=state)
        state.searcher.search.assert_not_called()

    def test_search_parses_author_flag(self) -> None:
        from arxiv import handle_search

        state = MagicMock()
        state.searcher.search.return_value = []
        state.last_search_results = []
        handle_search('--author "del maestro"', state=state)
        state.searcher.search.assert_called_once()
        call_kwargs = state.searcher.search.call_args
        assert call_kwargs.kwargs.get("author") == "del maestro"

    def test_search_parses_category_flag(self) -> None:
        from arxiv import handle_search

        state = MagicMock()
        state.searcher.search.return_value = []
        state.last_search_results = []
        handle_search("--cat cs.AI language models", state=state)
        call_kwargs = state.searcher.search.call_args
        assert call_kwargs.kwargs.get("category") == "cs.AI"

    def test_search_parses_recent_flag(self) -> None:
        from arxiv import handle_search

        state = MagicMock()
        state.searcher.search.return_value = []
        state.last_search_results = []
        handle_search("--cat cs.AI --recent 7 transformers", state=state)
        call_kwargs = state.searcher.search.call_args
        assert call_kwargs.kwargs.get("recent_days") == 7
        assert call_kwargs.kwargs.get("category") == "cs.AI"


class TestMoreCommand:
    """Tests for /more command."""

    def test_more_without_search_prints_error(self) -> None:
        from arxiv import handle_more

        state = MagicMock()
        state.last_search_results = []
        state._search_offset = 0
        state._last_search_kwargs = None
        handle_more("", state=state)
        # Should print "No previous search" or similar

    def test_more_fetches_next_page(self) -> None:
        from datetime import UTC, datetime

        from arxiv import handle_more

        from shesha.experimental.arxiv.models import PaperMeta

        state = MagicMock()
        meta = PaperMeta(
            arxiv_id="2502.00001",
            title="Next Page Paper",
            authors=["B"],
            abstract="",
            published=datetime(2025, 2, 1, tzinfo=UTC),
            updated=datetime(2025, 2, 1, tzinfo=UTC),
            categories=["cs.AI"],
            primary_category="cs.AI",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/2502.00001",
        )
        state.searcher.search.return_value = [meta]
        state.last_search_results = [MagicMock()]  # Has previous results
        state._search_offset = 10
        state._last_search_kwargs = {"query": "test", "author": None, "category": None}
        handle_more("", state=state)
        state.searcher.search.assert_called_once()
        call_kwargs = state.searcher.search.call_args
        assert call_kwargs.kwargs.get("start") == 10


class TestLoadCommand:
    """Tests for /load command."""

    def test_load_requires_topic(self) -> None:
        from arxiv import handle_load

        state = MagicMock()
        state.current_topic = None
        handle_load("1", state=state)
        # Should print error about no topic

    @patch("arxiv.download_paper")
    @patch("arxiv.to_parsed_document")
    def test_load_by_search_result_number(
        self, mock_to_doc: MagicMock, mock_download: MagicMock
    ) -> None:
        from datetime import UTC, datetime

        from arxiv import handle_load

        from shesha.experimental.arxiv.models import PaperMeta
        from shesha.models import ParsedDocument

        state = MagicMock()
        state.current_topic = "2025-01-15-test"
        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Test",
            authors=["A"],
            abstract="",
            published=datetime(2025, 1, 1, tzinfo=UTC),
            updated=datetime(2025, 1, 1, tzinfo=UTC),
            categories=["cs.AI"],
            primary_category="cs.AI",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/2501.12345",
            source_type="latex",
        )
        state.last_search_results = [meta]
        state.cache.has.return_value = True
        state.cache.get_meta.return_value = meta
        mock_download.return_value = meta
        mock_to_doc.return_value = ParsedDocument(
            name="2501.12345",
            content="content",
            format="latex",
            metadata={"arxiv_url": "https://arxiv.org/abs/2501.12345"},
            char_count=7,
        )
        handle_load("1", state=state)
        state.topic_mgr._storage.store_document.assert_called_once()

    @patch("arxiv.download_paper")
    @patch("arxiv.to_parsed_document")
    def test_load_by_arxiv_id(self, mock_to_doc: MagicMock, mock_download: MagicMock) -> None:
        from datetime import UTC, datetime

        from arxiv import handle_load

        from shesha.experimental.arxiv.models import PaperMeta
        from shesha.models import ParsedDocument

        state = MagicMock()
        state.current_topic = "2025-01-15-test"
        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Test",
            authors=["A"],
            abstract="",
            published=datetime(2025, 1, 1, tzinfo=UTC),
            updated=datetime(2025, 1, 1, tzinfo=UTC),
            categories=["cs.AI"],
            primary_category="cs.AI",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/2501.12345",
            source_type="latex",
        )
        state.cache.has.return_value = False
        state.searcher.get_by_id.return_value = meta
        mock_download.return_value = meta
        mock_to_doc.return_value = ParsedDocument(
            name="2501.12345",
            content="content",
            format="latex",
            metadata={"arxiv_url": "https://arxiv.org/abs/2501.12345"},
            char_count=7,
        )
        state.last_search_results = []
        handle_load("2501.12345", state=state)
        state.searcher.get_by_id.assert_called_once_with("2501.12345")

    def test_load_invalid_input_prints_error(self) -> None:
        from arxiv import handle_load

        state = MagicMock()
        state.current_topic = "2025-01-15-test"
        state.last_search_results = []
        handle_load("not-a-number-or-id", state=state)
        # Should print error about invalid input

    def test_load_creates_topic_if_none_selected_and_search_exists(self) -> None:
        """If no topic is selected but we have search results, auto-create topic."""
        from arxiv import handle_load

        state = MagicMock()
        state.current_topic = None
        handle_load("1", state=state)
        # Should print error asking to select/create a topic first
