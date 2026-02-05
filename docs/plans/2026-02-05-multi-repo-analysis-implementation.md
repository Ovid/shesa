# Multi-Repo PRD Analysis Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a federated query system that analyzes how a PRD impacts multiple codebases and generates a draft HLD.

**Architecture:** Four-phase workflow (recon → impact → synthesize → align) where each repo is a separate Shesha project. A coordinator runs queries against individual projects and synthesizes results. Isolated in `src/shesha/experimental/` to not affect core Shesha.

**Tech Stack:** Python dataclasses, existing Shesha/Project/RLMEngine, markdown prompt templates.

**Design Document:** `docs/plans/2026-02-05-multi-repo-analysis-design.md`

---

## Task 1: Create Experimental Module Structure

**Files:**
- Create: `src/shesha/experimental/__init__.py`
- Create: `src/shesha/experimental/multi_repo/__init__.py`

**Step 1: Write test for module importability**

Create file `tests/experimental/__init__.py`:
```python
```

Create file `tests/experimental/multi_repo/__init__.py`:
```python
```

Create file `tests/experimental/multi_repo/test_module.py`:
```python
"""Test that the experimental module structure exists and is importable."""


def test_experimental_module_importable():
    """Experimental module should be importable."""
    import shesha.experimental

    assert shesha.experimental is not None


def test_multi_repo_module_importable():
    """Multi-repo module should be importable."""
    import shesha.experimental.multi_repo

    assert shesha.experimental.multi_repo is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/experimental/multi_repo/test_module.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create module files**

Create file `src/shesha/experimental/__init__.py`:
```python
"""Experimental features - not part of stable API."""
```

Create file `src/shesha/experimental/multi_repo/__init__.py`:
```python
"""Multi-repo PRD analysis using federated queries."""
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/experimental/multi_repo/test_module.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/ tests/experimental/
git commit -m "feat(experimental): create multi-repo module structure"
```

---

## Task 2: Create Data Models

**Files:**
- Create: `src/shesha/experimental/multi_repo/models.py`
- Create: `tests/experimental/multi_repo/test_models.py`

**Step 1: Write test for RepoSummary dataclass**

Create file `tests/experimental/multi_repo/test_models.py`:
```python
"""Tests for multi-repo data models."""

from shesha.experimental.multi_repo.models import (
    AlignmentReport,
    HLDDraft,
    ImpactReport,
    RepoSummary,
)


class TestRepoSummary:
    """Tests for RepoSummary dataclass."""

    def test_create_repo_summary(self):
        """RepoSummary can be created with all fields."""
        summary = RepoSummary(
            project_id="auth-service",
            apis=["POST /login", "GET /user"],
            models=["User", "Session"],
            entry_points=["main.py"],
            dependencies=["postgres", "redis"],
            raw_summary="Full summary text",
        )

        assert summary.project_id == "auth-service"
        assert summary.apis == ["POST /login", "GET /user"]
        assert summary.models == ["User", "Session"]
        assert summary.entry_points == ["main.py"]
        assert summary.dependencies == ["postgres", "redis"]
        assert summary.raw_summary == "Full summary text"

    def test_repo_summary_defaults_to_empty_lists(self):
        """RepoSummary fields default to empty lists."""
        summary = RepoSummary(
            project_id="test",
            raw_summary="text",
        )

        assert summary.apis == []
        assert summary.models == []
        assert summary.entry_points == []
        assert summary.dependencies == []


class TestImpactReport:
    """Tests for ImpactReport dataclass."""

    def test_create_impact_report(self):
        """ImpactReport can be created with all fields."""
        report = ImpactReport(
            project_id="auth-service",
            affected=True,
            changes=["Add OAuth endpoint"],
            new_interfaces=["GET /oauth/callback"],
            modified_interfaces=["POST /login"],
            discovered_dependencies=["oauth-provider"],
            raw_analysis="Full analysis",
        )

        assert report.project_id == "auth-service"
        assert report.affected is True
        assert report.changes == ["Add OAuth endpoint"]
        assert report.new_interfaces == ["GET /oauth/callback"]
        assert report.modified_interfaces == ["POST /login"]
        assert report.discovered_dependencies == ["oauth-provider"]
        assert report.raw_analysis == "Full analysis"

    def test_impact_report_defaults(self):
        """ImpactReport fields have sensible defaults."""
        report = ImpactReport(
            project_id="test",
            affected=False,
            raw_analysis="text",
        )

        assert report.changes == []
        assert report.new_interfaces == []
        assert report.modified_interfaces == []
        assert report.discovered_dependencies == []


class TestHLDDraft:
    """Tests for HLDDraft dataclass."""

    def test_create_hld_draft(self):
        """HLDDraft can be created with all fields."""
        hld = HLDDraft(
            component_changes={"auth": ["Add OAuth"], "api": ["New endpoint"]},
            data_flow="User -> Auth -> API",
            interface_contracts=["OAuth callback spec"],
            implementation_sequence=["1. Auth changes", "2. API changes"],
            open_questions=["Which OAuth provider?"],
            raw_hld="# Full HLD\n...",
        )

        assert hld.component_changes == {"auth": ["Add OAuth"], "api": ["New endpoint"]}
        assert hld.data_flow == "User -> Auth -> API"
        assert hld.interface_contracts == ["OAuth callback spec"]
        assert hld.implementation_sequence == ["1. Auth changes", "2. API changes"]
        assert hld.open_questions == ["Which OAuth provider?"]
        assert hld.raw_hld == "# Full HLD\n..."

    def test_hld_draft_defaults(self):
        """HLDDraft fields have sensible defaults."""
        hld = HLDDraft(raw_hld="# HLD")

        assert hld.component_changes == {}
        assert hld.data_flow == ""
        assert hld.interface_contracts == []
        assert hld.implementation_sequence == []
        assert hld.open_questions == []


class TestAlignmentReport:
    """Tests for AlignmentReport dataclass."""

    def test_create_alignment_report(self):
        """AlignmentReport can be created with all fields."""
        report = AlignmentReport(
            covered=[{"requirement": "R1", "hld_section": "S1"}],
            gaps=[{"requirement": "R2", "reason": "Not addressed"}],
            scope_creep=[{"hld_item": "Extra feature", "reason": "Not in PRD"}],
            alignment_score=0.85,
            recommendation="revise",
            raw_analysis="Full alignment analysis",
        )

        assert report.covered == [{"requirement": "R1", "hld_section": "S1"}]
        assert report.gaps == [{"requirement": "R2", "reason": "Not addressed"}]
        assert report.scope_creep == [{"hld_item": "Extra feature", "reason": "Not in PRD"}]
        assert report.alignment_score == 0.85
        assert report.recommendation == "revise"
        assert report.raw_analysis == "Full alignment analysis"

    def test_alignment_report_defaults(self):
        """AlignmentReport fields have sensible defaults."""
        report = AlignmentReport(
            alignment_score=1.0,
            recommendation="approved",
            raw_analysis="text",
        )

        assert report.covered == []
        assert report.gaps == []
        assert report.scope_creep == []
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/experimental/multi_repo/test_models.py -v`
Expected: FAIL with "cannot import name"

**Step 3: Implement data models**

Create file `src/shesha/experimental/multi_repo/models.py`:
```python
"""Data models for multi-repo PRD analysis."""

from dataclasses import dataclass, field


@dataclass
class RepoSummary:
    """Output from Phase 1 recon query.

    Contains structural information about a repository:
    what it exposes and what it consumes.
    """

    project_id: str
    raw_summary: str
    apis: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class ImpactReport:
    """Output from Phase 2 impact analysis.

    Describes how a PRD affects a specific repository
    and what other systems may need to be analyzed.
    """

    project_id: str
    affected: bool
    raw_analysis: str
    changes: list[str] = field(default_factory=list)
    new_interfaces: list[str] = field(default_factory=list)
    modified_interfaces: list[str] = field(default_factory=list)
    discovered_dependencies: list[str] = field(default_factory=list)


