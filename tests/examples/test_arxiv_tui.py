"""Tests for the arXiv explorer TUI."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure examples/ is importable
sys.path.insert(0, str(Path(__file__).parents[2] / "examples"))

from shesha.tui.widgets.info_bar import InfoBar
from shesha.tui.widgets.output_area import OutputArea


def _extract_output_text(output: OutputArea) -> str:
    """Extract all visible text from OutputArea, including Markdown content."""
    parts: list[str] = []
    for widget in output.walk_children():
        rendered = str(widget.render())
        # Skip Blank renderables from Markdown containers
        if "Blank" not in rendered:
            parts.append(rendered)
    return " ".join(parts)


def _make_state(*, current_topic: str | None = None) -> MagicMock:
    """Create a mock AppState for testing."""
    from arxiv_explorer import AppState

    state = MagicMock(spec=AppState)
    state.current_topic = current_topic
    state.shesha = MagicMock()
    state.topic_mgr = MagicMock()
    state.cache = MagicMock()
    state.searcher = MagicMock()
    state.last_search_results = []
    state._search_offset = 0
    state._last_search_kwargs = None
    return state


class TestTUIStartup:
    """Tests for create_app() and TUI startup."""

    async def test_create_app_returns_shesha_tui(self) -> None:
        """create_app() returns a SheshaTUI instance."""
        from arxiv_explorer import create_app

        from shesha.tui import SheshaTUI

        state = _make_state()
        app = create_app(state, model="gpt-4o")
        assert isinstance(app, SheshaTUI)

    async def test_app_mounts_with_no_topic(self) -> None:
        """When no topic is set, InfoBar shows 'No topic'."""
        from arxiv_explorer import create_app

        state = _make_state()
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            info_bar = pilot.app.query_one(InfoBar)
            line1, _ = info_bar._state.render_lines()
            assert "No topic" in line1

    async def test_app_mounts_with_topic_name(self) -> None:
        """When a topic is set, InfoBar shows the topic name."""
        from arxiv_explorer import create_app

        from shesha.experimental.arxiv.models import TopicInfo

        state = _make_state(current_topic="2025-01-15-quantum")
        state.topic_mgr.get_topic_info_by_project_id.return_value = TopicInfo(
            name="quantum",
            created=MagicMock(),
            paper_count=2,
            size_bytes=0,
            project_id="2025-01-15-quantum",
        )
        state.shesha.get_project.return_value = MagicMock()
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            info_bar = pilot.app.query_one(InfoBar)
            line1, _ = info_bar._state.render_lines()
            assert "quantum" in line1


class TestTUIStartupMessages:
    """Tests for startup_message and startup_warning display."""

    async def test_startup_warning_shows_in_output(self) -> None:
        """startup_warning appears as a system message in OutputArea."""
        from arxiv_explorer import create_app

        state = _make_state()
        app = create_app(state, model="gpt-4o", startup_warning="Topic not found!")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("Topic not found!" in t for t in texts)

    async def test_startup_message_shows_in_output(self) -> None:
        """startup_message appears as a system message in OutputArea."""
        from arxiv_explorer import create_app

        state = _make_state()
        app = create_app(
            state, model="gpt-4o", startup_message="Switched to topic: quantum (3 papers)"
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("Switched to topic: quantum" in t for t in texts)

    async def test_warning_shows_before_message(self) -> None:
        """When both warning and message are set, warning appears first."""
        from arxiv_explorer import create_app

        state = _make_state()
        app = create_app(
            state,
            model="gpt-4o",
            startup_warning="Warning text",
            startup_message="Info text",
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            warning_idx = next(i for i, t in enumerate(texts) if "Warning text" in t)
            info_idx = next(i for i, t in enumerate(texts) if "Info text" in t)
            assert warning_idx < info_idx


class TestTUICommands:
    """Tests for non-threaded TUI commands."""

    async def test_papers_no_topic_shows_error(self) -> None:
        """/topic papers with no topic shows error message."""
        from arxiv_explorer import create_app

        state = _make_state()
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic papers")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("No topic" in t for t in texts)

    async def test_papers_lists_documents(self) -> None:
        """/topic papers with topic lists papers as markdown."""
        from datetime import UTC, datetime

        from arxiv_explorer import create_app

        from shesha.experimental.arxiv.models import PaperMeta, TopicInfo

        state = _make_state(current_topic="2025-01-15-quantum")
        state.topic_mgr.get_topic_info_by_project_id.return_value = TopicInfo(
            name="quantum",
            created=datetime(2025, 1, 15, tzinfo=UTC),
            paper_count=1,
            size_bytes=0,
            project_id="2025-01-15-quantum",
        )
        state.shesha.get_project.return_value = MagicMock()
        state.topic_mgr._storage.list_documents.return_value = ["2501.12345"]
        state.cache.get_meta.return_value = PaperMeta(
            arxiv_id="2501.12345",
            title="Quantum Error Correction",
            authors=["Smith"],
            abstract="Abstract",
            published=datetime(2025, 1, 1, tzinfo=UTC),
            updated=datetime(2025, 1, 1, tzinfo=UTC),
            categories=["cs.AI"],
            primary_category="cs.AI",
            pdf_url="https://arxiv.org/pdf/2501.12345",
            arxiv_url="https://arxiv.org/abs/2501.12345",
        )
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic papers")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            # Markdown content lives in nested children (MarkdownH*, MarkdownParagraph, etc.)
            all_text = _extract_output_text(output)
            assert "2501.12345" in all_text

    async def test_topic_bare_shows_usage_help(self) -> None:
        """/topic with no args shows usage help listing subcommands."""
        from arxiv_explorer import create_app

        state = _make_state()
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("Topic management" in t or "/topic list" in t for t in texts)

    async def test_topic_creates_and_switches(self) -> None:
        """/topic create <name> creates a new topic, switches, and updates InfoBar."""
        from arxiv_explorer import create_app

        state = _make_state()
        state.topic_mgr.resolve.return_value = None
        state.topic_mgr.create.return_value = "2025-01-15-new-topic"
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic create new-topic")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            assert state.current_topic == "2025-01-15-new-topic"
            info_bar = pilot.app.query_one(InfoBar)
            line1, _ = info_bar._state.render_lines()
            assert "new-topic" in line1

    async def test_topic_switch_existing(self) -> None:
        """/topic switch <name> switches to existing topic and updates InfoBar."""
        from arxiv_explorer import create_app

        state = _make_state()
        state.topic_mgr.resolve.return_value = "2025-01-15-quantum"
        state.topic_mgr._storage.list_documents.return_value = ["doc1", "doc2"]
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic switch quantum")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            assert state.current_topic == "2025-01-15-quantum"
            info_bar = pilot.app.query_one(InfoBar)
            line1, _ = info_bar._state.render_lines()
            assert "quantum" in line1

    async def test_topic_delete(self) -> None:
        """/topic delete <name> deletes the topic."""
        from arxiv_explorer import create_app

        state = _make_state(current_topic="2025-01-15-quantum")
        state.topic_mgr.get_topic_info_by_project_id.return_value = MagicMock(name="quantum")
        state.shesha.get_project.return_value = MagicMock()
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic delete quantum")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            state.topic_mgr.delete.assert_called_once_with("quantum")

    async def test_topic_delete_current_resets_infobar(self) -> None:
        """/topic delete of current topic resets InfoBar to 'No topic'."""
        from arxiv_explorer import create_app

        state = _make_state(current_topic="2025-01-15-quantum")
        state.topic_mgr.get_topic_info_by_project_id.return_value = MagicMock(name="quantum")
        state.topic_mgr.resolve.return_value = "2025-01-15-quantum"
        state.shesha.get_project.return_value = MagicMock()
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic delete quantum")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            assert state.current_topic is None
            info_bar = pilot.app.query_one(InfoBar)
            line1, _ = info_bar._state.render_lines()
            assert "No topic" in line1

    async def test_topic_delete_other_does_not_reset_current(self) -> None:
        """/topic delete of a different topic must not clear current_topic."""
        from arxiv_explorer import create_app

        # current topic is "quantum"; deleting "a" should not clear it
        # (the old substring check `"a" in "2025-01-15-quantum"` was True)
        state = _make_state(current_topic="2025-01-15-quantum")
        state.topic_mgr.get_topic_info_by_project_id.return_value = MagicMock(name="quantum")
        state.shesha.get_project.return_value = MagicMock()
        state.topic_mgr.resolve.return_value = "2025-01-10-a"
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic delete a")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            # current_topic must still be set — "a" is a different topic
            assert state.current_topic == "2025-01-15-quantum"

    async def test_topic_rename_calls_rename(self) -> None:
        """/topic rename <old> <new> calls topic_mgr.rename()."""
        from arxiv_explorer import create_app

        state = _make_state(current_topic="2025-01-15-quantum")
        state.topic_mgr.get_topic_info_by_project_id.return_value = MagicMock(name="quantum")
        state.shesha.get_project.return_value = MagicMock()
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic rename quantum qec")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            state.topic_mgr.rename.assert_called_once_with("quantum", "qec")

    async def test_topic_rename_updates_infobar(self) -> None:
        """/topic rename updates InfoBar when renaming the current topic."""
        from arxiv_explorer import create_app

        state = _make_state(current_topic="2025-01-15-quantum")
        state.topic_mgr.get_topic_info_by_project_id.return_value = MagicMock(name="quantum")
        state.topic_mgr.resolve.return_value = "2025-01-15-quantum"
        state.shesha.get_project.return_value = MagicMock()
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic rename quantum qec")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            info_bar = pilot.app.query_one(InfoBar)
            line1, _ = info_bar._state.render_lines()
            assert "qec" in line1

    async def test_history_empty_shows_message(self) -> None:
        """/topic list with no topics shows info message."""
        from arxiv_explorer import create_app

        state = _make_state()
        state.topic_mgr.list_topics.return_value = []
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic list")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("No topics" in t for t in texts)

    async def test_history_lists_topics(self) -> None:
        """/topic list with topics shows markdown table."""
        from datetime import UTC, datetime

        from arxiv_explorer import create_app

        from shesha.experimental.arxiv.models import TopicInfo

        state = _make_state()
        state.topic_mgr.list_topics.return_value = [
            TopicInfo(
                name="quantum",
                created=datetime(2025, 1, 15, tzinfo=UTC),
                paper_count=3,
                size_bytes=12_400_000,
                project_id="2025-01-15-quantum",
            ),
        ]
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic list")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            all_text = _extract_output_text(output)
            assert "quantum" in all_text

    async def test_topic_switch_by_number(self) -> None:
        """/topic switch <number> switches to topic by list position."""
        from datetime import UTC, datetime

        from arxiv_explorer import create_app

        from shesha.experimental.arxiv.models import TopicInfo

        state = _make_state()
        state.topic_mgr.list_topics.return_value = [
            TopicInfo(
                name="quantum",
                created=datetime(2025, 1, 15, tzinfo=UTC),
                paper_count=2,
                size_bytes=0,
                project_id="2025-01-15-quantum",
            ),
        ]
        state.topic_mgr._storage.list_documents.return_value = ["doc1", "doc2"]
        state.shesha.get_project.return_value = MagicMock()
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic switch 1")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            assert state.current_topic == "2025-01-15-quantum"
            info_bar = pilot.app.query_one(InfoBar)
            line1, _ = info_bar._state.render_lines()
            assert "quantum" in line1

    async def test_old_commands_not_registered(self) -> None:
        """Old commands /load, /papers, /history, /check-citations are gone."""
        from arxiv_explorer import create_app

        state = _make_state()
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            assert pilot.app._command_registry.resolve("/load") is None
            assert pilot.app._command_registry.resolve("/papers") is None
            assert pilot.app._command_registry.resolve("/history") is None
            assert pilot.app._command_registry.resolve("/check-citations") is None

    async def test_topic_switch_not_found_shows_error(self) -> None:
        """/topic switch nonexistent shows error."""
        from arxiv_explorer import create_app

        state = _make_state()
        state.topic_mgr.resolve.return_value = None
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic switch nonexistent")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("not found" in t for t in texts)

    async def test_topic_create_already_exists_shows_error(self) -> None:
        """/topic create <existing> shows error when topic already exists."""
        from arxiv_explorer import create_app

        state = _make_state()
        state.topic_mgr.resolve.return_value = "2025-01-15-quantum"
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic create quantum")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("already exists" in t for t in texts)


class TestTUISearchCommands:
    """Tests for threaded /search and /more TUI commands."""

    async def test_search_shows_results(self) -> None:
        """/search shows formatted results in OutputArea."""
        from datetime import UTC, datetime

        from arxiv_explorer import create_app

        from shesha.experimental.arxiv.models import PaperMeta

        state = _make_state()
        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Quantum Error Correction",
            authors=["Smith"],
            abstract="Abstract",
            published=datetime(2025, 1, 1, tzinfo=UTC),
            updated=datetime(2025, 1, 1, tzinfo=UTC),
            categories=["cs.AI"],
            primary_category="cs.AI",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/2501.12345",
        )
        state.searcher.search.return_value = [meta]
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/search quantum")
            assert resolved is not None
            handler, args, threaded = resolved
            assert threaded is True
            worker = pilot.app.run_worker(lambda: handler(args), thread=True)
            await worker.wait()
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            all_text = _extract_output_text(output)
            assert "2501.12345" in all_text
            assert len(state.last_search_results) == 1

    async def test_search_empty_shows_usage(self) -> None:
        """/search with no query shows usage message."""
        from arxiv_explorer import create_app

        state = _make_state()
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/search")
            assert resolved is not None
            handler, args, threaded = resolved
            worker = pilot.app.run_worker(lambda: handler(args), thread=True)
            await worker.wait()
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("Usage" in t or "usage" in t for t in texts)

    async def test_more_fetches_next_page(self) -> None:
        """/more fetches and appends next page of results."""
        from datetime import UTC, datetime

        from arxiv_explorer import create_app

        from shesha.experimental.arxiv.models import PaperMeta

        state = _make_state()
        state._last_search_kwargs = {"query": "quantum"}
        state._search_offset = 10
        state.last_search_results = [MagicMock()]
        next_meta = PaperMeta(
            arxiv_id="2502.00001",
            title="Next Page Paper",
            authors=["Jones"],
            abstract="",
            published=datetime(2025, 2, 1, tzinfo=UTC),
            updated=datetime(2025, 2, 1, tzinfo=UTC),
            categories=["cs.AI"],
            primary_category="cs.AI",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/2502.00001",
        )
        state.searcher.search.return_value = [next_meta]
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/more")
            assert resolved is not None
            handler, args, threaded = resolved
            assert threaded is True
            worker = pilot.app.run_worker(lambda: handler(args), thread=True)
            await worker.wait()
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            all_text = _extract_output_text(output)
            assert "2502.00001" in all_text

    async def test_more_without_search_shows_error(self) -> None:
        """/more without prior search shows error."""
        from arxiv_explorer import create_app

        state = _make_state()
        state._last_search_kwargs = None
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/more")
            assert resolved is not None
            handler, args, threaded = resolved
            worker = pilot.app.run_worker(lambda: handler(args), thread=True)
            await worker.wait()
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("No previous search" in t for t in texts)


class TestTUILoadCommand:
    """Tests for threaded /topic add TUI command."""

    async def test_load_by_number_stores_document(self) -> None:
        """/topic add <number> downloads and stores a paper."""
        from datetime import UTC, datetime
        from unittest.mock import patch

        from arxiv_explorer import create_app

        from shesha.experimental.arxiv.models import PaperMeta
        from shesha.models import ParsedDocument

        state = _make_state(current_topic="2025-01-15-test")
        state.topic_mgr.get_topic_info_by_project_id.return_value = MagicMock(name="test")
        state.shesha.get_project.return_value = MagicMock()
        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Test Paper",
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
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            with (
                patch("arxiv_explorer.download_paper", return_value=meta),
                patch(
                    "arxiv_explorer.to_parsed_document",
                    return_value=ParsedDocument(
                        name="2501.12345",
                        content="content",
                        format="latex",
                        metadata={},
                        char_count=7,
                    ),
                ),
            ):
                resolved = pilot.app._command_registry.resolve("/topic add 1")
                assert resolved is not None
                handler, args, threaded = resolved
                assert threaded is True
                worker = pilot.app.run_worker(lambda: handler(args), thread=True)
                await worker.wait()
                await pilot.pause()
            state.topic_mgr._storage.store_document.assert_called_once()

    async def test_load_skips_already_added_papers(self) -> None:
        """/topic add skips papers already in the topic."""
        from datetime import UTC, datetime
        from unittest.mock import patch

        from arxiv_explorer import create_app

        from shesha.experimental.arxiv.models import PaperMeta
        from shesha.models import ParsedDocument

        state = _make_state(current_topic="2025-01-15-test")
        state.topic_mgr.get_topic_info_by_project_id.return_value = MagicMock(name="test")
        state.shesha.get_project.return_value = MagicMock()
        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Test Paper",
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
        # Paper is already in the topic
        state.topic_mgr._storage.list_documents.return_value = ["2501.12345"]
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            with (
                patch("arxiv_explorer.download_paper", return_value=meta) as mock_download,
                patch(
                    "arxiv_explorer.to_parsed_document",
                    return_value=ParsedDocument(
                        name="2501.12345",
                        content="content",
                        format="latex",
                        metadata={},
                        char_count=7,
                    ),
                ),
            ):
                resolved = pilot.app._command_registry.resolve("/topic add 1")
                assert resolved is not None
                handler, args, threaded = resolved
                worker = pilot.app.run_worker(lambda: handler(args), thread=True)
                await worker.wait()
                await pilot.pause()
            # Should NOT have downloaded the paper
            mock_download.assert_not_called()
            # Should show a "skipped" or "already" message
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("already" in t.lower() for t in texts)

    async def test_load_requires_topic(self) -> None:
        """/topic add without a topic shows error."""
        from arxiv_explorer import create_app

        state = _make_state()
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic add 1")
            assert resolved is not None
            handler, args, threaded = resolved
            worker = pilot.app.run_worker(lambda: handler(args), thread=True)
            await worker.wait()
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("No topic" in t for t in texts)


class TestTUICheckCitations:
    """Tests for threaded /check TUI command."""

    async def test_check_citations_runs_pipeline(self) -> None:
        """/check runs the citation verification pipeline."""
        from datetime import UTC, datetime
        from unittest.mock import patch

        from arxiv_explorer import create_app

        from shesha.experimental.arxiv.models import (
            PaperMeta,
            TopicInfo,
            VerificationResult,
            VerificationStatus,
        )

        state = _make_state(current_topic="2025-01-15-test")
        state.topic_mgr.get_topic_info_by_project_id.return_value = TopicInfo(
            name="test",
            created=datetime(2025, 1, 15, tzinfo=UTC),
            paper_count=1,
            size_bytes=0,
            project_id="2025-01-15-test",
        )
        state.shesha.get_project.return_value = MagicMock()
        state.topic_mgr._storage.list_documents.return_value = ["2501.12345"]
        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Test Paper",
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
        state.cache.get_meta.return_value = meta
        state.cache.get_source_files.return_value = {
            "main.tex": "\\documentclass{article}\\begin{document}Test.\\end{document}",
            "refs.bib": (
                "@article{a, author={A}, title={Paper A}, year={2023}, eprint={2301.00001}}"
            ),
        }
        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = VerificationResult(
            citation_key="a",
            status=VerificationStatus.VERIFIED,
        )
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            with patch("arxiv_explorer.ArxivVerifier", return_value=mock_verifier):
                resolved = pilot.app._command_registry.resolve("/check")
                assert resolved is not None
                handler, args, threaded = resolved
                assert threaded is True
                worker = pilot.app.run_worker(lambda: handler(args), thread=True)
                await worker.wait()
                await pilot.pause()
            mock_verifier.verify.assert_called_once()

    async def test_check_citations_requires_topic(self) -> None:
        """/check without a topic shows error."""
        from arxiv_explorer import create_app

        state = _make_state()
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/check")
            assert resolved is not None
            handler, args, threaded = resolved
            worker = pilot.app.run_worker(lambda: handler(args), thread=True)
            await worker.wait()
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("No topic" in t for t in texts)


class TestTUIConversationalQuery:
    """Tests for conversational query guard."""

    async def test_query_with_no_topic_shows_error(self) -> None:
        """Submitting a question with no topic selected shows error, not a query."""
        from arxiv_explorer import create_app

        from shesha.tui.widgets.input_area import InputArea

        state = _make_state()
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "What is this paper about?"
            await pilot.press("enter")
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("No topic" in t for t in texts)
            # Should NOT have started a query
            assert pilot.app._query_in_progress is False

    async def test_query_with_no_papers_shows_error(self) -> None:
        """Submitting a question with no papers loaded shows error."""
        from arxiv_explorer import create_app

        from shesha.experimental.arxiv.models import TopicInfo
        from shesha.tui.widgets.input_area import InputArea

        state = _make_state(current_topic="2025-01-15-quantum")
        state.topic_mgr.get_topic_info_by_project_id.return_value = TopicInfo(
            name="quantum",
            created=MagicMock(),
            paper_count=0,
            size_bytes=0,
            project_id="2025-01-15-quantum",
        )
        state.shesha.get_project.return_value = MagicMock()
        state.topic_mgr._storage.list_documents.return_value = []
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "What is this paper about?"
            await pilot.press("enter")
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("No papers" in t for t in texts)
            assert pilot.app._query_in_progress is False

    async def test_query_with_topic_and_papers_proceeds(self) -> None:
        """With topic and papers, query proceeds to _run_query."""
        from arxiv_explorer import create_app

        from shesha.experimental.arxiv.models import TopicInfo
        from shesha.tui.widgets.input_area import InputArea

        state = _make_state(current_topic="2025-01-15-quantum")
        state.topic_mgr.get_topic_info_by_project_id.return_value = TopicInfo(
            name="quantum",
            created=MagicMock(),
            paper_count=1,
            size_bytes=0,
            project_id="2025-01-15-quantum",
        )
        mock_project = MagicMock()
        state.shesha.get_project.return_value = mock_project
        state.topic_mgr._storage.list_documents.return_value = ["2501.12345"]
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "What is this paper about?"
            await pilot.press("enter")
            await pilot.pause()
            # Query should have started (it will fail because mock project
            # doesn't implement query properly, but _query_in_progress
            # should have been set)
            # We check that no "No topic" or "No papers" message was shown
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert not any("No topic" in t for t in texts)
            assert not any("No papers" in t for t in texts)
