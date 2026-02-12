"""Pydantic schemas for the web API."""

from __future__ import annotations

from pydantic import BaseModel


class TopicCreate(BaseModel):
    name: str


class TopicRename(BaseModel):
    new_name: str


class TopicInfo(BaseModel):
    name: str
    paper_count: int
    size: str
    project_id: str


class PaperAdd(BaseModel):
    arxiv_id: str
    topics: list[str]


class PaperInfo(BaseModel):
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    category: str
    date: str
    arxiv_url: str
    source_type: str | None = None


class SearchResult(BaseModel):
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    category: str
    date: str
    arxiv_url: str
    in_topics: list[str] = []


class TraceStepSchema(BaseModel):
    step_type: str
    iteration: int
    content: str
    timestamp: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    duration_ms: int | None = None


class TraceListItem(BaseModel):
    trace_id: str
    question: str
    timestamp: str
    status: str
    total_tokens: int
    duration_ms: int


class TraceFull(BaseModel):
    trace_id: str
    question: str
    model: str
    timestamp: str
    steps: list[TraceStepSchema]
    total_tokens: dict[str, int]
    total_iterations: int
    duration_ms: int
    status: str


class ExchangeSchema(BaseModel):
    exchange_id: str
    question: str
    answer: str
    trace_id: str | None = None
    timestamp: str
    tokens: dict[str, int]
    execution_time: float
    model: str


class ConversationHistory(BaseModel):
    exchanges: list[ExchangeSchema]


class ModelInfo(BaseModel):
    model: str
    max_input_tokens: int | None = None


class ModelUpdate(BaseModel):
    model: str


class ContextBudget(BaseModel):
    used_tokens: int
    max_tokens: int
    percentage: float
    level: str  # "green", "amber", "red"


class DownloadTaskStatus(BaseModel):
    task_id: str
    papers: list[dict[str, str]]
