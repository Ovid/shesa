"""WebSocket handlers for query execution and citation checking."""

from __future__ import annotations

import asyncio
import functools
import logging
import threading
from collections.abc import Callable

from fastapi import WebSocket, WebSocketDisconnect

from shesha.exceptions import DocumentNotFoundError
from shesha.experimental.arxiv.cache import PaperCache
from shesha.experimental.arxiv.citations import (
    ArxivVerifier,
    detect_llm_phrases,
    extract_citations_from_bbl,
    extract_citations_from_bib,
    extract_citations_from_text,
    format_check_report_json,
)
from shesha.experimental.arxiv.models import (
    CheckReport,
    ExtractedCitation,
    VerificationResult,
    VerificationStatus,
)
from shesha.experimental.arxiv.relevance import check_topical_relevance
from shesha.experimental.arxiv.verifiers import (
    CascadingVerifier,
    CrossRefVerifier,
    OpenAlexVerifier,
    SemanticScholarVerifier,
)
from shesha.experimental.web.dependencies import AppState
from shesha.experimental.web.session import WebConversationSession
from shesha.models import ParsedDocument
from shesha.rlm.trace import StepType, TokenUsage

logger = logging.getLogger(__name__)


def build_citation_instructions(paper_ids: list[str], cache: PaperCache) -> str:
    """Build citation instruction text to append to user questions.

    Tells the LLM to cite papers using [@arxiv:ID] format and lists
    available papers with their titles.
    """
    if not paper_ids:
        return ""

    lines = [
        "\n\nCITATION INSTRUCTIONS: When citing a source paper in your answer, "
        "use the format [@arxiv:ID] inline (e.g. [@arxiv:2005.09008v1]). "
        "Available papers:",
    ]
    for pid in paper_ids:
        meta = cache.get_meta(pid)
        title = meta.title if meta else pid
        lines.append(f'- [@arxiv:{pid}] "{title}"')
    lines.append("Always use [@arxiv:ID] when referencing a specific paper's claims or quotes.")

    return "\n".join(lines)


async def websocket_handler(ws: WebSocket, state: AppState) -> None:
    """Handle WebSocket connections for queries and citation checks."""
    await ws.accept()
    cancel_event: threading.Event | None = None
    query_task: asyncio.Task[None] | None = None

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "cancel":
                if cancel_event is not None:
                    cancel_event.set()
                await ws.send_json({"type": "cancelled"})

            elif msg_type == "query":
                # Cancel any in-flight query before starting a new one
                if cancel_event is not None:
                    cancel_event.set()
                cancel_event = threading.Event()
                query_task = asyncio.create_task(_handle_query(ws, state, data, cancel_event))

            elif msg_type == "check_citations":
                await _handle_check_citations(ws, state, data)

            else:
                await ws.send_json(
                    {"type": "error", "message": f"Unknown message type: {msg_type}"}
                )
    except WebSocketDisconnect:
        if cancel_event is not None:
            cancel_event.set()
        if query_task is not None and not query_task.done():
            query_task.cancel()


