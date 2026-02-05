"""Hardened system prompts for RLM execution."""

# Maximum characters per sub-LLM call (used for guidance in prompt)
MAX_SUBCALL_CHARS = 500_000


def wrap_repl_output(output: str, max_chars: int = 50000) -> str:
    """Wrap REPL output in untrusted tags with truncation."""
    if len(output) > max_chars:
        output = output[:max_chars] + f"\n... [truncated, {len(output) - max_chars} chars omitted]"

    return f"""<repl_output type="untrusted_document_content">
{output}
</repl_output>"""
