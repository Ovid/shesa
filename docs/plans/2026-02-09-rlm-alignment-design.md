# RLM Alignment: Close Gaps with Reference Implementation

**Date:** 2026-02-09
**Branch:** ovid/oolong
**Problem:** Shesha's RLM scores ~24% on OOLONG (trec_coarse) at 8K context vs the paper's ~75% for RLM(GPT-5). After 3 prompt rewrites and 2 model swaps, the root cause is identified: models prefer code-only solutions (regex) over `llm_query()` for semantic classification. Comparing our implementation with the paper's reference RLM (`rlm/`) reveals structural gaps.

## Changes

### 1. System Prompt Rewrite (`prompts/system.md`)

**Add truncation warning:**
> "You will only be able to see truncated outputs from the REPL environment, so you should use `llm_query()` to analyze variables directly."

This gives the model a practical reason to use sub-calls even when contexts are small enough to print.

**Add 3 more examples** (ported from reference `rlm/rlm/utils/prompts.py`):
- Simple single-chunk query (reference lines 21-26)
- Iterative buffer pattern with state accumulation (reference lines 29-38)
- Batched classification via `llm_query_batched` (reference lines 40-59)

Keep existing Chunk-Classify-Synthesize example. Total: 4 examples, all using `llm_query`/`llm_query_batched`.

**Add confidence framing:**
> "Your sub-LLMs are powerful — they can handle up to {max_subcall_chars:,} characters per call. Don't be afraid to put a lot of content into them."

**Add `llm_query_batched`** to the Available Functions section.

**Keep Shesha-specific additions** that don't exist in reference but are valuable:
- Phase 1 Scout
- Security warnings / untrusted content tags
- Error handling for oversized content
- Document-grounded answer rules

### 2. Add `llm_query_batched` to Sandbox

**API:** `llm_query_batched(prompts: List[str]) -> List[str]`

Single-arg style matching the reference. Each prompt is a complete string.

**Sandbox side (`runner.py`):**
- New `llm_query_batched` function registered in namespace
- Sends `{"action": "llm_query_batch", "prompts": [...]}` via JSON protocol
- Blocks until response `{"action": "llm_batch_response", "results": [...]}`

**Host side (`executor.py`):**
- Handle `"action": "llm_query_batch"` messages in the execute loop
- Dispatch calls sequentially (each prompt goes through existing `llm_query_handler`)
- Return all results in order
- If any call fails, return error for that slot, continue others

**Security:** Each prompt in the batch gets content-wrapped at the host level. Since single-arg batched calls don't separate instruction from content, the host wraps the entire prompt as untrusted content in the subcall template. This is the same security posture as the reference implementation.

### 3. Simplify `llm_query` — Make `content` Optional

**Change signature:**
```python
def llm_query(instruction: str, content: str = "") -> str:
```

**When called with one arg** (`llm_query("Classify this: ...")`):
- Host sends `instruction` directly to sub-LLM, no untrusted wrapping
- Matches reference behavior

**When called with two args** (`llm_query("Classify each entry", chunk)`):
- Existing behavior unchanged — `content` wrapped in `<untrusted_document_content>` tags

**Files changed:**
- `runner.py`: Change signature default
- `executor.py`: Skip content wrapping when `content` is empty string
- `prompts/system.md`: Document both call styles

### 4. Iteration Prompt — Remind Model of Original Query

The reference sends `USER_PROMPT_WITH_ROOT` each iteration:
> "Think step-by-step... to answer the original prompt: \"{root_prompt}\""

Shesha currently sends only raw REPL output.

**Change in `engine.py`:**

After `wrap_repl_output`, append:
```
Continue using the REPL environment to answer the original query: "{query}"
Your next action:
```

Only on iterations > 0 (first iteration already has the query in context).

## Files Affected

| File | Change |
|------|--------|
| `prompts/system.md` | Rewrite: truncation warning, 3 more examples, batched API, confidence framing |
| `src/shesha/sandbox/runner.py` | Add `llm_query_batched`, make `content` optional in `llm_query` |
| `src/shesha/sandbox/executor.py` | Handle `llm_query_batch` protocol, skip wrapping for empty content |
| `src/shesha/rlm/engine.py` | Append query reminder to iteration messages |
| `src/shesha/rlm/prompts.py` | May need helper for batch content wrapping |

## Testing Strategy

All changes require TDD per CLAUDE.md:

1. **Prompt changes:** No unit tests needed (prompt is a template file)
2. **`llm_query_batched`:** Test sandbox protocol round-trip, test with mock handler, test error in one slot
3. **Optional `content`:** Test single-arg call skips wrapping, two-arg still wraps
4. **Iteration prompt:** Test that query reminder is appended after iteration 0

## Success Criteria

Re-run OOLONG benchmark after changes. If the model now uses `llm_query()`/`llm_query_batched()` for semantic classification (visible in traces), the alignment is working regardless of final score.
