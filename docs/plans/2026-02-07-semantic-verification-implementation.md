# Semantic Verification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add opt-in semantic verification that adversarially reviews RLM findings for accuracy, with code-specific checks when analyzing source code.

**Architecture:** After the existing mechanical citation verification, a new `--verify` path makes 1-2 LLM subcalls to adversarially review findings. Layer 1 (generic) checks evidence support and confidence. Layer 2 (code-specific) checks for comment-mining, test/production conflation, and idiom misidentification. Output is reformatted into a verified summary + appendix.

**Tech Stack:** Python dataclasses, existing LLMClient, existing PromptLoader, JSON parsing.

**Design doc:** `docs/plans/2026-02-07-semantic-verification-design.md`

**Worktree:** `.worktrees/semantic-verification` (branch: `ovid/semantic-verification`)

---

### Task 1: SemanticVerificationReport Data Model

**Files:**
- Create: `src/shesha/rlm/semantic_verification.py`
- Create: `tests/unit/rlm/test_semantic_verification.py`

**Step 1: Write failing tests**

```python
# tests/unit/rlm/test_semantic_verification.py
"""Tests for semantic verification module."""

from shesha.rlm.semantic_verification import (
    FindingVerification,
    SemanticVerificationReport,
)


class TestFindingVerification:
    """Tests for FindingVerification dataclass."""

    def test_construction(self) -> None:
        """FindingVerification stores all fields."""
        fv = FindingVerification(
            finding_id="P0.1",
            original_claim="String eval injection",
            confidence="low",
            reason="No injection vector exists.",
            evidence_classification="code_analysis",
            flags=["standard_idiom"],
        )
        assert fv.finding_id == "P0.1"
        assert fv.confidence == "low"
        assert fv.flags == ["standard_idiom"]


class TestSemanticVerificationReport:
    """Tests for SemanticVerificationReport dataclass."""

    def test_construction(self) -> None:
        """SemanticVerificationReport stores findings and content_type."""
        report = SemanticVerificationReport(
            findings=[
                FindingVerification(
                    finding_id="P1.1",
                    original_claim="Schema clone issue",
                    confidence="high",
                    reason="Genuine issue.",
                    evidence_classification="code_analysis",
                    flags=[],
                ),
            ],
            content_type="code",
        )
        assert len(report.findings) == 1
        assert report.content_type == "code"

    def test_high_confidence_filters_correctly(self) -> None:
        """high_confidence returns only high and medium findings."""
        report = SemanticVerificationReport(
            findings=[
                FindingVerification(
                    finding_id="P0.1",
                    original_claim="Claim A",
                    confidence="high",
                    reason="Real.",
                    evidence_classification="code_analysis",
                    flags=[],
                ),
                FindingVerification(
                    finding_id="P0.2",
                    original_claim="Claim B",
                    confidence="low",
                    reason="Not real.",
                    evidence_classification="comment_derived",
                    flags=["comment_derived"],
                ),
                FindingVerification(
                    finding_id="P1.1",
                    original_claim="Claim C",
                    confidence="medium",
                    reason="Probably real.",
                    evidence_classification="code_analysis",
                    flags=[],
                ),
            ],
            content_type="code",
        )
        high = report.high_confidence
        assert len(high) == 2
        assert high[0].finding_id == "P0.1"
        assert high[1].finding_id == "P1.1"

    def test_low_confidence_filters_correctly(self) -> None:
        """low_confidence returns only low findings."""
        report = SemanticVerificationReport(
            findings=[
                FindingVerification(
                    finding_id="P0.1",
                    original_claim="Claim A",
                    confidence="high",
                    reason="Real.",
                    evidence_classification="code_analysis",
                    flags=[],
                ),
                FindingVerification(
                    finding_id="P0.2",
                    original_claim="Claim B",
                    confidence="low",
                    reason="Not real.",
                    evidence_classification="comment_derived",
                    flags=["comment_derived"],
                ),
            ],
            content_type="general",
        )
        low = report.low_confidence
        assert len(low) == 1
        assert low[0].finding_id == "P0.2"

    def test_empty_report(self) -> None:
        """Empty report returns empty lists for both filters."""
        report = SemanticVerificationReport(findings=[], content_type="general")
        assert report.high_confidence == []
        assert report.low_confidence == []
```

**Step 2: Run tests to verify they fail**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/rlm/test_semantic_verification.py -v`
Expected: FAIL with ImportError (module doesn't exist yet)

**Step 3: Write minimal implementation**

```python
# src/shesha/rlm/semantic_verification.py
"""Post-FINAL semantic verification for RLM findings."""

from dataclasses import dataclass, field


@dataclass
class FindingVerification:
    """Verification result for a single finding."""

    finding_id: str
    original_claim: str
    confidence: str  # "high", "medium", "low"
    reason: str
    evidence_classification: str
    flags: list[str] = field(default_factory=list)


@dataclass
class SemanticVerificationReport:
    """Result of semantic verification."""

    findings: list[FindingVerification]
    content_type: str  # "code" or "general"

    @property
    def high_confidence(self) -> list[FindingVerification]:
        """Findings rated high or medium confidence."""
        return [f for f in self.findings if f.confidence in ("high", "medium")]

    @property
    def low_confidence(self) -> list[FindingVerification]:
        """Findings rated low confidence."""
        return [f for f in self.findings if f.confidence == "low"]
```

**Step 4: Run tests to verify they pass**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/rlm/test_semantic_verification.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
cd .worktrees/semantic-verification && git add src/shesha/rlm/semantic_verification.py tests/unit/rlm/test_semantic_verification.py && git commit -m "feat: add SemanticVerificationReport data model"
```

---

### Task 2: Content Type Detection

**Files:**
- Modify: `src/shesha/rlm/semantic_verification.py`
- Modify: `tests/unit/rlm/test_semantic_verification.py`

**Step 1: Write failing tests**

Append to `tests/unit/rlm/test_semantic_verification.py`:

```python
from shesha.rlm.semantic_verification import detect_content_type


class TestDetectContentType:
    """Tests for detect_content_type()."""

    def test_empty_list_returns_general(self) -> None:
        """Empty document list returns 'general'."""
        assert detect_content_type([]) == "general"

    def test_majority_code_files(self) -> None:
        """Returns 'code' when majority are code files."""
        names = ["main.py", "utils.py", "test_main.py", "README.md"]
        assert detect_content_type(names) == "code"

    def test_majority_non_code_files(self) -> None:
        """Returns 'general' when majority are not code files."""
        names = ["chapter1.txt", "chapter2.txt", "notes.md", "main.py"]
        assert detect_content_type(names) == "general"

    def test_perl_files_detected(self) -> None:
        """Perl .pm and .pl files are recognized as code."""
        names = ["lib/Foo.pm", "lib/Bar.pm", "bin/script.pl"]
        assert detect_content_type(names) == "code"

    def test_mixed_code_extensions(self) -> None:
        """Various code extensions are all recognized."""
        names = ["app.js", "server.ts", "main.go", "lib.rs"]
        assert detect_content_type(names) == "code"

    def test_case_insensitive(self) -> None:
        """File extension matching is case-insensitive."""
        names = ["Main.PY", "Utils.JS", "App.CPP"]
        assert detect_content_type(names) == "code"

    def test_no_extension_treated_as_non_code(self) -> None:
        """Files without extensions are not counted as code."""
        names = ["Makefile", "Dockerfile", "README"]
        assert detect_content_type(names) == "general"

    def test_exactly_half_returns_general(self) -> None:
        """When exactly half are code, returns 'general' (majority required)."""
        names = ["main.py", "readme.txt"]
        assert detect_content_type(names) == "general"
```

**Step 2: Run tests to verify they fail**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/rlm/test_semantic_verification.py::TestDetectContentType -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Add to `src/shesha/rlm/semantic_verification.py`:

```python
from pathlib import PurePosixPath

CODE_EXTENSIONS = frozenset({
    ".py", ".pl", ".pm", ".t",
    ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
    ".rs", ".go", ".java", ".rb", ".c", ".cpp", ".h", ".hpp", ".cc",
    ".cs", ".swift", ".kt", ".scala", ".clj", ".ex", ".exs",
    ".sh", ".bash", ".zsh", ".ps1",
    ".sql", ".r", ".m", ".mm",
    ".lua", ".vim", ".el", ".hs",
    ".php", ".dart", ".v", ".zig",
})


def detect_content_type(doc_names: list[str]) -> str:
    """Detect whether documents are primarily code.

    Args:
        doc_names: List of document filenames/paths.

    Returns:
        "code" if majority of documents have code file extensions,
        "general" otherwise.
    """
    if not doc_names:
        return "general"
    code_count = sum(
        1 for name in doc_names
        if PurePosixPath(name).suffix.lower() in CODE_EXTENSIONS
    )
    return "code" if code_count > len(doc_names) / 2 else "general"
```

**Step 4: Run tests to verify they pass**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/rlm/test_semantic_verification.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
cd .worktrees/semantic-verification && git add src/shesha/rlm/semantic_verification.py tests/unit/rlm/test_semantic_verification.py && git commit -m "feat: add content type detection for semantic verification"
```

---

### Task 3: Cited Document Gathering

**Files:**
- Modify: `src/shesha/rlm/semantic_verification.py`
- Modify: `tests/unit/rlm/test_semantic_verification.py`

**Step 1: Write failing tests**

Append to test file:

```python
from shesha.rlm.semantic_verification import gather_cited_documents


class TestGatherCitedDocuments:
    """Tests for gather_cited_documents()."""

    def test_gathers_cited_docs(self) -> None:
        """Gathers documents referenced in the answer."""
        answer = "According to Doc 0 and Doc 2, the code is correct."
        documents = ["Content of doc 0", "Content of doc 1", "Content of doc 2"]
        doc_names = ["main.py", "utils.py", "test.py"]

        result = gather_cited_documents(answer, documents, doc_names)
        assert "Content of doc 0" in result
        assert "Content of doc 2" in result
        assert "Content of doc 1" not in result

    def test_includes_doc_name_in_header(self) -> None:
        """Each gathered document has a header with name and index."""
        answer = "See Doc 1 for details."
        documents = ["first", "second"]
        doc_names = ["a.py", "b.py"]

        result = gather_cited_documents(answer, documents, doc_names)
        assert "b.py" in result
        assert "Document 1" in result

    def test_out_of_range_doc_id_skipped(self) -> None:
        """Doc IDs beyond the document list are skipped."""
        answer = "See Doc 0 and Doc 999."
        documents = ["only doc"]
        doc_names = ["file.py"]

        result = gather_cited_documents(answer, documents, doc_names)
        assert "only doc" in result
        assert "999" not in result

    def test_no_citations_returns_empty(self) -> None:
        """Returns empty string when no citations found."""
        answer = "No references here."
        documents = ["content"]
        doc_names = ["file.py"]

        result = gather_cited_documents(answer, documents, doc_names)
        assert result == ""

    def test_context_bracket_pattern(self) -> None:
        """Handles context[N] citation style."""
        answer = "Found in context[0]."
        documents = ["the content"]
        doc_names = ["file.py"]

        result = gather_cited_documents(answer, documents, doc_names)
        assert "the content" in result
```

**Step 2: Run tests to verify they fail**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/rlm/test_semantic_verification.py::TestGatherCitedDocuments -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Add to `src/shesha/rlm/semantic_verification.py`:

```python
from shesha.rlm.verification import extract_citations


def gather_cited_documents(
    answer: str,
    documents: list[str],
    doc_names: list[str],
) -> str:
    """Gather documents cited in the answer, formatted for verification.

    Args:
        answer: The final answer text containing document citations.
        documents: All document contents.
        doc_names: All document names/paths.

    Returns:
        Formatted string with cited documents, or empty string if none cited.
    """
    doc_ids = extract_citations(answer)
    parts = []
    for doc_id in doc_ids:
        if 0 <= doc_id < len(documents):
            name = doc_names[doc_id] if doc_id < len(doc_names) else f"doc_{doc_id}"
            parts.append(f"### Document {doc_id} ({name})\n\n{documents[doc_id]}")
    return "\n\n---\n\n".join(parts)
```

**Step 4: Run tests to verify they pass**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/rlm/test_semantic_verification.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
cd .worktrees/semantic-verification && git add src/shesha/rlm/semantic_verification.py tests/unit/rlm/test_semantic_verification.py && git commit -m "feat: add cited document gathering for semantic verification"
```

---

### Task 4: Verification Response Parsing

**Files:**
- Modify: `src/shesha/rlm/semantic_verification.py`
- Modify: `tests/unit/rlm/test_semantic_verification.py`

**Step 1: Write failing tests**

Append to test file:

```python
import json

import pytest

from shesha.rlm.semantic_verification import parse_verification_response


class TestParseVerificationResponse:
    """Tests for parse_verification_response()."""

    def test_valid_json_response(self) -> None:
        """Parses valid JSON verification response."""
        data = {
            "findings": [
                {
                    "finding_id": "P0.1",
                    "original_claim": "Injection risk",
                    "confidence": "low",
                    "reason": "No injection vector.",
                    "evidence_classification": "code_analysis",
                    "flags": ["standard_idiom"],
                }
            ]
        }
        result = parse_verification_response(json.dumps(data))
        assert len(result) == 1
        assert result[0].finding_id == "P0.1"
        assert result[0].confidence == "low"
        assert result[0].flags == ["standard_idiom"]

    def test_multiple_findings(self) -> None:
        """Parses response with multiple findings."""
        data = {
            "findings": [
                {
                    "finding_id": "P0.1",
                    "original_claim": "A",
                    "confidence": "low",
                    "reason": "R1",
                    "evidence_classification": "code_analysis",
                    "flags": [],
                },
                {
                    "finding_id": "P1.1",
                    "original_claim": "B",
                    "confidence": "high",
                    "reason": "R2",
                    "evidence_classification": "control_flow",
                    "flags": [],
                },
            ]
        }
        result = parse_verification_response(json.dumps(data))
        assert len(result) == 2
        assert result[0].confidence == "low"
        assert result[1].confidence == "high"

    def test_json_with_surrounding_text(self) -> None:
        """Extracts JSON even when surrounded by other text."""
        data = {"findings": [
            {
                "finding_id": "P0.1",
                "original_claim": "X",
                "confidence": "medium",
                "reason": "R",
                "evidence_classification": "code_analysis",
                "flags": [],
            }
        ]}
        text = f"Here is my analysis:\n```json\n{json.dumps(data)}\n```"
        result = parse_verification_response(text)
        assert len(result) == 1
        assert result[0].confidence == "medium"

    def test_invalid_json_raises(self) -> None:
        """Raises ValueError on unparseable response."""
        with pytest.raises(ValueError, match="Could not parse"):
            parse_verification_response("This is not JSON at all")

    def test_missing_findings_key_raises(self) -> None:
        """Raises ValueError when JSON lacks 'findings' key."""
        with pytest.raises(ValueError, match="Could not parse"):
            parse_verification_response('{"results": []}')

    def test_missing_optional_flags_defaults_empty(self) -> None:
        """Missing 'flags' field defaults to empty list."""
        data = {
            "findings": [
                {
                    "finding_id": "P0.1",
                    "original_claim": "X",
                    "confidence": "high",
                    "reason": "R",
                    "evidence_classification": "code_analysis",
                }
            ]
        }
        result = parse_verification_response(json.dumps(data))
        assert result[0].flags == []
```

**Step 2: Run tests to verify they fail**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/rlm/test_semantic_verification.py::TestParseVerificationResponse -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Add to `src/shesha/rlm/semantic_verification.py`:

```python
import json
import re


def parse_verification_response(text: str) -> list[FindingVerification]:
    """Parse structured JSON from a verification LLM response.

    Extracts a JSON object with a 'findings' array from the response text.
    Handles responses wrapped in markdown code blocks.

    Args:
        text: Raw LLM response text.

    Returns:
        List of FindingVerification objects.

    Raises:
        ValueError: If no valid findings JSON can be extracted.
    """
    # Try to extract JSON from markdown code blocks first
    code_block_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    candidates = []
    if code_block_match:
        candidates.append(code_block_match.group(1).strip())
    # Also try each line that starts with {
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("{"):
            candidates.append(stripped)
    # Try the full text as well
    candidates.append(text.strip())

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "findings" in data:
            return [
                FindingVerification(
                    finding_id=f.get("finding_id", ""),
                    original_claim=f.get("original_claim", ""),
                    confidence=f.get("confidence", "medium"),
                    reason=f.get("reason", ""),
                    evidence_classification=f.get("evidence_classification", ""),
                    flags=f.get("flags", []),
                )
                for f in data["findings"]
            ]

    raise ValueError("Could not parse semantic verification response: no valid JSON found")
```

**Step 4: Run tests to verify they pass**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/rlm/test_semantic_verification.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
cd .worktrees/semantic-verification && git add src/shesha/rlm/semantic_verification.py tests/unit/rlm/test_semantic_verification.py && git commit -m "feat: add verification response parsing for semantic verification"
```

---

### Task 5: Config and StepType Changes

**Files:**
- Modify: `src/shesha/config.py` (add `verify: bool = False`)
- Modify: `src/shesha/rlm/trace.py` (add `SEMANTIC_VERIFICATION` step type)
- Modify: `tests/unit/test_config.py` (add test for verify field)
- Modify: `tests/unit/rlm/test_engine.py` (add test for StepType)

**Step 1: Write failing tests**

Add to `tests/unit/test_config.py`:

```python
class TestVerifyConfig:
    """Tests for verify config field."""

    def test_verify_defaults_false(self) -> None:
        """verify defaults to False."""
        config = SheshaConfig()
        assert config.verify is False

    def test_verify_can_be_set_true(self) -> None:
        """verify can be set to True."""
        config = SheshaConfig(verify=True)
        assert config.verify is True
```

Add to `tests/unit/rlm/test_engine.py` (near the existing `test_engine_verify_citations_defaults_true`):

```python
def test_semantic_verification_step_type_exists():
    """SEMANTIC_VERIFICATION step type exists."""
    assert StepType.SEMANTIC_VERIFICATION.value == "semantic_verification"
