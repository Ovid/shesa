"""Multi-repo PRD analyzer using federated queries."""

from typing import TYPE_CHECKING

from shesha.experimental.multi_repo.models import (
    ImpactReport,
    RepoSummary,
)

if TYPE_CHECKING:
    from shesha import Shesha


class MultiRepoAnalyzer:
    """Federated PRD analysis across multiple repositories.

    Coordinates analysis of how a PRD impacts multiple codebases,
    running queries against individual projects and synthesizing
    results into a draft HLD.
    """

    def __init__(
        self,
        shesha: "Shesha",
        max_discovery_rounds: int = 2,
        max_revision_rounds: int = 2,
        phase_timeout_seconds: int = 300,
        total_timeout_seconds: int = 1800,
    ) -> None:
        """Initialize the analyzer.

        Args:
            shesha: Shesha instance for project management.
            max_discovery_rounds: Max rounds of discovering new repos (default 2).
            max_revision_rounds: Max rounds of HLD revision (default 2).
            phase_timeout_seconds: Timeout per phase query (default 5 min).
            total_timeout_seconds: Total analysis timeout (default 30 min).
        """
        self._shesha = shesha
        self._max_discovery_rounds = max_discovery_rounds
        self._max_revision_rounds = max_revision_rounds
        self._phase_timeout_seconds = phase_timeout_seconds
        self._total_timeout_seconds = total_timeout_seconds

        self._repos: list[str] = []
        self._summaries: dict[str, RepoSummary] = {}
        self._impacts: dict[str, ImpactReport] = {}

    @property
    def repos(self) -> list[str]:
        """List of project_ids currently in the analysis."""
        return self._repos

    @property
    def summaries(self) -> dict[str, RepoSummary]:
        """Recon summaries by project_id (populated after Phase 1)."""
        return self._summaries

    @property
    def impacts(self) -> dict[str, ImpactReport]:
        """Impact reports by project_id (populated after Phase 2)."""
        return self._impacts

    def add_repo(self, url_or_path: str) -> str:
        """Add a repo to the analysis.

        If the repo was previously indexed, reuses it (with update check).
        If updates are available, they are automatically applied.

        Args:
            url_or_path: Git repository URL or local filesystem path.

        Returns:
            The project_id for the added repository.
        """
        result = self._shesha.create_project_from_repo(url_or_path)

        # Apply updates if available
        if result.status == "updates_available":
            result = result.apply_updates()

        project_id = result.project.project_id

        # Avoid duplicates
        if project_id not in self._repos:
            self._repos.append(project_id)

        return project_id
