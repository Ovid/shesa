"""Tests for RLM prompts."""

from shesha.prompts import PromptLoader
from shesha.rlm.prompts import MAX_SUBCALL_CHARS, truncate_code_output, wrap_repl_output


def _build_doc_sizes_list(doc_infos: list[tuple[str, str]]) -> str:
    """Build doc_sizes_list string from list of (name, size_str) tuples."""
    lines = [f"    - context[{i}] ({name}): {size}" for i, (name, size) in enumerate(doc_infos)]
    return "\n".join(lines)


def test_system_prompt_contains_security_warning():
    """System prompt contains prompt injection warning."""
    loader = PromptLoader()

    prompt = loader.render_system_prompt(max_subcall_chars=MAX_SUBCALL_CHARS)
    assert "untrusted" in prompt.lower()
    assert "adversarial" in prompt.lower() or "injection" in prompt.lower()


def test_system_prompt_no_longer_contains_metadata():
    """System prompt does not contain doc_count, total_chars, or doc_sizes_list."""
    loader = PromptLoader()

    prompt = loader.render_system_prompt(max_subcall_chars=MAX_SUBCALL_CHARS)
    # These dynamic values should NOT be in the system prompt anymore
    assert "{doc_count}" not in prompt
    assert "{total_chars" not in prompt
    assert "{doc_sizes_list}" not in prompt


def test_system_prompt_explains_final():
    """System prompt explains FINAL function."""
    loader = PromptLoader()

    prompt = loader.render_system_prompt(max_subcall_chars=MAX_SUBCALL_CHARS)
    assert "FINAL" in prompt


def test_subcall_prompt_wraps_content():
    """Subcall prompt wraps content in untrusted tags."""
    loader = PromptLoader()

    prompt = loader.render_subcall_prompt(
        instruction="Summarize this",
        content="Document content here",
    )
    assert "<untrusted_document_content>" in prompt
    assert "</untrusted_document_content>" in prompt
    assert "Document content here" in prompt
    assert "Summarize this" in prompt


def test_system_prompt_contains_sub_llm_limit():
    """System prompt tells LLM about sub-LLM character limit."""
    loader = PromptLoader()

    prompt = loader.render_system_prompt(max_subcall_chars=MAX_SUBCALL_CHARS)
    # Must mention the limit (500,000 formatted with commas)
    assert "500,000" in prompt or "500000" in prompt


def test_system_prompt_contains_chunking_guidance():
    """System prompt explains chunking strategy for large documents."""
    loader = PromptLoader()

    prompt = loader.render_system_prompt(max_subcall_chars=MAX_SUBCALL_CHARS)
    prompt_lower = prompt.lower()
    # Must explain chunking strategy
    assert "chunk" in prompt_lower
    # Must mention buffer pattern for complex queries
    assert "buffer" in prompt_lower


def test_subcall_prompt_no_size_limit():
    """Subcall prompt passes content through without modification."""
    loader = PromptLoader()
    large_content = "x" * 600_000  # 600K chars

    prompt = loader.render_subcall_prompt(
        instruction="Summarize this",
        content=large_content,
    )

    # Content should be passed through completely
    assert large_content in prompt
    assert "<untrusted_document_content>" in prompt


def test_system_prompt_requires_document_grounding():
    """System prompt instructs LLM to answer only from documents, not own knowledge."""
    loader = PromptLoader()

    prompt = loader.render_system_prompt(max_subcall_chars=MAX_SUBCALL_CHARS)
    prompt_lower = prompt.lower()

    # Must instruct to use only documents
    assert "only" in prompt_lower and "document" in prompt_lower

    # Must instruct to not use own knowledge
    assert "own knowledge" in prompt_lower or "prior knowledge" in prompt_lower

    # Must instruct what to do if info not found
    assert "not found" in prompt_lower or "not contain" in prompt_lower


def test_context_metadata_prompt_exists():
    """PromptLoader can render context metadata."""
    loader = PromptLoader()

    doc_sizes_list = _build_doc_sizes_list(
        [
            ("a.txt", "5,000 chars"),
            ("b.txt", "4,000 chars"),
            ("c.txt", "6,000 chars"),
        ]
    )

    result = loader.render_context_metadata(
        doc_count=3,
        total_chars=15000,
        doc_sizes_list=doc_sizes_list,
    )
    assert isinstance(result, str)
    assert len(result) > 0


