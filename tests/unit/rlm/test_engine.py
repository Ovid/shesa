"""Tests for RLM engine."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


def test_query_result_verification_defaults_none():
    """QueryResult.verification defaults to None."""
    result = QueryResult(
        answer="ans",
        trace=Trace(),
        token_usage=TokenUsage(),
        execution_time=0.0,
    )
    assert result.verification is None


def test_query_result_accepts_verification():
    """QueryResult accepts optional verification param."""
    from shesha.rlm.verification import Citation, VerificationResult

    vr = VerificationResult(
        citations=[Citation(doc_id=0, found=True)],
        quotes=[],
    )
    result = QueryResult(
        answer="ans",
        trace=Trace(),
        token_usage=TokenUsage(),
        execution_time=0.0,
        verification=vr,
    )
    assert result.verification is vr
    assert result.verification.all_valid is True


def test_engine_verify_citations_defaults_true():
    """RLMEngine.verify_citations defaults to True."""
    engine = RLMEngine(model="test-model")
    assert engine.verify_citations is True


def test_engine_verify_citations_can_be_disabled():
    """RLMEngine accepts verify_citations=False."""
    engine = RLMEngine(model="test-model", verify_citations=False)
    assert engine.verify_citations is False


def test_semantic_verification_step_type_exists():
    """SEMANTIC_VERIFICATION step type exists."""
    assert StepType.SEMANTIC_VERIFICATION.value == "semantic_verification"


def test_engine_verify_defaults_false():
    """RLMEngine.verify defaults to False."""
    engine = RLMEngine(model="test-model")
    assert engine.verify is False


def test_engine_verify_can_be_enabled():
    """RLMEngine accepts verify=True."""
    engine = RLMEngine(model="test-model", verify=True)
    assert engine.verify is True


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
    def test_engine_raises_for_oversized_subcall_content(
        self,
        mock_llm_cls: MagicMock,
    ):
        """Engine raises SubcallContentError when subcall content exceeds limit."""
        from shesha.sandbox.executor import SubcallContentError

        # Create engine with small limit for testing
        engine = RLMEngine(model="test-model", max_subcall_content_chars=1000)

        # Call _handle_llm_query directly with oversized content
        trace = Trace()
        token_usage = TokenUsage()
        large_content = "x" * 5000  # 5K chars, exceeds 1K limit

        with pytest.raises(SubcallContentError) as exc_info:
            engine._handle_llm_query(
                instruction="Summarize this",
                content=large_content,
                trace=trace,
                token_usage=token_usage,
                iteration=0,
            )

        error_msg = str(exc_info.value)
        assert "5,000" in error_msg or "5000" in error_msg  # actual size
        assert "1,000" in error_msg or "1000" in error_msg  # limit
        assert "chunk" in error_msg.lower()  # guidance to chunk smaller
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

    @patch("shesha.rlm.engine.LLMClient")
    @patch("shesha.rlm.engine.ContainerExecutor")
    def test_engine_runs_semantic_verification_when_enabled(
        self,
        mock_executor_cls: MagicMock,
        mock_llm_cls: MagicMock,
    ) -> None:
        """Engine runs semantic verification when verify=True."""
        verification_findings = json.dumps(
            {
                "findings": [
                    {
                        "finding_id": "P0.1",
                        "original_claim": "Issue",
                        "confidence": "high",
                        "reason": "Confirmed.",
                        "evidence_classification": "code_analysis",
                        "flags": [],
                    }
                ]
            }
        )

        # Mock LLM: first call is the main query, subsequent calls are verification subcalls.
        # doc_names=["main.py"] is a code file, so Layer 2 also runs (3 LLM calls total).
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            # Main query response
            MagicMock(
                content='```repl\nFINAL("## P0.1: Issue\\nSee Doc 0.")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            # Layer 1: Adversarial verification subcall response
            MagicMock(
                content=verification_findings,
                prompt_tokens=200,
                completion_tokens=100,
                total_tokens=300,
            ),
            # Layer 2: Code-specific verification subcall response
            MagicMock(
                content=verification_findings,
                prompt_tokens=200,
                completion_tokens=100,
                total_tokens=300,
            ),
        ]
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        verification_json = json.dumps(
            {
                "citations": [{"doc_id": 0, "found": True}],
                "quotes": [],
            }
        )
        mock_executor.execute.side_effect = [
            # FINAL execution
            MagicMock(
                status="ok",
                stdout="",
                stderr="",
                error=None,
                final_answer="## P0.1: Issue\nSee Doc 0.",
            ),
            # Mechanical verification
            MagicMock(
                status="ok",
                stdout=verification_json,
                stderr="",
                error=None,
                final_answer=None,
            ),
        ]
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify=True, verify_citations=True)
        result = engine.query(
            documents=["Doc content here"],
            question="Find issues",
            doc_names=["main.py"],
        )

        assert result.semantic_verification is not None
        assert len(result.semantic_verification.findings) == 1
        assert result.semantic_verification.findings[0].confidence == "high"

    @patch("shesha.rlm.engine.LLMClient")
    @patch("shesha.rlm.engine.ContainerExecutor")
    def test_engine_skips_semantic_verification_when_disabled(
        self,
        mock_executor_cls: MagicMock,
        mock_llm_cls: MagicMock,
    ) -> None:
        """Engine skips semantic verification when verify=False."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("answer")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify=False, verify_citations=False)
        result = engine.query(documents=["Doc"], question="What?")

        assert result.semantic_verification is None

    @patch("shesha.rlm.engine.LLMClient")
    @patch("shesha.rlm.engine.ContainerExecutor")
    def test_engine_semantic_verification_failure_does_not_block_answer(
        self,
        mock_executor_cls: MagicMock,
        mock_llm_cls: MagicMock,
    ) -> None:
        """Semantic verification failure doesn't prevent answer delivery."""
        # Answer must reference Doc 0 so gather_cited_documents finds citations
        final_answer_text = "See Doc 0 for details"
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            MagicMock(
                content=f'```repl\nFINAL("{final_answer_text}")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            # Verification subcall returns garbage (unparseable)
            MagicMock(
                content="I refuse to output JSON",
                prompt_tokens=200,
                completion_tokens=100,
                total_tokens=300,
            ),
        ]
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer=final_answer_text,
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify=True, verify_citations=False)
        result = engine.query(
            documents=["Doc content"],
            question="What?",
            doc_names=["file.txt"],
        )

        assert result.answer == final_answer_text
        assert result.semantic_verification is None
        # Error recorded in trace
        sem_steps = [s for s in result.trace.steps if s.type == StepType.SEMANTIC_VERIFICATION]
        assert len(sem_steps) >= 1
        last_step = sem_steps[-1].content
        assert "error" in last_step.lower() or "Could not parse" in last_step


