# Code Echo + Per-Iteration Continue Prompt Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the two remaining structural gaps between Shesha and the reference RLM: per-block code echo in iteration feedback, and per-iteration sub-LLM re-instruction via `iteration_continue.md`.

**Architecture:** Add a new prompt template `iteration_continue.md` with `{question}` placeholder, rendered via `PromptLoader.render_iteration_continue()`. Restructure `engine.py` post-execution to emit one user message per code block (code echo + wrapped output) followed by the continuation prompt, replacing the current single combined message.

**Tech Stack:** Python, pytest, ruff, mypy

---

### Task 1: Add `iteration_continue.md` Schema

**Files:**
- Modify: `src/shesha/prompts/validator.py:16-47`
- Test: `tests/unit/prompts/test_validator.py`

**Step 1: Write the failing tests**

Add two tests to `tests/unit/prompts/test_validator.py`:

```python
def test_iteration_continue_schema_defined():
    """PROMPT_SCHEMAS includes iteration_continue.md with required placeholders."""
    assert "iteration_continue.md" in PROMPT_SCHEMAS
    schema = PROMPT_SCHEMAS["iteration_continue.md"]
    assert schema.required == {"question"}
    assert schema.optional == set()
    assert schema.required_file is True


def test_validate_iteration_continue_passes_valid():
    """validate_prompt passes for valid iteration_continue.md content."""
    content = "Continue answering: {question}"
    validate_prompt("iteration_continue.md", content)
```

Also update `test_core_schemas_are_required_files` (line 122-131) — add `"iteration_continue.md"` to the tuple.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/prompts/test_validator.py -v`
Expected: 2 FAIL (`test_iteration_continue_schema_defined`, `test_validate_iteration_continue_passes_valid`), 1 FAIL (`test_core_schemas_are_required_files`)

**Step 3: Write minimal implementation**

Add to `PROMPT_SCHEMAS` in `src/shesha/prompts/validator.py:16-47`, after the `iteration_zero.md` entry (line 36):

```python
    "iteration_continue.md": PromptSchema(
        required={"question"},
        optional=set(),
    ),
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/prompts/test_validator.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/shesha/prompts/validator.py tests/unit/prompts/test_validator.py
git commit -m "feat: add iteration_continue.md schema to prompt validator"
```

---

### Task 2: Create `prompts/iteration_continue.md` Template

**Files:**
- Create: `prompts/iteration_continue.md`

**Step 1: Create the template file**

```markdown
The history before is your previous interactions with the REPL environment.

Think step-by-step on what to do using the REPL environment (which contains the context) to answer the original prompt: "{question}"

Continue using the REPL environment, which has the `context` variable, and querying sub-LLMs by writing to ```repl``` tags, and determine your answer.
Your next action:
```

This matches the reference `rlm/rlm/utils/prompts.py:141-143` structure — it re-instructs the model to use sub-LLMs each iteration.

**Step 2: Verify validator accepts it**

Run: `python -m shesha.prompts`
Expected: All prompts pass validation (exit 0)

**Step 3: Commit**

```bash
git add prompts/iteration_continue.md
git commit -m "feat: add iteration_continue.md prompt template"
```

---

### Task 3: Add `render_iteration_continue()` to PromptLoader

**Files:**
- Modify: `src/shesha/prompts/loader.py:129-139`
- Test: `tests/unit/prompts/test_loader.py`
- Test: `tests/unit/rlm/test_prompts.py`

**Step 1: Write the failing tests**

In `tests/unit/prompts/test_loader.py`, update the `valid_prompts_dir` fixture (line 12-33) — add after the `iteration_zero.md` line (line 21):

```python
    (prompts_dir / "iteration_continue.md").write_text("Continue: {question}")
```

Then add a new test:

```python
def test_loader_render_iteration_continue(valid_prompts_dir: Path):
    """PromptLoader renders iteration_continue prompt with question."""
    loader = PromptLoader(prompts_dir=valid_prompts_dir)
    result = loader.render_iteration_continue(question="What is the answer?")
    assert "What is the answer?" in result
