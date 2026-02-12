# Citation Verification Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add multi-source citation verification (CrossRef, OpenAlex, Semantic Scholar), fuzzy title matching with LLM fallback, topical relevance checking, and UI improvements to reduce false positives and noise in citation reports.

**Architecture:** Cascading verification pipeline where citations are checked against arXiv first, then external APIs (CrossRef, OpenAlex, Semantic Scholar) by DOI or title search. Fuzzy title matching (Jaccard similarity) with LLM fallback for ambiguous cases. Batched LLM-based topical relevance check per paper. Frontend email modal for API polite-pool access. All external APIs are free and keyless.

**Tech Stack:** Python (httpx for HTTP, litellm for LLM calls), React/TypeScript frontend, FastAPI WebSocket backend.

**Design doc:** `docs/plans/2026-02-12-citation-verification-upgrade-design.md`

---

### Task 1: Extend Data Models

**Files:**
- Modify: `src/shesha/experimental/arxiv/models.py`
- Test: `tests/unit/experimental/arxiv/test_citations.py`

**Step 1: Write the failing test**

Add to `tests/unit/experimental/arxiv/test_citations.py`:

```python
class TestVerificationStatusExtended:
    """Tests for new verification statuses."""

    def test_verified_external_status_exists(self) -> None:
        from shesha.experimental.arxiv.models import VerificationStatus

        assert VerificationStatus.VERIFIED_EXTERNAL.value == "verified_external"

    def test_topically_unrelated_status_exists(self) -> None:
        from shesha.experimental.arxiv.models import VerificationStatus

        assert VerificationStatus.TOPICALLY_UNRELATED.value == "topically_unrelated"


class TestVerificationResultSource:
    """Tests for source field on VerificationResult."""

    def test_source_defaults_to_none(self) -> None:
        from shesha.experimental.arxiv.models import VerificationResult, VerificationStatus

        result = VerificationResult(
            citation_key="key1",
            status=VerificationStatus.VERIFIED,
        )
        assert result.source is None

    def test_source_can_be_set(self) -> None:
        from shesha.experimental.arxiv.models import VerificationResult, VerificationStatus

        result = VerificationResult(
            citation_key="key1",
            status=VerificationStatus.VERIFIED_EXTERNAL,
            source="crossref",
        )
        assert result.source == "crossref"


class TestCheckReportVerifiedExternal:
    """Tests that VERIFIED_EXTERNAL counts as verified."""

    def test_verified_external_counted_in_verified_count(self) -> None:
        from shesha.experimental.arxiv.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        citations = [
            ExtractedCitation(key="a", title="T1", authors=[], year=None),
            ExtractedCitation(key="b", title="T2", authors=[], year=None),
        ]
        results = [
            VerificationResult(citation_key="a", status=VerificationStatus.VERIFIED),
            VerificationResult(
                citation_key="b", status=VerificationStatus.VERIFIED_EXTERNAL, source="openalex"
            ),
        ]
        report = CheckReport(
            arxiv_id="2301.00001",
            title="Test",
            citations=citations,
            verification_results=results,
            llm_phrases=[],
        )
        assert report.verified_count == 2
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/experimental/arxiv/test_citations.py::TestVerificationStatusExtended -v`
Run: `pytest tests/unit/experimental/arxiv/test_citations.py::TestVerificationResultSource -v`
Run: `pytest tests/unit/experimental/arxiv/test_citations.py::TestCheckReportVerifiedExternal -v`
Expected: FAIL — `VERIFIED_EXTERNAL`, `TOPICALLY_UNRELATED` don't exist; `source` field doesn't exist

**Step 3: Write minimal implementation**

In `src/shesha/experimental/arxiv/models.py`:

1. Add to `VerificationStatus` enum (after line 76):
```python
    VERIFIED_EXTERNAL = "verified_external"
    TOPICALLY_UNRELATED = "topically_unrelated"
```

2. Add `source` field to `VerificationResult` (after line 101):
```python
    source: str | None = None  # "arxiv", "crossref", "openalex", "semantic_scholar"
```

3. Update `CheckReport.verified_count` to include `VERIFIED_EXTERNAL` (line 140):
```python
    return sum(
        1
        for r in self.verification_results
        if r.status in (VerificationStatus.VERIFIED, VerificationStatus.VERIFIED_EXTERNAL)
    )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/experimental/arxiv/test_citations.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/arxiv/models.py tests/unit/experimental/arxiv/test_citations.py
git commit -m "feat: extend VerificationStatus with VERIFIED_EXTERNAL and TOPICALLY_UNRELATED"
```

---

### Task 2: Fuzzy Title Matching

**Files:**
- Modify: `src/shesha/experimental/arxiv/citations.py`
- Test: `tests/unit/experimental/arxiv/test_citations.py`

**Step 1: Write the failing tests**

Add to `tests/unit/experimental/arxiv/test_citations.py`:

```python
class TestFuzzyTitleMatch:
    """Tests for Jaccard-based fuzzy title matching."""

    def test_exact_match_returns_high_score(self) -> None:
        from shesha.experimental.arxiv.citations import title_similarity

        assert title_similarity("Quantum Error Correction", "Quantum Error Correction") == 1.0

    def test_contained_title_returns_high_score(self) -> None:
        from shesha.experimental.arxiv.citations import title_similarity

        score = title_similarity("Chess Strategies", "Chess Strategies: A Survey")
        assert score >= 0.5

    def test_reordered_words_returns_high_score(self) -> None:
        from shesha.experimental.arxiv.citations import title_similarity

        score = title_similarity(
            "Learning to Play Chess from Textbooks",
            "From Textbooks Learning to Play Chess",
        )
        assert score >= 0.85

    def test_completely_different_returns_low_score(self) -> None:
        from shesha.experimental.arxiv.citations import title_similarity

        score = title_similarity(
            "Quantum Error Correction Survey",
            "Sentiment Analysis of Victorian Novels",
        )
        assert score < 0.5

    def test_acronym_expansion_moderate_score(self) -> None:
        from shesha.experimental.arxiv.citations import title_similarity

        score = title_similarity(
            "Learning Chess from Text",
            "LEAP: Learning to Play Chess from Textbooks",
        )
        # Should be in ambiguous range (0.5-0.85) — LLM would decide
        assert 0.3 < score < 1.0

    def test_empty_titles(self) -> None:
        from shesha.experimental.arxiv.citations import title_similarity

        assert title_similarity("", "") == 0.0

    def test_latex_commands_stripped(self) -> None:
        from shesha.experimental.arxiv.citations import title_similarity

        score = title_similarity(
            r"\emph{Quantum} Error \textbf{Correction}",
            "Quantum Error Correction",
        )
        assert score == 1.0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/experimental/arxiv/test_citations.py::TestFuzzyTitleMatch -v`
Expected: FAIL — `title_similarity` doesn't exist

**Step 3: Write minimal implementation**

In `src/shesha/experimental/arxiv/citations.py`, add a new public function (after the existing `_titles_match`):

```python
def _normalize_title(t: str) -> str:
    """Normalize a title for comparison."""
    t = re.sub(r"\\[a-zA-Z]+", "", t)  # Strip LaTeX commands
    t = re.sub(r"[^\w\s]", "", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def title_similarity(cited: str, actual: str) -> float:
    """Compute Jaccard similarity between two titles (word-set overlap).

    Returns a float between 0.0 and 1.0.
    """
    c_words = set(_normalize_title(cited).split())
    a_words = set(_normalize_title(actual).split())
    if not c_words and not a_words:
        return 0.0
    if not c_words or not a_words:
        return 0.0
    intersection = c_words & a_words
    union = c_words | a_words
    return len(intersection) / len(union)
```

Update `_titles_match` to use `_normalize_title` (refactor — extract the inner `normalize`):

```python
def _titles_match(cited: str, actual: str) -> bool:
    """Fuzzy title comparison -- normalize and check containment."""
    c, a = _normalize_title(cited), _normalize_title(actual)
    return c == a or c in a or a in c
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/experimental/arxiv/test_citations.py -v`
Expected: All PASS (both old and new tests)

**Step 5: Commit**

```bash
git add src/shesha/experimental/arxiv/citations.py tests/unit/experimental/arxiv/test_citations.py
git commit -m "feat: add Jaccard-based title_similarity for fuzzy citation matching"
```

---

### Task 3: Rate Limiter Utility

**Files:**
- Create: `src/shesha/experimental/arxiv/rate_limit.py`
- Test: `tests/unit/experimental/arxiv/test_rate_limit.py`

**Step 1: Write the failing tests**

Create `tests/unit/experimental/arxiv/test_rate_limit.py`:

```python
"""Tests for rate limiter utility."""

from __future__ import annotations

import time

from shesha.experimental.arxiv.rate_limit import RateLimiter


class TestRateLimiter:
    """Tests for the RateLimiter class."""

    def test_first_call_not_delayed(self) -> None:
        limiter = RateLimiter(min_interval=1.0)
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    def test_second_call_delayed(self) -> None:
        limiter = RateLimiter(min_interval=0.2)
        limiter.wait()
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.15  # Allow small tolerance

    def test_no_delay_after_interval_elapsed(self) -> None:
        limiter = RateLimiter(min_interval=0.1)
        limiter.wait()
        time.sleep(0.15)  # Wait longer than interval
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed < 0.05

    def test_backoff_delays_next_call(self) -> None:
        limiter = RateLimiter(min_interval=0.05)
        limiter.wait()
        limiter.backoff(retry_after=0.2)
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.15  # Allow small tolerance

    def test_backoff_default_is_5x_interval(self) -> None:
        limiter = RateLimiter(min_interval=0.04)
        limiter.wait()
        limiter.backoff()  # Should default to 0.04 * 5 = 0.2
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.15
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/experimental/arxiv/test_rate_limit.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Write minimal implementation**

Create `src/shesha/experimental/arxiv/rate_limit.py`:

```python
"""Rate limiter for external API calls."""

