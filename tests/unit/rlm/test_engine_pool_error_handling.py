"""Tests for engine pool error handling when reset_namespace fails."""

from unittest.mock import MagicMock, patch

from shesha.rlm.engine import RLMEngine
from shesha.sandbox.pool import ContainerPool


class TestPoolExecutorErrorHandling:
    """Tests for handling broken executors in pool-backed queries."""

    def _make_engine_with_pool(
        self,
        mock_llm_cls: MagicMock,
        mock_executor: MagicMock,
    ) -> tuple[RLMEngine, MagicMock]:
        """Create engine with mock pool and executor."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("answer")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_pool = MagicMock(spec=ContainerPool)
        mock_pool.acquire.return_value = mock_executor

        engine = RLMEngine(model="test-model", pool=mock_pool)
        return engine, mock_pool

    @patch("shesha.rlm.engine.LLMClient")
    def test_broken_executor_not_released_to_pool(
        self,
        mock_llm_cls: MagicMock,
    ):
        """When reset_namespace raises, executor is discarded, not released."""
        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )
        mock_executor.reset_namespace.side_effect = RuntimeError("No socket connection")

        engine, mock_pool = self._make_engine_with_pool(mock_llm_cls, mock_executor)
        engine.query(documents=["doc"], question="Q?")

        # Broken executor should be stopped, not released
        mock_executor.stop.assert_called_once()
        mock_pool.release.assert_not_called()
        mock_pool.discard.assert_called_once_with(mock_executor)

    @patch("shesha.rlm.engine.LLMClient")
    def test_healthy_executor_released_to_pool(
        self,
        mock_llm_cls: MagicMock,
    ):
        """When reset_namespace succeeds, executor is released normally."""
        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )

        engine, mock_pool = self._make_engine_with_pool(mock_llm_cls, mock_executor)
        engine.query(documents=["doc"], question="Q?")

        # Healthy executor should be released, not stopped
        mock_pool.release.assert_called_once_with(mock_executor)
        mock_executor.stop.assert_not_called()

    @patch("shesha.rlm.engine.LLMClient")
    def test_query_result_not_masked_by_reset_failure(
        self,
        mock_llm_cls: MagicMock,
    ):
        """Query result is returned even when reset_namespace fails."""
        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )
        mock_executor.reset_namespace.side_effect = RuntimeError("No socket connection")

        engine, mock_pool = self._make_engine_with_pool(mock_llm_cls, mock_executor)
        result = engine.query(documents=["doc"], question="Q?")

        # Should still get the answer
        assert result.answer == "answer"


class TestPoolDiscard:
    """Tests for ContainerPool.discard method."""

    def test_discard_removes_from_in_use(self):
        """discard() removes executor from _in_use without adding to _available."""
        pool = ContainerPool.__new__(ContainerPool)
        pool._lock = __import__("threading").Lock()
        pool._available = __import__("collections").deque()
        pool._in_use = set()

        mock_executor = MagicMock()
        pool._in_use.add(mock_executor)

        pool.discard(mock_executor)

        assert mock_executor not in pool._in_use
        assert mock_executor not in pool._available

    def test_discard_unknown_executor_is_safe(self):
        """discard() does not raise for unknown executors."""
        pool = ContainerPool.__new__(ContainerPool)
        pool._lock = __import__("threading").Lock()
        pool._available = __import__("collections").deque()
        pool._in_use = set()

        mock_executor = MagicMock()
        # Should not raise
        pool.discard(mock_executor)
