# Container Pool Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `RLMEngine.query()` use the `ContainerPool` (acquire/release) instead of creating throwaway `ContainerExecutor` instances per query.

**Architecture:** Add optional `pool: ContainerPool | None` param to `RLMEngine.__init__`. When pool is provided, `query()` acquires an executor from it, sets the `llm_query_handler`, uses it, then resets namespace and releases back. When no pool is provided, falls back to current behavior (create/start/stop per query). `Shesha.__init__` passes its pool to the engine.

**Tech Stack:** Python, pytest, unittest.mock

---

### Task 1: Make RLMEngine accept and use a pool

**Files:**
- Test: `tests/unit/rlm/test_engine.py`
- Modify: `src/shesha/rlm/engine.py`

**Step 1: Write failing test — engine uses pool when provided**

Add to `tests/unit/rlm/test_engine.py`, inside `class TestRLMEngine`:

```python
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_acquires_executor_from_pool(
        self,
        mock_llm_cls: MagicMock,
    ):
        """When pool is provided, engine acquires executor from pool instead of creating one."""
        from shesha.sandbox.pool import ContainerPool

        # Mock LLM
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("answer")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        # Mock pool
        mock_pool = MagicMock(spec=ContainerPool)
        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )
        mock_pool.acquire.return_value = mock_executor

        engine = RLMEngine(model="test-model", pool=mock_pool)
        result = engine.query(
            documents=["Doc content"],
            question="What?",
        )

        assert result.answer == "answer"
        # Pool was used
        mock_pool.acquire.assert_called_once()
        mock_pool.release.assert_called_once_with(mock_executor)
        # Executor was NOT stopped (pool manages lifecycle)
        mock_executor.stop.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/rlm/test_engine.py::TestRLMEngine::test_engine_acquires_executor_from_pool -v`
Expected: FAIL — `RLMEngine.__init__` does not accept `pool` parameter

**Step 3: Write failing test — engine resets namespace on release**

Add to `tests/unit/rlm/test_engine.py`, inside `class TestRLMEngine`:

```python
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_resets_namespace_before_release(
        self,
        mock_llm_cls: MagicMock,
    ):
        """Engine resets executor namespace before releasing back to pool."""
        from shesha.sandbox.pool import ContainerPool

        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("done")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_pool = MagicMock(spec=ContainerPool)
        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok", stdout="", stderr="", error=None, final_answer="done",
        )
        mock_pool.acquire.return_value = mock_executor

        engine = RLMEngine(model="test-model", pool=mock_pool)
        engine.query(documents=["doc"], question="Q?")

        # Namespace reset before release
        mock_executor.reset_namespace.assert_called_once()
```

**Step 4: Write failing test — engine falls back without pool**

Add to `tests/unit/rlm/test_engine.py`, inside `class TestRLMEngine`:

```python
    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_creates_executor_without_pool(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Without pool, engine creates and stops its own executor (backward compat)."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("answer")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok", stdout="", stderr="", error=None, final_answer="answer",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")  # No pool
        result = engine.query(documents=["doc"], question="Q?")

        assert result.answer == "answer"
        # Created its own executor
        mock_executor_cls.assert_called_once()
        mock_executor.start.assert_called_once()
        mock_executor.stop.assert_called_once()
```

**Step 5: Run all three new tests to confirm they fail**

Run: `pytest tests/unit/rlm/test_engine.py::TestRLMEngine::test_engine_acquires_executor_from_pool tests/unit/rlm/test_engine.py::TestRLMEngine::test_engine_resets_namespace_before_release tests/unit/rlm/test_engine.py::TestRLMEngine::test_engine_creates_executor_without_pool -v`
Expected: First two FAIL (no `pool` param), third may pass (existing behavior)

**Step 6: Implement pool support in `RLMEngine`**

In `src/shesha/rlm/engine.py`:

1. Add import at top (line 1 area — add to existing imports):

```python
from shesha.sandbox.pool import ContainerPool
```

2. Update `__init__` to accept pool (add after `prompts_dir` param):

```python
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        max_iterations: int = 20,
        max_output_chars: int = 50000,
        execution_timeout: int = 30,
        max_subcall_content_chars: int = 500_000,
        prompts_dir: Path | None = None,
        pool: ContainerPool | None = None,
    ) -> None:
        """Initialize the RLM engine."""
        self.model = model
        self.api_key = api_key
        self.max_iterations = max_iterations
        self.max_output_chars = max_output_chars
        self.execution_timeout = execution_timeout
        self.max_subcall_content_chars = max_subcall_content_chars
        self.prompt_loader = PromptLoader(prompts_dir)
        self._pool = pool
```

3. Replace the executor creation and cleanup block in `query()`. Replace lines 218-219 and the finally block (lines 327-329). The new `query()` method executor section should be:

Replace these lines (around 206-219):
```python
        # Create executor with callback for llm_query
        def llm_query_callback(instruction: str, content: str) -> str:
            ...

        executor = ContainerExecutor(llm_query_handler=llm_query_callback)
        executor.start()
```

