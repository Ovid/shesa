# Design: Analysis Shortcut Prompt Hardening

## Problem

The analysis shortcut has two failure modes observed in practice:

1. **Classifier too permissive on ambiguous queries.** "SECURITY.md?" after a conversation about README accuracy gets classified as ANALYSIS_OK, even though it's asking about a specific file. The classifier has rules for this case but the LLM doesn't reliably follow abstract rules.

2. **Shortcut LLM answers with absence instead of NEED_DEEPER.** When the analysis doesn't mention something the user asked about, the shortcut LLM says "the analysis does not mention X" instead of returning NEED_DEEPER. This is misleading because absence from the analysis doesn't mean absence from the codebase.

## Approach

Tighten both prompts in `src/shesha/analysis/shortcut.py`. No architectural changes.

### Classifier prompt changes

Add few-shot examples and a "when in doubt" bias:

- Add 9 concrete examples (5 NEED_DEEPER, 4 ANALYSIS_OK) so the LLM has patterns to match, not just abstract rules
- Add two new NEED_DEEPER categories: "asking about things the summary doesn't cover" and "terse/ambiguous filename references"
- Add explicit default: "When in doubt, respond NEED_DEEPER"

### Shortcut LLM prompt changes

Add an explicit "absence is not an answer" rule:

- Add a CRITICAL paragraph: "Never answer by describing what the analysis lacks. 'The analysis does not cover X' is NOT a valid answer — respond NEED_DEEPER instead."
- Add bullet list of NEED_DEEPER situations including "the analysis does not contain the information needed" and "you are unsure whether the analysis fully covers the question"

## Files to change

1. `src/shesha/analysis/shortcut.py` — update `_CLASSIFIER_PROMPT` and `_SYSTEM_PROMPT`
2. `tests/unit/analysis/test_shortcut_classifier.py` — update tests that verify prompt content (e.g., `test_does_not_receive_analysis_context` checks the system prompt text)
3. `tests/unit/analysis/test_shortcut.py` — update any tests that verify `_SYSTEM_PROMPT` content

## Risk

**False NEED_DEEPER (over-conservative).** The shortcut might bail to full RLM more often. This is acceptable: it costs more tokens but produces correct answers. The few-shot examples for ANALYSIS_OK provide positive signal for genuinely answerable questions (architecture, dependencies, project purpose).

## Out of scope

- Changing the two-stage architecture (classifier + shortcut LLM)
- Changing how conversation history is formatted
- Changing the analysis generation prompt