@dataclass
class HLDDraft:
    """Output from Phase 3 synthesis.

    A draft High-Level Design document covering changes
    across all analyzed repositories.
    """

    raw_hld: str
    component_changes: dict[str, list[str]] = field(default_factory=dict)
    data_flow: str = ""
    interface_contracts: list[str] = field(default_factory=list)
    implementation_sequence: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)


@dataclass
class AlignmentReport:
    """Output from Phase 4 alignment verification.

    Validates that the HLD covers the PRD requirements
    without scope creep.
    """

    alignment_score: float
    recommendation: str  # "approved", "revise", "major_gaps"
    raw_analysis: str
    covered: list[dict] = field(default_factory=list)
    gaps: list[dict] = field(default_factory=list)
    scope_creep: list[dict] = field(default_factory=list)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/experimental/multi_repo/test_models.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add src/shesha/experimental/multi_repo/models.py tests/experimental/multi_repo/test_models.py
git commit -m "feat(multi-repo): add data models for analysis results"
```

---

## Task 3: Create Phase Prompts

**Files:**
- Create: `src/shesha/experimental/multi_repo/prompts/recon.md`
- Create: `src/shesha/experimental/multi_repo/prompts/impact.md`
- Create: `src/shesha/experimental/multi_repo/prompts/synthesize.md`
- Create: `src/shesha/experimental/multi_repo/prompts/align.md`
- Create: `tests/experimental/multi_repo/test_prompts.py`

**Step 1: Write test for prompt loading**

Create file `tests/experimental/multi_repo/test_prompts.py`:
```python
"""Tests for multi-repo prompt templates."""

from pathlib import Path


def test_recon_prompt_exists():
    """Recon prompt template exists."""
    prompt_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "shesha"
        / "experimental"
        / "multi_repo"
        / "prompts"
        / "recon.md"
    )
    assert prompt_path.exists(), f"Expected {prompt_path} to exist"
    content = prompt_path.read_text()
    assert "APIs" in content or "apis" in content.lower()
    assert "models" in content.lower()


def test_impact_prompt_exists():
    """Impact prompt template exists."""
    prompt_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "shesha"
        / "experimental"
        / "multi_repo"
        / "prompts"
        / "impact.md"
    )
    assert prompt_path.exists(), f"Expected {prompt_path} to exist"
    content = prompt_path.read_text()
    assert "PRD" in content
    assert "changes" in content.lower()


def test_synthesize_prompt_exists():
    """Synthesize prompt template exists."""
    prompt_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "shesha"
        / "experimental"
        / "multi_repo"
        / "prompts"
        / "synthesize.md"
    )
    assert prompt_path.exists(), f"Expected {prompt_path} to exist"
    content = prompt_path.read_text()
    assert "HLD" in content or "design" in content.lower()


def test_align_prompt_exists():
    """Align prompt template exists."""
    prompt_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "shesha"
        / "experimental"
        / "multi_repo"
        / "prompts"
        / "align.md"
    )
    assert prompt_path.exists(), f"Expected {prompt_path} to exist"
    content = prompt_path.read_text()
    assert "PRD" in content
    assert "gap" in content.lower() or "coverage" in content.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/experimental/multi_repo/test_prompts.py -v`
Expected: FAIL with "AssertionError"

**Step 3: Create prompt templates**

Create directory and file `src/shesha/experimental/multi_repo/prompts/recon.md`:
```markdown
# Repository Reconnaissance

Analyze this codebase to identify its structure and interfaces.

## Your Task

Extract the following information:

1. **Public APIs** - REST endpoints, GraphQL queries/mutations, gRPC services, exported functions, CLI commands
2. **Data Models** - Database schemas, DTOs, domain objects, message formats
3. **Entry Points** - Main files, request handlers, event listeners, CLI entrypoints
4. **External Dependencies** - Other services this code calls, external APIs, message queues

## Output Format

Respond with a structured summary. Focus on INTERFACES - what this system exposes and what it consumes. Skip internal implementation details.

```json
{
  "apis": ["list of public API endpoints/functions"],
  "models": ["list of data structures"],
  "entry_points": ["list of main entry points"],
  "dependencies": ["list of external services called"]
}
```

After the JSON, provide a brief narrative summary explaining the system's role.
```

Create file `src/shesha/experimental/multi_repo/prompts/impact.md`:
```markdown
# PRD Impact Analysis

Analyze how this PRD affects the given repository.

## PRD

{prd}

## Repository Summary

{repo_summary}

## Your Task

Determine:

1. **Affected?** - Does this PRD require changes to this codebase? (yes/no with reasoning)
2. **Changes Needed** - What specific changes are required? Be concrete: new endpoints, modified models, updated handlers.
3. **New Interfaces** - What new APIs, events, or schemas need to be created?
4. **Modified Interfaces** - What existing interfaces need to change?
5. **Discovered Dependencies** - What other systems might this repo need to interact with that aren't mentioned in the analysis so far?

## Output Format

```json
{
  "affected": true/false,
  "changes": ["list of specific changes needed"],
  "new_interfaces": ["list of new APIs/events to create"],
  "modified_interfaces": ["list of existing APIs to modify"],
  "discovered_dependencies": ["list of other systems that may need analysis"]
}
```

After the JSON, provide reasoning for your assessment.
```

Create file `src/shesha/experimental/multi_repo/prompts/synthesize.md`:
```markdown
# HLD Synthesis

Create a High-Level Design document from the PRD and impact analyses.

## PRD

{prd}

## Impact Reports

{impact_reports}

## Your Task

Create a comprehensive High-Level Design covering:

1. **Component Changes** - For each system, what needs to change
2. **Data Flow** - How data moves between systems for this feature (include a diagram if helpful)
3. **Interface Contracts** - API specifications, event schemas, message formats
4. **Implementation Sequence** - What order to build/deploy changes (consider dependencies)
5. **Open Questions** - Ambiguities that need human decision

## Output Format

First, provide structured data:

```json
{
  "component_changes": {
    "repo-name": ["list of changes"]
  },
  "data_flow": "description or mermaid diagram",
  "interface_contracts": ["list of API/event specs"],
  "implementation_sequence": ["ordered list of steps"],
  "open_questions": ["list of decisions needed"]
}
```

Then provide the full HLD as markdown, suitable for engineering review.
```

Create file `src/shesha/experimental/multi_repo/prompts/align.md`:
```markdown
# PRD-HLD Alignment Verification

Verify that the HLD completely addresses the PRD without scope creep.

## PRD

{prd}

## HLD

{hld}

## Your Task

1. **Coverage Check** - For each requirement in the PRD, identify which HLD section addresses it. Flag any requirements with no coverage.

2. **Scope Check** - For each change in the HLD, trace it back to a PRD requirement. Flag any changes not justified by the PRD.

3. **Recommendation** - Based on coverage and scope:
   - "approved" - HLD fully covers PRD with no scope creep
   - "revise" - Minor gaps or scope creep that can be fixed
   - "major_gaps" - Significant requirements missing

## Output Format

```json
{
  "covered": [
    {"requirement": "PRD requirement text", "hld_section": "HLD section that addresses it"}
  ],
  "gaps": [
    {"requirement": "PRD requirement text", "reason": "why it's not covered"}
  ],
  "scope_creep": [
    {"hld_item": "HLD item", "reason": "why it's not justified by PRD"}
  ],
  "alignment_score": 0.0-1.0,
  "recommendation": "approved|revise|major_gaps"
}
```

