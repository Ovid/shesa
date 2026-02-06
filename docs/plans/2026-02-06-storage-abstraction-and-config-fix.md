# Storage Abstraction & Configuration Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix two architectural flaws: (1) Remove `FilesystemStorage` special-casing from `Project.query()`, `RLMEngine`, and `TraceWriter` by adding trace methods to the `StorageBackend` protocol; (2) Make `Shesha.__init__` use `SheshaConfig.load()` and plumb `max_traces_per_project` through to `cleanup_old_traces`.

**Architecture:** Add `get_traces_dir()` and `list_traces()` to `StorageBackend` protocol. Change `TraceWriter`/`IncrementalTraceWriter` to accept `StorageBackend` instead of `FilesystemStorage`. Remove `isinstance` check from `Project.query()` — just pass `self._storage` directly. For config: default `Shesha.__init__` to `SheshaConfig.load()`, pass `max_traces_per_project` through `RLMEngine` to `cleanup_old_traces`.

**Tech Stack:** Python, pytest, mypy

---

### Task 1: Add trace methods to StorageBackend protocol

**Files:**
- Modify: `src/shesha/storage/base.py` (add `get_traces_dir` and `list_traces` to protocol)
- Test: `tests/unit/storage/test_filesystem.py` (existing tests already cover these methods)

**Step 1: Write the failing test**

Add a test in `tests/unit/storage/test_filesystem.py` that verifies `FilesystemStorage` satisfies the `StorageBackend` protocol including the new trace methods. This test is just a type-conformance check — the real behavioral tests already exist.

No new test needed — existing `test_get_traces_dir_creates_directory` and `test_list_traces_*` tests already confirm `FilesystemStorage` has these methods. We just need to add them to the protocol.

**Step 2: Add trace methods to StorageBackend protocol**

In `src/shesha/storage/base.py`, add these methods to the `StorageBackend` protocol:

```python
def get_traces_dir(self, project_id: str) -> Path:
    """Get the traces directory for a project, creating it if needed."""
    ...

def list_traces(self, project_id: str) -> list[Path]:
    """List all trace files in a project, sorted by name (oldest first)."""
    ...
```

**Step 3: Run tests to verify nothing breaks**

Run: `pytest tests/unit/storage/ -v`
Expected: PASS (FilesystemStorage already implements these methods)

**Step 4: Run type checker**

Run: `mypy src/shesha/storage/`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/storage/base.py
git commit -m "feat(storage): add trace methods to StorageBackend protocol"
```

---

### Task 2: Change TraceWriter and IncrementalTraceWriter to use StorageBackend

**Files:**
- Modify: `src/shesha/rlm/trace_writer.py` (change type from `FilesystemStorage` to `StorageBackend`)
- Modify: `tests/unit/rlm/test_trace_writer.py` (update type annotations in fixtures)

**Step 1: Write the failing test**

Add a test that constructs `TraceWriter` with a mock `StorageBackend` (not `FilesystemStorage`) and verifies it works:

```python
class TestTraceWriterWithProtocol:
    """TraceWriter works with any StorageBackend, not just FilesystemStorage."""

    def test_trace_writer_accepts_storage_backend(self, tmp_path: Path) -> None:
        """TraceWriter accepts any StorageBackend implementation."""
        from shesha.storage.filesystem import FilesystemStorage

        storage: StorageBackend = FilesystemStorage(root_path=tmp_path)
        storage.create_project("test-project")

        from shesha.rlm.trace_writer import TraceWriter

        # This should work without needing FilesystemStorage specifically
        writer = TraceWriter(storage)
        assert writer.storage is storage
```

Run: `pytest tests/unit/rlm/test_trace_writer.py::TestTraceWriterWithProtocol -v`
Expected: FAIL because `TraceWriter.__init__` type-hints `FilesystemStorage`

Note: This is really a mypy-level test. The runtime won't fail because Python is duck-typed. But the important change is making the type annotation correct.

**Step 2: Update trace_writer.py to use StorageBackend**

In `src/shesha/rlm/trace_writer.py`:
- Change `from shesha.storage.filesystem import FilesystemStorage` to `from shesha.storage.base import StorageBackend`
- Change `TraceWriter.__init__(self, storage: FilesystemStorage, ...)` to `TraceWriter.__init__(self, storage: StorageBackend, ...)`
- Change `IncrementalTraceWriter.__init__(self, storage: FilesystemStorage, ...)` to `IncrementalTraceWriter.__init__(self, storage: StorageBackend, ...)`

**Step 3: Run tests**

Run: `pytest tests/unit/rlm/test_trace_writer.py -v`
Expected: PASS (all existing tests should still pass — `FilesystemStorage` satisfies `StorageBackend`)

**Step 4: Run type checker**

Run: `mypy src/shesha/rlm/trace_writer.py`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/rlm/trace_writer.py
git commit -m "refactor(trace): TraceWriter accepts StorageBackend protocol instead of FilesystemStorage"
```

---

### Task 3: Change RLMEngine.query() to accept StorageBackend

