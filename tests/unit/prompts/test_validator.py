"""Tests for prompt validator."""

import pytest

from shesha.prompts.validator import (
    PROMPT_SCHEMAS,
    PromptValidationError,
    extract_placeholders,
    validate_prompt,
)


def test_extract_placeholders_finds_simple():
    """extract_placeholders finds {name} patterns."""
    text = "Hello {name}, you have {count} messages."
    placeholders = extract_placeholders(text)
    assert placeholders == {"name", "count"}


def test_extract_placeholders_handles_format_spec():
    """extract_placeholders handles {name:,} format specs."""
    text = "Total: {total_chars:,} chars"
    placeholders = extract_placeholders(text)
    assert placeholders == {"total_chars"}


def test_extract_placeholders_empty():
    """extract_placeholders returns empty set for no placeholders."""
    text = "No placeholders here"
    placeholders = extract_placeholders(text)
    assert placeholders == set()


def test_extract_placeholders_ignores_escaped_braces():
    """extract_placeholders ignores {{escaped}} braces."""
    text = "Use {{literal}} braces and {real_placeholder}"
    placeholders = extract_placeholders(text)
    assert placeholders == {"real_placeholder"}


def test_prompt_schemas_defined():
    """PROMPT_SCHEMAS defines required placeholders for each prompt."""
    assert "system.md" in PROMPT_SCHEMAS
    assert "subcall.md" in PROMPT_SCHEMAS
    assert "code_required.md" in PROMPT_SCHEMAS

    assert "doc_count" in PROMPT_SCHEMAS["system.md"].required
    assert "instruction" in PROMPT_SCHEMAS["subcall.md"].required
    assert PROMPT_SCHEMAS["code_required.md"].required == set()


def test_validate_prompt_passes_valid():
    """validate_prompt passes when all required placeholders present."""
    content = (
        "Hello {instruction}\n"
        "<untrusted_document_content>\n"
        "{content}\n"
        "</untrusted_document_content>\n"
    )
    # Should not raise
    validate_prompt("subcall.md", content)


def test_validate_prompt_fails_missing():
    """validate_prompt raises for missing required placeholder."""
    content = "Hello {instruction}"  # missing {content}
    with pytest.raises(PromptValidationError) as exc_info:
        validate_prompt("subcall.md", content)
    assert "missing required placeholder" in str(exc_info.value).lower()
    assert "content" in str(exc_info.value)


def test_validate_prompt_fails_unknown():
    """validate_prompt raises for unknown placeholder."""
    content = "Hello {instruction}, {content}, {typo}"
    with pytest.raises(PromptValidationError) as exc_info:
        validate_prompt("subcall.md", content)
    assert "unknown placeholder" in str(exc_info.value).lower()
    assert "typo" in str(exc_info.value)


def test_validate_subcall_missing_untrusted_tags_fails():
    """validate_prompt rejects subcall.md without untrusted_document_content tags."""
    # Template with placeholders but no security tags
    content = "{instruction}\n\n{content}\n"
    with pytest.raises(PromptValidationError) as exc_info:
        validate_prompt("subcall.md", content)
    assert "untrusted_document_content" in str(exc_info.value)


def test_validate_subcall_with_untrusted_tags_passes():
    """validate_prompt accepts subcall.md with untrusted_document_content tags."""
    content = (
        "{instruction}\n\n<untrusted_document_content>\n{content}\n</untrusted_document_content>\n"
    )
    # Should not raise
    validate_prompt("subcall.md", content)


def test_verify_adversarial_schema_defined():
    """PROMPT_SCHEMAS includes verify_adversarial.md with required placeholders."""
    assert "verify_adversarial.md" in PROMPT_SCHEMAS
    schema = PROMPT_SCHEMAS["verify_adversarial.md"]
    assert schema.required == {"findings", "documents"}
    assert schema.optional == set()
    assert schema.required_file is False


def test_verify_code_schema_defined():
    """PROMPT_SCHEMAS includes verify_code.md with required placeholders."""
    assert "verify_code.md" in PROMPT_SCHEMAS
    schema = PROMPT_SCHEMAS["verify_code.md"]
    assert schema.required == {"previous_results", "findings", "documents"}
    assert schema.optional == set()
    assert schema.required_file is False


def test_core_schemas_are_required_files():
    """Core prompt schemas (system, subcall, code_required) are required files."""
    for name in ("system.md", "subcall.md", "code_required.md"):
        assert PROMPT_SCHEMAS[name].required_file is True


def test_validate_verify_adversarial_passes_valid():
    """validate_prompt passes for valid verify_adversarial.md content."""
    content = "Verify these {findings} against {documents}."
    validate_prompt("verify_adversarial.md", content)


def test_validate_verify_adversarial_fails_missing_placeholder():
    """validate_prompt raises when verify_adversarial.md is missing a placeholder."""
    content = "Only {findings} here."
    with pytest.raises(PromptValidationError) as exc_info:
        validate_prompt("verify_adversarial.md", content)
    assert "documents" in str(exc_info.value)


def test_validate_verify_code_passes_valid():
    """validate_prompt passes for valid verify_code.md content."""
    content = "Review {previous_results} for {findings} in {documents}."
    validate_prompt("verify_code.md", content)


def test_validate_verify_code_fails_missing_placeholder():
    """validate_prompt raises when verify_code.md is missing a placeholder."""
    content = "Only {findings} and {documents} here."
    with pytest.raises(PromptValidationError) as exc_info:
        validate_prompt("verify_code.md", content)
    assert "previous_results" in str(exc_info.value)
