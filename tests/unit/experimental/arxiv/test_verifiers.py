"""Tests for external citation verifiers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from shesha.experimental.arxiv.models import (
    ExtractedCitation,
    VerificationStatus,
)


class TestCrossRefVerifier:
    """Tests for CrossRef DOI and title verification."""

    def test_verify_by_doi_verified(self) -> None:
        from shesha.experimental.arxiv.verifiers import CrossRefVerifier

        citation = ExtractedCitation(
            key="smith2023",
            title="Quantum Error Correction",
            authors=[],
            year=None,
            doi="10.1234/example",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "message": {
                "title": ["Quantum Error Correction"],
                "DOI": "10.1234/example",
            },
        }
        with patch(
            "shesha.experimental.arxiv.verifiers.httpx.get",
            return_value=mock_response,
        ):
            verifier = CrossRefVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.VERIFIED_EXTERNAL
        assert result.source == "crossref"

    def test_verify_by_doi_not_found(self) -> None:
        from shesha.experimental.arxiv.verifiers import CrossRefVerifier

        citation = ExtractedCitation(
            key="bad",
            title="Does Not Exist",
            authors=[],
            year=None,
            doi="10.9999/nonexistent",
        )
        mock_response = MagicMock()
        mock_response.status_code = 404
        with patch(
            "shesha.experimental.arxiv.verifiers.httpx.get",
            return_value=mock_response,
        ):
            verifier = CrossRefVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.NOT_FOUND

    def test_verify_by_title_search(self) -> None:
        from shesha.experimental.arxiv.verifiers import CrossRefVerifier

        citation = ExtractedCitation(
            key="jones2023",
            title="Surface Codes Revisited",
            authors=[],
            year=None,
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "message": {"items": [{"title": ["Surface Codes Revisited"], "DOI": "10.5678/sc"}]},
        }
        with patch(
            "shesha.experimental.arxiv.verifiers.httpx.get",
            return_value=mock_response,
        ):
            verifier = CrossRefVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.VERIFIED_EXTERNAL
        assert result.source == "crossref"

    def test_verify_no_identifiers_no_title(self) -> None:
        from shesha.experimental.arxiv.verifiers import CrossRefVerifier

        citation = ExtractedCitation(key="anon", title=None, authors=[], year=None)
        verifier = CrossRefVerifier()
        result = verifier.verify(citation)
        assert result.status == VerificationStatus.UNRESOLVED

    def test_verify_uses_polite_email_in_headers(self) -> None:
        from shesha.experimental.arxiv.verifiers import CrossRefVerifier

        citation = ExtractedCitation(
            key="x",
            title="T",
            authors=[],
            year=None,
            doi="10.1234/x",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "message": {"title": ["T"], "DOI": "10.1234/x"},
        }
        with patch(
            "shesha.experimental.arxiv.verifiers.httpx.get",
            return_value=mock_response,
        ) as mock_get:
            verifier = CrossRefVerifier(polite_email="user@example.com")
            verifier.verify(citation)
        call_kwargs = mock_get.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        user_agent = headers.get("User-Agent", "")
        assert "mailto:user@example.com" in user_agent

    def test_verify_network_error_returns_unresolved(self) -> None:
        from shesha.experimental.arxiv.verifiers import CrossRefVerifier

        citation = ExtractedCitation(key="x", title="T", authors=[], year=None, doi="10.1234/x")
        with patch(
            "shesha.experimental.arxiv.verifiers.httpx.get",
            side_effect=Exception("timeout"),
        ):
            verifier = CrossRefVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.UNRESOLVED


class TestOpenAlexVerifier:
    """Tests for OpenAlex title search verification."""

    def test_verify_title_match(self) -> None:
        from shesha.experimental.arxiv.verifiers import OpenAlexVerifier

        citation = ExtractedCitation(
            key="smith2023",
            title="Quantum Error Correction",
            authors=[],
            year=None,
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Quantum Error Correction",
                    "doi": "https://doi.org/10.1234/x",
                }
            ]
        }
        with patch(
            "shesha.experimental.arxiv.verifiers.httpx.get",
            return_value=mock_response,
        ):
            verifier = OpenAlexVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.VERIFIED_EXTERNAL
        assert result.source == "openalex"

    def test_verify_no_results(self) -> None:
        from shesha.experimental.arxiv.verifiers import OpenAlexVerifier

        citation = ExtractedCitation(
            key="x", title="Nonexistent Paper Title", authors=[], year=None
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        with patch(
            "shesha.experimental.arxiv.verifiers.httpx.get",
            return_value=mock_response,
        ):
            verifier = OpenAlexVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.UNRESOLVED

    def test_verify_no_title_returns_unresolved(self) -> None:
        from shesha.experimental.arxiv.verifiers import OpenAlexVerifier

        citation = ExtractedCitation(key="x", title=None, authors=[], year=None)
        verifier = OpenAlexVerifier()
        result = verifier.verify(citation)
        assert result.status == VerificationStatus.UNRESOLVED

    def test_polite_email_in_query_params(self) -> None:
        from shesha.experimental.arxiv.verifiers import OpenAlexVerifier

        citation = ExtractedCitation(key="x", title="Test", authors=[], year=None)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        with patch(
            "shesha.experimental.arxiv.verifiers.httpx.get",
            return_value=mock_response,
        ) as mock_get:
            verifier = OpenAlexVerifier(polite_email="user@example.com")
            verifier.verify(citation)
        call_args = mock_get.call_args
        params = call_args.kwargs.get("params") or call_args[1].get("params", {})
        assert params.get("mailto") == "user@example.com"


class TestSemanticScholarVerifier:
    """Tests for Semantic Scholar title search verification."""

    def test_verify_title_match(self) -> None:
        from shesha.experimental.arxiv.verifiers import SemanticScholarVerifier

        citation = ExtractedCitation(
            key="x", title="Quantum Error Correction", authors=[], year=None
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"title": "Quantum Error Correction", "paperId": "abc123"}]
        }
        with patch(
            "shesha.experimental.arxiv.verifiers.httpx.get",
            return_value=mock_response,
        ):
            verifier = SemanticScholarVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.VERIFIED_EXTERNAL
        assert result.source == "semantic_scholar"

    def test_verify_no_results(self) -> None:
        from shesha.experimental.arxiv.verifiers import SemanticScholarVerifier

        citation = ExtractedCitation(key="x", title="Nonexistent Paper", authors=[], year=None)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        with patch(
            "shesha.experimental.arxiv.verifiers.httpx.get",
            return_value=mock_response,
        ):
            verifier = SemanticScholarVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.UNRESOLVED

    def test_verify_rate_limited_returns_unresolved(self) -> None:
        from shesha.experimental.arxiv.verifiers import SemanticScholarVerifier

        citation = ExtractedCitation(key="x", title="Test", authors=[], year=None)
        mock_response = MagicMock()
        mock_response.status_code = 429
        with patch(
            "shesha.experimental.arxiv.verifiers.httpx.get",
            return_value=mock_response,
        ):
            verifier = SemanticScholarVerifier()
            result = verifier.verify(citation)
        assert result.status == VerificationStatus.UNRESOLVED

    def test_respects_1_second_rate_limit(self) -> None:
        from shesha.experimental.arxiv.verifiers import SemanticScholarVerifier

        verifier = SemanticScholarVerifier()
        assert verifier._limiter._min_interval >= 1.0
