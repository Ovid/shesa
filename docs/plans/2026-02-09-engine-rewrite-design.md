# Engine Rewrite Design: Reference RLM Parity

**Date:** 2026-02-09
**Branch:** ovid/oolong-2
**Goal:** Rewrite Shesha's RLM engine to achieve behavioral parity with the
reference `rlm/` implementation, closing the ~30% OOLONG accuracy gap
(Shesha ~28% vs reference ~60%).

## Decisions Made

| Decision | Choice |
|----------|--------|
| Scope | Full engine rewrite (not prompt-only or adapter) |
| Sandbox | Keep Docker (ContainerExecutor + ContainerPool) |
| FINAL_VAR | Add support (sandbox protocol already supports it) |
| SHOW_VARS | Add support (new sandbox function) |
| Security tags | Strip for now (no `<repl_output>`, no `<untrusted_document_content>`) |
| System prompt | Reference text verbatim |
| REPL variable listing | Add to sandbox protocol and code echo |

## TODO (post-rewrite)

- Re-add `<repl_output>` and `<untrusted_document_content>` security tags
  after confirming OOLONG parity. These are important for production prompt
  injection defense but may affect LLM behavior.

## Architecture Overview

The rewrite touches the engine loop, prompt templates, and sandbox protocol
while preserving the public API, trace recording, verification, Docker
sandbox, and LLM client.

```
UNCHANGED                          CHANGED
─────────────────────              ─────────────────────
shesha.py (public API)             engine.py (main loop)
project.py                         prompts.py (format_code_echo)
config.py                          prompts/system.md
sandbox/executor.py                prompts/iteration_zero.md
sandbox/pool.py                    prompts/iteration_continue.md
trace.py                           prompts/context_metadata.md
trace_writer.py                    prompts/loader.py (signature)
verification.py                    prompts/validator.py (schemas)
semantic_verification.py           sandbox/runner.py (SHOW_VARS, vars)
llm/client.py
```

## Detailed Changes

### 1. Prompt Templates (Replace Verbatim)

#### `prompts/system.md`

Replace with the reference's `RLM_SYSTEM_PROMPT` from
`rlm/rlm/utils/prompts.py:6-91`. Key differences from current Shesha:

- Describes `SHOW_VARS()` and `FINAL_VAR(variable_name)` functions
- Says "500K chars" directly instead of `{max_subcall_chars:,}`
- Uses `llm_query(prompt)` single-arg style (matches Shesha sandbox)
- No security warning sections (stripped per decision)
- No "Document-Grounded Answers" section
- No `<repl_output>` tag references
- Slightly different example set (same patterns, different wording)

**Consequence:** `PromptLoader.render_system_prompt()` loses its
`max_subcall_chars` parameter — the value is hardcoded in the prompt text.

#### `prompts/iteration_zero.md`

Replace with:
```
You have not interacted with the REPL environment or seen your prompt /
context yet. Your next action should be to look through and figure out how
to answer the prompt, so don't just provide a final answer yet.

Think step-by-step on what to do using the REPL environment (which contains
the context) to answer the original prompt: "{question}"

Continue using the REPL environment, which has the `context` variable, and
querying sub-LLMs by writing to ```repl``` tags, and determine your answer.
Your next action:
```

The reference combines the safeguard with `USER_PROMPT_WITH_ROOT` on
iteration 0. Shesha currently only has the safeguard + bare question.

#### `prompts/iteration_continue.md`

Replace with:
```
The history before is your previous interactions with the REPL environment.
Think step-by-step on what to do using the REPL environment (which contains
the context) to answer the original prompt: "{question}"

Continue using the REPL environment, which has the `context` variable, and
querying sub-LLMs by writing to ```repl``` tags, and determine your answer.
Your next action:
```

Nearly identical to current Shesha but adds "Think step-by-step on what to
do using the REPL environment (which contains the context) to answer the
original prompt:" prefix.

#### `prompts/context_metadata.md`

Replace with:
```
Your context is a {context_type} with {context_total_length} total characters,
and is broken up into chunks of char lengths: {context_lengths}.
```

Changes:
- Uses `context_type` (e.g., "list") instead of "list of N documents"
- Uses `context_lengths` (e.g., "[19234]") instead of per-document breakdown
- No per-document names or "EXCEEDS LIMIT" warnings

### 2. Prompt Loader (`src/shesha/prompts/loader.py`)

- `render_system_prompt()`: Remove `max_subcall_chars` parameter. The
  reference hardcodes "500K" in the prompt text.
