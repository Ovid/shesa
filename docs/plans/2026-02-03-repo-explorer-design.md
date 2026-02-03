# Git Repository Explorer Script Design

**Date:** 2026-02-03
**Status:** Draft

## Overview

Create an interactive script (`examples/repo.py`) that lets users explore git repositories (local or remote) using Shesha's RLM. Similar to the existing `barsoom.py` but for arbitrary codebases.

## User Interface

### Invocation

```bash
# Load specific repo
./repo.py https://github.com/user/repo
./repo.py /local/path/to/repo

# Interactive picker (no args)
./repo.py

# Flags
./repo.py <repo> --update    # Auto-apply updates without prompting
./repo.py <repo> --verbose   # Show execution stats
```

### Picker (no args, repos exist)

```
Available repositories:
  1. user-repo (github.com/user/repo)
  2. local-project (/home/user/code/project)

Enter number or new repo URL: _
```

### Picker (no args, no repos)

```
No repositories loaded yet.
Enter repo URL or local path: _
```

### Update Prompt

When updates are available and `--update` not specified:

```
Updates available for user-repo.
Apply updates? (y/n): _
```

### Interactive Session

```
Loaded user-repo (142 files)
Ask questions about the codebase. Type "quit" or "exit" to leave.

> How does authentication work?
[Thought for 12 seconds]
Authentication is handled by...

> _
```

## Architecture

### Entry Flow

```
main()
├── Parse args (repo URL/path, --update, --verbose)
├── Initialize Shesha with storage path (./repo_data)
├── Determine repo to use:
│   ├── If URL/path provided → use it
│   └── If no args:
│       ├── List existing projects
│       ├── If projects exist → show numbered picker
│       └── If no projects → prompt for URL
├── Load/create project via create_project_from_repo()
├── Handle update status:
│   ├── "created" → print file count, continue
│   ├── "unchanged" → print "Using cached", continue
│   └── "updates_available":
│       ├── If --update → auto apply
│       └── Else → prompt y/n
└── Enter interactive REPL loop
```

### File Structure

| File | Action | Description |
|------|--------|-------------|
| `examples/script_utils.py` | Create | Shared utilities |
| `examples/repo.py` | Create | Git repo explorer |
| `examples/barsoom.py` | Modify | Import from script_utils.py |

### Shared Utilities (`script_utils.py`)

Extract from barsoom.py:

```python
# Constants
HISTORY_WARN_CHARS = 50_000
HISTORY_WARN_EXCHANGES = 10

# Classes
ThinkingSpinner          # Animated "Thinking..." spinner

# Functions
format_progress()        # Format step type for verbose output
format_thought_time()    # "[Thought for N seconds]"
format_stats()           # Execution stats for --verbose
format_history_prefix()  # Context prefix for follow-ups
is_exit_command()        # Check for quit/exit
should_warn_history_size()  # Check if history too large
install_urllib3_cleanup_hook()  # Suppress shutdown errors
```

### repo.py Structure

```python
#!/usr/bin/env python3
"""Interactive git repository explorer using Shesha."""

import argparse
import os
import sys
import time

from script_utils import (
    ThinkingSpinner,
    format_progress,
    format_thought_time,
    format_stats,
    format_history_prefix,
    is_exit_command,
    should_warn_history_size,
    install_urllib3_cleanup_hook,
)
from shesha import Shesha
from shesha.config import SheshaConfig

STORAGE_PATH = "./repo_data"

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    ...

def show_picker(shesha: Shesha) -> str | None:
    """Show interactive repo picker. Returns URL/path or None to exit."""
    ...

def prompt_for_repo() -> str:
    """Prompt user to enter a repo URL or path."""
    ...

def handle_updates(result, auto_update: bool) -> RepoProjectResult:
    """Handle update prompting. Returns updated result if applied."""
    ...

def main() -> None:
    """Main entry point."""
    ...
```

## Features

### From barsoom.py (included)

- `--verbose` flag for execution stats
- Thinking spinner animation
- Conversation history with context for follow-ups
- History size warnings (10 exchanges or 50k chars)
- urllib3 cleanup hook

### From barsoom.py (excluded)

- `--prompt` single query mode (interactive only)
- `--setup` force re-upload (not applicable)

### New Features

- Repo URL/path as positional argument
- `--update` flag for auto-applying updates
- Interactive picker when no args provided
- Update detection and prompting

## Dependencies

Uses existing Shesha infrastructure:
- `shesha.create_project_from_repo()` - handles clone, ingest, update detection
- `RepoProjectResult.apply_updates()` - pulls and re-ingests when updates available
- `RepoProjectResult.status` - "created", "unchanged", or "updates_available"
