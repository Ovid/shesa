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
        """/papers with no topic shows error message."""
        from arxiv_explorer import create_app

        state = _make_state()
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/papers")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("No topic" in t for t in texts)

    async def test_papers_lists_documents(self) -> None:
        """/papers with topic lists papers as markdown."""
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
            resolved = pilot.app._command_registry.resolve("/papers")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            # Markdown content lives in nested children (MarkdownH*, MarkdownParagraph, etc.)
            all_text = _extract_output_text(output)
            assert "2501.12345" in all_text

    async def test_topic_bare_shows_current(self) -> None:
        """/topic with no args shows current topic name."""
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
            resolved = pilot.app._command_registry.resolve("/topic")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("quantum" in t for t in texts)

    async def test_topic_creates_and_switches(self) -> None:
        """/topic <name> creates a new topic, switches, and updates InfoBar."""
        from arxiv_explorer import create_app

        state = _make_state()
        state.topic_mgr.resolve.return_value = None
        state.topic_mgr.create.return_value = "2025-01-15-new-topic"
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic new-topic")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            assert state.current_topic == "2025-01-15-new-topic"
            info_bar = pilot.app.query_one(InfoBar)
            line1, _ = info_bar._state.render_lines()
            assert "new-topic" in line1

    async def test_topic_switch_existing(self) -> None:
        """/topic <name> switches to existing topic and updates InfoBar."""
        from arxiv_explorer import create_app

        state = _make_state()
        state.topic_mgr.resolve.return_value = "2025-01-15-quantum"
        state.topic_mgr._storage.list_documents.return_value = ["doc1", "doc2"]
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/topic quantum")
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
        """/history with no topics shows info message."""
        from arxiv_explorer import create_app

        state = _make_state()
        state.topic_mgr.list_topics.return_value = []
        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/history")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("No topics" in t for t in texts)

    async def test_history_lists_topics(self) -> None:
        """/history with topics shows markdown table."""
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
            resolved = pilot.app._command_registry.resolve("/history")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            all_text = _extract_output_text(output)
            assert "quantum" in all_text
