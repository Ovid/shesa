"""Tests for container pool."""

from unittest.mock import MagicMock, patch

import pytest

from shesha.sandbox.pool import ContainerPool


class TestContainerPool:
    """Tests for ContainerPool."""

    @patch("shesha.sandbox.pool.ContainerExecutor")
    def test_pool_creates_containers_on_start(self, mock_executor_cls: MagicMock):
        """Pool creates specified number of containers on start."""
        pool = ContainerPool(size=3, image="shesha-sandbox")
        pool.start()

        assert mock_executor_cls.call_count == 3
        assert len(pool._available) == 3

    @patch("shesha.sandbox.pool.ContainerExecutor")
    def test_acquire_returns_executor(self, mock_executor_cls: MagicMock):
        """Acquiring from pool returns an executor."""
        mock_executor = MagicMock()
        mock_executor_cls.return_value = mock_executor

        pool = ContainerPool(size=1, image="shesha-sandbox")
        pool.start()

        executor = pool.acquire()
        assert executor is mock_executor
        assert len(pool._available) == 0

    @patch("shesha.sandbox.pool.ContainerExecutor")
    def test_release_returns_executor_to_pool(self, mock_executor_cls: MagicMock):
        """Releasing returns executor to pool."""
        mock_executor = MagicMock()
        mock_executor_cls.return_value = mock_executor

        pool = ContainerPool(size=1, image="shesha-sandbox")
        pool.start()

        executor = pool.acquire()
        pool.release(executor)
        assert len(pool._available) == 1

    @patch("shesha.sandbox.pool.ContainerExecutor")
    def test_stop_stops_all_containers(self, mock_executor_cls: MagicMock):
        """Stopping pool stops all containers."""
        mock_executor = MagicMock()
        mock_executor_cls.return_value = mock_executor

        pool = ContainerPool(size=2, image="shesha-sandbox")
        pool.start()
        pool.stop()

        assert mock_executor.stop.call_count == 2

    @patch("shesha.sandbox.pool.ContainerExecutor")
    def test_acquire_raises_after_stop(self, mock_executor_cls: MagicMock):
        """Acquiring from a stopped pool raises RuntimeError."""
        pool = ContainerPool(size=1, image="shesha-sandbox")
        pool.start()
        pool.stop()

        with pytest.raises(RuntimeError, match="stopped"):
            pool.acquire()
