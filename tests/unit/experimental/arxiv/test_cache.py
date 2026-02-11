"""Tests for paper cache."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

# Late import: test helper uses deferred import pattern matching other test files
from shesha.experimental.arxiv.models import PaperMeta


def _make_meta() -> PaperMeta:
    return PaperMeta(
        arxiv_id="2501.12345",
        title="Test Paper",
        authors=["Smith, J."],
        abstract="Abstract",
        published=datetime(2025, 1, 15, tzinfo=UTC),
        updated=datetime(2025, 1, 15, tzinfo=UTC),
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
