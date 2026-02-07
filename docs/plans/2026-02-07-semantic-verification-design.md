# Semantic Verification for RLM Findings

**Date:** 2026-02-07
**Branch:** TBD (from ovid/improve-accuracy)

## Problem

The current post-FINAL verification (`src/shesha/rlm/verification.py`) only performs
mechanical checks: do cited document IDs exist, and do quoted strings appear in the
cited documents. It does not verify whether findings are *accurate* -- whether a cited
pattern is actually a flaw, whether evidence is parroted from comments, or whether
test code is being conflated with production code.

A meta-review of an LLM-generated architectural review of DBIx::Class showed that
81% of findings were wrong:

| Category | Count | Pct |
|---|---|---|
| Parroted from comments/docs | 4 | 25% |
| Code analysis, not real flaws | 9 | 56% |
| **Genuine issues** | **3** | **19%** |

Failure modes: comment mining (reporting FIXMEs as "discoveries"), idiom
misidentification (flagging standard language patterns as flaws), test/production
conflation, and severity miscalibration (non-issues rated P0, real issues rated P1).

## Design

### Architecture

Current flow:
```
User Query -> RLM Loop -> Mechanical Verification -> Result
```

New flow with `--verify`:
```
User Query -> RLM Loop -> Mechanical Verification -> Semantic Verification -> Result
                                                          |
                                                    Layer 1: Generic adversarial review
                                                          |
                                                    Layer 2: Content-specific checks (if code)
                                                          |
                                                    Reformat output: Summary + Appendix
```

Semantic verification is a new module (`src/shesha/rlm/semantic_verification.py`),
separate from `verification.py`. Both run post-FINAL, but semantic verification runs
after mechanical verification so it can incorporate citation validity.

Semantic verification uses `llm_query()` subcalls -- the same mechanism the RLM
already uses for sub-LLM calls during analysis. No new infrastructure needed.

Verification is **opt-in** via a `verify` field on `SheshaConfig` and a `--verify`
CLI flag. When disabled (default), behavior is identical to today.

### Layer 1: Generic Adversarial Verification

Runs for all content types. A single `llm_query()` subcall that acts as a skeptical
reviewer. Prompt lives at `prompts/verify_adversarial.md`.

**Inputs:**
- The final answer (findings to verify)
- Cited documents only (extracted by parsing document references from the answer,
  reusing the citation parser from `verification.py`)

**What it checks for each finding:**
1. **Evidence support** -- Does the cited evidence actually support the claim?
2. **Context completeness** -- Is evidence quoted selectively in a way that changes
   its meaning? (e.g., quoting a FIXME but ignoring the fix three lines below)
3. **Confidence rating** -- High / Medium / Low, with a one-sentence justification

**Output format** (structured JSON):
```json
{
  "findings": [
    {
      "finding_id": "P0.1",
      "original_claim": "String eval injection surface",
      "confidence": "low",
      "reason": "Evidence shows all dynamic values pass through quotemeta(). No injection vector demonstrated.",
      "evidence_classification": "code_analysis",
      "flags": []
    }
  ]
}
```

The prompt instructs the reviewer to be genuinely skeptical -- not to rubber-stamp
findings, but to actively look for reasons each finding might be wrong. It says:
"Do not hesitate to rate findings as low confidence if it's really low confidence."

### Layer 2: Code-Specific Verification

Runs only when content is code. A second `llm_query()` subcall using
`prompts/verify_code.md`. Receives the same inputs as Layer 1 plus Layer 1's output
(so it can amend confidence ratings rather than starting from scratch).

**Content type detection:** Simple heuristic -- check file extensions in the project's
document list. If a majority of documents have recognized code extensions (`.py`,
`.pl`, `.pm`, `.js`, `.rs`, `.go`, `.java`, `.rb`, `.c`, `.cpp`, etc.), classify the
project as code. Detection happens in the semantic verification module, not the prompt.
No LLM call needed.

**What it checks:**

1. **Comment-source detection** -- Is the finding's evidence primarily drawn from
   comments, FIXMEs, TODOs, or documentation strings? If so, flag as
   `comment_derived`. Not necessarily wrong, but the user should know.

