"""Tests for RLM prompts."""

from shesha.rlm.prompts import build_subcall_prompt, build_system_prompt


def test_system_prompt_contains_security_warning():
    """System prompt contains prompt injection warning."""
    prompt = build_system_prompt(
        doc_count=3,
        total_chars=10000,
        doc_names=["a.txt", "b.txt", "c.txt"],
    )
    assert "untrusted" in prompt.lower()
    assert "adversarial" in prompt.lower() or "injection" in prompt.lower()


def test_system_prompt_contains_context_info():
    """System prompt contains context information."""
    prompt = build_system_prompt(
        doc_count=3,
        total_chars=10000,
        doc_names=["a.txt", "b.txt", "c.txt"],
    )
    assert "3" in prompt  # doc count
    assert "a.txt" in prompt


def test_system_prompt_explains_final():
    """System prompt explains FINAL function."""
    prompt = build_system_prompt(
        doc_count=1,
        total_chars=100,
        doc_names=["doc.txt"],
    )
    assert "FINAL" in prompt


def test_subcall_prompt_wraps_content():
    """Subcall prompt wraps content in untrusted tags."""
    prompt = build_subcall_prompt(
        instruction="Summarize this",
        content="Document content here",
    )
    assert "<untrusted_document_content>" in prompt
    assert "</untrusted_document_content>" in prompt
    assert "Document content here" in prompt
    assert "Summarize this" in prompt


def test_system_prompt_contains_sub_llm_capacity_hint():
    """System prompt tells LLM about sub-LLM's large context capacity."""
    prompt = build_system_prompt(
        doc_count=3,
        total_chars=100000,
        doc_names=["a.txt", "b.txt", "c.txt"],
    )
    # Must mention ~500K capacity to prevent excessive chunking
    assert "500K" in prompt or "500k" in prompt


def test_system_prompt_contains_batching_guidance():
    """System prompt encourages batching documents to minimize API calls."""
    prompt = build_system_prompt(
        doc_count=3,
        total_chars=100000,
        doc_names=["a.txt", "b.txt", "c.txt"],
    )
    prompt_lower = prompt.lower()
    # Must encourage batching/efficiency
    assert "batch" in prompt_lower or "minimize" in prompt_lower
    assert "api call" in prompt_lower or "llm_query" in prompt_lower
