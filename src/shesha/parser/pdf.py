"""PDF parser using PyMuPDF (fitz)."""

from pathlib import Path

import fitz  # PyMuPDF

from shesha.storage.base import ParsedDocument


class PdfParser:
    """Parser for PDF files using PyMuPDF."""

    def can_parse(self, path: Path, mime_type: str | None = None) -> bool:
        """Check if this parser can handle the given file."""
        return path.suffix.lower() == ".pdf"

    def parse(self, path: Path) -> ParsedDocument:
        """Parse a PDF file and return a ParsedDocument."""
        warnings: list[str] = []
        pages_text: list[str] = []

        with fitz.open(path) as doc:
            page_count = len(doc)
            for page_num, page in enumerate(doc, 1):
                text = page.get_text()
                if text.strip():
                    pages_text.append(f"--- Page {page_num} ---\n{text}")
                else:
                    warnings.append(f"Page {page_num} has no extractable text")

        content = "\n\n".join(pages_text)

        return ParsedDocument(
            name=path.name,
            content=content,
            format="pdf",
            metadata={"page_count": page_count},
            char_count=len(content),
            parse_warnings=warnings,
        )