2. **Test vs. production conflation** -- Are cited files in test directories (`t/`,
   `tests/`, `test/`, `spec/`, `__tests__/`)? If so, flag as `test_code`. A
   monkeypatch in a test file is not a production concern.

3. **Idiom check** -- Is the flagged pattern a standard idiom in the detected
   language? The prompt includes guidance like: "Dynamic method installation via
   symbol table manipulation is standard Perl. Metaclass programming is standard
   Python. Reflection-based dispatch is standard Java." The LLM's own knowledge of
   language conventions handles this -- no exhaustive idiom database needed.

4. **Severity calibration** -- Given the above checks, is the severity rating
   appropriate? A comment-derived finding from test code should not be P0/Critical.

Layer 2 merges its results into Layer 1's output, potentially downgrading confidence
ratings or adding flags.

### Output Format

The `SemanticVerificationReport` reformats output into two sections.

**Section A: Verified Summary (what the boss reads)**

Only findings rated High or Medium confidence after both verification layers.
Presented with: finding title and severity, core claim, key evidence, and any
flags (e.g., "partially comment-derived" or "affects test code only"). Re-sorted
by post-verification severity.

**Section B: Verification Appendix (what engineers dig into)**

All findings that were downgraded or filtered, with: original claim, confidence
rating and reason for downgrade, flags applied, and a one-line explanation of why
it was excluded from the summary.

Example:
```
## Verified Findings (3 of 16 -- High/Medium confidence)

### P1.1: Schema clone shares storage (High confidence)
...

### P1.5: Deploy statement splitting (Medium confidence)
...

---

## Verification Appendix (13 findings filtered)

P0.1: String eval "injection surface" -- LOW CONFIDENCE
  Reason: All dynamic values pass through quotemeta(). No injection vector demonstrated.
  Flags: standard_idiom

P0.5: Monkeypatching -- LOW CONFIDENCE
  Reason: 5 of 6 instances are in test files (t/), not production code.
  Flags: test_code
...
```

### Evidence Scope

Targeted re-examination: parse findings, extract cited document references, pull
only those specific documents, and send those + findings to the verification subcall.
The meta-review showed that errors were almost entirely about misinterpreting code
the LLM did look at, not about missing code it should have looked at.

### CLI Integration

**Config** (`src/shesha/config.py`): Add `verify: bool = False` to `SheshaConfig`.

**Example scripts**: Both `examples/repo.py` and `examples/barsoom.py` get a
`--verify` argparse flag. Help text: "Run post-analysis semantic verification.
Produces higher-accuracy results by adversarially reviewing all findings. Note:
this can significantly increase analysis time and token count (typically 1-2
additional LLM calls)."

When `--verify` is passed, the script sets `verify=True` on the config. After
receiving the result, it checks `result.semantic_verification` and reformats
output into Summary + Appendix.

### Token Cost

- Layer 1: ~50-100K input tokens (findings + cited documents), ~2-5K output
- Layer 2: ~50-100K input tokens (same docs + Layer 1 output), ~2-5K output
- Worst case for code: 2 subcalls, ~200K total tokens, ~$0.60-0.75 at Sonnet pricing
- Time: ~1-2 additional minutes per analysis

## New Files

| File | Purpose |
|---|---|
| `prompts/verify_adversarial.md` | Layer 1 adversarial review prompt |
| `prompts/verify_code.md` | Layer 2 code-specific verification prompt |
| `src/shesha/rlm/semantic_verification.py` | Verification logic, report dataclass, content type detection |

## Modified Files

| File | Change |
|---|---|
| `src/shesha/config.py` | Add `verify: bool = False` |
| `src/shesha/rlm/engine.py` | Call semantic verification after mechanical verification when `verify=True` |
| `src/shesha/project.py` | Thread `verify` through to engine |
| `examples/repo.py` | Add `--verify` flag, reformat output with Summary + Appendix |
| `examples/barsoom.py` | Add `--verify` flag, reformat output with Summary + Appendix |

## Non-goals

- Replacing the existing mechanical citation verification (it stays as-is, cheap and fast)
- Verifying sub-LLM citation accuracy (only the final answer is verified)
- Exhaustive idiom databases (the LLM's own language knowledge handles this)
- Cross-run consistency checks (each run is independent)
- Full re-examination of all project documents (targeted only)