**Files:**
- Modify: `src/shesha/rlm/engine.py` (change `storage: FilesystemStorage | None` to `storage: StorageBackend | None`)
- Modify: `tests/unit/rlm/test_engine.py` (existing tests use `FilesystemStorage` — they still pass, but update type annotations)

**Step 1: Write a failing test**

Add a test to `tests/unit/rlm/test_engine.py` that passes a mock `StorageBackend` to `engine.query()`:

```python
def test_engine_query_accepts_storage_backend(self, ...):
    """engine.query() accepts any StorageBackend, not just FilesystemStorage."""
```

This is a mypy-level change. At runtime it already works because of duck typing.

**Step 2: Update engine.py**

In `src/shesha/rlm/engine.py`:
- Change `from shesha.storage.filesystem import FilesystemStorage` to `from shesha.storage.base import StorageBackend`
- Change `storage: FilesystemStorage | None = None` to `storage: StorageBackend | None = None`

**Step 3: Run tests**

Run: `pytest tests/unit/rlm/test_engine.py -v`
Expected: PASS

**Step 4: Run type checker**

Run: `mypy src/shesha/rlm/engine.py`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/rlm/engine.py
git commit -m "refactor(engine): RLMEngine.query() accepts StorageBackend protocol"
```

---

### Task 4: Remove isinstance check from Project.query()

**Files:**
- Modify: `src/shesha/project.py` (remove `isinstance` check and `FilesystemStorage` import)
- Modify: `tests/unit/test_project.py` (update tests — remove special-case tests, add simpler "storage is always passed" test)

**Step 1: Write the failing test**

Replace the two existing tests (`test_query_passes_none_storage_for_non_filesystem_backend` and `test_query_passes_filesystem_storage_for_tracing`) with a single test:

```python
def test_query_passes_storage_to_engine(
    self, mock_storage: MagicMock, mock_registry: MagicMock
):
    """Query always passes storage to engine regardless of backend type."""
    mock_engine = MagicMock()
    mock_engine.query.return_value = MagicMock(answer="test answer")

    mock_storage.load_all_documents.return_value = [
        ParsedDocument(
            name="doc.txt",
            content="doc content",
            format="txt",
            metadata={},
            char_count=11,
            parse_warnings=[],
        )
    ]

    project = Project(
        project_id="test-project",
        storage=mock_storage,
        parser_registry=mock_registry,
        rlm_engine=mock_engine,
    )

    project.query("test question")

    call_kwargs = mock_engine.query.call_args.kwargs
    assert call_kwargs.get("storage") is mock_storage
    assert call_kwargs.get("project_id") == "test-project"
```

Run: `pytest tests/unit/test_project.py::TestProject::test_query_passes_storage_to_engine -v`
Expected: FAIL because `Project.query()` still does the isinstance check and passes `None` for non-FilesystemStorage

**Step 2: Update Project.query()**

In `src/shesha/project.py`:
- Remove `from shesha.storage.filesystem import FilesystemStorage` import
- Replace:
  ```python
  fs_storage = self._storage if isinstance(self._storage, FilesystemStorage) else None
  ```
  With just:
  ```python
  ```
  (remove it entirely)
- Change `storage=fs_storage` to `storage=self._storage` in the `self._rlm_engine.query()` call

**Step 3: Remove old tests, verify new test passes**

Remove `test_query_passes_none_storage_for_non_filesystem_backend` and `test_query_passes_filesystem_storage_for_tracing` from `tests/unit/test_project.py`.

Run: `pytest tests/unit/test_project.py -v`
Expected: PASS

**Step 4: Run full test suite**

Run: `pytest tests/unit/ -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/project.py tests/unit/test_project.py
git commit -m "refactor(project): remove FilesystemStorage special-casing from Project.query()"
```

---

### Task 5: Make Shesha.__init__ use SheshaConfig.load()

**Files:**
- Modify: `src/shesha/shesha.py` (change default from `SheshaConfig()` to `SheshaConfig.load()`)
- Modify: `tests/unit/test_shesha.py` (update shesha_instance fixture, add test for env var config)

**Step 1: Write the failing test**

Add a test that verifies `Shesha` picks up env vars without explicit config:

```python
def test_shesha_uses_config_load_by_default(self, tmp_path: Path):
    """Shesha uses SheshaConfig.load() by default, picking up env vars."""
    import os
    from unittest.mock import patch as mock_patch

    with (
        mock_patch("shesha.shesha.docker"),
        mock_patch("shesha.shesha.ContainerPool"),
        mock_patch.dict(os.environ, {"SHESHA_MAX_ITERATIONS": "99"}),
    ):
        shesha = Shesha(storage_path=tmp_path)
        assert shesha._config.max_iterations == 99