from __future__ import annotations

import time


class RateLimiter:
    """Rate limiter that enforces a minimum interval and handles 429 backoff."""

    def __init__(self, min_interval: float) -> None:
        self._min_interval = min_interval
        self._last_call: float = 0.0
        self._backoff_until: float = 0.0

    def wait(self) -> None:
        """Block until the minimum interval has elapsed since the last call."""
        now = time.monotonic()
        # Respect backoff from 429 responses
        if self._backoff_until > now:
            time.sleep(self._backoff_until - now)
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval and self._last_call > 0:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    def backoff(self, retry_after: float | None = None) -> None:
        """Set a backoff period (e.g., after a 429 response).

        Args:
            retry_after: Seconds to wait. Defaults to 5x the min_interval.
        """
        delay = retry_after if retry_after is not None else self._min_interval * 5
        self._backoff_until = time.monotonic() + delay
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/experimental/arxiv/test_rate_limit.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/arxiv/rate_limit.py tests/unit/experimental/arxiv/test_rate_limit.py
git commit -m "feat: add RateLimiter utility for external API calls"
```

---

### Task 4: CrossRefVerifier

**Files:**
- Create: `src/shesha/experimental/arxiv/verifiers.py`
- Test: `tests/unit/experimental/arxiv/test_verifiers.py`

**Context:** `httpx` is already in `dev` dependencies. The CrossRef API is free, no key needed. For polite pool, include `mailto:` in User-Agent header.

**Step 1: Write the failing tests**

Create `tests/unit/experimental/arxiv/test_verifiers.py`:

```python
"""Tests for external citation verifiers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from shesha.experimental.arxiv.models import (
    ExtractedCitation,
    VerificationResult,
    VerificationStatus,
)


class TestCrossRefVerifier:
    """Tests for CrossRef DOI and title verification."""

    def test_verify_by_doi_verified(self) -> None:
        """A citation with DOI that matches title returns VERIFIED_EXTERNAL."""
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
            "message": {"title": ["Quantum Error Correction"], "DOI": "10.1234/example"},
        }

        with patch("shesha.experimental.arxiv.verifiers.httpx.get", return_value=mock_response):
            verifier = CrossRefVerifier()
            result = verifier.verify(citation)

        assert result.status == VerificationStatus.VERIFIED_EXTERNAL
        assert result.source == "crossref"

    def test_verify_by_doi_not_found(self) -> None:
        """A citation with DOI that doesn't exist returns NOT_FOUND."""
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

        with patch("shesha.experimental.arxiv.verifiers.httpx.get", return_value=mock_response):
            verifier = CrossRefVerifier()
            result = verifier.verify(citation)

        assert result.status == VerificationStatus.NOT_FOUND

    def test_verify_by_title_search(self) -> None:
        """A citation without DOI/arXiv falls back to title search."""
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
            "message": {
                "items": [
                    {"title": ["Surface Codes Revisited"], "DOI": "10.5678/sc"},
                ]
            },
        }

        with patch("shesha.experimental.arxiv.verifiers.httpx.get", return_value=mock_response):
            verifier = CrossRefVerifier()
            result = verifier.verify(citation)

        assert result.status == VerificationStatus.VERIFIED_EXTERNAL
        assert result.source == "crossref"

    def test_verify_no_identifiers_no_title(self) -> None:
        """A citation with no DOI, no arXiv ID, no title returns UNRESOLVED."""
        from shesha.experimental.arxiv.verifiers import CrossRefVerifier

        citation = ExtractedCitation(
            key="anon",
            title=None,
            authors=[],
            year=None,
        )

        verifier = CrossRefVerifier()
        result = verifier.verify(citation)
        assert result.status == VerificationStatus.UNRESOLVED

    def test_verify_uses_polite_email_in_headers(self) -> None:
        """When email is provided, it's included in User-Agent header."""
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

        with patch("shesha.experimental.arxiv.verifiers.httpx.get", return_value=mock_response) as mock_get:
            verifier = CrossRefVerifier(polite_email="user@example.com")
            verifier.verify(citation)

        call_kwargs = mock_get.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        user_agent = headers.get("User-Agent", "")
        assert "mailto:user@example.com" in user_agent

    def test_verify_network_error_returns_unresolved(self) -> None:
        """Network errors return UNRESOLVED, not crash."""
        from shesha.experimental.arxiv.verifiers import CrossRefVerifier

        citation = ExtractedCitation(
            key="x", title="T", authors=[], year=None, doi="10.1234/x"
        )

        with patch("shesha.experimental.arxiv.verifiers.httpx.get", side_effect=Exception("timeout")):
            verifier = CrossRefVerifier()
            result = verifier.verify(citation)

        assert result.status == VerificationStatus.UNRESOLVED
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/experimental/arxiv/test_verifiers.py::TestCrossRefVerifier -v`
Expected: FAIL — module doesn't exist

**Step 3: Write minimal implementation**

Create `src/shesha/experimental/arxiv/verifiers.py`:

```python
"""External citation verifiers (CrossRef, OpenAlex, Semantic Scholar)."""

from __future__ import annotations

import httpx

from shesha.experimental.arxiv.citations import title_similarity
from shesha.experimental.arxiv.models import (
    ExtractedCitation,
    VerificationResult,
    VerificationStatus,
)
from shesha.experimental.arxiv.rate_limit import RateLimiter

# Thresholds for fuzzy title matching
MATCH_THRESHOLD = 0.85  # Above this = confident match
NO_MATCH_THRESHOLD = 0.50  # Below this = no match

_REQUEST_TIMEOUT = 15.0


class CrossRefVerifier:
    """Verify citations using the CrossRef API."""

    def __init__(self, polite_email: str | None = None) -> None:
        self._email = polite_email
        # Polite pool gets faster rate; default is conservative
        self._limiter = RateLimiter(min_interval=0.5 if polite_email else 1.0)

    def _headers(self) -> dict[str, str]:
        ua = "shesha-citation-checker/1.0"
        if self._email:
            ua += f" (mailto:{self._email})"
        return {"User-Agent": ua}

    def verify(self, citation: ExtractedCitation) -> VerificationResult:
        """Verify a citation via CrossRef (by DOI or title search)."""
        if citation.doi:
            return self._verify_by_doi(citation)
        if citation.title:
            return self._verify_by_title(citation)
        return VerificationResult(
            citation_key=citation.key,
            status=VerificationStatus.UNRESOLVED,
            message="No DOI or title to search",
        )

    def _verify_by_doi(self, citation: ExtractedCitation) -> VerificationResult:
        try:
            self._limiter.wait()
            resp = httpx.get(
                f"https://api.crossref.org/works/{citation.doi}",
                headers=self._headers(),
                timeout=_REQUEST_TIMEOUT,
            )
        except Exception:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message="CrossRef API request failed",
            )

        if resp.status_code == 404:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.NOT_FOUND,
                message=f"DOI {citation.doi} not found on CrossRef",
                severity="error",
            )
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "5"))
            self._limiter.backoff(retry_after=retry_after)
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message="CrossRef rate limited, will retry later",
            )
        if resp.status_code != 200:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message=f"CrossRef returned status {resp.status_code}",
            )

        data = resp.json().get("message", {})
        found_titles = data.get("title", [])
        found_title = found_titles[0] if found_titles else None

        if citation.title and found_title:
            sim = title_similarity(citation.title, found_title)
            if sim >= MATCH_THRESHOLD:
                return VerificationResult(
                    citation_key=citation.key,
                    status=VerificationStatus.VERIFIED_EXTERNAL,
                    source="crossref",
                    actual_title=found_title,
                )
            if sim < NO_MATCH_THRESHOLD:
                return VerificationResult(
                    citation_key=citation.key,
                    status=VerificationStatus.MISMATCH,
                    message=f'Cites "{citation.title}" but DOI resolves to "{found_title}"',
                    actual_title=found_title,
                    severity="warning",
                    source="crossref",
                )
            # Ambiguous (0.50-0.85) — return with actual_title for LLM fallback in orchestrator
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                source="crossref",
                actual_title=found_title,
                message=f"Title match ambiguous (similarity={sim:.2f})",
            )

        # DOI exists but no title to compare — count as verified
        return VerificationResult(
            citation_key=citation.key,
            status=VerificationStatus.VERIFIED_EXTERNAL,
            source="crossref",
        )

    def _verify_by_title(self, citation: ExtractedCitation) -> VerificationResult:
        try:
            self._limiter.wait()
            resp = httpx.get(
                "https://api.crossref.org/works",
                params={"query.title": citation.title, "rows": "3"},
                headers=self._headers(),
                timeout=_REQUEST_TIMEOUT,
            )
        except Exception:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message="CrossRef title search failed",
            )

        if resp.status_code != 200:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message=f"CrossRef returned status {resp.status_code}",
            )

        items = resp.json().get("message", {}).get("items", [])
        for item in items:
            found_titles = item.get("title", [])
            found_title = found_titles[0] if found_titles else None
            if found_title and citation.title:
                sim = title_similarity(citation.title, found_title)
                if sim >= MATCH_THRESHOLD:
                    return VerificationResult(
                        citation_key=citation.key,
                        status=VerificationStatus.VERIFIED_EXTERNAL,
                        source="crossref",
                        actual_title=found_title,
                    )

        return VerificationResult(
            citation_key=citation.key,
            status=VerificationStatus.UNRESOLVED,
            message="No matching title found on CrossRef",
        )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/experimental/arxiv/test_verifiers.py::TestCrossRefVerifier -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/arxiv/verifiers.py tests/unit/experimental/arxiv/test_verifiers.py
