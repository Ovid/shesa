# TUI UX Fixes Design

## Problems

1. `/analysis` and `/analyze` are confusingly similar names
2. `/analysis` output renders as raw markdown (uses `add_system_message` which always uses `Static`)
3. No way to scroll the output area (InputArea holds focus, intercepts all keys)

## Changes

### 1. Rename `/analysis` to `/summary`

**File:** `examples/repo.py`

Rename the command registration from `/analysis` to `/summary`. Update description and internal reference text ("Use /summary to view" etc). Keep `/analyze` as-is.

### 2. Markdown-aware system messages

**File:** `src/shesha/tui/widgets/output_area.py`

Add `add_system_markdown(text)` method that respects the `markdown_enabled` toggle — renders with `Markdown()` when on, `Static()` when off. The `/summary` handler in `repo.py` calls this instead of `add_system_message()`.

### 3. Tab-to-toggle focus with border highlight

**Files:** `src/shesha/tui/widgets/input_area.py`, `src/shesha/tui/app.py`, CSS

Tab toggles focus between InputArea and OutputArea. When a pane has focus, it gets a bright accent border; the unfocused pane gets a dim/no border. PageUp/PageDown/arrow keys work naturally on whichever pane has focus.

**Tab key rules:**
- Completion popup active → Tab navigates completions (existing behavior, takes priority)
- Completion popup inactive → Tab toggles focus between InputArea and OutputArea

**Focus behavior:**
- OutputArea focused: arrow keys, PageUp/PageDown, Home/End scroll the output
- InputArea focused: keys work for text editing as normal
- On startup: InputArea has focus (existing behavior)
- After submitting input (Enter): InputArea keeps focus (existing behavior)

**Visual indicator:** The focused pane gets `border: solid $accent`, unfocused pane gets `border: solid $surface-darken-2` (dimmed). Both InputArea and OutputArea already have border styling that can be adjusted via `:focus` / `:focus-within` pseudo-classes.

## Files

| Action | Path |
|--------|------|
| Modify | `examples/repo.py` |
| Modify | `src/shesha/tui/widgets/output_area.py` |
| Modify | `tests/unit/tui/test_output_area.py` |
| Modify | `src/shesha/tui/widgets/input_area.py` |
| Modify | `tests/unit/tui/test_input_area.py` |
| Modify | `src/shesha/tui/app.py` |
| Modify | `tests/unit/tui/test_app.py` |
