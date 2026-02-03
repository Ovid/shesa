# Query Trace Logging Design

**Date:** 2026-02-03
**Status:** Approved
**Branch:** ovid/logging

## Overview

Automatic JSONL trace logging for every query to enable post-hoc debugging. Each trace captures the complete execution flow: prompts, generated code, outputs, and metadata.

## Requirements

- **Purpose:** Post-hoc debugging - review traces when something goes wrong
- **Trigger:** Always save - every query gets a trace file automatically
- **Content:** Full context including system prompts
- **Retention:** Keep last 50 traces per project (count-based)

## File Structure

```
projects/{project_id}/
├── docs/           # existing document storage
└── traces/         # new
    ├── 2026-02-03T14-30-00-123_a1b2c3d4.jsonl
    ├── 2026-02-03T14-35-22-456_e5f6g7h8.jsonl
    └── ...
```

**Filename format:** `{ISO-timestamp}_{short-id}.jsonl`
- Timestamp: `YYYY-MM-DDTHH-MM-SS-mmm` (colons replaced with dashes for filesystem compatibility, milliseconds for uniqueness)
- Short ID: First 8 chars of a UUID (for programmatic reference)

## JSONL Content Format

Each trace file contains one JSON object per line. The first line is always a header with query metadata, followed by one line per step.

### Line 1 - Header

```json
{
  "type": "header",
  "trace_id": "a1b2c3d4-...",
  "timestamp": "2026-02-03T14:30:00.123Z",
  "question": "What character appears in all seven novels?",
  "document_ids": ["doc_1", "doc_2", "doc_3"],
  "model": "claude-sonnet-4-20250514",
  "system_prompt": "You are an RLM agent...",
  "subcall_prompt": "You are answering a sub-query..."
}
```

### Subsequent Lines - Steps

```json
{
  "type": "step",
  "step_type": "code_generated",
  "iteration": 1,
  "timestamp": "2026-02-03T14:30:01.456Z",
  "content": "chars = set()\nfor doc in documents:\n    ...",
  "tokens_used": 150,
  "duration_ms": 1234
}
```

Step types: `code_generated`, `code_output`, `subcall_request`, `subcall_response`, `error`, `final_answer`

### Final Line - Summary

```json
{
  "type": "summary",
  "answer": "John Carter appears in all seven novels",
  "total_iterations": 3,
  "total_tokens": {"prompt": 4500, "completion": 890},
  "total_duration_ms": 12345,
  "status": "success"
}
```

Status values: `success`, `max_iterations`, `error`

## Implementation

### New Module: `src/shesha/rlm/trace_writer.py`

Responsibilities:
- `TraceWriter` class that wraps trace serialization
- `write_trace(project_id: str, trace: Trace, query_context: QueryContext) -> Path` - writes the JSONL file
- `cleanup_old_traces(project_id: str, max_count: int = 50)` - removes oldest traces when limit exceeded

### Changes to Existing Code

1. **`engine.py`** - After `query()` completes, call `TraceWriter.write_trace()` with the result
2. **`storage/filesystem.py`** - Add `get_traces_dir(project_id)` and `list_traces(project_id)` methods
3. **`models.py`** - Add `QueryContext` dataclass to bundle the metadata (question, doc IDs, model, prompts)
4. **`config.py`** - Add `SHESHA_MAX_TRACES_PER_PROJECT` setting (default: 50)

### No Changes To

- `Trace` / `TraceStep` dataclasses (already have all needed fields)
- Public API surface (trace saving is automatic, internal)

## Error Handling

**Write failures:**
- Trace writing should never cause a query to fail
- If writing fails (disk full, permissions), log a warning but return the `QueryResult` normally
- Use a try/except wrapper around the write operation

**Partial traces (query interrupted):**
- If query fails mid-execution, still write whatever steps were collected
- `status` field in summary will be `error` with the exception message
- Ensures you can debug failed queries, not just successful ones

**Concurrent queries:**
- Millisecond timestamps + UUID in filename prevent collisions
- Each query writes its own file independently

**Cleanup race conditions:**
- Cleanup runs after successful write
- Simple approach: list files, sort by timestamp, delete oldest if over limit
- Small race window acceptable (might briefly have 51 files)

**Redaction:**
- Traces are written after redaction is applied (using existing `Trace.redacted()`)
- Ensures secrets don't leak to disk
- Respects existing `RedactionConfig` settings

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SHESHA_MAX_TRACES_PER_PROJECT` | 50 | Maximum traces to keep per project |

## Testing Strategy

### Unit Tests: `tests/unit/rlm/test_trace_writer.py`

- `test_write_trace_creates_jsonl_file` - file created in correct location
- `test_trace_file_contains_header_with_metadata` - first line has question, model, prompts
- `test_trace_file_contains_all_steps` - each step type serialized correctly
- `test_trace_file_ends_with_summary` - final line has totals and status
- `test_cleanup_removes_oldest_traces` - keeps only N most recent
- `test_cleanup_does_nothing_under_limit` - no deletion when count < max
- `test_write_failure_does_not_raise` - graceful handling of write errors
- `test_traces_are_redacted_before_writing` - secrets stripped

### Unit Tests: `tests/unit/storage/test_filesystem_traces.py`

- `test_get_traces_dir_creates_directory` - lazy creation
- `test_list_traces_returns_sorted_by_timestamp` - oldest first for cleanup

### Integration Test

- `test_query_creates_trace_file` - end-to-end: query -> trace file exists with correct content

## Estimated Scope

- `src/shesha/rlm/trace_writer.py` - ~80-100 lines
- `src/shesha/models.py` - `QueryContext` dataclass ~15 lines
- Updates to `engine.py`, `storage/filesystem.py`, `config.py` - ~30 lines total
- Tests - ~150 lines
