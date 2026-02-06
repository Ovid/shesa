"""Tests for RLM prompts."""

from shesha.prompts import PromptLoader
from shesha.rlm.prompts import MAX_SUBCALL_CHARS, wrap_repl_output


def _build_doc_sizes_list(doc_infos: list[tuple[str, str]]) -> str:
    """Build doc_sizes_list string from list of (name, size_str) tuples."""
    lines = [f"    - context[{i}] ({name}): {size}" for i, (name, size) in enumerate(doc_infos)]
    return "\n".join(lines)


def test_system_prompt_contains_security_warning():
    """System prompt contains prompt injection warning."""
    loader = PromptLoader()

    doc_sizes_list = _build_doc_sizes_list(
        [
            ("a.txt", "3,000 chars"),
            ("b.txt", "3,500 chars"),
            ("c.txt", "3,500 chars"),
        ]
    )

    prompt = loader.render_system_prompt(
        doc_count=3,
        total_chars=10000,
        doc_sizes_list=doc_sizes_list,
        max_subcall_chars=MAX_SUBCALL_CHARS,
    )
    assert "untrusted" in prompt.lower()
    assert "adversarial" in prompt.lower() or "injection" in prompt.lower()


def test_system_prompt_contains_context_info():
    """System prompt contains context information."""
    loader = PromptLoader()

    doc_sizes_list = _build_doc_sizes_list(
        [
            ("a.txt", "3,000 chars"),
            ("b.txt", "3,500 chars"),
            ("c.txt", "3,500 chars"),
        ]
    )

    prompt = loader.render_system_prompt(
        doc_count=3,
        total_chars=10000,
        doc_sizes_list=doc_sizes_list,
        max_subcall_chars=MAX_SUBCALL_CHARS,
    )
    assert "3" in prompt  # doc count
    assert "a.txt" in prompt


def test_system_prompt_explains_final():
    """System prompt explains FINAL function."""
    loader = PromptLoader()

    doc_sizes_list = "    - context[0] (doc.txt): 100 chars"

    prompt = loader.render_system_prompt(
        doc_count=1,
        total_chars=100,
        doc_sizes_list=doc_sizes_list,
        max_subcall_chars=MAX_SUBCALL_CHARS,
    )
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

    doc_sizes_list = _build_doc_sizes_list(
        [
            ("a.txt", "30,000 chars"),
            ("b.txt", "35,000 chars"),
            ("c.txt", "35,000 chars"),
        ]
    )

    prompt = loader.render_system_prompt(
        doc_count=3,
        total_chars=100000,
        doc_sizes_list=doc_sizes_list,
        max_subcall_chars=MAX_SUBCALL_CHARS,
    )
    # Must mention the limit (500,000 formatted with commas)
    assert "500,000" in prompt or "500000" in prompt


def test_system_prompt_contains_chunking_guidance():
    """System prompt explains chunking strategy for large documents."""
    loader = PromptLoader()

    doc_sizes_list = _build_doc_sizes_list(
        [
            ("a.txt", "30,000 chars"),
            ("b.txt", "35,000 chars"),
            ("c.txt", "35,000 chars"),
        ]
    )

    prompt = loader.render_system_prompt(
        doc_count=3,
        total_chars=100000,
        doc_sizes_list=doc_sizes_list,
        max_subcall_chars=MAX_SUBCALL_CHARS,
    )
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

    doc_sizes_list = _build_doc_sizes_list(
        [
            ("a.txt", "3,000 chars"),
            ("b.txt", "3,500 chars"),
            ("c.txt", "3,500 chars"),
        ]
    )

    prompt = loader.render_system_prompt(
        doc_count=3,
        total_chars=10000,
        doc_sizes_list=doc_sizes_list,
        max_subcall_chars=MAX_SUBCALL_CHARS,
    )
    prompt_lower = prompt.lower()

    # Must instruct to use only documents
    assert "only" in prompt_lower and "document" in prompt_lower

    # Must instruct to not use own knowledge
    assert "own knowledge" in prompt_lower or "prior knowledge" in prompt_lower

    # Must instruct what to do if info not found
    assert "not found" in prompt_lower or "not contain" in prompt_lower


def test_system_prompt_includes_per_document_sizes():
    """System prompt shows size of each document when doc_sizes provided."""
    loader = PromptLoader()

    doc_sizes_list = _build_doc_sizes_list(
        [
            ("a.txt", "5,000 chars"),
            ("b.txt", "4,000 chars"),
            ("c.txt", "6,000 chars"),
        ]
    )

    prompt = loader.render_system_prompt(
        doc_count=3,
        total_chars=15000,
        doc_sizes_list=doc_sizes_list,
        max_subcall_chars=MAX_SUBCALL_CHARS,
    )
    # Should show each document with its size
    assert "context[0]" in prompt
    assert "a.txt" in prompt
    assert "5,000" in prompt
    assert "context[1]" in prompt
    assert "b.txt" in prompt
    assert "4,000" in prompt


def test_system_prompt_warns_about_oversized_documents():
    """System prompt warns when a document exceeds the sub-LLM limit."""
    loader = PromptLoader()

    oversized = MAX_SUBCALL_CHARS + 10000  # Slightly over limit
    doc_sizes_list = _build_doc_sizes_list(
        [
            ("small.txt", "100,000 chars"),
            ("large.txt", f"{oversized:,} chars EXCEEDS LIMIT - must chunk"),
        ]
    )

    prompt = loader.render_system_prompt(
        doc_count=2,
        total_chars=oversized + 100000,
        doc_sizes_list=doc_sizes_list,
        max_subcall_chars=MAX_SUBCALL_CHARS,
    )
    # Should warn about the oversized document
    assert "EXCEEDS LIMIT" in prompt or "must chunk" in prompt.lower()
    # The small one should not have a warning
    assert "small.txt" in prompt


def test_system_prompt_explains_error_handling():
    """System prompt explains how to handle size limit errors."""
    loader = PromptLoader()

    doc_sizes_list = "    - context[0] (doc.txt): 1,000 chars"

    prompt = loader.render_system_prompt(
        doc_count=1,
        total_chars=1000,
        doc_sizes_list=doc_sizes_list,
        max_subcall_chars=MAX_SUBCALL_CHARS,
    )
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


def test_wrap_repl_output_truncates_large_output():
    """wrap_repl_output truncates output exceeding max_chars."""
    large_output = "x" * 60000  # 60K chars

    wrapped = wrap_repl_output(large_output, max_chars=50000)

    # Should be truncated
    assert "truncated" in wrapped.lower()
    assert "10,000" in wrapped or "10000" in wrapped  # chars omitted


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