```

In `tests/unit/rlm/test_prompts.py`, add two tests at the end:

```python
def test_iteration_continue_prompt_exists():
    """PromptLoader can render an iteration-continue prompt template."""
    loader = PromptLoader()
    result = loader.render_iteration_continue(question="What color is the sky?")
    assert isinstance(result, str)
    assert len(result) > 0


def test_iteration_continue_prompt_mentions_sub_llms():
    """Rendered iteration-continue template mentions sub-LLMs."""
    loader = PromptLoader()
    result = loader.render_iteration_continue(question="What color is the sky?")
    assert "sub-LLM" in result or "sub-llm" in result.lower() or "querying" in result.lower()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/prompts/test_loader.py::test_loader_render_iteration_continue tests/unit/rlm/test_prompts.py::test_iteration_continue_prompt_exists tests/unit/rlm/test_prompts.py::test_iteration_continue_prompt_mentions_sub_llms -v`
Expected: ALL FAIL (AttributeError: 'PromptLoader' has no attribute 'render_iteration_continue')

**Step 3: Write minimal implementation**

Add to `src/shesha/prompts/loader.py` after `render_iteration_zero` (line 135), before `render_code_required`:

```python
    def render_iteration_continue(self, question: str) -> str:
        """Render the per-iteration continuation prompt.

        Re-instructs the model to use sub-LLMs each iteration.
        Matches reference rlm/rlm/utils/prompts.py:141-143.
        """
        return self._prompts["iteration_continue.md"].format(question=question)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/prompts/test_loader.py tests/unit/rlm/test_prompts.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/shesha/prompts/loader.py tests/unit/prompts/test_loader.py tests/unit/rlm/test_prompts.py
git commit -m "feat: add render_iteration_continue() to PromptLoader"
```

---

### Task 4: Update Test Fixtures for `iteration_continue.md`

**Files:**
- Modify: `tests/unit/prompts/test_cli.py`
- Modify: `tests/unit/prompts/test_loader.py` (fixtures that create prompts dirs without `iteration_continue.md`)

**Step 1: Update `test_cli.py` fixtures**

In `tests/unit/prompts/test_cli.py`, add after each `iteration_zero.md` line in both test functions (lines 15 and 39):

```python
    (prompts_dir / "iteration_continue.md").write_text("Continue: {question}")
```

**Step 2: Update `test_loader.py` fixtures that don't use `valid_prompts_dir`**

In `tests/unit/prompts/test_loader.py`, update all inline fixture blocks that create prompts directories but don't include `iteration_continue.md`. These are:

- `test_loader_validates_on_init` (line 42-56) — add after `iteration_zero.md` line 50:
  ```python
      (prompts_dir / "iteration_continue.md").write_text("{question}")
  ```

- `test_loader_succeeds_without_optional_verify_files` (line 131-146) — add after `iteration_zero.md` line 138:
  ```python
      (prompts_dir / "iteration_continue.md").write_text("{question}")
  ```

- `test_loader_render_verify_adversarial_raises_when_not_loaded` (line 149-164) — add after `iteration_zero.md` line 156:
  ```python
      (prompts_dir / "iteration_continue.md").write_text("{question}")
  ```

- `test_loader_render_verify_code_raises_when_not_loaded` (line 167-182) — add after `iteration_zero.md` line 174:
  ```python
      (prompts_dir / "iteration_continue.md").write_text("{question}")
  ```

**Step 3: Run all prompt tests to verify they pass**

Run: `pytest tests/unit/prompts/ -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add tests/unit/prompts/test_cli.py tests/unit/prompts/test_loader.py
git commit -m "test: update prompt fixtures to include iteration_continue.md"
```

---

### Task 5: Restructure Engine Post-Execution Messages

**Files:**
- Modify: `src/shesha/rlm/engine.py:646-659`

**Step 1: Write the failing test**

There's no easy unit test for the engine message flow without mocking extensively. This is a structural change to how messages are built. Instead, verify by inspection and integration:

Add a test to `tests/unit/rlm/test_prompts.py` that verifies the code echo format function:

```python
def test_format_code_echo_message():
    """Code echo message contains both the code and wrapped output."""
    from shesha.rlm.prompts import format_code_echo

    code = 'print("hello")'
    output = "hello"
    result = format_code_echo(code, output)

    assert "Code executed:" in result
    assert 'print("hello")' in result
    assert "```python" in result
    assert '<repl_output type="untrusted_document_content">' in result
    assert "hello" in result
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/rlm/test_prompts.py::test_format_code_echo_message -v`
Expected: FAIL (ImportError: cannot import name 'format_code_echo')

**Step 3: Implement `format_code_echo` in prompts.py**

Add to `src/shesha/rlm/prompts.py`:

```python
def format_code_echo(code: str, output: str) -> str:
    """Format a code block and its output as a code echo message.

    Matches the reference RLM's per-block feedback format
    (rlm/rlm/utils/parsing.py:93-96), but keeps Shesha's
    <repl_output> security tags.
    """
    wrapped = wrap_repl_output(output)
    return f"Code executed:\n```python\n{code}\n```\n\n{wrapped}"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/rlm/test_prompts.py::test_format_code_echo_message -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/rlm/prompts.py tests/unit/rlm/test_prompts.py