```

Run: `pytest tests/unit/test_shesha.py::TestShesha::test_shesha_uses_config_load_by_default -v`
Expected: FAIL because `Shesha.__init__` uses `SheshaConfig()` which ignores env vars

**Step 2: Update Shesha.__init__**

In `src/shesha/shesha.py`, change line 51:
```python
# Before:
config = SheshaConfig()
# After:
config = SheshaConfig.load()
```

**Step 3: Run tests**

Run: `pytest tests/unit/test_shesha.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/shesha/shesha.py tests/unit/test_shesha.py
git commit -m "fix(config): Shesha.__init__ uses SheshaConfig.load() to honor env vars and config files"
```

---

### Task 6: Plumb max_traces_per_project through to cleanup_old_traces

**Files:**
- Modify: `src/shesha/rlm/engine.py` (add `max_traces_per_project` param, pass to cleanup)
- Modify: `src/shesha/shesha.py` (pass `config.max_traces_per_project` to engine)
- Modify: `tests/unit/rlm/test_engine.py` (add test for max_traces plumbing)

**Step 1: Write the failing test**

```python
class TestEngineMaxTracesConfig:
    """Tests for max_traces_per_project plumbing."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_passes_max_traces_to_cleanup(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Engine passes max_traces_per_project to cleanup_old_traces."""
        from shesha.storage.filesystem import FilesystemStorage

        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("test-project")

        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content="```repl\nFINAL('answer')\n```",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )
        mock_executor_cls.return_value = mock_executor

        with patch("shesha.rlm.engine.TraceWriter") as mock_writer_cls:
            mock_writer = MagicMock()
            mock_writer_cls.return_value = mock_writer

            engine = RLMEngine(model="test-model", max_traces_per_project=25)
            engine.query(
                documents=["doc content"],
                question="What?",
                storage=storage,
                project_id="test-project",
            )

            mock_writer.cleanup_old_traces.assert_called_once_with(
                "test-project", max_count=25
            )
```

Run: `pytest tests/unit/rlm/test_engine.py::TestEngineMaxTracesConfig -v`
Expected: FAIL because `RLMEngine` doesn't accept `max_traces_per_project`

**Step 2: Add max_traces_per_project to RLMEngine**

In `src/shesha/rlm/engine.py`:
- Add `max_traces_per_project: int = 50` param to `__init__`
- Store as `self.max_traces_per_project = max_traces_per_project`
- Change line 200 from:
  ```python
  TraceWriter(storage, suppress_errors=True).cleanup_old_traces(project_id)
  ```
  To:
  ```python
  TraceWriter(storage, suppress_errors=True).cleanup_old_traces(
      project_id, max_count=self.max_traces_per_project
  )
  ```

**Step 3: Pass config value from Shesha to RLMEngine**

In `src/shesha/shesha.py`, add `max_traces_per_project` to the `RLMEngine` constructor call:
```python
self._rlm_engine = RLMEngine(
    model=config.model,
    api_key=config.api_key,
    max_iterations=config.max_iterations,
    max_output_chars=config.max_output_chars,
    execution_timeout=config.execution_timeout_sec,
    pool=self._pool,
    max_traces_per_project=config.max_traces_per_project,
)
```

**Step 4: Run tests**

Run: `pytest tests/unit/rlm/test_engine.py tests/unit/test_shesha.py tests/unit/test_config.py -v`
Expected: PASS

**Step 5: Run full test suite and type checker**

Run: `make all`
Expected: PASS

**Step 6: Commit**

```bash
git add src/shesha/rlm/engine.py src/shesha/shesha.py tests/unit/rlm/test_engine.py
git commit -m "fix(config): plumb max_traces_per_project from config through engine to cleanup"
```

---

### Task 7: Update changelog and flaws doc

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `scratch/flaws.md`

**Step 1: Update CHANGELOG.md**

Add under `[Unreleased]` → `Changed`:
- `TraceWriter` and `IncrementalTraceWriter` now accept `StorageBackend` protocol instead of `FilesystemStorage`
- `RLMEngine.query()` accepts `StorageBackend` protocol instead of `FilesystemStorage`
- `Project.query()` always passes storage to engine (removed `FilesystemStorage` special-casing)
- `Shesha.__init__` now uses `SheshaConfig.load()` by default, honoring env vars and config files
- `cleanup_old_traces` now uses `config.max_traces_per_project` instead of hardcoded 50

**Step 2: Update scratch/flaws.md**

Mark both flaws as RESOLVED with short descriptions of what was done.

**Step 3: Commit**

```bash
git add CHANGELOG.md scratch/flaws.md
git commit -m "docs: mark storage abstraction and config consistency flaws as resolved"
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Add trace methods to `StorageBackend` protocol | `storage/base.py` |
| 2 | `TraceWriter`/`IncrementalTraceWriter` → `StorageBackend` | `rlm/trace_writer.py` |
| 3 | `RLMEngine.query()` → `StorageBackend` | `rlm/engine.py` |
| 4 | Remove `isinstance` check from `Project.query()` | `project.py`, test |
| 5 | `Shesha.__init__` uses `SheshaConfig.load()` | `shesha.py`, test |
| 6 | Plumb `max_traces_per_project` to `cleanup_old_traces` | `engine.py`, `shesha.py`, test |
| 7 | Update changelog and flaws doc | `CHANGELOG.md`, `scratch/flaws.md` |