def test_context_metadata_contains_doc_info():
    """Rendered context metadata includes doc count, total chars, and chunk lengths."""
    loader = PromptLoader()

    doc_sizes_list = _build_doc_sizes_list(
        [
            ("a.txt", "5,000 chars"),
            ("b.txt", "4,000 chars"),
            ("c.txt", "6,000 chars"),
        ]
    )

    result = loader.render_context_metadata(
        doc_count=3,
        total_chars=15000,
        doc_sizes_list=doc_sizes_list,
    )
    assert "3" in result  # doc count
    assert "15,000" in result  # total chars
    assert "a.txt" in result or "context[0]" in result  # doc sizes


def test_context_metadata_warns_about_oversized_documents():
    """Context metadata warns when a document exceeds the sub-LLM limit."""
    loader = PromptLoader()

    oversized = MAX_SUBCALL_CHARS + 10000
    doc_sizes_list = _build_doc_sizes_list(
        [
            ("small.txt", "100,000 chars"),
            ("large.txt", f"{oversized:,} chars EXCEEDS LIMIT - must chunk"),
        ]
    )

    result = loader.render_context_metadata(
        doc_count=2,
        total_chars=oversized + 100000,
        doc_sizes_list=doc_sizes_list,
    )
    assert "EXCEEDS LIMIT" in result or "must chunk" in result.lower()
    assert "small.txt" in result or "context[0]" in result


def test_system_prompt_explains_error_handling():
    """System prompt explains how to handle size limit errors."""
    loader = PromptLoader()

    prompt = loader.render_system_prompt(max_subcall_chars=MAX_SUBCALL_CHARS)
    prompt_lower = prompt.lower()
    # Must explain what to do when hitting limit
    assert "error" in prompt_lower
    assert "retry" in prompt_lower or "chunk" in prompt_lower


def test_code_required_prompt():
    """code_required prompt asks for REPL code."""
    loader = PromptLoader()

    prompt = loader.render_code_required()

    # Should ask for code in a repl block
    assert "repl" in prompt.lower() or "code" in prompt.lower()


def test_wrap_repl_output_basic():
    """wrap_repl_output wraps output in untrusted tags."""
    output = "print result"

    wrapped = wrap_repl_output(output)

    assert '<repl_output type="untrusted_document_content">' in wrapped
    assert "</repl_output>" in wrapped
    assert "print result" in wrapped


def test_wrap_repl_output_does_not_truncate():
    """wrap_repl_output is a pure wrapper, truncation happens per-block."""
    large_output = "x" * 60000  # 60K chars

    wrapped = wrap_repl_output(large_output)

    # Should NOT be truncated — wrap_repl_output just wraps in tags
    assert "truncated" not in wrapped.lower()
    assert large_output in wrapped
    assert '<repl_output type="untrusted_document_content">' in wrapped


def test_truncate_code_output_under_limit():
    """Output under the limit is returned unchanged."""
    output = "x" * 19000  # Under 20K

    result = truncate_code_output(output, max_chars=20_000)

    assert result == output


def test_truncate_code_output_over_limit():
    """Output over the limit is truncated with a nudge message."""
    output = "x" * 25000  # Over 20K

    result = truncate_code_output(output, max_chars=20_000)

    # Should be truncated to max_chars
    assert len(result) < len(output)
    # Should include nudge message referencing llm_query()
    assert "truncated" in result.lower()
    assert "20,000" in result
    assert "25,000" in result
    assert "llm_query()" in result


def test_truncate_code_output_exact_limit():
    """Output exactly at the limit is returned unchanged."""
    output = "x" * 20_000

    result = truncate_code_output(output, max_chars=20_000)

    assert result == output


def test_wrap_subcall_content_basic():
    """wrap_subcall_content wraps content in untrusted tags."""
    from shesha.rlm.prompts import wrap_subcall_content

    content = "Document text here"
    wrapped = wrap_subcall_content(content)

    assert "<untrusted_document_content>" in wrapped
    assert "</untrusted_document_content>" in wrapped
    assert "Document text here" in wrapped