```

**Step 2: Run tests to verify they fail**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/test_config.py::TestVerifyConfig tests/unit/rlm/test_engine.py::test_semantic_verification_step_type_exists -v`
Expected: FAIL (field/enum value doesn't exist)

**Step 3: Write minimal implementation**

In `src/shesha/config.py`, add after the `verify_citations` field (line 51):

```python
    # Semantic verification
    verify: bool = False
```

In `src/shesha/rlm/trace.py`, add to the `StepType` enum (after `VERIFICATION`):

```python
    SEMANTIC_VERIFICATION = "semantic_verification"
```

**Step 4: Run tests to verify they pass**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/test_config.py::TestVerifyConfig tests/unit/rlm/test_engine.py::test_semantic_verification_step_type_exists -v`
Expected: All PASS

**Step 5: Run full test suite to check for regressions**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest -x -q`
Expected: All pass

**Step 6: Commit**

```bash
cd .worktrees/semantic-verification && git add src/shesha/config.py src/shesha/rlm/trace.py tests/unit/test_config.py tests/unit/rlm/test_engine.py && git commit -m "feat: add verify config flag and SEMANTIC_VERIFICATION step type"
```

---

### Task 6: Prompt Templates and Loading

**Files:**
- Create: `prompts/verify_adversarial.md`
- Create: `prompts/verify_code.md`
- Modify: `src/shesha/prompts/validator.py` (add schemas)
- Modify: `src/shesha/prompts/loader.py` (add render methods)
- Modify: `tests/unit/prompts/test_loader.py` (add tests)
- Modify: `tests/unit/prompts/test_validator.py` (add tests)

**Step 1: Write failing tests**

Add to `tests/unit/prompts/test_validator.py`:

```python
class TestVerifyAdversarialSchema:
    """Tests for verify_adversarial.md schema."""

    def test_schema_exists(self) -> None:
        """verify_adversarial.md has a schema entry."""
        from shesha.prompts.validator import PROMPT_SCHEMAS
        assert "verify_adversarial.md" in PROMPT_SCHEMAS

    def test_requires_findings_and_documents(self) -> None:
        """Schema requires findings and documents placeholders."""
        from shesha.prompts.validator import PROMPT_SCHEMAS
        schema = PROMPT_SCHEMAS["verify_adversarial.md"]
        assert "findings" in schema.required
        assert "documents" in schema.required


class TestVerifyCodeSchema:
    """Tests for verify_code.md schema."""

    def test_schema_exists(self) -> None:
        """verify_code.md has a schema entry."""
        from shesha.prompts.validator import PROMPT_SCHEMAS
        assert "verify_code.md" in PROMPT_SCHEMAS

    def test_requires_previous_results_findings_documents(self) -> None:
        """Schema requires previous_results, findings, and documents."""
        from shesha.prompts.validator import PROMPT_SCHEMAS
        schema = PROMPT_SCHEMAS["verify_code.md"]
        assert "previous_results" in schema.required
        assert "findings" in schema.required
        assert "documents" in schema.required
```

Add to `tests/unit/prompts/test_loader.py`:

```python
class TestVerifyAdversarialPrompt:
    """Tests for verify_adversarial.md loading."""

    def test_loads_and_validates(self, tmp_prompts_dir: Path) -> None:
        """verify_adversarial.md loads successfully."""
        loader = PromptLoader(tmp_prompts_dir)
        raw = loader.get_raw_template("verify_adversarial.md")
        assert "{findings}" in raw
        assert "{documents}" in raw

    def test_render_verify_adversarial(self, tmp_prompts_dir: Path) -> None:
        """render_verify_adversarial_prompt substitutes placeholders."""
        loader = PromptLoader(tmp_prompts_dir)
        result = loader.render_verify_adversarial_prompt(
            findings="Test findings",
            documents="Test documents",
        )
        assert "Test findings" in result
        assert "Test documents" in result
        assert "{findings}" not in result


class TestVerifyCodePrompt:
    """Tests for verify_code.md loading."""

    def test_loads_and_validates(self, tmp_prompts_dir: Path) -> None:
        """verify_code.md loads successfully."""
        loader = PromptLoader(tmp_prompts_dir)
        raw = loader.get_raw_template("verify_code.md")
        assert "{previous_results}" in raw
        assert "{findings}" in raw
        assert "{documents}" in raw

    def test_render_verify_code(self, tmp_prompts_dir: Path) -> None:
        """render_verify_code_prompt substitutes placeholders."""
        loader = PromptLoader(tmp_prompts_dir)
        result = loader.render_verify_code_prompt(
            previous_results="Previous",
            findings="Findings",
            documents="Documents",
        )
        assert "Previous" in result
        assert "Findings" in result
        assert "Documents" in result
        assert "{previous_results}" not in result
```

**Note:** The test_loader.py tests use a `tmp_prompts_dir` fixture. Check if it exists; if so, it needs to be updated to create the new prompt files. If the fixture copies from the real prompts dir, the new files will be picked up automatically once created.

**Step 2: Run tests to verify they fail**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/prompts/test_validator.py::TestVerifyAdversarialSchema tests/unit/prompts/test_validator.py::TestVerifyCodeSchema tests/unit/prompts/test_loader.py::TestVerifyAdversarialPrompt tests/unit/prompts/test_loader.py::TestVerifyCodePrompt -v`
Expected: FAIL

**Step 3: Create prompt templates**

Create `prompts/verify_adversarial.md`:

```markdown
You are a skeptical technical reviewer. Your job is to verify the accuracy of findings from a document analysis.

Below are findings from an analysis, followed by the source documents that were cited as evidence.

## Findings to Verify

{findings}

## Source Documents

{documents}

## Your Task

For EACH finding listed above, evaluate:

1. **Evidence support**: Does the cited evidence actually support the claim being made? Look for logical leaps, misinterpretations, or conclusions not supported by the evidence.

2. **Context completeness**: Is evidence being quoted selectively in a way that changes its meaning? Check whether surrounding content contradicts or qualifies the finding.

3. **Confidence rating**: Rate as "high", "medium", or "low" based on your evaluation. Do not hesitate to rate findings as low confidence if it's really low confidence.

Respond with a JSON object in the following format:

```json
{{
  "findings": [
    {{
      "finding_id": "<ID from the original finding>",
      "original_claim": "<brief restatement of the claim>",
      "confidence": "high|medium|low",
      "reason": "<1-2 sentence explanation of your rating>",
      "evidence_classification": "code_analysis|comment_derived|control_flow|documentation",
      "flags": []
    }}
  ]
}}
```

IMPORTANT:
- Output ONLY the JSON object, no other text before or after it
- Include ALL findings from the analysis, even if you rate them as high confidence
- Be genuinely skeptical -- a good review often filters out 30-60% of initial findings, but only when warranted by the evidence
- Classify evidence_classification based on what the finding primarily relies on
```

Create `prompts/verify_code.md`:

```markdown
You are a code review expert specializing in distinguishing genuine architectural issues from standard language idioms and patterns.

You are reviewing findings from a codebase analysis. A previous adversarial review has already evaluated each finding. Your job is to apply code-specific verification checks and update the confidence ratings where appropriate.

## Previous Verification Results

{previous_results}

## Original Findings

{findings}

## Source Code

{documents}

## Your Task

For EACH finding, apply these code-specific checks:

1. **Comment-source detection**: Is the finding's evidence primarily drawn from code comments, FIXMEs, TODOs, or documentation strings rather than actual code behavior? If so, add "comment_derived" to flags.

2. **Test vs. production code**: Are the cited files in test directories (t/, tests/, test/, spec/, __tests__/)? If evidence is primarily from test code, add "test_code" to flags. A pattern in test code is generally not a production architectural concern.

3. **Language idiom check**: Is the flagged pattern a standard idiom in the programming language being used? Consider:
   - Perl: Dynamic method installation via symbol table, localised overrides, runtime class determination, AUTOLOAD, string eval for performance
   - Python: Metaclasses, __getattr__, monkey-patching in tests, dynamic class creation
   - Ruby: method_missing, open classes, DSL metaprogramming
   - Java: Reflection-based dispatch, annotation processing, dynamic proxies
   - JavaScript/TypeScript: Prototype manipulation, dynamic property access, Proxy objects
   - Go: Interface-based polymorphism, code generation via go:generate
   If the pattern is a standard idiom, add "standard_idiom" to flags.

4. **Severity calibration**: Given the above checks, is the severity appropriate? A comment-derived finding about test code should not be Critical/P0.

Respond with a JSON object in the same format as the previous results, with updated confidence ratings and flags:

```json
{{
  "findings": [
    {{
      "finding_id": "<ID>",
      "original_claim": "<brief restatement>",
      "confidence": "high|medium|low",
      "reason": "<updated 1-2 sentence explanation incorporating code-specific checks>",
      "evidence_classification": "<updated classification>",
      "flags": ["<any applicable flags: comment_derived, test_code, standard_idiom>"]
    }}
  ]
}}
```

IMPORTANT:
- Output ONLY the JSON object, no other text before or after it
- Include ALL findings, even those unchanged from the previous review
- If a finding was already low confidence and you agree, keep it low but update the reason to include code-specific observations
- Do not hesitate to rate findings as low confidence if it's really low confidence
```

**Step 4: Add schemas to validator.py**

Add to `PROMPT_SCHEMAS` dict in `src/shesha/prompts/validator.py`:

```python
    "verify_adversarial.md": PromptSchema(
        required={"findings", "documents"},
        optional=set(),
    ),
    "verify_code.md": PromptSchema(
        required={"previous_results", "findings", "documents"},
        optional=set(),
    ),
```

**Step 5: Add render methods to loader.py**

Add to `PromptLoader` class in `src/shesha/prompts/loader.py`:

```python
    def render_verify_adversarial_prompt(
        self, findings: str, documents: str
    ) -> str:
        """Render the adversarial verification prompt."""
        return self._prompts["verify_adversarial.md"].format(
            findings=findings,
            documents=documents,
        )

    def render_verify_code_prompt(
        self, previous_results: str, findings: str, documents: str
    ) -> str:
        """Render the code-specific verification prompt."""
        return self._prompts["verify_code.md"].format(
            previous_results=previous_results,
            findings=findings,
            documents=documents,
        )
```

**Step 6: Run tests to verify they pass**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/prompts/ -v`
Expected: All PASS

**Note:** The `test_loader.py` fixture (`tmp_prompts_dir`) likely copies all files from the real prompts dir. If instead it creates minimal files, the fixture will need updating to create `verify_adversarial.md` and `verify_code.md` with their required placeholders. Check the fixture implementation and adapt accordingly.

**Step 7: Run full test suite**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest -x -q`
Expected: All pass

**Step 8: Commit**

```bash
cd .worktrees/semantic-verification && git add prompts/verify_adversarial.md prompts/verify_code.md src/shesha/prompts/validator.py src/shesha/prompts/loader.py tests/unit/prompts/ && git commit -m "feat: add adversarial and code-specific verification prompt templates"
```

---

### Task 7: Engine Integration

This is the core wiring task. The engine calls semantic verification after mechanical verification when `verify=True`.

**Files:**
- Modify: `src/shesha/rlm/engine.py`
- Modify: `tests/unit/rlm/test_engine.py`

**Step 1: Write failing tests**

Add to `tests/unit/rlm/test_engine.py`:

```python
from shesha.rlm.semantic_verification import SemanticVerificationReport


def test_engine_verify_defaults_false():
    """RLMEngine.verify defaults to False."""
    engine = RLMEngine(model="test-model")
    assert engine.verify is False


def test_engine_verify_can_be_enabled():
    """RLMEngine accepts verify=True."""
    engine = RLMEngine(model="test-model", verify=True)
    assert engine.verify is True
```

Add to the `TestRLMEngine` class:

```python
    @patch("shesha.rlm.engine.LLMClient")
    @patch("shesha.rlm.engine.ContainerExecutor")
    def test_engine_runs_semantic_verification_when_enabled(
        self,
        mock_executor_cls: MagicMock,
        mock_llm_cls: MagicMock,
    ) -> None:
        """Engine runs semantic verification when verify=True."""
        import json

        # Mock LLM: first call is the main query, subsequent calls are verification subcalls
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            # Main query response
            MagicMock(
                content='```repl\nFINAL("## P0.1: Issue\\nSee Doc 0.")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            # Adversarial verification subcall response
            MagicMock(
                content=json.dumps({
                    "findings": [{
                        "finding_id": "P0.1",
                        "original_claim": "Issue",
                        "confidence": "high",
                        "reason": "Confirmed.",
                        "evidence_classification": "code_analysis",
                        "flags": [],
                    }]
                }),
                prompt_tokens=200,
                completion_tokens=100,
                total_tokens=300,
            ),
        ]
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        verification_json = json.dumps({
            "citations": [{"doc_id": 0, "found": True}],
            "quotes": [],
        })
        mock_executor.execute.side_effect = [
            # FINAL execution
            MagicMock(
                status="ok", stdout="", stderr="", error=None,
                final_answer="## P0.1: Issue\nSee Doc 0.",
            ),
            # Mechanical verification
            MagicMock(
                status="ok", stdout=verification_json, stderr="", error=None,
                final_answer=None,
            ),
        ]
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify=True, verify_citations=True)
        result = engine.query(
            documents=["Doc content here"],
            question="Find issues",
            doc_names=["main.py"],
        )

        assert result.semantic_verification is not None
        assert len(result.semantic_verification.findings) == 1
        assert result.semantic_verification.findings[0].confidence == "high"

    @patch("shesha.rlm.engine.LLMClient")
    @patch("shesha.rlm.engine.ContainerExecutor")
    def test_engine_skips_semantic_verification_when_disabled(
        self,
        mock_executor_cls: MagicMock,
        mock_llm_cls: MagicMock,
    ) -> None:
        """Engine skips semantic verification when verify=False."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("answer")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.return_value = MagicMock(
            status="ok", stdout="", stderr="", error=None,
            final_answer="answer",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify=False, verify_citations=False)
        result = engine.query(documents=["Doc"], question="What?")

        assert result.semantic_verification is None

    @patch("shesha.rlm.engine.LLMClient")
    @patch("shesha.rlm.engine.ContainerExecutor")
    def test_engine_semantic_verification_failure_does_not_block_answer(
        self,
        mock_executor_cls: MagicMock,
        mock_llm_cls: MagicMock,
    ) -> None:
        """Semantic verification failure doesn't prevent answer delivery."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            MagicMock(
                content='```repl\nFINAL("answer")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            # Verification subcall returns garbage
            MagicMock(
                content="I refuse to output JSON",
                prompt_tokens=200,
                completion_tokens=100,
                total_tokens=300,
            ),
        ]
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.return_value = MagicMock(
            status="ok", stdout="", stderr="", error=None,
            final_answer="answer",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify=True, verify_citations=False)
        result = engine.query(
            documents=["Doc"],
            question="What?",
            doc_names=["file.txt"],
        )

        assert result.answer == "answer"
        assert result.semantic_verification is None
        # Error recorded in trace
        sem_steps = [
            s for s in result.trace.steps
            if s.type == StepType.SEMANTIC_VERIFICATION
        ]
        assert len(sem_steps) >= 1
        assert "error" in sem_steps[-1].content.lower() or "Could not parse" in sem_steps[-1].content