- `render_context_metadata()`: Change signature to accept `context_type: str`
  and `context_lengths: str` instead of `doc_count`, `total_chars`,
  `doc_sizes_list`.
- `render_iteration_zero()`: No signature change (still takes `question`).
- `render_iteration_continue()`: No signature change (still takes `question`).

### 3. Prompt Validator (`src/shesha/prompts/validator.py`)

Update validation schemas to match new prompt template variables:
- `system.md`: No variables (500K hardcoded)
- `context_metadata.md`: `{context_type}`, `{context_total_length}`,
  `{context_lengths}`
- `iteration_zero.md`: `{question}`
- `iteration_continue.md`: `{question}`

### 4. Engine Rewrite (`src/shesha/rlm/engine.py`)

#### 4a. FINAL_VAR handling

The sandbox runner already sends `final_var` and `final_value` fields in the
execution result. The executor already parses them into `ExecutionResult`.
The engine currently ignores them. Add:

```python
if result.final_answer is not None:
    final_answer = str(result.final_answer) if not isinstance(result.final_answer, str) else result.final_answer
elif result.final_var is not None:
    final_answer = result.final_value or ""
```

#### 4b. Max-iterations fallback

Replace:
```python
answer = "[Max iterations reached without final answer]"
```

With a final LLM call (matches reference `rlm/rlm/core/rlm.py:324-335`):
```python
# Ask for one last attempt at an answer
fallback_messages = messages + [
    {
        "role": "assistant",
        "content": "Please provide a final answer to the user's question "
                   "based on the information provided.",
    }
]
response = llm.complete(messages=fallback_messages)
token_usage.prompt_tokens += response.prompt_tokens
token_usage.completion_tokens += response.completion_tokens
answer = response.content
```

Record as FINAL_ANSWER step with content prefixed "[max-iter fallback]".

#### 4c. Code block detection

Change regex from:
```python
pattern = r"```(?:repl|python)\n(.*?)```"
```
To (match reference `rlm/rlm/utils/parsing.py:20`):
```python
pattern = r"```repl\s*\n(.*?)\n```"
```

Only detect `repl` blocks, not `python` blocks. Matches reference behavior.

#### 4d. Code echo format

Replace the code echo message format. Currently:
```python
format_code_echo(code, output)
# → "Code executed:\n```python\n{code}\n```\n\n<repl_output ...>{output}</repl_output>"
```

New format (matches reference `rlm/rlm/utils/parsing.py:93-96`):
```python
# → "Code executed:\n```python\n{code}\n```\n\nREPL output:\n{output}\n\nREPL variables: ['x', 'answer']"
```

No `<repl_output>` security tags (stripped per decision).

#### 4e. Context metadata construction

Change how context metadata is built before the loop:
```python
# Current: per-document breakdown with names
# New: simple type + lengths like reference
context_type = "list" if len(documents) > 1 else "str"
context_lengths = [len(d) for d in documents]
context_total_length = sum(context_lengths)
# Truncate if > 100 chunks (reference does this)
if len(context_lengths) > 100:
    others = len(context_lengths) - 100
    context_lengths_str = str(context_lengths[:100]) + f"... [{others} others]"
else:
    context_lengths_str = str(context_lengths)

context_metadata = self.prompt_loader.render_context_metadata(
    context_type=context_type,
    context_total_length=context_total_length,
    context_lengths=context_lengths_str,
)
```

Note: Shesha always passes a list to the sandbox. The reference passes a
string when the input is a string. For OOLONG (1 document), the reference
says `context_type = "str"` and the model accesses `context[:N]`. Shesha
says `context_type = "list"` and the model accesses `context[0][:N]`.
This difference is intentional — Shesha's multi-document abstraction is
correct. The system prompt examples show both patterns.

Wait — actually, to truly match reference behavior for single-document
queries, we should consider: when there's exactly 1 document, should we
set `context = documents[0]` (a string) instead of `context = [documents[0]]`
(a list with one element)?

**Decision: Keep context as list.** The reference's prompt handles both.
Shesha's system prompt examples already use `context[0]`. If OOLONG scores
don't match after the rewrite, this is a knob to try.

#### 4f. Remove `MAX_SUBCALL_CHARS` import

The engine currently imports `MAX_SUBCALL_CHARS` from `shesha.rlm.prompts`
and uses it for the system prompt and for doc-size warnings. Since the
system prompt now hardcodes "500K":
- Remove from system prompt rendering
- Keep using `self.max_subcall_content_chars` for the actual size check
  in `_handle_llm_query()`

