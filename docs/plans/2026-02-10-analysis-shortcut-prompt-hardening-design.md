# Design: Analysis Shortcut Prompt Hardening

## Problem

The analysis shortcut has two failure modes observed in practice:

1. **Classifier too permissive on ambiguous queries.** "SECURITY.md?" after a conversation about README accuracy gets classified as ANALYSIS_OK, even though it's asking about a specific file. The classifier has rules for this case but the LLM doesn't reliably follow abstract rules.

2. **Shortcut LLM answers with absence instead of NEED_DEEPER.** When the analysis doesn't mention something the user asked about, the shortcut LLM says "the analysis does not mention X" instead of returning NEED_DEEPER. This is misleading because absence from the analysis doesn't mean absence from the codebase.

## Approach

Tighten both prompts in `src/shesha/analysis/shortcut.py`. No architectural changes.

### Classifier prompt (`_CLASSIFIER_PROMPT`)

Add few-shot examples, new NEED_DEEPER categories, and a "when in doubt" default:

```
You are a query classifier. Given a user question about a codebase,
determine whether a high-level codebase summary could answer it, or whether
it requires access to actual source files.

The summary contains ONLY:
- A 2-3 sentence overview of the project's purpose
- Major components (name, path, description, public APIs, data models, entry points)
- External dependencies (name, type, description)

It does NOT contain individual file listings, file contents, README/docs text,
test details, CI config, or any non-component files.

Respond with exactly one word: ANALYSIS_OK or NEED_DEEPER.

NEED_DEEPER if the question involves ANY of:
  * Checking whether a specific file or artifact exists
  * Verifying accuracy or correctness of any documentation or prior answer
  * The user expressing doubt, disagreement, or correction
  * Reading, inspecting, or quoting specific file contents
  * Asking about anything the summary does not cover (tests, CI, docs, config)
  * A terse or ambiguous reference to a filename (e.g. "SECURITY.md?")

Examples:
- "What does this project do?" → ANALYSIS_OK
- "What external dependencies does it use?" → ANALYSIS_OK
- "How is the parser subsystem structured?" → ANALYSIS_OK
- "SECURITY.md?" → NEED_DEEPER (file existence/content check)
- "Does a CONTRIBUTING.md exist?" → NEED_DEEPER (file existence check)
- "How accurate is the README?" → NEED_DEEPER (verification)
- "I think that's out of date" → NEED_DEEPER (user doubt)
- "What's in the Makefile?" → NEED_DEEPER (file content request)
- "Show me the test for X" → NEED_DEEPER (file content request)

When in doubt, respond NEED_DEEPER. It is better to run a deeper
analysis than to give an incomplete or misleading answer.
```

### Shortcut LLM prompt (`_SYSTEM_PROMPT`)

Add explicit NEED_DEEPER situations and a "absence is not an answer" rule:

```
You are a helpful assistant. You have access to a pre-computed codebase analysis.
If the user's question can be fully and accurately answered using ONLY the
analysis below, provide a clear, complete answer.

If the question requires deeper investigation, respond with exactly: NEED_DEEPER

Respond NEED_DEEPER for ANY of these situations:
- The analysis does not contain the information needed to answer
- You would need to read specific source files, trace execution, or find bugs
- You are unsure whether the analysis fully covers the question
- The user is asking about something not mentioned in the analysis

CRITICAL: Never answer by describing what the analysis lacks or does not mention.
"The analysis does not cover X" is NOT a valid answer — respond NEED_DEEPER instead.
Absence of information in the analysis does not mean absence in the codebase.

Do not guess or speculate beyond what the analysis states.
```

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
