# arXiv Explorer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build `examples/arxiv.py`, an interactive CLI for searching arXiv, loading papers into Shesha, and exploring them conversationally with citation checking.

**Architecture:** Supporting modules live in `src/shesha/experimental/arxiv/` (paper cache, topic management, search, download, citation extraction/verification) — cleanly separated from main Shesha code but properly packaged. The main CLI in `examples/arxiv.py` wires them together with a command loop following the barsoom.py/repo.py patterns. Topics map to Shesha projects; a separate paper cache avoids re-downloading.

**Tech Stack:** `arxiv` (PyPI), `bibtexparser` (PyPI), Shesha API, argparse, `script_utils.py`

**Design doc:** `docs/plans/2026-02-11-arxiv-explorer-design.md`

---

## Task 1: Project Setup & Data Models

**Files:**
- Modify: `pyproject.toml` (add optional `[arxiv]` extra)
- Create: `src/shesha/experimental/__init__.py` and `src/shesha/experimental/arxiv/__init__.py`
- Create: `src/shesha/experimental/arxiv/models.py`
- Create: `tests/unit/experimental/__init__.py` and `tests/unit/experimental/arxiv/__init__.py`
- Create: `tests/unit/experimental/arxiv/test_models.py`

### Step 1: Add dependencies to pyproject.toml

Add a new optional extra under `[project.optional-dependencies]`:

```toml
arxiv = [
    "arxiv>=2.0",
    "bibtexparser>=2.0",
]
```

Also add `"arxiv>=2.0"` and `"bibtexparser>=2.0"` to the `dev` extras list so tests can import them.

Run: `pip install -e ".[dev]"` to install.

### Step 2: Write failing tests for data models

Create `tests/unit/experimental/__init__.py` and `tests/unit/experimental/arxiv/__init__.py` (empty).

Create `tests/unit/experimental/arxiv/test_models.py`:

```python
"""Tests for arXiv explorer data models."""

from __future__ import annotations

from datetime import datetime, timezone


class TestPaperMeta:
    """Tests for PaperMeta dataclass."""

    def test_create_paper_meta(self) -> None:
        from shesha.experimental.arxiv.models import PaperMeta

        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Test Paper",
            authors=["Smith, J.", "Doe, A."],
            abstract="A test abstract.",
            published=datetime(2025, 1, 15, tzinfo=timezone.utc),
            updated=datetime(2025, 1, 15, tzinfo=timezone.utc),
            categories=["cs.AI", "cs.CL"],
            primary_category="cs.AI",
            pdf_url="https://arxiv.org/pdf/2501.12345",
            arxiv_url="https://arxiv.org/abs/2501.12345",
        )
        assert meta.arxiv_id == "2501.12345"
        assert meta.title == "Test Paper"
        assert len(meta.authors) == 2
        assert meta.primary_category == "cs.AI"

    def test_paper_meta_optional_fields(self) -> None:
        from shesha.experimental.arxiv.models import PaperMeta

        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Test",
            authors=["Smith"],
            abstract="Abstract",
            published=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated=datetime(2025, 1, 1, tzinfo=timezone.utc),
            categories=["cs.AI"],
            primary_category="cs.AI",
            pdf_url="https://arxiv.org/pdf/2501.12345",
            arxiv_url="https://arxiv.org/abs/2501.12345",
        )
        assert meta.comment is None
        assert meta.journal_ref is None
        assert meta.doi is None
        assert meta.source_type is None

    def test_paper_meta_to_dict_roundtrip(self) -> None:
        """PaperMeta can serialize to dict and back for JSON storage."""
        from shesha.experimental.arxiv.models import PaperMeta

        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Test",
            authors=["Smith"],
            abstract="Abstract",
            published=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated=datetime(2025, 1, 1, tzinfo=timezone.utc),
            categories=["cs.AI"],
            primary_category="cs.AI",
            pdf_url="https://arxiv.org/pdf/2501.12345",
            arxiv_url="https://arxiv.org/abs/2501.12345",
            source_type="latex",
        )
        d = meta.to_dict()
        restored = PaperMeta.from_dict(d)
        assert restored.arxiv_id == meta.arxiv_id
        assert restored.title == meta.title
        assert restored.source_type == "latex"
        assert restored.published == meta.published


class TestExtractedCitation:
    """Tests for ExtractedCitation dataclass."""

    def test_create_citation(self) -> None:
        from shesha.experimental.arxiv.models import ExtractedCitation

        cite = ExtractedCitation(
            key="smith2023",
            title="Some Paper Title",
            authors=["Smith, J."],
            year="2023",
            arxiv_id="2301.04567",
        )
        assert cite.key == "smith2023"
        assert cite.arxiv_id == "2301.04567"

    def test_citation_without_arxiv_id(self) -> None:
        from shesha.experimental.arxiv.models import ExtractedCitation

        cite = ExtractedCitation(
            key="doe2022",
            title="Journal Paper",
            authors=["Doe, A."],
            year="2022",
        )
        assert cite.arxiv_id is None
        assert cite.doi is None


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    def test_verified_citation(self) -> None:
        from shesha.experimental.arxiv.models import VerificationResult, VerificationStatus

        result = VerificationResult(
            citation_key="smith2023",
            status=VerificationStatus.VERIFIED,
        )
        assert result.status == VerificationStatus.VERIFIED
        assert result.message is None

    def test_mismatched_citation(self) -> None:
        from shesha.experimental.arxiv.models import VerificationResult, VerificationStatus

        result = VerificationResult(
            citation_key="smith2023",
            status=VerificationStatus.MISMATCH,
            message='Cites "Quantum Memory" but actual paper is "Fluid Dynamics"',
            actual_title="Fluid Dynamics of Turbulent Flow",
            arxiv_url="https://arxiv.org/abs/2301.04567",
        )
        assert result.status == VerificationStatus.MISMATCH
        assert "Fluid Dynamics" in result.message


class TestTopicInfo:
    """Tests for TopicInfo dataclass."""

    def test_create_topic_info(self) -> None:
        from shesha.experimental.arxiv.models import TopicInfo

        info = TopicInfo(
            name="quantum-error-correction",
            created=datetime(2025, 1, 15, tzinfo=timezone.utc),
            paper_count=3,
            size_bytes=12_400_000,
            project_id="2025-01-15-quantum-error-correction",
        )
        assert info.name == "quantum-error-correction"
        assert info.paper_count == 3

    def test_topic_info_formatted_size(self) -> None:
        from shesha.experimental.arxiv.models import TopicInfo

        info = TopicInfo(
            name="test",
            created=datetime(2025, 1, 1, tzinfo=timezone.utc),
            paper_count=1,
            size_bytes=12_400_000,
            project_id="2025-01-01-test",
        )
        assert info.formatted_size == "12.4 MB"

    def test_topic_info_formatted_size_kb(self) -> None:
        from shesha.experimental.arxiv.models import TopicInfo

        info = TopicInfo(
            name="test",
            created=datetime(2025, 1, 1, tzinfo=timezone.utc),
            paper_count=0,
            size_bytes=500,
            project_id="2025-01-01-test",
        )
        assert info.formatted_size == "0.5 KB"


class TestCheckReport:
    """Tests for CheckReport dataclass."""

    def test_create_check_report(self) -> None:
        from shesha.experimental.arxiv.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        cite = ExtractedCitation(key="a", title="T", authors=["A"], year="2023")
        vr = VerificationResult(citation_key="a", status=VerificationStatus.VERIFIED)
        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[cite],
            verification_results=[vr],
            llm_phrases=[],
        )
        assert report.verified_count == 1
        assert report.mismatch_count == 0
        assert report.unresolved_count == 0


class TestCitationVerifierProtocol:
    """Tests for the CitationVerifier Protocol."""

    def test_arxiv_verifier_satisfies_protocol(self) -> None:
        """ArxivVerifier should satisfy the CitationVerifier Protocol."""
        from shesha.experimental.arxiv.models import CitationVerifier

        # Verify the protocol has the expected method signature
        assert hasattr(CitationVerifier, "verify")
```

Run: `pytest tests/unit/experimental/arxiv/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shesha.experimental.arxiv'`

### Step 3: Implement data models

Create `src/shesha/experimental/__init__.py` and `src/shesha/experimental/arxiv/__init__.py` (both empty).

Create `src/shesha/experimental/arxiv/models.py`:

```python
"""Data models for the arXiv explorer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol


@dataclass
class PaperMeta:
    """Metadata for a cached arXiv paper."""

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    published: datetime
    updated: datetime
    categories: list[str]
    primary_category: str
    pdf_url: str
    arxiv_url: str
    comment: str | None = None
    journal_ref: str | None = None
    doi: str | None = None
    source_type: str | None = None  # "latex", "pdf", or None if not yet downloaded

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "published": self.published.isoformat(),
            "updated": self.updated.isoformat(),
            "categories": self.categories,
            "primary_category": self.primary_category,
            "pdf_url": self.pdf_url,
            "arxiv_url": self.arxiv_url,
            "comment": self.comment,
            "journal_ref": self.journal_ref,
            "doi": self.doi,
            "source_type": self.source_type,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PaperMeta:
        """Deserialize from a dict."""
        return cls(
            arxiv_id=d["arxiv_id"],
            title=d["title"],
            authors=d["authors"],
            abstract=d["abstract"],
            published=datetime.fromisoformat(d["published"]),
            updated=datetime.fromisoformat(d["updated"]),
            categories=d["categories"],
            primary_category=d["primary_category"],
            pdf_url=d["pdf_url"],
            arxiv_url=d["arxiv_url"],
            comment=d.get("comment"),
            journal_ref=d.get("journal_ref"),
            doi=d.get("doi"),
            source_type=d.get("source_type"),
        )


class VerificationStatus(Enum):
    """Status of a citation verification."""

    VERIFIED = "verified"
    MISMATCH = "mismatch"
    NOT_FOUND = "not_found"
    UNRESOLVED = "unresolved"  # Non-arXiv citation, cannot verify yet


@dataclass
class ExtractedCitation:
    """A citation extracted from a paper."""

    key: str
    title: str | None
    authors: list[str]
    year: str | None
    arxiv_id: str | None = None
    doi: str | None = None
    raw_text: str | None = None  # Original text of the citation entry


@dataclass
class VerificationResult:
    """Result of verifying a single citation."""

    citation_key: str
    status: VerificationStatus
    message: str | None = None
    actual_title: str | None = None
    arxiv_url: str | None = None


@dataclass
class TopicInfo:
    """Metadata about a topic for display in /history."""

    name: str
    created: datetime
    paper_count: int
    size_bytes: int
    project_id: str

    @property
    def formatted_size(self) -> str:
        """Human-readable size string."""
        if self.size_bytes < 1024:
            return f"{self.size_bytes} B"
        elif self.size_bytes < 1024 * 1024:
            return f"{self.size_bytes / 1024:.1f} KB"
        elif self.size_bytes < 1024 * 1024 * 1024:
            return f"{self.size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{self.size_bytes / (1024 * 1024 * 1024):.1f} GB"


@dataclass
class CheckReport:
    """Full citation check report for one paper."""

    arxiv_id: str
    title: str
    citations: list[ExtractedCitation]
    verification_results: list[VerificationResult]
    llm_phrases: list[tuple[int, str]]  # (line_number, matched_phrase)

    @property
    def verified_count(self) -> int:
        return sum(
            1 for r in self.verification_results
            if r.status == VerificationStatus.VERIFIED
        )

    @property
    def mismatch_count(self) -> int:
        return sum(
            1 for r in self.verification_results
            if r.status in (VerificationStatus.MISMATCH, VerificationStatus.NOT_FOUND)
        )

    @property
    def unresolved_count(self) -> int:
        return sum(
            1 for r in self.verification_results
            if r.status == VerificationStatus.UNRESOLVED
        )


class CitationVerifier(Protocol):
    """Protocol for citation verifiers.

    Initial implementation: ArxivVerifier (arXiv API only).
    Future: CrossRefVerifier, SemanticScholarVerifier.
    """

    def verify(self, citation: ExtractedCitation) -> VerificationResult: ...
```

### Step 4: Run tests

Run: `pytest tests/unit/experimental/arxiv/test_models.py -v`
Expected: All PASS

### Step 5: Commit

```bash
git add pyproject.toml src/shesha/experimental/ tests/unit/experimental/arxiv/
git commit -m "feat(arxiv): add project setup and data models"
```

---

## Task 2: Paper Cache

**Files:**
- Create: `src/shesha/experimental/arxiv/cache.py`
- Create: `tests/unit/experimental/arxiv/test_cache.py`

The paper cache stores downloaded papers on disk to avoid re-downloading. Each paper gets a directory named by arXiv ID containing `meta.json`, optional `source/` directory (LaTeX files), and optional `paper.pdf`.

### Step 1: Write failing tests

Create `tests/unit/experimental/arxiv/test_cache.py`:

