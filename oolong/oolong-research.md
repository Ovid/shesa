# OOLONG Benchmark Research

## Problem Statement

Shesha's RLM scores 0% on OOLONG (trec_coarse) with gpt-5.2. The paper reports
~68% for RLM(GPT-5) on the same benchmark. Something is fundamentally wrong with
how the RLM explores these tasks.

Goal is NOT to increase our OOLONG score. It's to increase our accuracy. That
will naturally increase our OOLONG score.

We use ./oolong/run_oolong_and_pairs.py to generate OOLONG scores.  We use
oolong/last-run.log to trace what happened when that program run (last run
only).

You must ALWAYS update this doc with our current research.

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

## Dataset Structure and Scaling

Each context window is packed with general-knowledge questions (from TREC), one per
line:

```
Date: Jun 16, 2024 || User: 98779 || Instance: Where is Glasgow ?
```

The number of questions **doubles with each context length scale**:

| Scale | Questions | Characters | ~Tokens | Fill Ratio |
|-------|-----------|------------|---------|------------|
| 8K | 188 | 19K | 5.6K | 0.69 |
| 16K | 388 | 39K | 11.5K | 0.70 |
| 32K | 787 | 77K | 23K | 0.70 |
| 64K | 1,585 | 153K | 46K | 0.70 |
| 128K | 3,182 | 317K | 94K | 0.72 |
| 256K | 6,374 | 618K | 185K | 0.71 |
| 512K | 12,760 | 1.2M | 369K | 0.70 |
| 1M | 25,531 | 2.5M | 744K | 0.71 |

Actual token count is ~70% of the nominal `context_len` label. Each question is
~97-100 characters including metadata. The dataset has 2 context windows per length
and 25 benchmark questions per window.

### Why RLMs should win

The paper categorizes benchmarks by complexity:
- **S-NIAH**: O(1) — find one needle regardless of context size
- **OOLONG**: O(N) — classify and aggregate ALL N entries
- **OOLONG-Pairs**: O(N²) — find pairs across ALL entries

A base model must hold everything in its attention window and reason over it at once.
An RLM can chunk the data, classify per chunk via `llm_query()`, and aggregate. The
paper reports RLM outperforms base by ~28% (GPT-5) on OOLONG and the gap is even
more dramatic on OOLONG-Pairs (base <0.1%, RLM 23-58%).

### Current test scope

Our runs only test the **8K** window (188 questions, 19K chars) since
`MAX_WINDOWS_PER_LEN=1` and it processes lengths in order. This is the easiest
scale — if we can't get it right here, larger scales won't work either.

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

## Fix #1: Remove sub-call minimization from system prompt

**Status: Applied (commit 8023a6f) — validated, insufficient**

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

---

## Run #2 Results (2026-02-09 08:08, post-fix #1)

**Score: ~27% (6.75/25)** — up from 0%, but far from the paper's ~68%.

All 25 oolong questions + 1 pairs task completed before keyboard interrupt.

### Full results

| ID | Gold | Predicted | Score | Category |
|----|------|-----------|-------|----------|
| 13000009 | human being | cannot be determined from the provided text | 0.0 | label |
| 13000010 | more common than | same frequency as | 0.0 | comparison |
| 13000011 | more common than | same frequency as | 0.0 | comparison |
| 13000012 | less common than | same frequency as | 0.0 | comparison |
| 13000013 | less common than | same frequency as | 0.0 | comparison |
| 13000014 | less common than | less common than abbreviation | **1.0** | comparison |
| 13000015 | less common than | same frequency as | 0.0 | comparison |
| 13000016 | less common than | same frequency as | 0.0 | comparison |
| 13000017 | less common than | less common than abbreviation | **1.0** | comparison |
| 13000018 | less common than | same frequency as | 0.0 | comparison |
| 13000019 | less common than | same frequency as | 0.0 | comparison |
| 13000020 | less common than | less common than abbreviation | **1.0** | comparison |
| 13000021 | less common than | same frequency as | 0.0 | comparison |
| 13000022 | less common than | less common than abbreviation | **1.0** | comparison |
| 13000023 | [28] | 0 | 0.0 | count |
| 13000024 | [23] | 2 | 0.0 | count |
| 13000025 | [20] | 2 | 0.0 | count |
| 13000026 | [35] | 0 | 0.0 | count |
| 13000027 | [40] | 2 | 0.0 | count |
| 13000028 | [42] | 0 | 0.0 | count |
| 13000029 | [94706] | User: 94706 | **1.0** | user-id |
| 13000030 | human being | human | 0.0 | label |
| 13000031 | human being | human being | **1.0** | label |
| 13000032 | [1] | 0 | 0.75 | count |
| 13000033 | [90816] | (long refusal) | 0.0 | user-id |

