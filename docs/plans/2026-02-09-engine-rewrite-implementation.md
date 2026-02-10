# Engine Rewrite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite Shesha's RLM engine to achieve behavioral parity with the reference `rlm/` implementation, closing the ~30% OOLONG accuracy gap (Shesha ~28% vs reference ~60%).

**Architecture:** Replace prompt templates, update sandbox protocol (SHOW_VARS, vars field), and modify engine loop (FINAL_VAR, max-iter fallback, code block regex, code echo format, context metadata). Preserve public API, trace recording, Docker sandbox, and LLM client.

**Tech Stack:** Python 3.12, pytest, Docker sandbox, LiteLLM

**Design doc:** `docs/plans/2026-02-09-engine-rewrite-design.md`

---

### Task 1: Add SHOW_VARS to Sandbox Runner

**Files:**
- Modify: `src/shesha/sandbox/runner.py`
- Test: `tests/unit/sandbox/test_runner.py`

**Step 1: Write the failing test**

```python
# In tests/unit/sandbox/test_runner.py (add new test)
def test_show_vars_registered_in_namespace():
    """SHOW_VARS is available in the sandbox namespace."""
    from shesha.sandbox.runner import NAMESPACE, main
    # After register_builtins runs, SHOW_VARS should exist
    # We can't call main() easily, but we can test the function directly
    from shesha.sandbox.runner import execute_code, NAMESPACE

    # Clear and re-register
    NAMESPACE.clear()
    NAMESPACE["llm_query"] = lambda x: x
    NAMESPACE["llm_query_batched"] = lambda x: x
    NAMESPACE["FINAL"] = lambda x: x
    NAMESPACE["FINAL_VAR"] = lambda x: x
    NAMESPACE["FinalAnswer"] = type("FinalAnswer", (), {})
    NAMESPACE["FinalVar"] = type("FinalVar", (), {})
    NAMESPACE["SHOW_VARS"] = None  # placeholder until we implement

    # Execute code that creates a variable
    NAMESPACE.clear()
    # Can't easily test via main(), test show_vars function directly
```

Actually, the runner is designed to run as a subprocess inside Docker. Testing it directly is brittle. Instead, test SHOW_VARS behavior through the executor or by directly testing the `execute_code` + namespace interaction.

Better approach: add a `show_vars` function at module level in runner.py, test it in isolation.

**Step 1: Write the failing test**

Create a new test file or add to existing sandbox tests. The runner is a standalone script, so we test the function in isolation.

