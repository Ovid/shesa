"""Tests for citation verification and report formatting."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch


class TestArxivVerifier:
    """Tests for ArxivVerifier."""

    @patch("shesha.experimental.arxiv.citations.ArxivSearcher")
    def test_verified_when_title_matches(self, mock_searcher_cls: MagicMock) -> None:
        from shesha.experimental.arxiv.citations import ArxivVerifier
        from shesha.experimental.arxiv.models import (
            ExtractedCitation,
            PaperMeta,
            VerificationStatus,
        )

        mock_searcher = MagicMock()
        mock_searcher_cls.return_value = mock_searcher
        mock_searcher.get_by_id.return_value = PaperMeta(
            arxiv_id="2301.04567",
            title="Quantum Error Correction Survey",
            authors=["Smith, J."],
            abstract="",
            published=datetime(2023, 1, 1, tzinfo=UTC),
            updated=datetime(2023, 1, 1, tzinfo=UTC),
            categories=["cs.QI"],
            primary_category="cs.QI",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/2301.04567",
        )
        verifier = ArxivVerifier(searcher=mock_searcher)
        cite = ExtractedCitation(
            key="smith2023",
            title="Quantum Error Correction Survey",
            authors=["Smith, J."],
            year="2023",
            arxiv_id="2301.04567",
        )
        result = verifier.verify(cite)
        assert result.status == VerificationStatus.VERIFIED

    @patch("shesha.experimental.arxiv.citations.ArxivSearcher")
    def test_mismatch_when_title_differs(self, mock_searcher_cls: MagicMock) -> None:
        from shesha.experimental.arxiv.citations import ArxivVerifier
        from shesha.experimental.arxiv.models import (
            ExtractedCitation,
            PaperMeta,
            VerificationStatus,
        )

        mock_searcher = MagicMock()
        mock_searcher_cls.return_value = mock_searcher
        mock_searcher.get_by_id.return_value = PaperMeta(
            arxiv_id="2301.04567",
            title="Fluid Dynamics of Turbulent Flow",
            authors=["Jones, K."],
            abstract="",
            published=datetime(2023, 1, 1, tzinfo=UTC),
            updated=datetime(2023, 1, 1, tzinfo=UTC),
            categories=["physics.flu-dyn"],
            primary_category="physics.flu-dyn",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/2301.04567",
        )
        verifier = ArxivVerifier(searcher=mock_searcher)
        cite = ExtractedCitation(
            key="smith2023",
            title="Quantum Memory Architectures",
            authors=["Smith, J."],
            year="2023",
            arxiv_id="2301.04567",
        )
        result = verifier.verify(cite)
        assert result.status == VerificationStatus.MISMATCH
        assert "Fluid Dynamics" in (result.actual_title or "")

    @patch("shesha.experimental.arxiv.citations.ArxivSearcher")
    def test_not_found_when_id_missing(self, mock_searcher_cls: MagicMock) -> None:
        from shesha.experimental.arxiv.citations import ArxivVerifier
        from shesha.experimental.arxiv.models import ExtractedCitation, VerificationStatus

        mock_searcher = MagicMock()
        mock_searcher_cls.return_value = mock_searcher
        mock_searcher.get_by_id.return_value = None

        verifier = ArxivVerifier(searcher=mock_searcher)
        cite = ExtractedCitation(
            key="x",
            title="Nonexistent",
            authors=[],
            year="2023",
            arxiv_id="9999.99999",
        )
        result = verifier.verify(cite)
        assert result.status == VerificationStatus.NOT_FOUND

    def test_unresolved_for_non_arxiv_citation(self) -> None:
        from shesha.experimental.arxiv.citations import ArxivVerifier
        from shesha.experimental.arxiv.models import ExtractedCitation, VerificationStatus

        verifier = ArxivVerifier(searcher=MagicMock())
        cite = ExtractedCitation(
            key="book2020",
            title="Some Book",
            authors=["Author"],
            year="2020",
            arxiv_id=None,
        )
        result = verifier.verify(cite)
        assert result.status == VerificationStatus.UNRESOLVED


class TestFormatCheckReport:
    """Tests for report formatting."""

    def test_format_includes_disclaimer(self) -> None:
        from shesha.experimental.arxiv.citations import format_check_report
        from shesha.experimental.arxiv.models import CheckReport

        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[],
            verification_results=[],
            llm_phrases=[],
        )
        output = format_check_report(report)
        assert "DISCLAIMER" in output
        assert "capable of making mistakes" in output

    def test_format_shows_mismatch_details(self) -> None:
        from shesha.experimental.arxiv.citations import format_check_report
        from shesha.experimental.arxiv.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        cite = ExtractedCitation(
            key="x",
            title="Quantum Memory",
            authors=[],
            year="2023",
            arxiv_id="2301.04567",
        )
        vr = VerificationResult(
            citation_key="x",
            status=VerificationStatus.MISMATCH,
            message='Cites "Quantum Memory" but actual paper is "Fluid Dynamics"',
            actual_title="Fluid Dynamics of Turbulent Flow",
            arxiv_url="https://arxiv.org/abs/2301.04567",
        )
        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[cite],
            verification_results=[vr],
            llm_phrases=[],
        )
        output = format_check_report(report)
        assert "MISMATCH" in output or "X" in output
        assert "Fluid Dynamics" in output
        assert "2301.04567" in output

    def test_format_shows_llm_phrases(self) -> None:
        from shesha.experimental.arxiv.citations import format_check_report
        from shesha.experimental.arxiv.models import CheckReport

        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[],
            verification_results=[],
            llm_phrases=[(42, "As of my last knowledge update, X is true.")],
        )
        output = format_check_report(report)
        assert "42" in output
        assert "knowledge update" in output.lower()