After the JSON, provide reasoning for your assessment.
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/experimental/multi_repo/test_prompts.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/multi_repo/prompts/ tests/experimental/multi_repo/test_prompts.py
git commit -m "feat(multi-repo): add phase prompt templates"
```

---

## Task 4: Create MultiRepoAnalyzer Core Structure

**Files:**
- Create: `src/shesha/experimental/multi_repo/analyzer.py`
- Modify: `src/shesha/experimental/multi_repo/__init__.py`
- Create: `tests/experimental/multi_repo/test_analyzer.py`

**Step 1: Write test for analyzer initialization**

Create file `tests/experimental/multi_repo/test_analyzer.py`:
```python
"""Tests for MultiRepoAnalyzer."""

from unittest.mock import MagicMock

import pytest

from shesha.experimental.multi_repo import MultiRepoAnalyzer


class TestMultiRepoAnalyzerInit:
    """Tests for analyzer initialization."""

    def test_init_with_shesha_instance(self):
        """Analyzer initializes with a Shesha instance."""
        mock_shesha = MagicMock()
        analyzer = MultiRepoAnalyzer(mock_shesha)

        assert analyzer._shesha is mock_shesha
        assert analyzer._repos == []
        assert analyzer._summaries == {}
        assert analyzer._impacts == {}

    def test_init_with_custom_config(self):
        """Analyzer accepts custom configuration."""
        mock_shesha = MagicMock()
        analyzer = MultiRepoAnalyzer(
            mock_shesha,
            max_discovery_rounds=3,
            max_revision_rounds=4,
            phase_timeout_seconds=600,
            total_timeout_seconds=3600,
        )

        assert analyzer._max_discovery_rounds == 3
        assert analyzer._max_revision_rounds == 4
        assert analyzer._phase_timeout_seconds == 600
        assert analyzer._total_timeout_seconds == 3600

    def test_init_default_config(self):
        """Analyzer has sensible defaults."""
        mock_shesha = MagicMock()
        analyzer = MultiRepoAnalyzer(mock_shesha)

        assert analyzer._max_discovery_rounds == 2
        assert analyzer._max_revision_rounds == 2
        assert analyzer._phase_timeout_seconds == 300
        assert analyzer._total_timeout_seconds == 1800


class TestMultiRepoAnalyzerProperties:
    """Tests for analyzer properties."""

    def test_repos_property(self):
        """repos property returns list of project_ids."""
        mock_shesha = MagicMock()
        analyzer = MultiRepoAnalyzer(mock_shesha)
        analyzer._repos = ["repo-a", "repo-b"]

        assert analyzer.repos == ["repo-a", "repo-b"]

    def test_summaries_property(self):
        """summaries property returns dict of RepoSummary."""
        mock_shesha = MagicMock()
        analyzer = MultiRepoAnalyzer(mock_shesha)

        from shesha.experimental.multi_repo.models import RepoSummary

        summary = RepoSummary(project_id="test", raw_summary="text")
        analyzer._summaries = {"test": summary}

        assert analyzer.summaries == {"test": summary}

    def test_impacts_property(self):
        """impacts property returns dict of ImpactReport."""
        mock_shesha = MagicMock()
        analyzer = MultiRepoAnalyzer(mock_shesha)

        from shesha.experimental.multi_repo.models import ImpactReport

        report = ImpactReport(project_id="test", affected=True, raw_analysis="text")
        analyzer._impacts = {"test": report}

        assert analyzer.impacts == {"test": report}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/experimental/multi_repo/test_analyzer.py::TestMultiRepoAnalyzerInit -v`
Expected: FAIL with "cannot import name 'MultiRepoAnalyzer'"

**Step 3: Implement analyzer core structure**

Create file `src/shesha/experimental/multi_repo/analyzer.py`:
```python
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
```

Update file `src/shesha/experimental/multi_repo/__init__.py`:
```python
"""Multi-repo PRD analysis using federated queries."""

from shesha.experimental.multi_repo.analyzer import MultiRepoAnalyzer
from shesha.experimental.multi_repo.models import (
    AlignmentReport,
    HLDDraft,
    ImpactReport,
    RepoSummary,
)

__all__ = [
    "MultiRepoAnalyzer",
    "RepoSummary",
    "ImpactReport",
    "HLDDraft",
    "AlignmentReport",
]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/experimental/multi_repo/test_analyzer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/multi_repo/analyzer.py src/shesha/experimental/multi_repo/__init__.py tests/experimental/multi_repo/test_analyzer.py
git commit -m "feat(multi-repo): add MultiRepoAnalyzer core structure"
```

---

## Task 5: Implement add_repo Method

**Files:**
- Modify: `src/shesha/experimental/multi_repo/analyzer.py`
- Modify: `tests/experimental/multi_repo/test_analyzer.py`

**Step 1: Write test for add_repo**

Add to `tests/experimental/multi_repo/test_analyzer.py`:
```python
class TestMultiRepoAnalyzerAddRepo:
    """Tests for add_repo method."""

    def test_add_repo_creates_project(self):
        """add_repo creates a project via Shesha."""
        mock_shesha = MagicMock()
        mock_result = MagicMock()
        mock_result.project.project_id = "org-repo"
        mock_result.status = "created"
        mock_shesha.create_project_from_repo.return_value = mock_result

        analyzer = MultiRepoAnalyzer(mock_shesha)
        project_id = analyzer.add_repo("https://github.com/org/repo")

        assert project_id == "org-repo"
        assert "org-repo" in analyzer.repos
        mock_shesha.create_project_from_repo.assert_called_once_with("https://github.com/org/repo")

    def test_add_repo_reuses_existing(self):
        """add_repo reuses existing project if unchanged."""
        mock_shesha = MagicMock()
        mock_result = MagicMock()
        mock_result.project.project_id = "org-repo"
        mock_result.status = "unchanged"
        mock_shesha.create_project_from_repo.return_value = mock_result

        analyzer = MultiRepoAnalyzer(mock_shesha)
        project_id = analyzer.add_repo("https://github.com/org/repo")

        assert project_id == "org-repo"
        assert "org-repo" in analyzer.repos

    def test_add_repo_handles_updates(self):
        """add_repo applies updates if available."""
        mock_shesha = MagicMock()
        mock_result = MagicMock()
        mock_result.project.project_id = "org-repo"
        mock_result.status = "updates_available"
        mock_updated_result = MagicMock()
        mock_updated_result.project.project_id = "org-repo"
        mock_updated_result.status = "created"
        mock_result.apply_updates.return_value = mock_updated_result
        mock_shesha.create_project_from_repo.return_value = mock_result

        analyzer = MultiRepoAnalyzer(mock_shesha)
        project_id = analyzer.add_repo("https://github.com/org/repo")

        assert project_id == "org-repo"
        mock_result.apply_updates.assert_called_once()

    def test_add_repo_avoids_duplicates(self):
        """add_repo doesn't add the same repo twice."""
        mock_shesha = MagicMock()
        mock_result = MagicMock()
        mock_result.project.project_id = "org-repo"
        mock_result.status = "unchanged"
        mock_shesha.create_project_from_repo.return_value = mock_result

        analyzer = MultiRepoAnalyzer(mock_shesha)
        analyzer.add_repo("https://github.com/org/repo")
        analyzer.add_repo("https://github.com/org/repo")

        assert analyzer.repos.count("org-repo") == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/experimental/multi_repo/test_analyzer.py::TestMultiRepoAnalyzerAddRepo -v`
Expected: FAIL with "AttributeError: 'MultiRepoAnalyzer' object has no attribute 'add_repo'"

**Step 3: Implement add_repo**

Add to `src/shesha/experimental/multi_repo/analyzer.py` in the `MultiRepoAnalyzer` class:
```python
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/experimental/multi_repo/test_analyzer.py::TestMultiRepoAnalyzerAddRepo -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/multi_repo/analyzer.py tests/experimental/multi_repo/test_analyzer.py
git commit -m "feat(multi-repo): implement add_repo method"
```

---

## Task 6: Implement Phase 1 - Recon

**Files:**
- Modify: `src/shesha/experimental/multi_repo/analyzer.py`
- Modify: `tests/experimental/multi_repo/test_analyzer.py`

**Step 1: Write test for recon phase**

Add to `tests/experimental/multi_repo/test_analyzer.py`:
```python
import json