### 5. Sandbox Runner (`src/shesha/sandbox/runner.py`)

#### 5a. Add `SHOW_VARS()` function

```python
def show_vars():
    """List all non-private variables in the REPL namespace."""
    available = {
        k: type(v).__name__
        for k, v in NAMESPACE.items()
        if not k.startswith("_")
        and k not in BUILTINS_SET
    }
    if not available:
        return "No variables created yet. Use ```repl``` blocks to create variables."
    return f"Available variables: {available}"
```

Where `BUILTINS_SET` is a frozenset of the built-in function names
(`llm_query`, `llm_query_batched`, `FINAL`, `FINAL_VAR`, `SHOW_VARS`,
`FinalAnswer`, `FinalVar`, `context`).

Register in `register_builtins()`: `NAMESPACE["SHOW_VARS"] = show_vars`

#### 5b. Add variable listing to execution results

After executing code, include non-private variable names and types:

```python
def _list_vars():
    return {
        k: type(v).__name__
        for k, v in NAMESPACE.items()
        if not k.startswith("_")
        and k not in BUILTINS_SET
    }
```

In `execute_code()`, add to result dict:
```python
return {
    "status": "error" if error else "ok",
    "stdout": stdout_capture.getvalue(),
    "stderr": stderr_capture.getvalue(),
    "return_value": return_value,
    "error": error,
    "vars": _list_vars(),  # NEW
}
```

### 6. Executor (`src/shesha/sandbox/executor.py`)

#### 6a. Parse `vars` from execution response

Add to `ExecutionResult`:
```python
vars: dict[str, str] | None = None
```

In the response parsing:
```python
ExecutionResult(
    ...
    vars=result.get("vars"),
)
```

### 7. Code Echo with Variables (`src/shesha/rlm/prompts.py`)

Update `format_code_echo()`:

```python
def format_code_echo(code: str, output: str, vars: dict[str, str] | None = None) -> str:
    parts = [f"Code executed:\n```python\n{code}\n```\n\nREPL output:\n{output}"]
    if vars:
        parts.append(f"\nREPL variables: {list(vars.keys())}")
    return "\n".join(parts)
```

Remove `wrap_repl_output()` function (no longer used).

### 8. Engine Loop: Variable Passing

Update the code echo section in the engine loop to pass `vars`:

```python
for code_block, output, exec_result in zip(code_blocks, all_output, exec_results):
    messages.append({
        "role": "user",
        "content": format_code_echo(code_block, output, exec_result.vars),
    })
```

This requires keeping `exec_results` alongside `all_output` in the loop.

## What's Preserved

- **Traces:** All `Trace`, `TraceStep`, `StepType`, `IncrementalTraceWriter`
  infrastructure unchanged. Every step still recorded. Same JSONL format.
- **Public API:** `Shesha`, `SheshaConfig`, `project.query()`,
  `project.upload()`, `result.answer`, `result.token_usage.total_tokens`
  — all unchanged.
- **Verification:** Citation and semantic verification still run post-FINAL.
- **Docker sandbox:** `ContainerExecutor`, `ContainerPool` — unchanged
  (minor protocol addition: `vars` field).
- **LLM client:** `LLMClient` with retry logic — unchanged.
- **Sub-LLM handling:** `_handle_llm_query()` and `_handle_llm_query_batch()`
  — unchanged (still uses `_subcall_lock`, still records trace steps).
- **Dead executor recovery:** Still detects and replaces broken containers.
- **Execution mode:** "fast" (parallel subcalls) vs "deep" (sequential)
  — unchanged.

## Verification Plan

1. Run `make all` — all existing tests must pass (or be updated if they
   test changed behavior like code echo format).
2. Run `python oolong/run_reference_implementation.py` — confirm reference
   still scores ~60%.
3. Run `python oolong/run_oolong_and_pairs.py` — Shesha should now score
   close to the reference's ~60%.
4. Compare traces between Shesha and reference to identify any remaining
   behavioral differences.

## Risk Analysis

| Risk | Mitigation |
|------|------------|
| Test breakage | Update tests to match new behavior |
| Prompt regression | Reference prompt is proven to work (scored 60%) |
| Context type mismatch | Shesha uses list, reference uses string; keep list, monitor |
| Security regression | TODO to re-add security tags; not production-facing yet |
| Trace compatibility | Trace format unchanged; only message content differs |