With:
```python
        # Create executor with callback for llm_query
        def llm_query_callback(instruction: str, content: str) -> str:
            return self._handle_llm_query(
                instruction,
                content,
                trace,
                token_usage,
                current_iteration,
                on_progress,
                on_step=_write_step,
            )

        # Acquire executor from pool or create standalone
        if self._pool is not None:
            executor = self._pool.acquire()
            executor.llm_query_handler = llm_query_callback
            owns_executor = False
        else:
            executor = ContainerExecutor(llm_query_handler=llm_query_callback)
            executor.start()
            owns_executor = True
```

Replace the finally block (around lines 327-329):
```python
        finally:
            _finalize_trace("[interrupted]", "interrupted")
            executor.stop()
```

With:
```python
        finally:
            _finalize_trace("[interrupted]", "interrupted")
            if owns_executor:
                executor.stop()
            else:
                executor.llm_query_handler = None
                executor.reset_namespace()
                self._pool.release(executor)  # type: ignore[union-attr]
```

**Step 7: Run all engine tests**

Run: `pytest tests/unit/rlm/test_engine.py -v`
Expected: ALL PASS

**Step 8: Commit**

```bash
git add src/shesha/rlm/engine.py tests/unit/rlm/test_engine.py
git commit -m "feat: RLMEngine acquires executor from pool when provided"
```

---

### Task 2: Wire pool into Shesha → RLMEngine

**Files:**
- Test: `tests/unit/test_shesha.py`
- Modify: `src/shesha/shesha.py`

**Step 1: Read `tests/unit/test_shesha.py` to understand existing test patterns**

Read the file first to understand how `Shesha` is tested (likely patches Docker, pool, etc.).

**Step 2: Write failing test — Shesha passes pool to engine**

Add to `tests/unit/test_shesha.py` (adapt to existing mock patterns):

```python
@patch("shesha.shesha.RepoIngester")
@patch("shesha.shesha.RLMEngine")
@patch("shesha.shesha.ContainerPool")
@patch("shesha.shesha.FilesystemStorage")
@patch("shesha.shesha.Shesha._check_docker_available")
def test_shesha_passes_pool_to_engine(
    mock_docker_check: MagicMock,
    mock_storage_cls: MagicMock,
    mock_pool_cls: MagicMock,
    mock_engine_cls: MagicMock,
    mock_ingester_cls: MagicMock,
):
    """Shesha passes pool to RLMEngine constructor."""
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool

    shesha = Shesha(model="test-model")

    # Verify RLMEngine was created with pool parameter
    mock_engine_cls.assert_called_once()
    call_kwargs = mock_engine_cls.call_args
    # pool should be passed as keyword arg
    assert call_kwargs[1].get("pool") is mock_pool or (
        len(call_kwargs[0]) > 5 and call_kwargs[0][5] is mock_pool
    )
```

**Step 3: Run test to verify it fails**

Run: `pytest tests/unit/test_shesha.py::test_shesha_passes_pool_to_engine -v`
Expected: FAIL — engine not called with `pool` arg

**Step 4: Update `Shesha.__init__` to pass pool to engine**

In `src/shesha/shesha.py`, change the RLMEngine construction (around lines 70-76):

```python
        # Create RLM engine
        self._rlm_engine = RLMEngine(
            model=config.model,
            api_key=config.api_key,
            max_iterations=config.max_iterations,
            max_output_chars=config.max_output_chars,
            execution_timeout=config.execution_timeout_sec,
            pool=self._pool,
        )
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_shesha.py::test_shesha_passes_pool_to_engine -v`
Expected: PASS

**Step 6: Run full test suite**

Run: `pytest tests/unit/ -q`
Expected: ALL PASS

**Step 7: Commit**

```bash
git add src/shesha/shesha.py tests/unit/test_shesha.py
git commit -m "feat: Shesha passes container pool to RLMEngine"
```

---

### Task 3: Run full checks and update docs

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `scratch/flaws.md`

**Step 1: Run full test suite, linter, type checker**

Run: `pytest tests/unit/ -q`
Expected: ALL PASS

Run: `ruff check src/shesha/rlm/engine.py src/shesha/shesha.py && mypy src/shesha/rlm/engine.py src/shesha/shesha.py`
Expected: No errors

**Step 2: Add changelog entry**

Under `## [Unreleased]` → `### Fixed`, add (create the section if it doesn't exist under Unreleased):

```markdown
- RLM engine now uses the container pool for queries instead of creating throwaway containers, eliminating cold-start overhead and idle resource waste
```

**Step 3: Mark flaw as resolved in `scratch/flaws.md`**

Replace the container pool flaw entry with strikethrough + RESOLVED, similar to other resolved items.

**Step 4: Commit**

```bash
git add CHANGELOG.md
git add -f scratch/flaws.md
git commit -m "docs: mark container pool integration flaw as resolved"
```