```

**Step 2: Run tests to verify they fail**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/rlm/test_engine.py::test_engine_verify_defaults_false tests/unit/rlm/test_engine.py::test_engine_verify_can_be_enabled -v`
Expected: FAIL (attribute doesn't exist)

**Step 3: Write implementation**

In `src/shesha/rlm/engine.py`:

1. Add imports at the top:

```python
from shesha.rlm.semantic_verification import (
    SemanticVerificationReport,
    detect_content_type,
    gather_cited_documents,
    parse_verification_response,
)
```

2. Add `verify: bool = False` parameter to `RLMEngine.__init__`:

```python
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        max_iterations: int = 20,
        max_output_chars: int = 50000,
        execution_timeout: int = 30,
        max_subcall_content_chars: int = 500_000,
        prompts_dir: Path | None = None,
        pool: ContainerPool | None = None,
        max_traces_per_project: int = 50,
        verify_citations: bool = True,
        verify: bool = False,
    ) -> None:
        # ... existing code ...
        self.verify = verify
```

3. Add `semantic_verification` field to `QueryResult`:

```python
@dataclass
class QueryResult:
    """Result of an RLM query."""

    answer: str
    trace: Trace
    token_usage: TokenUsage
    execution_time: float
    verification: VerificationResult | None = field(default=None)
    semantic_verification: SemanticVerificationReport | None = field(default=None)
```

4. Add a `_run_semantic_verification` method to `RLMEngine`:

```python
    def _run_semantic_verification(
        self,
        final_answer: str,
        documents: list[str],
        doc_names: list[str],
        trace: Trace,
        token_usage: TokenUsage,
        iteration: int,
        on_progress: ProgressCallback | None = None,
        on_step: Callable[[TraceStep], None] | None = None,
    ) -> SemanticVerificationReport | None:
        """Run semantic verification on the final answer.

        Returns SemanticVerificationReport or None if verification fails.
        """
        # Gather cited documents
        cited_docs_text = gather_cited_documents(final_answer, documents, doc_names)
        if not cited_docs_text:
            return None

        # Layer 1: Adversarial verification
        prompt = self.prompt_loader.render_verify_adversarial_prompt(
            findings=final_answer,
            documents=cited_docs_text,
        )

        step = trace.add_step(
            type=StepType.SEMANTIC_VERIFICATION,
            content="Starting adversarial verification (Layer 1)",
            iteration=iteration,
        )
        if on_step:
            on_step(step)
        if on_progress:
            on_progress(StepType.SEMANTIC_VERIFICATION, iteration, "Adversarial verification")

        sub_llm = LLMClient(model=self.model, api_key=self.api_key)
        response = sub_llm.complete(messages=[{"role": "user", "content": prompt}])
        token_usage.prompt_tokens += response.prompt_tokens
        token_usage.completion_tokens += response.completion_tokens

        findings = parse_verification_response(response.content)

        step = trace.add_step(
            type=StepType.SEMANTIC_VERIFICATION,
            content=f"Layer 1 complete: {len(findings)} findings reviewed",
            iteration=iteration,
            tokens_used=response.total_tokens,
        )
        if on_step:
            on_step(step)
        if on_progress:
            on_progress(
                StepType.SEMANTIC_VERIFICATION, iteration,
                f"Layer 1 complete: {len(findings)} findings",
            )

        # Layer 2: Code-specific checks (only for code projects)
        content_type = detect_content_type(doc_names)
        if content_type == "code":
            import json

            layer1_json = json.dumps(
                {"findings": [
                    {
                        "finding_id": f.finding_id,
                        "original_claim": f.original_claim,
                        "confidence": f.confidence,
                        "reason": f.reason,
                        "evidence_classification": f.evidence_classification,
                        "flags": f.flags,
                    }
                    for f in findings
                ]},
                indent=2,
            )

            prompt = self.prompt_loader.render_verify_code_prompt(
                previous_results=layer1_json,
                findings=final_answer,
                documents=cited_docs_text,
            )

            step = trace.add_step(
                type=StepType.SEMANTIC_VERIFICATION,
                content="Starting code-specific verification (Layer 2)",
                iteration=iteration,
            )
            if on_step:
                on_step(step)
            if on_progress:
                on_progress(
                    StepType.SEMANTIC_VERIFICATION, iteration,
                    "Code-specific verification",
                )

            sub_llm2 = LLMClient(model=self.model, api_key=self.api_key)
            response2 = sub_llm2.complete(messages=[{"role": "user", "content": prompt}])
            token_usage.prompt_tokens += response2.prompt_tokens
            token_usage.completion_tokens += response2.completion_tokens

            findings = parse_verification_response(response2.content)

            step = trace.add_step(
                type=StepType.SEMANTIC_VERIFICATION,
                content=f"Layer 2 complete: {len(findings)} findings reviewed",
                iteration=iteration,
                tokens_used=response2.total_tokens,
            )
            if on_step:
                on_step(step)
            if on_progress:
                on_progress(
                    StepType.SEMANTIC_VERIFICATION, iteration,
                    f"Layer 2 complete: {len(findings)} findings",
                )

        return SemanticVerificationReport(
            findings=findings,
            content_type=content_type,
        )
```

5. Wire it into `query()` — after the mechanical verification block (around line 353), add:

```python
                    semantic_verification = None
                    if self.verify:
                        try:
                            semantic_verification = self._run_semantic_verification(
                                final_answer=final_answer,
                                documents=documents,
                                doc_names=doc_names or [],
                                trace=trace,
                                token_usage=token_usage,
                                iteration=iteration,
                                on_progress=on_progress,
                                on_step=_write_step,
                            )
                        except Exception as exc:
                            step = trace.add_step(
                                type=StepType.SEMANTIC_VERIFICATION,
                                content=f"Semantic verification error: {exc}",
                                iteration=iteration,
                            )
                            _write_step(step)
                            if on_progress:
                                on_progress(
                                    StepType.SEMANTIC_VERIFICATION,
                                    iteration,
                                    f"Semantic verification error: {exc}",
                                )
```

6. Add `semantic_verification` to the `QueryResult` construction:

```python
                    query_result = QueryResult(
                        answer=final_answer,
                        trace=trace,
                        token_usage=token_usage,
                        execution_time=time.time() - start_time,
                        verification=verification,
                        semantic_verification=semantic_verification,
                    )
```

**Step 4: Run tests to verify they pass**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/rlm/test_engine.py -v`
Expected: All PASS

**Step 5: Run full test suite**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest -x -q`
Expected: All pass

**Step 6: Commit**

```bash
cd .worktrees/semantic-verification && git add src/shesha/rlm/engine.py src/shesha/rlm/semantic_verification.py tests/unit/rlm/test_engine.py && git commit -m "feat: integrate semantic verification into RLM engine"
```

---

### Task 8: DI Wiring (Shesha -> RLMEngine)

**Files:**
- Modify: `src/shesha/shesha.py`
- Modify: `tests/unit/test_shesha_di.py`

**Step 1: Write failing test**

Add to `tests/unit/test_shesha_di.py`:

```python
class TestVerifyWiring:
    """Tests for verify config wiring."""

    def test_verify_passed_to_engine(self, tmp_path: Path) -> None:
        """verify config is passed to RLMEngine."""
        from shesha.config import SheshaConfig

        config = SheshaConfig(model="test-model", verify=True)
        shesha = Shesha(config=config, storage=_make_mock_storage())
        assert shesha._rlm_engine.verify is True

    def test_verify_default_false(self, tmp_path: Path) -> None:
        """verify defaults to False in RLMEngine."""
        from shesha.config import SheshaConfig

        config = SheshaConfig(model="test-model")
        shesha = Shesha(config=config, storage=_make_mock_storage())
        assert shesha._rlm_engine.verify is False
```

**Step 2: Run test to verify it fails**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/test_shesha_di.py::TestVerifyWiring -v`
Expected: FAIL (verify not passed through)

**Step 3: Write implementation**

In `src/shesha/shesha.py`, add `verify=config.verify` to the `RLMEngine(...)` constructor call (around line 95):

```python
        self._rlm_engine = engine or RLMEngine(
            model=config.model,
            api_key=config.api_key,
            max_iterations=config.max_iterations,
            max_output_chars=config.max_output_chars,
            execution_timeout=config.execution_timeout_sec,
            max_traces_per_project=config.max_traces_per_project,
            verify_citations=config.verify_citations,
            verify=config.verify,
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/test_shesha_di.py::TestVerifyWiring -v`
Expected: All PASS

**Step 5: Run full test suite**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest -x -q`
Expected: All pass

**Step 6: Commit**

```bash
cd .worktrees/semantic-verification && git add src/shesha/shesha.py tests/unit/test_shesha_di.py && git commit -m "feat: wire verify config through Shesha to RLMEngine"
```

---

### Task 9: CLI --verify Flag and Output Formatting

**Files:**
- Modify: `examples/repo.py`
- Modify: `examples/barsoom.py`
- Modify: `examples/script_utils.py`

**Step 1: Write failing tests for output formatting**

Create or append to `tests/unit/test_script_utils.py`:

```python
from shesha.rlm.semantic_verification import (
    FindingVerification,
    SemanticVerificationReport,
)

# Import from examples needs sys.path manipulation
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "examples"))
from script_utils import format_verified_output


class TestFormatVerifiedOutput:
    """Tests for format_verified_output()."""

    def test_formats_summary_and_appendix(self) -> None:
        """Output contains both verified findings and appendix."""
        report = SemanticVerificationReport(
            findings=[
                FindingVerification(
                    finding_id="P1.1",
                    original_claim="Real issue",
                    confidence="high",
                    reason="Confirmed by code.",
                    evidence_classification="code_analysis",
                    flags=[],
                ),
                FindingVerification(
                    finding_id="P0.1",
                    original_claim="False alarm",
                    confidence="low",
                    reason="Standard idiom.",
                    evidence_classification="code_analysis",
                    flags=["standard_idiom"],
                ),
            ],
            content_type="code",
        )
        original_answer = "## P1.1: Real issue\nDetails.\n\n## P0.1: False alarm\nMore details."
        output = format_verified_output(original_answer, report)

        assert "Verified Findings" in output
        assert "Verification Appendix" in output
        assert "P1.1" in output
        assert "P0.1" in output
        assert "standard_idiom" in output

    def test_no_high_confidence_shows_message(self) -> None:
        """When no findings are high/medium confidence, shows appropriate message."""
        report = SemanticVerificationReport(
            findings=[
                FindingVerification(
                    finding_id="P0.1",
                    original_claim="Bogus",
                    confidence="low",
                    reason="Not real.",
                    evidence_classification="code_analysis",
                    flags=[],
                ),
            ],
            content_type="general",
        )
        output = format_verified_output("Original", report)
        assert "0" in output or "no verified findings" in output.lower() or "None" in output

    def test_all_high_confidence_no_appendix_content(self) -> None:
        """When all findings are high confidence, appendix says none filtered."""
        report = SemanticVerificationReport(
            findings=[
                FindingVerification(
                    finding_id="P1.1",
                    original_claim="Good finding",
                    confidence="high",
                    reason="Confirmed.",
                    evidence_classification="code_analysis",
                    flags=[],
                ),
            ],
            content_type="code",
        )
        output = format_verified_output("Original", report)
        assert "Verified Findings" in output
        assert "0 findings filtered" in output or "no findings filtered" in output.lower() or "Appendix" in output
```

**Step 2: Run tests to verify they fail**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/test_script_utils.py::TestFormatVerifiedOutput -v`
Expected: FAIL with ImportError

**Step 3: Write implementation**

Add to `examples/script_utils.py`:

```python
from shesha.rlm.semantic_verification import SemanticVerificationReport


def format_verified_output(
    original_answer: str,
    report: SemanticVerificationReport,
) -> str:
    """Format analysis output with verification summary and appendix.

    Args:
        original_answer: The original FINAL answer from the RLM.
        report: Semantic verification report.

    Returns:
        Formatted string with verified findings summary and appendix.
    """
    high = report.high_confidence
    low = report.low_confidence
    total = len(report.findings)

    lines: list[str] = []

    # Section A: Verified Summary
    lines.append(
        f"## Verified Findings ({len(high)} of {total}"
        f" -- High/Medium confidence)\n"
    )

    if high:
        for f in high:
            flags_str = f"  Flags: {', '.join(f.flags)}\n" if f.flags else ""
            lines.append(
                f"### {f.finding_id}: {f.original_claim} "
                f"({f.confidence.capitalize()} confidence)\n"
                f"  {f.reason}\n"
                f"{flags_str}"
            )
    else:
        lines.append("No findings met the high/medium confidence threshold.\n")

    lines.append("---\n")

    # Section B: Appendix
    lines.append(
        f"## Verification Appendix ({len(low)} findings filtered)\n"
    )

    if low:
        for f in low:
            flags_str = f"  Flags: {', '.join(f.flags)}" if f.flags else ""
            lines.append(
                f"{f.finding_id}: {f.original_claim} -- LOW CONFIDENCE\n"
                f"  Reason: {f.reason}\n"
                f"{flags_str}\n"
            )
    else:
        lines.append("No findings were filtered.\n")

    # Include original answer below for reference
    lines.append("---\n")
    lines.append("## Original Analysis\n")
    lines.append(original_answer)

    return "\n".join(lines)
```

**Step 4: Add --verify flag to repo.py**

In `examples/repo.py`, add to `parse_args()`:

```python
    parser.add_argument(
        "--verify",
        action="store_true",
        help=(
            "Run post-analysis semantic verification. Produces higher-accuracy "
            "results by adversarially reviewing all findings. Note: this can "
            "significantly increase analysis time and token count "
            "(typically 1-2 additional LLM calls)."
        ),
    )
```

In `main()`, pass `verify` to config (around line 518):

```python
    config = SheshaConfig.load(storage_path=STORAGE_PATH, verify=args.verify)
```

In `run_interactive_loop()`, after `print(result.answer)` (around line 471), add:

```python
            if result.semantic_verification is not None:
                print()
                print(format_verified_output(result.answer, result.semantic_verification))
            else:
                print(result.answer)
```

(Replace the existing `print(result.answer)` with this conditional.)

Also add `format_verified_output` to the imports from `script_utils`.

**Step 5: Add --verify flag to barsoom.py**

Same pattern as repo.py:

1. Add `--verify` argument to `parse_args()`:

```python
    parser.add_argument(
        "--verify",
        action="store_true",
        help=(
            "Run post-analysis semantic verification. Produces higher-accuracy "
            "results by adversarially reviewing all findings. Note: this can "
            "significantly increase analysis time and token count "
            "(typically 1-2 additional LLM calls)."
        ),
    )
```

2. Pass `verify` to config:

```python
    config = SheshaConfig.load(storage_path=STORAGE_PATH, verify=args.verify)
```

3. In both the `--prompt` handler and the interactive loop, replace `print(result.answer)` with the conditional that checks `result.semantic_verification`.

4. Add `format_verified_output` to the imports from `script_utils`.

**Step 6: Update format_progress step names in script_utils.py**

In `format_progress()`, add the new step types to `step_names`:

```python
    step_names = {
        StepType.CODE_GENERATED: "Generating code",
        StepType.CODE_OUTPUT: "Executing code",
        StepType.SUBCALL_REQUEST: "Sub-LLM query",
        StepType.SUBCALL_RESPONSE: "Sub-LLM response",
        StepType.FINAL_ANSWER: "Final answer",
        StepType.ERROR: "Error",
        StepType.VERIFICATION: "Verification",
        StepType.SEMANTIC_VERIFICATION: "Semantic verification",
    }
```

**Step 7: Run tests to verify they pass**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest tests/unit/test_script_utils.py -v`
Expected: All PASS

**Step 8: Run full test suite**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && pytest -x -q`
Expected: All pass

**Step 9: Commit**

```bash
cd .worktrees/semantic-verification && git add examples/repo.py examples/barsoom.py examples/script_utils.py tests/unit/test_script_utils.py && git commit -m "feat: add --verify CLI flag and verified output formatting"
```

---

### Task 10: CHANGELOG and Final Checks

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Update CHANGELOG**

Add under `## [Unreleased]` / `### Added`:

```markdown
- Semantic verification (`--verify` flag): opt-in post-analysis adversarial review that checks whether findings are supported by evidence. For code projects, adds code-specific checks for comment-mining, test/production conflation, and language idiom misidentification. Output reformatted into verified summary + appendix. Note: significantly increases analysis time and token cost (1-2 additional LLM calls)
```

**Step 2: Run full test suite including linting**

Run: `cd .worktrees/semantic-verification && source .venv/bin/activate && make all`
Expected: All pass (format + lint + typecheck + test)

**Step 3: Fix any issues found by mypy/ruff**

Address any type errors or lint issues.

**Step 4: Commit**

```bash
cd .worktrees/semantic-verification && git add CHANGELOG.md && git commit -m "docs: add semantic verification to CHANGELOG"
```

If there were lint/type fixes:

```bash
cd .worktrees/semantic-verification && git add -u && git commit -m "fix: address mypy/ruff issues in semantic verification"
```

---

## Execution Notes

- **Working directory:** All commands run from `.worktrees/semantic-verification`
- **Activate venv:** `source .venv/bin/activate` before every test/commit session
- **TDD discipline:** Never write implementation before the failing test
- **After each commit:** Run `pytest -x -q` to catch regressions early
- **After Task 10:** Run `make all` (format + lint + typecheck + test) for final validation
- **Prompt template note:** The `{{` and `}}` in prompt templates are Python `str.format()` escaped braces — they render as literal `{` and `}` in the final prompt
- **Test fixture note:** In Task 6, the `tmp_prompts_dir` fixture in `test_loader.py` may need updating to include the new prompt files. Check its implementation before writing the tests.