git commit -m "feat: add CrossRefVerifier for DOI and title-based citation verification"
```

---

### Task 5: OpenAlexVerifier

**Files:**
- Modify: `src/shesha/experimental/arxiv/verifiers.py`
- Modify: `tests/unit/experimental/arxiv/test_verifiers.py`

**Step 1: Write the failing tests**

Add to `tests/unit/experimental/arxiv/test_verifiers.py`:

```python
class TestOpenAlexVerifier:
    """Tests for OpenAlex title search verification."""

    def test_verify_title_match(self) -> None:
        from shesha.experimental.arxiv.verifiers import OpenAlexVerifier

        citation = ExtractedCitation(
            key="smith2023", title="Quantum Error Correction", authors=[], year=None
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"title": "Quantum Error Correction", "doi": "https://doi.org/10.1234/x"},
            ]
        }

        with patch("shesha.experimental.arxiv.verifiers.httpx.get", return_value=mock_response):
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

        with patch("shesha.experimental.arxiv.verifiers.httpx.get", return_value=mock_response):
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

        citation = ExtractedCitation(
            key="x", title="Test", authors=[], year=None
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        with patch("shesha.experimental.arxiv.verifiers.httpx.get", return_value=mock_response) as mock_get:
            verifier = OpenAlexVerifier(polite_email="user@example.com")
            verifier.verify(citation)

        call_args = mock_get.call_args
        params = call_args.kwargs.get("params") or call_args[1].get("params", {})
        assert params.get("mailto") == "user@example.com"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/experimental/arxiv/test_verifiers.py::TestOpenAlexVerifier -v`
Expected: FAIL — `OpenAlexVerifier` doesn't exist

**Step 3: Write minimal implementation**

Add to `src/shesha/experimental/arxiv/verifiers.py`:

```python
class OpenAlexVerifier:
    """Verify citations using the OpenAlex API."""

    def __init__(self, polite_email: str | None = None) -> None:
        self._email = polite_email
        # Polite pool gets faster rate; default is conservative
        self._limiter = RateLimiter(min_interval=0.5 if polite_email else 1.0)

    def verify(self, citation: ExtractedCitation) -> VerificationResult:
        """Verify a citation via OpenAlex title search."""
        if not citation.title:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message="No title to search",
            )

        params: dict[str, str] = {"search": citation.title, "per_page": "3"}
        if self._email:
            params["mailto"] = self._email

        try:
            self._limiter.wait()
            resp = httpx.get(
                "https://api.openalex.org/works",
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
        except Exception:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message="OpenAlex API request failed",
            )

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "5"))
            self._limiter.backoff(retry_after=retry_after)
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message="OpenAlex rate limited, will retry later",
            )
        if resp.status_code != 200:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message=f"OpenAlex returned status {resp.status_code}",
            )

        results = resp.json().get("results", [])
        best_sim = 0.0
        best_title: str | None = None
        for item in results:
            found_title = item.get("title")
            if found_title and citation.title:
                sim = title_similarity(citation.title, found_title)
                if sim >= MATCH_THRESHOLD:
                    return VerificationResult(
                        citation_key=citation.key,
                        status=VerificationStatus.VERIFIED_EXTERNAL,
                        source="openalex",
                        actual_title=found_title,
                    )
                if sim > best_sim:
                    best_sim = sim
                    best_title = found_title

        # Return ambiguous match for LLM fallback in orchestrator
        if best_sim >= NO_MATCH_THRESHOLD and best_title:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                source="openalex",
                actual_title=best_title,
                message=f"Title match ambiguous (similarity={best_sim:.2f})",
            )

        return VerificationResult(
            citation_key=citation.key,
            status=VerificationStatus.UNRESOLVED,
            message="No matching title found on OpenAlex",
        )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/experimental/arxiv/test_verifiers.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/arxiv/verifiers.py tests/unit/experimental/arxiv/test_verifiers.py
git commit -m "feat: add OpenAlexVerifier for title-based citation verification"
```

---

### Task 6: SemanticScholarVerifier

**Files:**
- Modify: `src/shesha/experimental/arxiv/verifiers.py`
- Modify: `tests/unit/experimental/arxiv/test_verifiers.py`

**Step 1: Write the failing tests**

Add to `tests/unit/experimental/arxiv/test_verifiers.py`:

```python
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

        with patch("shesha.experimental.arxiv.verifiers.httpx.get", return_value=mock_response):
            verifier = SemanticScholarVerifier()
            result = verifier.verify(citation)

        assert result.status == VerificationStatus.VERIFIED_EXTERNAL
        assert result.source == "semantic_scholar"

    def test_verify_no_results(self) -> None:
        from shesha.experimental.arxiv.verifiers import SemanticScholarVerifier

        citation = ExtractedCitation(
            key="x", title="Nonexistent Paper", authors=[], year=None
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}

        with patch("shesha.experimental.arxiv.verifiers.httpx.get", return_value=mock_response):
            verifier = SemanticScholarVerifier()
            result = verifier.verify(citation)

        assert result.status == VerificationStatus.UNRESOLVED

    def test_verify_rate_limited_returns_unresolved(self) -> None:
        from shesha.experimental.arxiv.verifiers import SemanticScholarVerifier

        citation = ExtractedCitation(
            key="x", title="Test", authors=[], year=None
        )

        mock_response = MagicMock()
        mock_response.status_code = 429

        with patch("shesha.experimental.arxiv.verifiers.httpx.get", return_value=mock_response):
            verifier = SemanticScholarVerifier()
            result = verifier.verify(citation)

        assert result.status == VerificationStatus.UNRESOLVED

    def test_respects_1_second_rate_limit(self) -> None:
        """Semantic Scholar free tier requires 1 req/sec."""
        from shesha.experimental.arxiv.verifiers import SemanticScholarVerifier

        verifier = SemanticScholarVerifier()
        assert verifier._limiter._min_interval >= 1.0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/experimental/arxiv/test_verifiers.py::TestSemanticScholarVerifier -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Add to `src/shesha/experimental/arxiv/verifiers.py`:

```python
class SemanticScholarVerifier:
    """Verify citations using the Semantic Scholar API."""

    def __init__(self) -> None:
        self._limiter = RateLimiter(min_interval=1.0)

    def verify(self, citation: ExtractedCitation) -> VerificationResult:
        """Verify a citation via Semantic Scholar title search."""
        if not citation.title:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message="No title to search",
            )

        try:
            self._limiter.wait()
            resp = httpx.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={"query": citation.title, "limit": "3", "fields": "title"},
                timeout=_REQUEST_TIMEOUT,
            )
        except Exception:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message="Semantic Scholar API request failed",
            )

        if resp.status_code != 200:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message=f"Semantic Scholar returned status {resp.status_code}",
            )

        results = resp.json().get("data", [])
        best_sim = 0.0
        best_title: str | None = None
        for item in results:
            found_title = item.get("title")
            if found_title and citation.title:
                sim = title_similarity(citation.title, found_title)
                if sim >= MATCH_THRESHOLD:
                    return VerificationResult(
                        citation_key=citation.key,
                        status=VerificationStatus.VERIFIED_EXTERNAL,
                        source="semantic_scholar",
                        actual_title=found_title,
                    )
                if sim > best_sim:
                    best_sim = sim
                    best_title = found_title

        # Return ambiguous match for LLM fallback in orchestrator
        if best_sim >= NO_MATCH_THRESHOLD and best_title:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                source="semantic_scholar",
                actual_title=best_title,
                message=f"Title match ambiguous (similarity={best_sim:.2f})",
            )

        return VerificationResult(
            citation_key=citation.key,
            status=VerificationStatus.UNRESOLVED,
            message="No matching title found on Semantic Scholar",
        )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/experimental/arxiv/test_verifiers.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/arxiv/verifiers.py tests/unit/experimental/arxiv/test_verifiers.py
git commit -m "feat: add SemanticScholarVerifier for title-based citation verification"
```

---

### Task 7: Cascading Verification Orchestrator

**Files:**
- Modify: `src/shesha/experimental/arxiv/verifiers.py`
- Modify: `tests/unit/experimental/arxiv/test_verifiers.py`

**Context:** The orchestrator tries verifiers in order: ArxivVerifier (if arXiv ID) → CrossRefVerifier (if DOI) → OpenAlexVerifier (title) → SemanticScholarVerifier (title) → CrossRefVerifier title search. Stops at first confident result.

**Step 1: Write the failing tests**

Add to `tests/unit/experimental/arxiv/test_verifiers.py`:

```python
class TestCascadingVerifier:
    """Tests for the cascading verification orchestrator."""

    def test_arxiv_id_uses_arxiv_verifier_first(self) -> None:
        from shesha.experimental.arxiv.verifiers import CascadingVerifier

        citation = ExtractedCitation(
            key="x", title="T", authors=[], year=None, arxiv_id="2301.00001"
        )

        mock_arxiv = MagicMock()
        mock_arxiv.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.VERIFIED, source="arxiv"
        )

        verifier = CascadingVerifier(arxiv_verifier=mock_arxiv)
        result = verifier.verify(citation)

        assert result.status == VerificationStatus.VERIFIED
        mock_arxiv.verify.assert_called_once()

    def test_arxiv_not_found_falls_through_to_external(self) -> None:
        from shesha.experimental.arxiv.verifiers import CascadingVerifier

        citation = ExtractedCitation(
            key="x", title="Some Paper", authors=[], year=None, arxiv_id="2301.99999"
        )

        mock_arxiv = MagicMock()
        mock_arxiv.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.NOT_FOUND, severity="error"
        )

        mock_openalex = MagicMock()
        mock_openalex.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.VERIFIED_EXTERNAL, source="openalex"
        )

        verifier = CascadingVerifier(
            arxiv_verifier=mock_arxiv, openalex_verifier=mock_openalex
        )
        result = verifier.verify(citation)

        assert result.status == VerificationStatus.VERIFIED_EXTERNAL

    def test_doi_uses_crossref_first(self) -> None:
        from shesha.experimental.arxiv.verifiers import CascadingVerifier

        citation = ExtractedCitation(
            key="x", title="T", authors=[], year=None, doi="10.1234/example"
        )

        mock_crossref = MagicMock()
        mock_crossref.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.VERIFIED_EXTERNAL, source="crossref"
        )

        verifier = CascadingVerifier(crossref_verifier=mock_crossref)
        result = verifier.verify(citation)

        assert result.status == VerificationStatus.VERIFIED_EXTERNAL
        assert result.source == "crossref"

    def test_title_only_cascades_through_external_verifiers(self) -> None:
        from shesha.experimental.arxiv.verifiers import CascadingVerifier

        citation = ExtractedCitation(
            key="x", title="Some Paper", authors=[], year=None
        )

        mock_openalex = MagicMock()
        mock_openalex.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.UNRESOLVED
        )
        mock_s2 = MagicMock()
        mock_s2.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.VERIFIED_EXTERNAL, source="semantic_scholar"
        )

        verifier = CascadingVerifier(
            openalex_verifier=mock_openalex, semantic_scholar_verifier=mock_s2
        )
        result = verifier.verify(citation)

        assert result.status == VerificationStatus.VERIFIED_EXTERNAL
        assert result.source == "semantic_scholar"

    def test_all_fail_returns_unresolved(self) -> None:
        from shesha.experimental.arxiv.verifiers import CascadingVerifier

        citation = ExtractedCitation(
            key="x", title="Totally Unknown Paper", authors=[], year=None
        )

        mock_openalex = MagicMock()
        mock_openalex.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.UNRESOLVED
        )
        mock_s2 = MagicMock()
        mock_s2.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.UNRESOLVED
        )
        mock_crossref = MagicMock()
        mock_crossref.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.UNRESOLVED
        )

        verifier = CascadingVerifier(
            openalex_verifier=mock_openalex,
            semantic_scholar_verifier=mock_s2,
            crossref_verifier=mock_crossref,
        )
        result = verifier.verify(citation)

        assert result.status == VerificationStatus.UNRESOLVED

    def test_stops_at_first_verified(self) -> None:
        """Should not call later verifiers once one succeeds."""
        from shesha.experimental.arxiv.verifiers import CascadingVerifier

        citation = ExtractedCitation(
            key="x", title="Found Paper", authors=[], year=None
        )

        mock_openalex = MagicMock()
        mock_openalex.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.VERIFIED_EXTERNAL, source="openalex"
        )
        mock_s2 = MagicMock()

        verifier = CascadingVerifier(
            openalex_verifier=mock_openalex, semantic_scholar_verifier=mock_s2
        )
        verifier.verify(citation)

        mock_s2.verify.assert_not_called()

    def test_ambiguous_match_triggers_llm_judgment(self) -> None:
        """When fuzzy match is ambiguous (0.50-0.85), LLM is consulted."""
        from shesha.experimental.arxiv.verifiers import CascadingVerifier

        citation = ExtractedCitation(
            key="x", title="Learning Chess from Text", authors=[], year=None
        )

        # OpenAlex returns ambiguous match
        mock_openalex = MagicMock()
        mock_openalex.verify.return_value = VerificationResult(
            citation_key="x",
            status=VerificationStatus.UNRESOLVED,
            source="openalex",
            actual_title="LEAP: Learning to Play Chess from Textbooks",
            message="Title match ambiguous (similarity=0.65)",
        )

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "YES. These are the same paper."

        with patch("shesha.experimental.arxiv.verifiers.litellm.completion", return_value=mock_completion):
            verifier = CascadingVerifier(
                openalex_verifier=mock_openalex, model="test-model"
            )
            result = verifier.verify(citation)

        assert result.status == VerificationStatus.VERIFIED_EXTERNAL
        assert "LLM title judgment" in (result.message or "")

    def test_ambiguous_match_llm_says_no(self) -> None:
        """When LLM says NO for ambiguous match, continues to next verifier."""
        from shesha.experimental.arxiv.verifiers import CascadingVerifier

        citation = ExtractedCitation(
            key="x", title="Chess Engine Analysis", authors=[], year=None
        )

        mock_openalex = MagicMock()
        mock_openalex.verify.return_value = VerificationResult(
            citation_key="x",
            status=VerificationStatus.UNRESOLVED,
            source="openalex",
            actual_title="Chess Board Manufacturing Analysis",
            message="Title match ambiguous (similarity=0.55)",
        )

        mock_s2 = MagicMock()
        mock_s2.verify.return_value = VerificationResult(
            citation_key="x", status=VerificationStatus.UNRESOLVED
        )

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "NO. Different papers."

        with patch("shesha.experimental.arxiv.verifiers.litellm.completion", return_value=mock_completion):
            verifier = CascadingVerifier(
                openalex_verifier=mock_openalex,
                semantic_scholar_verifier=mock_s2,
                model="test-model",
            )
            result = verifier.verify(citation)

        # Should have fallen through to S2
        mock_s2.verify.assert_called_once()
        assert result.status == VerificationStatus.UNRESOLVED
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/experimental/arxiv/test_verifiers.py::TestCascadingVerifier -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Add to `src/shesha/experimental/arxiv/verifiers.py`:

```python
import logging

import litellm

from shesha.experimental.arxiv.citations import ArxivVerifier

logger = logging.getLogger(__name__)


def _llm_title_judgment(
    cited_title: str,
    found_title: str,
    found_abstract: str | None,
    model: str,
) -> bool:
    """Ask the LLM whether two titles refer to the same paper.

    Only called for ambiguous fuzzy matches (similarity 0.50-0.85).
    Returns True if the LLM judges them to be the same paper.
    """
    abstract_line = f'\nFound abstract: "{found_abstract}"' if found_abstract else ""
    prompt = (
        f'Cited title: "{cited_title}"\n'
        f'Found title: "{found_title}"{abstract_line}\n\n'
        "Are these the same paper? Respond YES or NO with a one-sentence reason."
    )
    try:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        content = (response.choices[0].message.content or "").strip().upper()
        return content.startswith("YES")
    except Exception:
        logger.warning("LLM title judgment failed", exc_info=True)
        return False  # Conservative: don't verify if LLM fails


class CascadingVerifier:
    """Orchestrates verification across multiple sources."""

    def __init__(
        self,
        *,
        arxiv_verifier: ArxivVerifier | None = None,
        crossref_verifier: CrossRefVerifier | None = None,
        openalex_verifier: OpenAlexVerifier | None = None,
        semantic_scholar_verifier: SemanticScholarVerifier | None = None,
        polite_email: str | None = None,
        model: str | None = None,
    ) -> None:
        self._arxiv = arxiv_verifier
        self._crossref = crossref_verifier
        self._openalex = openalex_verifier
        self._s2 = semantic_scholar_verifier
        self._model = model

    def verify(self, citation: ExtractedCitation) -> VerificationResult:
        """Verify citation using cascading sources."""
        # 1. arXiv ID → ArxivVerifier
        if citation.arxiv_id and self._arxiv:
            result = self._arxiv.verify(citation)
            if result.status not in (
                VerificationStatus.NOT_FOUND,
                VerificationStatus.UNRESOLVED,
            ):
                return result
            # NOT_FOUND on arXiv — try external sources by title

        # 2. DOI → CrossRefVerifier
        if citation.doi and self._crossref:
            result = self._crossref.verify(citation)
            if result.status not in (VerificationStatus.UNRESOLVED,):
                return result

        # 3. Title search chain: OpenAlex → Semantic Scholar → CrossRef title
        if citation.title:
            for verifier in [self._openalex, self._s2, self._crossref]:
                if verifier is None:
                    continue
                # Skip CrossRef if we already tried it via DOI
                if verifier is self._crossref and citation.doi:
                    continue
                result = verifier.verify(citation)
                if result.status in (
                    VerificationStatus.VERIFIED_EXTERNAL,
                    VerificationStatus.MISMATCH,
                ):
                    return result
                # Ambiguous match (0.50-0.85) — try LLM judgment
                if (
                    result.status == VerificationStatus.UNRESOLVED
                    and result.actual_title
                    and result.message
                    and "ambiguous" in result.message.lower()
                    and self._model
                    and citation.title
                ):
                    is_same = _llm_title_judgment(
                        cited_title=citation.title,
                        found_title=result.actual_title,
                        found_abstract=None,
                        model=self._model,
                    )
                    if is_same:
                        return VerificationResult(
                            citation_key=citation.key,
                            status=VerificationStatus.VERIFIED_EXTERNAL,
                            source=result.source,
                            actual_title=result.actual_title,
                            message="Verified by LLM title judgment",
                        )

        return VerificationResult(
            citation_key=citation.key,
            status=VerificationStatus.UNRESOLVED,
            message="Could not verify in any database",
        )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/experimental/arxiv/test_verifiers.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/arxiv/verifiers.py tests/unit/experimental/arxiv/test_verifiers.py