def test_wrap_subcall_content_preserves_full_content():
    """wrap_subcall_content does not truncate content."""
    from shesha.rlm.prompts import wrap_subcall_content

    large_content = "x" * 600_000
    wrapped = wrap_subcall_content(large_content)

    assert large_content in wrapped
    assert "truncated" not in wrapped.lower()


def _render_default_prompt() -> str:
    """Helper to render a system prompt with default test values."""
    loader = PromptLoader()
    return loader.render_system_prompt(max_subcall_chars=MAX_SUBCALL_CHARS)


def test_iteration_zero_prompt_exists():
    """PromptLoader can render an iteration-0 prompt template."""
    loader = PromptLoader()
    result = loader.render_iteration_zero(question="What color is the sky?")
    assert isinstance(result, str)
    assert len(result) > 0


def test_iteration_zero_prompt_contains_safeguard():
    """Rendered iteration-0 template includes safeguard language."""
    loader = PromptLoader()
    result = loader.render_iteration_zero(question="What color is the sky?")
    assert "don't just provide a final answer yet" in result.lower()
    assert "look through" in result.lower()


def test_iteration_zero_prompt_includes_question():
    """Rendered iteration-0 template includes the question."""
    loader = PromptLoader()
    result = loader.render_iteration_zero(question="What color is the sky?")
    assert "What color is the sky?" in result


def test_system_prompt_contains_scout_and_analyze_phases():
    """System prompt describes scout and analyze phases."""
    prompt = _render_default_prompt()
    prompt_lower = prompt.lower()

    # Must mention scout and analyze phases
    assert "scout" in prompt_lower
    assert "analyze" in prompt_lower


def test_system_prompt_recommends_chunk_classify_synthesize():
    """System prompt teaches the chunk -> llm_query per chunk -> buffer -> synthesize strategy."""
    prompt = _render_default_prompt()
    prompt_lower = prompt.lower()

    # Must describe the chunking strategy
    assert "chunk" in prompt_lower
    # Must describe querying per chunk
    assert "per chunk" in prompt_lower or "each chunk" in prompt_lower
    # Must describe buffer/synthesize pattern
    assert "buffer" in prompt_lower


def test_system_prompt_error_handling_uses_try_except():
    """Error handling section uses try/except, not string-check pattern."""
    prompt = _render_default_prompt()

    # Must use try/except pattern
    assert "try:" in prompt
    assert "except ValueError" in prompt or "except ValueError:" in prompt
    # Must NOT use the old string-check pattern
    assert '"exceeds" in result' not in prompt


def test_system_prompt_encourages_subcall_use():
    """System prompt encourages using llm_query for semantic analysis."""
    prompt = _render_default_prompt()
    prompt_lower = prompt.lower()

    # Must encourage sub-call use, not minimize it
    assert "strongly encouraged" in prompt_lower
    # Must mention semantic analysis as a use case
    assert "semantic" in prompt_lower
    # Must mention batching for efficiency
    assert "batch" in prompt_lower


def test_system_prompt_truncation_warning():
    """System prompt warns that REPL output is truncated to motivate sub-call usage."""
    prompt = _render_default_prompt()
    prompt_lower = prompt.lower()

    assert "truncated" in prompt_lower
    assert "llm_query" in prompt_lower


def test_system_prompt_confidence_framing():
    """System prompt encourages heavy sub-call usage with confidence framing."""
    prompt = _render_default_prompt()
    prompt_lower = prompt.lower()

    # Must frame sub-LLMs as powerful and encourage large payloads
    assert "powerful" in prompt_lower
    assert "don't be afraid" in prompt_lower


def test_system_prompt_has_multiple_examples():
    """System prompt has multiple example patterns showing llm_query usage."""
    prompt = _render_default_prompt()

    # Must have at least 3 examples (simple, iterative, batched)
    assert "Example 1" in prompt
    assert "Example 2" in prompt
    assert "Example 3" in prompt


def test_system_prompt_examples_use_llm_query():
    """All examples demonstrate llm_query or llm_query_batched usage."""
    prompt = _render_default_prompt()

    # Every example should use llm_query or llm_query_batched
    assert "llm_query(" in prompt
    assert "llm_query_batched(" in prompt
