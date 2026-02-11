"""Tests for arXiv search wrapper."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch


def _mock_arxiv_result(
    arxiv_id: str = "2501.12345",
    title: str = "Test Paper",
    authors: list[str] | None = None,
) -> MagicMock:
    """Create a mock arxiv.Result object."""
    result = MagicMock()
    result.entry_id = f"http://arxiv.org/abs/{arxiv_id}"
    result.title = title
    result.summary = "An abstract."
    result.published = datetime(2025, 1, 15, tzinfo=UTC)
    result.updated = datetime(2025, 1, 15, tzinfo=UTC)
    result.categories = ["cs.AI"]
    result.primary_category = "cs.AI"
    result.pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    result.comment = "10 pages"
    result.journal_ref = None
    result.doi = None
    # Authors are objects with .name attribute
    author_names = authors or ["Smith, J.", "Doe, A."]
    result.authors = [MagicMock(name=n) for n in author_names]
    # Fix: MagicMock(name=...) sets the mock's name, not .name attribute
    for author, name in zip(result.authors, author_names):
        author.name = name
    return result


class TestArxivSearcher:
    """Tests for ArxivSearcher."""

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_returns_paper_metas(self, mock_arxiv: MagicMock) -> None:
        # Late import: module under test must be imported after patch is active
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([_mock_arxiv_result()])

        searcher = ArxivSearcher()
        results = searcher.search("quantum computing")
        assert len(results) == 1
        assert results[0].arxiv_id == "2501.12345"
        assert results[0].title == "Test Paper"

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_with_category(self, mock_arxiv: MagicMock) -> None:
        # Late import: module under test must be imported after patch is active
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([])

        searcher = ArxivSearcher()
        searcher.search("language models", category="cs.AI")
        # Verify the query included the category
        search_call = mock_arxiv.Search.call_args
        assert "cat:cs.AI" in search_call.kwargs.get(
            "query", search_call.args[0] if search_call.args else ""
        )

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_by_author(self, mock_arxiv: MagicMock) -> None:
        # Late import: module under test must be imported after patch is active
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([])

        searcher = ArxivSearcher()
        searcher.search("", author="del maestro")
        search_call = mock_arxiv.Search.call_args
        query = search_call.kwargs.get("query", search_call.args[0] if search_call.args else "")
        assert "au:" in query

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_with_start_offset(self, mock_arxiv: MagicMock) -> None:
        # Late import: module under test must be imported after patch is active
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([_mock_arxiv_result()])

        searcher = ArxivSearcher()
        searcher.search("quantum", start=10)
        search_call = mock_arxiv.Search.call_args
        assert (
            search_call.kwargs.get("start", search_call.args[1] if len(search_call.args) > 1 else 0)
            == 10
        )

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_recent_days(self, mock_arxiv: MagicMock) -> None:
        # Late import: module under test must be imported after patch is active
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([])

        searcher = ArxivSearcher()
        searcher.search("quantum", recent_days=7)
        search_call = mock_arxiv.Search.call_args
        query = search_call.kwargs.get("query", search_call.args[0] if search_call.args else "")
        assert "submittedDate:" in query

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_get_by_id(self, mock_arxiv: MagicMock) -> None:
        # Late import: module under test must be imported after patch is active
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([_mock_arxiv_result()])

        searcher = ArxivSearcher()
        meta = searcher.get_by_id("2501.12345")
        assert meta is not None
        assert meta.arxiv_id == "2501.12345"

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_get_by_id_not_found(self, mock_arxiv: MagicMock) -> None:
        # Late import: module under test must be imported after patch is active
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([])

        searcher = ArxivSearcher()
        meta = searcher.get_by_id("0000.00000")
        assert meta is None

    def test_format_result(self) -> None:
        # Late import: module under test
        from shesha.experimental.arxiv.models import PaperMeta
        from shesha.experimental.arxiv.search import format_result

        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Topological Quantum Error Correction with Low Overhead",
            authors=["Smith, J.", "Jones, K.", "Lee, M."],
            abstract="Abstract",
            published=datetime(2025, 1, 15, tzinfo=UTC),
            updated=datetime(2025, 1, 15, tzinfo=UTC),
            categories=["cs.QI"],
            primary_category="cs.QI",
            pdf_url="https://arxiv.org/pdf/2501.12345",
            arxiv_url="https://arxiv.org/abs/2501.12345",
            comment="12 pages",
        )
        output = format_result(meta, index=1)
        assert "[2501.12345]" in output
        assert "Topological Quantum Error Correction" in output
        assert "Smith, J." in output
        assert "cs.QI" in output
        assert "https://arxiv.org/abs/2501.12345" in output

    def test_extract_arxiv_id_from_entry_id(self) -> None:
        # Late import: module under test
        from shesha.experimental.arxiv.search import extract_arxiv_id

        assert extract_arxiv_id("http://arxiv.org/abs/2501.12345v1") == "2501.12345v1"
        assert extract_arxiv_id("http://arxiv.org/abs/2501.12345") == "2501.12345"
