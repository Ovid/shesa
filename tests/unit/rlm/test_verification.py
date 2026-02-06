"""Tests for citation verification module."""

from shesha.rlm.verification import (
    Citation,
    Quote,
    VerificationResult,
    extract_citations,
    extract_quotes,
)


class TestDataclasses:
    """Tests for verification dataclasses."""

    def test_citation_construction(self) -> None:
        """Citation stores doc_id and found status."""
        c = Citation(doc_id=5, found=True)
        assert c.doc_id == 5
        assert c.found is True

    def test_quote_construction(self) -> None:
        """Quote stores text, doc_id, and found status."""
        q = Quote(text="some quoted text here", doc_id=3, found=True)
        assert q.text == "some quoted text here"
        assert q.doc_id == 3
        assert q.found is True

    def test_verification_result_construction(self) -> None:
        """VerificationResult stores citations and quotes."""
        citations = [Citation(doc_id=1, found=True)]
        quotes = [Quote(text="example quote text", doc_id=1, found=True)]
        result = VerificationResult(citations=citations, quotes=quotes)
        assert len(result.citations) == 1
        assert len(result.quotes) == 1

    def test_verification_result_all_valid(self) -> None:
        """all_valid is True when all citations and quotes are found."""
        result = VerificationResult(
            citations=[Citation(doc_id=0, found=True), Citation(doc_id=1, found=True)],
            quotes=[Quote(text="some quote text", doc_id=0, found=True)],
        )
        assert result.all_valid is True

    def test_verification_result_not_all_valid_citation(self) -> None:
        """all_valid is False when a citation is not found."""
        result = VerificationResult(
            citations=[Citation(doc_id=999, found=False)],
            quotes=[],
        )
        assert result.all_valid is False

    def test_verification_result_not_all_valid_quote(self) -> None:
        """all_valid is False when a quote is not found."""
        result = VerificationResult(
            citations=[Citation(doc_id=0, found=True)],
            quotes=[Quote(text="fabricated text here", doc_id=0, found=False)],
        )
        assert result.all_valid is False

    def test_verification_result_empty_is_valid(self) -> None:
        """Empty verification result is valid."""
        result = VerificationResult(citations=[], quotes=[])
        assert result.all_valid is True


class TestExtractCitations:
    """Tests for extract_citations()."""

    def test_doc_n_pattern(self) -> None:
        """Extracts 'Doc N' references."""
        ids = extract_citations("See Doc 5 and Doc 12 for details.")
        assert ids == [5, 12]

    def test_doc_bold_n_pattern(self) -> None:
        """Extracts 'Doc **N**' markdown bold references."""
        ids = extract_citations("Found in Doc **3** and Doc **17**.")
        assert ids == [3, 17]

    def test_standalone_bold_n_pattern(self) -> None:
        """Extracts standalone **N** references (common in summaries)."""
        ids = extract_citations("Evidence from **7** supports this.")
        assert ids == [7]

    def test_context_bracket_pattern(self) -> None:
        """Extracts context[N] references."""
        ids = extract_citations("I checked context[0] and context[42].")
        assert ids == [0, 42]

    def test_mixed_patterns(self) -> None:
        """Extracts from mixed patterns without duplicates."""
        ids = extract_citations("Doc 5 is cited. Also **5** again. And context[5].")
        assert ids == [5]

    def test_empty_input(self) -> None:
        """Returns empty list for text with no citations."""
        ids = extract_citations("No document references here.")
        assert ids == []

    def test_deduplication(self) -> None:
        """Duplicate doc IDs are deduplicated."""
        ids = extract_citations("Doc 3 and Doc 3 again.")
        assert ids == [3]

    def test_preserves_order(self) -> None:
        """Doc IDs are returned in order of first appearance."""
        ids = extract_citations("Doc 10, then Doc 2, then Doc 10 again.")
        assert ids == [10, 2]


class TestExtractQuotes:
    """Tests for extract_quotes()."""

    def test_double_quoted_strings(self) -> None:
        """Extracts double-quoted strings >= 10 chars."""
        quotes = extract_quotes('The code says "this is a longer quote" in the file.')
        assert quotes == ["this is a longer quote"]

    def test_minimum_length_filter(self) -> None:
        """Quotes shorter than 10 chars are excluded."""
        quotes = extract_quotes('He said "short" and "this is long enough".')
        assert quotes == ["this is long enough"]

    def test_multiple_quotes(self) -> None:
        """Extracts multiple qualifying quotes."""
        text = 'Found "first quote text" and "second quote text" in code.'
        quotes = extract_quotes(text)
        assert quotes == ["first quote text", "second quote text"]

    def test_empty_no_quotes(self) -> None:
        """Returns empty list when no quotes are present."""
        quotes = extract_quotes("No quoted text here.")
        assert quotes == []

    def test_backtick_quoted_strings(self) -> None:
        """Extracts backtick-quoted code references >= 10 chars."""
        quotes = extract_quotes("The function `get_all_items_from_db` does this.")
        assert quotes == ["get_all_items_from_db"]

    def test_deduplication(self) -> None:
        """Duplicate quotes are deduplicated."""
        text = 'Mentions "duplicate text here" and "duplicate text here" again.'
        quotes = extract_quotes(text)
        assert quotes == ["duplicate text here"]