### Pattern analysis

**What scores 1.0 — and why it's misleading:**
- **"X is less common than abbreviation"** (IDs 14, 17, 20, 22): The word "abbreviation"
  appears 11 times in questions like "What is the abbreviation for...", so even a
  grep-based approach gets these right by accident. All other comparisons still fail.
- **User ID extraction** (ID 29): Straightforward text lookup, no semantic analysis.
- **"human being" label** (ID 31): Got this one right but missed ID 30 ("human"
  instead of "human being" — close miss).

**What still fails — the same core problem:**
- **Comparison questions**: 10 of 13 wrong, all answering "same frequency as" — the
  model is still counting substring matches of label names in the header (2 each),
  not classifying questions semantically.
- **Count questions**: Gold answers are real label frequencies (28, 23, 20, 35, 40, 42).
  Model answers 0 or 2 for all of them — still counting header mentions.
- **ID 13000009**: Now says "cannot be determined from the provided text" instead of
  guessing wrong. The model *recognizes* it can't answer from text alone, but still
  doesn't reach for `llm_query()`.

**Per-query timing**: 12-30 seconds each — consistent with zero sub-calls. If the
model were making `llm_query()` calls, each query would take much longer.

### Conclusion from run #2

The prompt change removed the prohibition against sub-calls, and the model is now
slightly less confident in its regex approach (ID 9 admits it can't determine the
label). But it **still isn't using `llm_query()`**. Removing the "don't do X"
guidance wasn't enough — the model needs stronger positive encouragement or a
different prompting strategy to actually invoke sub-calls.

### Trace analysis from run #2