git commit -m "feat: add format_code_echo() for per-block iteration feedback"
```

---

### Task 6: Wire Up Engine to Use Code Echo + Continuation Prompt

**Files:**
- Modify: `src/shesha/rlm/engine.py:646-659`

**Step 1: Update engine imports**

At the top of `engine.py`, update the import from `shesha.rlm.prompts` to include `format_code_echo`:

```python
from shesha.rlm.prompts import (
    MAX_SUBCALL_CHARS,
    format_code_echo,
    truncate_code_output,
    wrap_repl_output,
    wrap_subcall_content,
)
```

Note: `wrap_repl_output` is no longer used directly in engine.py after this change (it's used inside `format_code_echo`). Remove it from the import if the linter flags it.

**Step 2: Replace post-execution message building**

Replace `engine.py:646-659` (the "Add output to conversation" block):

```python
                # current code:
                # Add output to conversation
                combined_output = "\n\n".join(all_output)
                wrapped_output = wrap_repl_output(combined_output)

                # Append query reminder so the model stays focused across iterations
                reminder = (
                    "Continue using the REPL environment to answer"
                    f' the original query: "{question}"\n'
                    "Your next action:"
                )
                iteration_msg = f"{wrapped_output}\n\n{reminder}"

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": iteration_msg})
```

With:

```python
                # Add assistant response, then per-block code echo messages
                messages.append({"role": "assistant", "content": response.content})
                for code, output in zip(code_blocks, all_output):
                    messages.append({
                        "role": "user",
                        "content": format_code_echo(code, output),
                    })

                # Per-iteration continuation prompt re-instructs sub-LLM usage
                messages.append({
                    "role": "user",
                    "content": self.prompt_loader.render_iteration_continue(
                        question=question,
                    ),
                })
```

**Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add src/shesha/rlm/engine.py
git commit -m "feat: per-block code echo + iteration_continue prompt in engine loop"
```

---

### Task 7: Run Full Quality Suite

**Step 1: Run `make all`**

Run: `make all`
Expected: format + lint + typecheck + all tests pass

**Step 2: Fix any issues**

If ruff, mypy, or tests fail, fix and re-run.

**Step 3: Final commit if needed**

```bash
git add -A
git commit -m "fix: address lint/type issues from code echo changes"
```

---

### Task 8: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add entries under `[Unreleased]`**

```markdown
### Changed
- Iteration feedback now sends per-code-block messages with code echo (matching reference RLM)
- Per-iteration continuation prompt re-instructs model to use sub-LLMs via `iteration_continue.md`
- Replaced inline reminder string with external prompt template
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: update changelog for code echo and iteration continue prompt"
```
