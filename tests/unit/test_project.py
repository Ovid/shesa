"""Tests for Project class."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shesha.project import Project
from shesha.models import ParsedDocument


@pytest.fixture
def mock_storage() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_registry() -> MagicMock:
    registry = MagicMock()
    parser = MagicMock()
    parser.parse.return_value = ParsedDocument(
        name="test.txt",
        content="content",
        format="txt",
        metadata={},
        char_count=7,
        parse_warnings=[],
    )
    registry.find_parser.return_value = parser
    return registry


class TestProject:
    """Tests for Project."""

    def test_upload_file(self, mock_storage: MagicMock, mock_registry: MagicMock, tmp_path: Path):
        """Upload parses and stores a file."""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        project = Project(
            project_id="test-project",
            storage=mock_storage,
            parser_registry=mock_registry,
        )
        project.upload(test_file)

        mock_storage.store_document.assert_called_once()

    def test_list_documents(self, mock_storage: MagicMock, mock_registry: MagicMock):
        """List documents returns storage list."""
        mock_storage.list_documents.return_value = ["a.txt", "b.txt"]

        project = Project(
            project_id="test-project",
            storage=mock_storage,
            parser_registry=mock_registry,
        )
        docs = project.list_documents()

        assert docs == ["a.txt", "b.txt"]

    def test_delete_document(self, mock_storage: MagicMock, mock_registry: MagicMock):
        """Delete document calls storage."""
        project = Project(
            project_id="test-project",
            storage=mock_storage,
            parser_registry=mock_registry,
        )
        project.delete_document("old.txt")

        mock_storage.delete_document.assert_called_with("test-project", "old.txt")