```python
"""Tests for paper cache."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _make_meta() -> "PaperMeta":
    from shesha.experimental.arxiv.models import PaperMeta

    return PaperMeta(
        arxiv_id="2501.12345",
        title="Test Paper",
        authors=["Smith, J."],
        abstract="Abstract",
        published=datetime(2025, 1, 15, tzinfo=timezone.utc),
        updated=datetime(2025, 1, 15, tzinfo=timezone.utc),
        categories=["cs.AI"],
        primary_category="cs.AI",
        pdf_url="https://arxiv.org/pdf/2501.12345",
        arxiv_url="https://arxiv.org/abs/2501.12345",
        source_type="latex",
    )


class TestPaperCache:
    """Tests for PaperCache."""

    def test_empty_cache_has_no_paper(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.cache import PaperCache

        cache = PaperCache(tmp_path / "cache")
        assert not cache.has("2501.12345")

    def test_store_and_retrieve_meta(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.cache import PaperCache

        cache = PaperCache(tmp_path / "cache")
        meta = _make_meta()
        cache.store_meta(meta)
        assert cache.has("2501.12345")
        restored = cache.get_meta("2501.12345")
        assert restored is not None
        assert restored.title == "Test Paper"
        assert restored.source_type == "latex"

    def test_store_and_retrieve_source_files(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.cache import PaperCache

        cache = PaperCache(tmp_path / "cache")
        meta = _make_meta()
        cache.store_meta(meta)
        source_files = {"main.tex": "\\documentclass{article}", "refs.bib": "@article{a}"}
        cache.store_source_files("2501.12345", source_files)
        retrieved = cache.get_source_files("2501.12345")
        assert retrieved is not None
        assert retrieved["main.tex"] == "\\documentclass{article}"
        assert retrieved["refs.bib"] == "@article{a}"

    def test_get_source_files_returns_none_when_missing(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.cache import PaperCache

        cache = PaperCache(tmp_path / "cache")
        meta = _make_meta()
        cache.store_meta(meta)
        assert cache.get_source_files("2501.12345") is None

    def test_store_and_retrieve_pdf(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.cache import PaperCache

        cache = PaperCache(tmp_path / "cache")
        meta = _make_meta()
        cache.store_meta(meta)
        pdf_content = b"%PDF-1.4 fake content"
        cache.store_pdf("2501.12345", pdf_content)
        pdf_path = cache.get_pdf_path("2501.12345")
        assert pdf_path is not None
        assert pdf_path.exists()
        assert pdf_path.read_bytes() == pdf_content

    def test_get_pdf_path_returns_none_when_missing(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.cache import PaperCache

        cache = PaperCache(tmp_path / "cache")
        assert cache.get_pdf_path("2501.12345") is None

    def test_list_papers(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.cache import PaperCache

        cache = PaperCache(tmp_path / "cache")
        assert cache.list_papers() == []
        cache.store_meta(_make_meta())
        papers = cache.list_papers()
        assert papers == ["2501.12345"]

    def test_get_meta_returns_none_for_missing(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.cache import PaperCache

        cache = PaperCache(tmp_path / "cache")
        assert cache.get_meta("nonexistent") is None

    def test_cache_dir_created_on_first_store(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.cache import PaperCache

        cache_dir = tmp_path / "cache"
        cache = PaperCache(cache_dir)
        assert not cache_dir.exists()
        cache.store_meta(_make_meta())
        assert cache_dir.exists()
```

Run: `pytest tests/unit/experimental/arxiv/test_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shesha.experimental.arxiv.cache'`

### Step 2: Implement PaperCache

Create `src/shesha/experimental/arxiv/cache.py`:

```python
"""Local disk cache for downloaded arXiv papers."""

from __future__ import annotations

import json
from pathlib import Path

from shesha.experimental.arxiv.models import PaperMeta


class PaperCache:
    """Cache downloaded papers to avoid re-downloading from arXiv."""

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir

    def has(self, arxiv_id: str) -> bool:
        """Check if a paper is cached."""
        meta_path = self._paper_dir(arxiv_id) / "meta.json"
        return meta_path.exists()

    def store_meta(self, meta: PaperMeta) -> None:
        """Store paper metadata."""
        paper_dir = self._paper_dir(meta.arxiv_id)
        paper_dir.mkdir(parents=True, exist_ok=True)
        meta_path = paper_dir / "meta.json"
        meta_path.write_text(json.dumps(meta.to_dict(), indent=2))

    def get_meta(self, arxiv_id: str) -> PaperMeta | None:
        """Retrieve paper metadata, or None if not cached."""
        meta_path = self._paper_dir(arxiv_id) / "meta.json"
        if not meta_path.exists():
            return None
        data = json.loads(meta_path.read_text())
        return PaperMeta.from_dict(data)

    def store_source_files(self, arxiv_id: str, files: dict[str, str]) -> None:
        """Store extracted LaTeX source files."""
        source_dir = self._paper_dir(arxiv_id) / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            file_path = source_dir / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

    def get_source_files(self, arxiv_id: str) -> dict[str, str] | None:
        """Retrieve source files, or None if not available."""
        source_dir = self._paper_dir(arxiv_id) / "source"
        if not source_dir.exists():
            return None
        files = {}
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                relative = file_path.relative_to(source_dir).as_posix()
                files[relative] = file_path.read_text()
        return files

    def store_pdf(self, arxiv_id: str, content: bytes) -> None:
        """Store a downloaded PDF."""
        paper_dir = self._paper_dir(arxiv_id)
        paper_dir.mkdir(parents=True, exist_ok=True)
        (paper_dir / "paper.pdf").write_bytes(content)

    def get_pdf_path(self, arxiv_id: str) -> Path | None:
        """Get path to cached PDF, or None if not available."""
        pdf_path = self._paper_dir(arxiv_id) / "paper.pdf"
        return pdf_path if pdf_path.exists() else None

    def list_papers(self) -> list[str]:
        """List all cached paper arXiv IDs."""
        if not self._cache_dir.exists():
            return []
        return sorted(
            d.name for d in self._cache_dir.iterdir()
            if d.is_dir() and (d / "meta.json").exists()
        )

    def _paper_dir(self, arxiv_id: str) -> Path:
        """Get the cache directory for a specific paper."""
        return self._cache_dir / arxiv_id
```

### Step 3: Run tests

Run: `pytest tests/unit/experimental/arxiv/test_cache.py -v`
Expected: All PASS

### Step 4: Commit

```bash
git add src/shesha/experimental/arxiv/cache.py tests/unit/experimental/arxiv/test_cache.py
git commit -m "feat(arxiv): add paper cache for local storage"
```

---

## Task 3: Topic Manager

**Files:**
- Create: `src/shesha/experimental/arxiv/topics.py`
- Create: `tests/unit/experimental/arxiv/test_topics.py`

TopicManager wraps Shesha projects to provide topic CRUD. Each topic is a Shesha project with ID `YYYY-MM-DD-<slug>`. Topic metadata (creation date, name) is stored in a `_topic.json` file alongside Shesha's `_meta.json`.

**Key insight:** Since `project.upload()` only accepts file paths, we need to use `storage.store_document()` directly to copy ParsedDocuments from the paper cache into a topic.

### Step 1: Write failing tests

Create `tests/unit/experimental/arxiv/test_topics.py`:

```python
"""Tests for topic manager."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_shesha_and_storage(tmp_path: Path) -> tuple[MagicMock, "FilesystemStorage"]:
    """Create a real FilesystemStorage with a mock Shesha that delegates to it."""
    from shesha.storage.filesystem import FilesystemStorage

    storage_path = tmp_path / "shesha_data"
    storage = FilesystemStorage(storage_path)

    shesha = MagicMock()
    shesha._storage = storage
    shesha.list_projects.side_effect = lambda: storage.list_projects()
    shesha.delete_project.side_effect = (
        lambda pid, cleanup_repo=True: storage.delete_project(pid)
    )
    return shesha, storage


class TestTopicManager:
    """Tests for TopicManager."""

    def test_create_topic(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        project_id = mgr.create("quantum-error-correction")
        assert "quantum-error-correction" in project_id
        assert storage.project_exists(project_id)

    def test_create_topic_includes_date(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        project_id = mgr.create("test-topic")
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert project_id.startswith(today)

    def test_list_topics_empty(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        assert mgr.list_topics() == []

    def test_list_topics_returns_topic_info(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        mgr.create("topic-a")
        topics = mgr.list_topics()
        assert len(topics) == 1
        assert topics[0].name == "topic-a"
        assert topics[0].paper_count == 0
        assert topics[0].size_bytes >= 0

    def test_delete_topic(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        project_id = mgr.create("to-delete")
        mgr.delete("to-delete")
        assert not storage.project_exists(project_id)

    def test_resolve_topic_name(self, tmp_path: Path) -> None:
        """Resolve a slug name to a full project ID."""
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        project_id = mgr.create("my-topic")
        resolved = mgr.resolve("my-topic")
        assert resolved == project_id

    def test_resolve_returns_none_for_unknown(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        assert mgr.resolve("nonexistent") is None

    def test_get_topic_info_with_size(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager
        from shesha.models import ParsedDocument

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        project_id = mgr.create("sized-topic")
        # Store a document to add some size
        doc = ParsedDocument(
            name="test.txt",
            content="Hello world " * 1000,
            format="text",
            metadata={},
            char_count=12000,
        )
        storage.store_document(project_id, doc)
        info = mgr.get_topic_info("sized-topic")
        assert info is not None
        assert info.paper_count == 1
        assert info.size_bytes > 0

    def test_get_topic_info_by_project_id(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        project_id = mgr.create("by-id-test")
        info = mgr.get_topic_info_by_project_id(project_id)
        assert info is not None
        assert info.name == "by-id-test"

    def test_get_topic_info_by_project_id_returns_none(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.topics import TopicManager

        shesha, storage = _make_shesha_and_storage(tmp_path)
        mgr = TopicManager(shesha, storage, tmp_path / "shesha_data")
        assert mgr.get_topic_info_by_project_id("nonexistent") is None

    def test_slugify(self, tmp_path: Path) -> None:
        """Topic names are slugified (lowercase, hyphens, no special chars)."""
        from shesha.experimental.arxiv.topics import slugify

        assert slugify("Quantum Error Correction") == "quantum-error-correction"
        assert slugify("cs.AI + language models!") == "cs-ai-language-models"
        assert slugify("  spaces  everywhere  ") == "spaces-everywhere"
```

Run: `pytest tests/unit/experimental/arxiv/test_topics.py -v`
Expected: FAIL

### Step 2: Implement TopicManager

Create `src/shesha/experimental/arxiv/topics.py`:

```python
"""Topic management backed by Shesha projects."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from shesha.experimental.arxiv.models import TopicInfo

if TYPE_CHECKING:
    from shesha import Shesha
    from shesha.storage.filesystem import FilesystemStorage


def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


class TopicManager:
    """Manage topics backed by Shesha projects."""

    TOPIC_META_FILE = "_topic.json"

    def __init__(
        self,
        shesha: Shesha,
        storage: FilesystemStorage,
        data_dir: Path,
    ) -> None:
        self._shesha = shesha
        self._storage = storage
        self._data_dir = data_dir

    def create(self, name: str) -> str:
        """Create a new topic. Returns the project ID."""
        slug = slugify(name)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        project_id = f"{today}-{slug}"
        self._storage.create_project(project_id)
        # Write topic metadata
        topic_meta = {
            "name": slug,
            "created": datetime.now(tz=timezone.utc).isoformat(),
        }
        meta_path = self._project_path(project_id) / self.TOPIC_META_FILE
        meta_path.write_text(json.dumps(topic_meta, indent=2))
        return project_id

    def list_topics(self) -> list[TopicInfo]:
        """List all topics with metadata."""
        topics = []
        for project_id in self._storage.list_projects():
            info = self._read_topic_info(project_id)
            if info is not None:
                topics.append(info)
        return sorted(topics, key=lambda t: t.created)

    def delete(self, name: str) -> None:
        """Delete a topic by slug name."""
        project_id = self.resolve(name)
        if project_id is None:
            msg = f"Topic not found: {name}"
            raise ValueError(msg)
        self._storage.delete_project(project_id)

    def resolve(self, name: str) -> str | None:
        """Resolve a topic slug to its full project ID."""
        slug = slugify(name)
        for project_id in self._storage.list_projects():
            meta = self._read_topic_meta(project_id)
            if meta is not None and meta.get("name") == slug:
                return project_id
        return None

    def get_topic_info(self, name: str) -> TopicInfo | None:
        """Get info for a specific topic."""
        project_id = self.resolve(name)
        if project_id is None:
            return None
        return self._read_topic_info(project_id)

    def get_topic_info_by_project_id(self, project_id: str) -> TopicInfo | None:
        """Get topic info directly from a project ID."""
        if not self._storage.project_exists(project_id):
            return None
        return self._read_topic_info(project_id)

    def _read_topic_info(self, project_id: str) -> TopicInfo | None:
        """Read topic info from a project directory."""
        meta = self._read_topic_meta(project_id)
        if meta is None:
            return None
        docs = self._storage.list_documents(project_id)
        size = self._compute_size(project_id)
        created = datetime.fromisoformat(meta["created"])
        return TopicInfo(
            name=meta["name"],
            created=created,
            paper_count=len(docs),
            size_bytes=size,
            project_id=project_id,
        )

    def _read_topic_meta(self, project_id: str) -> dict | None:
        """Read the _topic.json for a project, or None if not a topic."""
        meta_path = self._project_path(project_id) / self.TOPIC_META_FILE
        if not meta_path.exists():
            return None
        return json.loads(meta_path.read_text())

    def _compute_size(self, project_id: str) -> int:
        """Compute total size on disk for a project."""
        project_path = self._project_path(project_id)
        total = 0
        for dirpath, _dirnames, filenames in os.walk(project_path):
            for filename in filenames:
                total += os.path.getsize(os.path.join(dirpath, filename))
        return total

    def _project_path(self, project_id: str) -> Path:
        """Get the filesystem path for a project."""
        return self._data_dir / "projects" / project_id
```

