"""Container pool for managing warm sandbox containers."""

import threading
from collections import deque

from shesha.sandbox.executor import ContainerExecutor


class ContainerPool:
    """Pool of pre-warmed containers for fast execution."""

    def __init__(
        self,
        size: int = 3,
        image: str = "shesha-sandbox",
        memory_limit: str = "512m",
    ) -> None:
        """Initialize pool settings."""
        self.size = size
        self.image = image
        self.memory_limit = memory_limit
        self._available: deque[ContainerExecutor] = deque()
        self._in_use: set[ContainerExecutor] = set()
        self._lock = threading.Lock()
        self._started = False

    def start(self) -> None:
        """Start the pool and warm up containers."""
        if self._started:
            return
        for _ in range(self.size):
            executor = ContainerExecutor(
                image=self.image,
                memory_limit=self.memory_limit,
            )
            executor.start()
            self._available.append(executor)
        self._started = True

    def stop(self) -> None:
        """Stop all containers in the pool."""
        with self._lock:
            for executor in self._available:
                executor.stop()
            for executor in self._in_use:
                executor.stop()
            self._available.clear()
            self._in_use.clear()
            self._started = False

    def acquire(self) -> ContainerExecutor:
        """Acquire an executor from the pool."""
        with self._lock:
            if not self._started:
                raise RuntimeError("Cannot acquire from a stopped pool")
            if self._available:
                executor = self._available.popleft()
            else:
                # Create new container if pool exhausted
                executor = ContainerExecutor(
                    image=self.image,
                    memory_limit=self.memory_limit,
                )
                executor.start()
            self._in_use.add(executor)
            return executor

    def release(self, executor: ContainerExecutor) -> None:
        """Release an executor back to the pool."""
        with self._lock:
            if executor in self._in_use:
                self._in_use.remove(executor)
                self._available.append(executor)

    def discard(self, executor: ContainerExecutor) -> None:
        """Remove an executor from _in_use without returning it to _available.

        Use this for broken executors that should not be reused.
        """
        with self._lock:
            self._in_use.discard(executor)

    def __enter__(self) -> "ContainerPool":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit."""
        self.stop()