async def _handle_query(
    ws: WebSocket,
    state: AppState,
    data: dict[str, object],
    cancel_event: threading.Event,
) -> None:
    """Execute a query and stream progress."""
    topic = str(data.get("topic", ""))
    question = str(data.get("question", ""))

    project_id = state.topic_mgr.resolve(topic)
    if not project_id:
        await ws.send_json({"type": "error", "message": f"Topic '{topic}' not found"})
        return

    doc_names = state.topic_mgr._storage.list_documents(project_id)
    if not doc_names:
        await ws.send_json({"type": "error", "message": "No papers in topic"})
        return

    project = state.shesha.get_project(project_id)

    # Load documents filtered by paper_ids (required)
    paper_ids = data.get("paper_ids")
    loaded_docs: list[ParsedDocument]

    if not paper_ids or not isinstance(paper_ids, list) or len(paper_ids) == 0:
        await ws.send_json(
            {"type": "error", "message": "Please select one or more papers before querying"}
        )
        return

    # Load only the requested papers, skipping any that don't exist
    loaded_docs = []
    for pid in paper_ids:
        try:
            doc = state.topic_mgr._storage.get_document(project_id, str(pid))
            loaded_docs.append(doc)
        except DocumentNotFoundError:
            logger.warning("Requested paper_id %r not found in project %s", pid, project_id)
    if not loaded_docs:
        await ws.send_json(
            {"type": "error", "message": "No valid papers found for the given paper_ids"}
        )
        return

    # Load session for history prefix
    project_dir = state.topic_mgr._storage._project_path(project_id)
    session = WebConversationSession(project_dir)
    history_prefix = session.format_history_prefix()
    citation_suffix = build_citation_instructions([d.name for d in loaded_docs], state.cache)
    full_question = (history_prefix + question if history_prefix else question) + citation_suffix

    # Use asyncio.Queue for thread-safe message passing from the query
    # thread to the async WebSocket send loop.
    message_queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_progress(
        step_type: StepType, iteration: int, content: str, token_usage: TokenUsage
    ) -> None:
        step_msg: dict[str, object] = {
            "type": "step",
            "step_type": step_type.value,
            "iteration": iteration,
            "content": content,
        }
        if token_usage.prompt_tokens > 0:
            step_msg["prompt_tokens"] = token_usage.prompt_tokens
            step_msg["completion_tokens"] = token_usage.completion_tokens
        loop.call_soon_threadsafe(message_queue.put_nowait, step_msg)

    await ws.send_json({"type": "status", "phase": "Starting", "iteration": 0})

    # Drain the queue in a background task
    async def drain_queue() -> None:
        while True:
            msg = await message_queue.get()
            if msg is None:
                break
            await ws.send_json(msg)

    drain_task = asyncio.create_task(drain_queue())

    # Run query in thread to avoid blocking the event loop.
    # Call the RLM engine directly so we can pass the (possibly filtered)
    # document list instead of letting project.query() reload all docs.
    rlm_engine = project._rlm_engine
    if rlm_engine is None:
        await ws.send_json({"type": "error", "message": "Query engine not configured"})
        await message_queue.put(None)
        await drain_task
        return

    storage = state.topic_mgr._storage
    try:
        result = await loop.run_in_executor(
            None,
            lambda: rlm_engine.query(
                documents=[d.content for d in loaded_docs],
                question=full_question,
                doc_names=[d.name for d in loaded_docs],
                on_progress=on_progress,
                storage=storage,
                project_id=project_id,
                cancel_event=cancel_event,
            ),
        )
    except Exception as exc:
        await message_queue.put(None)
        await drain_task
        await ws.send_json({"type": "error", "message": str(exc)})
        return

    # Signal the drain task to stop, then wait for it
    await message_queue.put(None)
    await drain_task

    # Save to session
    trace_id = None
    traces = state.topic_mgr._storage.list_traces(project_id)
    if traces:
        trace_id = traces[-1].stem

    consulted_paper_ids = [d.name for d in loaded_docs]

    session.add_exchange(
        question=question,
        answer=result.answer,
        trace_id=trace_id,
        tokens={
            "prompt": result.token_usage.prompt_tokens,
            "completion": result.token_usage.completion_tokens,
            "total": result.token_usage.total_tokens,
        },
        execution_time=result.execution_time,
        model=state.model,
        paper_ids=consulted_paper_ids,
    )

    await ws.send_json(
        {
            "type": "complete",
            "answer": result.answer,
            "trace_id": trace_id,
            "tokens": {
                "prompt": result.token_usage.prompt_tokens,
                "completion": result.token_usage.completion_tokens,
                "total": result.token_usage.total_tokens,
            },
            "duration_ms": int(result.execution_time * 1000),
            "paper_ids": consulted_paper_ids,
        }
    )


