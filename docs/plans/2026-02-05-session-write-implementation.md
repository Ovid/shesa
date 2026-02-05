# Session Write Feature Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `write` command to save session transcripts as markdown files from interactive example scripts.

**Architecture:** Add shared utilities to `examples/script_utils.py` for write command parsing, filename generation, and markdown formatting. Integrate into both `repo.py` and `barsoom.py` interactive loops.

**Tech Stack:** Python pathlib, datetime for timestamps, existing script_utils module pattern.

---

### Task 1: Add `is_write_command` function

**Files:**
- Test: `tests/unit/test_script_utils.py`
- Modify: `examples/script_utils.py`

**Step 1: Write the failing tests**

Add to `tests/unit/test_script_utils.py`:

```python
class TestIsWriteCommand:
    """Tests for is_write_command function."""

    def test_write_alone_is_write_command(self) -> None:
        """'write' by itself should be recognized."""
        from examples.script_utils import is_write_command

        assert is_write_command("write")
        assert is_write_command("WRITE")
        assert is_write_command("Write")

    def test_write_with_filename_is_write_command(self) -> None:
        """'write <filename>' should be recognized."""
        from examples.script_utils import is_write_command

        assert is_write_command("write myfile.md")
        assert is_write_command("write path/to/file.md")
        assert is_write_command("WRITE session.md")

    def test_other_not_write_command(self) -> None:
        """Other inputs should not be write commands."""
        from examples.script_utils import is_write_command

        assert not is_write_command("hello")
        assert not is_write_command("writeup")
        assert not is_write_command("rewrite")
        assert not is_write_command("")
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_script_utils.py::TestIsWriteCommand -v`
Expected: FAIL with ImportError (is_write_command not found)

**Step 3: Write minimal implementation**

Add to `examples/script_utils.py`:

```python
def is_write_command(user_input: str) -> bool:
    """Check if user input is a write command.

    Args:
        user_input: The user's input string.

    Returns:
        True if the input is 'write' or 'write <filename>'.
    """
    lower = user_input.lower()
    return lower == "write" or lower.startswith("write ")
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_script_utils.py::TestIsWriteCommand -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_script_utils.py examples/script_utils.py
git commit -m "feat(examples): add is_write_command function"
```

---

### Task 2: Add `parse_write_command` function

**Files:**
- Test: `tests/unit/test_script_utils.py`
- Modify: `examples/script_utils.py`

**Step 1: Write the failing tests**

Add to `tests/unit/test_script_utils.py`:

```python
class TestParseWriteCommand:
    """Tests for parse_write_command function."""

    def test_write_alone_returns_none(self) -> None:
        """'write' by itself returns None (auto-generate filename)."""
        from examples.script_utils import parse_write_command

        assert parse_write_command("write") is None
        assert parse_write_command("WRITE") is None

    def test_write_with_filename_returns_filename(self) -> None:
        """'write <filename>' returns the filename."""
        from examples.script_utils import parse_write_command

        assert parse_write_command("write myfile.md") == "myfile.md"
        assert parse_write_command("write path/to/file.md") == "path/to/file.md"

    def test_strips_whitespace_from_filename(self) -> None:
        """Whitespace around filename should be stripped."""
        from examples.script_utils import parse_write_command

        assert parse_write_command("write   myfile.md   ") == "myfile.md"
        assert parse_write_command("WRITE    session.md") == "session.md"

    def test_adds_md_extension_if_missing(self) -> None:
        """Add .md extension if not present."""
        from examples.script_utils import parse_write_command

        assert parse_write_command("write myfile") == "myfile.md"
        assert parse_write_command("write path/to/file") == "path/to/file.md"

    def test_preserves_md_extension(self) -> None:
        """Don't double-add .md extension."""
        from examples.script_utils import parse_write_command

        assert parse_write_command("write myfile.md") == "myfile.md"
        assert parse_write_command("write FILE.MD") == "FILE.MD"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_script_utils.py::TestParseWriteCommand -v`
Expected: FAIL with ImportError (parse_write_command not found)

**Step 3: Write minimal implementation**

Add to `examples/script_utils.py`:

```python
def parse_write_command(user_input: str) -> str | None:
    """Parse write command and extract filename.

    Args:
        user_input: The user's input string (already confirmed as write command).

    Returns:
        The filename with .md extension, or None for auto-generate.
    """
    parts = user_input.split(maxsplit=1)
    if len(parts) == 1:
        return None

    filename = parts[1].strip()
    if not filename.lower().endswith(".md"):
        filename = filename + ".md"
    return filename
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_script_utils.py::TestParseWriteCommand -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_script_utils.py examples/script_utils.py
git commit -m "feat(examples): add parse_write_command function"
```

