"""Tests for RLM engine."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from shesha.rlm.engine import QueryResult, RLMEngine, extract_code_blocks
from shesha.rlm.trace import StepType, TokenUsage, Trace


def test_extract_code_blocks_finds_repl():
    """extract_code_blocks finds ```repl blocks."""
    text = """Here is some code:

```repl
print("hello")
```

And more text."""
    blocks = extract_code_blocks(text)
    assert len(blocks) == 1
    assert 'print("hello")' in blocks[0]


def test_extract_code_blocks_finds_python():
    """extract_code_blocks also finds ```python blocks."""
    text = """```python
x = 1
```"""
    blocks = extract_code_blocks(text)
    assert len(blocks) == 1
    assert "x = 1" in blocks[0]


def test_query_result_dataclass():
    """QueryResult stores query results."""
    result = QueryResult(
        answer="The answer",
        trace=Trace(),
        token_usage=TokenUsage(100, 50),
        execution_time=1.5,
    )
    assert result.answer == "The answer"
    assert result.execution_time == 1.5


class TestRLMEngine:
    """Tests for RLMEngine."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_runs_until_final(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Engine runs until FINAL is called."""
        # Mock LLM to return code with FINAL
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("The answer is 42")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        # Mock executor
        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="The answer is 42",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")
        result = engine.query(
            documents=["Doc 1 content", "Doc 2 content"],
            question="What is the answer?",
        )

        assert result.answer == "The answer is 42"
        assert len(result.trace.steps) > 0

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_calls_on_progress_callback(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Engine calls on_progress callback for each step."""
        # Mock LLM to return code with FINAL
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("Done")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        # Mock executor
        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="output",
            stderr="",
            error=None,
            final_answer="Done",
        )
        mock_executor_cls.return_value = mock_executor

        # Track callback invocations
        progress_calls: list[tuple[StepType, int]] = []

        def on_progress(step_type: StepType, iteration: int, content: str) -> None:
            progress_calls.append((step_type, iteration))

        engine = RLMEngine(model="test-model")
        result = engine.query(
            documents=["Doc content"],
            question="Test?",
            on_progress=on_progress,
        )

        assert result.answer == "Done"
        # Should have at least CODE_GENERATED, CODE_OUTPUT, FINAL_ANSWER
        step_types = [call[0] for call in progress_calls]
        assert StepType.CODE_GENERATED in step_types
        assert StepType.CODE_OUTPUT in step_types
        assert StepType.FINAL_ANSWER in step_types

    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_acquires_executor_from_pool(
        self,
        mock_llm_cls: MagicMock,
    ):
        """When pool is provided, engine acquires executor from pool instead of creating one."""
        from shesha.sandbox.pool import ContainerPool

        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("answer")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

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
        result = engine.query(documents=["Doc content"], question="What?")

        assert result.answer == "answer"
        mock_pool.acquire.assert_called_once()
        mock_pool.release.assert_called_once_with(mock_executor)
        mock_executor.stop.assert_not_called()

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
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="done",
        )
        mock_pool.acquire.return_value = mock_executor

        engine = RLMEngine(model="test-model", pool=mock_pool)
        engine.query(documents=["doc"], question="Q?")

        mock_executor.reset_namespace.assert_called_once()

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
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")  # No pool
        result = engine.query(documents=["doc"], question="Q?")

        assert result.answer == "answer"
        mock_executor_cls.assert_called_once()
        mock_executor.start.assert_called_once()
        mock_executor.stop.assert_called_once()

    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_returns_error_for_oversized_subcall_content(
        self,
        mock_llm_cls: MagicMock,
    ):
        """Engine returns error string when subcall content exceeds limit."""
        # Create engine with small limit for testing
        engine = RLMEngine(model="test-model", max_subcall_content_chars=1000)

        # Call _handle_llm_query directly with oversized content
        trace = Trace()
        token_usage = TokenUsage()
        large_content = "x" * 5000  # 5K chars, exceeds 1K limit

        result = engine._handle_llm_query(
            instruction="Summarize this",
            content=large_content,
            trace=trace,
            token_usage=token_usage,
            iteration=0,
        )

        # Should return error string, not call the LLM
        assert "Error" in result
        assert "5,000" in result or "5000" in result  # actual size
        assert "1,000" in result or "1000" in result  # limit
        assert "chunk" in result.lower()  # guidance to chunk smaller
        mock_llm_cls.assert_not_called()  # No sub-LLM call made

    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_allows_subcall_content_under_limit(
        self,
        mock_llm_cls: MagicMock,
    ):
        """Engine makes sub-LLM call when content is under limit."""
        # Mock sub-LLM
        mock_sub_llm = MagicMock()
        mock_sub_llm.complete.return_value = MagicMock(
            content="Analysis result",
            prompt_tokens=50,
            completion_tokens=25,
            total_tokens=75,
        )
        mock_llm_cls.return_value = mock_sub_llm

        # Create engine with reasonable limit
        engine = RLMEngine(model="test-model", max_subcall_content_chars=10000)

        trace = Trace()
        token_usage = TokenUsage()
        small_content = "x" * 500  # 500 chars, under 10K limit

        result = engine._handle_llm_query(
            instruction="Summarize this",
            content=small_content,
            trace=trace,
            token_usage=token_usage,
            iteration=0,
        )

        # Should return LLM response
        assert result == "Analysis result"
        mock_llm_cls.assert_called_once()  # Sub-LLM was called

    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_wraps_subcall_content_in_untrusted_tags(
        self,
        mock_llm_cls: MagicMock,
    ):
        """_handle_llm_query wraps content in untrusted tags before calling LLM."""
        mock_sub_llm = MagicMock()
        mock_sub_llm.complete.return_value = MagicMock(
            content="Summary result",
            prompt_tokens=50,
            completion_tokens=25,
            total_tokens=75,
        )
        mock_llm_cls.return_value = mock_sub_llm

        engine = RLMEngine(model="test-model", max_subcall_content_chars=10000)
        trace = Trace()
        token_usage = TokenUsage()

        engine._handle_llm_query(
            instruction="Summarize this",
            content="Untrusted document data",
            trace=trace,
            token_usage=token_usage,
            iteration=0,
        )

        # Verify the prompt sent to LLM contains the wrapping tags
        call_args = mock_sub_llm.complete.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        prompt_text = messages[0]["content"]
        assert "<untrusted_document_content>" in prompt_text
        assert "</untrusted_document_content>" in prompt_text
        assert "Untrusted document data" in prompt_text


class TestEngineTraceWriterSuppression:
    """Tests for engine trace writer suppress_errors configuration."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_creates_incremental_trace_writer_with_suppress_errors(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Engine creates IncrementalTraceWriter with suppress_errors=True."""
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

        with patch("shesha.rlm.engine.IncrementalTraceWriter") as mock_inc_writer_cls:
            mock_inc_writer = MagicMock()
            mock_inc_writer.path = None
            mock_inc_writer_cls.return_value = mock_inc_writer

            engine = RLMEngine(model="test-model")
            engine.query(
                documents=["doc content"],
                question="What?",
                storage=storage,
                project_id="test-project",
            )

            mock_inc_writer_cls.assert_called_once_with(storage, suppress_errors=True)

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_creates_trace_writer_with_suppress_errors(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Engine creates TraceWriter with suppress_errors=True for cleanup."""
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

            engine = RLMEngine(model="test-model")
            engine.query(
                documents=["doc content"],
                question="What?",
                storage=storage,
                project_id="test-project",
            )

            mock_writer_cls.assert_called_once_with(storage, suppress_errors=True)


class TestEngineTraceWriting:
    """Tests for trace writing integration."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_query_writes_trace_when_storage_provided(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Query writes trace file when storage is provided."""
        from shesha.storage.filesystem import FilesystemStorage

        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("test-project")

        # Configure mock to return FINAL answer
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

        engine = RLMEngine(model="test-model")
        engine.query(
            documents=["doc content"],
            question="What?",
            storage=storage,
            project_id="test-project",
        )

        traces = storage.list_traces("test-project")
        assert len(traces) == 1

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_query_writes_trace_incrementally(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Query writes trace steps incrementally, not just at the end."""
        from shesha.storage.filesystem import FilesystemStorage

        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("test-project")

        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content="```repl\nFINAL('done')\n```",
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
            final_answer="done",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")
        engine.query(
            documents=["doc content"],
            question="What?",
            storage=storage,
            project_id="test-project",
        )

        traces = storage.list_traces("test-project")
        assert len(traces) == 1

        # Verify JSONL has header, steps, and summary
        lines = traces[0].read_text().strip().split("\n")
        assert len(lines) >= 3  # header + at least one step + summary

        header = json.loads(lines[0])
        assert header["type"] == "header"
        assert header["question"] == "What?"

        summary = json.loads(lines[-1])
        assert summary["type"] == "summary"
        assert summary["status"] == "success"

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_query_writes_partial_trace_on_exception(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """If query is interrupted by exception, partial trace is still written."""
        from shesha.storage.filesystem import FilesystemStorage

        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("test-project")

        # LLM returns code, then raises on second call
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            MagicMock(
                content="```repl\nprint('hello')\n```",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            KeyboardInterrupt(),
        ]
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            stdout="hello",
            stderr="",
            error=None,
            final_answer=None,  # No final answer, loop continues
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")
        try:
            engine.query(
                documents=["doc content"],
                question="What?",
                storage=storage,
                project_id="test-project",
            )
        except KeyboardInterrupt:
            pass  # Expected

        # Partial trace should still exist
        traces = storage.list_traces("test-project")
        assert len(traces) == 1

        lines = traces[0].read_text().strip().split("\n")

        # Should have header
        header = json.loads(lines[0])
        assert header["type"] == "header"

        # Should have at least the steps from iteration 0
        step_lines = [json.loads(line) for line in lines[1:] if json.loads(line)["type"] == "step"]
        assert len(step_lines) >= 1

        # Should have summary with interrupted status
        summary = json.loads(lines[-1])
        assert summary["type"] == "summary"
        assert summary["status"] == "interrupted"


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

            mock_writer.cleanup_old_traces.assert_called_once_with("test-project", max_count=25)
