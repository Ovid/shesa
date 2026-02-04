"""Trace writer for saving query traces to JSONL files."""

import datetime
import json
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

        # Build lines
        lines: list[str] = []

        # Header
        header = {
            "type": "header",
            "trace_id": context.trace_id,
            "timestamp": now.isoformat(),
            "question": context.question,
            "document_ids": context.document_ids,
            "model": context.model,
            "system_prompt": context.system_prompt,
            "subcall_prompt": context.subcall_prompt,
        }
        lines.append(json.dumps(header))

        # Steps
        for step in trace.steps:
            step_data = {
                "type": "step",
                "step_type": step.type.value,
                "iteration": step.iteration,
                "timestamp": datetime.datetime.fromtimestamp(
                    step.timestamp, tz=datetime.UTC
                ).isoformat(),
                "content": step.content,
                "tokens_used": step.tokens_used,
                "duration_ms": step.duration_ms,
            }
            lines.append(json.dumps(step_data))

        # Write file
        path = traces_dir / filename
        path.write_text("\n".join(lines) + "\n")

        return path