async def _handle_check_citations(ws: WebSocket, state: AppState, data: dict[str, object]) -> None:
    """Check citations for selected papers and stream progress."""
    topic = str(data.get("topic", ""))
    project_id = state.topic_mgr.resolve(topic)
    if not project_id:
        await ws.send_json({"type": "error", "message": f"Topic '{topic}' not found"})
        return

    paper_ids = data.get("paper_ids")
    if not paper_ids or not isinstance(paper_ids, list) or len(paper_ids) == 0:
        await ws.send_json(
            {"type": "error", "message": "Please select one or more papers to check"}
        )
        return

    polite_email = data.get("polite_email")
    email_str = str(polite_email) if polite_email else None

    loop = asyncio.get_running_loop()
    api_key = state.shesha._config.api_key
    verifier = CascadingVerifier(
        arxiv_verifier=ArxivVerifier(searcher=state.searcher),
        crossref_verifier=CrossRefVerifier(polite_email=email_str),
        openalex_verifier=OpenAlexVerifier(polite_email=email_str),
        semantic_scholar_verifier=SemanticScholarVerifier(),
        polite_email=email_str,
        model=state.model,
        api_key=api_key,
    )
    total = len(paper_ids)
    all_papers: list[dict[str, object]] = []

    for idx, pid in enumerate(paper_ids, 1):
        await ws.send_json(
            {
                "type": "citation_progress",
                "current": idx,
                "total": total,
                "phase": "Verifying citations...",
            }
        )

        def _send_citation_progress(
            current_citation: int, total_citations: int, _idx: int = idx
        ) -> None:
            """Send per-citation progress from worker thread."""
            asyncio.run_coroutine_threadsafe(
                ws.send_json(
                    {
                        "type": "citation_progress",
                        "current": _idx,
                        "total": total,
                        "phase": f"Checking citation {current_citation}/{total_citations}...",
                    }
                ),
                loop,
            )

        paper_json = await loop.run_in_executor(
            None,
            functools.partial(
                _check_single_paper,
                str(pid),
                state,
                verifier,
                project_id,
                state.model,
                progress_callback=_send_citation_progress,
            ),
        )
        if paper_json is not None:
            all_papers.append(paper_json)

    await ws.send_json({"type": "citation_report", "papers": all_papers})


def _check_single_paper(
    paper_id: str,
    state: AppState,
    verifier: CascadingVerifier,
    project_id: str,
    model: str,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, object] | None:
    """Check citations for a single paper. Returns JSON-serializable dict or None."""
    meta = state.cache.get_meta(paper_id)
    if meta is None:
        return None

    citations: list[ExtractedCitation] = []
    source_files = state.cache.get_source_files(paper_id)
    full_text = ""

    if source_files is not None:
        for filename, content in source_files.items():
            full_text += content + "\n"
            if filename.endswith(".bib"):
                citations.extend(extract_citations_from_bib(content))
            elif filename.endswith(".bbl"):
                citations.extend(extract_citations_from_bbl(content))
    else:
        try:
            doc = state.topic_mgr._storage.get_document(project_id, paper_id)
            full_text = doc.content
            citations.extend(extract_citations_from_text(full_text))
        except Exception:
            full_text = ""

    llm_phrases = detect_llm_phrases(full_text)
    total_citations = len(citations)
    results: list[VerificationResult] = []
    for i, c in enumerate(citations, 1):
        if progress_callback and total_citations > 1:
            progress_callback(i, total_citations)
        results.append(verifier.verify(c))

    # Topical relevance check on verified citations
    verified_keys = {
        r.citation_key
        for r in results
        if r.status in (VerificationStatus.VERIFIED, VerificationStatus.VERIFIED_EXTERNAL)
    }
    relevance_results = check_topical_relevance(
        paper_title=meta.title,
        paper_abstract=getattr(meta, "abstract", "") or "",
        citations=citations,
        verified_keys=verified_keys,
        model=model,
        api_key=state.shesha._config.api_key,
    )
    results.extend(relevance_results)

    report = CheckReport(
        arxiv_id=meta.arxiv_id,
        title=meta.title,
        citations=citations,
        verification_results=results,
        llm_phrases=llm_phrases,
    )
    return format_check_report_json(report)
