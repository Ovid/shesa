"""Post-FINAL citation verification for RLM answers."""

import re
from dataclasses import dataclass


@dataclass
class Citation:
    """A document citation found in an answer."""

    doc_id: int
    found: bool


@dataclass
class Quote:
    """A quoted string found in an answer."""

    text: str
    doc_id: int
    found: bool


@dataclass
class VerificationResult:
    """Result of citation verification."""

    citations: list[Citation]
    quotes: list[Quote]

    @property
    def all_valid(self) -> bool:
        """True when all citations and quotes were found."""
        return all(c.found for c in self.citations) and all(q.found for q in self.quotes)


# Patterns for extracting doc citations from LLM answers
_CITATION_PATTERNS = [
    re.compile(r"\bDoc\s+\*\*(\d+)\*\*"),  # Doc **N**
    re.compile(r"\bDoc\s+(\d+)"),  # Doc N
    re.compile(r"\bcontext\[(\d+)\]"),  # context[N]
    re.compile(r"(?<!\w)\*\*(\d+)\*\*(?!\w)"),  # standalone **N**
]


def extract_citations(text: str) -> list[int]:
    """Extract unique doc IDs from an answer, preserving first-appearance order."""
    seen: set[int] = set()
    result: list[int] = []
    for pattern in _CITATION_PATTERNS:
        for match in pattern.finditer(text):
            doc_id = int(match.group(1))
            if doc_id not in seen:
                seen.add(doc_id)
                result.append(doc_id)
    return result
