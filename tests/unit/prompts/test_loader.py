"""Tests for PromptLoader."""

from pathlib import Path

import pytest

from shesha.prompts.loader import PromptLoader, resolve_prompts_dir
from shesha.prompts.validator import PromptValidationError


@pytest.fixture
def valid_prompts_dir(tmp_path: Path) -> Path:
    """Create a valid prompts directory."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    (prompts_dir / "system.md").write_text(
        "Doc count: {doc_count}, chars: {total_chars:,}\n"
        "Sizes: {doc_sizes_list}\n"
        "Limit: {max_subcall_chars:,}"
    )
    (prompts_dir / "subcall.md").write_text("{instruction}\n<content>{content}</content>")
    (prompts_dir / "code_required.md").write_text("Write code now.")

    return prompts_dir


def test_loader_loads_from_directory(valid_prompts_dir: Path):
    """PromptLoader loads prompts from specified directory."""
    loader = PromptLoader(prompts_dir=valid_prompts_dir)
    assert loader.prompts_dir == valid_prompts_dir


def test_loader_validates_on_init(tmp_path: Path):
    """PromptLoader validates prompts on initialization."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    # Missing required placeholder
    (prompts_dir / "system.md").write_text("Missing placeholders")
    (prompts_dir / "subcall.md").write_text("{instruction}\n{content}")
    (prompts_dir / "code_required.md").write_text("Write code.")

    with pytest.raises(PromptValidationError) as exc_info:
        PromptLoader(prompts_dir=prompts_dir)
    assert "system.md" in str(exc_info.value)


def test_loader_render_system_prompt(valid_prompts_dir: Path):
    """PromptLoader renders system prompt with variables."""
    loader = PromptLoader(prompts_dir=valid_prompts_dir)
    result = loader.render_system_prompt(
        doc_count=3,
        total_chars=10000,
        doc_sizes_list="  - doc1: 5000\n  - doc2: 5000",
        max_subcall_chars=500000,
    )
    assert "3" in result
    assert "10,000" in result
    assert "doc1" in result
    assert "500,000" in result


def test_loader_render_subcall_prompt(valid_prompts_dir: Path):
    """PromptLoader renders subcall prompt with variables."""
    loader = PromptLoader(prompts_dir=valid_prompts_dir)
    result = loader.render_subcall_prompt(
        instruction="Summarize this",
        content="Document content here",
    )
    assert "Summarize this" in result
    assert "Document content here" in result


def test_loader_render_code_required(valid_prompts_dir: Path):
    """PromptLoader renders code_required prompt."""
    loader = PromptLoader(prompts_dir=valid_prompts_dir)
    result = loader.render_code_required()
    assert "Write code" in result


def test_resolve_prompts_dir_uses_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """resolve_prompts_dir uses SHESHA_PROMPTS_DIR env var."""
    monkeypatch.setenv("SHESHA_PROMPTS_DIR", str(tmp_path))
    result = resolve_prompts_dir()
    assert result == tmp_path


def test_loader_raises_when_directory_missing(tmp_path: Path):
    """PromptLoader raises FileNotFoundError for missing directory."""
    missing_dir = tmp_path / "nonexistent"
    with pytest.raises(FileNotFoundError) as exc_info:
        PromptLoader(prompts_dir=missing_dir)
    assert "Prompts directory not found" in str(exc_info.value)


def test_loader_raises_when_file_missing(tmp_path: Path):
    """PromptLoader raises FileNotFoundError for missing prompt file."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    # Only create some files, not all
    (prompts_dir / "system.md").write_text(
        "{doc_count}{total_chars:,}{doc_sizes_list}{max_subcall_chars:,}"
    )

    with pytest.raises(FileNotFoundError) as exc_info:
        PromptLoader(prompts_dir=prompts_dir)
    assert "Required prompt file not found" in str(exc_info.value)
