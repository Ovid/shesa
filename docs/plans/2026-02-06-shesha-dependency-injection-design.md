# Shesha Dependency Injection Design

## Problem

`Shesha.__init__` hard-binds infrastructure components (`FilesystemStorage`,
`RLMEngine`, `ParserRegistry`, `RepoIngester`), making it hard to:

- **Test** without Docker/filesystem (must mock at lower levels)
- **Extend** with alternate storage backends, engines, or parsers

## Solution

Add optional DI parameters to `Shesha.__init__`. When not provided, current
defaults apply. Fully backward-compatible.

## Constructor Changes

```python
def __init__(
    self,
    model: str | None = None,
    storage_path: str | Path | None = None,
    api_key: str | None = None,
    pool_size: int | None = None,
    config: SheshaConfig | None = None,
    # New DI parameters
    storage: StorageBackend | None = None,
    engine: RLMEngine | None = None,
    parser_registry: ParserRegistry | None = None,
    repo_ingester: RepoIngester | None = None,
) -> None:
```

### Behavior

| Parameter | When provided | When None (default) |
|-----------|--------------|-------------------|
| `storage` | Used directly | `FilesystemStorage(config.storage_path, ...)` |
| `engine` | Used directly | `RLMEngine(model=config.model, ...)` |
| `parser_registry` | Used directly | `create_default_registry()` |
| `repo_ingester` | Used directly | `RepoIngester(storage_path=config.storage_path)` |

### Pool management

`start()` always creates a `ContainerPool` and sets it on the engine,
regardless of whether the engine was injected or default-created.

### Type annotations

`self._storage` typed as `StorageBackend` (was already used this way downstream).
Import of `FilesystemStorage` stays at top level (needed for default construction).

## Test Plan

TDD: write failing tests first, then implement.

1. Test custom storage injection - mock StorageBackend, verify used by
   create_project/list_projects/get_project
2. Test custom engine injection - mock RLMEngine, verify Project.query() uses it
3. Test custom parser_registry injection - verify used by create_project
4. Test custom repo_ingester injection - mock, verify repo operations use it
5. Verify existing tests still pass (backward compatibility)

## Files Changed

- `src/shesha/shesha.py` - Constructor signature + init logic
- `tests/test_shesha_di.py` - New test file for DI tests
- `scratch/flaws.md` - Mark flaw as resolved
- `CHANGELOG.md` - Add entry