**Trace for ID 13000009** ("Which label is least common?"):
- The model DID use `llm_query()` this time — 1 sub-call (improvement over run #1's zero)
- But it followed the **Search-then-Analyze** pattern: grepped for keyword matches,
  combined 16K chars of snippets around label-name mentions, sent those to `llm_query()`
- The sub-LLM correctly responded "cannot be determined from the provided text" because
  the keyword excerpts don't contain labeled data — just the label names in the header
- **1 iteration, 1 sub-call, ~14s** — the model tried the right tool but on the wrong
  content

**Trace for pairs task** (the 57KB trace — most complex):
- Model used `llm_query()` 3 times across 3 iterations
- Iteration 0: crashed (tried `import pandas`, not in sandbox; multiple code blocks
  cascaded NameErrors)
- Iteration 1: used `llm_query()` to understand data format (good!), then tried to
  classify with only 3 labels (NUMERIC-VALUE, LOCATION, OTHER) — too coarse for the
  task which needs all 6 labels. Also sent empty content to classifier (0 chars)
  because JSONL parsing failed and the regex extraction code hadn't run yet.
- Iteration 2: properly parsed data with regex (188 instances extracted!), used keyword
  heuristics for most classifications, sent only 11 "ambiguous" questions to
  `llm_query()` for classification. Found 29 eligible users / 406 pairs vs gold 496
  pairs (f1=0.004 due to precision issues).

**Key findings:**
1. The model IS now using `llm_query()` — the prompt change worked for encouraging
   sub-calls
2. But for **oolong classification questions**, it follows the Search-then-Analyze
   pattern (grep → excerpts → 1 llm_query on excerpts) instead of the
   Chunk-and-Classify pattern (classify all 188 entries → aggregate)
3. The model doesn't grasp that **every question needs semantic classification**. It
   uses `llm_query()` only as a final analysis step on pre-filtered excerpts, not as
   the classification mechanism.
4. For pairs tasks, the model makes a genuine attempt at classification but uses
   heuristic regex first and only falls back to `llm_query()` for "ambiguous" cases
   — missing many entries that need semantic judgment.

### Root cause refinement

The prompt provides two example patterns:
1. **Search-then-Analyze** — grep/regex → combine excerpts → 1 llm_query call
2. **Chunk-and-Classify** — chunk content → llm_query per chunk → buffer → synthesize

The model **defaults to pattern #1** for all questions, even when pattern #2 is
appropriate. It treats `llm_query()` as a final-step analyzer rather than a per-item
classifier. The Search-then-Analyze example appears first and is more detailed, so
the model anchors on it.

### Next steps (from run #2)

The model needs to **recognize when to use each pattern**. Options:

1. **Reorder/reweight the examples** — put Chunk-and-Classify first since it's the
   more important pattern for information-dense tasks
2. **Add explicit decision guidance** — "If the question asks about classification,
   labeling, or counting across many items, use the Chunk-and-Classify pattern"
3. **Simplify the prompt radically** — the paper's prompt has NO examples. It just
   says "chunk → sub-call per chunk → buffer → synthesize." Maybe the detailed
   examples are doing more harm than good by anchoring on Pattern #1.
4. **Remove the Search-then-Analyze example entirely** — it may be training the model
   to default to regex-first approaches. The Chunk-and-Classify pattern subsumes it
   (you can always search first, then classify the results).

---

## Fix #2: Radical prompt simplification — remove Search-then-Analyze example

**Status: Applied (commit 10cfca6) — validated, no improvement**

### Rationale

Run #2 showed the model anchors on whichever example pattern appears first/most
prominently. The prompt had two patterns:

1. **Search-then-Analyze** (grep → excerpts → 1 llm_query) — appeared first, more
   detailed, with keyword expansion and coverage checking sub-steps
2. **Chunk-and-Classify** (chunk → llm_query per chunk → buffer → synthesize) —
   appeared second, briefer

The model defaulted to pattern #1 for ALL questions, even when pattern #2 was required.
The paper's prompt has NO examples — it just describes the chunk → sub-call → buffer
→ synthesize strategy in prose. Our detailed Search-then-Analyze example was actively
harmful.

### What changed

**`prompts/system.md`** — Radical simplification (176 → 124 lines):

| Before | After |
|--------|-------|
| Phase 1 (Scout) + Phase 2 (Search) + Phase 3 (Analyze) | Phase 1 (Scout) + Phase 2 (Analyze) |
| Search-then-Analyze example (grep → excerpts → 1 llm_query) | **Removed entirely** |
| Chunk-and-Classify example (second, briefer) | Now the **only** example ("Chunk, Classify, and Synthesize") |
| Keyword expansion guidance | Removed |
| Coverage checking (15% threshold) | Removed |
| Brainstorming step | Removed |
| "Execute immediately" in Phase 3 | Moved to Phase 2 |

Key text in Phase 2:

> "You are **strongly encouraged to use `llm_query()` as much as possible**. It is
> especially useful when you need to understand the **semantics** of the content:
> classification, labeling, comparison, summarization, or any reasoning that goes
> beyond pattern matching. Code alone cannot determine meaning — use `llm_query()`
> for that."

> "**Recommended strategy**: Look at the context and figure out a chunking strategy,
> then break the content into smart chunks, and **query `llm_query()` per chunk**"

### What preserved

- Phase 1 (Scout) — unchanged
- Security warnings (untrusted content tagging, prompt injection)
- Error handling patterns (try/except ValueError, chunk and retry)
- Source priority (code > docs)
- Document-grounded answer requirement
- Subcall instruction quality guidance (avoid brevity, ask for depth)
- Batching efficiency guidance (aim for ~200K-400K chars per call)

**`tests/unit/rlm/test_prompts.py`** — 3 tests updated:
- `test_system_prompt_contains_multi_phase_guidance` → `test_system_prompt_contains_scout_and_analyze_phases`
  (no longer checks for "search" phase)
- `test_system_prompt_contains_keyword_expansion_guidance` → `test_system_prompt_recommends_chunk_classify_synthesize`
  (checks for "chunk", "per chunk"/"each chunk", "buffer")
- `test_system_prompt_contains_coverage_verification` → replaced by the chunk_classify test above

**All 24 prompt tests pass. Full suite validation in progress.**

### Hypothesis

By removing the Search-then-Analyze example, the model should no longer anchor on
regex-first approaches. The only example now shows the correct Chunk-and-Classify
workflow. Combined with the prose guidance emphasizing semantic analysis and per-chunk
`llm_query()` calls, the model should:

1. Recognize that OOLONG questions require semantic classification
2. Use the chunk → llm_query per chunk → buffer → synthesize pattern
3. Actually classify all 188 entries instead of grep-counting label names in headers

### Expected impact

If the hypothesis is correct:
- Comparison questions should improve dramatically (from ~4/13 to ~10+/13)
- Count questions should get real frequencies (28, 23, 20, etc.) instead of 0 or 2
- Label identification questions should improve
- Overall score should approach the paper's ~68%

If the hypothesis is wrong, the model may still fall back to code-only approaches
(regex, string matching) because the "Execute immediately" instruction and the
general LLM bias toward code solutions may override the prose guidance. In that case,
we'd need to consider more drastic changes (e.g., few-shot examples in the query
itself, or modifying the RLM core loop to detect and correct non-semantic approaches).

