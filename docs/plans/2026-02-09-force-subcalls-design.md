# Force Sub-calls: Close Structural Gaps with Reference RLM

**Date:** 2026-02-09
**Branch:** ovid/oolong-2
**Problem:** After 3 prompt iterations and 4 benchmark runs, Shesha scores ~24-27% on OOLONG vs the paper's ~56.5%. The model (gpt-5.2) prefers code-only solutions (regex) over `llm_query()` for semantic classification. Prompt encouragement alone isn't enough — the architecture must mechanically force the model to use sub-calls.

## Strategy

Close the three structural gaps between Shesha and the reference RLM that create **forcing functions** — architectural constraints that make `llm_query()` the path of least resistance rather than just the recommended path.

## Changes

### 1. REPL Output Truncation: 50K → 20K per Code Block (HIGH IMPACT)

**Why:** The reference truncates each code block output to 20,000 characters (`rlm/rlm/utils/parsing.py:67`). Shesha allows 50,000 combined. At 8K OOLONG scale (19K chars context), `print(context[0])` shows everything under the current limit — no reason to delegate. With 20K, the output is borderline at 8K scale and definitively truncated at 16K+, making `llm_query()` the only way to reason over content the model can't see.

**Current:** `engine.py:65` `max_output_chars=50000`. All code block outputs combined, then truncated.

**New:** `max_output_chars=20000`. Truncate each code block's output individually. When truncation occurs, append:
> `[Output truncated to 20,000 of {original_len} characters. Use llm_query() to analyze content you cannot see.]`

**Files:**
- `engine.py` — Change default, apply truncation per code block (inner loop ~line 477) instead of on combined output
- `prompts.py` — Adjust `wrap_repl_output` or truncate before wrapping
- Tests — Update assertions on default and truncation behavior

### 2. Iteration-0 Safeguard (HIGH IMPACT)

**Why:** The reference prevents the model from jumping to `FINAL()` on the first iteration (`rlm/rlm/utils/prompts.py:136`). Without this, gpt-5.2 routinely produces a final answer in 1 iteration (~8 seconds, zero sub-calls). This was the primary failure mode in runs #1-#3.

**Current:** `engine.py:402` — First message is the bare question.

**New:** Prepend safeguard text to the first user message:
> "You have not interacted with the REPL environment or seen your prompt / context yet. Your next action should be to look through and figure out how to answer the prompt, so don't just provide a final answer yet."

Safeguard text lives in a prompt template (not hardcoded in engine), consistent with existing prompt management.

**Files:**
- `prompts/` — New template for iteration-0 wrapper
- `engine.py` — Wrap question with safeguard before inserting as first user message
- Tests — Verify first user message includes safeguard; subsequent iterations don't

### 3. Context Metadata as Assistant Message (MEDIUM IMPACT)

**Why:** The reference sends context metadata as a fake assistant message (`rlm/rlm/utils/prompts.py:119-122`), making the model "think" it already acknowledged the data. This primes it to continue working rather than starting fresh. Shesha bakes this into the system prompt.

**Current:** Context metadata (doc count, total chars, chunk sizes) in system prompt via `PromptLoader.render_system()`.

**New:** Remove metadata from system prompt. Inject as first assistant message:
> "Your context is a list of {doc_count} documents with {total_chars} total characters, and is broken up into chunks of char lengths: {chunk_lengths}."

Conversation becomes:
```
system:    [system prompt WITHOUT context metadata]
assistant: "Your context is a list of 3 documents with 19,234 total characters..."
user:      "You have not interacted with the REPL... {question}"
```

**Files:**
- `prompts/` — New template for context metadata assistant message; remove metadata from system prompt template
- `engine.py` — Initialize messages with assistant metadata message before user question
- `loader.py` — `render_system()` no longer needs metadata params; new `render_context_metadata()` method
- Tests — Verify conversation starts with assistant message; system prompt no longer contains metadata

**Note:** Verify LiteLLM / target models accept conversations starting with an assistant message. If not, prefix with an empty user message.

## What We're NOT Doing This Round

- **Code echo in feedback** — Reference shows executed code alongside output. Low-medium impact.
- **Max-iterations graceful fallback** — Reference asks once more instead of hard-failing. Low impact.
- **Model swap** — Testing with Claude/GPT-4o. Zero code change but doesn't fix architecture. Can layer on later.

These can be added if scores remain low after this round.

## Code Documentation

All changes must include comments explaining **why** the value or behavior exists, not just what it does. For example, the 20K truncation limit should reference the paper's forcing-function rationale, not just say "truncation limit." This helps future maintainers understand that these aren't arbitrary numbers — they're deliberate architectural choices from the reference implementation.

## Testing Strategy

All changes require TDD per CLAUDE.md.

**Change 1 (Truncation):**
- Test `max_output_chars` defaults to 20,000
- Test each code block output truncated individually (not combined)
- Test truncated output includes the "Use llm_query()" nudge
- Test outputs under 20K are not truncated

**Change 2 (Iteration-0 safeguard):**
- Test first user message includes safeguard text
- Test safeguard references "don't just provide a final answer yet"
- Test subsequent iteration messages do NOT include safeguard

**Change 3 (Context metadata as assistant message):**
- Test conversation starts with assistant message containing doc count and total chars
- Test system prompt no longer contains document metadata
- Test `render_context_metadata()` produces expected format

## Benchmark Validation

After all three changes:
```bash
docker build -t shesha-sandbox src/shesha/sandbox/
python oolong/run_oolong_and_pairs.py --model openai/gpt-5-mini
```

**Success criteria:** The model uses `llm_query()`/`llm_query_batched()` for semantic classification (visible in traces as multiple sub-calls and multi-iteration runs). Score improvement expected but behavioral shift is the primary signal.
