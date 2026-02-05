"""Tests for prompts CLI validation tool."""

import subprocess
import sys
from pathlib import Path


def test_cli_validates_valid_prompts(tmp_path: Path):
    """CLI exits 0 for valid prompts."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    (prompts_dir / "system.md").write_text(
        "{doc_count} {total_chars:,} {doc_sizes_list} {max_subcall_chars:,}"
    )
    (prompts_dir / "subcall.md").write_text("{instruction}\n{content}")
    (prompts_dir / "code_required.md").write_text("Write code.")

    result = subprocess.run(
        [sys.executable, "-m", "shesha.prompts", "--prompts-dir", str(prompts_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "OK" in result.stdout or "passed" in result.stdout.lower()


def test_cli_fails_invalid_prompts(tmp_path: Path):
    """CLI exits 1 for invalid prompts."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    (prompts_dir / "system.md").write_text("Missing all placeholders")
    (prompts_dir / "subcall.md").write_text("{instruction}\n{content}")
    (prompts_dir / "code_required.md").write_text("Write code.")

    result = subprocess.run(
        [sys.executable, "-m", "shesha.prompts", "--prompts-dir", str(prompts_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "system.md" in result.stdout or "system.md" in result.stderr