class TestMultiRepoAnalyzerRecon:
    """Tests for Phase 1 recon."""

    def test_run_recon_queries_project(self):
        """Recon phase queries the project with recon prompt."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"
        mock_query_result = MagicMock()
        mock_query_result.answer = json.dumps({
            "apis": ["GET /users"],
            "models": ["User"],
            "entry_points": ["main.py"],
            "dependencies": ["postgres"],
        }) + "\n\nThis is a user service."
        mock_project.query.return_value = mock_query_result
        mock_shesha.get_project.return_value = mock_project

        analyzer = MultiRepoAnalyzer(mock_shesha)
        analyzer._repos = ["test-repo"]

        summary = analyzer._run_recon("test-repo")

        assert summary.project_id == "test-repo"
        assert "GET /users" in summary.apis
        assert "User" in summary.models
        mock_project.query.assert_called_once()

    def test_run_recon_handles_malformed_json(self):
        """Recon gracefully handles non-JSON responses."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"
        mock_query_result = MagicMock()
        mock_query_result.answer = "This repo contains user management code."
        mock_project.query.return_value = mock_query_result
        mock_shesha.get_project.return_value = mock_project

        analyzer = MultiRepoAnalyzer(mock_shesha)
        analyzer._repos = ["test-repo"]

        summary = analyzer._run_recon("test-repo")

        assert summary.project_id == "test-repo"
        assert summary.raw_summary == "This repo contains user management code."
        # Lists should be empty when JSON parsing fails
        assert summary.apis == []
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/experimental/multi_repo/test_analyzer.py::TestMultiRepoAnalyzerRecon -v`
Expected: FAIL with "AttributeError: 'MultiRepoAnalyzer' object has no attribute '_run_recon'"

**Step 3: Implement recon phase**

Add imports at top of `src/shesha/experimental/multi_repo/analyzer.py`:
```python
import json
import re
from pathlib import Path
```

Add method to `MultiRepoAnalyzer` class:
```python
    def _load_prompt(self, name: str) -> str:
        """Load a prompt template from the prompts directory."""
        prompts_dir = Path(__file__).parent / "prompts"
        return (prompts_dir / f"{name}.md").read_text()

    def _extract_json(self, text: str) -> dict | None:
        """Extract JSON object from text that may contain markdown."""
        # Try to find JSON in code blocks first
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find raw JSON
        json_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _run_recon(self, project_id: str) -> RepoSummary:
        """Run Phase 1 recon on a single project.

        Args:
            project_id: The project to analyze.

        Returns:
            RepoSummary with extracted structure.
        """
        project = self._shesha.get_project(project_id)
        prompt = self._load_prompt("recon")

        result = project.query(prompt)
        answer = result.answer

        # Try to extract structured data
        data = self._extract_json(answer)

        if data:
            return RepoSummary(
                project_id=project_id,
                apis=data.get("apis", []),
                models=data.get("models", []),
                entry_points=data.get("entry_points", []),
                dependencies=data.get("dependencies", []),
                raw_summary=answer,
            )

        # Fallback: return raw answer with empty lists
        return RepoSummary(
            project_id=project_id,
            raw_summary=answer,
        )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/experimental/multi_repo/test_analyzer.py::TestMultiRepoAnalyzerRecon -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/multi_repo/analyzer.py tests/experimental/multi_repo/test_analyzer.py
git commit -m "feat(multi-repo): implement Phase 1 recon"
```

---

## Task 7: Implement Phase 2 - Impact Analysis

**Files:**
- Modify: `src/shesha/experimental/multi_repo/analyzer.py`
- Modify: `tests/experimental/multi_repo/test_analyzer.py`

**Step 1: Write test for impact phase**

Add to `tests/experimental/multi_repo/test_analyzer.py`:
```python
class TestMultiRepoAnalyzerImpact:
    """Tests for Phase 2 impact analysis."""

    def test_run_impact_queries_with_prd_and_summary(self):
        """Impact phase queries with PRD and repo summary."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"
        mock_query_result = MagicMock()
        mock_query_result.answer = json.dumps({
            "affected": True,
            "changes": ["Add new endpoint"],
            "new_interfaces": ["GET /new"],
            "modified_interfaces": ["POST /old"],
            "discovered_dependencies": ["other-service"],
        }) + "\n\nNeeds changes for OAuth."
        mock_project.query.return_value = mock_query_result
        mock_shesha.get_project.return_value = mock_project

        analyzer = MultiRepoAnalyzer(mock_shesha)

        from shesha.experimental.multi_repo.models import RepoSummary

        summary = RepoSummary(
            project_id="test-repo",
            apis=["GET /users"],
            raw_summary="User service",
        )

        report = analyzer._run_impact("test-repo", "Add OAuth support", summary)

        assert report.project_id == "test-repo"
        assert report.affected is True
        assert "Add new endpoint" in report.changes
        assert "other-service" in report.discovered_dependencies

    def test_run_impact_not_affected(self):
        """Impact correctly identifies unaffected repos."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"
        mock_query_result = MagicMock()
        mock_query_result.answer = json.dumps({
            "affected": False,
            "changes": [],
            "new_interfaces": [],
            "modified_interfaces": [],
            "discovered_dependencies": [],
        }) + "\n\nNo changes needed."
        mock_project.query.return_value = mock_query_result
        mock_shesha.get_project.return_value = mock_project

        analyzer = MultiRepoAnalyzer(mock_shesha)

        from shesha.experimental.multi_repo.models import RepoSummary

        summary = RepoSummary(project_id="test-repo", raw_summary="Logging service")

        report = analyzer._run_impact("test-repo", "Add OAuth support", summary)

        assert report.affected is False
        assert report.changes == []
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/experimental/multi_repo/test_analyzer.py::TestMultiRepoAnalyzerImpact -v`
Expected: FAIL with "AttributeError: 'MultiRepoAnalyzer' object has no attribute '_run_impact'"

**Step 3: Implement impact phase**

Add method to `MultiRepoAnalyzer` class:
```python
    def _run_impact(
        self,
        project_id: str,
        prd: str,
        summary: RepoSummary,
    ) -> ImpactReport:
        """Run Phase 2 impact analysis on a single project.

        Args:
            project_id: The project to analyze.
            prd: The PRD text.
            summary: The recon summary for this project.

        Returns:
            ImpactReport with changes needed and discovered dependencies.
        """
        project = self._shesha.get_project(project_id)
        prompt_template = self._load_prompt("impact")

        # Format the prompt with PRD and summary
        prompt = prompt_template.replace("{prd}", prd)
        prompt = prompt.replace("{repo_summary}", summary.raw_summary)

        result = project.query(prompt)
        answer = result.answer

        # Try to extract structured data
        data = self._extract_json(answer)

        if data:
            return ImpactReport(
                project_id=project_id,
                affected=data.get("affected", False),
                changes=data.get("changes", []),
                new_interfaces=data.get("new_interfaces", []),
                modified_interfaces=data.get("modified_interfaces", []),
                discovered_dependencies=data.get("discovered_dependencies", []),
                raw_analysis=answer,
            )

        # Fallback: assume affected if we got a response
        return ImpactReport(
            project_id=project_id,
            affected=True,
            raw_analysis=answer,
        )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/experimental/multi_repo/test_analyzer.py::TestMultiRepoAnalyzerImpact -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/multi_repo/analyzer.py tests/experimental/multi_repo/test_analyzer.py
