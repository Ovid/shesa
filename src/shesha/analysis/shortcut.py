"""Analysis shortcut — skip RLM when the pre-computed analysis can answer."""

from shesha.llm.client import LLMClient

_SYSTEM_PROMPT = """\
You are a helpful assistant. You have access to a pre-computed codebase analysis.
If the user's question can be fully and accurately answered using ONLY the
analysis below, provide a clear, complete answer.

If the question requires deeper investigation (e.g., reading specific source
files, tracing execution paths, finding bugs, or anything not covered by the
analysis), respond with exactly: NEED_DEEPER

Do not guess or speculate beyond what the analysis states."""

_SENTINEL = "NEED_DEEPER"


def try_answer_from_analysis(
    question: str,
    analysis_context: str | None,
    model: str,
    api_key: str | None,
) -> tuple[str, int, int] | None:
    """Try to answer a question using only the pre-computed analysis.

    Returns ``(answer, prompt_tokens, completion_tokens)`` if the LLM can
    answer from analysis alone, or ``None`` if deeper investigation is needed
    (falls through to full RLM).
    """
    if not analysis_context:
        return None

    client = LLMClient(model=model, system_prompt=_SYSTEM_PROMPT, api_key=api_key)

    user_content = (
        f"<untrusted_document_content>\n{analysis_context}\n</untrusted_document_content>"
        f"\n\nQuestion: {question}"
    )

    try:
        response = client.complete([{"role": "user", "content": user_content}])
    except Exception:
        return None  # Graceful fallback to full RLM query

    answer = response.content.strip()
    if answer == _SENTINEL:
        return None

    return (answer, response.prompt_tokens, response.completion_tokens)
