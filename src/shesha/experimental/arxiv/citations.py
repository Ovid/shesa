"""Citation extraction and LLM-tell phrase detection."""

from __future__ import annotations

import logging
import re

from shesha.experimental.arxiv.models import (
    CheckReport,
    ExtractedCitation,
    VerificationResult,
    VerificationStatus,
)
from shesha.experimental.arxiv.search import ArxivSearcher

# Patterns that suggest LLM-generated text
LLM_TELL_PATTERNS = [
    re.compile(r"as of my last (?:knowledge )?(?:update|training|cutoff)", re.IGNORECASE),
    re.compile(r"it is important to note that", re.IGNORECASE),
    re.compile(r"I cannot provide", re.IGNORECASE),
    re.compile(r"I don't have access to", re.IGNORECASE),
    re.compile(r"as of my knowledge cutoff", re.IGNORECASE),
    re.compile(r"as an AI language model", re.IGNORECASE),
    re.compile(r"I was trained on data up to", re.IGNORECASE),
]

# Pattern to find arXiv IDs in text
ARXIV_ID_PATTERN = re.compile(r"(?:arXiv:)?(\d{4}\.\d{4,5}(?:v\d+)?)")


def extract_citations_from_bib(bib_content: str) -> list[ExtractedCitation]:
    """Extract citations from a .bib file using bibtexparser."""
    if not bib_content.strip():
        return []
    try:
        # Late import: bibtexparser is an optional dependency
        import bibtexparser

        # Suppress noisy warnings about DuplicateBlockKeyBlock etc.
        _btp_logger = logging.getLogger("bibtexparser.middlewares.middleware")
        _prev_level = _btp_logger.level
        _btp_logger.setLevel(logging.ERROR)
        try:
            library = bibtexparser.parse_string(bib_content)  # type: ignore[attr-defined]
        finally:
            _btp_logger.setLevel(_prev_level)
        citations = []
        for entry in library.entries:
            key = entry.key
            fields = {f.key: f.value for f in entry.fields}
            arxiv_id = fields.get("eprint")
            # Also check for arXiv ID in note or url fields
            if arxiv_id is None:
                for field_name in ("note", "url"):
                    val = fields.get(field_name, "")
                    match = ARXIV_ID_PATTERN.search(val)
                    if match:
                        arxiv_id = match.group(1)
                        break
            authors_raw = fields.get("author", "")
            authors = [a.strip() for a in authors_raw.split(" and ")] if authors_raw else []
            citations.append(
                ExtractedCitation(
                    key=key,
                    title=fields.get("title"),
                    authors=authors,
                    year=fields.get("year"),
                    arxiv_id=arxiv_id,
                    doi=fields.get("doi"),
                    raw_text=None,
                )
            )
        return citations
    except Exception:
        return []  # Malformed BibTeX should not crash


def extract_citations_from_bbl(bbl_content: str) -> list[ExtractedCitation]:
    r"""Extract citations from a .bbl file (\\bibitem entries)."""
    if not bbl_content.strip():
        return []
    citations = []
    # Split on \bibitem{...}
    pattern = re.compile(
        r"\\bibitem\{([^}]+)\}(.*?)(?=\\bibitem\{|\\end\{thebibliography\}|$)", re.DOTALL
    )
    for match in pattern.finditer(bbl_content):
        key = match.group(1)
        raw_text = match.group(2).strip()
        # Try to find arXiv ID in the text
        arxiv_match = ARXIV_ID_PATTERN.search(raw_text)
        arxiv_id = arxiv_match.group(1) if arxiv_match else None
        citations.append(
            ExtractedCitation(
                key=key,
                title=None,  # Difficult to parse reliably from formatted text
                authors=[],
                year=None,
                arxiv_id=arxiv_id,
                raw_text=raw_text,
            )
        )
    return citations


