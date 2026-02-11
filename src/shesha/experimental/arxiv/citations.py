"""Citation extraction and LLM-tell phrase detection."""

from __future__ import annotations

import re

from shesha.experimental.arxiv.models import ExtractedCitation

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

        library = bibtexparser.parse_string(bib_content)  # type: ignore[attr-defined]
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