### Step 3: Run tests

Run: `pytest tests/unit/experimental/arxiv/test_topics.py -v`
Expected: All PASS

### Step 4: Commit

```bash
git add src/shesha/experimental/arxiv/topics.py tests/unit/experimental/arxiv/test_topics.py
git commit -m "feat(arxiv): add topic manager backed by Shesha projects"
```

---

## Task 4: arXiv Search Wrapper

**Files:**
- Create: `src/shesha/experimental/arxiv/search.py`
- Create: `tests/unit/experimental/arxiv/test_search.py`

Thin wrapper around the `arxiv` Python package. Manages pagination state, converts `arxiv.Result` objects to our `PaperMeta` model, and formats results for display.

### Step 1: Write failing tests

Create `tests/unit/experimental/arxiv/test_search.py`. Mock the `arxiv` package to avoid hitting the real API:

```python
"""Tests for arXiv search wrapper."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


def _mock_arxiv_result(
    arxiv_id: str = "2501.12345",
    title: str = "Test Paper",
    authors: list[str] | None = None,
) -> MagicMock:
    """Create a mock arxiv.Result object."""
    result = MagicMock()
    result.entry_id = f"http://arxiv.org/abs/{arxiv_id}"
    result.title = title
    result.summary = "An abstract."
    result.published = datetime(2025, 1, 15, tzinfo=timezone.utc)
    result.updated = datetime(2025, 1, 15, tzinfo=timezone.utc)
    result.categories = ["cs.AI"]
    result.primary_category = "cs.AI"
    result.pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    result.comment = "10 pages"
    result.journal_ref = None
    result.doi = None
    # Authors are objects with .name attribute
    author_names = authors or ["Smith, J.", "Doe, A."]
    result.authors = [MagicMock(name=n) for n in author_names]
    # Fix: MagicMock(name=...) sets the mock's name, not .name attribute
    for author, name in zip(result.authors, author_names):
        author.name = name
    return result


class TestArxivSearcher:
    """Tests for ArxivSearcher."""

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_returns_paper_metas(self, mock_arxiv: MagicMock) -> None:
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([_mock_arxiv_result()])

        searcher = ArxivSearcher()
        results = searcher.search("quantum computing")
        assert len(results) == 1
        assert results[0].arxiv_id == "2501.12345"
        assert results[0].title == "Test Paper"

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_with_category(self, mock_arxiv: MagicMock) -> None:
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([])

        searcher = ArxivSearcher()
        searcher.search("language models", category="cs.AI")
        # Verify the query included the category
        search_call = mock_arxiv.Search.call_args
        assert "cat:cs.AI" in search_call.kwargs.get("query", search_call.args[0] if search_call.args else "")

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_by_author(self, mock_arxiv: MagicMock) -> None:
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([])

        searcher = ArxivSearcher()
        searcher.search("", author="del maestro")
        search_call = mock_arxiv.Search.call_args
        query = search_call.kwargs.get("query", search_call.args[0] if search_call.args else "")
        assert "au:" in query

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_with_start_offset(self, mock_arxiv: MagicMock) -> None:
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([_mock_arxiv_result()])

        searcher = ArxivSearcher()
        searcher.search("quantum", start=10)
        search_call = mock_arxiv.Search.call_args
        assert search_call.kwargs.get("start", search_call.args[1] if len(search_call.args) > 1 else 0) == 10

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_search_recent_days(self, mock_arxiv: MagicMock) -> None:
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([])

        searcher = ArxivSearcher()
        searcher.search("quantum", recent_days=7)
        search_call = mock_arxiv.Search.call_args
        query = search_call.kwargs.get("query", search_call.args[0] if search_call.args else "")
        assert "submittedDate:" in query

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_get_by_id(self, mock_arxiv: MagicMock) -> None:
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([_mock_arxiv_result()])

        searcher = ArxivSearcher()
        meta = searcher.get_by_id("2501.12345")
        assert meta is not None
        assert meta.arxiv_id == "2501.12345"

    @patch("shesha.experimental.arxiv.search.arxiv")
    def test_get_by_id_not_found(self, mock_arxiv: MagicMock) -> None:
        from shesha.experimental.arxiv.search import ArxivSearcher

        mock_client = MagicMock()
        mock_arxiv.Client.return_value = mock_client
        mock_client.results.return_value = iter([])

        searcher = ArxivSearcher()
        meta = searcher.get_by_id("0000.00000")
        assert meta is None

    def test_format_result(self) -> None:
        from shesha.experimental.arxiv.models import PaperMeta
        from shesha.experimental.arxiv.search import format_result

        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Topological Quantum Error Correction with Low Overhead",
            authors=["Smith, J.", "Jones, K.", "Lee, M."],
            abstract="Abstract",
            published=datetime(2025, 1, 15, tzinfo=timezone.utc),
            updated=datetime(2025, 1, 15, tzinfo=timezone.utc),
            categories=["cs.QI"],
            primary_category="cs.QI",
            pdf_url="https://arxiv.org/pdf/2501.12345",
            arxiv_url="https://arxiv.org/abs/2501.12345",
            comment="12 pages",
        )
        output = format_result(meta, index=1)
        assert "[2501.12345]" in output
        assert "Topological Quantum Error Correction" in output
        assert "Smith, J." in output
        assert "cs.QI" in output
        assert "https://arxiv.org/abs/2501.12345" in output

    def test_extract_arxiv_id_from_entry_id(self) -> None:
        from shesha.experimental.arxiv.search import extract_arxiv_id

        assert extract_arxiv_id("http://arxiv.org/abs/2501.12345v1") == "2501.12345v1"
        assert extract_arxiv_id("http://arxiv.org/abs/2501.12345") == "2501.12345"
```

Run: `pytest tests/unit/experimental/arxiv/test_search.py -v`
Expected: FAIL

### Step 2: Implement ArxivSearcher

Create `src/shesha/experimental/arxiv/search.py`. The `arxiv` package import should be guarded so tests can mock it:

```python
"""arXiv search wrapper with pagination."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import arxiv

from shesha.experimental.arxiv.models import PaperMeta


def extract_arxiv_id(entry_id: str) -> str:
    """Extract the arXiv ID from an entry_id URL."""
    # entry_id looks like "http://arxiv.org/abs/2501.12345v1"
    match = re.search(r"/abs/(.+)$", entry_id)
    if match:
        return match.group(1)
    return entry_id


def _result_to_meta(result: arxiv.Result) -> PaperMeta:
    """Convert an arxiv.Result to our PaperMeta model."""
    arxiv_id = extract_arxiv_id(result.entry_id)
    return PaperMeta(
        arxiv_id=arxiv_id,
        title=result.title,
        authors=[a.name for a in result.authors],
        abstract=result.summary,
        published=result.published,
        updated=result.updated,
        categories=result.categories,
        primary_category=result.primary_category,
        pdf_url=result.pdf_url or f"https://arxiv.org/pdf/{arxiv_id}",
        arxiv_url=f"https://arxiv.org/abs/{arxiv_id}",
        comment=result.comment,
        journal_ref=result.journal_ref,
        doi=result.doi,
    )


def format_result(meta: PaperMeta, index: int) -> str:
    """Format a single search result for display."""
    authors = ", ".join(meta.authors[:3])
    if len(meta.authors) > 3:
        authors += f" +{len(meta.authors) - 3} more"
    date_str = meta.published.strftime("%Y-%m-%d")
    comment_str = f" | {meta.comment}" if meta.comment else ""
    lines = [
        f"  {index}. [{meta.arxiv_id}] \"{meta.title}\"",
        f"     {authors} | {meta.primary_category} | {date_str}{comment_str}",
        f"     {meta.arxiv_url}",
    ]
    return "\n".join(lines)


class ArxivSearcher:
    """Search arXiv with rate-limited pagination."""

    def __init__(self, page_size: int = 10) -> None:
        self._client = arxiv.Client(
            page_size=page_size,
            delay_seconds=3.0,
            num_retries=3,
        )
        self._page_size = page_size

    def search(
        self,
        query: str,
        *,
        author: str | None = None,
        category: str | None = None,
        recent_days: int | None = None,
        max_results: int = 10,
        start: int = 0,
    ) -> list[PaperMeta]:
        """Search arXiv and return results.

        Args:
            query: Keyword search string.
            author: Filter by author name.
            category: Filter by arXiv category (e.g., "cs.AI").
            recent_days: Only return papers from the last N days.
            max_results: Maximum results to return.
            start: Offset for pagination (0-based).
        """
        parts = []
        if query:
            parts.append(f"all:{query}")
        if author:
            parts.append(f"au:{author}")
        if category:
            parts.append(f"cat:{category}")
        if recent_days is not None:
            now = datetime.now(tz=timezone.utc)
            start_date = now - timedelta(days=recent_days)
            # arXiv date format: YYYYMMDDTTTT
            date_from = start_date.strftime("%Y%m%d0000")
            date_to = now.strftime("%Y%m%d2359")
            parts.append(f"submittedDate:[{date_from}+TO+{date_to}]")
        full_query = " AND ".join(parts) if parts else "all:*"

        search = arxiv.Search(
            query=full_query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
            start=start,
        )
        results = list(self._client.results(search))
        return [_result_to_meta(r) for r in results]

    def get_by_id(self, arxiv_id: str) -> PaperMeta | None:
        """Fetch metadata for a specific arXiv ID."""
        search = arxiv.Search(id_list=[arxiv_id])
        results = list(self._client.results(search))
        if not results:
            return None
        return _result_to_meta(results[0])
```

### Step 3: Run tests

Run: `pytest tests/unit/experimental/arxiv/test_search.py -v`
Expected: All PASS

### Step 4: Commit

```bash
git add src/shesha/experimental/arxiv/search.py tests/unit/experimental/arxiv/test_search.py
git commit -m "feat(arxiv): add arXiv search wrapper with pagination"
```

---

## Task 5: Paper Downloader

**Files:**
- Create: `src/shesha/experimental/arxiv/download.py`
- Create: `tests/unit/experimental/arxiv/test_download.py`

Downloads papers from arXiv (source first, PDF fallback), extracts LaTeX source from tarballs, and converts to Shesha `ParsedDocument` format.

### Step 1: Write failing tests

Create `tests/unit/experimental/arxiv/test_download.py`:

```python
"""Tests for paper downloader."""

from __future__ import annotations

import gzip
import io
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_meta() -> "PaperMeta":
    from shesha.experimental.arxiv.models import PaperMeta

    return PaperMeta(
        arxiv_id="2501.12345",
        title="Test Paper",
        authors=["Smith, J."],
        abstract="Abstract",
        published=datetime(2025, 1, 15, tzinfo=timezone.utc),
        updated=datetime(2025, 1, 15, tzinfo=timezone.utc),
        categories=["cs.AI"],
        primary_category="cs.AI",
        pdf_url="https://arxiv.org/pdf/2501.12345",
        arxiv_url="https://arxiv.org/abs/2501.12345",
    )


def _make_tarball(files: dict[str, str]) -> bytes:
    """Create an in-memory tar.gz containing the given files."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in files.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _make_gzipped_tex(content: str) -> bytes:
    """Create gzipped single-file source (arXiv format for single .tex)."""
    return gzip.compress(content.encode("utf-8"))


class TestExtractTarball:
    """Tests for tarball extraction."""

    def test_extract_tex_and_bib(self) -> None:
        from shesha.experimental.arxiv.download import extract_source_files

        tarball = _make_tarball({
            "main.tex": "\\documentclass{article}\\begin{document}Hello\\end{document}",
            "refs.bib": "@article{smith2023, title={Test}}",
        })
        files = extract_source_files(tarball)
        assert "main.tex" in files
        assert "refs.bib" in files
        assert "\\documentclass" in files["main.tex"]

    def test_extract_filters_non_text_files(self) -> None:
        from shesha.experimental.arxiv.download import extract_source_files

        tarball = _make_tarball({
            "main.tex": "\\documentclass{article}",
            "figure.png": "fake png data",
        })
        files = extract_source_files(tarball)
        assert "main.tex" in files
        # Binary files should be excluded
        assert "figure.png" not in files

    def test_extract_bbl_file(self) -> None:
        from shesha.experimental.arxiv.download import extract_source_files

        tarball = _make_tarball({
            "main.tex": "\\documentclass{article}",
            "main.bbl": "\\begin{thebibliography}{1}\\bibitem{a} Author\\end{thebibliography}",
        })
        files = extract_source_files(tarball)
        assert "main.bbl" in files

    def test_extract_single_gzipped_tex(self) -> None:
        """arXiv serves single-file submissions as gzipped .tex, not tarball."""
        from shesha.experimental.arxiv.download import extract_source_files

        content = "\\documentclass{article}\\begin{document}Hi\\end{document}"
        gz_data = _make_gzipped_tex(content)
        files = extract_source_files(gz_data)
        assert len(files) == 1
        assert any("documentclass" in v for v in files.values())


class TestToParsedDocument:
    """Tests for converting cached papers to ParsedDocument."""

    def test_latex_source_to_document(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.cache import PaperCache
        from shesha.experimental.arxiv.download import to_parsed_document

        cache = PaperCache(tmp_path / "cache")
        meta = _make_meta()
        meta.source_type = "latex"
        cache.store_meta(meta)
        cache.store_source_files("2501.12345", {
            "main.tex": "\\documentclass{article}\\begin{document}Content here.\\end{document}",
            "refs.bib": "@article{s, title={T}}",
        })
        doc = to_parsed_document("2501.12345", cache)
        assert doc.name == "2501.12345"
        assert "Content here" in doc.content
        assert doc.metadata.get("arxiv_url") == "https://arxiv.org/abs/2501.12345"

    def test_pdf_fallback_to_document(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.cache import PaperCache
        from shesha.experimental.arxiv.download import to_parsed_document

        cache = PaperCache(tmp_path / "cache")
        meta = _make_meta()
        meta.source_type = "pdf"
        cache.store_meta(meta)
        # We can't easily test real PDF extraction, so just verify it handles
        # the case where a PDF path exists
        cache.store_pdf("2501.12345", b"%PDF-1.4 fake")
        # This will fail to extract text from fake PDF — that's OK,
        # the function should handle it gracefully
        doc = to_parsed_document("2501.12345", cache)
        assert doc.name == "2501.12345"
        assert doc.metadata.get("arxiv_url") == "https://arxiv.org/abs/2501.12345"


class TestDownloadPaper:
    """Tests for the full download flow."""

    @patch("shesha.experimental.arxiv.download.urllib.request.urlopen")
    def test_download_tries_source_first(
        self, mock_urlopen: MagicMock, tmp_path: Path
    ) -> None:
        from shesha.experimental.arxiv.cache import PaperCache
        from shesha.experimental.arxiv.download import download_paper
        from shesha.experimental.arxiv.search import ArxivSearcher

        cache = PaperCache(tmp_path / "cache")
        meta = _make_meta()

        # Mock source download returning a tarball
        tarball = _make_tarball({"main.tex": "\\documentclass{article}"})
        mock_response = MagicMock()
        mock_response.read.return_value = tarball
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result_meta = download_paper(meta, cache)
        assert result_meta.source_type == "latex"
        assert cache.has("2501.12345")
        assert cache.get_source_files("2501.12345") is not None

    @patch("shesha.experimental.arxiv.download.urllib.request.urlopen")
    def test_download_falls_back_to_pdf(
        self, mock_urlopen: MagicMock, tmp_path: Path
    ) -> None:
        from urllib.error import HTTPError

        from shesha.experimental.arxiv.cache import PaperCache
        from shesha.experimental.arxiv.download import download_paper

        cache = PaperCache(tmp_path / "cache")
        meta = _make_meta()

        # First call (source) raises 404, second call (PDF) succeeds
        pdf_response = MagicMock()
        pdf_response.read.return_value = b"%PDF-1.4 fake content"
        pdf_response.__enter__ = lambda s: s
        pdf_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.side_effect = [
            HTTPError(url="", code=404, msg="Not Found", hdrs=None, fp=None),
            pdf_response,
        ]

        result_meta = download_paper(meta, cache)
        assert result_meta.source_type == "pdf"
        assert cache.get_pdf_path("2501.12345") is not None

    def test_skip_download_if_cached(self, tmp_path: Path) -> None:
        from shesha.experimental.arxiv.cache import PaperCache
        from shesha.experimental.arxiv.download import download_paper

        cache = PaperCache(tmp_path / "cache")
        meta = _make_meta()
        meta.source_type = "latex"
        cache.store_meta(meta)

        # Should return immediately without downloading
        result = download_paper(meta, cache)
        assert result.source_type == "latex"
```

Run: `pytest tests/unit/experimental/arxiv/test_download.py -v`
Expected: FAIL

### Step 2: Implement downloader

Create `src/shesha/experimental/arxiv/download.py`:

```python
"""Download arXiv papers (source first, PDF fallback)."""

from __future__ import annotations

import gzip
import io
import tarfile
import time
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

from shesha.models import ParsedDocument

from shesha.experimental.arxiv.cache import PaperCache
from shesha.experimental.arxiv.models import PaperMeta

# File extensions to extract from LaTeX source archives
TEXT_EXTENSIONS = {".tex", ".bib", ".bbl", ".bst", ".sty", ".cls", ".txt", ".md"}

# Delay between downloads to respect arXiv rate limits
DOWNLOAD_DELAY_SECONDS = 3.0


def extract_source_files(data: bytes) -> dict[str, str]:
    """Extract text files from a tar.gz or gzipped .tex file."""
    files: dict[str, str] = {}
    try:
        # Try as tarball first
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                suffix = Path(member.name).suffix.lower()
                if suffix not in TEXT_EXTENSIONS:
                    continue
                f = tar.extractfile(member)
                if f is None:
                    continue
                try:
                    content = f.read().decode("utf-8", errors="replace")
                    files[member.name] = content
                finally:
                    f.close()
    except tarfile.TarError:
        # Not a tarball — try as gzipped single file
        try:
            content = gzip.decompress(data).decode("utf-8", errors="replace")
            files["main.tex"] = content
        except (gzip.BadGzipFile, UnicodeDecodeError):
            pass  # Neither tarball nor gzipped tex — no source available
    return files


def to_parsed_document(arxiv_id: str, cache: PaperCache) -> ParsedDocument:
    """Convert a cached paper to a Shesha ParsedDocument."""
    meta = cache.get_meta(arxiv_id)
    if meta is None:
        msg = f"Paper not in cache: {arxiv_id}"
        raise ValueError(msg)

    content = ""
    fmt = "text"

    source_files = cache.get_source_files(arxiv_id)
    if source_files is not None:
        # Concatenate all source files with headers
        parts = []
        for filename, file_content in sorted(source_files.items()):
            parts.append(f"--- {filename} ---\n{file_content}")
        content = "\n\n".join(parts)
        fmt = "latex"
    else:
        # Try PDF text extraction
        pdf_path = cache.get_pdf_path(arxiv_id)
        if pdf_path is not None:
            try:
                import pdfplumber

                with pdfplumber.open(pdf_path) as pdf:
                    pages = [page.extract_text() or "" for page in pdf.pages]
                    content = "\n\n".join(pages)
                    fmt = "pdf"
            except Exception:
                content = f"[PDF text extraction failed for {arxiv_id}]"
                fmt = "pdf"

    doc_metadata: dict[str, str | int | float | bool] = {
        "arxiv_id": meta.arxiv_id,
        "arxiv_url": meta.arxiv_url,
        "title": meta.title,
        "authors": ", ".join(meta.authors),
        "primary_category": meta.primary_category,
    }

    return ParsedDocument(
        name=arxiv_id,
        content=content,
        format=fmt,
        metadata=doc_metadata,
        char_count=len(content),
    )


def download_paper(meta: PaperMeta, cache: PaperCache) -> PaperMeta:
    """Download a paper to the cache. Returns updated meta with source_type."""
    if cache.has(meta.arxiv_id):
        existing = cache.get_meta(meta.arxiv_id)
        if existing is not None:
            return existing
        return meta

    # Try source first
    source_url = f"https://export.arxiv.org/e-print/{meta.arxiv_id}"
    try:
        with urllib.request.urlopen(source_url) as response:
            data = response.read()
        files = extract_source_files(data)
        if files:
            meta.source_type = "latex"
            cache.store_meta(meta)
            cache.store_source_files(meta.arxiv_id, files)
            return meta
    except HTTPError:
        pass  # Source not available, fall back to PDF

    time.sleep(DOWNLOAD_DELAY_SECONDS)

    # Fall back to PDF
    pdf_url = f"https://export.arxiv.org/pdf/{meta.arxiv_id}"
    try:
        with urllib.request.urlopen(pdf_url) as response:
            pdf_data = response.read()
        meta.source_type = "pdf"
        cache.store_meta(meta)
        cache.store_pdf(meta.arxiv_id, pdf_data)
    except HTTPError:
        # Neither available — store meta only
        meta.source_type = None
        cache.store_meta(meta)

    return meta
```

### Step 3: Run tests

Run: `pytest tests/unit/experimental/arxiv/test_download.py -v`
Expected: All PASS

### Step 4: Commit

```bash
git add src/shesha/experimental/arxiv/download.py tests/unit/experimental/arxiv/test_download.py
git commit -m "feat(arxiv): add paper downloader with source-first strategy"
```

---

## Task 6: Citation Extraction

**Files:**
- Create: `src/shesha/experimental/arxiv/citations.py`
- Create: `tests/unit/experimental/arxiv/test_citations.py`

Extract citations from .bib files (using `bibtexparser`), .bbl files (regex), and detect LLM-tell phrases.

### Step 1: Write failing tests

Create `tests/unit/experimental/arxiv/test_citations.py`:

```python
"""Tests for citation extraction and LLM-tell phrase detection."""

from __future__ import annotations

class TestExtractFromBib:
    """Tests for .bib file citation extraction."""

    def test_extract_single_entry(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bib

        bib = """
@article{smith2023quantum,
    author = {Smith, John and Doe, Alice},
    title = {Quantum Error Correction Survey},
    journal = {Physical Review Letters},
    year = {2023},
    eprint = {2301.04567},
}
"""
        cites = extract_citations_from_bib(bib)
        assert len(cites) == 1
        assert cites[0].key == "smith2023quantum"
        assert cites[0].title == "Quantum Error Correction Survey"
        assert cites[0].year == "2023"
        assert cites[0].arxiv_id == "2301.04567"

    def test_extract_multiple_entries(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bib

        bib = """
@article{a, author={A}, title={Paper A}, year={2023}}
@inproceedings{b, author={B}, title={Paper B}, year={2024}}
"""
        cites = extract_citations_from_bib(bib)
        assert len(cites) == 2

    def test_extract_arxiv_id_from_eprint(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bib

        bib = """
@article{x, author={X}, title={T}, year={2023}, eprint={2501.12345}, archivePrefix={arXiv}}
"""
        cites = extract_citations_from_bib(bib)
        assert cites[0].arxiv_id == "2501.12345"

    def test_extract_doi(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bib

        bib = """
@article{x, author={X}, title={T}, year={2023}, doi={10.1234/example}}
"""
        cites = extract_citations_from_bib(bib)
        assert cites[0].doi == "10.1234/example"

    def test_empty_bib(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bib

        assert extract_citations_from_bib("") == []

    def test_malformed_bib_does_not_crash(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bib

        # Malformed BibTeX should return empty, not crash
        result = extract_citations_from_bib("this is not valid bibtex {{{")
        assert isinstance(result, list)


class TestExtractFromBbl:
    """Tests for .bbl file citation extraction."""

    def test_extract_bibitem(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bbl

        bbl = r"""
\begin{thebibliography}{10}

\bibitem{smith2023}
J.~Smith and A.~Doe.
\newblock Quantum error correction survey.
\newblock {\em Physical Review Letters}, 2023.

\bibitem{jones2024}
K.~Jones.
\newblock Surface codes revisited.
\newblock arXiv:2401.67890, 2024.

\end{thebibliography}
"""
        cites = extract_citations_from_bbl(bbl)
        assert len(cites) == 2
        assert cites[0].key == "smith2023"
        assert cites[1].key == "jones2024"

    def test_extract_arxiv_id_from_bbl_text(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bbl

        bbl = r"""
\begin{thebibliography}{1}
\bibitem{x}
Author. Title. arXiv:2301.04567, 2023.
\end{thebibliography}
"""
        cites = extract_citations_from_bbl(bbl)
        assert len(cites) == 1
        assert cites[0].arxiv_id == "2301.04567"

    def test_empty_bbl(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_bbl

        assert extract_citations_from_bbl("") == []


class TestDetectLLMPhrases:
    """Tests for LLM-tell phrase detection."""

    def test_detect_knowledge_update_phrase(self) -> None:
        from shesha.experimental.arxiv.citations import detect_llm_phrases

        text = "Line one.\nAs of my last knowledge update, this is true.\nLine three."
        results = detect_llm_phrases(text)
        assert len(results) == 1
        line_num, phrase = results[0]
        assert line_num == 2
        assert "knowledge update" in phrase.lower()

    def test_detect_important_to_note(self) -> None:
        from shesha.experimental.arxiv.citations import detect_llm_phrases

        text = "It is important to note that the results suggest otherwise."
        results = detect_llm_phrases(text)
        assert len(results) == 1

    def test_no_false_positives_on_clean_text(self) -> None:
        from shesha.experimental.arxiv.citations import detect_llm_phrases

        text = "We present a novel method for quantum error correction.\nOur results show improvement."
        results = detect_llm_phrases(text)
        assert results == []

    def test_detect_multiple_phrases(self) -> None:
        from shesha.experimental.arxiv.citations import detect_llm_phrases

        text = (
            "As of my last knowledge update, X.\n"
            "Normal line.\n"
            "I cannot provide specific details.\n"
        )
        results = detect_llm_phrases(text)
        assert len(results) == 2

    def test_case_insensitive(self) -> None:
        from shesha.experimental.arxiv.citations import detect_llm_phrases

        text = "AS OF MY LAST KNOWLEDGE UPDATE, things changed."
        results = detect_llm_phrases(text)
        assert len(results) == 1


class TestExtractFromText:
    """Tests for plain text (PDF-extracted) citation extraction."""

    def test_extract_arxiv_ids_from_text(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_text

        text = (
            "We build on prior work [1] and extend the results of arXiv:2301.04567.\n"
            "See also 2502.67890v2 for related approaches.\n"
        )
        cites = extract_citations_from_text(text)
        assert len(cites) == 2
        ids = {c.arxiv_id for c in cites}
        assert "2301.04567" in ids
        assert "2502.67890v2" in ids

    def test_empty_text(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_text

        assert extract_citations_from_text("") == []

    def test_no_arxiv_ids(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_text

        text = "This paper has no arXiv references, only DOIs like 10.1234/example."
        assert extract_citations_from_text(text) == []

    def test_deduplicates_ids(self) -> None:
        from shesha.experimental.arxiv.citations import extract_citations_from_text

        text = "We cite arXiv:2301.04567 here and again arXiv:2301.04567 there."
        cites = extract_citations_from_text(text)
        assert len(cites) == 1
```

