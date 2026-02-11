"""Tests for topic manager."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from shesha.storage.filesystem import FilesystemStorage


def _make_shesha_and_storage(tmp_path: Path) -> tuple[MagicMock, FilesystemStorage]:
    """Create a real FilesystemStorage with a mock Shesha that delegates to it."""
    # Late import inside test helper to avoid top-level dependency on shesha internals
    from shesha.storage.filesystem import FilesystemStorage

    storage_path = tmp_path / "shesha_data"
    storage = FilesystemStorage(storage_path)

    shesha = MagicMock()
    shesha._storage = storage
    shesha.list_projects.side_effect = lambda: storage.list_projects()
    shesha.delete_project.side_effect = lambda pid, cleanup_repo=True: storage.delete_project(pid)
    return shesha, storage


class TestTopicManager:
    """Tests for TopicManager."""

    def test_create_topic(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        project_id = mgr.create("quantum-error-correction")
        assert "quantum-error-correction" in project_id
        assert storage.project_exists(project_id)

    def test_create_topic_includes_date(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        project_id = mgr.create("test-topic")
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        assert project_id.startswith(today)

    def test_list_topics_empty(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        assert mgr.list_topics() == []

    def test_list_topics_returns_topic_info(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        mgr.create("topic-a")
        topics = mgr.list_topics()
        assert len(topics) == 1
        assert topics[0].name == "topic-a"
        assert topics[0].paper_count == 0
        assert topics[0].size_bytes >= 0

    def test_delete_topic(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        project_id = mgr.create("to-delete")
        mgr.delete("to-delete")
        assert not storage.project_exists(project_id)

    def test_resolve_topic_name(self, tmp_path: Path) -> None:
        """Resolve a slug name to a full project ID."""
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        project_id = mgr.create("my-topic")
        resolved = mgr.resolve("my-topic")
        assert resolved == project_id

    def test_resolve_returns_none_for_unknown(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        assert mgr.resolve("nonexistent") is None

    def test_get_topic_info_with_size(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager
        from shesha.models import ParsedDocument

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        project_id = mgr.create("sized-topic")
        # Store a document to add some size
        doc = ParsedDocument(
            name="test.txt",
            content="Hello world " * 1000,
            format="text",
            metadata={},
            char_count=12000,
        )
        storage.store_document(project_id, doc)
        info = mgr.get_topic_info("sized-topic")
        assert info is not None
        assert info.paper_count == 1
        assert info.size_bytes > 0

    def test_get_topic_info_by_project_id(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        project_id = mgr.create("by-id-test")
        info = mgr.get_topic_info_by_project_id(project_id)
        assert info is not None
        assert info.name == "by-id-test"

    def test_get_topic_info_by_project_id_returns_none(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        assert mgr.get_topic_info_by_project_id("nonexistent") is None

    def test_create_existing_topic_is_idempotent(self, tmp_path: Path) -> None:
        """Creating a topic that already exists returns its project ID."""
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        project_id_1 = mgr.create("existing-topic")
        project_id_2 = mgr.create("existing-topic")
        assert project_id_1 == project_id_2
        assert storage.project_exists(project_id_1)

    def test_slugify(self, tmp_path: Path) -> None:
        """Topic names are slugified (lowercase, hyphens, no special chars)."""
        from shesha.experimental.arxiv.topics import slugify

        assert slugify("Quantum Error Correction") == "quantum-error-correction"
        assert slugify("cs.AI + language models!") == "cs-ai-language-models"
        assert slugify("  spaces  everywhere  ") == "spaces-everywhere"