git commit -m "feat: add CascadingVerifier to orchestrate multi-source verification"
```

---

### Task 8: Topical Relevance Checker

**Files:**
- Create: `src/shesha/experimental/arxiv/relevance.py`
- Test: `tests/unit/experimental/arxiv/test_relevance.py`

**Context:** Uses litellm (already a core dependency) to batch-check verified citations for topical relevance. Single LLM call per paper with JSON response.

**Step 1: Write the failing tests**

Create `tests/unit/experimental/arxiv/test_relevance.py`:

```python
"""Tests for topical relevance checker."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from shesha.experimental.arxiv.models import (
    ExtractedCitation,
    VerificationResult,
    VerificationStatus,
)


class TestTopicalRelevanceChecker:
    """Tests for LLM-based topical relevance checking."""

    def test_flags_unrelated_citation(self) -> None:
        from shesha.experimental.arxiv.relevance import check_topical_relevance

        citations = [
            ExtractedCitation(key="a", title="RNA Catalysis", authors=[], year=None),
            ExtractedCitation(key="b", title="Victorian Novel Analysis", authors=[], year=None),
        ]
        verified_keys = {"a", "b"}

        llm_response = json.dumps([
            {"key": "a", "relevant": True, "reason": "Directly related to RNA research"},
            {"key": "b", "relevant": False, "reason": "Literary analysis unrelated to biochemistry"},
        ])
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = llm_response

        with patch("shesha.experimental.arxiv.relevance.litellm.completion", return_value=mock_completion):
            results = check_topical_relevance(
                paper_title="Abiogenesis and Early RNA World",
                paper_abstract="Study of early RNA...",
                citations=citations,
                verified_keys=verified_keys,
                model="test-model",
            )

        assert len(results) == 1  # Only unrelated ones returned
        assert results[0].citation_key == "b"
        assert results[0].status == VerificationStatus.TOPICALLY_UNRELATED

    def test_skips_unverified_citations(self) -> None:
        from shesha.experimental.arxiv.relevance import check_topical_relevance

        citations = [
            ExtractedCitation(key="a", title="Paper A", authors=[], year=None),
            ExtractedCitation(key="b", title="Paper B", authors=[], year=None),
        ]
        # Only "a" is verified
        verified_keys = {"a"}

        llm_response = json.dumps([
            {"key": "a", "relevant": True, "reason": "Related"},
        ])
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = llm_response

        with patch("shesha.experimental.arxiv.relevance.litellm.completion", return_value=mock_completion) as mock_llm:
            results = check_topical_relevance(
                paper_title="Test Paper",
                paper_abstract="Abstract...",
                citations=citations,
                verified_keys=verified_keys,
                model="test-model",
            )

        # "b" should not appear in the prompt — check the LLM call
        call_args = mock_llm.call_args
        prompt_text = call_args.kwargs["messages"][0]["content"]
        assert "Paper B" not in prompt_text
        assert results == []

    def test_no_verified_citations_returns_empty(self) -> None:
        from shesha.experimental.arxiv.relevance import check_topical_relevance

        citations = [
            ExtractedCitation(key="a", title="Paper A", authors=[], year=None),
        ]

        # No verified keys — should not call LLM
        with patch("shesha.experimental.arxiv.relevance.litellm.completion") as mock_llm:
            results = check_topical_relevance(
                paper_title="Test",
                paper_abstract="Abstract",
                citations=citations,
                verified_keys=set(),
                model="test-model",
            )

        mock_llm.assert_not_called()
        assert results == []

    def test_llm_error_returns_empty(self) -> None:
        from shesha.experimental.arxiv.relevance import check_topical_relevance

        citations = [
            ExtractedCitation(key="a", title="Paper A", authors=[], year=None),
        ]

        with patch("shesha.experimental.arxiv.relevance.litellm.completion", side_effect=Exception("API error")):
            results = check_topical_relevance(
                paper_title="Test",
                paper_abstract="Abstract",
                citations=citations,
                verified_keys={"a"},
                model="test-model",
            )

        assert results == []

    def test_malformed_json_returns_empty(self) -> None:
        from shesha.experimental.arxiv.relevance import check_topical_relevance

        citations = [
            ExtractedCitation(key="a", title="Paper A", authors=[], year=None),
        ]

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "not valid json"

        with patch("shesha.experimental.arxiv.relevance.litellm.completion", return_value=mock_completion):
            results = check_topical_relevance(
                paper_title="Test",
                paper_abstract="Abstract",
                citations=citations,
                verified_keys={"a"},
                model="test-model",
            )

        assert results == []
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/experimental/arxiv/test_relevance.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Create `src/shesha/experimental/arxiv/relevance.py`:

```python
"""Topical relevance checking via LLM."""

from __future__ import annotations

import json
import logging

import litellm

from shesha.experimental.arxiv.models import (
    ExtractedCitation,
    VerificationResult,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


def check_topical_relevance(
    *,
    paper_title: str,
    paper_abstract: str,
    citations: list[ExtractedCitation],
    verified_keys: set[str],
    model: str,
) -> list[VerificationResult]:
    """Check topical relevance of verified citations using the LLM.

    Returns VerificationResult entries only for citations flagged as unrelated.
    """
    # Filter to verified citations with titles
    to_check = [c for c in citations if c.key in verified_keys and c.title]
    if not to_check:
        return []

    citation_list = "\n".join(
        f'{i + 1}. key: "{c.key}", title: "{c.title}"' for i, c in enumerate(to_check)
    )

    prompt = f"""Paper title: "{paper_title}"
Paper abstract: "{paper_abstract}"

For each citation below, determine whether it is topically relevant to this paper.
Be generous — interdisciplinary citations are legitimate. Only flag citations that
are clearly unrelated to the paper's subject matter.

Respond with a JSON array of objects with "key" (string), "relevant" (boolean),
and "reason" (one sentence). No other text.

