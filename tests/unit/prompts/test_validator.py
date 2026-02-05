"""Tests for prompt validator."""

from shesha.prompts.validator import extract_placeholders


def test_extract_placeholders_finds_simple():
    """extract_placeholders finds {name} patterns."""
    text = "Hello {name}, you have {count} messages."
    placeholders = extract_placeholders(text)
    assert placeholders == {"name", "count"}


def test_extract_placeholders_handles_format_spec():
    """extract_placeholders handles {name:,} format specs."""
    text = "Total: {total_chars:,} chars"
    placeholders = extract_placeholders(text)
    assert placeholders == {"total_chars"}


def test_extract_placeholders_empty():
    """extract_placeholders returns empty set for no placeholders."""
    text = "No placeholders here"
    placeholders = extract_placeholders(text)
    assert placeholders == set()
