# /write Overwrite Protection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent `/write` from silently overwriting existing files; require trailing `!` to force overwrite.

**Architecture:** All logic lives in `_cmd_write()` in `app.py`. Parse `!` suffix as force flag, check `Path.exists()` before writing, resolve actual on-disk filename for case-insensitive collision messages. `session.py` unchanged.

**Tech Stack:** Python pathlib, Textual TUI, pytest

---

### Task 1: Test force flag parsing

**Files:**
- Test: `tests/unit/tui/test_app.py`

**Step 1: Write the failing test**

Add to `tests/unit/tui/test_app.py`:

```python
class TestWriteOverwriteProtection:
    """Tests for /write overwrite protection."""

    async def test_write_force_flag_strips_bang(self) -> None:
        """The ! suffix is stripped from filename before writing."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            # Add an exchange so /write has something to save
            pilot.app._session.add_exchange("q", "a", "s")
            with patch.object(pilot.app._session, "write_transcript", return_value="notes.md") as mock_write:
                pilot.app._cmd_write("notes!")
                mock_write.assert_called_once_with("notes.md")

    async def test_write_force_flag_with_md_extension(self) -> None:
        """The ! suffix works when .md extension is already present."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            pilot.app._session.add_exchange("q", "a", "s")
            with patch.object(pilot.app._session, "write_transcript", return_value="notes.md") as mock_write:
                pilot.app._cmd_write("notes.md!")
                mock_write.assert_called_once_with("notes.md")
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/tui/test_app.py::TestWriteOverwriteProtection -v`
Expected: FAIL — current `_cmd_write` doesn't strip `!`, so filename includes it.

**Step 3: Implement force flag parsing in `_cmd_write`**

Modify `src/shesha/tui/app.py` `_cmd_write` method (lines 493-507). Replace the current implementation with:

```python
def _cmd_write(self, args: str) -> None:
    """Save session transcript."""
    if self._session.exchange_count == 0:
        self.query_one(OutputArea).add_system_message("Nothing to save - no exchanges yet.")
        return

    raw_args = args.strip()

    # Parse force flag (trailing !)
    force = raw_args.endswith("!")
    if force:
        raw_args = raw_args[:-1].rstrip()

    filename = raw_args or None
    if filename and not filename.lower().endswith(".md"):
        filename = filename + ".md"

    # Check for existing file
    if filename is not None:
        filepath = Path(filename)
        if filepath.exists() and not force:
            # Resolve actual on-disk name (handles case-insensitive filesystems)
            parent = filepath.parent or Path(".")
            actual = next(
                (p for p in parent.iterdir() if p.name.lower() == filepath.name.lower()),
                filepath,
            )
            self.query_one(OutputArea).add_system_message(
                f"File {actual.name} already exists. Use /write {raw_args}! to overwrite."
            )
            return
    else:
        # Auto-generated filename — still check for collision
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        auto_name = f"session-{timestamp}.md"
        filepath = Path(auto_name)
        if filepath.exists():
            self.query_one(OutputArea).add_system_message(
                f"File {auto_name} already exists. Use /write {auto_name}! to overwrite."
            )
            return

    try:
        path = self._session.write_transcript(filename)
        self.query_one(OutputArea).add_system_message(
            f"Session saved to {path} ({self._session.exchange_count} exchanges)"
        )
    except OSError as e:
        self.query_one(OutputArea).add_system_message(f"Error saving: {e}")
```

Note: `Path` is already imported in `app.py`. The `datetime` import for auto-generated names is placed inline since it's only used in that branch — add a comment explaining why if the project style requires it, or move it to the top of the file alongside the existing imports.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/tui/test_app.py::TestWriteOverwriteProtection -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/tui/test_app.py src/shesha/tui/app.py
git commit -m "feat: parse ! force flag in /write command"
```

---

### Task 2: Test existence check blocks write

**Files:**
- Test: `tests/unit/tui/test_app.py`

**Step 1: Write the failing test**

Add to `TestWriteOverwriteProtection` in `tests/unit/tui/test_app.py`:

```python
    async def test_write_blocked_when_file_exists(self, tmp_path: object) -> None:
        """Writing is blocked when target file already exists."""
        from pathlib import Path as P

        tmp = P(str(tmp_path))
        existing = tmp / "notes.md"
        existing.write_text("important content")

        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            pilot.app._session.add_exchange("q", "a", "s")
            with patch.object(pilot.app._session, "write_transcript") as mock_write:
                pilot.app._cmd_write(str(existing))
                mock_write.assert_not_called()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("already exists" in t for t in texts)

        # Original file untouched
        assert existing.read_text() == "important content"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/tui/test_app.py::TestWriteOverwriteProtection::test_write_blocked_when_file_exists -v`
Expected: PASS (implementation from Task 1 should already handle this).

If it already passes, that confirms our Task 1 implementation is correct. Move on.

**Step 3: Commit**

```bash
git add tests/unit/tui/test_app.py
git commit -m "test: verify /write blocks on existing file"
```

---

### Task 3: Test force flag bypasses existence check

**Files:**
- Test: `tests/unit/tui/test_app.py`

**Step 1: Write the failing test**

Add to `TestWriteOverwriteProtection`:

```python
    async def test_write_force_overwrites_existing(self, tmp_path: object) -> None:
        """Force flag (!) allows overwriting an existing file."""
        from pathlib import Path as P

        tmp = P(str(tmp_path))
        existing = tmp / "notes.md"
        existing.write_text("old content")

        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            pilot.app._session.add_exchange("q", "a", "s")
            with patch.object(
                pilot.app._session, "write_transcript", return_value=str(existing)
            ) as mock_write:
                pilot.app._cmd_write(f"{existing}!")
                mock_write.assert_called_once_with(str(existing))
