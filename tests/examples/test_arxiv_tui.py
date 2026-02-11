"""Tests for the arXiv explorer TUI."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure examples/ is importable
sys.path.insert(0, str(Path(__file__).parents[2] / "examples"))

from shesha.tui.widgets.info_bar import InfoBar
from shesha.tui.widgets.output_area import OutputArea


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
