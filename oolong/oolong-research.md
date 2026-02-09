# OOLONG Benchmark Research

## Problem Statement

Shesha's RLM scores 0% on OOLONG (trec_coarse) with gpt-5.2. The paper reports
~68% for RLM(GPT-5) on the same benchmark. Something is fundamentally wrong with
how the RLM explores these tasks.

## What OOLONG Requires

The trec_coarse split contains 188 general-knowledge questions per context window.
Each question belongs to one of 6 semantic labels:
- numeric value
- description and abstract concept
- human being
- location
- entity
- abbreviation

**Labels are NOT in the data.** The context only contains the questions (with dates,
user IDs). The model must **semantically classify** each question, then answer
aggregate statistical queries like:
- "Which label is least common?"
- "Is label X more/less/same frequency as label Y?"

This requires O(N) semantic reasoning — every entry must be examined.

## Root Cause: RLM Uses Grep Instead of Semantic Classification

### Evidence from execution traces (2026-02-09 run)

**Trace 1** — Question: "Which label is least common?"
- Gold: `human being` | Predicted: `numeric value` | Score: 0.0
- The model ran `re.findall(re.escape(lab), doc0)` for each label string
- Found: all labels appear exactly 2 times (from header/footer text listing categories),
  except "abbreviation" (11 times — because questions literally ask "What is the
  abbreviation for...")
- Picked "numeric value" as least common (tied at 2)
- **Zero `llm_query()` calls. One iteration. ~2,600 tokens. Done in 8 seconds.**

**Trace 2** — Question: "Is 'numeric value' more/less/same as 'description and abstract concept'?"
- Gold: `more common than` | Predicted: `same frequency as` | Score: 0.0
- Same regex approach — both labels match 2 times (from the header text)
- Concluded "same frequency"
- **Zero `llm_query()` calls. One iteration. ~2,600 tokens. Done in 7 seconds.**

### The pattern across all 4 completed queries

| ID | Gold | Predicted | llm_query calls | Iterations |
|----|------|-----------|-----------------|------------|
| 13000009 | human being | numeric value | 0 | 1 |
| 13000010 | more common than | same frequency as | 0 | 1 |
| 13000011 | more common than | same frequency as | 0 | 1 |
| 13000012 | less common than | same frequency as | 0 | 1 |

The model never attempts semantic classification. It treats label names as literal
strings to grep for, completely missing the point of the task.

## Why the RLM Takes This Shortcut

The system prompt contains guidance that actively discourages the correct approach:

1. **"Minimize sub-LLM calls"** — "Aim for 1-3 calls maximum per query"
2. **"Do NOT loop over documents calling llm_query() on each one individually"**
3. **"CRITICAL: Execute immediately"** — encourages rushing to FINAL()

OOLONG requires the model to use `llm_query()` to classify entries (either individually
or in batches), which directly conflicts with guidance #1 and #2.

## What the Paper Says About This

From Section 3.1:
- Qwen3-Coder "chunks by newline" and makes sub-LM calls per chunk (the correct
  approach for OOLONG)
- GPT-5 is "conservative about sub-querying LMs" — but still scores ~68%
- The paper notes the RLM system prompt "is not tuned for any particular benchmark"

The paper's system prompt likely doesn't have the aggressive "minimize sub-calls"
language that Shesha's current prompt uses.

## Scoring Verification

The `score_oolong()` function is correct for these cases:
- Exact match, substring match, numerical decay (0.75^|y-ŷ|), token-set fallback
- The predictions genuinely don't match the gold answers

## Paper's System Prompt vs Shesha's (Appendix D Comparison)

The paper's actual system prompt (from Appendix D of rlm.txt) is **diametrically
opposed** to Shesha's on the topic of sub-LLM calls.

### Paper's GPT-5 prompt (key excerpts)

> "recursively query sub-LLMs, which you are **strongly encouraged to use as much
> as possible**"

> "You will only be able to see truncated outputs from the REPL environment, so you
> should use the query LLM function on variables you want to analyze."

> "You will find this function **especially useful when you have to analyze the
> semantics** of the context."

> "first look at the context and figure out a chunking strategy, then break up the
> context into smart chunks, and **query an LLM per chunk** with a particular question
> and save the answers to a buffer, then query an LLM with all the buffers to produce
> your final answer."

> "don't be afraid to put a lot of context into them"

### Paper's Qwen3-Coder addition

The only difference for Qwen is an added cost-batching warning:

> "Be very careful about using 'llm_query' as it incurs high runtime costs. Always
> batch as much information as reasonably possible into each call (aim for around
> ~200k characters per call)."

This still encourages sub-calls — just batched efficiently.

### Shesha's current prompt (`prompts/system.md`)

> "**IMPORTANT — Minimize sub-LLM calls**: Each `llm_query()` call is expensive
> (time + tokens). Aim for **1-3 calls maximum** per query."

> "Do NOT loop over documents calling `llm_query()` on each one individually."

> "Depth through instruction quality, not additional subcalls"

### The gap

| Aspect | Paper | Shesha |
|--------|-------|--------|
| Sub-call philosophy | "use as much as possible" | "minimize, 1-3 max" |
| Semantic analysis | "especially useful for semantics" | Not mentioned |
| Looping over items | "query an LLM per chunk" | "Do NOT loop" |
| Chunking strategy | "smart chunks → sub-call per chunk → buffer" | "combine all → 1 sub-call" |
| Cost guidance | Qwen only: "batch to ~200k per call" | "1-3 calls maximum" |

### What Shesha adds that the paper lacks (keep these)

- Security: untrusted content tagging, prompt injection warnings
- Three-phase scout → search → analyze pattern
- Coverage checking guidance (15% threshold)
- Error handling patterns (ValueError on size exceed)
- Source priority (code > docs)
- Document-grounded answer requirement

## Fix Applied

**Status: Complete (prompt change) — needs OOLONG re-run to validate**

### What changed

**`prompts/system.md`** — Phase 3 section rewritten:

| Before | After |
|--------|-------|
| "Phase 3 — Analyze in one batch" | "Phase 3 — Analyze with `llm_query()`" |
| "Minimize sub-LLM calls" | "strongly encouraged to use it as much as needed" |
| "1-3 calls maximum" | Removed — no hard limit |
| "Do NOT loop over documents" | Removed |
| "Depth through instruction quality, not additional subcalls" | Removed |
| Only "combine → 1 call" example | Added "Chunk-and-Classify Pattern" example |

Key additions:
- Explicit guidance that semantic analysis requires `llm_query()` ("Code alone cannot
  determine meaning")
- "Buffer pattern for complex analysis" — chunk → sub-call per chunk → buffer →
  synthesize
- Batching efficiency guidance (aim for ~200K-400K chars per call)
- New example showing the chunk-and-classify workflow

**`tests/unit/rlm/test_prompts.py`** — 2 tests updated:
- `test_system_prompt_subcall_limit_is_1_to_3` → `test_system_prompt_encourages_subcall_use`
- `test_system_prompt_depth_through_instruction_quality` → `test_system_prompt_subcall_instruction_quality`

**All 874 unit tests pass.**

### What preserved

- Security warnings (untrusted content tagging, prompt injection)
- Phase 1 (Scout) and Phase 2 (Search) — unchanged
- Coverage checking guidance (15% threshold)
- Error handling patterns
- Source priority (code > docs)
- Document-grounded answer requirement
- Subcall instruction quality guidance (avoid brevity, ask for depth)

### Next steps

1. Re-run OOLONG benchmark to validate the fix
2. Compare traces — model should now use `llm_query()` for classification
3. If scores improve, this confirms the root cause
4. Consider cost impact — more sub-calls = higher API cost per query
