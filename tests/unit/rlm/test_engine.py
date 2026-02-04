"""Tests for RLM engine."""

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
