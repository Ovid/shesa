"""Tests for citation instruction builder."""

from unittest.mock import MagicMock

from shesha.experimental.web.websockets import build_citation_instructions


def test_build_citation_instructions_single_paper() -> None:
    """Single paper produces instruction block with one entry."""
    cache = MagicMock()
    meta = MagicMock()
    meta.title = "An Objective Bayesian Analysis"
    cache.get_meta.return_value = meta

    result = build_citation_instructions(["2005.09008v1"], cache)

    assert "[@arxiv:2005.09008v1]" in result
    assert "An Objective Bayesian Analysis" in result
    assert "CITATION INSTRUCTIONS" in result


def test_build_citation_instructions_multiple_papers() -> None:
    """Multiple papers listed in instruction block."""
    cache = MagicMock()

    def fake_meta(arxiv_id: str) -> MagicMock:
        m = MagicMock()
        m.title = f"Title for {arxiv_id}"
        return m

    cache.get_meta.side_effect = fake_meta

    result = build_citation_instructions(["2005.09008v1", "2401.12345"], cache)

    assert "[@arxiv:2005.09008v1]" in result
    assert "[@arxiv:2401.12345]" in result
    assert "Title for 2005.09008v1" in result
    assert "Title for 2401.12345" in result


def test_build_citation_instructions_missing_meta_uses_id() -> None:
    """When cache has no metadata, fall back to arxiv_id as title."""
    cache = MagicMock()
    cache.get_meta.return_value = None

    result = build_citation_instructions(["2005.09008v1"], cache)

    assert "[@arxiv:2005.09008v1]" in result
    # Should still produce valid instructions even without title
    assert "2005.09008v1" in result


def test_build_citation_instructions_empty_list() -> None:
    """Empty paper list returns empty string."""
    cache = MagicMock()

    result = build_citation_instructions([], cache)

    assert result == ""
