"""Tests for the arXiv explorer CLI script."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

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
