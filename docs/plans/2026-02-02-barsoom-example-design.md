# Barsoom Example Design

## Overview

Interactive CLI example that loads the 7 Edgar Rice Burroughs Barsoom novels and allows users to query them using Shesha's RLM approach.

## CLI Interface

```
examples/barsoom.py [--setup] [--verbose]
```

**Flags:**
- `--setup` - Force re-upload of novels (even if project exists)
- `--verbose` - Show execution stats after each answer

**Startup behavior:**
1. Check if "barsoom" project exists
2. If missing OR `--setup` flag: upload novels with progress messages
3. Enter interactive question loop

**Exit:** Type "quit" or "exit" (case-insensitive)

## Environment

**Required:**
- `SHESHA_API_KEY` - API key for LLM provider

**Optional:**
- `SHESHA_MODEL` - Model to use (defaults to `claude-sonnet-4-20250514`)

## Setup Flow

When project is missing or `--setup` is passed:

```
Setting up Barsoom project...
Uploading: A Princess of Mars (barsoom-1.txt)
Uploading: The Gods of Mars (barsoom-2.txt)
Uploading: The Warlord of Mars (barsoom-3.txt)
Uploading: Thuvia, Maid of Mars (barsoom-4.txt)
Uploading: The Chessmen of Mars (barsoom-5.txt)
Uploading: The Master Mind of Mars (barsoom-6.txt)
Uploading: A Fighting Man of Mars (barsoom-7.txt)
Setup complete! 7 novels loaded.
```

## Interactive Loop

```
Ask questions about the Barsoom series. Type "quit" or "exit" to leave.

> Who is Dejah Thoris?

[Answer prints here]

> What happens to her in book 3?

[Answer prints here]

> exit
Goodbye!
```

**Behavior:**
- Prompt is `> `
- Empty input: re-prompt silently
- "quit" or "exit" (case-insensitive): exit gracefully

## Verbose Output

With `--verbose`, each answer includes stats:

```
> Who is Dejah Thoris?

Dejah Thoris is a princess of Helium...

---
Execution time: 12.3s
Tokens: 4,521 (prompt: 3,200, completion: 1,321)
Trace steps: 5

>
```

## Error Handling

**Missing API key:**
```
Error: SHESHA_API_KEY environment variable not set.
Set it with: export SHESHA_API_KEY=your-api-key
```

**Query errors:**
- Show error message, don't crash
- Continue the loop so user can retry

**Ctrl+C:**
- Catch gracefully, print "Goodbye!" and exit

## Implementation Details

**File:** `examples/barsoom.py`

**Storage path:** `./barsoom_data`

**Project name:** `"barsoom"`

**Book title mapping:**
```python
BOOKS = {
    "barsoom-1.txt": "A Princess of Mars",
    "barsoom-2.txt": "The Gods of Mars",
    "barsoom-3.txt": "The Warlord of Mars",
    "barsoom-4.txt": "Thuvia, Maid of Mars",
    "barsoom-5.txt": "The Chessmen of Mars",
    "barsoom-6.txt": "The Master Mind of Mars",
    "barsoom-7.txt": "A Fighting Man of Mars",
}
```

**Dataset size:** ~2.8MB / ~700-800K tokens across 7 novels - ideal RLM test case since it far exceeds context window limits.