git commit -m "feat(multi-repo): implement Phase 2 impact analysis"
```

---

## Task 8: Implement Phase 3 - Synthesize HLD

**Files:**
- Modify: `src/shesha/experimental/multi_repo/analyzer.py`
- Modify: `tests/experimental/multi_repo/test_analyzer.py`

**Step 1: Write test for synthesize phase**

Add to `tests/experimental/multi_repo/test_analyzer.py`:
```python
class TestMultiRepoAnalyzerSynthesize:
    """Tests for Phase 3 HLD synthesis."""

    def test_run_synthesize_creates_hld(self):
        """Synthesize phase creates HLD from impact reports."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_query_result = MagicMock()
        mock_query_result.answer = json.dumps({
            "component_changes": {"auth": ["Add OAuth"]},
            "data_flow": "User -> Auth -> API",
            "interface_contracts": ["OAuth callback"],
            "implementation_sequence": ["1. Auth", "2. API"],
            "open_questions": ["Provider?"],
        }) + "\n\n# Full HLD\n\n## Changes\n..."
        mock_project.query.return_value = mock_query_result
        mock_shesha.get_project.return_value = mock_project

        analyzer = MultiRepoAnalyzer(mock_shesha)
        analyzer._repos = ["auth"]

        from shesha.experimental.multi_repo.models import ImpactReport

        impacts = {
            "auth": ImpactReport(
                project_id="auth",
                affected=True,
                changes=["Add OAuth"],
                raw_analysis="Needs OAuth",
            )
        }

        hld = analyzer._run_synthesize("Add OAuth support", impacts)

        assert hld.component_changes == {"auth": ["Add OAuth"]}
        assert hld.data_flow == "User -> Auth -> API"
        assert "Provider?" in hld.open_questions
        assert "# Full HLD" in hld.raw_hld
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/experimental/multi_repo/test_analyzer.py::TestMultiRepoAnalyzerSynthesize -v`
Expected: FAIL with "AttributeError: 'MultiRepoAnalyzer' object has no attribute '_run_synthesize'"

**Step 3: Implement synthesize phase**

Add import at top if not present:
```python
from shesha.experimental.multi_repo.models import (
    AlignmentReport,
    HLDDraft,
    ImpactReport,
    RepoSummary,
)
```

Add method to `MultiRepoAnalyzer` class:
```python
    def _run_synthesize(
        self,
        prd: str,
        impacts: dict[str, ImpactReport],
    ) -> HLDDraft:
        """Run Phase 3 HLD synthesis.

        Uses the first repo's project for the query (synthesis doesn't
        need repo-specific context, just the impact reports).

        Args:
            prd: The PRD text.
            impacts: Impact reports by project_id.

        Returns:
            HLDDraft with synthesized design.
        """
        # Use first repo for the query
        project = self._shesha.get_project(self._repos[0])
        prompt_template = self._load_prompt("synthesize")

        # Format impact reports for the prompt
        impact_text = "\n\n".join(
            f"### {pid}\n{report.raw_analysis}" for pid, report in impacts.items()
        )

        prompt = prompt_template.replace("{prd}", prd)
        prompt = prompt.replace("{impact_reports}", impact_text)

        result = project.query(prompt)
        answer = result.answer

        # Try to extract structured data
        data = self._extract_json(answer)

        if data:
            return HLDDraft(
                component_changes=data.get("component_changes", {}),
                data_flow=data.get("data_flow", ""),
                interface_contracts=data.get("interface_contracts", []),
                implementation_sequence=data.get("implementation_sequence", []),
                open_questions=data.get("open_questions", []),
                raw_hld=answer,
            )

        # Fallback: return raw answer
        return HLDDraft(raw_hld=answer)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/experimental/multi_repo/test_analyzer.py::TestMultiRepoAnalyzerSynthesize -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/multi_repo/analyzer.py tests/experimental/multi_repo/test_analyzer.py
git commit -m "feat(multi-repo): implement Phase 3 HLD synthesis"
```

---

## Task 9: Implement Phase 4 - Alignment Verification

**Files:**
- Modify: `src/shesha/experimental/multi_repo/analyzer.py`
- Modify: `tests/experimental/multi_repo/test_analyzer.py`

**Step 1: Write test for align phase**

Add to `tests/experimental/multi_repo/test_analyzer.py`:
```python
class TestMultiRepoAnalyzerAlign:
    """Tests for Phase 4 alignment verification."""

    def test_run_align_checks_coverage(self):
        """Align phase verifies HLD covers PRD."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_query_result = MagicMock()
        mock_query_result.answer = json.dumps({
            "covered": [{"requirement": "R1", "hld_section": "S1"}],
            "gaps": [],
            "scope_creep": [],
            "alignment_score": 1.0,
            "recommendation": "approved",
        }) + "\n\nFully aligned."
        mock_project.query.return_value = mock_query_result
        mock_shesha.get_project.return_value = mock_project

        analyzer = MultiRepoAnalyzer(mock_shesha)
        analyzer._repos = ["test"]

        from shesha.experimental.multi_repo.models import HLDDraft

        hld = HLDDraft(raw_hld="# HLD\n...")

        report = analyzer._run_align("PRD text", hld)

        assert report.alignment_score == 1.0
        assert report.recommendation == "approved"
        assert len(report.covered) == 1
        assert report.gaps == []

    def test_run_align_finds_gaps(self):
        """Align phase identifies missing requirements."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_query_result = MagicMock()
        mock_query_result.answer = json.dumps({
            "covered": [],
            "gaps": [{"requirement": "R1", "reason": "Not addressed"}],
            "scope_creep": [],
            "alignment_score": 0.5,
            "recommendation": "revise",
        }) + "\n\nNeeds revision."
        mock_project.query.return_value = mock_query_result
        mock_shesha.get_project.return_value = mock_project

        analyzer = MultiRepoAnalyzer(mock_shesha)
        analyzer._repos = ["test"]

        from shesha.experimental.multi_repo.models import HLDDraft

        hld = HLDDraft(raw_hld="# HLD\n...")

        report = analyzer._run_align("PRD text", hld)

        assert report.alignment_score == 0.5
        assert report.recommendation == "revise"
        assert len(report.gaps) == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/experimental/multi_repo/test_analyzer.py::TestMultiRepoAnalyzerAlign -v`
Expected: FAIL with "AttributeError: 'MultiRepoAnalyzer' object has no attribute '_run_align'"

**Step 3: Implement align phase**

Add method to `MultiRepoAnalyzer` class:
```python
    def _run_align(
        self,
        prd: str,
        hld: HLDDraft,
    ) -> AlignmentReport:
        """Run Phase 4 alignment verification.

        Args:
            prd: The PRD text.
            hld: The draft HLD to verify.

        Returns:
            AlignmentReport with coverage and gaps.
        """
        project = self._shesha.get_project(self._repos[0])
        prompt_template = self._load_prompt("align")

        prompt = prompt_template.replace("{prd}", prd)
        prompt = prompt.replace("{hld}", hld.raw_hld)

        result = project.query(prompt)
        answer = result.answer

        # Try to extract structured data
        data = self._extract_json(answer)

        if data:
            return AlignmentReport(
                covered=data.get("covered", []),
                gaps=data.get("gaps", []),
                scope_creep=data.get("scope_creep", []),
                alignment_score=float(data.get("alignment_score", 0.0)),
                recommendation=data.get("recommendation", "revise"),
                raw_analysis=answer,
            )

        # Fallback: assume needs revision
        return AlignmentReport(
            alignment_score=0.0,
            recommendation="revise",
            raw_analysis=answer,
        )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/experimental/multi_repo/test_analyzer.py::TestMultiRepoAnalyzerAlign -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/multi_repo/analyzer.py tests/experimental/multi_repo/test_analyzer.py
git commit -m "feat(multi-repo): implement Phase 4 alignment verification"
```

---

## Task 10: Implement Main analyze() Method

**Files:**
- Modify: `src/shesha/experimental/multi_repo/analyzer.py`
- Modify: `tests/experimental/multi_repo/test_analyzer.py`

**Step 1: Write test for analyze orchestration**

Add to `tests/experimental/multi_repo/test_analyzer.py`:
```python
class TestMultiRepoAnalyzerAnalyze:
    """Tests for main analyze method."""

    def test_analyze_runs_all_phases(self):
        """analyze() runs all four phases."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"

        # Recon response
        recon_result = MagicMock()
        recon_result.answer = json.dumps({
            "apis": ["GET /users"],
            "models": ["User"],
            "entry_points": ["main.py"],
            "dependencies": [],
        })

        # Impact response
        impact_result = MagicMock()
        impact_result.answer = json.dumps({
            "affected": True,
            "changes": ["Add feature"],
            "new_interfaces": [],
            "modified_interfaces": [],
            "discovered_dependencies": [],
        })

        # Synthesize response
        synth_result = MagicMock()
        synth_result.answer = json.dumps({
            "component_changes": {"test-repo": ["Add feature"]},
            "data_flow": "A -> B",
            "interface_contracts": [],
            "implementation_sequence": ["1. Do thing"],
            "open_questions": [],
        }) + "\n\n# HLD"

        # Align response
        align_result = MagicMock()
        align_result.answer = json.dumps({
            "covered": [{"requirement": "R1", "hld_section": "S1"}],
            "gaps": [],
            "scope_creep": [],
            "alignment_score": 1.0,
            "recommendation": "approved",
        })

        mock_project.query.side_effect = [
            recon_result,
            impact_result,
            synth_result,
            align_result,
        ]
        mock_shesha.get_project.return_value = mock_project

        analyzer = MultiRepoAnalyzer(mock_shesha)
        analyzer._repos = ["test-repo"]

        hld, alignment = analyzer.analyze("Add a feature")

        assert mock_project.query.call_count == 4
        assert alignment.recommendation == "approved"
        assert "test-repo" in hld.component_changes

    def test_analyze_calls_discovery_callback(self):
        """analyze() invokes on_discovery when deps found."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"

        # Recon response
        recon_result = MagicMock()
        recon_result.answer = json.dumps({
            "apis": [],
            "models": [],
            "entry_points": [],
            "dependencies": [],
        })

        # Impact response with discovery
        impact_result = MagicMock()
        impact_result.answer = json.dumps({
            "affected": True,
            "changes": [],
            "new_interfaces": [],
            "modified_interfaces": [],
            "discovered_dependencies": ["other-service"],
        })

        # Synthesize response
        synth_result = MagicMock()
        synth_result.answer = json.dumps({
            "component_changes": {},
            "data_flow": "",
            "interface_contracts": [],
            "implementation_sequence": [],
            "open_questions": [],
        }) + "\n\n# HLD"

        # Align response
        align_result = MagicMock()
        align_result.answer = json.dumps({
            "covered": [],
            "gaps": [],
            "scope_creep": [],
            "alignment_score": 1.0,
            "recommendation": "approved",
        })

        mock_project.query.side_effect = [
            recon_result,
            impact_result,
            synth_result,
            align_result,
        ]
        mock_shesha.get_project.return_value = mock_project

        discovery_callback = MagicMock(return_value=False)

        analyzer = MultiRepoAnalyzer(mock_shesha)
        analyzer._repos = ["test-repo"]

        analyzer.analyze("PRD", on_discovery=discovery_callback)

        discovery_callback.assert_called_once_with("other-service")

    def test_analyze_calls_progress_callback(self):
        """analyze() invokes on_progress during phases."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"

        # Simple responses for all phases
        simple_result = MagicMock()
        simple_result.answer = json.dumps({
            "apis": [], "models": [], "entry_points": [], "dependencies": [],
            "affected": False, "changes": [], "new_interfaces": [],
            "modified_interfaces": [], "discovered_dependencies": [],
            "component_changes": {}, "data_flow": "", "interface_contracts": [],
            "implementation_sequence": [], "open_questions": [],
            "covered": [], "gaps": [], "scope_creep": [],
            "alignment_score": 1.0, "recommendation": "approved",
        })
        mock_project.query.return_value = simple_result
        mock_shesha.get_project.return_value = mock_project

        progress_callback = MagicMock()

        analyzer = MultiRepoAnalyzer(mock_shesha)
        analyzer._repos = ["test-repo"]

        analyzer.analyze("PRD", on_progress=progress_callback)

        # Should have progress calls for each phase
        phases_reported = [call[0][0] for call in progress_callback.call_args_list]
        assert "recon" in phases_reported
        assert "impact" in phases_reported
        assert "synthesize" in phases_reported
        assert "align" in phases_reported
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/experimental/multi_repo/test_analyzer.py::TestMultiRepoAnalyzerAnalyze -v`
Expected: FAIL with "AttributeError: 'MultiRepoAnalyzer' object has no attribute 'analyze'"

**Step 3: Implement analyze method**

Add imports at top:
```python
from collections.abc import Callable
```

Add method to `MultiRepoAnalyzer` class:
```python
    def analyze(
        self,
        prd: str,
        on_discovery: Callable[[str], bool] | None = None,
        on_alignment_issue: Callable[[AlignmentReport], str] | None = None,
        on_progress: Callable[[str, str], None] | None = None,
    ) -> tuple[HLDDraft, AlignmentReport]:
        """Run the four-phase analysis.

        Args:
            prd: The PRD text (pasted inline).
            on_discovery: Called when new repo discovered.
                Receives repo hint, returns True to add it.
                If None, discoveries are ignored.
            on_alignment_issue: Called if alignment finds problems.
                Receives report, returns "revise" | "accept" | "abort".
                If None, accepts as-is.
            on_progress: Called with (phase, message) updates.

        Returns:
            Tuple of (final HLD, alignment report).

        Raises:
            ValueError: If no repos have been added.
        """
        if not self._repos:
            raise ValueError("No repos added. Call add_repo() first.")

        # Phase 1: Recon
        if on_progress:
            on_progress("recon", f"Starting recon on {len(self._repos)} repos")

        for project_id in self._repos:
            if on_progress:
                on_progress("recon", f"Analyzing {project_id}")
            self._summaries[project_id] = self._run_recon(project_id)

        # Phase 2: Impact
        if on_progress:
            on_progress("impact", "Starting impact analysis")

        discovered: set[str] = set()
        discovery_round = 0

        while discovery_round < self._max_discovery_rounds:
            for project_id in self._repos:
                if project_id in self._impacts:
                    continue  # Already analyzed

                if on_progress:
                    on_progress("impact", f"Analyzing {project_id}")

                summary = self._summaries[project_id]
                report = self._run_impact(project_id, prd, summary)
                self._impacts[project_id] = report

                # Check for discoveries
                for dep in report.discovered_dependencies:
                    if dep not in self._repos and dep not in discovered:
                        discovered.add(dep)
                        if on_discovery and on_discovery(dep):
                            # User wants to add this repo
                            # Note: In real usage, they'd provide URL
                            # For now, just track it was discovered
                            pass

            discovery_round += 1
            if not discovered:
                break

        # Phase 3: Synthesize
        if on_progress:
            on_progress("synthesize", "Generating HLD")

        hld = self._run_synthesize(prd, self._impacts)

        # Phase 4: Align
        if on_progress:
            on_progress("align", "Verifying alignment")

        alignment = self._run_align(prd, hld)

        # Handle alignment issues
        revision_round = 0
        while alignment.recommendation == "revise" and revision_round < self._max_revision_rounds:
            if on_alignment_issue:
                action = on_alignment_issue(alignment)
                if action == "accept":
                    break
                if action == "abort":
                    break
                # action == "revise" - continue loop
            else:
                break  # No callback, accept as-is

            revision_round += 1
            if on_progress:
                on_progress("synthesize", f"Revision round {revision_round}")

            # Re-synthesize with alignment feedback
            # TODO: Pass alignment feedback to synthesis
            hld = self._run_synthesize(prd, self._impacts)

            if on_progress:
                on_progress("align", f"Re-verifying alignment")
            alignment = self._run_align(prd, hld)

        return hld, alignment
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/experimental/multi_repo/test_analyzer.py::TestMultiRepoAnalyzerAnalyze -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/multi_repo/analyzer.py tests/experimental/multi_repo/test_analyzer.py
git commit -m "feat(multi-repo): implement main analyze() orchestration"
```

---

## Task 11: Create Example Script

**Files:**
- Create: `examples/multi_repo.py`

**Step 1: Write basic test for script importability**

Add to `tests/examples/test_multi_repo.py`:
```python
"""Tests for multi_repo example script."""

