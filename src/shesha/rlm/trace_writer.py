"""Trace writer for saving query traces to JSONL files."""

import datetime
from pathlib import Path

from shesha.models import QueryContext
from shesha.rlm.trace import TokenUsage, Trace
from shesha.storage.filesystem import FilesystemStorage


class TraceWriter:
    """Writes query traces to JSONL files."""

    def __init__(self, storage: FilesystemStorage) -> None:
        """Initialize with storage backend."""
        self.storage = storage

    def write_trace(
        self,
        project_id: str,
        trace: Trace,
        context: QueryContext,
        answer: str,
        token_usage: TokenUsage,
        execution_time: float,
        status: str,
    ) -> Path:
        """Write a trace to a JSONL file.

        Args:
            project_id: The project ID
            trace: The execution trace
            context: Query metadata
            answer: The final answer
            token_usage: Token usage statistics
            execution_time: Total execution time in seconds
            status: Query status (success, max_iterations, error)

        Returns:
            Path to the created trace file
        """
        traces_dir = self.storage.get_traces_dir(project_id)

        # Generate filename: YYYY-MM-DDTHH-MM-SS-mmm_shortid.jsonl
        now = datetime.datetime.now(datetime.UTC)
        timestamp = now.strftime("%Y-%m-%dT%H-%M-%S") + f"-{now.microsecond // 1000:03d}"
        short_id = context.trace_id[:8]
        filename = f"{timestamp}_{short_id}.jsonl"

        path = traces_dir / filename
        path.write_text("")  # Create empty file for now

        return path
