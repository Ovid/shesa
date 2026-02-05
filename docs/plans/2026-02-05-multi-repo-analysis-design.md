# Multi-Repo PRD Analysis Design

**Date:** 2026-02-05
**Status:** Draft
**Author:** Brainstorming session

## Overview

Enable analysis of how a PRD (Product Requirements Document) impacts multiple codebases, generating a draft HLD (High-Level Design) that spans those systems.

### Problem

Currently, `examples/repo.py` allows querying a single repository at a time. When a PRD affects multiple systems, there's no way to analyze cross-system interactions and generate a unified design.

### Solution

A federated query system that:
1. Keeps each repo as its own Shesha project
2. Runs coordinated queries against individual projects
3. Synthesizes results into a comprehensive HLD
4. Validates alignment between PRD and HLD

## Requirements

**Input:**
- PRD text (pasted inline)
- Initial list of repo URLs/paths
- Iterative discovery of additional repos during analysis

**Output:**
- Draft HLD containing:
  - Component-level changes per system
  - Data flow diagrams
  - Interface contracts (APIs, events, schemas)
  - Implementation sequence
  - Open questions

## Module Structure

The feature lives in an isolated experimental module:

```
src/shesha/
├── experimental/
│   ├── __init__.py           # Empty or exports nothing by default
│   └── multi_repo/
│       ├── __init__.py       # Public API: MultiRepoAnalyzer
│       ├── analyzer.py       # Coordinator logic
│       ├── models.py         # Data classes for results
│       └── prompts/          # Specialized prompts for federation
│           ├── recon.md      # Phase 1: Extract repo structure
│           ├── impact.md     # Phase 2: Assess PRD impact
│           ├── synthesize.md # Phase 3: Generate HLD
│           └── align.md      # Phase 4: Verify alignment
```

**Isolation guarantees:**
- No imports from `experimental/` in main Shesha code
- `examples/repo.py` stays unchanged
- New `examples/multi_repo.py` demonstrates the feature
- Disabling: simply don't import from `experimental/`

## Four-Phase Workflow

```
Phase 1: RECON ──────► Phase 2: IMPACT ──────► Phase 3: SYNTHESIZE ──────► Phase 4: ALIGN
(per-repo,             (per-repo,              (single query)              (single query)
 parallel)              parallel)
     │                      │                        │                          │
     ▼                      ▼                        ▼                          ▼
 RepoSummary           ImpactReport               HLDDraft               AlignmentReport
                            │                                                   │
                            ▼                                                   ▼
                    [discovery loop]                                   [revision loop]
                    "Add more repos?"                              "Gaps found. Revise?"
```

### Phase 1: RECON (per-repo, parallel)

Extract structural summaries from each repository.

**Goal:** Understand what each system exposes and consumes.

**Prompt direction:**
- Identify public APIs (REST, GraphQL, gRPC, exported functions)
- Identify data models (DB schemas, DTOs, domain objects)
- Identify entry points (main files, handlers, CLI commands)
- Identify external dependencies (services this code calls)
- Focus on interfaces, skip implementation details

### Phase 2: IMPACT (per-repo, parallel)

Assess how the PRD affects each repository.

**Goal:** Determine specific changes needed and discover other impacted systems.

**Prompt direction:**
- Does this PRD require changes to this codebase?
- What specific changes are needed?
- What other systems might need to be analyzed?

**Iterative discovery:** If an ImpactReport mentions a system not yet analyzed, the coordinator pauses and asks the user whether to add it. If yes, runs Phases 1-2 on the new repo before continuing.

### Phase 3: SYNTHESIZE (single query)

Generate the draft HLD from all impact reports.

**Goal:** Create a comprehensive design document.

**Prompt direction:**
- Component changes per system
- Data flow for the new feature
- Interface contracts (API specs, event schemas)
- Implementation sequence (build/deploy order)
- Open questions needing human decision

### Phase 4: ALIGN (single query)

Validate HLD against PRD requirements.

**Goal:** Ensure complete coverage without scope creep.

**Prompt direction:**
- For each PRD requirement: is it addressed by the HLD?
- For each HLD change: is it justified by the PRD?
- Output: coverage mapping, gaps, scope creep, recommendation

**Revision loop:** If alignment finds issues, user can choose to revise (re-run Phase 3 with feedback) or accept as-is. Max 2 revision rounds.

## Data Models

```python
@dataclass
class RepoSummary:
    """Output from Phase 1 recon query."""
    project_id: str
    apis: list[str]           # Endpoints, exported functions, CLI commands
    models: list[str]         # Data structures, schemas, DB tables
    entry_points: list[str]   # Main files, handlers, routes
    dependencies: list[str]   # External services this repo calls
    raw_summary: str          # Full LLM response for context


@dataclass
class ImpactReport:
    """Output from Phase 2 impact analysis."""
    project_id: str
    affected: bool                    # Does PRD affect this repo?
    changes: list[str]                # Specific changes needed
    new_interfaces: list[str]         # New APIs/events to create
    modified_interfaces: list[str]    # Existing APIs to change
    discovered_dependencies: list[str] # Other repos we should analyze
    raw_analysis: str                 # Full LLM response


@dataclass
class HLDDraft:
    """Output from Phase 3 synthesis."""
    component_changes: dict[str, list[str]]  # repo → changes
    data_flow: str                            # Mermaid diagram or description
    interface_contracts: list[str]            # API specs, event schemas
    implementation_sequence: list[str]        # Ordered steps
    open_questions: list[str]                 # Things needing human input
    raw_hld: str                              # Full markdown HLD


@dataclass
class AlignmentReport:
    """Output from Phase 4 alignment verification."""
    covered: list[dict]           # PRD req → HLD section mapping
    gaps: list[dict]              # Missing requirements
    scope_creep: list[dict]       # Unnecessary HLD items
    alignment_score: float        # 0.0 to 1.0
    recommendation: str           # "approved", "revise", "major_gaps"
    raw_analysis: str             # Full LLM response
```

