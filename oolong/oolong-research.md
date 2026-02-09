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

---

## Run #4 Results (2026-02-09 13:16, post-fix #3)

**Only a pairs task result survived in `last-run.log`** (the log file is mostly null
bytes — likely a sparse/truncated write). The single meaningful line:

```
2026-02-09 13:16:21,959 DEBUG    pairs rlm t=16 f1=0.125 |pred|=1 |gold|=15
```

### Pairs task analysis

| Metric | Value | Interpretation |
|--------|-------|----------------|
| F1 | 0.125 | Very low — barely matching gold |
| \|pred\| | 1 | RLM produced only 1 user pair |
| \|gold\| | 15 | 15 pairs expected |
| Iterations (t) | 16 | Used 16 of 40 max iterations |

The RLM found 1 correct pair out of 15. With precision=1.0 (the 1 pair it found was
correct) and recall=1/15≈0.067, F1 = 2×1.0×0.067/(1.0+0.067) ≈ 0.125.

Compare to run #2's pairs result: f1=0.004, |pred|=406, |gold|=496. Run #2 had the
opposite problem — way too many predictions (low precision). Run #4 has high precision
but near-zero recall.

### What this tells us about fix #3

The iteration count (16, vs 1 in runs #1-#3 for oolong questions) suggests the model
IS now iterating more — it's not immediately jumping to FINAL(). The iteration query
reminder ("Continue using the REPL to answer: {query}") and truncation warnings may
be having some effect on encouraging multi-step reasoning.

However, the single-pair output suggests the model is still not classifying all entries
semantically. It likely classified a small subset (or only found 1 qualifying pair via
partial classification) rather than processing all 188 entries through `llm_query()`.

### Incomplete data caveat

The log is corrupted (null bytes filling most of the file). We don't have:
- Full oolong question scores (the 25 classification/comparison/count questions)
- Trace details showing what code the RLM generated
- Whether `llm_query()` / `llm_query_batched()` were actually used and how

**To get full results, the benchmark needs to be re-run with clean logging.**

---

## Current Status & Problem Summary (2026-02-09)

### The core problem

Shesha's RLM scores **~24-27% on OOLONG** (classification/comparison questions) and
**F1≈0.004-0.125 on OOLONG-Pairs**. The paper reports **~68% on OOLONG** and
**23-58% on OOLONG-Pairs** for RLM(GPT-5).

The root cause: **the model prefers code-only solutions (regex, string matching) over
semantic classification via `llm_query()`**. OOLONG requires classifying every entry
into 1 of 6 semantic labels (the labels are NOT in the data — each entry is a
general-knowledge question like "Where is Glasgow?" that must be classified as
"location"). The model instead greps for label name strings in headers/footers and
counts those literal matches.

### What we've tried (4 prompt iterations)

| Fix | What Changed | Score | Core Behavior Change |
|-----|-------------|-------|---------------------|
| Baseline | "Minimize sub-calls, 1-3 max" | 0% | Pure regex, zero llm_query() |
| Fix #1 | Removed prohibition, added encouragement | 27% | 1 llm_query() on wrong content (excerpts not full data) |
| Fix #2 | Removed Search-then-Analyze example entirely | 24% | No change — model still defaults to regex |
| Fix #3 | Aligned with reference: 4 examples, llm_query_batched, truncation warning, iteration reminder | ~12.5% F1 (pairs only, incomplete) | More iterations (16 vs 1), but still not classifying all entries |

### Why prompt tuning isn't enough

Two key observations after 4 runs:
1. **gpt-5.2 has a strong code-first bias** — given a Python REPL, it prefers regex/string
   ops over delegating to `llm_query()`, even when the prompt explicitly says to use it
2. **The model treats `llm_query()` as a final-step analyzer**, not a per-item classifier —
   it greps first, then sends excerpts to `llm_query()`, instead of sending raw chunks
   for classification

### Untested approaches (next steps)

**Option A: Try a different model** (zero code change, highest signal)
```bash
python oolong/run_oolong_and_pairs.py --model anthropic/claude-sonnet-4-5-20250929
python oolong/run_oolong_and_pairs.py --model openai/gpt-4o
```
If Claude or another model follows the Chunk-and-Classify guidance correctly, the
problem is model behavior, not our prompt. The paper found Qwen3-Coder uses sub-calls
more aggressively than GPT-5 — model choice matters.

**Option B: Task-level prompt injection** (moderate change)
Prepend classification guidance to the query itself, not just the system prompt:
> "This task requires semantic classification of every entry. You MUST use
> `llm_query()` to classify entries in chunks — code alone cannot determine semantic
> categories."
This goes in the benchmark runner (`run_oolong_and_pairs.py`), not the system prompt.

**Option C: RLM loop intervention** (most invasive)
Add a detector in the RLM loop that notices when the model writes regex-based
classification code and injects a corrective message. Risks overfitting to OOLONG.

**Recommendation: Start with Option A** — it's the cheapest experiment and gives the
most signal about whether the problem is model-specific or architectural.

---

## Fix #4: Force sub-calls via structural alignment with reference RLM

**Status: Design complete — awaiting implementation**

**Design doc:** `docs/plans/2026-02-09-force-subcalls-design.md`

### Rationale

After 3 prompt rewrites and 4 runs, the conclusion is clear: prompt encouragement
alone doesn't work. gpt-5.2 has a strong code-first bias that persists regardless of
wording. The reference RLM doesn't just *encourage* sub-calls — it creates
**architectural forcing functions** that make `llm_query()` the path of least
resistance.

Comparing Shesha against the reference (`rlm/`) reveals structural gaps that remove
these forcing functions. This fix closes the three most impactful ones.

### Changes (3 structural fixes)

**1. REPL output truncation: 50K → 20K per code block** (HIGH IMPACT)

The reference truncates each code block output to 20K chars
(`rlm/rlm/utils/parsing.py:67`). Shesha allows 50K combined. At 8K OOLONG scale
(19K chars context), `print(context[0])` shows everything — the model has no reason
to delegate. With 20K per code block:
- 8K scale (19K chars): borderline, reinforcing truncation warning
- 16K+ scale (39K+ chars): definitively truncated, forcing `llm_query()` usage

When truncation occurs, append:
> `[Output truncated to 20,000 of {N} characters. Use llm_query() to analyze
> content you cannot see.]`

**2. Iteration-0 safeguard** (HIGH IMPACT)

The reference prevents the model from jumping to `FINAL()` on iteration 0
(`rlm/rlm/utils/prompts.py:136`). Shesha's first message is the bare question —
the model routinely produces a final answer in 1 iteration (~8s, zero sub-calls).

Prepend to first user message:
> "You have not interacted with the REPL environment or seen your prompt / context
> yet. Your next action should be to look through and figure out how to answer the
> prompt, so don't just provide a final answer yet."

**3. Context metadata as assistant message** (MEDIUM IMPACT)

The reference sends context metadata as a fake assistant message
(`rlm/rlm/utils/prompts.py:119-122`), priming the model to "continue working"
rather than start fresh. Shesha bakes this into the system prompt.

Remove metadata from system prompt. Inject as first assistant message:
> "Your context is a list of {doc_count} documents with {total_chars} total
> characters, and is broken up into chunks of char lengths: {chunk_lengths}."

### Hypothesis

The reference RLM's architecture creates three forcing functions that Shesha lacks:
1. Truncation makes `llm_query()` *necessary* (can't see full output)
2. Iteration-0 guard prevents shortcuts (must explore first)
3. Assistant priming sets expectation of continued work (not one-shot answer)

With all three in place, the model should:
- Actually iterate (>1 iteration per query)
- Use `llm_query()` / `llm_query_batched()` for semantic classification
- Produce correct label frequencies instead of header-string counts

### What we're NOT doing this round

- Code echo in feedback (LOW-MEDIUM)
- Max-iterations graceful fallback (LOW)
- Model swap experiment (deferred — fix architecture first)

### How to validate

```bash
docker build -t shesha-sandbox src/shesha/sandbox/
python oolong/run_oolong_and_pairs.py --model openai/gpt-5-mini
```

**Success criteria:** Model uses `llm_query()`/`llm_query_batched()` for semantic
classification (visible in traces). Score improvement expected but behavioral shift
is the primary signal.

---

## Run #5 Results (2026-02-09 20:51, post-fix #4)

**Score: ~28% (estimated from 14 completed queries: 4/14)** — no meaningful improvement
over runs #2-#3. The three structural forcing functions did not change behavior at 8K
scale.

### Partial results (benchmark still running when analyzed)

| ID | Gold | Predicted | Score |
|----|------|-----------|-------|
| 13000009 | human being | Label: numeric value | 0.0 |
| 13000010 | more common than | same frequency as | 0.0 |
| 13000011 | more common than | same frequency as | 0.0 |
| 13000012 | less common than | same frequency as | 0.0 |
| 13000013 | less common than | same frequency as | 0.0 |
| 13000014 | less common than | less common than abbreviation | **1.0** |
| 13000015 | less common than | same frequency as location | 0.0 |
| 13000016 | less common than | same frequency as entity | 0.0 |
| 13000017 | less common than | less common than abbreviation | **1.0** |
| 13000018 | less common than | same frequency as location | 0.0 |
| 13000019 | less common than | same frequency as entity | 0.0 |
| 13000020 | less common than | less common than abbreviation | **1.0** |
| 13000021 | less common than | same frequency as entity | 0.0 |
| 13000022 | less common than | less common than abbreviation | **1.0** |

### Trace analysis — mixed sub-call usage

Examined 15 traces from this run. Key finding: **inconsistent behavior**.

**Earliest trace (ID 13000009: "Which label is least common?"):**
- 3 iterations, **zero sub-calls**
- Used `doc.count(label)` and `re.search()` — pure regex on header text
- Found all labels appear 2 times (from header), picked "numeric value"
- Duration: 26s, 10,986 tokens

**Most recent trace (ID ~13000022: "How many data points classified as numeric value?"):**
- 2 iterations, **uses `llm_query_batched()` correctly**
- Chunked 188 questions into batches of 20, sent each batch to sub-LLM for semantic
  classification with proper per-line label instructions
- This IS the correct RLM pattern — exactly what we want to see
- Duration: 95+ seconds (trace incomplete)

### Why fix #4 didn't help at 8K scale

The three structural changes were:
1. **20K per-block truncation** — but 8K context is only 19K chars, so
   `print(context[0])` fits within the limit. **Not a forcing function at this scale.**
2. **Iteration-0 safeguard** — prevents immediate FINAL(), but the model still does
   regex on iteration 1-2 before calling FINAL() on iteration 2-3
3. **Assistant-first context metadata** — primes continuation but doesn't force sub-calls

The truncation forcing function only becomes effective at **16K+ scale** (39K chars)
where `print(context[0])` would be truncated. At 8K, the model can see everything and
has no architectural reason to delegate.

### Updated run summary

| Run | Fix | Score | llm_query usage | Key finding |
|-----|-----|-------|-----------------|-------------|
| #1 | Baseline | 0% | Zero | Pure regex |
| #2 | Encouragement | 27% | 1 call (wrong content) | Regex + 1 llm_query on excerpts |
| #3 | Simplified examples | 24% | Minimal | No change |
| #4 | Corrupted log | ~12.5% F1 (pairs only) | Unknown | More iterations (16 vs 1) |
| #5 | 20K truncation + iteration-0 + assistant metadata | ~28% | **Mixed** — some queries use llm_query_batched correctly, others pure regex | Forcing functions work for SOME queries but not consistently |

---

## Reference RLM Deep Comparison (2026-02-09)

After Run #5, performed detailed comparison of Shesha's engine against the reference
implementation in `rlm/`. Found **two remaining structural gaps** beyond the three
already fixed:

### Gap 1: Code echo in iteration feedback

**Reference** (`rlm/rlm/utils/parsing.py:93-96`): Each code block's output is sent as
a **separate user message** that echoes the code back alongside the result:

```
Code executed:
\`\`\`python
{code}
\`\`\`

REPL output:
{result}
```

**Shesha** (`engine.py:636-637`): All code block outputs are combined into one
`<repl_output>` wrapper with NO code echo. The model can't see what it ran.

**Impact:** The model loses context about what approaches it already tried. Without
seeing its own code, it may re-try the same regex approach or not build on previous
work effectively.

### Gap 2: Per-iteration user prompt re-instruction

**Reference** (`rlm/rlm/utils/prompts.py:141-143`): After every iteration (not just
iteration 0), the user message explicitly re-instructs the model:

```
"The history before is your previous interactions with the REPL environment.
Think step-by-step on what to do using the REPL environment (which contains
the context) to answer the original prompt: "{root_prompt}". Continue using
the REPL environment, which has the `context` variable, and querying sub-LLMs
by writing to ```repl``` tags, and determine your answer. Your next action:"
```

**Shesha** (`engine.py:629-634`): Much weaker reminder:

```
"Continue using the REPL environment to answer the original query: "{question}"
Your next action:"
```

The reference explicitly says "querying sub-LLMs" every iteration. Shesha doesn't
mention sub-LLMs in the iteration reminder at all.

**Impact:** Each iteration is a fresh opportunity for the model to choose regex vs
llm_query(). The reference explicitly nudges toward sub-LLMs every time.

### Gap 3: "Extremely important information" framing

**Reference** (`rlm/rlm/utils/prompts.py:10`):
> "A `context` variable that contains extremely important information about your query.
> You should check the content of the `context` variable to understand what you are
> working with. Make sure you look through it sufficiently."

**Shesha**: `"A context variable — a list of document contents as strings."` — neutral,
no urgency.

**Impact:** Minor — but the stronger framing may encourage more thorough exploration
before jumping to regex solutions.

### What Shesha has that the reference lacks (KEEP)

- `<repl_output type="untrusted_document_content">` security tagging
- Prompt injection warnings
- `wrap_subcall_content()` security boundary
- Document-grounded answer requirement
- Error handling guidance (try/except ValueError pattern)
- Source priority (code > docs)

---

## Reference RLM Benchmark Comparison (2026-02-09)

### Motivation

After 5 runs and 4 prompt fixes, Shesha's OOLONG score remained at ~24-28%.
Before investing more effort in fixing Shesha's engine, we needed to answer a
fundamental question: **is the problem in the benchmark harness or in Shesha's
RLM implementation?**

### Approach

Created `oolong/run_reference_implementation.py` — a mirror of
`run_oolong_and_pairs.py` that calls the paper's reference RLM (`rlm/`)
instead of Shesha. Key properties:

- **Same scoring functions** — imported directly from `run_oolong_and_pairs.py`
  (identical `score_oolong()`, `f1_score()`, `parse_pairs_from_text()`)
- **Same dataset** — same parquet cache, same context windows, same questions
- **Same CSV format** — `ref:` prefix on model name, otherwise identical schema
- **Local REPL** — reference RLM's in-process Python sandbox (no Docker)
- **Same models** — tested with both gpt-5-mini and gpt-5.2

Design doc: `docs/plans/2026-02-09-reference-rlm-benchmark-design.md`

### Run #6: Reference RLM with gpt-5-mini (2026-02-09 22:08)

**Score: ~59% (8.8/15)** — 15 of 25 oolong questions completed before interrupt.

| ID | Gold | Reference Prediction | Score | Shesha #5 |
|----|------|---------------------|-------|-----------|
| 13000009 | human being | human being | **1.0** | 0.0 |
| 13000010 | more common than | more common than | **1.0** | 0.0 |
| 13000011 | more common than | same frequency as | 0.0 | 0.0 |
| 13000012 | less common than | less common than | **1.0** | 0.0 |
| 13000013 | less common than | same frequency as | 0.0 | 0.0 |
| 13000014 | less common than | less common than | **1.0** | 1.0 |
| 13000015 | less common than | same frequency as | 0.0 | 0.0 |
| 13000016 | less common than | same frequency as | 0.0 | 0.0 |
| 13000017 | less common than | less common than | **1.0** | 1.0 |
| 13000018 | less common than | same frequency as | 0.0 | 0.0 |
| 13000019 | less common than | same frequency as | 0.0 | 0.0 |
| 13000020 | less common than | less common than | **1.0** | 1.0 |
| 13000021 | less common than | less common than | **1.0** | 0.0 |
| 13000022 | less common than | less common than | **1.0** | 1.0 |
| 13000023 | 28 | 27 | **0.8** | 0.0 |

### Run #7: Reference RLM with gpt-5.2 (2026-02-09 22:24)

**Score: 60% (9/15)** — 15 of 25 oolong questions completed before interrupt.

| ID | Gold | Reference Prediction | Score | Shesha #5 |
|----|------|---------------------|-------|-----------|
| 13000009 | human being | human being | **1.0** | 0.0 |
| 13000010 | more common than | less common than | 0.0 | 0.0 |
| 13000011 | more common than | less common than | 0.0 | 0.0 |
| 13000012 | less common than | less common than | **1.0** | 0.0 |
| 13000013 | less common than | less common than | **1.0** | 0.0 |
| 13000014 | less common than | less common than | **1.0** | 1.0 |
| 13000015 | less common than | more common than | 0.0 | 0.0 |
| 13000016 | less common than | more common than | 0.0 | 0.0 |
| 13000017 | less common than | same frequency as | 0.0 | 1.0 |
| 13000018 | less common than | less common than | **1.0** | 0.0 |
| 13000019 | less common than | less common than | **1.0** | 0.0 |
| 13000020 | less common than | less common than | **1.0** | 1.0 |
| 13000021 | less common than | more common than | 0.0 | 0.0 |
| 13000022 | less common than | less common than | **1.0** | 1.0 |
| 13000023 | 28 | 28 | **1.0** | 0.0 |

### Analysis

#### The benchmark harness is correct

Same scoring functions, same dataset, same models — the reference RLM scores
**~60% vs Shesha's ~28%**. The problem is definitively in Shesha's RLM engine,
not the test code.

#### Error quality is fundamentally different

**Shesha's errors:** Almost all "same frequency as" — the model is counting
literal label-name string matches in header text (all appear ~2 times). This is
a methodology failure: regex instead of semantic classification.

**Reference's errors:** "more common than" (reversed direction), "less common
than" (when gold is "more common than"). The reference is doing real semantic
classification and comparison — its counts are close but sometimes wrong. These
are genuine classification/counting errors, not methodology failures.

#### Count questions prove it

ID 13000023 (gold: 28 "numeric value" questions):
- **Reference gpt-5.2:** 28 (exact match, score 1.0)
- **Reference gpt-5-mini:** 27 (off by 1, score 0.8)
- **Shesha:** 0 or 176 (not even close)

The reference is classifying all 188 entries semantically and counting correctly.
Shesha is counting something else entirely.

#### Timing confirms sub-LLM usage

| Runner | Time per question | Interpretation |
|--------|------------------|----------------|
| Shesha | 8-25 seconds | Zero or minimal `llm_query()` calls |
| Reference | 40-180 seconds | Heavy sub-LLM classification work |

The reference spends 2-10x longer per question because it's making multiple
`llm_query()` calls to classify entries in chunks. Shesha shortcuts with regex.

#### Both models perform similarly on the reference

gpt-5-mini (~59%) and gpt-5.2 (60%) produce comparable results on the reference
RLM. The model isn't the bottleneck — the architecture is.

### Updated Run Summary

| Run | Runner | Model | Fix | Score | Core Behavior |
|-----|--------|-------|-----|-------|---------------|
| #1 | Shesha | gpt-5.2 | Baseline | 0% | Pure regex, zero llm_query() |
| #2 | Shesha | gpt-5.2 | Encouragement | 27% | 1 llm_query() on wrong content |
| #3 | Shesha | gpt-5.2 | Simplified examples | 24% | No change |
| #4 | Shesha | gpt-5.2 | Reference alignment | ~12.5% F1 (pairs only) | More iterations, incomplete |
| #5 | Shesha | gpt-5.2 | Structural forcing | ~28% | Mixed — some correct, inconsistent |
| **#6** | **Reference** | **gpt-5-mini** | **N/A** | **~59%** | **Real semantic classification** |
| **#7** | **Reference** | **gpt-5.2** | **N/A** | **60%** | **Real semantic classification** |

### Conclusion

**The gap is architectural, not prompt-based.** The reference RLM's architecture
forces sub-LLM usage through:

1. **20K per-block output truncation** — model can't see full context, must
   delegate to `llm_query()`
2. **Iteration-0 safeguard** — prevents immediate FINAL(), forces exploration
3. **Per-iteration sub-LLM reminder** — explicitly says "querying sub-LLMs"
   every iteration
4. **Per-code-block feedback** — echoes code back alongside output, helping the
   model build on previous work
5. **Simple API** — `llm_query(prompt)` single-arg reduces friction

Shesha has partially implemented some of these (fixes #3-#4), but the combined
effect of all five creates a fundamentally different execution pattern. The
reference forces the model into a classify-via-sub-calls workflow; Shesha still
allows shortcuts.

### Next Steps

The reference benchmark runner (`oolong/run_reference_implementation.py`) is now
a permanent diagnostic tool. Going forward:

1. **Close remaining structural gaps** — implement the 2 gaps identified in the
   "Reference RLM Deep Comparison" section above (code echo in feedback,
   per-iteration sub-LLM reminder)
2. **Re-run Shesha benchmark after each fix** — compare against reference
   baseline (~60%)
3. **Target: Shesha within 10% of reference** — if Shesha reaches ~50%+ on
   OOLONG, the architecture is working correctly and remaining gaps are
   optimization
