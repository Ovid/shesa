"""Core data models for Shesha."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from shesha.project import Project


@dataclass
class ParsedDocument:
    """A parsed document ready for storage and querying."""

    name: str
    content: str
    format: str
    metadata: dict[str, str | int | float | bool]
    char_count: int
    parse_warnings: list[str] = field(default_factory=list)


@dataclass
class RepoProjectResult:
    """Result from create_project_from_repo()."""

    project: "Project"
    status: Literal["created", "unchanged", "updates_available"]
    files_ingested: int
    files_skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    _apply_updates_fn: Callable[[], "RepoProjectResult"] | None = field(default=None, repr=False)

    def apply_updates(self) -> "RepoProjectResult":
        """Pull changes and re-ingest. Only valid when status is 'updates_available'."""
        if self.status != "updates_available":
            raise ValueError("apply_updates() is only valid when status is 'updates_available'")
        if self._apply_updates_fn is None:
            raise ValueError("No apply_updates function provided")
        return self._apply_updates_fn()


@dataclass
class QueryContext:
    """Metadata about a query for trace logging."""

    trace_id: str
    question: str
    document_ids: list[str]
    model: str
    system_prompt: str
    subcall_prompt: str
