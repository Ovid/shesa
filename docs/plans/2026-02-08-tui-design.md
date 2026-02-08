# TUI Design - Claude Code-style Interactive Interface

## Overview

Replace the plain `input()`/`print()` interactive loops in `barsoom.py` and `repo.py` with a Textual-based TUI (Text User Interface) inspired by Claude Code's interface. The TUI provides a 3-pane layout with scrolling output, a live info bar, and a rich input area.

## Decisions

- **Framework:** Textual (pulls in Rich for markdown rendering)
- **Location:** `src/shesha/tui/` as a proper package, optional dep `[tui]`
- **Shared component:** Single `SheshaTUI` class used by both `barsoom.py` and `repo.py`
- **Scope:** TUI handles Q&A loop only; setup/picker flows remain plain terminal I/O
- **Markdown:** ON by default, toggled with `/markdown` command
- **Theme:** Dark by default, `/theme` command to toggle light/dark
- **`multi_repo.py`:** Not included (different interaction pattern)

## Architecture

### Module Structure

```
src/shesha/tui/
    __init__.py          # Exports SheshaTUI
    app.py               # Main Textual App subclass
    widgets/
        __init__.py
        output_area.py   # Scrolling output pane (markdown or plain)
        info_bar.py      # Status bar (project, tokens, phase)
        input_area.py    # Prompt input with multiline support
    commands.py          # Command registry & dispatch
```

### Integration

Examples configure and launch the TUI after their setup phase:

```python
from shesha.tui import SheshaTUI

# After setup/picker completes...
tui = SheshaTUI(
    project=project,
    project_name="barsoom",
    analysis_context=analysis_context,  # optional
)
tui.run()
```

Extra commands can be registered per-example:

```python
tui.register_command("/analysis", handler=show_analysis)
tui.register_command("/analyze", handler=regenerate_analysis)
```

## Layout

```
 ┌──────────────────────────────────────────────────────────────┐
 │  [Output Area]                                               │
 │                                                              │
 │  [Thought for 29 seconds]                                    │
 │  The son of Dejah Thoris and John Carter is **Carthoris      │
 │  of Helium**. He first appears in...                         │
 │                                                              │
 │  > Who is Tars Tarkas?                                       │
 │  [Thought for 15 seconds]                                    │
 │  Tars Tarkas is the Jeddak of the Tharks...                  │
 │                                                              │
 ├──────────────────────────────────────────────────────────────┤
 │ Project: barsoom │ Tokens: 116,763 (prompt: 110,473, comp: 6,290)│
 │ Phase: [13.7s] [Iteration 3] Sub-LLM query                   │
 ├──────────────────────────────────────────────────────────────┤
 │ > _                                                          │
 └──────────────────────────────────────────────────────────────┘
```

- **Output area:** Takes all remaining vertical space. Scrolls automatically. Each exchange shows the user's question (prefixed with `>`) followed by thought time and response. Markdown ON renders via Rich's Markdown; OFF shows plain text.
- **Info bar:** Fixed 2-line panel. Updates in real-time during queries.
- **Input area:** Fixed bottom panel. Single line by default, expands for multiline (up to ~8-10 lines). `>` prompt styled in brand color.
- **Borders:** Teal/cyan (`#00bcd4` or similar) matching the Shesha logo. Applied to all border lines and the outer frame.

## Input Handling

### Keyboard

| Key | Behavior |
|---|---|
| Enter | Submit input |
| Shift+Enter | Insert newline (multiline input) |
| Trailing `\` | Continue to next line (stripped before sending) |
| Up/Down arrow | Cycle through input history for the session |
| Escape (1st) | Clear input area (if text present) |
| Escape (2nd) | Cancel running query (if input empty and query in progress) |
| Ctrl+C | Exit TUI cleanly |

### Paste Detection

When pasted text contains more than 3 lines, the input area displays `[Pasted text +N lines]` as a compact summary. The full text is stored internally and sent on Enter.

### Command Auto-complete

Typing `/` triggers a completion popup above the input area showing matching commands. Filters as user continues typing. Arrow keys + Enter to select.

## Commands

All commands must start with `/` (leading whitespace OK).

| Command | Description |
|---|---|
| `/help` | Show available commands |
| `/write [filename]` | Save session transcript (always raw markdown) |
| `/markdown` | Toggle markdown rendering on/off |
| `/theme` | Toggle dark/light theme |
| `/quit` | Exit the TUI |
| `/analysis` | Show codebase analysis (repo.py only) |
| `/analyze` | Generate/regenerate analysis (repo.py only) |

## Info Bar

### Line 1 - Session Info

```
Project: barsoom │ Tokens: 116,763 (prompt: 110,473, comp: 6,290)
```

Token counts update after each query. Cumulative session totals.

### Line 2 - Phase

During query execution, shows live progress mapped from the existing `StepType` enum and `on_progress` callback:

```
Phase: [13.7s] [Iteration 3] Sub-LLM query
```

Elapsed timer ticks in real-time. States:
- **Before first progress event:** `Phase: [0.3s] Thinking...`
- **During execution:** `Phase: [13.7s] [Iteration 3] Sub-LLM query`
- **After completion:** `Phase: [52.3s] Done (3 iterations)` (briefly, then `Ready`)
- **On cancellation:** `Cancelled`

This replaces both the `ThinkingSpinner` and the `--verbose` flag.

## Theme Support

- **Dark mode (default):** Matches Shesha logo aesthetic. Dark background, teal accents.
- **Light mode:** Toggled via `/theme`. Uses Textual's CSS variant system with semantic colors (`$surface`, `$text`, `$background`).
- Teal accent color stays constant in both modes (sufficient contrast).
- Respects `NO_COLOR` convention for accessibility (polish item).

## Impact on Existing Code

### `script_utils.py` - Slimmed Down

**Retained** (pre-TUI utilities):
- `install_urllib3_cleanup_hook`
- `format_analysis_for_display`
- `format_analysis_as_context`
- `format_verified_output`
- `format_session_transcript`
- `write_session`
- `generate_session_filename`

**Absorbed by TUI** (removed from script_utils):
- `ThinkingSpinner`
- `format_progress`
- `format_thought_time`
- `format_stats`
- `format_history_prefix`
- `is_exit_command`, `is_help_command`, `is_write_command`, `is_analysis_command`, `is_regenerate_command`
- `parse_write_command`
- `should_warn_history_size`

### `barsoom.py` and `repo.py`

Interactive loops replaced with `SheshaTUI(...).run()`. Setup/picker code stays. Examples become significantly shorter.

### `multi_repo.py`

Unchanged.

## Dependencies

```toml
[project.optional-dependencies]
tui = [
    "textual>=1.0",
]
```

Textual pulls in Rich automatically. Core `shesha` library unchanged - no new required dependencies.
