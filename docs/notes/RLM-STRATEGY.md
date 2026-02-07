# RLM Strategy Log

This document tracks the evolution of Shesha's strategy for answering questions about codebases. Each section describes a strategy, the problem it solved, and its known limitations.

## Background: How the RLM Loop Works

Documents are loaded as a `context[]` array inside a Docker sandbox. The LLM generates Python code to explore them, sees the output, and repeats until it calls `FINAL("answer")`. During execution, the LLM can call `llm_query(instruction, content)` to delegate analysis of document excerpts to a sub-LLM.

The loop runs for up to 20 iterations. Each iteration is: LLM generates code -> sandbox executes it -> output fed back to LLM. The LLM's job is to scout the documents, search for relevant evidence, analyze it via sub-LLM calls, and produce a final answer.

---

## Strategy 1: Unstructured Exploration (v0.1 - v0.3)

### Approach

The system prompt gave the LLM general guidance: "peek at documents first", "filter with code", "batch aggressively", and aim for "3-5 sub-LLM calls maximum." The LLM was left to figure out its own search terms, decide when it had enough evidence, and choose how to batch content.

### What Worked

- Simple to implement and understand
- Flexible enough to handle varied question types
- LLM could adapt its strategy per question

### What Didn't Work

Running the same question ("What are the architectural flaws?") against DBIx::Class three times produced vastly different results:

| Run | Lines | Sub-LLM Calls | Findings |
|-----|-------|---------------|----------|
| dbic1.md | 70 | Few | 10 flaws, concise, some citations sparse |
| dbic2.md | 121 | Medium | 9 flaws, structured sections, abundant citations |
| dbic3.md | 199 | Many | Comprehensive with evidence sections A-I, mitigation strategies |

The problems were:

1. **Inconsistent search coverage.** Without explicit instructions to measure coverage, the LLM sometimes searched with narrow keywords and missed large parts of the corpus. One run might find 15% of docs relevant; another might find 40%.

2. **Fragmented sub-LLM calls.** The LLM often looped over documents calling `llm_query()` individually, producing many small calls (expensive, slow) instead of one large batched call. Each fragment saw only its own slice of evidence, producing weaker analysis.

3. **No ground truth on citations.** All three runs cited documents by number ("Doc **223**") and included quoted evidence. But there was no mechanism to verify that those doc IDs actually existed in the corpus or that the quoted strings appeared in those documents.

---

## Strategy 2: Structured Scout/Search/Analyze (v0.4+)

**Commit:** `7e50b7b` (2026-02-06)

### Approach

Replaced the loose guidance with three explicitly named phases in the system prompt:

**Phase 1 -- Scout (always do first).** Before choosing any search terms, print the first ~200 chars of sample documents (first 5 + some from middle/end). Understand document types and structure. Print total count and size distribution. Reason about what the documents contain before deciding search terms.

**Phase 2 -- Search broadly with coverage check.** Choose keywords based on the question AND scouting results. After searching, always print how many documents matched and what fraction of the total. If matches are below 15% on an open-ended question, brainstorm 5-10 additional search terms across categories:

- Informal language: "hack", "kludge", "workaround"
- Sentiment markers: "ugly", "terrible", "broken"
- Action markers: "TODO", "FIXME", "XXX"
- Domain-specific vocabulary

Run a second search with expanded terms and combine results. For targeted/narrow questions, low coverage is expected -- skip expansion.

**Phase 3 -- Analyze in one batch.** Send combined excerpts to a single `llm_query()` call. Only split into 2-3 batches if content exceeds the 500k-char limit. Target 1-3 calls maximum (tightened from 3-5).

### What Changed

| Aspect | Before | After |
|--------|--------|-------|
| Search terms | Ad hoc, LLM's judgment | Scouting-informed, with systematic expansion |
| Coverage check | None | Explicit: print match count and percentage |
| Expansion trigger | None | < 15% coverage on open-ended questions |
| Sub-LLM call budget | 3-5 | 1-3 (empirical finding: single large calls outperform fragments) |
| Batching | "Batch aggressively" (vague) | "Single call; only split if > 500k chars" (concrete) |

### What It Solved

- Consistent search coverage across runs (the 15% rule catches under-searching)
- Fewer, larger sub-LLM calls produce better-connected analysis
- LLM no longer loops over documents with individual `llm_query()` calls
- Scouting prevents keyword choices that miss the document structure entirely

### Known Limitations

- Coverage check is heuristic. 15% is a rule of thumb, not a guarantee.
- The LLM still controls keyword selection; scouting helps but doesn't eliminate bad choices.
- Citation accuracy is still unverified -- the LLM can still cite doc IDs that don't exist or misquote evidence.

---

## Strategy 3: Post-FINAL Citation Verification (v0.4+, unreleased)

