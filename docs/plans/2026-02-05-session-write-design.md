# Session Write Feature Design

## Overview

Add a `write` command to the interactive example scripts (`repo.py` and `barsoom.py`) that saves the current session transcript to a markdown file.

## Command Syntax

- `write` - Saves to auto-generated filename like `session-2026-02-05-143022.md`
- `write myfile` - Saves to `myfile.md` (adds `.md` if not present)
- `write myfile.md` - Saves to `myfile.md` exactly as specified
- `write path/to/file.md` - Saves to specified path (creates directories if needed)

All inputs are trimmed of leading/trailing whitespace, including the filename argument.

## Output Format

Chat-style markdown with metadata header:

```markdown
# Session Transcript

- **Date:** 2026-02-05 14:30:22
- **Project:** https://github.com/Ovid/shesha
- **Exchanges:** 5

---

**User:** How does the sandbox work?

The sandbox executes code in isolated Docker containers with network isolation...

---

**User:** What about the security model?

Security is handled through two mechanisms:
1. Container isolation
2. Network whitelisting for LLM API egress only

---
```

## File Location

Files are saved to the current working directory by default. Users control the location by where they run the script or by providing a path.

## Implementation

### New Functions in `script_utils.py`

- `is_write_command(user_input: str) -> bool` - Check if input starts with "write"
- `parse_write_command(user_input: str) -> str | None` - Extract filename or return None for auto-generate
- `generate_session_filename() -> str` - Create timestamped filename like `session-2026-02-05-143022.md`
- `format_session_transcript(history: list[tuple[str, str]], project_name: str) -> str` - Format the markdown content
- `write_session(history: list[tuple[str, str]], project_name: str, filename: str | None) -> str` - Main function that handles everything and returns the path written

### Changes to Example Scripts

Both `repo.py` and `barsoom.py`:

1. Import the new utilities
2. Add check for `is_write_command()` in the interactive loop, before `is_exit_command()`
3. Call `write_session()` and print confirmation
4. Pass project name/URL for metadata context

## Error Handling

- **Directory doesn't exist:** Create it using `Path.mkdir(parents=True, exist_ok=True)`
- **Write fails:** Catch exception, print `Error saving session: <error message>`, continue loop
- **Empty session:** Print `Nothing to save - no exchanges yet.`, continue loop
- **Overwriting existing file:** Silently overwrite (no confirmation)
- **Invalid filename:** Let OS handle it and report error naturally

## User Feedback

After successful save: `Session saved to session-2026-02-05-143022.md (5 exchanges)`
