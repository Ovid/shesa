"""Project class for managing document collections."""

from pathlib import Path

from shesha.parser.registry import ParserRegistry
from shesha.rlm.engine import QueryResult, RLMEngine
from shesha.storage.base import StorageBackend


class Project:
    """A project containing documents for querying."""

    def __init__(
        self,
        project_id: str,
        storage: StorageBackend,
        parser_registry: ParserRegistry,
        rlm_engine: RLMEngine | None = None,
    ) -> None:
        """Initialize a project."""
        self.project_id = project_id
        self._storage = storage
        self._parser_registry = parser_registry
        self._rlm_engine = rlm_engine

    def upload(self, path: Path | str, recursive: bool = False) -> list[str]:
        """Upload a file or directory to the project."""
        path = Path(path)
        uploaded: list[str] = []

        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            files = [f for f in path.glob(pattern) if f.is_file()]
        else:
            files = [path]

        for file_path in files:
            parser = self._parser_registry.find_parser(file_path)
            if parser is None:
                continue  # Skip unsupported files

            doc = parser.parse(file_path)
            self._storage.store_document(self.project_id, doc, raw_path=file_path)
            uploaded.append(doc.name)

        return uploaded

    def list_documents(self) -> list[str]:
        """List all documents in the project."""
        return self._storage.list_documents(self.project_id)

    def delete_document(self, doc_name: str) -> None:
        """Delete a document from the project."""
        self._storage.delete_document(self.project_id, doc_name)

    def query(self, question: str) -> QueryResult:
        """Query the documents with a question."""
        if self._rlm_engine is None:
            raise RuntimeError("No RLM engine configured for queries")

        docs = self._storage.load_all_documents(self.project_id)
        return self._rlm_engine.query(
            documents=[d.content for d in docs],
            question=question,
            doc_names=[d.name for d in docs],
        )