---

## Run #3 Results (2026-02-09 08:34, post-fix #2)

**Score: ~24% (6.1/25)** — slightly WORSE than run #2's ~27%. Fix #2 was a wash.

### Full results

| ID | Gold | Predicted | Score | vs Run #2 |
|----|------|-----------|-------|-----------|
| 13000009 | human being | human being | **1.0** | +1.0 |
| 13000010 | more common than | same frequency as | 0.0 | same |
| 13000011 | more common than | same frequency as | 0.0 | same |
| 13000012 | less common than | same frequency as | 0.0 | same |
| 13000013 | less common than | same frequency as | 0.0 | same |
| 13000014 | less common than | less common than abbreviation | **1.0** | same |
| 13000015 | less common than | same frequency as location | 0.0 | same |
| 13000016 | less common than | same frequency as entity | 0.0 | same |
| 13000017 | less common than | less common than abbreviation | **1.0** | same |
| 13000018 | less common than | same frequency as location | 0.0 | same |
| 13000019 | less common than | same frequency as entity | 0.0 | same |
| 13000020 | less common than | less common than abbreviation | **1.0** | same |
| 13000021 | less common than | same frequency as entity | 0.0 | same |
| 13000022 | less common than | less common than abbreviation | **1.0** | same |
| 13000023 | [28] | 176 | 0.0 | was 0 |
| 13000024 | [23] | 15 | 0.1 | was 2 |
| 13000025 | [20] | 0 | 0.0 | was 2 |
| 13000026 | [35] | 0 | 0.0 | same |
| 13000027 | [40] | 0 | 0.0 | was 2 |
| 13000028 | [42] | 24 | 0.0 | was 0 |
| 13000029 | [94706] | How | 0.0 | **-1.0 regression** |
| 13000030 | human being | Not found in documents | 0.0 | was "human" |
| 13000031 | human being | N/A | 0.0 | **-1.0 regression** |
| 13000032 | [1] | 1 | **1.0** | was 0.75 |
| 13000033 | [90816] | 94706 | 0.0 | same |

### What changed vs run #2

**Improvements:**
- ID 9: label now correct "human being" (+1.0)
- ID 32: exact count match (+0.25)
- ID 24: closer prediction (15 vs gold 23, was 2)
- Count predictions now show real-looking numbers (176, 15, 24) instead of just 0 and 2

**Regressions:**
- ID 29: user-id was correct, now returns "How" (-1.0)
- ID 31: label was correct "human being", now "N/A" (-1.0)

**Unchanged — the core problem:**
- Comparisons: 10/13 still "same frequency as" — no semantic classification
- Timing: 10-25s per query — consistent with minimal/no `llm_query()` usage

### Conclusion from run #3

Fix #2 (removing Search-then-Analyze example, simplifying to Chunk-and-Classify only)
had **no meaningful effect**. The hypothesis was wrong. The model's behavior is not
primarily driven by which examples appear in the prompt — it has a deeper bias toward
code-only solutions (regex, string matching) that persists regardless of prompt wording.

The count predictions shifting from 0/2 to 176/15/24 suggests the model is at least
*trying* to count something different (176 is close to total entries 188), but it's
still not doing per-entry semantic classification.

**Two prompt rewrites have now failed to fix the core problem.** The model won't use
`llm_query()` for per-item classification no matter how we describe the strategy.

---

## Root Cause Reassessment (post-fix #2)

After two prompt fixes and three benchmark runs, the pattern is clear:

**The model prefers code-only solutions.** Given a Python REPL with both code tools
(regex, string ops) and an LLM tool (`llm_query()`), gpt-5.2 defaults to code even
when the task requires semantic reasoning. This is likely a property of the model, not
the prompt — it's faster, cheaper, and feels more "precise" to write code than to
delegate to a sub-LLM.

The paper's RLM(GPT-5) scored ~68% on OOLONG, which means GPT-5 *did* use sub-calls
for classification. Either:
1. GPT-5 has different behavior than gpt-5.2 in this regard
2. The paper's system prompt has subtle differences we haven't captured
3. The paper used a different prompting pipeline (e.g., per-query system prompt, or
   the question itself provides enough context to trigger classification)

### Evidence summary across 3 runs

| Run | Prompt Change | Score | llm_query usage | Core behavior |
|-----|---------------|-------|-----------------|---------------|
| #1 | Original ("minimize sub-calls, 1-3 max") | 0% | Zero calls | Pure regex |
| #2 | Removed prohibition, added encouragement | 27% | 1 call (wrong content) | Regex + 1 llm_query on excerpts |
| #3 | Removed all examples except Chunk-and-Classify | 24% | Unknown (timing suggests minimal) | Regex, slightly different counts |

## Next Steps

Prompt tuning has hit diminishing returns. Three options remain, in order of
invasiveness:

### Option A: Try a different model

The simplest test. If Claude or Qwen3-Coder follows the Chunk-and-Classify prompt
guidance while gpt-5.2 doesn't, the problem is model behavior, not our prompt. The
`--model` flag is now available:

```bash
python oolong/run_oolong_and_pairs.py --model anthropic/claude-sonnet-4-5-20250929
python oolong/run_oolong_and_pairs.py --model openai/gpt-4o
```

This also matches the paper's methodology — they tested multiple models and found
Qwen3-Coder uses sub-calls more aggressively than GPT-5.

### Option B: Inject task-specific guidance into the query

Instead of relying on the system prompt alone, prepend guidance to the user's question:

> "This task requires semantic classification of every entry. You MUST use
> `llm_query()` to classify entries in chunks — code alone cannot determine semantic
> categories."

This would go in the benchmark runner, not the system prompt (which should stay
task-agnostic). It's a form of prompt engineering at the query level rather than the
system level.

### Option C: Modify the RLM core loop

Add a "classification detector" that notices when the model is doing regex-based
counting on a classification task and injects a corrective message. This is the most
invasive option and risks overfitting to OOLONG.

### Recommendation

**Start with Option A.** It's zero-code-change and tells us whether the problem is
our prompt or the model. If a different model scores significantly higher with the
same prompt, we know the prompt is fine and gpt-5.2 is the bottleneck.

---

## Fix #3: Align with reference RLM implementation (2026-02-09)

**Status: Applied — awaiting benchmark validation**

After comparing Shesha's implementation with the paper's reference RLM (`rlm/`),
identified and fixed 5 structural gaps:

### Changes made

1. **System prompt rewrite** — Added truncation warning ("you will only see truncated
   outputs"), 4 examples (up from 1) matching the reference patterns, confidence
   framing ("sub-LLMs are powerful"), and `llm_query_batched` documentation.

2. **`llm_query_batched(prompts)`** — New concurrent sub-LLM call API matching the
   reference. Critical for OOLONG where 188 entries need classification.

3. **Optional `content` arg** — `llm_query(prompt)` now works with single arg
   (matching reference API), reducing friction. Two-arg still supported.

4. **Iteration query reminder** — Each iteration now appends "Continue using the REPL
   to answer: {query}" matching the reference's `USER_PROMPT_WITH_ROOT`.

5. **Line length fix** in engine (lint compliance).

### Hypothesis

The reference RLM makes `llm_query` the path of least resistance: simple API, many
examples, truncated output forces delegation. Shesha was making it the path of MORE
resistance: two-arg API, fewer examples, full output visible at small scales.

If this hypothesis is correct, the model should now:
- Use `llm_query()` or `llm_query_batched()` for semantic classification
- Chunk entries and classify via sub-calls rather than regex
- Produce significantly higher accuracy on comparison questions

### How to test

```bash
# Rebuild Docker image first (runner.py changed)
docker build -t shesha-sandbox src/shesha/sandbox/

# Then run benchmark
python oolong/run_oolong_and_pairs.py --model openai/gpt-5-mini
```
