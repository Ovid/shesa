# Force Sub-calls: Implementation Plan

**Design doc:** `docs/plans/2026-02-09-force-subcalls-design.md`
**Branch:** ovid/oolong-2

All steps follow TDD (Red → Green → Refactor → Commit).
Code comments must explain **why** each change exists, referencing the paper's forcing-function rationale.

---

## Step 1: Per-code-block output truncation (20K)

### 1a. RED — Write failing tests

**File:** `tests/unit/rlm/test_prompts.py`

Update existing truncation test and add new ones:

- `test_truncate_code_output_under_limit()` — Output under 20K returned unchanged.
- `test_truncate_code_output_over_limit()` — Output over 20K truncated with nudge message: `"[Output truncated to 20,000 of {N} characters. Use llm_query() to analyze content you cannot see.]"`
- `test_truncate_code_output_exact_limit()` — Output exactly at 20K returned unchanged.
- `test_wrap_repl_output_no_truncation()` — `wrap_repl_output()` no longer truncates (just wraps in tags).

These test a new `truncate_code_output(output: str, max_chars: int) -> str` function in `prompts.py`.

### 1b. GREEN — Implement truncation

**File:** `src/shesha/rlm/prompts.py`

- Add `truncate_code_output(output: str, max_chars: int = 20_000) -> str` function with docstring explaining:
  - This matches the reference RLM's 20K per-block limit (`rlm/rlm/utils/parsing.py:67`)
  - The limit is a forcing function: when the model can't see full output, it must use `llm_query()` to analyze content
  - The nudge message reinforces this by telling the model what to do
- Remove truncation logic from `wrap_repl_output()` — it becomes a pure wrapper (just adds `<repl_output>` tags). Keep `max_chars` parameter but default to a very high value as a safety net, or remove it entirely.

**File:** `src/shesha/rlm/engine.py`

- Change default `max_output_chars` from `50_000` to `20_000`. Add comment explaining the paper alignment.
- In the inner code-block loop (~line 490, after building `output`), call `truncate_code_output(output, self.max_output_chars)` before appending to `all_output`.
- At line 626, `wrap_repl_output(combined_output)` no longer needs `self.max_output_chars` since truncation already happened per-block.

**File:** `tests/unit/rlm/test_prompts.py`

- Update `test_wrap_repl_output_truncates_large_output` — this test now verifies wrap_repl_output does NOT truncate (or remove the test if wrap_repl_output no longer has truncation logic).

### 1c. REFACTOR + COMMIT

Verify all tests pass. Commit.

---

## Step 2: Iteration-0 safeguard

### 2a. RED — Write failing tests

**File:** `tests/unit/rlm/test_prompts.py`

- `test_iteration_zero_prompt_exists()` — `PromptLoader` can render an iteration-0 prompt template.
- `test_iteration_zero_prompt_contains_safeguard()` — Rendered template includes "don't just provide a final answer yet" and "look through" guidance.
- `test_iteration_zero_prompt_includes_question()` — Rendered template includes the `{question}` placeholder.

**File:** `src/shesha/prompts/validator.py`

- Add schema for new template file (e.g., `iteration_zero.md`) with required placeholder `{question}`.

### 2b. GREEN — Implement safeguard

**File:** `prompts/iteration_zero.md` (NEW)

```markdown
You have not interacted with the REPL environment or seen your prompt / context yet. Your next action should be to look through and figure out how to answer the prompt, so don't just provide a final answer yet.

{question}
```

Add comment at top or in the template explaining this matches `rlm/rlm/utils/prompts.py:136` from the reference implementation.

**File:** `src/shesha/prompts/validator.py`

- Add `"iteration_zero.md"` to `PROMPT_SCHEMAS` with `required={"question"}`.

**File:** `src/shesha/prompts/loader.py`

- Add `render_iteration_zero(self, question: str) -> str` method.

**File:** `src/shesha/rlm/engine.py`

- At line 402, change:
  ```python
  messages: list[dict[str, str]] = [{"role": "user", "content": question}]
  ```
  to:
  ```python
  # Iteration-0 safeguard: prevent model from jumping to FINAL()
  # without exploring. Matches reference rlm/rlm/utils/prompts.py:136.
  first_user_msg = self.prompt_loader.render_iteration_zero(question=question)
  messages: list[dict[str, str]] = [{"role": "user", "content": first_user_msg}]
  ```

### 2c. REFACTOR + COMMIT

Verify all tests pass. Commit.

---

## Step 3: Context metadata as assistant message

### 3a. RED — Write failing tests

**File:** `tests/unit/rlm/test_prompts.py`

- `test_context_metadata_prompt_exists()` — `PromptLoader` can render context metadata.
- `test_context_metadata_contains_doc_info()` — Rendered template includes doc count, total chars, chunk lengths.
- `test_system_prompt_no_longer_contains_metadata()` — `render_system_prompt()` no longer requires or contains `doc_count`, `total_chars`, `doc_sizes_list`. Only requires `max_subcall_chars`.

### 3b. GREEN — Implement metadata as assistant message

**File:** `prompts/context_metadata.md` (NEW)

