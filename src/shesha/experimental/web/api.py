"""FastAPI application for Shesha web interface."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from shesha.experimental.web.dependencies import AppState
from shesha.experimental.web.schemas import TopicCreate, TopicInfo, TopicRename


def create_api(state: AppState) -> FastAPI:
    """Create and configure the FastAPI app."""
    app = FastAPI(title="Shesha arXiv Explorer", version="0.1.0")

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

    return app
