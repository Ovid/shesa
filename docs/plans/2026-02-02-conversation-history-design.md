# Conversation History for Barsoom Example

**Date:** 2026-02-02
**Status:** Approved
**Scope:** `examples/barsoom.py` only

## Problem

Currently each `project.query()` call is independent. Follow-up questions with pronouns like "Who is she?" fail because the RLM has no context about previous exchanges.

## Solution

Add session-only conversation history to the interactive mode in `barsoom.py`. History is prepended to each question so the RLM has context for pronoun resolution.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | Session-only (in memory) | Simplest; matches typical chat UX |
| Mechanism | Prepend to question | No API changes; contained to barsoom.py |
| Limit | Unlimited with warning | Flexibility; user controls when to clear |
| Warning threshold | 50k chars OR 10 exchanges | Both limits for robustness |
| Warning action | Offer to clear (y/n) | Interactive but not automatic |

## Implementation

### Constants

```python
HISTORY_WARN_CHARS = 50_000
HISTORY_WARN_EXCHANGES = 10
```

### Data Structure

```python
history: list[tuple[str, str]] = []  # [(question, answer), ...]
```

### New Functions

```python
def format_history_prefix(history: list[tuple[str, str]]) -> str:
    """Format conversation history as context for a follow-up question."""
    if not history:
        return ""

    lines = ["Previous conversation:"]
    for i, (q, a) in enumerate(history, 1):
        lines.append(f"Q{i}: {q}")
        lines.append(f"A{i}: {a}")
        lines.append("")  # blank line between exchanges

    lines.append("Current question:")
    return "\n".join(lines)


def should_warn_history_size(history: list[tuple[str, str]]) -> bool:
    """Check if history is large enough to warrant a warning."""
    if len(history) >= HISTORY_WARN_EXCHANGES:
        return True
    total_chars = sum(len(q) + len(a) for q, a in history)
    return total_chars >= HISTORY_WARN_CHARS
```

### Changes to main()

1. Initialize `history = []` before interactive loop
2. Before each query, check `should_warn_history_size()` and offer to clear
3. Prepend `format_history_prefix(history)` to the question
4. After successful query, append `(user_input, result.answer)` to history

### Non-Interactive Mode

`--prompt` flag unchanged - single query, no history context.

## User Experience

```
> Who is Dejah Thoris?
She is the Princess of Helium and John Carter's love interest...

> Who is her father?
Tardos Mors is her father, the Jeddak of Helium...

[After 10 exchanges]
Warning: Conversation history is large (10 exchanges).
Clear history? (y/n): n
> ...
```

## Files Changed

- `examples/barsoom.py` - all changes contained here

## Testing

- Unit tests for `format_history_prefix()` and `should_warn_history_size()`
- Test empty history returns empty string
- Test history formatting with 1, 2, N exchanges
- Test warning triggers at character threshold
- Test warning triggers at exchange threshold