Run: `pytest tests/unit/experimental/arxiv/test_citations.py -v`
Expected: FAIL

### Step 2: Implement citation extraction

Create `src/shesha/experimental/arxiv/citations.py`:

```python
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
        import bibtexparser

        library = bibtexparser.parse(bib_content)
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
        return []


def extract_citations_from_bbl(bbl_content: str) -> list[ExtractedCitation]:
    """Extract citations from a .bbl file (\\bibitem entries)."""
    if not bbl_content.strip():
        return []
    citations = []
    # Split on \bibitem{...}
    pattern = re.compile(r"\\bibitem\{([^}]+)\}(.*?)(?=\\bibitem\{|\\end\{thebibliography\}|$)", re.DOTALL)
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
```

### Step 3: Run tests

Run: `pytest tests/unit/experimental/arxiv/test_citations.py -v`
Expected: All PASS

### Step 4: Commit

```bash
git add src/shesha/experimental/arxiv/citations.py tests/unit/experimental/arxiv/test_citations.py
git commit -m "feat(arxiv): add citation extraction and LLM-tell detection"
```

---

## Task 7: Citation Verification & Report

**Files:**
- Modify: `src/shesha/experimental/arxiv/citations.py` (add verification functions)
- Create: `tests/unit/experimental/arxiv/test_verification.py`

Verify arXiv citations against the arXiv API and format check reports.

### Step 1: Write failing tests

Create `tests/unit/experimental/arxiv/test_verification.py`:

```python
"""Tests for citation verification and report formatting."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestArxivVerifier:
    """Tests for ArxivVerifier."""

    @patch("shesha.experimental.arxiv.citations.ArxivSearcher")
    def test_verified_when_title_matches(self, mock_searcher_cls: MagicMock) -> None:
        from shesha.experimental.arxiv.citations import ArxivVerifier
        from shesha.experimental.arxiv.models import ExtractedCitation, PaperMeta, VerificationStatus

        mock_searcher = MagicMock()
        mock_searcher_cls.return_value = mock_searcher
        mock_searcher.get_by_id.return_value = PaperMeta(
            arxiv_id="2301.04567",
            title="Quantum Error Correction Survey",
            authors=["Smith, J."],
            abstract="",
            published=datetime(2023, 1, 1, tzinfo=timezone.utc),
            updated=datetime(2023, 1, 1, tzinfo=timezone.utc),
            categories=["cs.QI"],
            primary_category="cs.QI",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/2301.04567",
        )
        verifier = ArxivVerifier(searcher=mock_searcher)
        cite = ExtractedCitation(
            key="smith2023",
            title="Quantum Error Correction Survey",
            authors=["Smith, J."],
            year="2023",
            arxiv_id="2301.04567",
        )
        result = verifier.verify(cite)
        assert result.status == VerificationStatus.VERIFIED

    @patch("shesha.experimental.arxiv.citations.ArxivSearcher")
    def test_mismatch_when_title_differs(self, mock_searcher_cls: MagicMock) -> None:
        from shesha.experimental.arxiv.citations import ArxivVerifier
        from shesha.experimental.arxiv.models import ExtractedCitation, PaperMeta, VerificationStatus

        mock_searcher = MagicMock()
        mock_searcher_cls.return_value = mock_searcher
        mock_searcher.get_by_id.return_value = PaperMeta(
            arxiv_id="2301.04567",
            title="Fluid Dynamics of Turbulent Flow",
            authors=["Jones, K."],
            abstract="",
            published=datetime(2023, 1, 1, tzinfo=timezone.utc),
            updated=datetime(2023, 1, 1, tzinfo=timezone.utc),
            categories=["physics.flu-dyn"],
            primary_category="physics.flu-dyn",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/2301.04567",
        )
        verifier = ArxivVerifier(searcher=mock_searcher)
        cite = ExtractedCitation(
            key="smith2023",
            title="Quantum Memory Architectures",
            authors=["Smith, J."],
            year="2023",
            arxiv_id="2301.04567",
        )
        result = verifier.verify(cite)
        assert result.status == VerificationStatus.MISMATCH
        assert "Fluid Dynamics" in (result.actual_title or "")

    @patch("shesha.experimental.arxiv.citations.ArxivSearcher")
    def test_not_found_when_id_missing(self, mock_searcher_cls: MagicMock) -> None:
        from shesha.experimental.arxiv.citations import ArxivVerifier
        from shesha.experimental.arxiv.models import ExtractedCitation, VerificationStatus

        mock_searcher = MagicMock()
        mock_searcher_cls.return_value = mock_searcher
        mock_searcher.get_by_id.return_value = None

        verifier = ArxivVerifier(searcher=mock_searcher)
        cite = ExtractedCitation(
            key="x",
            title="Nonexistent",
            authors=[],
            year="2023",
            arxiv_id="9999.99999",
        )
        result = verifier.verify(cite)
        assert result.status == VerificationStatus.NOT_FOUND

    def test_unresolved_for_non_arxiv_citation(self) -> None:
        from shesha.experimental.arxiv.citations import ArxivVerifier
        from shesha.experimental.arxiv.models import ExtractedCitation, VerificationStatus

        verifier = ArxivVerifier(searcher=MagicMock())
        cite = ExtractedCitation(
            key="book2020",
            title="Some Book",
            authors=["Author"],
            year="2020",
            arxiv_id=None,
        )
        result = verifier.verify(cite)
        assert result.status == VerificationStatus.UNRESOLVED


class TestFormatCheckReport:
    """Tests for report formatting."""

    def test_format_includes_disclaimer(self) -> None:
        from shesha.experimental.arxiv.citations import format_check_report
        from shesha.experimental.arxiv.models import CheckReport

        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[],
            verification_results=[],
            llm_phrases=[],
        )
        output = format_check_report(report)
        assert "DISCLAIMER" in output
        assert "capable of making mistakes" in output

    def test_format_shows_mismatch_details(self) -> None:
        from shesha.experimental.arxiv.citations import format_check_report
        from shesha.experimental.arxiv.models import (
            CheckReport,
            ExtractedCitation,
            VerificationResult,
            VerificationStatus,
        )

        cite = ExtractedCitation(
            key="x",
            title="Quantum Memory",
            authors=[],
            year="2023",
            arxiv_id="2301.04567",
        )
        vr = VerificationResult(
            citation_key="x",
            status=VerificationStatus.MISMATCH,
            message='Cites "Quantum Memory" but actual paper is "Fluid Dynamics"',
            actual_title="Fluid Dynamics of Turbulent Flow",
            arxiv_url="https://arxiv.org/abs/2301.04567",
        )
        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[cite],
            verification_results=[vr],
            llm_phrases=[],
        )
        output = format_check_report(report)
        assert "MISMATCH" in output or "X" in output
        assert "Fluid Dynamics" in output
        assert "2301.04567" in output

    def test_format_shows_llm_phrases(self) -> None:
        from shesha.experimental.arxiv.citations import format_check_report
        from shesha.experimental.arxiv.models import CheckReport

        report = CheckReport(
            arxiv_id="2501.12345",
            title="Test Paper",
            citations=[],
            verification_results=[],
            llm_phrases=[(42, "As of my last knowledge update, X is true.")],
        )
        output = format_check_report(report)
        assert "42" in output
        assert "knowledge update" in output.lower()
```

Run: `pytest tests/unit/experimental/arxiv/test_verification.py -v`
Expected: FAIL

### Step 2: Add verification and report formatting to citations.py

Add to `src/shesha/experimental/arxiv/citations.py`:

```python
# Add these imports at top:
from shesha.experimental.arxiv.models import CheckReport, VerificationResult, VerificationStatus
from shesha.experimental.arxiv.search import ArxivSearcher


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
    """Fuzzy title comparison — normalize and check containment."""
    def normalize(t: str) -> str:
        return re.sub(r"[^\w\s]", "", t.lower()).strip()
    c, a = normalize(cited), normalize(actual)
    # Exact match or one contains the other (handles truncated titles)
    return c == a or c in a or a in c


def format_check_report(report: CheckReport) -> str:
    """Format a citation check report for display."""
    lines = [DISCLAIMER, ""]
    lines.append(f"-- Citation Check: {report.arxiv_id} \"{report.title}\" --")
    lines.append("")
    lines.append(f"Citations found: {len(report.citations)}")
    lines.append(f"  OK  {report.verified_count} verified")
    lines.append(f"  ?   {report.unresolved_count} unresolved (non-arXiv, could not verify)")
    lines.append(f"  X   {report.mismatch_count} mismatches")

    # Show mismatch details
    mismatches = [
        r for r in report.verification_results
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
            lines.append(f"  Line {line_num}: \"{phrase}\"")
    else:
        lines.append("LLM-tell phrases: none detected")

    return "\n".join(lines)
```

### Step 3: Run tests

Run: `pytest tests/unit/experimental/arxiv/test_verification.py -v`
Expected: All PASS

### Step 4: Commit

```bash
git add src/shesha/experimental/arxiv/citations.py tests/unit/experimental/arxiv/test_verification.py
git commit -m "feat(arxiv): add citation verification and report formatting"
```

---

## Task 8: CLI Core — Argument Parsing, Main Loop, Basic Commands

**Files:**
- Create: `examples/arxiv.py`
- Create: `tests/examples/test_arxiv.py`

This task builds the skeleton: arg parsing, the command dispatch loop, and basic commands (`/help`, `/quit`, `/topic`, `/topic delete`, `/history`, `/papers`).

**Pattern:** Follow `examples/repo.py` — use `argparse`, `input()` for the REPL, and function handlers for slash commands.

### Step 1: Write failing tests for arg parsing and basic commands

Create `tests/examples/test_arxiv.py`:

```python
"""Tests for the arXiv explorer CLI script."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[2] / "examples"))


class TestParseArgs:
    """Tests for argument parsing."""

    def test_defaults(self) -> None:
        from arxiv import parse_args

        args = parse_args([])
        assert args.model is None
        assert args.data_dir is None
        assert args.topic is None

    def test_model_flag(self) -> None:
        from arxiv import parse_args

        args = parse_args(["--model", "claude-sonnet-4-20250514"])
        assert args.model == "claude-sonnet-4-20250514"

    def test_data_dir_flag(self) -> None:
        from arxiv import parse_args

        args = parse_args(["--data-dir", "/tmp/test"])
        assert args.data_dir == "/tmp/test"

    def test_topic_flag(self) -> None:
        from arxiv import parse_args

        args = parse_args(["--topic", "my-topic"])
        assert args.topic == "my-topic"


class TestCommandDispatch:
    """Tests for slash command dispatch."""

    def test_help_command(self, capsys: object) -> None:
        from arxiv import handle_help

        # handle_help should print available commands
        handle_help("", state=MagicMock())
        # Just verify it doesn't crash — output goes to stdout

    def test_unknown_command_prints_error(self, capsys: object) -> None:
        from arxiv import dispatch_command

        state = MagicMock()
        dispatch_command("/unknown", state)
        # Should print "Unknown command" message

    def test_dispatch_routes_to_help(self) -> None:
        from arxiv import dispatch_command

        state = MagicMock()
        with patch("arxiv.handle_help") as mock_help:
            dispatch_command("/help", state)
            mock_help.assert_called_once()


class TestHistoryCommand:
    """Tests for /history command."""

    def test_history_empty(self, capsys: object) -> None:
        from arxiv import handle_history

        state = MagicMock()
        state.topic_mgr.list_topics.return_value = []
        handle_history("", state=state)
        # Should print "No topics" or similar

    def test_history_shows_topics(self, capsys: object) -> None:
        from datetime import datetime, timezone

        from arxiv import handle_history
        from shesha.experimental.arxiv.models import TopicInfo

        state = MagicMock()
        state.topic_mgr.list_topics.return_value = [
            TopicInfo(
                name="quantum-error-correction",
                created=datetime(2025, 1, 15, tzinfo=timezone.utc),
                paper_count=3,
                size_bytes=12_400_000,
                project_id="2025-01-15-quantum-error-correction",
            ),
        ]
        handle_history("", state=state)
        # Should print topic info with created date, paper count, size
```

Run: `pytest tests/examples/test_arxiv.py -v`
Expected: FAIL

### Step 2: Implement CLI skeleton

Create `examples/arxiv.py`. This is a large file — here is the structure:

```python
#!/usr/bin/env python3
"""Shesha arXiv Explorer — search, load, and query arXiv papers."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from script_utils import ThinkingSpinner, format_progress, format_stats, format_thought_time

from shesha.experimental.arxiv.cache import PaperCache
from shesha.experimental.arxiv.models import PaperMeta, TopicInfo
from shesha.experimental.arxiv.search import ArxivSearcher, format_result
from shesha.experimental.arxiv.topics import TopicManager


STARTUP_BANNER = """\
Shesha arXiv Explorer
Answers are AI-generated and may contain errors. Always verify against primary sources.
Type /help for commands."""

DEFAULT_DATA_DIR = Path.home() / ".shesha-arxiv"


@dataclass
class AppState:
    """Mutable application state passed to command handlers."""

    shesha: object  # Shesha instance
    topic_mgr: TopicManager
    cache: PaperCache
    searcher: ArxivSearcher
    current_topic: str | None = None  # Current project_id
    last_search_results: list[PaperMeta] = field(default_factory=list)
    _search_offset: int = 0  # Offset for /more pagination
    _last_search_kwargs: dict | None = None  # Last search params for /more


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Shesha arXiv Explorer")
    parser.add_argument("--model", type=str, help="LLM model to use")
    parser.add_argument("--data-dir", type=str, help="Data directory")
    parser.add_argument("--topic", type=str, help="Start in a specific topic")
    return parser.parse_args(argv)


# --- Command handlers ---
# Each handler has signature: (args: str, state: AppState) -> None


def handle_help(args: str, state: AppState) -> None:
    """Print available commands."""
    commands = [
        ("/search <query>", "Search arXiv (--author, --cat, --recent)"),
        ("/more", "Show next page of search results"),
        ("/load <nums or IDs>", "Load papers into current topic"),
        ("/papers", "List papers in current topic with arXiv URLs"),
        ("/check-citations [ID]", "Citation verification with disclaimer"),
        ("/topic [name]", "Switch to / create a topic"),
        ("/topic delete <name>", "Delete a topic"),
        ("/history", "List all topics with date, paper count, size"),
        ("/help", "Show this help message"),
        ("/quit", "Exit"),
    ]
    print("\nAvailable commands:")
    for cmd, desc in commands:
        print(f"  {cmd:<30s} {desc}")
    print()


def handle_history(args: str, state: AppState) -> None:
    """List all topics with metadata."""
    topics = state.topic_mgr.list_topics()
    if not topics:
        print("No topics yet. Use /search and /load to get started.")
        return
    print("\nTopics:")
    total_size = 0
    for i, t in enumerate(topics, 1):
        created_str = t.created.strftime("%b %d, %Y")
        papers_word = "paper" if t.paper_count == 1 else "papers"
        marker = " *" if t.project_id == state.current_topic else ""
        print(
            f"  {i}. {t.name:<35s} Created: {created_str:<15s}"
            f"  {t.paper_count} {papers_word:<8s} {t.formatted_size}{marker}"
        )
        total_size += t.size_bytes
    formatted_total = TopicInfo(
        name="", created=topics[0].created, paper_count=0,
        size_bytes=total_size, project_id="",
    ).formatted_size
    print(f"{'':>60s} Total: {formatted_total}")
    print()


def handle_topic(args: str, state: AppState) -> None:
    """Switch to or create a topic, or delete one."""
    args = args.strip()
    if not args:
        if state.current_topic:
            info = state.topic_mgr.get_topic_info_by_project_id(state.current_topic)
            if info:
                print(f"Current topic: {info.name}")
            else:
                print(f"Current topic: {state.current_topic}")
        else:
            print("No topic selected. Use /topic <name> to create or switch.")
        return

    parts = args.split(maxsplit=1)
    if parts[0] == "delete" and len(parts) > 1:
        name = parts[1]
        try:
            state.topic_mgr.delete(name)
            print(f"Deleted topic: {name}")
            if state.current_topic and name in state.current_topic:
                state.current_topic = None
        except ValueError as e:
            print(f"Error: {e}")
        return

    # Switch to or create topic
    name = args
    project_id = state.topic_mgr.resolve(name)
    if project_id:
        state.current_topic = project_id
        docs = state.topic_mgr._storage.list_documents(project_id)
        print(f"Switched to topic: {name} ({len(docs)} papers)")
    else:
        project_id = state.topic_mgr.create(name)
        state.current_topic = project_id
        print(f"Created topic: {name}")


def handle_papers(args: str, state: AppState) -> None:
    """List papers in the current topic."""
    if state.current_topic is None:
        print("No topic selected. Use /topic <name> first.")
        return
    docs = state.topic_mgr._storage.list_documents(state.current_topic)
    if not docs:
        print("No papers loaded. Use /search and /load to add papers.")
        return
    # Get topic name for display
    info = state.topic_mgr.get_topic_info_by_project_id(state.current_topic)
    topic_name = info.name if info else state.current_topic
    print(f'\nPapers in "{topic_name}":')
    for i, doc_name in enumerate(docs, 1):
        meta = state.cache.get_meta(doc_name)
        if meta:
            print(f'  {i}. [{meta.arxiv_id}] "{meta.title}"')
            print(f"     {meta.arxiv_url}")
        else:
            print(f"  {i}. {doc_name}")
    print()


COMMANDS: dict[str, tuple[callable, str]] = {
    "/help": (handle_help, "Show available commands"),
    "/history": (handle_history, "List topics"),
    "/topic": (handle_topic, "Topic management"),
    "/papers": (handle_papers, "List loaded papers"),
    # /search, /more, /load, /check-citations added in Tasks 9-10
}


def dispatch_command(user_input: str, state: AppState) -> bool:
    """Dispatch a slash command. Returns True if should quit."""
    parts = user_input.split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd in ("/quit", "/exit"):
        return True

    handler_entry = COMMANDS.get(cmd)
    if handler_entry is None:
        print(f"Unknown command: {cmd}. Type /help for available commands.")
        return False

    handler, _ = handler_entry
    handler(args, state=state)
    return False


def main() -> None:
    """Main entry point."""
    args = parse_args()
    print(STARTUP_BANNER)
    # Full initialization deferred to Tasks 9-10
    # For now, just the REPL loop skeleton


if __name__ == "__main__":
    main()
```

**Note:** This is a skeleton. Tasks 9 and 10 will add `/search`, `/more`, `/load`, `/check-citations`, the Shesha initialization, and the conversational query path.

### Step 3: Run tests

Run: `pytest tests/examples/test_arxiv.py -v`
Expected: All PASS

### Step 4: Commit

```bash
git add examples/arxiv.py tests/examples/test_arxiv.py
git commit -m "feat(arxiv): add CLI skeleton with basic commands"
```

---

## Task 9: CLI Search & Load Commands

**Files:**
- Modify: `examples/arxiv.py` (add `/search`, `/more`, `/load` handlers)
- Modify: `tests/examples/test_arxiv.py` (add tests)

### Step 1: Write failing tests

Add to `tests/examples/test_arxiv.py`:

```python
class TestSearchCommand:
    """Tests for /search command."""

    def test_search_stores_results_in_state(self) -> None:
        from datetime import datetime, timezone

        from arxiv import handle_search
        from shesha.experimental.arxiv.models import PaperMeta

        state = MagicMock()
        meta = PaperMeta(
            arxiv_id="2501.12345", title="Test", authors=["A"],
            abstract="", published=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated=datetime(2025, 1, 1, tzinfo=timezone.utc),
            categories=["cs.AI"], primary_category="cs.AI",
            pdf_url="", arxiv_url="https://arxiv.org/abs/2501.12345",
        )
        state.searcher.search.return_value = [meta]
        state.last_search_results = []
        handle_search("quantum computing", state=state)
        assert len(state.last_search_results) == 1

    def test_search_empty_query_prints_usage(self) -> None:
        from arxiv import handle_search

        state = MagicMock()
        handle_search("", state=state)
        state.searcher.search.assert_not_called()

    def test_search_parses_author_flag(self) -> None:
        from arxiv import handle_search

        state = MagicMock()
        state.searcher.search.return_value = []
        state.last_search_results = []
        handle_search('--author "del maestro"', state=state)
        state.searcher.search.assert_called_once()
        call_kwargs = state.searcher.search.call_args
        assert call_kwargs.kwargs.get("author") == "del maestro"

    def test_search_parses_category_flag(self) -> None:
        from arxiv import handle_search

        state = MagicMock()
        state.searcher.search.return_value = []
        state.last_search_results = []
        handle_search("--cat cs.AI language models", state=state)
        call_kwargs = state.searcher.search.call_args
        assert call_kwargs.kwargs.get("category") == "cs.AI"

    def test_search_parses_recent_flag(self) -> None:
        from arxiv import handle_search

        state = MagicMock()
        state.searcher.search.return_value = []
        state.last_search_results = []
        handle_search("--cat cs.AI --recent 7 transformers", state=state)
        call_kwargs = state.searcher.search.call_args
        assert call_kwargs.kwargs.get("recent_days") == 7
        assert call_kwargs.kwargs.get("category") == "cs.AI"


class TestMoreCommand:
    """Tests for /more command."""

    def test_more_without_search_prints_error(self) -> None:
        from arxiv import handle_more

        state = MagicMock()
        state.last_search_results = []
        state._search_offset = 0
        state._last_search_kwargs = None
        handle_more("", state=state)
        # Should print "No previous search" or similar

    def test_more_fetches_next_page(self) -> None:
        from datetime import datetime, timezone

        from arxiv import handle_more
        from shesha.experimental.arxiv.models import PaperMeta

        state = MagicMock()
        meta = PaperMeta(
            arxiv_id="2502.00001", title="Next Page Paper", authors=["B"],
            abstract="", published=datetime(2025, 2, 1, tzinfo=timezone.utc),
            updated=datetime(2025, 2, 1, tzinfo=timezone.utc),
            categories=["cs.AI"], primary_category="cs.AI",
            pdf_url="", arxiv_url="https://arxiv.org/abs/2502.00001",
        )
        state.searcher.search.return_value = [meta]
        state.last_search_results = [MagicMock()]  # Has previous results
        state._search_offset = 10
        state._last_search_kwargs = {"query": "test", "author": None, "category": None}
        handle_more("", state=state)
        # Should have called search with start=10 for pagination
        state.searcher.search.assert_called_once()
        call_kwargs = state.searcher.search.call_args
        assert call_kwargs.kwargs.get("start") == 10


class TestLoadCommand:
    """Tests for /load command."""

    def test_load_requires_topic(self) -> None:
        from arxiv import handle_load

        state = MagicMock()
        state.current_topic = None
        handle_load("1", state=state)
        # Should print error about no topic

    @patch("arxiv.download_paper")
    @patch("arxiv.to_parsed_document")
    def test_load_by_search_result_number(
        self, mock_to_doc: MagicMock, mock_download: MagicMock
    ) -> None:
        from datetime import datetime, timezone

        from arxiv import handle_load
        from shesha.experimental.arxiv.models import PaperMeta
        from shesha.models import ParsedDocument

        state = MagicMock()
        state.current_topic = "2025-01-15-test"
        meta = PaperMeta(
            arxiv_id="2501.12345", title="Test", authors=["A"],
            abstract="", published=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated=datetime(2025, 1, 1, tzinfo=timezone.utc),
            categories=["cs.AI"], primary_category="cs.AI",
            pdf_url="", arxiv_url="https://arxiv.org/abs/2501.12345",
            source_type="latex",
        )
        state.last_search_results = [meta]
        state.cache.has.return_value = True
        state.cache.get_meta.return_value = meta
        mock_download.return_value = meta
        mock_to_doc.return_value = ParsedDocument(
            name="2501.12345", content="content", format="latex",
            metadata={"arxiv_url": "https://arxiv.org/abs/2501.12345"},
            char_count=7,
        )
        handle_load("1", state=state)
        # Should store the document in the topic
        state.topic_mgr._storage.store_document.assert_called_once()

    @patch("arxiv.download_paper")
    @patch("arxiv.to_parsed_document")
    def test_load_by_arxiv_id(
        self, mock_to_doc: MagicMock, mock_download: MagicMock
    ) -> None:
        from datetime import datetime, timezone

        from arxiv import handle_load
        from shesha.experimental.arxiv.models import PaperMeta
        from shesha.models import ParsedDocument

        state = MagicMock()
        state.current_topic = "2025-01-15-test"
        meta = PaperMeta(
            arxiv_id="2501.12345", title="Test", authors=["A"],
            abstract="", published=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated=datetime(2025, 1, 1, tzinfo=timezone.utc),
            categories=["cs.AI"], primary_category="cs.AI",
            pdf_url="", arxiv_url="https://arxiv.org/abs/2501.12345",
            source_type="latex",
        )
        state.cache.has.return_value = False
        state.searcher.get_by_id.return_value = meta
        mock_download.return_value = meta
        mock_to_doc.return_value = ParsedDocument(
            name="2501.12345", content="content", format="latex",
            metadata={"arxiv_url": "https://arxiv.org/abs/2501.12345"},
            char_count=7,
        )
        state.last_search_results = []
        handle_load("2501.12345", state=state)
        state.searcher.get_by_id.assert_called_once_with("2501.12345")

    def test_load_invalid_input_prints_error(self) -> None:
        from arxiv import handle_load

        state = MagicMock()
        state.current_topic = "2025-01-15-test"
        state.last_search_results = []
        handle_load("not-a-number-or-id", state=state)
        # Should print error about invalid input

    def test_load_creates_topic_if_none_selected_and_search_exists(self) -> None:
        """If no topic is selected but we have search results, auto-create topic."""
        from arxiv import handle_load

        state = MagicMock()
        state.current_topic = None
        handle_load("1", state=state)
        # Should print error asking to select/create a topic first
```

