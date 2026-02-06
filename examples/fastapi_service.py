#!/usr/bin/env python3
"""Example FastAPI service wrapping Shesha."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shesha import Shesha
from shesha.exceptions import ProjectExistsError, ProjectNotFoundError

# Global Shesha instance
shesha: Shesha | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage Shesha lifecycle."""
    global shesha
    shesha = Shesha(
        model="claude-sonnet-4-20250514",
        storage_path="./service_data",
    )
    shesha.start()
    yield
    shesha.stop()


app = FastAPI(
    title="Shesha API",
    description="Query documents using Recursive Language Models",
    lifespan=lifespan,
)


class QueryRequest(BaseModel):
    """Request body for queries."""

    question: str


class QueryResponse(BaseModel):
    """Response from a query."""

    answer: str
    execution_time: float
    total_tokens: int


@app.post("/projects")
def create_project(project_id: str) -> dict[str, str]:
    """Create a new project."""
    if shesha is None:
        raise HTTPException(500, "Shesha not initialized")
    try:
        shesha.create_project(project_id)
        return {"status": "created", "project_id": project_id}
    except ProjectExistsError as e:
        raise HTTPException(400, str(e))


@app.get("/projects")
def list_projects() -> dict[str, list[str]]:
    """List all projects."""
    if shesha is None:
        raise HTTPException(500, "Shesha not initialized")
    return {"projects": shesha.list_projects()}


@app.post("/projects/{project_id}/query")
def query_project(project_id: str, request: QueryRequest) -> QueryResponse:
    """Query a project's documents."""
    if shesha is None:
        raise HTTPException(500, "Shesha not initialized")
    try:
        project = shesha.get_project(project_id)
        result = project.query(request.question)
        return QueryResponse(
            answer=result.answer,
            execution_time=result.execution_time,
            total_tokens=result.token_usage.total_tokens,
        )
    except ProjectNotFoundError as e:
        raise HTTPException(404, str(e))


@app.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, str]:
    """Delete a project."""
    if shesha is None:
        raise HTTPException(500, "Shesha not initialized")
    shesha.delete_project(project_id)
    return {"status": "deleted", "project_id": project_id}


# Run with: uvicorn examples.fastapi_service:app --reload
