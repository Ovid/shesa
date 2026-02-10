# Model Display and CLI Flag Design

**Goal:** Show the active LLM model in the TUI info bar and add `--model` CLI flag to example scripts.

**Architecture:** The info bar gains a `model` field displayed on Line 1 with an abbreviated model name (date suffix stripped). Example scripts gain `--model` as highest-priority override over `SHESHA_MODEL` env var.

---

## Info Bar: Model Display

### Layout

Line 1 adds `Model: {abbreviated}` between project name and token counts:

```
Project: my-repo │ Model: claude-sonnet-4 │ Tokens: 1,234 (prompt: 800, comp: 434)
Mode: Fast │ Phase: Ready
```

### Abbreviation

A function `abbreviate_model(model: str) -> str` strips trailing date patterns from model strings:

- `claude-sonnet-4-20250514` → `claude-sonnet-4`
- `gpt-4o-2024-05-13` → `gpt-4o`
- `gemini-1.5-pro` → `gemini-1.5-pro` (no date, unchanged)

Pattern: strip `-YYYYMMDD` or `-YYYY-MM-DD` suffix (regex: `-\d{4}-?\d{2}-?\d{2}$`).

Lives in `info_bar.py` (display-only concern).

### Changes

- `InfoBarState.__init__` gains `model: str` parameter
- `InfoBarState._format()` includes `Model: {abbreviated}` on Line 1
- `InfoBar.__init__` gains `model: str` parameter, passes to state
- `SheshaTUI` passes `self._model` to `InfoBar(model=...)`

## Example Scripts: `--model` Flag

Both `repo.py` and `barsoom.py` gain:

```python
parser.add_argument("--model", type=str, help="LLM model name (overrides SHESHA_MODEL env var)")
```

Precedence (highest wins):
1. `--model` CLI flag
2. `SHESHA_MODEL` env var
3. Default: `claude-sonnet-4-20250514`

```python
model = args.model or os.environ.get("SHESHA_MODEL", "claude-sonnet-4-20250514")
```

No changes to `SheshaConfig`, `Shesha`, `RLMEngine`, or `Project`.

## Files

- Modify: `src/shesha/tui/widgets/info_bar.py` — add model field, abbreviation function, update format
- Modify: `src/shesha/tui/app.py` — pass model to InfoBar
- Modify: `examples/repo.py` — add `--model` arg, update precedence
- Modify: `examples/barsoom.py` — add `--model` arg, update precedence
- Test: `tests/unit/tui/test_info_bar.py` — test abbreviation, test model display
- Test: `tests/examples/test_repo.py` — test `--model` arg parsing
- Test: `tests/examples/test_barsoom.py` — test `--model` arg parsing