Citations:
{citation_list}"""

    try:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        content = response.choices[0].message.content
        if not content:
            return []

        # Strip markdown code fences if present
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        items = json.loads(content)
    except Exception:
        logger.warning("Topical relevance check failed", exc_info=True)
        return []

    results = []
    for item in items:
        if not item.get("relevant", True):
            key = item.get("key", "")
            reason = item.get("reason", "Flagged as topically unrelated")
            results.append(
                VerificationResult(
                    citation_key=key,
                    status=VerificationStatus.TOPICALLY_UNRELATED,
                    message=reason,
                    severity="warning",
                )
            )

    return results
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/experimental/arxiv/test_relevance.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/arxiv/relevance.py tests/unit/experimental/arxiv/test_relevance.py
git commit -m "feat: add LLM-based topical relevance checker for citations"
```

---

### Task 9: Update Report Formatting for New Statuses

**Files:**
- Modify: `src/shesha/experimental/arxiv/citations.py`
- Modify: `tests/unit/experimental/arxiv/test_citations.py`

**Step 1: Write the failing tests**

Add to `tests/unit/experimental/arxiv/test_citations.py`:

```python
class TestFormatCheckReportJsonExtended:
    """Tests for JSON report with new statuses."""

    def test_verified_external_grouped_as_verified(self) -> None:
        from shesha.experimental.arxiv.citations import format_check_report_json
        from shesha.experimental.arxiv.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        report = CheckReport(
            arxiv_id="2301.00001",
            title="Test",
            citations=[ExtractedCitation(key="a", title="T", authors=[], year=None)],
            verification_results=[
                VerificationResult(
                    citation_key="a",
                    status=VerificationStatus.VERIFIED_EXTERNAL,
                    source="crossref",
                )
            ],
            llm_phrases=[],
        )
        result = format_check_report_json(report)
        assert result["group"] == "verified"

    def test_topically_unrelated_included_in_output(self) -> None:
        from shesha.experimental.arxiv.citations import format_check_report_json
        from shesha.experimental.arxiv.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        report = CheckReport(
            arxiv_id="2301.00001",
            title="Test",
            citations=[
                ExtractedCitation(key="a", title="Good", authors=[], year=None),
                ExtractedCitation(key="b", title="Bad", authors=[], year=None),
            ],
            verification_results=[
                VerificationResult(
                    citation_key="a",
                    status=VerificationStatus.VERIFIED,
                ),
                VerificationResult(
                    citation_key="b",
                    status=VerificationStatus.TOPICALLY_UNRELATED,
                    message="Literary analysis unrelated",
                    severity="warning",
                ),
            ],
            llm_phrases=[],
        )
        result = format_check_report_json(report)
        assert result["group"] == "issues"
        assert result["has_issues"] is True
        assert len(result["topical_issues"]) == 1
        assert result["topical_issues"][0]["key"] == "b"

    def test_source_badge_included_in_verified_entries(self) -> None:
        from shesha.experimental.arxiv.citations import format_check_report_json
        from shesha.experimental.arxiv.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        report = CheckReport(
            arxiv_id="2301.00001",
            title="Test",
            citations=[ExtractedCitation(key="a", title="T", authors=[], year=None)],
            verification_results=[
                VerificationResult(
                    citation_key="a",
                    status=VerificationStatus.VERIFIED_EXTERNAL,
                    source="openalex",
                )
            ],
            llm_phrases=[],
        )
        result = format_check_report_json(report)
        assert "sources" in result
        assert result["sources"]["a"] == "openalex"

    def test_unresolved_label_updated(self) -> None:
        """Unresolved count label should indicate we tried external sources."""
        from shesha.experimental.arxiv.citations import format_check_report_json
        from shesha.experimental.arxiv.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        report = CheckReport(
            arxiv_id="2301.00001",
            title="Test",
            citations=[ExtractedCitation(key="a", title="T", authors=[], year=None)],
            verification_results=[
                VerificationResult(
                    citation_key="a", status=VerificationStatus.UNRESOLVED
                )
            ],
            llm_phrases=[],
        )
        result = format_check_report_json(report)
        assert result["group"] == "unverifiable"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/experimental/arxiv/test_citations.py::TestFormatCheckReportJsonExtended -v`
Expected: FAIL — `topical_issues` and `sources` keys missing

**Step 3: Write minimal implementation**

Update `format_check_report_json` in `src/shesha/experimental/arxiv/citations.py`:

1. Add `TOPICALLY_UNRELATED` to the has_issues check
2. Add `topical_issues` list to output
3. Add `sources` dict mapping citation key → source name
4. Include `VERIFIED_EXTERNAL` in verified count

Updated function (replace lines 256-306):

```python
def format_check_report_json(report: CheckReport) -> dict[str, object]:
    """Format a citation check report as a JSON-serializable dict.

    Groups papers into: "verified", "unverifiable", or "issues".
    """
    mismatches = [
        r
        for r in report.verification_results
        if r.status in (VerificationStatus.MISMATCH, VerificationStatus.NOT_FOUND)
    ]

    topical_issues = [
        r
        for r in report.verification_results
        if r.status == VerificationStatus.TOPICALLY_UNRELATED
    ]

    has_mismatches = len(mismatches) > 0
    has_llm_phrases = len(report.llm_phrases) > 0
    has_unresolved = report.unresolved_count > 0
    has_topical_issues = len(topical_issues) > 0
    zero_citations = len(report.citations) == 0

    has_issues = has_mismatches or has_llm_phrases or zero_citations or has_topical_issues

    if has_issues:
        group = "issues"
    elif has_unresolved:
        group = "unverifiable"
    else:
        group = "verified"

    # Build source map: citation_key -> source name
    sources: dict[str, str] = {}
    for r in report.verification_results:
        if r.source:
            sources[r.citation_key] = r.source

    # Strip version from arxiv_id for the URL (use base ID)
    base_id = report.arxiv_id.split("v")[0] if "v" in report.arxiv_id else report.arxiv_id

    return {
        "arxiv_id": report.arxiv_id,
        "title": report.title,
        "arxiv_url": f"https://arxiv.org/abs/{base_id}",
        "total_citations": len(report.citations),
        "verified_count": report.verified_count,
        "unresolved_count": report.unresolved_count,
        "mismatch_count": report.mismatch_count,
        "has_issues": has_issues,
        "group": group,
        "sources": sources,
        "mismatches": [
            {
                "key": r.citation_key,
                "message": r.message,
                "severity": r.severity or "error",
                "arxiv_url": r.arxiv_url,
            }
            for r in mismatches
        ],
        "topical_issues": [
            {
                "key": r.citation_key,
                "message": r.message,
                "severity": "warning",
            }
            for r in topical_issues
        ],
        "llm_phrases": [
            {"line": line_num, "text": phrase} for line_num, phrase in report.llm_phrases
        ],
    }
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/experimental/arxiv/test_citations.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/arxiv/citations.py tests/unit/experimental/arxiv/test_citations.py
git commit -m "feat: update report formatting for new verification statuses and source badges"
```

---

### Task 10: Update WebSocket Handler

**Files:**
- Modify: `src/shesha/experimental/web/ws.py`
- Modify: `tests/unit/experimental/web/test_ws_citations.py`

**Context:** Update `_handle_check_citations` and `_check_single_paper` to use `CascadingVerifier` instead of `ArxivVerifier`, accept `polite_email` from the client, and run topical relevance checking.

**Step 1: Write the failing tests**

Add to `tests/unit/experimental/web/test_ws_citations.py`:

```python
    def test_accepts_polite_email(self, client: TestClient, mock_state: MagicMock) -> None:
        """Email from client is passed through to verifiers."""
        mock_state.topic_mgr.resolve.return_value = "proj-id"
        meta = MagicMock()
        meta.arxiv_id = "2301.00001"
        meta.title = "Test Paper"
        mock_state.cache.get_meta.return_value = meta
        mock_state.cache.get_source_files.return_value = {
            "refs.bib": "@article{key1, title={Some Paper}, eprint={2301.99999}}"
        }

        mock_result = VerificationResult(
            citation_key="key1",
            status=VerificationStatus.VERIFIED,
            source="arxiv",
        )
        with patch("shesha.experimental.web.ws.CascadingVerifier") as mock_cv_cls:
            mock_cv = MagicMock()
            mock_cv.verify.return_value = mock_result
            mock_cv_cls.return_value = mock_cv

            with patch("shesha.experimental.web.ws.check_topical_relevance", return_value=[]):
                with client.websocket_connect("/api/ws") as ws:
                    ws.send_json({
                        "type": "check_citations",
                        "topic": "test",
                        "paper_ids": ["2301.00001"],
                        "polite_email": "user@example.com",
                    })
                    messages = []
                    while True:
                        msg = ws.receive_json()
                        messages.append(msg)
                        if msg["type"] in ("citation_report", "error"):
                            break

        # CascadingVerifier should have been created with the email
        mock_cv_cls.assert_called_once()
        call_kwargs = mock_cv_cls.call_args.kwargs
        assert call_kwargs.get("polite_email") == "user@example.com"

    def test_report_includes_sources(self, client: TestClient, mock_state: MagicMock) -> None:
        """Report JSON should include the sources dict."""
        mock_state.topic_mgr.resolve.return_value = "proj-id"
        meta = MagicMock()
        meta.arxiv_id = "2301.00001"
        meta.title = "Test Paper"
        mock_state.cache.get_meta.return_value = meta
        mock_state.cache.get_source_files.return_value = {
            "refs.bib": "@article{key1, title={Some Paper}, doi={10.1234/x}}"
        }

        mock_result = VerificationResult(
            citation_key="key1",
            status=VerificationStatus.VERIFIED_EXTERNAL,
            source="crossref",
        )
        with patch("shesha.experimental.web.ws.CascadingVerifier") as mock_cv_cls:
            mock_cv = MagicMock()
            mock_cv.verify.return_value = mock_result
            mock_cv_cls.return_value = mock_cv

            with patch("shesha.experimental.web.ws.check_topical_relevance", return_value=[]):
                with client.websocket_connect("/api/ws") as ws:
                    ws.send_json({
                        "type": "check_citations",
                        "topic": "test",
                        "paper_ids": ["2301.00001"],
                    })
                    messages = []
                    while True:
                        msg = ws.receive_json()
                        messages.append(msg)
                        if msg["type"] in ("citation_report", "error"):
                            break

        report = [m for m in messages if m["type"] == "citation_report"][0]
        paper = report["papers"][0]
        assert "sources" in paper
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/experimental/web/test_ws_citations.py -v`
Expected: FAIL — `CascadingVerifier` not imported, `check_topical_relevance` not imported

**Step 3: Write minimal implementation**

Update `src/shesha/experimental/web/ws.py`:

1. Update imports (replace ArxivVerifier import with CascadingVerifier and related):
```python
from shesha.experimental.arxiv.citations import (
    ArxivVerifier,
    detect_llm_phrases,
    extract_citations_from_bbl,
    extract_citations_from_bib,
    extract_citations_from_text,
    format_check_report_json,
)
from shesha.experimental.arxiv.relevance import check_topical_relevance
from shesha.experimental.arxiv.verifiers import (
    CascadingVerifier,
    CrossRefVerifier,
    OpenAlexVerifier,
    SemanticScholarVerifier,
)
```

2. Update `_handle_check_citations` to accept email and create CascadingVerifier:
```python
async def _handle_check_citations(ws: WebSocket, state: AppState, data: dict[str, object]) -> None:
    """Check citations for selected papers and stream progress."""
    topic = str(data.get("topic", ""))
    project_id = state.topic_mgr.resolve(topic)
    if not project_id:
        await ws.send_json({"type": "error", "message": f"Topic '{topic}' not found"})
        return

    paper_ids = data.get("paper_ids")
    if not paper_ids or not isinstance(paper_ids, list) or len(paper_ids) == 0:
        await ws.send_json(
            {"type": "error", "message": "Please select one or more papers to check"}
        )
        return

    polite_email = data.get("polite_email")
    email_str = str(polite_email) if polite_email else None

    loop = asyncio.get_running_loop()
    verifier = CascadingVerifier(
        arxiv_verifier=ArxivVerifier(searcher=state.searcher),
        crossref_verifier=CrossRefVerifier(polite_email=email_str),
        openalex_verifier=OpenAlexVerifier(polite_email=email_str),
        semantic_scholar_verifier=SemanticScholarVerifier(),
        polite_email=email_str,
        model=state.model,
    )
    total = len(paper_ids)
    all_papers: list[dict[str, object]] = []

    for idx, pid in enumerate(paper_ids, 1):
        await ws.send_json({
            "type": "citation_progress",
            "current": idx,
            "total": total,
            "phase": "Verifying citations...",
        })
        paper_json = await loop.run_in_executor(
            None,
            functools.partial(
                _check_single_paper, str(pid), state, verifier, project_id, state.model
            ),
        )
        if paper_json is not None:
            all_papers.append(paper_json)

    await ws.send_json({"type": "citation_report", "papers": all_papers})
```

3. Update `_check_single_paper` signature and add relevance check:
```python
def _check_single_paper(
    paper_id: str,
    state: AppState,
    verifier: CascadingVerifier,
    project_id: str,
    model: str,
) -> dict[str, object] | None:
    """Check citations for a single paper. Returns JSON-serializable dict or None."""
    meta = state.cache.get_meta(paper_id)
    if meta is None:
        return None

    citations: list[ExtractedCitation] = []
    source_files = state.cache.get_source_files(paper_id)
    full_text = ""

    if source_files is not None:
        for filename, content in source_files.items():
            full_text += content + "\n"
            if filename.endswith(".bib"):
                citations.extend(extract_citations_from_bib(content))
            elif filename.endswith(".bbl"):
                citations.extend(extract_citations_from_bbl(content))
    else:
        try:
            doc = state.topic_mgr._storage.get_document(project_id, paper_id)
            full_text = doc.content
            citations.extend(extract_citations_from_text(full_text))
        except Exception:
            full_text = ""

    llm_phrases = detect_llm_phrases(full_text)
    results = [verifier.verify(c) for c in citations]

    # Topical relevance check on verified citations
    verified_keys = {
        r.citation_key
        for r in results
        if r.status in (VerificationStatus.VERIFIED, VerificationStatus.VERIFIED_EXTERNAL)
    }
    relevance_results = check_topical_relevance(
        paper_title=meta.title,
        paper_abstract=meta.abstract,
        citations=citations,
        verified_keys=verified_keys,
        model=model,
    )
    results.extend(relevance_results)

    report = CheckReport(
        arxiv_id=meta.arxiv_id,
        title=meta.title,
        citations=citations,
        verification_results=results,
        llm_phrases=llm_phrases,
    )
    return format_check_report_json(report)
```

4. Add `polite_email` parameter to `CascadingVerifier.__init__` (back in verifiers.py — just accept and ignore for forward compat):

In `src/shesha/experimental/arxiv/verifiers.py`, update `CascadingVerifier.__init__`:
```python
    def __init__(
        self,
        *,
        arxiv_verifier: ArxivVerifier | None = None,
        crossref_verifier: CrossRefVerifier | None = None,
        openalex_verifier: OpenAlexVerifier | None = None,
        semantic_scholar_verifier: SemanticScholarVerifier | None = None,
        polite_email: str | None = None,  # Stored for reference; individual verifiers get it directly
    ) -> None:
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/experimental/web/test_ws_citations.py -v`
Expected: All PASS

Run: `pytest tests/unit/experimental/arxiv/ -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/web/ws.py src/shesha/experimental/arxiv/verifiers.py tests/unit/experimental/web/test_ws_citations.py
git commit -m "feat: integrate cascading verifier and topical relevance into WebSocket handler"
```

---

### Task 11: Update Frontend Types

**Files:**
- Modify: `src/shesha/experimental/web/frontend/src/types/index.ts`

**Step 1: Update types**

Add to `PaperReport` interface:
```typescript
export interface TopicalIssueEntry {
  key: string
  message: string
  severity: 'warning'
}

export interface PaperReport {
  arxiv_id: string
  title: string
  arxiv_url: string
  total_citations: number
  verified_count: number
  unresolved_count: number
  mismatch_count: number
  has_issues: boolean
  group: 'verified' | 'unverifiable' | 'issues'
  mismatches: MismatchEntry[]
  llm_phrases: LLMPhraseEntry[]
  topical_issues: TopicalIssueEntry[]
  sources: Record<string, string>
}
```

Update `WSMessage` to include `phase` in citation_progress:
```typescript
  | { type: 'citation_progress'; current: number; total: number; phase?: string }
```

**Step 2: Commit**

```bash
git add src/shesha/experimental/web/frontend/src/types/index.ts
git commit -m "feat: extend frontend types for multi-source verification"
```

---

### Task 12: Email Modal Component

**Files:**
- Create: `src/shesha/experimental/web/frontend/src/components/EmailModal.tsx`

**Step 1: Create the component**

```typescript
import { useState } from 'react'

interface EmailModalProps {
  onSubmit: (email: string) => void
  onSkip: () => void
}

const STORAGE_KEY = 'shesha-polite-email'

export function getStoredEmail(): string | null {
  return localStorage.getItem(STORAGE_KEY)
}

export function storeEmail(email: string): void {
  localStorage.setItem(STORAGE_KEY, email)
}

export function hasEmailDecision(): boolean {
  return localStorage.getItem(STORAGE_KEY) !== null || localStorage.getItem('shesha-email-skipped') === 'true'
}

export function markEmailSkipped(): void {
  localStorage.setItem('shesha-email-skipped', 'true')
}

export default function EmailModal({ onSubmit, onSkip }: EmailModalProps) {
  const [email, setEmail] = useState('')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-surface-1 border border-border rounded-lg shadow-2xl w-[480px] p-6">
        <h2 className="text-sm font-semibold text-text-primary mb-3">Citation Check — Email</h2>
        <p className="text-xs text-text-secondary leading-relaxed mb-4">
          CrossRef and OpenAlex offer faster access if you provide an email address.
          It's used only as a courtesy identifier in API requests — they never contact you.
          You can skip this, but checks will be slower.
        </p>
        <input
          type="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && email.trim()) {
              storeEmail(email.trim())
              onSubmit(email.trim())
            }
          }}
          placeholder="your@email.com"
          className="w-full bg-surface-2 border border-border rounded px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent mb-4"
          autoFocus
        />
        <div className="flex gap-2 justify-end">
          <button
            onClick={() => { markEmailSkipped(); onSkip() }}
            className="px-3 py-1.5 text-xs text-text-dim hover:text-text-secondary"
          >
            Skip
          </button>
          <button
            onClick={() => {
              if (email.trim()) {
                storeEmail(email.trim())
                onSubmit(email.trim())
              }
            }}
            disabled={!email.trim()}
            className="px-3 py-1.5 text-xs bg-accent text-white rounded hover:bg-accent/90 disabled:opacity-50"
          >
            Continue
          </button>
        </div>
      </div>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add src/shesha/experimental/web/frontend/src/components/EmailModal.tsx
git commit -m "feat: add EmailModal for polite-pool email collection"
```

---

### Task 13: Update CitationReport Component

**Files:**
- Modify: `src/shesha/experimental/web/frontend/src/components/CitationReport.tsx`

**Step 1: Update component**

Key changes:
1. Add source badges next to verified citations
2. Change "unresolved" label to "not found in databases"
3. Add topical issues section (orange) in Zone 4
4. Import new types

Updated component (full replacement):

```typescript
import type { PaperReport } from '../types'

interface CitationReportProps {
  checking: boolean
  progress: { current: number; total: number; phase?: string } | null
  report: PaperReport[] | null
  error: string | null
  onClose: () => void
}

const DISCLAIMER =
  'DISCLAIMER: This analysis is generated using AI and automated heuristics. ' +
  'It is capable of making mistakes. A flagged citation does NOT mean a paper is ' +
  'fraudulent \u2014 there may be legitimate explanations (metadata lag, preprint ' +
  'title changes, version differences). Always verify findings manually before ' +
  'drawing conclusions.'

const SOURCE_LABELS: Record<string, string> = {
  arxiv: 'arXiv',
  crossref: 'CrossRef',
  openalex: 'OpenAlex',
  semantic_scholar: 'S2',
}

function SourceBadge({ source }: { source: string }) {
  const label = SOURCE_LABELS[source] ?? source
  return (
    <span className="text-[10px] px-1 py-0.5 rounded bg-surface-2 text-text-dim border border-border">
      {label}
    </span>
  )
}

export default function CitationReport({ checking, progress, report, error, onClose }: CitationReportProps) {
  if (!checking && !report && !error) return null

  const verified = report?.filter(p => p.group === 'verified') ?? []
  const unverifiable = report?.filter(p => p.group === 'unverifiable') ?? []
  const issues = report?.filter(p => p.group === 'issues') ?? []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-surface-1 border border-border rounded-lg shadow-2xl w-[700px] max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h2 className="text-sm font-semibold text-text-primary">Citation Check</h2>
          <button onClick={onClose} className="text-text-dim hover:text-text-secondary text-lg leading-none">&times;</button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
          {/* Loading states */}
          {checking && progress && (
            <div className="text-center py-8">
              <div className="text-sm text-text-secondary mb-2">
                {progress.current}/{progress.total} &mdash; {progress.phase ?? 'Checking...'}
              </div>
              <div className="w-full bg-surface-2 rounded-full h-2">
                <div
                  className="bg-accent h-2 rounded-full transition-all"
                  style={{ width: `${(progress.current / progress.total) * 100}%` }}
                />
              </div>
            </div>
          )}

          {error && (
            <div className="text-center py-8 text-red text-sm">{error}</div>
          )}

          {checking && !progress && !error && (
            <div className="text-center py-8 text-text-dim text-sm">
              Starting citation check...
            </div>
          )}

          {/* Report content */}
          {report && (
            <>
              {/* Zone 1: Disclaimer */}
              <div className="rounded border border-red/30 bg-red/5 px-3 py-2">
                <p className="text-xs font-bold text-red leading-relaxed">{DISCLAIMER}</p>
              </div>

              {/* Zone 2: Verified papers */}
              {verified.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold text-green mb-1">
                    All citations verified ({verified.length})
                  </h3>
                  <ul className="space-y-0.5">
                    {verified.map(p => {
                      const uniqueSources = [...new Set(Object.values(p.sources ?? {}))]
                      return (
                        <li key={p.arxiv_id} className="flex items-baseline gap-1.5 text-xs text-text-secondary">
                          <span className="text-green shrink-0">&#10003;</span>
                          <span className="truncate">{p.title}</span>
                          <span className="text-text-dim shrink-0">
                            ({p.verified_count}/{p.total_citations} verified)
                          </span>
                          {uniqueSources.map(s => <SourceBadge key={s} source={s} />)}
                          <a
                            href={p.arxiv_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-accent hover:underline shrink-0"
                          >
                            arXiv
                          </a>
                        </li>
                      )
                    })}
                  </ul>
                </section>
              )}

              {/* Zone 3: Unverifiable papers */}
              {unverifiable.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold text-text-dim mb-1">
                    Some citations could not be checked ({unverifiable.length})
                  </h3>
                  <ul className="space-y-0.5">
                    {unverifiable.map(p => (
                      <li key={p.arxiv_id} className="flex items-baseline gap-1.5 text-xs text-text-secondary">
                        <span className="text-text-dim shrink-0">&#8212;</span>
                        <span className="truncate">{p.title}</span>
                        <span className="text-text-dim shrink-0">
                          ({p.verified_count} verified, {p.unresolved_count} not found in databases)
                        </span>
                        <a
                          href={p.arxiv_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-accent hover:underline shrink-0"
                        >
                          arXiv
                        </a>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {/* Zone 4: Papers with issues */}
              {issues.length > 0 && (
                <section className="space-y-3">
                  <h3 className="text-xs font-semibold text-amber mb-1">
                    Potential issues detected ({issues.length})
                  </h3>
                  {issues.map(p => (
                    <div key={p.arxiv_id} className="rounded border border-border bg-surface-2 px-3 py-2">
                      {/* Paper header */}
                      <div className="flex items-baseline gap-1.5 mb-1.5">
                        <span className="text-amber shrink-0">&#9888;</span>
                        <span className="text-xs font-medium text-text-primary truncate">{p.title}</span>
                        <a
                          href={p.arxiv_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-accent hover:underline shrink-0"
                        >
                          arXiv
                        </a>
                      </div>

                      {/* Citation stats */}
                      <div className="text-xs text-text-dim mb-1.5">
                        {p.total_citations === 0 ? (
                          <span className="text-amber">No citations could be extracted</span>
                        ) : (
                          <>
                            {p.total_citations} citations
                            {p.verified_count > 0 && <> &middot; {p.verified_count} OK</>}
                            {p.unresolved_count > 0 && <> &middot; {p.unresolved_count} not found in databases</>}
                            {p.mismatch_count > 0 && <> &middot; <span className="text-red">{p.mismatch_count} mismatches</span></>}
                          </>
                        )}
                      </div>

                      {/* Mismatch details */}
                      {p.mismatches.length > 0 && (
                        <div className="space-y-1 mb-1.5">
                          {p.mismatches.map((m, i) => (
                            <div
                              key={i}
                              className={`text-xs pl-4 border-l-2 ${
                                m.severity === 'error'
                                  ? 'border-red text-red'
                                  : 'border-amber text-amber'
                              }`}
                            >
                              <div>
                                <span className="font-mono">[{m.key}]</span>: {m.message}
                              </div>
                              {m.arxiv_url && (
                                <a
                                  href={m.arxiv_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-accent hover:underline"
                                >
                                  {m.arxiv_url}
                                </a>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Topical issues */}
                      {(p.topical_issues ?? []).length > 0 && (
                        <div className="space-y-1 mb-1.5">
                          <div className="text-xs text-orange-400 font-medium">Topically unrelated:</div>
                          {p.topical_issues.map((ti, i) => (
                            <div key={i} className="text-xs pl-4 border-l-2 border-orange-400 text-orange-400">
                              <span className="font-mono">[{ti.key}]</span>: {ti.message}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* LLM-tell phrases */}
                      {p.llm_phrases.length > 0 && (
                        <div className="text-xs">
                          <div className="text-purple-400 font-medium mb-0.5">LLM-tell phrases:</div>
                          {p.llm_phrases.map((lp, i) => (
                            <div key={i} className="text-purple-400/70 pl-4">
                              Line {lp.line}: &ldquo;{lp.text}&rdquo;
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add src/shesha/experimental/web/frontend/src/components/CitationReport.tsx
git commit -m "feat: update CitationReport with source badges, topical issues, and improved labels"
```

---

### Task 14: Update App.tsx — Email Modal Integration

**Files:**
- Modify: `src/shesha/experimental/web/frontend/src/App.tsx`

**Step 1: Update App.tsx**

1. Import EmailModal and helpers:
```typescript
import EmailModal, { getStoredEmail, hasEmailDecision } from './components/EmailModal'
```

2. Update citation progress state type and add email modal state:
```typescript
const [citationProgress, setCitationProgress] = useState<{ current: number; total: number; phase?: string } | null>(null)
const [showEmailModal, setShowEmailModal] = useState(false)
const [pendingCitationCheck, setPendingCitationCheck] = useState(false)
```

3. Update the citation_progress message handler in the `onMessage` effect to include phase:
```typescript
} else if (msg.type === 'citation_progress') {
  setCitationProgress({ current: msg.current, total: msg.total, phase: msg.phase })
}
```

3. Update `handleCheckCitations` to show email modal on first use:
```typescript
const handleCheckCitations = useCallback(() => {
  if (!activeTopic) {
    showToast('Select a topic first', 'warning')
    return
  }
  if (selectedPapers.size === 0) {
    showToast('Select papers to check', 'warning')
    return
  }

  // Show email modal if no decision yet
  if (!hasEmailDecision()) {
    setPendingCitationCheck(true)
    setShowEmailModal(true)
    return
  }

  // Proceed with check
  setCitationChecking(true)
  setCitationProgress(null)
  setCitationReport(null)
  setCitationError(null)
  const email = getStoredEmail()
  send({
    type: 'check_citations',
    topic: activeTopic,
    paper_ids: Array.from(selectedPapers),
    ...(email ? { polite_email: email } : {}),
  })
}, [activeTopic, selectedPapers, send])

const handleEmailSubmit = useCallback((email: string) => {
  setShowEmailModal(false)
  if (pendingCitationCheck) {
    setPendingCitationCheck(false)
    setCitationChecking(true)
    setCitationProgress(null)
    setCitationReport(null)
    setCitationError(null)
    send({
      type: 'check_citations',
      topic: activeTopic!,
      paper_ids: Array.from(selectedPapers),
      polite_email: email,
    })
  }
}, [activeTopic, selectedPapers, send, pendingCitationCheck])

const handleEmailSkip = useCallback(() => {
  setShowEmailModal(false)
  if (pendingCitationCheck) {
    setPendingCitationCheck(false)
    setCitationChecking(true)
    setCitationProgress(null)
    setCitationReport(null)
    setCitationError(null)
    send({
      type: 'check_citations',
      topic: activeTopic!,
      paper_ids: Array.from(selectedPapers),
    })
  }
}, [activeTopic, selectedPapers, send, pendingCitationCheck])
```

4. Add EmailModal to JSX (after CitationReport):
```typescript
{showEmailModal && (
  <EmailModal onSubmit={handleEmailSubmit} onSkip={handleEmailSkip} />
)}
```

**Step 2: Commit**

```bash
git add src/shesha/experimental/web/frontend/src/App.tsx
git commit -m "feat: integrate email modal into citation check flow"
```

---

### Task 15: Papers Default to Selected (UI Fix)

**Files:**
- Modify: `src/shesha/experimental/web/frontend/src/components/TopicSidebar.tsx`

**Context:** Currently, `onPapersLoaded` is only called when the expand arrow is clicked AND papers haven't been loaded before (line 50-54 in TopicSidebar.tsx). When a topic is selected via `handleTopicSelect` in App.tsx, it clears `selectedPapers` to an empty set. The papers should auto-load and auto-select when a topic is clicked.

**Step 1: Update TopicSidebar**

The fix: when a topic is selected (clicked), auto-expand it and load papers if not already loaded. This triggers `onPapersLoaded` which sets all papers as selected.

In `TopicSidebar.tsx`, add a `useEffect` that auto-expands and loads papers when `activeTopic` changes:

```typescript
// Auto-expand and load papers when active topic changes
useEffect(() => {
  if (!activeTopic) return
  setExpandedTopic(activeTopic)
  if (!topicPapers[activeTopic]) {
    api.papers.list(activeTopic).then(papers => {
      setTopicPapers(prev => ({ ...prev, [activeTopic]: papers }))
      onPapersLoaded(papers)
    }).catch(() => {})
  } else {
    onPapersLoaded(topicPapers[activeTopic])
  }
}, [activeTopic])  // eslint-disable-line react-hooks/exhaustive-deps
```

Add this after the existing `useEffect` hooks (after line 41).

**Step 2: Commit**

```bash
git add src/shesha/experimental/web/frontend/src/components/TopicSidebar.tsx
git commit -m "fix: auto-select all papers when topic is clicked"
```

---

### Task 16: Add httpx to web dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Update dependencies**

Add `httpx` to the `web` optional dependency group (line 52-56):

```toml
web = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "websockets>=12.0",
    "httpx>=0.27",
]
```

Also add `httpx` to the `arxiv` group since the external verifiers are part of the arxiv module:

```toml
arxiv = [
    "arxiv>=2.0",
    "bibtexparser>=2.0.0b7",
    "httpx>=0.27",
]
```

**Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add httpx to web and arxiv dependency groups"
```

---

### Task 17: Run Full Test Suite and Fix Issues

**Step 1: Run all Python tests**

Run: `pytest tests/ -v`

**Step 2: Run type checking**

Run: `mypy src/shesha`

**Step 3: Run linting**

Run: `ruff check src tests`
Run: `ruff format src tests`

**Step 4: Build frontend**

Run: `cd src/shesha/experimental/web/frontend && npm run build`

**Step 5: Fix any issues found**

Address any test failures, type errors, lint violations, or build errors.

**Step 6: Commit fixes**

```bash
git add -A
git commit -m "fix: resolve test, type, and lint issues from citation verification upgrade"
```

---

### Task 18: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add changelog entries under `[Unreleased]`**

```markdown
### Added
- Multi-source citation verification: CrossRef, OpenAlex, and Semantic Scholar alongside arXiv
- Fuzzy title matching with Jaccard similarity for better cross-source verification
- LLM-based topical relevance checking flags citations unrelated to the citing paper
- Source badges in citation report showing where each citation was verified
- Email modal for API polite-pool access (optional, stored in browser localStorage)

### Changed
- "unresolved" citations now labeled "not found in databases" to clarify we tried external sources
- Papers default to selected when clicking a topic

### Fixed
- Papers not auto-selected when clicking a topic name (required expanding the paper list first)
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: update changelog for citation verification upgrade"
```
