"""Tests for default parser registry."""

from pathlib import Path

from shesha.parser import create_default_registry


def test_default_registry_has_text_parser():
    """Default registry can parse text files."""
    registry = create_default_registry()
    assert registry.find_parser(Path("test.txt")) is not None


def test_default_registry_has_code_parser():
    """Default registry can parse code files."""
    registry = create_default_registry()
    assert registry.find_parser(Path("test.py")) is not None


def test_default_registry_has_pdf_parser():
    """Default registry can parse PDF files."""
    registry = create_default_registry()
    assert registry.find_parser(Path("test.pdf")) is not None


def test_default_registry_has_html_parser():
    """Default registry can parse HTML files."""
    registry = create_default_registry()
    assert registry.find_parser(Path("test.html")) is not None


def test_default_registry_has_docx_parser():
    """Default registry can parse docx files."""
    registry = create_default_registry()
    assert registry.find_parser(Path("test.docx")) is not None