```markdown
Your context is a list of {doc_count} documents with {total_chars:,} total characters, and is broken up into chunks of char lengths: {doc_sizes_list}.
```

**File:** `src/shesha/prompts/validator.py`

- Add `"context_metadata.md"` to `PROMPT_SCHEMAS` with `required={"doc_count", "total_chars", "doc_sizes_list"}`.

**File:** `prompts/system.md`

- Remove the `{doc_count}`, `{total_chars:,}`, `{doc_sizes_list}` placeholders from the "Available Variables and Functions" section.
- Replace line 7 (`A \`context\` variable — a list of {doc_count} document contents as strings ({total_chars:,} total characters).`) with something generic like: `A \`context\` variable — a list of document contents as strings.`
- Remove lines 8-9 (`Document sizes:` / `{doc_sizes_list}`).

**File:** `src/shesha/prompts/validator.py`

- Update `system.md` schema: remove `doc_count`, `total_chars`, `doc_sizes_list` from `required`. Only `max_subcall_chars` remains required.

**File:** `src/shesha/prompts/loader.py`

- Simplify `render_system_prompt()` signature: only takes `max_subcall_chars: int`.
- Add `render_context_metadata(self, doc_count: int, total_chars: int, doc_sizes_list: str) -> str` method.

**File:** `src/shesha/rlm/engine.py`

- Update `render_system_prompt()` call (~line 354) to only pass `max_subcall_chars`.
- Build context metadata string via `self.prompt_loader.render_context_metadata(...)`.
- Initialize messages with assistant message first:
  ```python
  # Context metadata as assistant message: primes the model to
  # continue working rather than start fresh. Matches reference
  # rlm/rlm/utils/prompts.py:119-122.
  context_metadata = self.prompt_loader.render_context_metadata(
      doc_count=len(documents),
      total_chars=total_chars,
      doc_sizes_list=doc_sizes_list,
  )
  first_user_msg = self.prompt_loader.render_iteration_zero(question=question)
  messages: list[dict[str, str]] = [
      {"role": "assistant", "content": context_metadata},
      {"role": "user", "content": first_user_msg},
  ]
  ```

### 3c. Update affected tests

**File:** `tests/unit/rlm/test_prompts.py`

- `test_system_prompt_contains_context_info()` — This currently checks for doc count and doc names in the system prompt. Update to check `render_context_metadata()` instead.
- `test_system_prompt_includes_per_document_sizes()` — Same: move assertions to `render_context_metadata()`.
- `test_system_prompt_warns_about_oversized_documents()` — Same: the EXCEEDS LIMIT warning moves to context metadata.
- All tests calling `render_system_prompt()` with 4 args must be updated to pass only `max_subcall_chars`.
- `_render_default_prompt()` helper and `_build_doc_sizes_list()` helper need updating.

### 3d. REFACTOR + COMMIT

Verify all tests pass. Commit.

---

## Step 4: Verify LiteLLM handles assistant-first conversations

### 4a. Manual check

Before benchmarking, verify that starting a conversation with `{"role": "assistant", ...}` works with LiteLLM and the target models (GPT-5-mini, GPT-5.2). If any API rejects this:

**Fallback:** Prepend a minimal user message before the assistant message:
```python
messages = [
    {"role": "user", "content": "I'm ready to work with the context."},
    {"role": "assistant", "content": context_metadata},
    {"role": "user", "content": first_user_msg},
]
```

This is a runtime concern, not a test concern — add a comment explaining the fallback if needed.

---

## Step 5: Full test suite + Docker rebuild

```bash
make all                                        # format + lint + typecheck + test
docker build -t shesha-sandbox src/shesha/sandbox/  # rebuild sandbox image
```

The Docker rebuild is needed because `runner.py` may have been modified in Fix #3. Confirm the sandbox image is current.

---

## Step 6: Benchmark validation

```bash
python oolong/run_oolong_and_pairs.py --model openai/gpt-5-mini
```

After run completes:
- Check traces for `llm_query()` / `llm_query_batched()` usage
- Count iterations per query (should be >1)
- Record scores in `oolong/oolong-research.md` as "Run #5 Results"
- Compare against runs #1-#4

---

## Files Changed Summary

| File | Change |
|------|--------|
| `src/shesha/rlm/prompts.py` | Add `truncate_code_output()`, simplify `wrap_repl_output()` |
| `src/shesha/rlm/engine.py` | Default 20K, per-block truncation, assistant metadata msg, iteration-0 safeguard |
| `src/shesha/prompts/loader.py` | Simplify `render_system_prompt()`, add `render_iteration_zero()`, `render_context_metadata()` |
| `src/shesha/prompts/validator.py` | Update system.md schema, add iteration_zero.md + context_metadata.md schemas |
| `prompts/system.md` | Remove doc metadata placeholders |
| `prompts/iteration_zero.md` | NEW — iteration-0 safeguard template |
| `prompts/context_metadata.md` | NEW — context metadata assistant message template |
| `tests/unit/rlm/test_prompts.py` | New truncation tests, safeguard tests, metadata tests; update existing tests |
