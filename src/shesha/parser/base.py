"""Document parser protocol."""

from pathlib import Path
from typing import Protocol

from shesha.storage.base import ParsedDocument


class DocumentParser(Protocol):
    """Protocol for document parsers."""

    def can_parse(self, path: Path, mime_type: str | None = None) -> bool:
        """Check if this parser can handle the given file."""
        ...

    def parse(self, path: Path) -> ParsedDocument:
        """Parse a file and return a ParsedDocument."""
        ...
