"""FastAPI application for Shesha web interface."""

from __future__ import annotations

import threading
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from shesha.experimental.arxiv.download import to_parsed_document
from shesha.experimental.web.dependencies import AppState
from shesha.experimental.web.schemas import (
    PaperAdd,
    PaperInfo,
    TopicCreate,
    TopicInfo,
    TopicRename,
)


def _resolve_topic_or_404(state: AppState, name: str) -> str:
    """Resolve a topic name to project_id, or raise 404."""
    project_id = state.topic_mgr.resolve(name)
    if not project_id:
        raise HTTPException(404, f"Topic '{name}' not found")
    return project_id


def create_api(state: AppState) -> FastAPI:
    """Create and configure the FastAPI app."""
    app = FastAPI(title="Shesha arXiv Explorer", version="0.1.0")

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

    return app