---

### Task 3: Add `generate_session_filename` function

**Files:**
- Test: `tests/unit/test_script_utils.py`
- Modify: `examples/script_utils.py`

**Step 1: Write the failing tests**

Add to `tests/unit/test_script_utils.py`:

```python
import re


class TestGenerateSessionFilename:
    """Tests for generate_session_filename function."""

    def test_filename_format(self) -> None:
        """Filename should match session-YYYY-MM-DD-HHMMSS.md pattern."""
        from examples.script_utils import generate_session_filename

        filename = generate_session_filename()
        pattern = r"^session-\d{4}-\d{2}-\d{2}-\d{6}\.md$"
        assert re.match(pattern, filename), f"'{filename}' doesn't match expected pattern"

    def test_filename_has_md_extension(self) -> None:
        """Filename should end with .md."""
        from examples.script_utils import generate_session_filename

        filename = generate_session_filename()
        assert filename.endswith(".md")

    def test_filename_starts_with_session(self) -> None:
        """Filename should start with 'session-'."""
        from examples.script_utils import generate_session_filename

        filename = generate_session_filename()
        assert filename.startswith("session-")
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_script_utils.py::TestGenerateSessionFilename -v`
Expected: FAIL with ImportError (generate_session_filename not found)

**Step 3: Write minimal implementation**

Add import at top of `examples/script_utils.py`:

```python
from datetime import datetime
```

Add function:

```python
def generate_session_filename() -> str:
    """Generate a timestamped session filename.

    Returns:
        Filename like 'session-2026-02-05-143022.md'.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    return f"session-{timestamp}.md"
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_script_utils.py::TestGenerateSessionFilename -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_script_utils.py examples/script_utils.py
git commit -m "feat(examples): add generate_session_filename function"
```

---

### Task 4: Add `format_session_transcript` function

**Files:**
- Test: `tests/unit/test_script_utils.py`
- Modify: `examples/script_utils.py`

**Step 1: Write the failing tests**

Add to `tests/unit/test_script_utils.py`:

```python
class TestFormatSessionTranscript:
    """Tests for format_session_transcript function."""

    def test_empty_history(self) -> None:
        """Empty history should still produce valid markdown with header."""
        from examples.script_utils import format_session_transcript

        result = format_session_transcript([], "test-project")
        assert "# Session Transcript" in result
        assert "**Project:** test-project" in result
        assert "**Exchanges:** 0" in result

    def test_single_exchange(self) -> None:
        """Single exchange should be formatted correctly."""
        from examples.script_utils import format_session_transcript

        history = [("What is X?", "X is a variable.")]
        result = format_session_transcript(history, "my-project")

        assert "# Session Transcript" in result
        assert "**Project:** my-project" in result
        assert "**Exchanges:** 1" in result
        assert "**User:** What is X?" in result
        assert "X is a variable." in result

    def test_multiple_exchanges(self) -> None:
        """Multiple exchanges should be separated by horizontal rules."""
        from examples.script_utils import format_session_transcript

        history = [("Q1?", "A1."), ("Q2?", "A2.")]
        result = format_session_transcript(history, "project")

        assert "**Exchanges:** 2" in result
        assert "**User:** Q1?" in result
        assert "A1." in result
        assert "**User:** Q2?" in result
        assert "A2." in result
        # Should have separators between exchanges
        assert result.count("---") >= 2

    def test_includes_date(self) -> None:
        """Transcript should include a date field."""
        from examples.script_utils import format_session_transcript

        result = format_session_transcript([], "project")
        assert "**Date:**" in result
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_script_utils.py::TestFormatSessionTranscript -v`
Expected: FAIL with ImportError (format_session_transcript not found)

**Step 3: Write minimal implementation**

Add to `examples/script_utils.py`:

```python
def format_session_transcript(history: list[tuple[str, str]], project_name: str) -> str:
    """Format conversation history as a markdown transcript.

    Args:
        history: List of (question, answer) tuples.
        project_name: Name or URL of the project for metadata.

    Returns:
        Formatted markdown string.
    """
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# Session Transcript",
        "",
        f"- **Date:** {date_str}",
        f"- **Project:** {project_name}",
        f"- **Exchanges:** {len(history)}",
        "",
        "---",
    ]

    for question, answer in history:
        lines.extend([
            "",
            f"**User:** {question}",
            "",
            answer,
            "",
            "---",
        ])

    return "\n".join(lines)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_script_utils.py::TestFormatSessionTranscript -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_script_utils.py examples/script_utils.py
git commit -m "feat(examples): add format_session_transcript function"
```

