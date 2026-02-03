"""Tests for filesystem storage backend."""

from pathlib import Path

import pytest

from shesha.exceptions import (
    DocumentNotFoundError,
    ProjectExistsError,
    ProjectNotFoundError,
)
from shesha.models import ParsedDocument
from shesha.security.paths import PathTraversalError
from shesha.storage.filesystem import FilesystemStorage


@pytest.fixture
def storage(tmp_path: Path) -> FilesystemStorage:
    """Create a temporary storage backend."""
    return FilesystemStorage(root_path=tmp_path)


class TestProjectOperations:
    """Tests for project CRUD operations."""

    def test_create_project(self, storage: FilesystemStorage):
        """Creating a project creates the directory structure."""
        storage.create_project("test-project")
        assert storage.project_exists("test-project")

    def test_list_projects_empty(self, storage: FilesystemStorage):
        """List projects returns empty list when none exist."""
        assert storage.list_projects() == []

    def test_list_projects(self, storage: FilesystemStorage):
        """List projects returns all project IDs."""
        storage.create_project("project-a")
        storage.create_project("project-b")
        projects = storage.list_projects()
        assert sorted(projects) == ["project-a", "project-b"]

    def test_delete_project(self, storage: FilesystemStorage):
        """Deleting a project removes it completely."""
        storage.create_project("to-delete")
        storage.delete_project("to-delete")
        assert not storage.project_exists("to-delete")

    def test_create_duplicate_project_raises(self, storage: FilesystemStorage):
        """Creating a project that exists raises an error."""
        storage.create_project("existing")
        with pytest.raises(ProjectExistsError):
            storage.create_project("existing")


class TestDocumentOperations:
    """Tests for document CRUD operations."""

    def test_store_and_retrieve_document(self, storage: FilesystemStorage):
        """Storing a document allows retrieval."""
        storage.create_project("docs-project")
        doc = ParsedDocument(
            name="test.txt",
            content="Hello world",
            format="txt",
            metadata={"encoding": "utf-8"},
            char_count=11,
            parse_warnings=[],
        )
        storage.store_document("docs-project", doc)
        retrieved = storage.get_document("docs-project", "test.txt")
        assert retrieved.name == doc.name
        assert retrieved.content == doc.content

    def test_list_documents(self, storage: FilesystemStorage):
        """List documents returns all document names."""
        storage.create_project("list-project")
        for name in ["a.txt", "b.txt", "c.txt"]:
            doc = ParsedDocument(
                name=name,
                content=f"Content of {name}",
                format="txt",
                metadata={},
                char_count=len(f"Content of {name}"),
                parse_warnings=[],
            )
            storage.store_document("list-project", doc)
        docs = storage.list_documents("list-project")
        assert sorted(docs) == ["a.txt", "b.txt", "c.txt"]

    def test_delete_document(self, storage: FilesystemStorage):
        """Deleting a document removes it."""
        storage.create_project("del-project")
        doc = ParsedDocument(
            name="to-delete.txt",
            content="Bye",
            format="txt",
            metadata={},
            char_count=3,
            parse_warnings=[],
        )
        storage.store_document("del-project", doc)
        storage.delete_document("del-project", "to-delete.txt")
        assert "to-delete.txt" not in storage.list_documents("del-project")

    def test_load_all_documents(self, storage: FilesystemStorage):
        """Load all documents returns all ParsedDocument objects."""
        storage.create_project("load-project")
        for i in range(3):
            doc = ParsedDocument(
                name=f"doc{i}.txt",
                content=f"Content {i}",
                format="txt",
                metadata={},
                char_count=9,
                parse_warnings=[],
            )
            storage.store_document("load-project", doc)
        docs = storage.load_all_documents("load-project")
        assert len(docs) == 3
        assert all(isinstance(d, ParsedDocument) for d in docs)

    def test_get_nonexistent_document_raises(self, storage: FilesystemStorage):
        """Getting a nonexistent document raises an error."""
        storage.create_project("empty-project")
        with pytest.raises(DocumentNotFoundError):
            storage.get_document("empty-project", "missing.txt")

    def test_store_document_nonexistent_project_raises(self, storage: FilesystemStorage):
        """Storing to a nonexistent project raises an error."""
        doc = ParsedDocument(
            name="orphan.txt",
            content="No home",
            format="txt",
            metadata={},
            char_count=7,
            parse_warnings=[],
        )
        with pytest.raises(ProjectNotFoundError):
            storage.store_document("no-such-project", doc)


class TestPathTraversalProtection:
    """Tests for path traversal protection in storage."""

    def test_project_id_traversal_blocked(self, tmp_path: Path) -> None:
        """Project ID with traversal is blocked."""
        storage = FilesystemStorage(tmp_path)
        with pytest.raises(PathTraversalError):
            storage.create_project("../escape")

    def test_document_name_traversal_blocked(self, tmp_path: Path) -> None:
        """Document name with traversal is blocked."""
        storage = FilesystemStorage(tmp_path)
        storage.create_project("test-project")
        doc = ParsedDocument(
            name="../../etc/passwd",
            content="malicious",
            format="txt",
            metadata={},
            char_count=9,
            parse_warnings=[],
        )
        with pytest.raises(PathTraversalError):
            storage.store_document("test-project", doc)
