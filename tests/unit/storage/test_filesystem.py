"""Tests for filesystem storage backend."""

from pathlib import Path

import pytest

from shesha.exceptions import (
    DocumentNotFoundError,
    ProjectExistsError,
    ProjectNotFoundError,
)
from shesha.models import (
    AnalysisComponent,
    AnalysisExternalDep,
    ParsedDocument,
    RepoAnalysis,
)
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

    def test_raw_file_copy_traversal_blocked(self, tmp_path: Path) -> None:
        """Raw file copy with traversal in doc.name is blocked."""
        storage = FilesystemStorage(tmp_path, keep_raw_files=True)
        storage.create_project("test-project")

        # Create a source file
        source_file = tmp_path / "source.txt"
        source_file.write_text("content")

        doc = ParsedDocument(
            name="../../../escape.txt",
            content="malicious",
            format="txt",
            metadata={},
            char_count=9,
            parse_warnings=[],
        )
        with pytest.raises(PathTraversalError):
            storage.store_document("test-project", doc, raw_path=source_file)

    def test_raw_file_copy_nested_path_works(self, tmp_path: Path) -> None:
        """Raw file copy with nested path (e.g., src/main.py) works."""
        storage = FilesystemStorage(tmp_path, keep_raw_files=True)
        storage.create_project("test-project")

        # Create a source file
        source_file = tmp_path / "source.txt"
        source_file.write_text("content")

        doc = ParsedDocument(
            name="src/main.py",
            content="code",
            format="py",
            metadata={},
            char_count=4,
            parse_warnings=[],
        )
        # Should not raise - nested paths are valid
        storage.store_document("test-project", doc, raw_path=source_file)

        # Verify file was created in correct nested location
        raw_path = tmp_path / "projects" / "test-project" / "raw" / "src" / "main.py"
        assert raw_path.exists()
        assert raw_path.read_text() == "content"


class TestTraceOperations:
    """Tests for trace file operations."""

    def test_get_traces_dir_creates_directory(self, storage: FilesystemStorage) -> None:
        """get_traces_dir creates traces directory if needed."""
        storage.create_project("trace-project")
        traces_dir = storage.get_traces_dir("trace-project")
        assert traces_dir.exists()
        assert traces_dir.name == "traces"

    def test_get_traces_dir_nonexistent_project_raises(self, storage: FilesystemStorage) -> None:
        """get_traces_dir raises for nonexistent project."""
        with pytest.raises(ProjectNotFoundError):
            storage.get_traces_dir("no-such-project")

    def test_list_traces_empty(self, storage: FilesystemStorage) -> None:
        """list_traces returns empty list when no traces exist."""
        storage.create_project("empty-traces")
        assert storage.list_traces("empty-traces") == []

    def test_list_traces_returns_sorted_by_name(self, storage: FilesystemStorage) -> None:
        """list_traces returns files sorted by name (oldest first)."""
        storage.create_project("sorted-traces")
        traces_dir = storage.get_traces_dir("sorted-traces")
        # Create files with timestamps in names (older first)
        (traces_dir / "2026-02-03T10-00-00-000_aaaa1111.jsonl").write_text("{}")
        (traces_dir / "2026-02-03T10-00-01-000_bbbb2222.jsonl").write_text("{}")
        (traces_dir / "2026-02-03T10-00-02-000_cccc3333.jsonl").write_text("{}")
        traces = storage.list_traces("sorted-traces")
        assert len(traces) == 3
        assert traces[0].name == "2026-02-03T10-00-00-000_aaaa1111.jsonl"
        assert traces[2].name == "2026-02-03T10-00-02-000_cccc3333.jsonl"


class TestAnalysisOperations:
    """Tests for analysis CRUD operations."""

    def test_store_and_load_analysis(self, storage: FilesystemStorage) -> None:
        """Storing an analysis allows retrieval."""
        storage.create_project("analysis-project")

        comp = AnalysisComponent(
            name="API",
            path="api/",
            description="REST API",
            apis=[{"type": "rest", "endpoints": ["/health"]}],
            models=["User"],
            entry_points=["api/main.py"],
            internal_dependencies=[],
            auth="JWT",
        )
        dep = AnalysisExternalDep(
            name="Redis",
            type="database",
            description="Cache",
            used_by=["api"],
            optional=True,
        )
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="A test application.",
            components=[comp],
            external_dependencies=[dep],
        )

        storage.store_analysis("analysis-project", analysis)
        loaded = storage.load_analysis("analysis-project")

        assert loaded is not None
        assert loaded.version == "1"
        assert loaded.head_sha == "abc123"
        assert loaded.overview == "A test application."
        assert len(loaded.components) == 1
        assert loaded.components[0].name == "API"
        assert loaded.components[0].auth == "JWT"
        assert len(loaded.external_dependencies) == 1
        assert loaded.external_dependencies[0].optional is True

    def test_load_analysis_returns_none_when_missing(
        self, storage: FilesystemStorage
    ) -> None:
        """Loading analysis returns None when no analysis exists."""
        storage.create_project("no-analysis")
        loaded = storage.load_analysis("no-analysis")
        assert loaded is None

    def test_delete_analysis(self, storage: FilesystemStorage) -> None:
        """Deleting an analysis removes it."""
        storage.create_project("del-analysis")
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="To delete",
            components=[],
            external_dependencies=[],
        )
        storage.store_analysis("del-analysis", analysis)
        storage.delete_analysis("del-analysis")
        assert storage.load_analysis("del-analysis") is None

    def test_delete_analysis_nonexistent_is_noop(
        self, storage: FilesystemStorage
    ) -> None:
        """Deleting nonexistent analysis doesn't raise."""
        storage.create_project("empty-analysis")
        storage.delete_analysis("empty-analysis")  # Should not raise

    def test_store_analysis_nonexistent_project_raises(
        self, storage: FilesystemStorage
    ) -> None:
        """Storing analysis to nonexistent project raises."""
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Orphan",
            components=[],
            external_dependencies=[],
        )
        with pytest.raises(ProjectNotFoundError):
            storage.store_analysis("no-such-project", analysis)

    def test_load_analysis_nonexistent_project_raises(
        self, storage: FilesystemStorage
    ) -> None:
        """Loading analysis from nonexistent project raises."""
        with pytest.raises(ProjectNotFoundError):
            storage.load_analysis("no-such-project")
