"""Tests for trace writer."""

import datetime
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from shesha.models import QueryContext
from shesha.rlm.trace import StepType, TokenUsage, Trace
from shesha.storage.filesystem import FilesystemStorage


class TestTraceWriterFileCreation:
    """Tests for trace file creation."""

    @pytest.fixture
    def storage(self, tmp_path: Path) -> FilesystemStorage:
        """Create a temporary storage backend."""
        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("test-project")
        return storage

    @pytest.fixture
    def trace(self) -> Trace:
        """Create a sample trace."""
        trace = Trace()
        trace.add_step(StepType.CODE_GENERATED, "print('hello')", iteration=0)
        trace.add_step(StepType.CODE_OUTPUT, "hello", iteration=0)
        return trace

    @pytest.fixture
    def context(self) -> QueryContext:
        """Create a sample query context."""
        return QueryContext(
            trace_id="abcd1234-5678-90ab-cdef-1234567890ab",
            question="What is the answer?",
            document_ids=["doc1", "doc2"],
            model="claude-sonnet-4-20250514",
            system_prompt="You are an assistant...",
            subcall_prompt="Analyze this...",
        )

    def test_write_trace_creates_jsonl_file(
        self,
        storage: FilesystemStorage,
        trace: Trace,
        context: QueryContext,
    ) -> None:
        """write_trace creates a .jsonl file in the traces directory."""
        from shesha.rlm.trace_writer import TraceWriter

        writer = TraceWriter(storage)
        # Mock datetime to get predictable filename
        fixed_time = datetime.datetime(2026, 2, 3, 14, 30, 0, 123000, tzinfo=datetime.UTC)
        with patch("shesha.rlm.trace_writer.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = fixed_time
            mock_dt.datetime.fromtimestamp = datetime.datetime.fromtimestamp
            mock_dt.UTC = datetime.UTC
            path = writer.write_trace(
                project_id="test-project",
                trace=trace,
                context=context,
                answer="42",
                token_usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
                execution_time=1.5,
                status="success",
            )

        assert path.exists()
        assert path.suffix == ".jsonl"
        assert path.parent.name == "traces"
        # Check filename format: YYYY-MM-DDTHH-MM-SS-mmm_shortid.jsonl
        assert "2026-02-03T14-30-00-123" in path.name
        assert "abcd1234" in path.name


class TestTraceWriterContent:
    """Tests for trace file content."""

    @pytest.fixture
    def storage(self, tmp_path: Path) -> FilesystemStorage:
        """Create a temporary storage backend."""
        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("test-project")
        return storage

    @pytest.fixture
    def trace(self) -> Trace:
        """Create a sample trace."""
        trace = Trace()
        trace.add_step(StepType.CODE_GENERATED, "print('hello')", iteration=0)
        trace.add_step(StepType.CODE_OUTPUT, "hello", iteration=0)
        return trace

    @pytest.fixture
    def context(self) -> QueryContext:
        """Create a sample query context."""
        return QueryContext(
            trace_id="abcd1234-5678-90ab-cdef-1234567890ab",
            question="What is the answer?",
            document_ids=["doc1", "doc2"],
            model="claude-sonnet-4-20250514",
            system_prompt="You are an assistant...",
            subcall_prompt="Analyze this...",
        )

    def test_trace_file_contains_header_with_metadata(
        self,
        storage: FilesystemStorage,
        trace: Trace,
        context: QueryContext,
    ) -> None:
        """First line of trace file is header with query metadata."""
        from shesha.rlm.trace_writer import TraceWriter

        writer = TraceWriter(storage)
        path = writer.write_trace(
            project_id="test-project",
            trace=trace,
            context=context,
            answer="42",
            token_usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
            execution_time=1.5,
            status="success",
        )

        lines = path.read_text().strip().split("\n")
        header = json.loads(lines[0])

        assert header["type"] == "header"
        assert header["trace_id"] == "abcd1234-5678-90ab-cdef-1234567890ab"
        assert header["question"] == "What is the answer?"
        assert header["document_ids"] == ["doc1", "doc2"]
        assert header["model"] == "claude-sonnet-4-20250514"
        assert header["system_prompt"] == "You are an assistant..."
        assert header["subcall_prompt"] == "Analyze this..."
        assert "timestamp" in header

    def test_trace_file_contains_all_steps(
        self,
        storage: FilesystemStorage,
        context: QueryContext,
    ) -> None:
        """Trace file contains one line per step with correct fields."""
        from shesha.rlm.trace_writer import TraceWriter

        trace = Trace()
        trace.add_step(
            StepType.CODE_GENERATED, "print('hello')", iteration=0, tokens_used=50
        )
        trace.add_step(
            StepType.CODE_OUTPUT, "hello", iteration=0, duration_ms=100
        )
        trace.add_step(
            StepType.FINAL_ANSWER, "42", iteration=0
        )

        writer = TraceWriter(storage)
        path = writer.write_trace(
            project_id="test-project",
            trace=trace,
            context=context,
            answer="42",
            token_usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
            execution_time=1.5,
            status="success",
        )

        lines = path.read_text().strip().split("\n")
        # Header + 3 steps + summary = 5 lines
        assert len(lines) >= 4  # At least header + 3 steps

        # Check step lines (lines 1, 2, 3)
        step1 = json.loads(lines[1])
        assert step1["type"] == "step"
        assert step1["step_type"] == "code_generated"
        assert step1["iteration"] == 0
        assert step1["content"] == "print('hello')"
        assert step1["tokens_used"] == 50

        step2 = json.loads(lines[2])
        assert step2["type"] == "step"
        assert step2["step_type"] == "code_output"
        assert step2["duration_ms"] == 100

        step3 = json.loads(lines[3])
        assert step3["type"] == "step"
        assert step3["step_type"] == "final_answer"