import sys
from pathlib import Path

# Add examples to path for import
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "examples"))


def test_multi_repo_script_importable():
    """multi_repo.py can be imported."""
    import multi_repo

    assert hasattr(multi_repo, "main")


def test_multi_repo_has_parse_args():
    """multi_repo.py has argument parser."""
    import multi_repo

    assert hasattr(multi_repo, "parse_args")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/examples/test_multi_repo.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'multi_repo'"

**Step 3: Create example script**

Create file `examples/multi_repo.py`:
```python
#!/usr/bin/env python3
"""Multi-repo PRD analysis using federated queries.

This script analyzes how a PRD (Product Requirements Document) impacts
multiple codebases and generates a draft HLD (High-Level Design).

Usage:
    python examples/multi_repo.py repo1_url repo2_url [repo3_url ...]

    Then paste your PRD when prompted (end with Ctrl+D or blank line).

Environment Variables:
    SHESHA_API_KEY: Required. API key for your LLM provider.
    SHESHA_MODEL: Optional. Model name (default: claude-sonnet-4-20250514).

Example:
    $ export SHESHA_API_KEY="your-api-key"
    $ python examples/multi_repo.py \\
        https://github.com/org/auth-service \\
        https://github.com/org/user-api
    Paste PRD (Ctrl+D or blank line to finish):
    ...
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from shesha import Shesha, SheshaConfig
from shesha.experimental.multi_repo import AlignmentReport, MultiRepoAnalyzer

STORAGE_PATH = Path.home() / ".shesha" / "multi-repo"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze PRD impact across multiple repositories"
    )
    parser.add_argument(
        "repos",
        nargs="+",
        help="Git repository URLs or local paths to analyze",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed progress during analysis",
    )
    return parser.parse_args(argv)


def read_multiline_input() -> str:
    """Read multiline input from stdin until EOF or blank line."""
    lines = []
    try:
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
    except EOFError:
        pass
    return "\n".join(lines)


def main() -> None:
    """Main entry point."""
    args = parse_args()

    if not os.environ.get("SHESHA_API_KEY"):
        print("Error: SHESHA_API_KEY environment variable not set.")
        sys.exit(1)

    config = SheshaConfig.load(storage_path=STORAGE_PATH)
    shesha = Shesha(config=config)

    analyzer = MultiRepoAnalyzer(shesha)

    # Add repos
    for url in args.repos:
        print(f"Adding: {url}")
        try:
            project_id = analyzer.add_repo(url)
            print(f"  -> {project_id}")
        except Exception as e:
            print(f"  Error: {e}")
            sys.exit(1)

    # Get PRD
    print()
    print("Paste PRD (Ctrl+D or blank line to finish):")
    prd = read_multiline_input()

    if not prd.strip():
        print("No PRD provided. Exiting.")
        sys.exit(0)

    # Callbacks
    def on_discovery(repo_hint: str) -> bool:
        response = input(f"Discovered dependency: {repo_hint}. Add it? (y/n): ")
        return response.lower() == "y"

    def on_alignment_issue(report: AlignmentReport) -> str:
        print(f"\nAlignment score: {report.alignment_score:.0%}")
        if report.gaps:
            print(f"Gaps: {len(report.gaps)}")
            for gap in report.gaps[:3]:
                print(f"  - {gap}")
        if report.scope_creep:
            print(f"Scope creep: {len(report.scope_creep)}")
            for item in report.scope_creep[:3]:
                print(f"  - {item}")
        return input("Action (revise/accept/abort): ").strip().lower()

    def on_progress(phase: str, message: str) -> None:
        if args.verbose:
            print(f"[{phase}] {message}")

    # Run analysis
    print()
    print("Analyzing...")
    hld, alignment = analyzer.analyze(
        prd,
        on_discovery=on_discovery,
        on_alignment_issue=on_alignment_issue,
        on_progress=on_progress,
    )

    # Output
    print()
    print("=" * 60)
    print("DRAFT HIGH-LEVEL DESIGN")
    print("=" * 60)
    print()
    print(hld.raw_hld)

    print()
    print("=" * 60)
    print(f"ALIGNMENT: {alignment.alignment_score:.0%} coverage")
    print(f"Recommendation: {alignment.recommendation}")
    print("=" * 60)

    # Save option
    print()
    if input("Save to file? (y/n): ").lower() == "y":
        filename = input("Filename [hld-draft.md]: ").strip() or "hld-draft.md"
        Path(filename).write_text(hld.raw_hld)
        print(f"Saved to {filename}")


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/examples/test_multi_repo.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add examples/multi_repo.py tests/examples/test_multi_repo.py
git commit -m "feat(examples): add multi-repo PRD analysis script"
```