def extract_citations_from_text(text: str) -> list[ExtractedCitation]:
    """Extract citations from plain text by finding arXiv IDs.

    Best-effort fallback for PDF-only papers where no .bib/.bbl is available.
    """
    if not text.strip():
        return []
    seen: set[str] = set()
    citations = []
    for match in ARXIV_ID_PATTERN.finditer(text):
        arxiv_id = match.group(1)
        if arxiv_id in seen:
            continue
        seen.add(arxiv_id)
        citations.append(
            ExtractedCitation(
                key=f"text-{arxiv_id}",
                title=None,
                authors=[],
                year=None,
                arxiv_id=arxiv_id,
                raw_text=None,
            )
        )
    return citations


def detect_llm_phrases(text: str) -> list[tuple[int, str]]:
    """Detect LLM-tell phrases in text. Returns (line_number, matched_text) pairs."""
    results = []
    for line_num, line in enumerate(text.splitlines(), start=1):
        for pattern in LLM_TELL_PATTERNS:
            match = pattern.search(line)
            if match:
                results.append((line_num, line.strip()))
                break  # One match per line is enough
    return results


DISCLAIMER = """DISCLAIMER: This analysis is generated using AI and automated heuristics.
It is capable of making mistakes. A flagged citation does NOT mean a paper is
fraudulent -- there may be legitimate explanations (metadata lag, preprint
title changes, version differences). Always verify findings manually before
drawing conclusions."""


class ArxivVerifier:
    """Verify citations against the arXiv API."""

    def __init__(self, searcher: ArxivSearcher | None = None) -> None:
        self._searcher = searcher or ArxivSearcher()

    def verify(self, citation: ExtractedCitation) -> VerificationResult:
        """Verify a single citation."""
        if citation.arxiv_id is None:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.UNRESOLVED,
                message="Non-arXiv citation, cannot verify",
            )
        actual = self._searcher.get_by_id(citation.arxiv_id)
        if actual is None:
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.NOT_FOUND,
                message=f"arXiv ID {citation.arxiv_id} does not exist",
            )
        # Compare titles if we have one
        if citation.title and not _titles_match(citation.title, actual.title):
            return VerificationResult(
                citation_key=citation.key,
                status=VerificationStatus.MISMATCH,
                message=f'Cites "{citation.title}" but actual paper is "{actual.title}"',
                actual_title=actual.title,
                arxiv_url=actual.arxiv_url,
            )
        return VerificationResult(
            citation_key=citation.key,
            status=VerificationStatus.VERIFIED,
            arxiv_url=actual.arxiv_url,
        )


def _titles_match(cited: str, actual: str) -> bool:
    """Fuzzy title comparison -- normalize and check containment."""

    def normalize(t: str) -> str:
        return re.sub(r"[^\w\s]", "", t.lower()).strip()

    c, a = normalize(cited), normalize(actual)
    # Exact match or one contains the other (handles truncated titles)
    return c == a or c in a or a in c


def format_check_report(report: CheckReport) -> str:
    """Format a citation check report for display."""
    lines = [DISCLAIMER, ""]
    lines.append(f'-- Citation Check: {report.arxiv_id} "{report.title}" --')
    lines.append("")
    lines.append(f"Citations found: {len(report.citations)}")
    lines.append(f"  OK  {report.verified_count} verified")
    lines.append(f"  ?   {report.unresolved_count} unresolved (non-arXiv, could not verify)")
    lines.append(f"  X   {report.mismatch_count} mismatches")

    # Show mismatch details
    mismatches = [
        r
        for r in report.verification_results
        if r.status in (VerificationStatus.MISMATCH, VerificationStatus.NOT_FOUND)
    ]
    if mismatches:
        lines.append("")
        for r in mismatches:
            lines.append(f"  MISMATCH [{r.citation_key}]: {r.message}")
            if r.arxiv_url:
                lines.append(f"    {r.arxiv_url}")

    # Show LLM-tell phrases
    lines.append("")
    if report.llm_phrases:
        lines.append("LLM-tell phrases found:")
        for line_num, phrase in report.llm_phrases:
            lines.append(f'  Line {line_num}: "{phrase}"')
    else:
        lines.append("LLM-tell phrases: none detected")

    return "\n".join(lines)