---

### Task 5: Add `write_session` function

**Files:**
- Test: `tests/unit/test_script_utils.py`
- Modify: `examples/script_utils.py`

**Step 1: Write the failing tests**

Add to `tests/unit/test_script_utils.py`:

```python
from pathlib import Path


class TestWriteSession:
    """Tests for write_session function."""

    def test_writes_file_to_specified_path(self, tmp_path: Path) -> None:
        """Should write transcript to specified filename."""
        from examples.script_utils import write_session

        history = [("Q?", "A.")]
        filepath = tmp_path / "test.md"

        result = write_session(history, "project", str(filepath))

        assert result == str(filepath)
        assert filepath.exists()
        content = filepath.read_text()
        assert "**User:** Q?" in content

    def test_auto_generates_filename(self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
        """Should auto-generate filename when None provided."""
        from examples import script_utils
        from examples.script_utils import write_session

        # Change to tmp_path for the test
        monkeypatch.chdir(tmp_path)

        history = [("Q?", "A.")]
        result = write_session(history, "project", None)

        assert result.startswith("session-")
        assert result.endswith(".md")
        assert Path(result).exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create parent directories if they don't exist."""
        from examples.script_utils import write_session

        history = [("Q?", "A.")]
        filepath = tmp_path / "subdir" / "nested" / "test.md"

        result = write_session(history, "project", str(filepath))

        assert filepath.exists()

    def test_returns_path_written(self, tmp_path: Path) -> None:
        """Should return the path that was written to."""
        from examples.script_utils import write_session

        history = [("Q?", "A.")]
        filepath = tmp_path / "output.md"

        result = write_session(history, "project", str(filepath))

        assert result == str(filepath)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_script_utils.py::TestWriteSession -v`
Expected: FAIL with ImportError (write_session not found)

**Step 3: Write minimal implementation**

Add import at top of `examples/script_utils.py` (if not already present):

```python
from pathlib import Path
```

Add function:

```python
def write_session(
    history: list[tuple[str, str]],
    project_name: str,
    filename: str | None
) -> str:
    """Write session transcript to a markdown file.

    Args:
        history: List of (question, answer) tuples.
        project_name: Name or URL of the project for metadata.
        filename: Output filename, or None to auto-generate.

    Returns:
        The path that was written to.

    Raises:
        OSError: If file cannot be written.
    """
    if filename is None:
        filename = generate_session_filename()

    filepath = Path(filename)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    content = format_session_transcript(history, project_name)
    filepath.write_text(content)

    return str(filepath)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_script_utils.py::TestWriteSession -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_script_utils.py examples/script_utils.py
git commit -m "feat(examples): add write_session function"
```

---

### Task 6: Integrate write command into `barsoom.py`

**Files:**
- Test: `tests/examples/test_barsoom.py`
- Modify: `examples/barsoom.py`

**Step 1: Check existing tests and add integration test**

First read `tests/examples/test_barsoom.py` to understand the test structure, then add:

```python
class TestWriteCommand:
    """Tests for write command in barsoom interactive loop."""

    def test_write_command_recognized(self) -> None:
        """Write command should not be treated as a query."""
        from examples.script_utils import is_write_command

        assert is_write_command("write")
        assert is_write_command("write session.md")
```

**Step 2: Run tests to verify baseline**

Run: `pytest tests/examples/test_barsoom.py -v`
Expected: PASS (existing tests should pass)

**Step 3: Update imports in barsoom.py**

Update the import blocks in `examples/barsoom.py`. In the `if __name__ == "__main__":` block:

```python
if __name__ == "__main__":
    from script_utils import (
        ThinkingSpinner,
        format_history_prefix,
        format_progress,
        format_stats,
        format_thought_time,
        install_urllib3_cleanup_hook,
        is_exit_command,
        is_write_command,
        parse_write_command,
        should_warn_history_size,
        write_session,
    )
else:
    from .script_utils import (
        ThinkingSpinner,
        format_history_prefix,
        format_progress,
        format_stats,
        format_thought_time,
        install_urllib3_cleanup_hook,
        is_exit_command,
        is_write_command,
        parse_write_command,
        should_warn_history_size,
        write_session,
    )
```