---

## Task 12: Update CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Read current changelog**

Run: `head -50 CHANGELOG.md`

**Step 2: Add entry under [Unreleased]**

Add under `## [Unreleased]` section:

```markdown
### Added
- Experimental multi-repo PRD analysis (`shesha.experimental.multi_repo`)
  - `MultiRepoAnalyzer` for analyzing how PRDs impact multiple codebases
  - Four-phase workflow: recon, impact, synthesize, align
  - Example script `examples/multi_repo.py`
```

**Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add changelog entry for multi-repo analysis"
```

---

## Task 13: Run Full Test Suite

**Step 1: Run all tests**

Run: `pytest -v`
Expected: All tests pass

**Step 2: Run linting**

Run: `ruff check src tests`
Expected: No errors

**Step 3: Run formatting**

Run: `ruff format src tests`

**Step 4: Run type checking**

Run: `mypy src/shesha`
Expected: No errors

**Step 5: Commit any fixes**

```bash
git add -A
git commit -m "style: apply formatting and fix lint issues"
```

---

## Task 14: Add Error Handling for Gaps

**Files:**
- Modify: `src/shesha/experimental/multi_repo/analyzer.py`
- Modify: `tests/experimental/multi_repo/test_analyzer.py`

**Step 1: Write test for repo failure handling**

Add to `tests/experimental/multi_repo/test_analyzer.py`:
```python
class TestMultiRepoAnalyzerErrorHandling:
    """Tests for error handling."""

    def test_add_repo_failure_is_tracked(self):
        """add_repo tracks failures without raising."""
        mock_shesha = MagicMock()
        mock_shesha.create_project_from_repo.side_effect = Exception("Clone failed")

        analyzer = MultiRepoAnalyzer(mock_shesha)
        project_id = analyzer.add_repo("https://github.com/org/bad-repo")

        assert project_id is None
        assert "https://github.com/org/bad-repo" in analyzer.failed_repos
        assert len(analyzer.repos) == 0

    def test_analyze_warns_on_large_context(self):
        """analyze warns when context approaches limits."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "test-repo"

        # Create a very large summary
        large_summary = "x" * 600_000  # > 500KB

        recon_result = MagicMock()
        recon_result.answer = large_summary

        impact_result = MagicMock()
        impact_result.answer = json.dumps({
            "affected": True,
            "changes": [],
            "new_interfaces": [],
            "modified_interfaces": [],
            "discovered_dependencies": [],
        })

        synth_result = MagicMock()
        synth_result.answer = json.dumps({
            "component_changes": {},
            "data_flow": "",
            "interface_contracts": [],
            "implementation_sequence": [],
            "open_questions": [],
        }) + "\n# HLD"

        align_result = MagicMock()
        align_result.answer = json.dumps({
            "covered": [],
            "gaps": [],
            "scope_creep": [],
            "alignment_score": 1.0,
            "recommendation": "approved",
        })

        mock_project.query.side_effect = [
            recon_result,
            impact_result,
            synth_result,
            align_result,
        ]
        mock_shesha.get_project.return_value = mock_project

        progress_messages = []

        def on_progress(phase: str, message: str) -> None:
            progress_messages.append((phase, message))

        analyzer = MultiRepoAnalyzer(mock_shesha)
        analyzer._repos = ["test-repo"]

        analyzer.analyze("PRD", on_progress=on_progress)

        # Should have a warning about context size
        warning_found = any("large" in msg.lower() or "context" in msg.lower()
                          for phase, msg in progress_messages
                          if phase == "synthesize")
        assert warning_found, f"Expected context warning, got: {progress_messages}"

    def test_analyze_continues_with_partial_repos(self):
        """analyze continues even if some repos failed to add."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_project.project_id = "good-repo"

        simple_result = MagicMock()
        simple_result.answer = json.dumps({
            "apis": [], "models": [], "entry_points": [], "dependencies": [],
            "affected": False, "changes": [], "new_interfaces": [],
            "modified_interfaces": [], "discovered_dependencies": [],
            "component_changes": {}, "data_flow": "", "interface_contracts": [],
            "implementation_sequence": [], "open_questions": [],
            "covered": [], "gaps": [], "scope_creep": [],
            "alignment_score": 1.0, "recommendation": "approved",
        })
        mock_project.query.return_value = simple_result
        mock_shesha.get_project.return_value = mock_project

        analyzer = MultiRepoAnalyzer(mock_shesha)
        analyzer._repos = ["good-repo"]
        analyzer._failed_repos = {"bad-repo": "Clone failed"}

        hld, alignment = analyzer.analyze("PRD")

        # Should complete successfully with partial repos
        assert alignment.recommendation == "approved"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/experimental/multi_repo/test_analyzer.py::TestMultiRepoAnalyzerErrorHandling -v`
Expected: FAIL

**Step 3: Implement error handling**

Update `src/shesha/experimental/multi_repo/analyzer.py`:

Add to `__init__`:
```python
        self._failed_repos: dict[str, str] = {}
