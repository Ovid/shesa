"""FastAPI application for Shesha web interface."""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import litellm
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from shesha.experimental.arxiv.download import to_parsed_document
from shesha.experimental.web.dependencies import AppState
from shesha.experimental.web.schemas import (
    ContextBudget,
    ConversationHistory,
    ModelInfo,
    ModelUpdate,
    PaperAdd,
    PaperInfo,
    SearchResult,
    TopicCreate,
    TopicInfo,
    TopicRename,
    TraceFull,
    TraceListItem,
    TraceStepSchema,
)
from shesha.experimental.web.session import WebConversationSession
from shesha.experimental.web.ws import websocket_handler


def _resolve_topic_or_404(state: AppState, name: str) -> str:
    """Resolve a topic name to project_id, or raise 404."""
    project_id = state.topic_mgr.resolve(name)
    if not project_id:
        raise HTTPException(404, f"Topic '{name}' not found")
    return project_id


def create_api(state: AppState) -> FastAPI:
    """Create and configure the FastAPI app."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        state.searcher.close()

    app = FastAPI(title="Shesha arXiv Explorer", version="0.1.0", lifespan=lifespan)

    # --- Topics ---

    @app.get("/api/topics", response_model=list[TopicInfo])
    def list_topics() -> list[TopicInfo]:
        topics = state.topic_mgr.list_topics()
        return [
            TopicInfo(
                name=t.name,
                paper_count=t.paper_count,
                size=t.formatted_size,
                project_id=t.project_id,
            )
            for t in topics
        ]

    @app.post("/api/topics", status_code=201)
    def create_topic(body: TopicCreate) -> dict[str, str]:
        existing = state.topic_mgr.resolve(body.name)
        if existing:
            raise HTTPException(409, f"Topic '{body.name}' already exists")
        project_id = state.topic_mgr.create(body.name)
        return {"name": body.name, "project_id": project_id}

    @app.patch("/api/topics/{name}")
    def rename_topic(name: str, body: TopicRename) -> dict[str, str]:
        try:
            state.topic_mgr.rename(name, body.new_name)
        except ValueError as e:
            raise HTTPException(404, str(e)) from e
        return {"name": body.new_name}

    @app.delete("/api/topics/{name}")
    def delete_topic(name: str) -> dict[str, str]:
        try:
            state.topic_mgr.delete(name)
        except ValueError as e:
            raise HTTPException(404, str(e)) from e
        return {"status": "deleted", "name": name}

    # --- Papers ---

    @app.get("/api/topics/{name}/papers", response_model=list[PaperInfo])
    def list_papers(name: str) -> list[PaperInfo]:
        project_id = _resolve_topic_or_404(state, name)
        doc_names = state.topic_mgr._storage.list_documents(project_id)
        papers: list[PaperInfo] = []
        for doc_name in doc_names:
            meta = state.cache.get_meta(doc_name)
            if meta is not None:
                papers.append(
                    PaperInfo(
                        arxiv_id=meta.arxiv_id,
                        title=meta.title,
                        authors=meta.authors,
                        abstract=meta.abstract,
                        category=meta.primary_category,
                        date=meta.published.strftime("%Y-%m-%d"),
                        arxiv_url=meta.arxiv_url,
                        source_type=meta.source_type,
                    )
                )
        return papers

    @app.post("/api/papers/add", response_model=None)
    def add_paper(body: PaperAdd) -> dict[str, object] | JSONResponse:
        # Resolve all topic names to project IDs first
        topic_projects: list[tuple[str, str]] = []
        for topic_name in body.topics:
            project_id = state.topic_mgr.resolve(topic_name)
            if not project_id:
                raise HTTPException(404, f"Topic '{topic_name}' not found")
            topic_projects.append((topic_name, project_id))

        if state.cache.has(body.arxiv_id):
            # Already cached — copy into all topics immediately
            doc = to_parsed_document(body.arxiv_id, state.cache)
            for _, project_id in topic_projects:
                state.topic_mgr._storage.store_document(project_id, doc)
            return {"status": "added", "arxiv_id": body.arxiv_id}

        # Need to download — create background task
        task_id = str(uuid.uuid4())
        state.download_tasks[task_id] = {
            "papers": [{"arxiv_id": body.arxiv_id, "status": "pending"}],
        }

        def _download() -> None:
            from shesha.experimental.arxiv.download import download_paper

            task = state.download_tasks[task_id]
            papers_list = task["papers"]
            assert isinstance(papers_list, list)
            papers_list[0]["status"] = "downloading"
            try:
                meta = state.cache.get_meta(body.arxiv_id)
                if meta is None:
                    papers_list[0]["status"] = "error"
                    return
                download_paper(meta, state.cache)
                doc = to_parsed_document(body.arxiv_id, state.cache)
                for _, project_id in topic_projects:
                    state.topic_mgr._storage.store_document(project_id, doc)
                papers_list[0]["status"] = "complete"
            except Exception:
                papers_list[0]["status"] = "error"

        thread = threading.Thread(target=_download, daemon=True)
        thread.start()

        return JSONResponse(status_code=202, content={"task_id": task_id})

    @app.delete("/api/topics/{name}/papers/{arxiv_id}")
    def remove_paper(name: str, arxiv_id: str) -> dict[str, str]:
        project_id = _resolve_topic_or_404(state, name)
        state.topic_mgr._storage.delete_document(project_id, arxiv_id)
        return {"status": "removed", "arxiv_id": arxiv_id}

    @app.get("/api/papers/tasks/{task_id}")
    def download_task_status(task_id: str) -> dict[str, object]:
        if task_id not in state.download_tasks:
            raise HTTPException(404, "Task not found")
        task = state.download_tasks[task_id]
        return {"task_id": task_id, "papers": task["papers"]}

    # --- Search ---

    @app.get("/api/search", response_model=list[SearchResult])
    def search_arxiv(
        q: str,
        author: str | None = None,
        category: str | None = None,
        sort_by: str = "relevance",
        start: int = 0,
    ) -> list[SearchResult]:
        results = state.searcher.search(
            q, author=author, category=category, sort_by=sort_by, start=start
        )
        # Build a mapping of arxiv_id -> list of topic names
        topic_docs: dict[str, list[str]] = {}
        for topic in state.topic_mgr.list_topics():
            docs = state.topic_mgr._storage.list_documents(topic.project_id)
            for doc_name in docs:
                topic_docs.setdefault(doc_name, []).append(topic.name)

        return [
            SearchResult(
                arxiv_id=r.arxiv_id,
                title=r.title,
                authors=r.authors,
                abstract=r.abstract,
                category=r.primary_category,
                date=r.published.strftime("%Y-%m-%d"),
                arxiv_url=r.arxiv_url,
                in_topics=topic_docs.get(r.arxiv_id, []),
            )
            for r in results
        ]

    @app.get("/api/papers/search", response_model=list[SearchResult])
    def search_local(q: str) -> list[SearchResult]:
        q_lower = q.lower()
        results: list[SearchResult] = []
        seen: set[str] = set()

        for topic in state.topic_mgr.list_topics():
            docs = state.topic_mgr._storage.list_documents(topic.project_id)
            for doc_name in docs:
                if doc_name in seen:
                    continue
                meta = state.cache.get_meta(doc_name)
                if meta is None:
                    continue
                # Match against title, authors, arxiv_id
                title_match = q_lower in meta.title.lower()
                author_match = any(q_lower in a.lower() for a in meta.authors)
                id_match = q_lower in meta.arxiv_id.lower()
                if title_match or author_match or id_match:
                    seen.add(doc_name)
                    # Find all topics containing this paper
                    in_topics = [topic.name]
                    results.append(
                        SearchResult(
                            arxiv_id=meta.arxiv_id,
                            title=meta.title,
                            authors=meta.authors,
                            abstract=meta.abstract,
                            category=meta.primary_category,
                            date=meta.published.strftime("%Y-%m-%d"),
                            arxiv_url=meta.arxiv_url,
                            in_topics=in_topics,
                        )
                    )

        return results

    # --- Traces ---

    def _parse_trace_file(trace_file: Path) -> dict[str, object]:
        """Parse a JSONL trace file into header, steps, and summary."""
        header: dict[str, object] = {}
        steps: list[dict[str, object]] = []
        summary: dict[str, object] = {}
        for line in trace_file.read_text().strip().splitlines():
            record = json.loads(line)
            rtype = record.get("type")
            if rtype == "header":
                header = record
            elif rtype == "step":
                steps.append(record)
            elif rtype == "summary":
                summary = record
        return {"header": header, "steps": steps, "summary": summary}

    @app.get("/api/topics/{name}/traces", response_model=list[TraceListItem])
    def list_traces(name: str) -> list[TraceListItem]:
        project_id = _resolve_topic_or_404(state, name)
        trace_files = state.topic_mgr._storage.list_traces(project_id)
        items: list[TraceListItem] = []
        for tf in trace_files:
            parsed = _parse_trace_file(tf)
            header = parsed["header"]
            summary = parsed["summary"]
            assert isinstance(header, dict)
            assert isinstance(summary, dict)
            total_tokens_raw = summary.get("total_tokens", {})
            assert isinstance(total_tokens_raw, dict)
            total_tokens = sum(total_tokens_raw.values())
            # Use filename stem as trace_id — matches what ws.py stores
            items.append(
                TraceListItem(
                    trace_id=tf.stem,
                    question=str(header.get("question", "")),
                    timestamp=str(header.get("timestamp", "")),
                    status=str(summary.get("status", "unknown")),
                    total_tokens=total_tokens,
                    duration_ms=int(summary.get("total_duration_ms", 0)),
                )
            )
        return items

    @app.get("/api/topics/{name}/traces/{trace_id:path}", response_model=TraceFull)
    def get_trace(name: str, trace_id: str) -> TraceFull:
        project_id = _resolve_topic_or_404(state, name)
        trace_files = state.topic_mgr._storage.list_traces(project_id)
        for tf in trace_files:
            # Match on filename stem (what ws.py stores) or header UUID
            parsed = _parse_trace_file(tf)
            header = parsed["header"]
            assert isinstance(header, dict)
            if tf.stem == trace_id or header.get("trace_id") == trace_id:
                summary = parsed["summary"]
                steps_raw = parsed["steps"]
                assert isinstance(summary, dict)
                assert isinstance(steps_raw, list)
                total_tokens_raw = summary.get("total_tokens", {})
                assert isinstance(total_tokens_raw, dict)
                steps = [
                    TraceStepSchema(
                        step_type=str(s.get("step_type", "")),
                        iteration=int(s.get("iteration", 0)),
                        content=str(s.get("content", "")),
                        timestamp=str(s.get("timestamp", "")),
                        tokens_used=s.get("tokens_used"),
                        duration_ms=s.get("duration_ms"),
                    )
                    for s in steps_raw
                ]
                doc_ids_raw = header.get("document_ids", [])
                doc_ids = list(doc_ids_raw) if isinstance(doc_ids_raw, list) else []
                return TraceFull(
                    trace_id=trace_id,
                    question=str(header.get("question", "")),
                    model=str(header.get("model", "")),
                    timestamp=str(header.get("timestamp", "")),
                    steps=steps,
                    total_tokens=total_tokens_raw,
                    total_iterations=int(summary.get("total_iterations", 0)),
                    duration_ms=int(summary.get("total_duration_ms", 0)),
                    status=str(summary.get("status", "unknown")),
                    document_ids=doc_ids,
                )
        raise HTTPException(404, f"Trace '{trace_id}' not found")

    # --- History & Export ---

    @app.get("/api/topics/{name}/history", response_model=ConversationHistory)
    def get_history(name: str) -> ConversationHistory:
        project_id = _resolve_topic_or_404(state, name)
        project_dir = state.topic_mgr._storage._project_path(project_id)
        session = WebConversationSession(project_dir)
        return ConversationHistory(exchanges=session.list_exchanges())  # type: ignore[arg-type]

    @app.delete("/api/topics/{name}/history")
    def clear_history(name: str) -> dict[str, str]:
        project_id = _resolve_topic_or_404(state, name)
        project_dir = state.topic_mgr._storage._project_path(project_id)
        session = WebConversationSession(project_dir)
        session.clear()
        return {"status": "cleared"}

    @app.get("/api/topics/{name}/export", response_class=PlainTextResponse)
    def export_transcript(name: str) -> PlainTextResponse:
        project_id = _resolve_topic_or_404(state, name)
        project_dir = state.topic_mgr._storage._project_path(project_id)
        session = WebConversationSession(project_dir)
        content = session.format_transcript()
        return PlainTextResponse(content=content, media_type="text/markdown")

    # --- Model ---

    @app.get("/api/model", response_model=ModelInfo)
    def get_model() -> ModelInfo:
        max_input: int | None = None
        try:
            info = litellm.get_model_info(state.model)
            max_input = info.get("max_input_tokens")
        except Exception:
            pass  # Model may not be in litellm's registry
        return ModelInfo(model=state.model, max_input_tokens=max_input)

    @app.put("/api/model", response_model=ModelInfo)
    def update_model(body: ModelUpdate) -> ModelInfo:
        state.model = body.model
        max_input: int | None = None
        try:
            info = litellm.get_model_info(body.model)
            max_input = info.get("max_input_tokens")
        except Exception:
            pass  # Model may not be in litellm's registry
        return ModelInfo(model=body.model, max_input_tokens=max_input)

    # --- Context Budget ---

    @app.get("/api/topics/{name}/context-budget", response_model=ContextBudget)
    def get_context_budget(name: str) -> ContextBudget:
        project_id = _resolve_topic_or_404(state, name)
        project_dir = state.topic_mgr._storage._project_path(project_id)

        # Documents go to the Docker sandbox, not the LLM context.
        # The LLM context contains: system prompt (~2k tokens) +
        # conversation history prefix + iterative code/output messages.
        # We estimate: base overhead + history chars.
        base_prompt_tokens = 2000  # system prompt + context metadata

        session = WebConversationSession(project_dir)
        history_chars = session.context_chars()

        # ~4 chars per token heuristic
        used_tokens = base_prompt_tokens + (history_chars // 4)

        # Get max tokens from litellm
        max_tokens = 128000  # reasonable default
        try:
            info = litellm.get_model_info(state.model)
            max_input = info.get("max_input_tokens")
            if max_input is not None:
                max_tokens = max_input
        except Exception:
            pass  # Fall back to default

        percentage = (used_tokens / max_tokens) * 100
        if percentage < 50:
            level = "green"
        elif percentage < 80:
            level = "amber"
        else:
            level = "red"

        return ContextBudget(
            used_tokens=used_tokens,
            max_tokens=max_tokens,
            percentage=round(percentage, 1),
            level=level,
        )

    # Suppress Chrome DevTools probing
    @app.get("/.well-known/{path:path}", include_in_schema=False)
    def well_known(path: str) -> Response:
        return Response(status_code=204)

    # --- WebSocket ---

    @app.websocket("/api/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await websocket_handler(ws, state)

    # --- Static files ---
    # Serve logo from images directory
    images_dir = Path(__file__).parent.parent.parent.parent.parent / "images"
    if images_dir.exists():
        app.mount("/static", StaticFiles(directory=str(images_dir)))

    # Serve built frontend (must be last — catches all unmatched routes)
    frontend_dist = Path(__file__).parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True))

    return app
