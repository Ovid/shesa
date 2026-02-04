"""Tests for data models."""

from unittest.mock import MagicMock

import pytest

from shesha.models import QueryContext, RepoProjectResult


class TestRepoProjectResult:
    """Tests for RepoProjectResult dataclass."""

    def test_created_status(self):
        """RepoProjectResult can be created with 'created' status."""
        mock_project = MagicMock()
        result = RepoProjectResult(
            project=mock_project,
            status="created",
            files_ingested=10,
            files_skipped=2,
            warnings=["some warning"],
        )

        assert result.project is mock_project
        assert result.status == "created"
        assert result.files_ingested == 10
        assert result.files_skipped == 2
        assert result.warnings == ["some warning"]

    def test_default_values(self):
        """RepoProjectResult has correct defaults for optional fields."""
        mock_project = MagicMock()
        result = RepoProjectResult(
            project=mock_project,
            status="created",
            files_ingested=5,
        )

        assert result.files_skipped == 0
        assert result.warnings == []

    def test_unchanged_status(self):
        """RepoProjectResult can be created with 'unchanged' status."""
        result = RepoProjectResult(
            project=MagicMock(),
            status="unchanged",
            files_ingested=0,
        )
        assert result.status == "unchanged"

    def test_updates_available_status(self):
        """RepoProjectResult can be created with 'updates_available' status."""
        result = RepoProjectResult(
            project=MagicMock(),
            status="updates_available",
            files_ingested=10,
        )
        assert result.status == "updates_available"

    def test_apply_updates_stores_callback(self):
        """RepoProjectResult stores apply_updates callback."""
        mock_project = MagicMock()
        callback_called = []

        def mock_callback():
            callback_called.append(True)
            return RepoProjectResult(
                project=mock_project,
                status="created",
                files_ingested=15,
            )

        result = RepoProjectResult(
            project=mock_project,
            status="updates_available",
            files_ingested=10,
            _apply_updates_fn=mock_callback,
        )

        updated = result.apply_updates()
        assert callback_called == [True]
        assert updated.files_ingested == 15

    def test_apply_updates_raises_when_unchanged(self):
        """apply_updates raises ValueError when status is not 'updates_available'."""
        mock_project = MagicMock()
        result = RepoProjectResult(
            project=mock_project,
            status="unchanged",
            files_ingested=10,
        )

        with pytest.raises(ValueError, match="only valid when status is 'updates_available'"):
            result.apply_updates()


class TestQueryContext:
    """Tests for QueryContext dataclass."""

    def test_query_context_stores_metadata(self) -> None:
        """QueryContext stores all query metadata."""
        ctx = QueryContext(
            trace_id="abc123",
            question="What is X?",
            document_ids=["doc1", "doc2"],
            model="claude-sonnet-4-20250514",
            system_prompt="You are an assistant...",
            subcall_prompt="Analyze this...",
        )
        assert ctx.trace_id == "abc123"
        assert ctx.question == "What is X?"
        assert ctx.document_ids == ["doc1", "doc2"]
        assert ctx.model == "claude-sonnet-4-20250514"
        assert ctx.system_prompt == "You are an assistant..."
        assert ctx.subcall_prompt == "Analyze this..."