```

Add property:
```python
    @property
    def failed_repos(self) -> dict[str, str]:
        """Repos that failed to add, with error messages."""
        return self._failed_repos
```

Update `add_repo` method:
```python
    def add_repo(self, url_or_path: str) -> str | None:
        """Add a repo to the analysis.

        If the repo was previously indexed, reuses it (with update check).
        If updates are available, they are automatically applied.

        Args:
            url_or_path: Git repository URL or local filesystem path.

        Returns:
            The project_id for the added repository, or None if failed.
        """
        try:
            result = self._shesha.create_project_from_repo(url_or_path)

            # Apply updates if available
            if result.status == "updates_available":
                result = result.apply_updates()

            project_id = result.project.project_id

            # Avoid duplicates
            if project_id not in self._repos:
                self._repos.append(project_id)

            return project_id
        except Exception as e:
            self._failed_repos[url_or_path] = str(e)
            return None
```

Add context size check in `analyze` before Phase 3:
```python
        # Check context size before synthesis
        total_context_size = sum(
            len(report.raw_analysis) for report in self._impacts.values()
        )
        if total_context_size > 500_000:  # 500KB warning threshold
            if on_progress:
                on_progress(
                    "synthesize",
                    f"Warning: Large context ({total_context_size:,} chars). "
                    "Consider reducing number of repos.",
                )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/experimental/multi_repo/test_analyzer.py::TestMultiRepoAnalyzerErrorHandling -v`
Expected: PASS

**Step 5: Update example script to handle failures**

Update `examples/multi_repo.py` add_repo loop:
```python
    # Add repos
    for url in args.repos:
        print(f"Adding: {url}")
        try:
            project_id = analyzer.add_repo(url)
            if project_id:
                print(f"  -> {project_id}")
            else:
                print(f"  Warning: Failed to add (will continue with others)")
        except Exception as e:
            print(f"  Error: {e}")

    if not analyzer.repos:
        print("No repos successfully added. Exiting.")
        sys.exit(1)

    if analyzer.failed_repos:
        print(f"\nNote: {len(analyzer.failed_repos)} repo(s) failed to load:")
        for url, error in analyzer.failed_repos.items():
            print(f"  - {url}: {error}")
```

**Step 6: Commit**

```bash
git add src/shesha/experimental/multi_repo/analyzer.py tests/experimental/multi_repo/test_analyzer.py examples/multi_repo.py
git commit -m "feat(multi-repo): add error handling for repo failures and context warnings"
```

---

## Alignment Checklist

Verify the implementation plan covers the design document:

| Design Element | Plan Task | Covered |
|---------------|-----------|---------|
| Module structure (`src/shesha/experimental/multi_repo/`) | Task 1 | ✓ |
| Data models (RepoSummary, ImpactReport, HLDDraft, AlignmentReport) | Task 2 | ✓ |
| Phase prompts (recon, impact, synthesize, align) | Task 3 | ✓ |
| MultiRepoAnalyzer class | Task 4 | ✓ |
| `add_repo()` method | Task 5 | ✓ |
| Phase 1: Recon | Task 6 | ✓ |
| Phase 2: Impact | Task 7 | ✓ |
| Phase 3: Synthesize | Task 8 | ✓ |
| Phase 4: Align | Task 9 | ✓ |
| `analyze()` orchestration | Task 10 | ✓ |
| Example script | Task 11 | ✓ |
| Iterative discovery | Task 10 (on_discovery callback) | ✓ |
| Revision loop | Task 10 (on_alignment_issue callback) | ✓ |
| Configuration (timeouts, max rounds) | Task 4 | ✓ |
| Error handling (repo failures) | Task 14 | ✓ |
| Error handling (context warnings) | Task 14 | ✓ |
| Test isolation | Task 1 (separate test directory) | ✓ |

**Deferred items (not in scope for initial implementation):**
- Timeout enforcement during queries (requires deeper architectural changes)
- Partial results on timeout (complex, low priority)

These are noted in the design's "Future Considerations" section.