class TestDeadExecutorNoPool:
    """Tests for early exit when executor dies without pool."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_only_one_llm_call_when_executor_dies(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Engine makes only 1 LLM call, not 20, when executor dies without pool."""
        from shesha.sandbox.executor import ExecutionResult

        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nprint("big output")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True

        def kill_on_execute(code, timeout=30):
            mock_executor.is_alive = False
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error="Protocol error: line too long",
            )

        mock_executor.execute.side_effect = kill_on_execute
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", max_iterations=20)  # No pool
        engine.query(documents=["doc"], question="Q?")

        # Should have only called LLM once, not continued for 20 iterations
        assert mock_llm.complete.call_count == 1

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_executor_died_answer_distinct_from_max_iterations(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Early exit answer is distinct from max iterations message."""
        from shesha.sandbox.executor import ExecutionResult

        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nprint("boom")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True

        def kill_on_execute(code, timeout=30):
            mock_executor.is_alive = False
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error="Protocol error: overflow",
            )

        mock_executor.execute.side_effect = kill_on_execute
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")  # No pool
        result = engine.query(documents=["doc"], question="Q?")

        # Answer should mention executor dying, not "max iterations"
        assert "max iterations" not in result.answer.lower()
        assert "executor" in result.answer.lower() or "died" in result.answer.lower()


class TestDeadExecutorWithPool:
    """Tests for dead executor recovery when pool is available."""

    @patch("shesha.rlm.engine.LLMClient")
    def test_dead_executor_stopped_before_discard(
        self,
        mock_llm_cls: MagicMock,
    ) -> None:
        """Dead executor is stopped before being discarded from pool."""
        from shesha.sandbox.executor import ExecutionResult
        from shesha.sandbox.pool import ContainerPool

        mock_llm = MagicMock()
        call_count = 0

        def llm_side_effect(messages):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(
                    content='```repl\nprint("boom")\n```',
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150,
                )
            return MagicMock(
                content='```repl\nFINAL("recovered")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            )

        mock_llm.complete.side_effect = llm_side_effect
        mock_llm_cls.return_value = mock_llm

        # First executor: dies on execute
        dead_executor = MagicMock()
        dead_executor.is_alive = True

        def kill_on_execute(code, timeout=30):
            dead_executor.is_alive = False
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error="Protocol error",
            )

        dead_executor.execute.side_effect = kill_on_execute

        # Second executor: works fine
        fresh_executor = MagicMock()
        fresh_executor.is_alive = True
        fresh_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="recovered",
        )

        mock_pool = MagicMock(spec=ContainerPool)
        mock_pool.acquire.side_effect = [dead_executor, fresh_executor]

        engine = RLMEngine(model="test-model", pool=mock_pool)
        result = engine.query(documents=["doc"], question="Q?")

        assert result.answer == "recovered"
        dead_executor.stop.assert_called_once()
        mock_pool.discard.assert_called_once_with(dead_executor)


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


class TestEngineVerification:
    """Tests for post-FINAL citation verification."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_runs_verification_after_final(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """Engine runs verification after FINAL and populates result.verification."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("Doc 0 says something")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        verification_json = json.dumps(
            {
                "citations": [{"doc_id": 0, "found": True}],
                "quotes": [],
            }
        )

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.side_effect = [
            # First call: the FINAL answer execution
            MagicMock(
                status="ok",
                stdout="",
                stderr="",
                error=None,
                final_answer="Doc 0 says something",
            ),
            # Second call: verification code execution
            MagicMock(
                status="ok",
                stdout=verification_json,
                stderr="",
                error=None,
                final_answer=None,
            ),
        ]
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify_citations=True)
        result = engine.query(documents=["Doc content"], question="What?")

        assert result.answer == "Doc 0 says something"
        assert result.verification is not None
        assert len(result.verification.citations) == 1
        assert result.verification.citations[0].found is True
        assert mock_executor.execute.call_count == 2

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_skips_verification_when_disabled(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """Engine skips verification when verify_citations=False."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("Doc 0 says something")\n```',
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
            final_answer="Doc 0 says something",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify_citations=False)
        result = engine.query(documents=["Doc content"], question="What?")

        assert result.answer == "Doc 0 says something"
        assert result.verification is None
        assert mock_executor.execute.call_count == 1

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_handles_verification_failure_gracefully(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """Verification failure doesn't affect answer delivery."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("Doc 0 answer")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.side_effect = [
            # First call: FINAL answer
            MagicMock(
                status="ok",
                stdout="",
                stderr="",
                error=None,
                final_answer="Doc 0 answer",
            ),
            # Second call: verification fails
            MagicMock(
                status="error",
                stdout="",
                stderr="Traceback: something broke",
                error="execution error",
                final_answer=None,
            ),
        ]
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify_citations=True)
        result = engine.query(documents=["Doc content"], question="What?")

        assert result.answer == "Doc 0 answer"
        assert result.verification is None

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_adds_verification_trace_step(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """VERIFICATION step appears in trace after successful verification."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("Doc 0 says something")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        verification_json = json.dumps(
            {
                "citations": [{"doc_id": 0, "found": True}],
                "quotes": [],
            }
        )

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.side_effect = [
            MagicMock(
                status="ok",
                stdout="",
                stderr="",
                error=None,
                final_answer="Doc 0 says something",
            ),
            MagicMock(
                status="ok",
                stdout=verification_json,
                stderr="",
                error=None,
                final_answer=None,
            ),
        ]
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify_citations=True)
        result = engine.query(documents=["Doc content"], question="What?")

        step_types = [s.type for s in result.trace.steps]
        assert StepType.VERIFICATION in step_types

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_records_verification_error_in_trace(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """Verification exception is recorded as a VERIFICATION trace step."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("Doc 0 answer")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.side_effect = [
            # First call: FINAL answer
            MagicMock(
                status="ok",
                stdout="",
                stderr="",
                error=None,
                final_answer="Doc 0 answer",
            ),
            # Second call: verification raises
            ValueError("Could not parse verification output: no valid JSON found"),
        ]
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify_citations=True)
        result = engine.query(documents=["Doc content"], question="What?")

        assert result.answer == "Doc 0 answer"
        assert result.verification is None
        # Error should be recorded in a VERIFICATION trace step
        verification_steps = [s for s in result.trace.steps if s.type == StepType.VERIFICATION]
        assert len(verification_steps) == 1
        assert "Could not parse verification output" in verification_steps[0].content
