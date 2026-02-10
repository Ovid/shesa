# /write Overwrite Protection Design

## Problem

The `/write` command in the TUI silently overwrites existing files. On macOS's
case-insensitive filesystem, `/write security` creates `security.md` which
resolves to and overwrites an existing `SECURITY.md`.

## Design

All changes are in `_cmd_write()` in `src/shesha/tui/app.py`. The
`write_transcript()` method in `session.py` stays untouched.

### Command Parsing

A trailing `!` acts as a force flag:

```
/write              -> auto-generate timestamped filename, no force
/write security     -> filename="security.md", no force
/write security!    -> filename="security.md", force=True
/write security.md! -> filename="security.md", force=True
```

The `!` is stripped before the `.md` extension logic runs.

### Existence Check

When `filepath.exists()` is True and force is False, the command shows the
actual on-disk filename (to surface case-insensitive collisions) and returns
without writing:

```
File SECURITY.md already exists. Use /write security! to overwrite.
```

To resolve the actual on-disk filename on case-insensitive filesystems:

```python
actual = next(
    (p for p in filepath.parent.iterdir() if p.name.lower() == filepath.name.lower()),
    filepath,
)
```

### Updated `_cmd_write()` Flow

1. Check for empty session (existing behavior)
2. Strip trailing `!` from args -> set `force` flag
3. Build filename (add `.md` if needed -- existing behavior)
4. If `filepath.exists()` and not `force`:
   - Resolve actual on-disk filename via parent directory scan
   - Show: `"File {actual_name} already exists. Use /write {user_input}! to overwrite."`
   - Return early
5. Call `self._session.write_transcript(filename)` (existing behavior)

### Tests

- Force flag parsing: `!` stripped, force detected, `.md` added correctly
- Existence check blocks write and shows correct message with actual filename
- Force flag bypasses existence check and overwrites
- Case-insensitive collision shows actual on-disk filename
