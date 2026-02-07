"""Semantic verification of RLM findings against source documents."""

from dataclasses import dataclass, field
from pathlib import PurePosixPath


@dataclass
class FindingVerification:
    """Verification result for a single finding."""

    finding_id: str
    original_claim: str
    confidence: str
    reason: str
    evidence_classification: str
    flags: list[str] = field(default_factory=list)


@dataclass
class SemanticVerificationReport:
    """Report containing verified findings."""

    findings: list[FindingVerification]
    content_type: str

    @property
    def high_confidence(self) -> list[FindingVerification]:
        """Return findings where confidence is high or medium."""
        return [f for f in self.findings if f.confidence in ("high", "medium")]

    @property
    def low_confidence(self) -> list[FindingVerification]:
        """Return findings where confidence is low."""
        return [f for f in self.findings if f.confidence == "low"]


CODE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".pl",
        ".pm",
        ".t",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".mjs",
        ".cjs",
        ".rs",
        ".go",
        ".java",
        ".rb",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".cc",
        ".cs",
        ".swift",
        ".kt",
        ".scala",
        ".clj",
        ".ex",
        ".exs",
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
        ".sql",
        ".r",
        ".m",
        ".mm",
        ".lua",
        ".vim",
        ".el",
        ".hs",
        ".php",
        ".dart",
        ".v",
        ".zig",
    }
)


def detect_content_type(doc_names: list[str]) -> str:
    """Detect whether documents are predominantly code or general content.

    Returns "code" if a strict majority of doc_names have code extensions,
    "general" otherwise. Empty list returns "general".
    """
    if not doc_names:
        return "general"
    code_count = sum(
        1
        for name in doc_names
        if PurePosixPath(name).suffix.lower() in CODE_EXTENSIONS
    )
    if code_count > len(doc_names) / 2:
        return "code"
    return "general"