Run: `pytest tests/examples/test_arxiv.py::TestSearchCommand -v`
Expected: FAIL

### Step 2: Implement search, more, and load handlers

Add these functions to `examples/arxiv.py` and register them in `COMMANDS`:

```python
import re
import time

from shesha.experimental.arxiv.download import download_paper, to_parsed_document
from shesha.experimental.arxiv.search import format_result

# Pattern to recognize arXiv IDs
ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")


def _parse_search_flags(args_str: str) -> tuple[str, dict]:
    """Parse --author, --cat, --recent flags from search args string.

    Returns (remaining_query, kwargs_for_searcher).
    """
    tokens = args_str.split()
    author = None
    category = None
    recent_days = None
    query_parts = []
    i = 0
    while i < len(tokens):
        if tokens[i] == "--author" and i + 1 < len(tokens):
            i += 1
            # Handle quoted author names
            if tokens[i].startswith('"'):
                parts = [tokens[i].lstrip('"')]
                while i + 1 < len(tokens) and not tokens[i].endswith('"'):
                    i += 1
                    parts.append(tokens[i].rstrip('"'))
                author = " ".join(parts).rstrip('"')
            else:
                author = tokens[i]
        elif tokens[i] == "--cat" and i + 1 < len(tokens):
            i += 1
            category = tokens[i]
        elif tokens[i] == "--recent" and i + 1 < len(tokens):
            i += 1
            try:
                recent_days = int(tokens[i])
            except ValueError:
                recent_days = None
        else:
            query_parts.append(tokens[i])
        i += 1
    query = " ".join(query_parts)
    kwargs: dict = {"author": author, "category": category}
    if recent_days is not None:
        kwargs["recent_days"] = recent_days
    return query, kwargs


def handle_search(args: str, state: AppState) -> None:
    """Search arXiv and display results."""
    args = args.strip()
    if not args:
        print("Usage: /search <query> [--author NAME] [--cat CATEGORY]")
        print("Examples:")
        print('  /search quantum error correction')
        print('  /search --author "del maestro"')
        print("  /search --cat cs.AI language models")
        return
    query, kwargs = _parse_search_flags(args)
    print(f"Searching arXiv...")
    try:
        results = state.searcher.search(query, **kwargs)
    except Exception as e:
        print(f"Search error: {e}")
        return
    state.last_search_results = results
    state._search_offset = len(results)
    state._last_search_kwargs = {"query": query, **kwargs}
    if not results:
        print("No results found.")
        return
    print(f"Found results. Showing 1-{len(results)}:\n")
    for i, meta in enumerate(results, 1):
        print(format_result(meta, i))
        print()


def handle_more(args: str, state: AppState) -> None:
    """Show next page of search results."""
    if state._last_search_kwargs is None or not state.last_search_results:
        print("No previous search. Use /search first.")
        return
    offset = state._search_offset
    print("Fetching more results...")
    try:
        results = state.searcher.search(**state._last_search_kwargs, max_results=10, start=offset)
    except Exception as e:
        print(f"Search error: {e}")
        return
    if not results:
        print("No more results.")
        return
    # Append to existing results
    start_idx = len(state.last_search_results)
    state.last_search_results.extend(results)
    state._search_offset = len(state.last_search_results)
    print(f"Showing {start_idx + 1}-{start_idx + len(results)}:\n")
    for i, meta in enumerate(results, start_idx + 1):
        print(format_result(meta, i))
        print()


def handle_load(args: str, state: AppState) -> None:
    """Load papers into the current topic by search result number or arXiv ID."""
    if state.current_topic is None:
        print("No topic selected. Use /topic <name> to create or switch first.")
        return
    args = args.strip()
    if not args:
        print("Usage: /load <numbers or arXiv IDs>")
        print("Examples:")
        print("  /load 1 3 5          (by search result number)")
        print("  /load 2501.12345     (by arXiv ID)")
        return

    # Parse tokens — each is either a result number or an arXiv ID
    tokens = args.split()
    papers_to_load: list[PaperMeta] = []
    for token in tokens:
        if ARXIV_ID_RE.match(token):
            # Direct arXiv ID
            if state.cache.has(token):
                meta = state.cache.get_meta(token)
                if meta:
                    papers_to_load.append(meta)
                    continue
            # Fetch metadata from arXiv
            print(f"  Looking up {token}...")
            meta = state.searcher.get_by_id(token)
            if meta is None:
                print(f"  Error: arXiv ID {token} not found.")
                continue
            papers_to_load.append(meta)
        else:
            # Try as result number
            try:
                num = int(token)
            except ValueError:
                print(f"  Error: '{token}' is not a valid number or arXiv ID.")
                continue
            if num < 1 or num > len(state.last_search_results):
                print(f"  Error: result #{num} out of range (1-{len(state.last_search_results)}).")
                continue
            papers_to_load.append(state.last_search_results[num - 1])

    if not papers_to_load:
        return

    print(f"Loading {len(papers_to_load)} paper(s) (source first, PDF fallback)...")
    for meta in papers_to_load:
        cached = state.cache.has(meta.arxiv_id)
        label = "[cached]" if cached else "[new]   "
        try:
            updated_meta = download_paper(meta, state.cache)
            doc = to_parsed_document(updated_meta.arxiv_id, state.cache)
            state.topic_mgr._storage.store_document(state.current_topic, doc)
            source_desc = updated_meta.source_type or "unknown"
            print(f"  {label} {meta.arxiv_id} - {source_desc}")
        except Exception as e:
            print(f"  [error]  {meta.arxiv_id} - {e}")
        if not cached:
            time.sleep(3.0)  # Respect arXiv rate limit between downloads


# Update COMMANDS dict to include new handlers:
# Add these entries:
#     "/search": (handle_search, "Search arXiv"),
#     "/more": (handle_more, "Next page of results"),
#     "/load": (handle_load, "Load papers"),
```

### Step 3: Run tests

Run: `pytest tests/examples/test_arxiv.py -v`
Expected: All PASS

### Step 4: Commit

```bash
git add examples/arxiv.py tests/examples/test_arxiv.py
git commit -m "feat(arxiv): add /search, /more, /load commands"
```

---

## Task 10: CLI Query & Citation Check

**Files:**
- Modify: `examples/arxiv.py` (add query handling, `/check-citations`, full Shesha init)
- Modify: `tests/examples/test_arxiv.py` (add tests)

### Step 1: Write failing tests

Add to `tests/examples/test_arxiv.py`:

```python
class TestCheckCitationsCommand:
    """Tests for /check-citations command."""

    def test_check_requires_topic(self) -> None:
        from arxiv import handle_check_citations

        state = MagicMock()
        state.current_topic = None
        handle_check_citations("", state=state)
        # Should not crash, prints error

    def test_check_no_papers_prints_message(self) -> None:
        from arxiv import handle_check_citations

        state = MagicMock()
        state.current_topic = "2025-01-15-test"
        state.topic_mgr._storage.list_documents.return_value = []
        handle_check_citations("", state=state)
        # Should print "no papers" message

    @patch("arxiv.ArxivVerifier")
    def test_check_runs_full_pipeline(self, mock_verifier_cls: MagicMock) -> None:
        from datetime import datetime, timezone

        from arxiv import handle_check_citations
        from shesha.experimental.arxiv.models import PaperMeta, VerificationResult, VerificationStatus

        state = MagicMock()
        state.current_topic = "2025-01-15-test"
        state.topic_mgr._storage.list_documents.return_value = ["2501.12345"]
        # Paper has bib file in cache
        meta = PaperMeta(
            arxiv_id="2501.12345", title="Test Paper", authors=["A"],
            abstract="", published=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated=datetime(2025, 1, 1, tzinfo=timezone.utc),
            categories=["cs.AI"], primary_category="cs.AI",
            pdf_url="", arxiv_url="https://arxiv.org/abs/2501.12345",
            source_type="latex",
        )
        state.cache.get_meta.return_value = meta
        state.cache.get_source_files.return_value = {
            "main.tex": "\\documentclass{article}\\begin{document}Test.\\end{document}",
            "refs.bib": "@article{a, author={A}, title={Paper A}, year={2023}, eprint={2301.00001}}",
        }
        mock_verifier = MagicMock()
        mock_verifier_cls.return_value = mock_verifier
        mock_verifier.verify.return_value = VerificationResult(
            citation_key="a",
            status=VerificationStatus.VERIFIED,
        )
        handle_check_citations("", state=state)
        mock_verifier.verify.assert_called_once()

    def test_check_output_includes_disclaimer(self, capsys: object) -> None:
        """Regardless of what happens, /check-citations must print the disclaimer."""
        from arxiv import handle_check_citations

        state = MagicMock()
        state.current_topic = "2025-01-15-test"
        state.topic_mgr._storage.list_documents.return_value = ["2501.12345"]
        state.cache.get_meta.return_value = MagicMock(
            arxiv_id="2501.12345", title="Test", source_type="latex"
        )
        state.cache.get_source_files.return_value = {"main.tex": "\\documentclass{article}"}
        handle_check_citations("", state=state)
        captured = capsys.readouterr()
        assert "DISCLAIMER" in captured.out


class TestConversationalQuery:
    """Tests for non-command input (questions)."""

    def test_query_requires_topic(self) -> None:
        from arxiv import handle_query

        state = MagicMock()
        state.current_topic = None
        handle_query("What is this paper about?", state=state)
        # Should not crash

    def test_query_requires_papers(self) -> None:
        from arxiv import handle_query

        state = MagicMock()
        state.current_topic = "2025-01-15-test"
        state.topic_mgr._storage.list_documents.return_value = []
        handle_query("What is this paper about?", state=state)
        # Should print error about no papers

    @patch("arxiv.ThinkingSpinner")
    def test_query_calls_shesha_project_query(self, mock_spinner: MagicMock) -> None:
        from unittest.mock import PropertyMock

        from arxiv import handle_query
        from shesha.rlm.trace import TokenUsage, Trace

        state = MagicMock()
        state.current_topic = "2025-01-15-test"
        state.topic_mgr._storage.list_documents.return_value = ["2501.12345"]

        # Mock the project returned by shesha.get_project()
        mock_result = MagicMock()
        mock_result.answer = "The paper discusses quantum error correction."
        mock_result.execution_time = 5.2
        mock_result.token_usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
        mock_result.trace = Trace()
        mock_result.semantic_verification = None
        state.shesha.get_project.return_value.query.return_value = mock_result

        handle_query("What is this paper about?", state=state)
        state.shesha.get_project.assert_called_once_with("2025-01-15-test")
        state.shesha.get_project.return_value.query.assert_called_once()


class TestMainFunction:
    """Tests for the main() entry point."""

    @patch("arxiv.input", side_effect=EOFError)
    @patch("arxiv.Shesha")
    @patch("arxiv.SheshaConfig")
    @patch("arxiv.FilesystemStorage")
    def test_main_prints_startup_banner(
        self,
        mock_storage: MagicMock,
        mock_config: MagicMock,
        mock_shesha: MagicMock,
        mock_input: MagicMock,
        capsys: object,
    ) -> None:
        from arxiv import main

        mock_config.load.return_value = MagicMock(storage_path="/tmp/test")
        mock_storage.return_value = MagicMock()
        mock_storage.return_value.list_projects.return_value = []
        try:
            main()
        except SystemExit:
            pass
        captured = capsys.readouterr()
        assert "Shesha arXiv Explorer" in captured.out
        assert "AI-generated" in captured.out

    @patch("arxiv.input", side_effect=["/quit"])
    @patch("arxiv.Shesha")
    @patch("arxiv.SheshaConfig")
    @patch("arxiv.FilesystemStorage")
    def test_main_quit_command_exits(
        self,
        mock_storage: MagicMock,
        mock_config: MagicMock,
        mock_shesha: MagicMock,
        mock_input: MagicMock,
    ) -> None:
        from arxiv import main

        mock_config.load.return_value = MagicMock(storage_path="/tmp/test")
        mock_storage.return_value = MagicMock()
        mock_storage.return_value.list_projects.return_value = []
        # Should exit cleanly without exception
        main()
```