## Public API

```python
class MultiRepoAnalyzer:
    """Federated PRD analysis across multiple repositories."""

    def __init__(
        self,
        shesha: Shesha,
        max_discovery_rounds: int = 2,
        max_revision_rounds: int = 2,
        phase_timeout_seconds: int = 300,
        total_timeout_seconds: int = 1800,
    ):
        """Uses existing Shesha instance for project management."""

    def add_repo(self, url_or_path: str) -> str:
        """Add a repo to the analysis. Returns project_id.

        If repo was previously indexed, reuses it (with update check).
        """

    def analyze(
        self,
        prd: str,
        on_discovery: Callable[[str], bool] | None = None,
        on_alignment_issue: Callable[[AlignmentReport], str] | None = None,
        on_progress: Callable[[str, str], None] | None = None,
    ) -> tuple[HLDDraft, AlignmentReport]:
        """Run the four-phase analysis.

        Args:
            prd: The PRD text (pasted inline)
            on_discovery: Called when new repo discovered.
                          Receives repo name, returns True to add it.
                          If None, prints prompt and reads stdin.
            on_alignment_issue: Called if alignment finds problems.
                          Receives report, returns "revise" | "accept" | "abort".
                          If None, prints issues and prompts stdin.
            on_progress: Called with (phase, message) updates.

        Returns:
            Tuple of (final HLD, alignment report).
        """

    @property
    def repos(self) -> list[str]:
        """List of project_ids currently in the analysis."""

    @property
    def summaries(self) -> dict[str, RepoSummary]:
        """Recon summaries by project_id (populated after Phase 1)."""

    @property
    def impacts(self) -> dict[str, ImpactReport]:
        """Impact reports by project_id (populated after Phase 2)."""
```

## Example Script

New `examples/multi_repo.py`:

```python
"""Multi-repo PRD analysis using federated queries.

Usage:
    python examples/multi_repo.py repo1_url repo2_url [repo3_url ...]

    Then paste your PRD when prompted (end with Ctrl+D or blank line).
"""

def main():
    # 1. Initialize
    shesha = Shesha(config)
    analyzer = MultiRepoAnalyzer(shesha)

    # 2. Add initial repos from args
    for url in args.repos:
        print(f"Adding: {url}")
        analyzer.add_repo(url)

    # 3. Get PRD from stdin
    print("Paste PRD (Ctrl+D or blank line to finish):")
    prd = read_multiline_input()

    # 4. Run analysis with interactive discovery
    def on_discovery(repo_hint: str) -> bool:
        response = input(f"Discovered dependency: {repo_hint}. Add it? (y/n): ")
        return response.lower() == "y"

    def on_alignment_issue(report: AlignmentReport) -> str:
        print(f"Alignment score: {report.alignment_score:.0%}")
        if report.gaps:
            print(f"Gaps: {len(report.gaps)}")
        if report.scope_creep:
            print(f"Scope creep: {len(report.scope_creep)}")
        return input("Action (revise/accept/abort): ").strip().lower()

    def on_progress(phase: str, message: str):
        print(f"[{phase}] {message}")

    hld, alignment = analyzer.analyze(
        prd,
        on_discovery=on_discovery,
        on_alignment_issue=on_alignment_issue,
        on_progress=on_progress,
    )

    # 5. Output results
    print("\n" + "="*60)
    print("DRAFT HIGH-LEVEL DESIGN")
    print("="*60 + "\n")
    print(hld.raw_hld)

    print("\n" + "="*60)
    print(f"ALIGNMENT: {alignment.alignment_score:.0%} coverage")
    print("="*60 + "\n")

    # 6. Optionally save
    if input("Save to file? (y/n): ").lower() == "y":
        filename = input("Filename [hld-draft.md]: ").strip() or "hld-draft.md"
        Path(filename).write_text(hld.raw_hld)
```

## Error Handling

### Repo failures
- If a repo fails to clone/index, report it and continue with others
- Analysis proceeds with partial data; HLD notes which repos failed

### Empty impact
- If Phase 2 finds a repo isn't affected, mark `affected=False`
- Still include in synthesis (confirms "no changes needed to X")

### Discovery loops
- Track discovered repos to avoid cycles
- Limit discovery depth (default: 2 rounds)
- User can always decline discovered repos

### Context limits
- If synthesis gets too large, summarize ImpactReports first
- Warn user if approaching limits

### Timeouts
- Per-phase timeout (default 5 min per repo query)
- Overall timeout (default 30 min)
- Partial results saved on timeout

## Testing Strategy

### Unit tests (`tests/experimental/multi_repo/`)
- `test_models.py` - Data class serialization
- `test_analyzer.py` - Coordinator logic with mocked queries
  - Phase orchestration (1→2→3→4)
  - Discovery callback invocation
  - Alignment revision loop
  - Partial failure handling

### Integration tests (optional)
- Small fixture repos in `tests/fixtures/repos/`
- End-to-end with real RLM queries
- Marked `@pytest.mark.slow`

### Test isolation
- Tests import only from `shesha.experimental.multi_repo`
- Confirms no coupling to core

## Future Considerations

Not in scope for initial implementation, but noted for future:
- Caching recon summaries across analysis sessions
- Parallel Phase 3 attempts with different synthesis strategies
- Export to external formats (Confluence, Notion, etc.)
- Integration with issue trackers for gap tracking