**Step 4: Add write command handling in interactive loop**

In the `main()` function, find the interactive loop (starts around line 261 with `while True:`). After the `is_exit_command` check (around line 271-273), add:

```python
        if is_write_command(user_input):
            if not history:
                print("Nothing to save - no exchanges yet.")
                print()
                continue
            try:
                filename = parse_write_command(user_input)
                path = write_session(history, PROJECT_NAME, filename)
                print(f"Session saved to {path} ({len(history)} exchanges)")
            except OSError as e:
                print(f"Error saving session: {e}")
            print()
            continue
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/examples/test_barsoom.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add examples/barsoom.py tests/examples/test_barsoom.py
git commit -m "feat(examples): add write command to barsoom.py"
```

---

### Task 7: Integrate write command into `repo.py`

**Files:**
- Test: `tests/unit/test_repo_script.py`
- Modify: `examples/repo.py`

**Step 1: Update imports in repo.py**

Update the import blocks in `examples/repo.py`. In the `if __name__ == "__main__":` block:

```python
if __name__ == "__main__":
    from script_utils import (
        ThinkingSpinner,
        format_history_prefix,
        format_progress,
        format_stats,
        format_thought_time,
        install_urllib3_cleanup_hook,
        is_exit_command,
        is_write_command,
        parse_write_command,
        should_warn_history_size,
        write_session,
    )
else:
    from .script_utils import (
        ThinkingSpinner,
        format_history_prefix,
        format_progress,
        format_stats,
        format_thought_time,
        install_urllib3_cleanup_hook,
        is_exit_command,
        is_write_command,
        parse_write_command,
        should_warn_history_size,
        write_session,
    )
```

**Step 2: Add project_name parameter to run_interactive_loop**

Update the function signature:

```python
def run_interactive_loop(project: Project, verbose: bool, project_name: str) -> None:
```

Update the docstring Args section to include:

```python
        project_name: Name or URL of the project for session transcript metadata.
```

**Step 3: Add write command handling in run_interactive_loop**

In `run_interactive_loop`, after the `is_exit_command` check (around line 317-319), add:

```python
        if is_write_command(user_input):
            if not history:
                print("Nothing to save - no exchanges yet.")
                print()
                continue
            try:
                filename = parse_write_command(user_input)
                path = write_session(history, project_name, filename)
                print(f"Session saved to {path} ({len(history)} exchanges)")
            except OSError as e:
                print(f"Error saving session: {e}")
            print()
            continue
```

**Step 4: Update call sites to pass project_name**

Find the call to `run_interactive_loop` in `main()` (around line 464). The project name varies:
- For URL-based repos: use `repo_url`
- For picker-selected projects: use `project_name`

Update the main function to track the project name and pass it:

Near the end of `main()`, before calling `run_interactive_loop`, determine the project name:

```python
    # Determine project name for transcript metadata
    if 'project_name' in dir() and project_name:
        display_name = project_name
    elif 'repo_url' in dir() and repo_url:
        display_name = repo_url
    else:
        display_name = project.project_id

    # Enter interactive loop
    run_interactive_loop(project, args.verbose, display_name)
```

Actually, looking at the code flow more carefully:
- When user selects from picker: `project_name = picker_result[0]` is set
- When user provides URL/path: `repo_url` is set

Simpler approach - just use `project.project_id` which is always available:

```python
    # Enter interactive loop
    run_interactive_loop(project, args.verbose, project.project_id)
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_repo_script.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add examples/repo.py
git commit -m "feat(examples): add write command to repo.py"
```

---

### Task 8: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Read current changelog**

Read the file to see the current format.

**Step 2: Add entry under [Unreleased]**

Add under the `## [Unreleased]` section:

```markdown
### Added

- Session write command (`write` or `write <filename>`) in example scripts (`repo.py`, `barsoom.py`) to save conversation transcripts as markdown files
```

**Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add changelog entry for session write feature"
```

---

### Task 9: Final verification

**Step 1: Run full test suite**

Run: `make all`
Expected: All checks pass (format, lint, typecheck, test)

**Step 2: Manual smoke test (optional)**

If desired, manually test with:

```bash
python examples/barsoom.py --prompt "Who is John Carter?"
# Then in a real session, type "write" to test
```

---

Plan complete and saved to `docs/plans/2026-02-05-session-write-implementation.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
