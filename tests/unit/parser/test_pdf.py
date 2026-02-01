"""Tests for PDF parser."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shesha.parser.pdf import PdfParser


@pytest.fixture
def parser() -> PdfParser:
    return PdfParser()


class TestPdfParser:
    """Tests for PdfParser."""

    def test_can_parse_pdf(self, parser: PdfParser):
        """PdfParser can parse .pdf files."""
        assert parser.can_parse(Path("document.pdf"))

    def test_cannot_parse_other(self, parser: PdfParser):
        """PdfParser cannot parse non-PDF files."""
        assert not parser.can_parse(Path("document.txt"))
        assert not parser.can_parse(Path("document.docx"))

    @patch("shesha.parser.pdf.fitz")
    def test_parse_pdf_extracts_text(self, mock_fitz: MagicMock, parser: PdfParser):
        """PdfParser extracts text from PDF pages."""
        # Mock PDF document
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Page 1 content"
        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_doc.__len__ = lambda self: 1
        mock_fitz.open.return_value.__enter__ = lambda self: mock_doc
        mock_fitz.open.return_value.__exit__ = lambda *args: None

        doc = parser.parse(Path("test.pdf"))
        assert doc.name == "test.pdf"
        assert "Page 1 content" in doc.content
        assert doc.format == "pdf"
        assert doc.metadata["page_count"] == 1
