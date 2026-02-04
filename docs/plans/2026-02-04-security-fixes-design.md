# Security Fixes Design

Date: 2026-02-04

## Overview

This design addresses security findings from an automated security review. The fixes target host-side vulnerabilities that Docker container isolation does not protect against.

## Issues Addressed

### High Priority (Host DoS)

| # | Issue | Location |
|---|-------|----------|
| 3 | Unbounded stream buffering | `executor.py:_read_line()` |
| 4 | Execution can hang indefinitely | `executor.py:_read_line()` |
| 5 | Unbounded JSON message size | `executor.py:execute()` |

### Medium Priority (Path Traversal)

| # | Issue | Location |
|---|-------|----------|
| 6 | Unsanitized project_id in paths | `repo/ingester.py` |
| 7 | Unsanitized doc.name in raw copy | `storage/filesystem.py` |

## Design

### 1. Protocol Limits (executor.py)

Add configurable limits at module level:

```python
MAX_BUFFER_SIZE = 10 * 1024 * 1024   # 10 MB max buffer
MAX_LINE_LENGTH = 1 * 1024 * 1024     # 1 MB max single line
MAX_READ_DURATION = 300               # 5 min total deadline
```

New exception in `sandbox/executor.py`:

```python
class ProtocolError(Exception):
    """Container protocol violation (oversized data, timeout)."""
```

Changes to `_read_line()`:
- Track start time at method entry
- Check elapsed time on each loop iteration, raise `ProtocolError` if exceeded
- Check `_raw_buffer` and `_content_buffer` sizes after each append
- Raise `ProtocolError` if either exceeds `MAX_BUFFER_SIZE`
- Check line length before returning, raise if exceeds `MAX_LINE_LENGTH`

Changes to `execute()`:
- Catch `ProtocolError` and return error `ExecutionResult`
- Ensure container is stopped on protocol violation

### 2. Path Traversal Protection (ingester.py)

Add helper method:

```python
from shesha.security.paths import safe_path

def _repo_path(self, project_id: str) -> Path:
    """Get safe path for a project's repo directory."""
    return safe_path(self.repos_dir, project_id)
```

Replace all `self.repos_dir / project_id` with `self._repo_path(project_id)`.

Affected methods:
- `clone()`
- `save_sha()`
- `save_source_url()`
- `get_source_url()`
- `get_saved_sha()`
- `get_repo_url()`
- `get_local_sha()`
- `list_files()`
- `fetch()`
- `pull()`
- `delete_repo()`

### 3. Raw File Copy Protection (filesystem.py)

Change line 88 from:

```python
shutil.copy2(raw_path, raw_dir / doc.name)
```

To:

```python
raw_dest = safe_path(raw_dir, doc.name)
raw_dest.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(raw_path, raw_dest)
```

The `mkdir` handles nested paths like `src/main.py` from repo ingestion.

### 4. Documentation Updates

**SECURITY.md** - Add new section:

```markdown
### 6. Protocol Limits

The container communication protocol enforces limits to prevent resource exhaustion:

| Limit | Value | Purpose |
|-------|-------|---------|
| Max buffer size | 10 MB | Prevents memory exhaustion from large outputs |
| Max line length | 1 MB | Prevents oversized JSON messages |
| Max read duration | 5 min | Overall deadline prevents hanging |

When limits are exceeded, the container is terminated and an error is returned.
```

Update "Path Traversal Protection" section to mention repo ingestion paths.

**CHANGELOG.md** - Add under `[Unreleased]`:

```markdown
### Fixed

- Host memory exhaustion via unbounded container output buffering
- Execution hanging indefinitely when container drips output without newlines
- Oversized JSON messages from container causing memory/CPU spike
- Path traversal in repository ingestion when project_id contains path separators
- Path traversal in raw file storage when document name contains path separators

### Security

- Added protocol limits for container communication (max buffer, max line, overall deadline)
- Applied `safe_path()` consistently to all filesystem operations in repo ingestion and storage
```

## Testing Strategy

### Protocol Limits

- Unit test: `_read_line()` raises `ProtocolError` when buffer exceeds limit
- Unit test: `_read_line()` raises `ProtocolError` when deadline exceeded
- Unit test: `execute()` returns error result on `ProtocolError`
- Integration test: Container producing oversized output is handled gracefully

### Path Traversal

- Unit test: `_repo_path("../escape")` raises `PathTraversalError`
- Unit test: `store_document()` with `doc.name="../escape"` raises `PathTraversalError`
- Unit test: `store_document()` with `doc.name="src/main.py"` creates nested directory

## Files Changed

1. `src/shesha/sandbox/executor.py` - Protocol limits
2. `src/shesha/repo/ingester.py` - Safe path for repo directories
3. `src/shesha/storage/filesystem.py` - Safe path for raw file copy
4. `SECURITY.md` - Document protocol limits
5. `CHANGELOG.md` - Document fixes
6. `tests/unit/sandbox/test_executor.py` - Protocol limit tests
7. `tests/unit/repo/test_ingester.py` - Path traversal tests
8. `tests/unit/test_filesystem.py` - Path traversal tests