Run: `pytest tests/examples/test_arxiv.py::TestCheckCitationsCommand -v`
Expected: FAIL

### Step 2: Implement query handling, /check-citations, and main()

Add these functions to `examples/arxiv.py`:

```python
import time

from shesha import Shesha, SheshaConfig
from shesha.storage.filesystem import FilesystemStorage
from shesha.rlm.trace import StepType

from shesha.experimental.arxiv.citations import (
    ArxivVerifier,
    detect_llm_phrases,
    extract_citations_from_bib,
    extract_citations_from_bbl,
    extract_citations_from_text,
    format_check_report,
)
from shesha.experimental.arxiv.models import CheckReport, ExtractedCitation


def handle_check_citations(args: str, state: AppState) -> None:
    """Run citation verification on loaded papers."""
    if state.current_topic is None:
        print("No topic selected. Use /topic <name> first.")
        return
    doc_names = state.topic_mgr._storage.list_documents(state.current_topic)
    if not doc_names:
        print("No papers loaded. Use /search and /load to add papers.")
        return

    # Filter to specific paper if ID provided
    target_id = args.strip() if args.strip() else None
    if target_id:
        doc_names = [d for d in doc_names if target_id in d]
        if not doc_names:
            print(f"Paper {target_id} not found in current topic.")
            return

    verifier = ArxivVerifier(searcher=state.searcher)

    for doc_name in doc_names:
        meta = state.cache.get_meta(doc_name)
        if meta is None:
            print(f"  Skipping {doc_name}: no metadata in cache.")
            continue

        # Extract citations
        citations: list[ExtractedCitation] = []
        source_files = state.cache.get_source_files(doc_name)
        full_text = ""

        if source_files is not None:
            for filename, content in source_files.items():
                full_text += content + "\n"
                if filename.endswith(".bib"):
                    citations.extend(extract_citations_from_bib(content))
                elif filename.endswith(".bbl"):
                    citations.extend(extract_citations_from_bbl(content))
        else:
            # Try to get text from the stored document (PDF fallback)
            try:
                doc = state.topic_mgr._storage.get_document(state.current_topic, doc_name)
                full_text = doc.content
                citations.extend(extract_citations_from_text(full_text))
            except Exception:
                full_text = ""

        # Detect LLM-tell phrases
        llm_phrases = detect_llm_phrases(full_text)

        # Verify citations
        print(f"  Checking citations in {meta.arxiv_id}...")
        verification_results = []
        for cite in citations:
            result = verifier.verify(cite)
            verification_results.append(result)

        report = CheckReport(
            arxiv_id=meta.arxiv_id,
            title=meta.title,
            citations=citations,
            verification_results=verification_results,
            llm_phrases=llm_phrases,
        )
        print(format_check_report(report))
        print()


def handle_query(question: str, state: AppState) -> None:
    """Handle a conversational query against loaded papers."""
    if state.current_topic is None:
        print("No topic selected. Use /topic <name> to create or switch first.")
        return
    doc_names = state.topic_mgr._storage.list_documents(state.current_topic)
    if not doc_names:
        print("No papers loaded. Use /search and /load to add papers first.")
        return

    project = state.shesha.get_project(state.current_topic)
    spinner = ThinkingSpinner()
    spinner.start()
    query_start_time = time.time()

    def on_progress(
        step_type: StepType, iteration: int, content: str, tokens: object
    ) -> None:
        spinner.stop()
        elapsed = time.time() - query_start_time
        print(format_progress(step_type, iteration, content, elapsed_seconds=elapsed))
        spinner.start()

    try:
        result = project.query(question, on_progress=on_progress)
    except Exception as e:
        spinner.stop()
        print(f"Query error: {e}")
        return
    spinner.stop()

    elapsed = time.time() - query_start_time
    print(format_thought_time(elapsed))
    print()
    print(result.answer)
    print()
    print(format_stats(result.execution_time, result.token_usage, result.trace))


# Update the COMMANDS dict — final version with all handlers:
COMMANDS = {
    "/help": (handle_help, "Show available commands"),
    "/history": (handle_history, "List topics"),
    "/topic": (handle_topic, "Topic management"),
    "/papers": (handle_papers, "List loaded papers"),
    "/search": (handle_search, "Search arXiv"),
    "/more": (handle_more, "Next page of results"),
    "/load": (handle_load, "Load papers"),
    "/check-citations": (handle_check_citations, "Citation verification"),
}


def main() -> None:
    """Main entry point."""
    args = parse_args()
    print(STARTUP_BANNER)

    # Determine data directory
    data_dir = Path(args.data_dir) if args.data_dir else DEFAULT_DATA_DIR
    shesha_data = data_dir / "shesha_data"
    cache_dir = data_dir / "paper-cache"

    # Check for API key
    if not os.environ.get("SHESHA_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: Set SHESHA_API_KEY or ANTHROPIC_API_KEY environment variable.")
        sys.exit(1)

    # Initialize components
    config = SheshaConfig.load(
        storage_path=str(shesha_data),
        model=args.model,
    )
    storage = FilesystemStorage(shesha_data)
    shesha = Shesha(config=config, storage=storage)
    cache = PaperCache(cache_dir)
    searcher = ArxivSearcher()
    topic_mgr = TopicManager(shesha, storage, shesha_data)

    state = AppState(
        shesha=shesha,
        topic_mgr=topic_mgr,
        cache=cache,
        searcher=searcher,
    )

    # If --topic specified, switch to it
    if args.topic:
        project_id = topic_mgr.resolve(args.topic)
        if project_id:
            state.current_topic = project_id
            docs = storage.list_documents(project_id)
            print(f"Topic: {args.topic} ({len(docs)} papers)")
        else:
            project_id = topic_mgr.create(args.topic)
            state.current_topic = project_id
            print(f"Created topic: {args.topic}")

    # Main REPL loop
    try:
        while True:
            try:
                prompt = "arxiv> "
                user_input = input(prompt).strip()
            except EOFError:
                break
            if not user_input:
                continue

            if user_input.startswith("/"):
                should_quit = dispatch_command(user_input, state)
                if should_quit:
                    break
            else:
                # Conversational query
                handle_query(user_input, state=state)
    except KeyboardInterrupt:
        print()  # Clean newline after ^C
    finally:
        print("Cleaning up...")
        try:
            shesha.stop()
        except Exception:
            pass  # May not have started


if __name__ == "__main__":
    main()
```

### Step 3: Run tests

Run: `pytest tests/examples/test_arxiv.py -v`
Expected: All PASS

### Step 4: Run full test suite

Run: `make all`
Expected: All tests pass, no lint/type errors

### Step 5: Commit

```bash
git add examples/arxiv.py tests/examples/test_arxiv.py
git commit -m "feat(arxiv): add conversational queries and /check-citations"
```

---

## Task 11: Integration Polish & Changelog

**Files:**
- Modify: `examples/arxiv.py` (edge cases, cleanup)
- Modify: `tests/examples/test_arxiv.py` (edge case tests)
- Modify: `CHANGELOG.md`

**Note:** `get_topic_info_by_project_id` is already implemented and tested in Task 3.

### Step 1: Write edge case tests

Add to `tests/examples/test_arxiv.py`:

```python
class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_topic_command_no_args_no_topic(self) -> None:
        from arxiv import handle_topic

        state = MagicMock()
        state.current_topic = None
        handle_topic("", state=state)
        # Should print "No topic selected"

    def test_topic_command_no_args_with_topic(self) -> None:
        from datetime import datetime, timezone

        from arxiv import handle_topic
        from shesha.experimental.arxiv.models import TopicInfo

        state = MagicMock()
        state.current_topic = "2025-01-15-my-topic"
        state.topic_mgr.get_topic_info_by_project_id.return_value = TopicInfo(
            name="my-topic",
            created=datetime(2025, 1, 15, tzinfo=timezone.utc),
            paper_count=2,
            size_bytes=5000,
            project_id="2025-01-15-my-topic",
        )
        handle_topic("", state=state)
        # Should print current topic name

    def test_topic_delete_nonexistent(self) -> None:
        from arxiv import handle_topic

        state = MagicMock()
        state.topic_mgr.delete.side_effect = ValueError("Topic not found: fake")
        handle_topic("delete fake", state=state)
        # Should print error message

    def test_papers_no_topic(self) -> None:
        from arxiv import handle_papers

        state = MagicMock()
        state.current_topic = None
        handle_papers("", state=state)
        # Should print "No topic selected"

    def test_dispatch_quit_returns_true(self) -> None:
        from arxiv import dispatch_command

        state = MagicMock()
        assert dispatch_command("/quit", state) is True

    def test_dispatch_exit_returns_true(self) -> None:
        from arxiv import dispatch_command

        state = MagicMock()
        assert dispatch_command("/exit", state) is True
```

### Step 2: Run all tests

Run: `pytest tests/unit/experimental/arxiv/ tests/examples/test_arxiv.py -v`
Expected: All PASS

### Step 3: Run full suite

Run: `make all`
Expected: All 1082+ tests pass, no lint/type errors, no warnings

### Step 4: Update CHANGELOG.md

Add under `[Unreleased]` > `Added`:

```markdown
- arXiv Explorer example (`examples/arxiv.py`) — interactive CLI for searching arXiv,
  loading papers into topics, and querying them with Shesha. Features:
  - `/search` with author, category, and keyword filtering
  - `/load` papers by search result number or arXiv ID (source first, PDF fallback)
  - `/check-citations` for automated citation verification against arXiv API with
    LLM-tell phrase detection (always shown with AI disclaimer)
  - `/history` for persistent topic management with creation dates and size on disk
  - Central paper cache to avoid redundant downloads
```

### Step 5: Final commit

```bash
git add examples/ src/shesha/experimental/ tests/ CHANGELOG.md pyproject.toml
git commit -m "feat(arxiv): complete arXiv Explorer example with citation checking"
```

---

## Summary

| Task | Description | Key Files |
|------|-------------|-----------|
| 1 | Setup + data models | `experimental/arxiv/models.py`, `pyproject.toml` |
| 2 | Paper cache | `experimental/arxiv/cache.py` |
| 3 | Topic manager | `experimental/arxiv/topics.py` |
| 4 | arXiv search wrapper | `experimental/arxiv/search.py` |
| 5 | Paper downloader | `experimental/arxiv/download.py` |
| 6 | Citation extraction | `experimental/arxiv/citations.py` |
| 7 | Citation verification | `experimental/arxiv/citations.py` (extend) |
| 8 | CLI core + basic commands | `arxiv.py` |
| 9 | Search + load commands | `arxiv.py` (extend) |
| 10 | Query + check-citations | `arxiv.py` (extend) |
| 11 | Integration polish | All files |
