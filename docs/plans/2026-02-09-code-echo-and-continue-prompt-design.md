# Code Echo + Per-Iteration Continue Prompt

**Date:** 2026-02-09
**Branch:** ovid/oolong-2
**Problem:** After implementing 3 structural forcing functions (20K truncation,
iteration-0 safeguard, assistant-first metadata), the model still inconsistently
uses `llm_query()` at 8K scale. Two remaining structural gaps vs the reference
RLM explain why.

## Changes

### 1. Code Echo in Iteration Feedback

**Why:** The reference sends each code block's output as a separate user message
that echoes the code back (`rlm/rlm/utils/parsing.py:93-96`). This gives the
model structured feedback about what it ran and what happened. Shesha currently
combines all outputs into one `<repl_output>` message with no code echo — the
model can't see what approaches it already tried.

**Current** (`engine.py:624-637`): After all code blocks execute, combine outputs
into one string, wrap in `<repl_output>`, append a brief reminder, add as one
user message.

**New:** Each code block produces its own user message:

```
Code executed:
\`\`\`python
{code}
\`\`\`

<repl_output type="untrusted_document_content">
{truncated_output}
</repl_output>
```

Security: `<repl_output>` tags preserved (Shesha addition, not in reference).
Truncation via `truncate_code_output()` still applied per block before wrapping.

### 2. Per-Iteration Continue Prompt

**Why:** The reference re-instructs the model to use sub-LLMs every iteration
(`rlm/rlm/utils/prompts.py:141-143`). Shesha's current reminder doesn't mention
sub-LLMs at all — it just says "Continue using the REPL environment to answer
the original query."

**New file: `prompts/iteration_continue.md`**

```markdown
The history before is your previous interactions with the REPL environment.

Think step-by-step on what to do using the REPL environment (which contains
the context) to answer the original prompt: "{question}"

Continue using the REPL environment, which has the `context` variable, and
querying sub-LLMs by writing to ```repl``` tags, and determine your answer.
Your next action:
```

This replaces the inline reminder string in `engine.py:629-633`.

## Complete Message Flow

```
system:    [system prompt]
assistant: [context metadata]
user:      [iteration_zero.md — safeguard + question]

--- iteration 0 ---
assistant: [model response with ```repl blocks]
user:      "Code executed:\n```python\n{code_1}\n```\n\n<repl_output>...\n</repl_output>"
user:      "Code executed:\n```python\n{code_2}\n```\n\n<repl_output>...\n</repl_output>"
user:      [iteration_continue.md — "Think step-by-step... querying sub-LLMs..."]

--- iteration 1+ repeats until FINAL() ---
```

Edge cases unchanged:
- No code blocks: append assistant response + code_required.md
- FINAL() found: break, no continuation message
- Dead executor: recovery logic unchanged

## Files Changed

| File | Change |
|------|--------|
| `src/shesha/rlm/engine.py` | Restructure post-execution: per-block messages + continuation prompt |
| `src/shesha/prompts/loader.py` | Add `render_iteration_continue()` |
| `src/shesha/prompts/validator.py` | Add `iteration_continue.md` schema |
| `prompts/iteration_continue.md` | NEW |
| `tests/unit/rlm/test_prompts.py` | Tests for iteration_continue rendering |
| `tests/unit/prompts/test_loader.py` | Update fixture, add render test |
| `tests/unit/prompts/test_validator.py` | Update schema assertions |
| `tests/unit/prompts/test_cli.py` | Update fixture |

## What We're NOT Doing

- Dropping `<repl_output>` security tags (Shesha security feature, keep)
- SHOW_VARS() function (reference has it, low priority)
- "Extremely important information" context framing (minor wording, not structural)
- Variable listing in output (reference shows `REPL variables: [...]`, low impact)