```

**Step 2: Run test to verify it passes**

Run: `pytest tests/unit/tui/test_app.py::TestWriteOverwriteProtection::test_write_force_overwrites_existing -v`
Expected: PASS (Task 1 implementation handles this).

**Step 3: Commit**

```bash
git add tests/unit/tui/test_app.py
git commit -m "test: verify /write ! flag bypasses overwrite protection"
```

---

### Task 4: Test case-insensitive collision shows actual filename

**Files:**
- Test: `tests/unit/tui/test_app.py`

**Step 1: Write the failing test**

Add to `TestWriteOverwriteProtection`:

```python
    async def test_write_shows_actual_filename_on_collision(self, tmp_path: object) -> None:
        """Collision message shows actual on-disk filename (e.g., SECURITY.md not security.md)."""
        from pathlib import Path as P

        tmp = P(str(tmp_path))
        existing = tmp / "NOTES.md"
        existing.write_text("important")

        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            pilot.app._session.add_exchange("q", "a", "s")
            # Try to write "notes.md" (lowercase) — should detect NOTES.md
            target = str(tmp / "notes")
            pilot.app._cmd_write(target)
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            msg = next(t for t in texts if "already exists" in t)
            # On case-insensitive FS (macOS): shows "NOTES.md"
            # On case-sensitive FS (Linux): file won't exist, so write proceeds
            # This test validates whichever behavior the OS provides
            if (tmp / "notes.md").exists():
                # Case-insensitive FS — should show actual name
                assert "NOTES.md" in msg
```

Note: This test is filesystem-dependent. On case-insensitive filesystems (macOS APFS), `Path("notes.md").exists()` returns True when `NOTES.md` exists and the test validates the actual filename is shown. On case-sensitive filesystems (Linux ext4), the file won't collide at all and the write proceeds normally, so we guard the assertion.

**Step 2: Run test**

Run: `pytest tests/unit/tui/test_app.py::TestWriteOverwriteProtection::test_write_shows_actual_filename_on_collision -v`
Expected: PASS on macOS; test is a no-op on case-sensitive Linux.

**Step 3: Commit**

```bash
git add tests/unit/tui/test_app.py
git commit -m "test: verify case-insensitive collision shows actual filename"
```

---

### Task 5: Test auto-generated filename collision

**Files:**
- Test: `tests/unit/tui/test_app.py`

**Step 1: Write the failing test**

Add to `TestWriteOverwriteProtection`:

```python
    async def test_write_auto_name_blocked_when_exists(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Auto-generated filename is blocked if a file with that name exists."""
        from pathlib import Path as P
        from unittest.mock import patch as mock_patch

        tmp = P(str(tmp_path))
        monkeypatch.chdir(tmp)

        # Pre-create the file that the auto-name would generate
        auto_file = tmp / "session-2026-01-01-120000.md"
        auto_file.write_text("old session")

        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            pilot.app._session.add_exchange("q", "a", "s")
            # Mock datetime so auto-name matches existing file
            with mock_patch("shesha.tui.app.datetime") as mock_dt:
                mock_dt.now.return_value.strftime.return_value = "2026-01-01-120000"
                with patch.object(pilot.app._session, "write_transcript") as mock_write:
                    pilot.app._cmd_write("")
                    mock_write.assert_not_called()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("already exists" in t for t in texts)
            assert any("session-2026-01-01-120000.md" in t for t in texts)
```

Note: The `datetime` import needs to be at the top of `app.py` (not inline) for this mock to work. Move it there in the implementation.

**Step 2: Run test to verify it fails or passes**

Run: `pytest tests/unit/tui/test_app.py::TestWriteOverwriteProtection::test_write_auto_name_blocked_when_exists -v`

If the inline `datetime` import causes the mock to miss, adjust the import location (see step 3).

**Step 3: Ensure `datetime` is imported at module level in `app.py`**

Add at the top of `src/shesha/tui/app.py` with the other imports:

```python
from datetime import datetime
```

And in `_cmd_write`, use `datetime.now()` directly (no inline import).

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/tui/test_app.py::TestWriteOverwriteProtection::test_write_auto_name_blocked_when_exists -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/tui/test_app.py src/shesha/tui/app.py
git commit -m "test: verify auto-generated filename collision is blocked"
```

---

### Task 6: Run full test suite and lint

**Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: All pass.

**Step 2: Run type checker and linter**

Run: `mypy src/shesha && ruff check src tests && ruff format --check src tests`
Expected: Clean.

**Step 3: Fix any issues found**

If any failures, fix and re-run.

**Step 4: Commit any fixes**

```bash
git add -u
git commit -m "fix: address lint/type issues from overwrite protection"
```

---

### Task 7: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add entry under `[Unreleased]`**

Under `### Fixed` (or create it):

```markdown
### Fixed
- `/write` command now warns before overwriting existing files; use `/write filename!` to force overwrite
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add changelog entry for /write overwrite protection"
```