```python
# tests/unit/sandbox/test_runner_show_vars.py
def test_show_vars_returns_user_variables():
    """SHOW_VARS returns user-created variables, not builtins."""
    from shesha.sandbox.runner import NAMESPACE, execute_code

    NAMESPACE.clear()
    # Simulate builtins that register_builtins would set
    NAMESPACE["llm_query"] = lambda x: x
    NAMESPACE["FINAL"] = lambda x: x
    NAMESPACE["FINAL_VAR"] = lambda x: x
    NAMESPACE["SHOW_VARS"] = lambda: None  # will be replaced
    NAMESPACE["context"] = ["doc"]

    # Create user variable
    execute_code("my_var = 42")

    # SHOW_VARS should list my_var but not builtins
    from shesha.sandbox.runner import show_vars
    result = show_vars()
    assert "my_var" in result
    assert "llm_query" not in result
    assert "FINAL" not in result
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/sandbox/test_runner_show_vars.py -v`
Expected: FAIL with ImportError (show_vars doesn't exist yet)

**Step 3: Write minimal implementation**

Add to `src/shesha/sandbox/runner.py`:

```python
# At module level, after NAMESPACE definition
BUILTINS_SET: frozenset[str] = frozenset()  # populated by register_builtins


def show_vars() -> str:
    """List all non-private variables in the REPL namespace."""
    available = {
        k: type(v).__name__
        for k, v in NAMESPACE.items()
        if not k.startswith("_") and k not in BUILTINS_SET
    }
    if not available:
        return "No variables created yet. Use ```repl``` blocks to create variables."
    return f"Available variables: {available}"
```

In `main()`, inside `register_builtins()`:
```python
NAMESPACE["SHOW_VARS"] = show_vars
```

And after `register_builtins()` is defined, set BUILTINS_SET:
```python
BUILTINS_SET = frozenset(["llm_query", "llm_query_batched", "FINAL", "FINAL_VAR",
                           "FinalAnswer", "FinalVar", "SHOW_VARS", "context"])
```

Note: BUILTINS_SET needs to be a module-level mutable that gets set in main(). Since the test imports from runner.py but doesn't call main(), we need BUILTINS_SET defined at module level with all the known builtins hardcoded.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/sandbox/test_runner_show_vars.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/sandbox/runner.py tests/unit/sandbox/test_runner_show_vars.py
git commit -m "feat: add SHOW_VARS function to sandbox runner"
```

---

### Task 2: Add `vars` Field to Sandbox Execution Results

**Files:**
- Modify: `src/shesha/sandbox/runner.py` (execute_code returns vars)
- Modify: `src/shesha/sandbox/executor.py` (ExecutionResult gets vars field)
- Test: `tests/unit/sandbox/test_runner_show_vars.py` (add test)
- Test: `tests/unit/sandbox/test_executor.py` (add test for vars parsing)

**Step 1: Write the failing tests**

```python
# tests/unit/sandbox/test_runner_show_vars.py (add)
def test_execute_code_returns_vars_field():
    """execute_code result includes vars dict of user variables."""
    from shesha.sandbox.runner import NAMESPACE, execute_code

    NAMESPACE.clear()
    NAMESPACE["llm_query"] = lambda x: x
    NAMESPACE["FINAL"] = lambda x: x
    NAMESPACE["FINAL_VAR"] = lambda x: x
    NAMESPACE["SHOW_VARS"] = lambda: None
    NAMESPACE["context"] = ["doc"]

    result = execute_code("x = 42\ny = 'hello'")
    assert "vars" in result
    assert "x" in result["vars"]
    assert result["vars"]["x"] == "int"
    assert "y" in result["vars"]
    assert result["vars"]["y"] == "str"
    # Builtins should not appear
    assert "llm_query" not in result["vars"]
```

```python
# tests/unit/sandbox/test_executor.py (add)
def test_execution_result_vars_field():
    """ExecutionResult has an optional vars field."""
    from shesha.sandbox.executor import ExecutionResult

    result = ExecutionResult(
        status="ok", stdout="", stderr="", return_value=None, error=None,
        vars={"x": "int", "answer": "str"},
    )
    assert result.vars == {"x": "int", "answer": "str"}


def test_execution_result_vars_defaults_none():
    """ExecutionResult.vars defaults to None."""
    from shesha.sandbox.executor import ExecutionResult

    result = ExecutionResult(
        status="ok", stdout="", stderr="", return_value=None, error=None,
    )
    assert result.vars is None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/sandbox/test_runner_show_vars.py::test_execute_code_returns_vars_field tests/unit/sandbox/test_executor.py::test_execution_result_vars_field tests/unit/sandbox/test_executor.py::test_execution_result_vars_defaults_none -v`
Expected: FAIL

**Step 3: Write minimal implementation**

In `src/shesha/sandbox/runner.py`, modify `execute_code()` to add vars:

```python
def _list_vars() -> dict[str, str]:
    """List non-private, non-builtin variables and their types."""
    return {
        k: type(v).__name__
        for k, v in NAMESPACE.items()
        if not k.startswith("_") and k not in BUILTINS_SET
    }
```

At end of `execute_code()`:
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

In `src/shesha/sandbox/executor.py`, add to `ExecutionResult`:
```python
vars: dict[str, str] | None = None
```

In the `execute()` method, parse `vars` from response:
```python
ExecutionResult(
    ...,
    vars=result.get("vars"),
)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/sandbox/test_runner_show_vars.py tests/unit/sandbox/test_executor.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/sandbox/runner.py src/shesha/sandbox/executor.py tests/unit/sandbox/test_runner_show_vars.py tests/unit/sandbox/test_executor.py
git commit -m "feat: add vars field to sandbox execution results"
```

---

### Task 3: Replace Prompt Templates

**Files:**
- Modify: `prompts/system.md`
- Modify: `prompts/iteration_zero.md`
- Modify: `prompts/iteration_continue.md`
- Modify: `prompts/context_metadata.md`
- Test: `tests/unit/rlm/test_prompts.py` (update tests)
- Test: `tests/unit/prompts/test_validator.py` (update schemas)
- Test: `tests/unit/prompts/test_loader.py` (update fixtures)

**Step 1: Write/update the failing tests**

First, update the validator tests and schemas, since the prompt templates will change.

In `tests/unit/prompts/test_validator.py`, change `test_prompt_schemas_defined`:

```python
def test_prompt_schemas_defined():
    """PROMPT_SCHEMAS defines required placeholders for each prompt."""
    assert "system.md" in PROMPT_SCHEMAS
    assert "context_metadata.md" in PROMPT_SCHEMAS
    assert "iteration_zero.md" in PROMPT_SCHEMAS
    assert "subcall.md" in PROMPT_SCHEMAS
    assert "code_required.md" in PROMPT_SCHEMAS

    # system.md has no placeholders (500K hardcoded in text)
    assert PROMPT_SCHEMAS["system.md"].required == set()
    # context_metadata.md uses new reference fields
    assert PROMPT_SCHEMAS["context_metadata.md"].required == {
        "context_type", "context_total_length", "context_lengths"
    }
    assert "question" in PROMPT_SCHEMAS["iteration_zero.md"].required
    assert "instruction" in PROMPT_SCHEMAS["subcall.md"].required
    assert PROMPT_SCHEMAS["code_required.md"].required == set()
```

In `tests/unit/rlm/test_prompts.py`:

- **Remove** `test_system_prompt_contains_security_warning` (security tags stripped)
- **Remove** `test_system_prompt_requires_document_grounding` (no doc grounding section)
- **Remove** `test_system_prompt_contains_scout_and_analyze_phases` (reference has no phases)
- **Remove** `test_system_prompt_error_handling_uses_try_except` (reference has no try/except section)
- **Remove** `test_system_prompt_recommends_chunk_classify_synthesize` (reference wording differs)
- **Remove** `test_system_prompt_has_multiple_examples` (reference doesn't number examples the same way)
- **Update** `test_system_prompt_contains_sub_llm_limit`: assert "500K" in prompt (hardcoded, not "500,000")
- **Update** `test_system_prompt_no_longer_contains_metadata`: remove `max_subcall_chars` param from call
- **Remove** `test_wrap_repl_output_basic` and `test_wrap_repl_output_does_not_truncate` (wrap_repl_output removed)
- **Update** `test_format_code_echo_message`: check for "REPL output:" instead of `<repl_output>`
- **Update** `test_context_metadata_*` tests for new signature
- **Update** import: remove `wrap_repl_output` from import

New prompt-specific tests:
```python
def test_system_prompt_describes_show_vars():
    """System prompt describes SHOW_VARS() function."""
    loader = PromptLoader()
    prompt = loader.render_system_prompt()
    assert "SHOW_VARS" in prompt

def test_system_prompt_describes_final_var():
    """System prompt describes FINAL_VAR() function."""
    loader = PromptLoader()
    prompt = loader.render_system_prompt()
    assert "FINAL_VAR" in prompt

def test_iteration_zero_prompt_includes_step_by_step():
    """Iteration-0 prompt includes step-by-step instruction with question."""
    loader = PromptLoader()
    result = loader.render_iteration_zero(question="What color is the sky?")
    assert "step-by-step" in result.lower()
    assert "What color is the sky?" in result
```

In `tests/unit/prompts/test_loader.py`:

- **Update** `valid_prompts_dir` fixture: system.md has no placeholders, context_metadata.md uses `{context_type}`, `{context_total_length}`, `{context_lengths}`
- **Update** `test_loader_render_system_prompt`: no params
- **Update** `test_loader_render_context_metadata`: new params
- **Update** `test_loader_validates_on_init`: system.md no longer needs max_subcall_chars
- **Update** helper prompts dirs in other tests

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/rlm/test_prompts.py tests/unit/prompts/test_validator.py tests/unit/prompts/test_loader.py -v`
Expected: FAIL (schemas don't match, templates don't match)

**Step 3: Write minimal implementation**

3a. Update `src/shesha/prompts/validator.py` — change PROMPT_SCHEMAS:

```python
"system.md": PromptSchema(
    required=set(),
    optional=set(),
),
"context_metadata.md": PromptSchema(
    required={"context_type", "context_total_length", "context_lengths"},
    optional=set(),
),
```

3b. Update `src/shesha/prompts/loader.py`:

```python
def render_system_prompt(self) -> str:
    """Render the system prompt (no variables — 500K hardcoded)."""
    return self._prompts["system.md"]

def render_context_metadata(
    self,
    context_type: str,
    context_total_length: int,
    context_lengths: str,
) -> str:
    """Render context metadata as assistant message."""
    return self._prompts["context_metadata.md"].format(
        context_type=context_type,
        context_total_length=context_total_length,
        context_lengths=context_lengths,
    )
```

3c. Replace `prompts/system.md` with the reference RLM_SYSTEM_PROMPT from `rlm/rlm/utils/prompts.py:6-91`. Copy it verbatim (with double-brace escaping for Python format strings like `{{chunk}}`, `{{query}}`, etc.).

3d. Replace `prompts/iteration_zero.md`:

```
You have not interacted with the REPL environment or seen your prompt / context yet. Your next action should be to look through and figure out how to answer the prompt, so don't just provide a final answer yet.

Think step-by-step on what to do using the REPL environment (which contains the context) to answer the original prompt: "{question}"

Continue using the REPL environment, which has the `context` variable, and querying sub-LLMs by writing to ```repl``` tags, and determine your answer.
Your next action:
```

3e. Replace `prompts/iteration_continue.md`:

```
The history before is your previous interactions with the REPL environment.

Think step-by-step on what to do using the REPL environment (which contains the context) to answer the original prompt: "{question}"

Continue using the REPL environment, which has the `context` variable, and querying sub-LLMs by writing to ```repl``` tags, and determine your answer.
Your next action:
```

3f. Replace `prompts/context_metadata.md`:

```
Your context is a {context_type} with {context_total_length} total characters, and is broken up into chunks of char lengths: {context_lengths}.
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/rlm/test_prompts.py tests/unit/prompts/test_validator.py tests/unit/prompts/test_loader.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add prompts/ src/shesha/prompts/ tests/unit/rlm/test_prompts.py tests/unit/prompts/test_validator.py tests/unit/prompts/test_loader.py
git commit -m "feat: replace prompt templates with reference RLM verbatim"
```

---

### Task 4: Update format_code_echo and Remove wrap_repl_output

**Files:**
- Modify: `src/shesha/rlm/prompts.py`
- Test: `tests/unit/rlm/test_prompts.py` (tests already updated in Task 3)

**Step 1: Write the failing test**

```python
# tests/unit/rlm/test_prompts.py (add)
def test_format_code_echo_with_vars():
    """Code echo includes REPL variables list when vars provided."""
    from shesha.rlm.prompts import format_code_echo

    code = 'x = 42'
    output = ""
    vars_dict = {"x": "int", "answer": "str"}
    result = format_code_echo(code, output, vars=vars_dict)

    assert "REPL variables:" in result
    assert "x" in result
    assert "answer" in result


def test_format_code_echo_without_vars():
    """Code echo omits REPL variables when vars is None."""
    from shesha.rlm.prompts import format_code_echo

    code = 'print("hello")'
    output = "hello"
    result = format_code_echo(code, output)

    assert "REPL variables:" not in result
    assert "REPL output:" in result
    assert "hello" in result


def test_format_code_echo_no_repl_output_tags():
    """Code echo uses plain 'REPL output:' not XML tags."""
    from shesha.rlm.prompts import format_code_echo

    result = format_code_echo("code", "output")
    assert "<repl_output" not in result
    assert "REPL output:" in result
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/rlm/test_prompts.py::test_format_code_echo_with_vars tests/unit/rlm/test_prompts.py::test_format_code_echo_without_vars tests/unit/rlm/test_prompts.py::test_format_code_echo_no_repl_output_tags -v`
Expected: FAIL

**Step 3: Write minimal implementation**

In `src/shesha/rlm/prompts.py`:

```python
def format_code_echo(code: str, output: str, vars: dict[str, str] | None = None) -> str:
    """Format a code block and its output as a code echo message.

    Matches the reference RLM's per-block feedback format
    (rlm/rlm/utils/parsing.py:93-96).
    """
    parts = [f"Code executed:\n```python\n{code}\n```\n\nREPL output:\n{output}"]
    if vars:
        parts.append(f"\nREPL variables: {list(vars.keys())}")
    return "\n".join(parts)
```

Remove `wrap_repl_output()` function entirely.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/rlm/test_prompts.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/rlm/prompts.py tests/unit/rlm/test_prompts.py
git commit -m "feat: update code echo to reference format, remove wrap_repl_output"
```

---

### Task 5: Update Engine — Code Block Regex and Code Echo

**Files:**
- Modify: `src/shesha/rlm/engine.py`
- Test: `tests/unit/rlm/test_engine.py`

**Step 1: Write/update the failing tests**

```python
# Update test_extract_code_blocks_finds_python to verify it does NOT match python blocks
def test_extract_code_blocks_ignores_python():
    """extract_code_blocks only matches ```repl blocks, not ```python."""
    text = """```python
x = 1
```"""
    blocks = extract_code_blocks(text)
    assert len(blocks) == 0

# Update test_extract_code_blocks_finds_repl to handle \n before closing backticks
def test_extract_code_blocks_finds_repl():
    """extract_code_blocks finds ```repl blocks."""
    text = '''Here is some code:

```repl
print("hello")
```

And more text.'''
    blocks = extract_code_blocks(text)
    assert len(blocks) == 1
    assert 'print("hello")' in blocks[0]
```

Also update `test_iteration_message_contains_query_reminder` to check for "REPL output:" instead of "repl_output":

```python
# In TestIterationQueryReminder:
# Change assertion from:
#   assert "repl_output" in code_echo_msg
# To:
#   assert "REPL output:" in code_echo_msg
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/rlm/test_engine.py::test_extract_code_blocks_ignores_python tests/unit/rlm/test_engine.py::TestIterationQueryReminder -v`
Expected: FAIL

**Step 3: Write minimal implementation**

In `src/shesha/rlm/engine.py`:

Change `extract_code_blocks`:
```python
def extract_code_blocks(text: str) -> list[str]:
    """Extract code from ```repl blocks."""
    pattern = r"```repl\s*\n(.*?)\n```"
    matches = re.findall(pattern, text, re.DOTALL)
    return matches
```

Update the code echo section in the engine loop to pass `vars`:
```python
# After executing all code blocks, before checking final_answer:
# Keep exec_results alongside all_output
```

Actually, we need to restructure the loop slightly. Currently it iterates `for code in code_blocks` and collects `all_output`. We need to also collect execution results to pass `vars` to `format_code_echo`.

Change the code execution section:
```python
all_output = []
exec_results = []  # NEW
final_answer = None

for code in code_blocks:
    ...
    all_output.append(output)
    exec_results.append(result)  # NEW
    ...
```

And the code echo section:
```python
for code_block, output, exec_result in zip(code_blocks, all_output, exec_results):
    messages.append(
        {
            "role": "user",
            "content": format_code_echo(code_block, output, exec_result.vars),
        }
    )
```

Update import: add `vars` parameter usage. Remove `wrap_repl_output` from imports (if still imported — check). The import line currently imports:
```python
from shesha.rlm.prompts import (
    MAX_SUBCALL_CHARS,
    format_code_echo,
    truncate_code_output,
    wrap_subcall_content,
)
```
`wrap_repl_output` is NOT imported in engine.py, so no change needed there.

Also update the system prompt rendering call to remove `max_subcall_chars`:
```python
system_prompt = self.prompt_loader.render_system_prompt()
```

And update context metadata construction:
```python
context_type = "list" if len(documents) > 1 else "str"
context_lengths = [len(d) for d in documents]
context_total_length = sum(context_lengths)
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

Remove the doc_sizes, size_lines, doc_sizes_list construction.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/rlm/test_engine.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/rlm/engine.py tests/unit/rlm/test_engine.py
git commit -m "feat: update engine code block regex and code echo format"
```

---

### Task 6: Add FINAL_VAR Handling to Engine

**Files:**
- Modify: `src/shesha/rlm/engine.py`
- Test: `tests/unit/rlm/test_engine.py`

**Step 1: Write the failing test**

```python
# tests/unit/rlm/test_engine.py (add to TestRLMEngine)
@patch("shesha.rlm.engine.ContainerExecutor")
@patch("shesha.rlm.engine.LLMClient")
def test_engine_handles_final_var(
    self,
    mock_llm_cls: MagicMock,
    mock_executor_cls: MagicMock,
):
    """Engine handles FINAL_VAR by using final_value from executor."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = MagicMock(
        content='```repl\nFINAL_VAR("my_answer")\n```',
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    )
    mock_llm_cls.return_value = mock_llm

    mock_executor = MagicMock()
    mock_executor.execute.return_value = MagicMock(
        status="ok",
        stdout="",
        stderr="",
        error=None,
        final_answer=None,
        final_var="my_answer",
        final_value="The computed answer",
    )
    mock_executor_cls.return_value = mock_executor

    engine = RLMEngine(model="test-model")
    result = engine.query(
        documents=["Doc content"],
        question="What is the answer?",
    )

    assert result.answer == "The computed answer"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/rlm/test_engine.py::TestRLMEngine::test_engine_handles_final_var -v`
Expected: FAIL (engine doesn't check final_var)

**Step 3: Write minimal implementation**

In `src/shesha/rlm/engine.py`, in the code execution loop, after checking `result.final_answer is not None`, add:

```python
elif result.final_var is not None:
    final_answer = result.final_value or ""
    step = trace.add_step(
        type=StepType.FINAL_ANSWER,
        content=final_answer,
        iteration=iteration,
    )
    _write_step(step)
    if on_progress:
        on_progress(
            StepType.FINAL_ANSWER,
            iteration,
            final_answer,
            copy.copy(token_usage),
        )
    break
```

This requires that `result` (the ExecutionResult) has `final_var` attribute. Check: the mock already sets `final_var` and `final_value`, and `ExecutionResult` already has these fields (from executor.py:47-48).

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/rlm/test_engine.py::TestRLMEngine::test_engine_handles_final_var -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/rlm/engine.py tests/unit/rlm/test_engine.py
git commit -m "feat: add FINAL_VAR handling to engine"
```

---

### Task 7: Add Max-Iterations LLM Fallback

**Files:**
- Modify: `src/shesha/rlm/engine.py`
- Test: `tests/unit/rlm/test_engine.py`

**Step 1: Write the failing test**

```python
# tests/unit/rlm/test_engine.py (add)
class TestMaxIterationsFallback:
    """Tests for max-iterations LLM fallback."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_max_iterations_asks_llm_for_final_answer(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """When max iterations reached, engine asks LLM for one last answer."""
        mock_llm = MagicMock()
        # All iterations return code without FINAL
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nprint("still working")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="still working",
            stderr="",
            error=None,
            final_answer=None,
            final_var=None,
            vars=None,
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", max_iterations=2)
        result = engine.query(documents=["Doc"], question="What?")

        # Should NOT be the old hard-coded message
        assert result.answer != "[Max iterations reached without final answer]"
        # LLM should be called 3 times: 2 iterations + 1 fallback
        assert mock_llm.complete.call_count == 3
        # Fallback response is used as the answer
        assert result.answer == 'print("still working")'  # last mock response content
```

Wait — the fallback adds a different message. Let me re-read the design:

The fallback adds an assistant message "Please provide a final answer..." and then calls `llm.complete(messages=fallback_messages)`. The mock's `complete` always returns the same response. So the answer will be the content of the last `complete()` call.

But actually the mock always returns `'```repl\nprint("still working")\n```'` — that would be the "answer" from the fallback. Let me make the mock more specific:

```python
    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_max_iterations_asks_llm_for_final_answer(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """When max iterations reached, engine asks LLM for one last answer."""
        mock_llm = MagicMock()
        responses = [
            # Iteration 0: code without FINAL
            MagicMock(
                content='```repl\nprint("exploring")\n```',
                prompt_tokens=100, completion_tokens=50, total_tokens=150,
            ),
            # Iteration 1: code without FINAL
            MagicMock(
                content='```repl\nprint("still exploring")\n```',
                prompt_tokens=100, completion_tokens=50, total_tokens=150,
            ),
            # Fallback: plain answer
            MagicMock(
                content="The answer is 42 based on my analysis.",
                prompt_tokens=100, completion_tokens=50, total_tokens=150,
            ),
        ]
        mock_llm.complete.side_effect = responses
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.return_value = MagicMock(
            status="ok", stdout="output", stderr="", error=None,
            final_answer=None, final_var=None, vars=None,
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", max_iterations=2)
        result = engine.query(documents=["Doc"], question="What?")

        # Should use LLM fallback response, not hard-coded message
        assert result.answer == "The answer is 42 based on my analysis."
        assert mock_llm.complete.call_count == 3
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/rlm/test_engine.py::TestMaxIterationsFallback -v`
Expected: FAIL (engine returns hard-coded message)

**Step 3: Write minimal implementation**

In `src/shesha/rlm/engine.py`, replace the max-iterations block:

```python
# Max iterations reached — ask LLM for one last answer
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

step = trace.add_step(
    type=StepType.FINAL_ANSWER,
    content=f"[max-iter fallback] {answer}",
    iteration=self.max_iterations - 1,
)
_write_step(step)

query_result = QueryResult(
    answer=answer,
    trace=trace,
    token_usage=token_usage,
    execution_time=time.time() - start_time,
)
_finalize_trace(answer, "max_iterations")
return query_result
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/rlm/test_engine.py::TestMaxIterationsFallback -v`
Expected: PASS

**Step 5: Also update test_executor_died_answer_distinct_from_max_iterations**

This test asserts `"max iterations" not in result.answer.lower()`. Since we now use an LLM fallback, the max-iterations path no longer produces a message with "max iterations" in it. The test still needs to verify that executor-died answer is distinct. Check: the executor-died path still returns `"[Executor died — cannot continue]"`, so the test should still pass as-is. Verify.

Run: `pytest tests/unit/rlm/test_engine.py::TestDeadExecutorNoPool -v`
Expected: PASS (executor died path unchanged)

**Step 6: Commit**

```bash
git add src/shesha/rlm/engine.py tests/unit/rlm/test_engine.py
git commit -m "feat: add max-iterations LLM fallback instead of hard-coded message"
```

---

### Task 8: Run Full Test Suite

**Step 1: Run all tests**

Run: `make all`
Expected: All tests pass, no lint or type errors

**Step 2: Fix any remaining failures**

If tests fail, fix them. Common issues:
- Import errors from removed `wrap_repl_output`
- Tests that reference old `max_subcall_chars` parameter in `render_system_prompt()`
- Tests that check for `<repl_output>` in code echo messages
- Tests in `test_loader.py` that create fixtures with old template formats
- Mock `execute` return values missing new fields (`vars`, `final_var`)

**Step 3: Commit fixes**

```bash
git add -A
git commit -m "fix: resolve remaining test failures from engine rewrite"
```

---

### Task 9: Integration Smoke Test

This is a manual verification step, not TDD.

**Step 1: Verify reference RLM still works**

Run: `python oolong/run_reference_implementation.py --model openai/gpt-5-mini`
Expected: ~59% accuracy on trec_coarse (no regression)

**Step 2: Run Shesha against OOLONG**

Run: `python oolong/run_oolong_and_pairs.py --model openai/gpt-5-mini`
Expected: Shesha accuracy should now approach the reference's ~60%

**Step 3: Compare traces**

If Shesha scores are still low, compare traces between Shesha and reference to identify remaining behavioral differences. Key knobs to try:
- Context type: change from list to string for single documents
- Output truncation limit: adjust from 20K
- Prompt wording differences

**Step 4: Document results**

Update `oolong/oolong-research.md` with the new results.

---

## Summary of Changes by File

| File | Change |
|------|--------|
| `src/shesha/sandbox/runner.py` | Add `show_vars()`, `_list_vars()`, `BUILTINS_SET`; add `vars` to `execute_code` result; register `SHOW_VARS` in `register_builtins` |
| `src/shesha/sandbox/executor.py` | Add `vars: dict[str, str] \| None` to `ExecutionResult`; parse from response |
| `src/shesha/prompts/validator.py` | Update `PROMPT_SCHEMAS`: system.md has no required, context_metadata.md uses new fields |
| `src/shesha/prompts/loader.py` | `render_system_prompt()`: remove param; `render_context_metadata()`: new params |
| `prompts/system.md` | Replace with reference RLM_SYSTEM_PROMPT verbatim |
| `prompts/iteration_zero.md` | Replace with reference format (safeguard + step-by-step + question) |
| `prompts/iteration_continue.md` | Replace with reference format (history + step-by-step + question) |
| `prompts/context_metadata.md` | Replace with reference format (context_type, total_length, lengths) |
| `src/shesha/rlm/prompts.py` | Update `format_code_echo()` (add vars param, use "REPL output:"); remove `wrap_repl_output()` |
| `src/shesha/rlm/engine.py` | Change regex to `repl` only; add FINAL_VAR handling; add max-iter LLM fallback; pass vars to code echo; update context metadata construction; remove `MAX_SUBCALL_CHARS` from system prompt call |
| `tests/unit/sandbox/test_runner_show_vars.py` | New: tests for SHOW_VARS and vars field |
| `tests/unit/sandbox/test_executor.py` | Add: tests for vars field on ExecutionResult |
| `tests/unit/rlm/test_prompts.py` | Update/remove tests for new prompt behavior |
| `tests/unit/rlm/test_engine.py` | Update code block tests; add FINAL_VAR test; add max-iter fallback test; update code echo assertions |
| `tests/unit/prompts/test_validator.py` | Update schema assertions |
| `tests/unit/prompts/test_loader.py` | Update fixtures and render calls |