**Commits:** `efc1737` through `a26ee33` (2026-02-07)

### Problem

Comparing the three DBIC runs showed that citations were unreliable in ways that structured prompting cannot fix:

1. **Hallucinated doc IDs.** The LLM writes "Doc **223**" in its answer. Does document 223 actually exist in this corpus? With 300+ documents, a wrong index is plausible and undetectable without checking.

2. **Fabricated quotes.** The LLM includes `"FIXME: this is rather horrific"` as evidence. Does that string actually appear in the cited document? The sub-LLM saw the evidence during analysis, but between receiving it and writing the final answer, the LLM can paraphrase, confabulate, or misattribute.

3. **No feedback loop.** Without verification, these errors accumulate silently. A user reading the answer has no way to know which citations are solid and which are invented.

### Approach

After `FINAL()` returns but before delivering the `QueryResult`, the engine runs a mechanical verification pass. This is Level 1 verification: zero LLM cost, purely mechanical checks.

**How it works:**

1. **Host-side parsing.** `extract_citations()` scans the final answer for doc references (patterns: `Doc N`, `Doc **N**`, `context[N]`, standalone `**N**`). `extract_quotes()` finds double-quoted and backtick-quoted strings >= 10 characters.

2. **Sandbox-side checking.** `build_verification_code()` generates a small Python script that runs in the existing sandbox where `context[]` is still loaded. For each cited doc ID, it attempts `context[N]` -- if IndexError, the citation is invalid. For each quote (truncated to 60 chars, case-insensitive), it checks whether the substring appears in any cited document.

3. **Result attachment.** The JSON output is parsed into a `VerificationResult` (with `Citation` and `Quote` dataclasses) and attached to `QueryResult.verification`. The `all_valid` property is True only if every citation and every quote passed.

4. **Fail-safe.** Any exception during verification yields `verification=None`. The answer is always returned regardless of verification outcome.

### Design Decisions

- **No prompt changes.** The LLM doesn't know verification is happening. It calls `FINAL()` as usual; the engine intercepts.
- **No iteration budget consumed.** Verification runs after the loop breaks.
- **Host-side parsing, sandbox-side checking.** Regex logic stays on the host; the sandbox code is just lookups. This avoids duplicating complex regex in generated code.
- **60-char truncation for quotes.** LLMs often paraphrase slightly. Matching the first 60 characters catches most real quotes while tolerating minor tail differences.
- **Case-insensitive matching.** Handles capitalization differences between the LLM's rendering and the original document.

### What It Catches

- Doc IDs that don't exist in the corpus (IndexError on `context[N]`)
- Quoted strings that don't appear in any cited document
- Attribution errors where a quote exists but not in the document the LLM claimed

### What It Does NOT Catch

This is important. Level 1 verification is mechanical. It does not evaluate meaning.

1. **Semantic accuracy.** A quote may exist in a document but not support the claim the LLM is making. "FIXME: this doesn't matter" contains "FIXME" but doesn't evidence a flaw.

2. **Paraphrased evidence.** If the LLM writes "the code returns nothing on error" but the document says "function returns null in edge case", substring matching may miss it entirely or match something unrelated.

3. **Context stripping.** A quote found in a document may have been taken out of context. Verification confirms presence, not meaning.

4. **Sub-LLM citation accuracy.** Verification only checks the final answer. If a `llm_query()` call returned incorrect citations that the main LLM incorporated, those intermediate errors are invisible.

5. **Cross-document claims.** Each quote is matched to one document (first match). Claims that synthesize across multiple documents aren't validated for the synthesis -- only for individual quote presence.

6. **False positive matches.** Short or common substrings may match in unrelated documents. The 60-char truncation and 10-char minimum help but don't eliminate this.

### Configuration

- `verify_citations` in `SheshaConfig` (default: `True`)
- Environment variable: `SHESHA_VERIFY_CITATIONS=false` to disable
- Per-engine: `RLMEngine(verify_citations=False)`

---

## Future Directions

### Level 2: Semantic Verification (not yet implemented)

Use a sub-LLM call to check whether each quote actually supports the claim it's attached to. This costs tokens but catches meaning-level errors that mechanical checks miss.

### Level 3: Coverage Verification (not yet implemented)

After the answer is produced, check whether the cited documents are representative of the full corpus. If the LLM cited 5 documents out of 300, is that because only 5 were relevant, or because the search was too narrow?

### Consistency Across Runs

The DBIC experiment showed that three runs of the same question produce different answers. Citation verification tells us which individual citations are real, but doesn't address the deeper question: are the *findings* consistent? A future strategy might run verification across multiple runs and identify findings that are cited with valid evidence in all runs.

### Verification-Informed Prompting

Currently the LLM doesn't know verification will happen. A future strategy might tell the LLM that citations will be checked, which could improve citing discipline at the source.
