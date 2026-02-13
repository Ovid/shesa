# Web Interface Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a React + FastAPI web interface for the Shesha arXiv Explorer, replacing the TUI.

**Architecture:** FastAPI backend wraps existing Shesha components (TopicManager, ArxivSearcher, PaperCache, RLM engine). React SPA communicates via REST + WebSocket. All new code lives in `src/shesha/experimental/web/` with the frontend in a `frontend/` subdirectory.

**Tech Stack:** Python (FastAPI, uvicorn, websockets), TypeScript (React 19, Vite, Tailwind CSS)

**Design doc:** `docs/plans/2026-02-12-web-interface-design.md`

**Visual reference:** `mockup.html` — the HTML mockup shows the target layout, color palette, and component placement. All frontend components should match this mockup's structure and styling.

---

## Phase 1: Core Engine Changes

### Task 1: Add cancellation support to RLMEngine

Real cancellation via `threading.Event` — the engine exits cleanly after the current step when the event is set.

**Files:**
- Modify: `src/shesha/rlm/engine.py` (query method signature + loop)
- Modify: `src/shesha/project.py` (pass cancel_event through)
- Test: `tests/unit/rlm/test_engine_cancellation.py`

**Step 1: Write failing tests**

Create `tests/unit/rlm/test_engine_cancellation.py`:

```python
"""Tests for RLM engine cancellation."""

import threading
from unittest.mock import MagicMock, patch

import pytest

from shesha.rlm.engine import RLMEngine


def test_query_accepts_cancel_event():
    """RLMEngine.query() accepts a cancel_event parameter."""
    engine = RLMEngine(model="test-model")
    event = threading.Event()
    # Should not raise TypeError for unexpected keyword
    # (Will fail for other reasons since no sandbox, but that's fine)
    with pytest.raises(Exception):  # No pool/executor available
        engine.query(
            documents=["doc"],
            question="q",
            cancel_event=event,
        )


def test_query_exits_when_cancel_event_set():
    """Query loop exits after current iteration when cancel_event is set."""
    engine = RLMEngine(model="test-model")
    event = threading.Event()

    # Mock the LLM to set the cancel event after first call
    mock_llm = MagicMock()
    call_count = 0

    def fake_complete(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            event.set()  # Cancel after first LLM call
        resp = MagicMock()
        resp.content = "I need to think more about this."
        resp.prompt_tokens = 100
        resp.completion_tokens = 50
        resp.total_tokens = 150
        return resp

    mock_llm.complete = fake_complete

    mock_executor = MagicMock()
    mock_executor.is_alive = True
    mock_executor.execute.return_value = MagicMock(
        status="ok", output="", final_answer=None
    )

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = mock_executor
    engine._pool = mock_pool

    with patch("shesha.rlm.engine.LLMClient", return_value=mock_llm):
        result = engine.query(
            documents=["test doc"],
            question="What is this?",
            cancel_event=event,
        )

    assert result.answer == "[interrupted]"
    # Should have only done 1 iteration, not max_iterations (20)
    assert call_count == 1


def test_query_returns_interrupted_status_in_trace(tmp_path):
    """Cancelled query writes trace with interrupted status."""
    engine = RLMEngine(model="test-model")
    event = threading.Event()
    event.set()  # Set immediately — should exit before first iteration

    mock_executor = MagicMock()
    mock_executor.is_alive = True
    mock_pool = MagicMock()
    mock_pool.acquire.return_value = mock_executor
    engine._pool = mock_pool

    mock_llm = MagicMock()
    with patch("shesha.rlm.engine.LLMClient", return_value=mock_llm):
        result = engine.query(
            documents=["test doc"],
            question="What is this?",
            cancel_event=event,
        )

    assert result.answer == "[interrupted]"
    # LLM should never have been called
    mock_llm.complete.assert_not_called()


def test_project_query_accepts_cancel_event():
    """Project.query() passes cancel_event to engine."""
    from shesha.project import Project
    from shesha.rlm.engine import RLMEngine

    mock_engine = MagicMock(spec=RLMEngine)
    mock_storage = MagicMock()
    mock_storage.load_all_documents.return_value = []

    project = Project(
        project_id="test",
        storage=mock_storage,
        parser_registry=MagicMock(),
        rlm_engine=mock_engine,
    )
    event = threading.Event()

    mock_engine.query.return_value = MagicMock()
    project.query("question", cancel_event=event)

    # Verify cancel_event was passed through
    _, kwargs = mock_engine.query.call_args
    assert kwargs["cancel_event"] is event
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/rlm/test_engine_cancellation.py -v`
Expected: FAIL — `query()` doesn't accept `cancel_event`

**Step 3: Implement cancellation in engine**

In `src/shesha/rlm/engine.py`, modify `query()` signature (around line 415):

```python
def query(
    self,
    documents: list[str],
    question: str,
    doc_names: list[str] | None = None,
    on_progress: ProgressCallback | None = None,
    storage: StorageBackend | None = None,
    project_id: str | None = None,
    cancel_event: threading.Event | None = None,
) -> QueryResult:
```

Add `import threading` at top of file.

Insert cancel check at the top of the iteration loop (line 534):

```python
for iteration in range(self.max_iterations):
    # Check for cancellation before each iteration
    if cancel_event is not None and cancel_event.is_set():
        answer = "[interrupted]"
        query_result = QueryResult(
            answer=answer,
            trace=trace,
            token_usage=token_usage,
            execution_time=time.time() - start_time,
        )
        _finalize_trace(answer, "interrupted")
        return query_result

    executor.llm_query_handler = _make_llm_callback(iteration)
    # ... rest of loop unchanged ...
```

In `src/shesha/project.py`, modify `query()`:

```python
def query(
    self,
    question: str,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> QueryResult:
```

And pass it through:

```python
return self._rlm_engine.query(
    documents=[d.content for d in docs],
    question=question,
    doc_names=[d.name for d in docs],
    on_progress=on_progress,
    storage=self._storage,
    project_id=self.project_id,
    cancel_event=cancel_event,
)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/rlm/test_engine_cancellation.py -v`
Expected: PASS

**Step 5: Run full test suite to check for regressions**

Run: `make all`
Expected: All existing tests still pass (cancel_event defaults to None)

**Step 6: Commit**

```bash
git add src/shesha/rlm/engine.py src/shesha/project.py tests/unit/rlm/test_engine_cancellation.py
git commit -m "feat: add cancel_event support to RLMEngine.query()"
```

---

### Task 2: Update TUI to use cancel_event

Replace the cosmetic query-ID-bump cancellation with real `cancel_event`.

**Files:**
- Modify: `src/shesha/tui/app.py` (add cancel_event field, pass to query, set on cancel)
- Test: `tests/unit/tui/test_app.py` (update existing cancellation tests)

**Step 1: Write failing test**

Add to `tests/unit/tui/test_app.py` (or create `tests/unit/tui/test_cancellation.py` if cleaner):

```python
def test_cancel_sets_cancel_event(app_with_mocks):
    """Double-escape sets the cancel_event on the running query."""
    # This test will depend on the existing test patterns in test_app.py.
    # The key assertion: after cancellation, the cancel_event should be set.
    # Exact test structure depends on existing fixtures — adapt to match.
    pass
```

Note: The exact test depends on existing TUI test fixtures (`app_with_mocks`, pilot patterns). Read `tests/unit/tui/test_app.py` to understand the existing cancellation test patterns (around line 418-506) and adapt.

**Step 2: Implement**

In `src/shesha/tui/app.py`:
- Add `_cancel_event: threading.Event | None = None` instance variable
- In `_make_query_runner()`, create a new `threading.Event()`, store it as `self._cancel_event`, pass it to `self._project.query(..., cancel_event=self._cancel_event)`
- In `on_input_area_query_cancelled()`, call `self._cancel_event.set()` if it exists (in addition to existing query_id bump for backward compat)

**Step 3: Run existing cancellation tests + new test**

Run: `pytest tests/unit/tui/ -v -k cancel`
Expected: All pass

**Step 4: Commit**

```bash
git add src/shesha/tui/app.py tests/unit/tui/
git commit -m "feat: TUI uses cancel_event for real query cancellation"
```

---

## Phase 2: Backend Foundation

### Task 3: Add `[web]` pip extra and project scaffolding

**Files:**
- Modify: `pyproject.toml`
- Create: `src/shesha/experimental/web/__init__.py`
- Create: `src/shesha/experimental/web/schemas.py`
- Create: `src/shesha/experimental/web/dependencies.py`
- Create: `tests/unit/experimental/web/__init__.py`
- Create: `tests/unit/experimental/web/test_schemas.py`

**Step 1: Add web extra to pyproject.toml**

Add after the `tui` extra (line 47):

```toml
web = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "websockets>=12.0",
]
```

Also add to `dev` extra so tests can run:

```toml
dev = [
    # ... existing deps ...
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "websockets>=12.0",
    "httpx>=0.27",  # For FastAPI TestClient
]
```

Add mypy override for `uvicorn`:

```toml
[[tool.mypy.overrides]]
module = "uvicorn"
ignore_missing_imports = true
```

**Step 2: Create directory structure**

```bash
mkdir -p src/shesha/experimental/web
touch src/shesha/experimental/web/__init__.py
mkdir -p tests/unit/experimental/web
touch tests/unit/experimental/web/__init__.py
```

**Step 3: Write schemas with tests**

Create `tests/unit/experimental/web/test_schemas.py`:

```python
"""Tests for web API schemas."""

from shesha.experimental.web.schemas import (
    TopicCreate,
    TopicInfo,
    TopicRename,
    PaperAdd,
    PaperInfo,
    SearchResult,
    TraceListItem,
    TraceFull,
    TraceStepSchema,
    ExchangeSchema,
    ConversationHistory,
    ModelInfo,
    ModelUpdate,
    ContextBudget,
    DownloadTaskStatus,
)


def test_topic_create():
    t = TopicCreate(name="Abiogenesis")
    assert t.name == "Abiogenesis"


def test_topic_info():
    t = TopicInfo(
        name="Abiogenesis",
        paper_count=5,
        size="2.3 MB",
        project_id="2026-02-12-abiogenesis",
    )
    assert t.paper_count == 5


def test_paper_add_multi_topic():
    p = PaperAdd(arxiv_id="2501.08753", topics=["Chess", "Education"])
    assert len(p.topics) == 2


def test_search_result_includes_in_topics():
    r = SearchResult(
        arxiv_id="2501.08753",
        title="Test Paper",
        authors=["Author A"],
        abstract="Abstract text",
        category="q-bio.PE",
        date="2025-01-15",
        arxiv_url="https://arxiv.org/abs/2501.08753",
        in_topics=["Abiogenesis"],
    )
    assert r.in_topics == ["Abiogenesis"]


def test_trace_step_schema():
    s = TraceStepSchema(
        step_type="code_generated",
        iteration=1,
        content="print('hello')",
        timestamp=1234567890.0,
        prompt_tokens=100,
        completion_tokens=50,
    )
    assert s.step_type == "code_generated"


def test_exchange_schema():
    e = ExchangeSchema(
        exchange_id="uuid-1",
        question="What?",
        answer="This.",
        trace_id="2025-01-15T10-30-00-123_abc",
        timestamp="2025-01-15T10:30:00Z",
        tokens={"prompt": 100, "completion": 50, "total": 150},
        execution_time=44.5,
        model="gpt-5-mini",
    )
    assert e.trace_id is not None


def test_context_budget():
    b = ContextBudget(
        used_tokens=31000,
        max_tokens=73000,
        percentage=42.5,
        level="green",
    )
    assert b.level == "green"


def test_download_task_status():
    d = DownloadTaskStatus(
        task_id="abc123",
        papers=[
            {"arxiv_id": "2501.08753", "status": "downloading"},
        ],
    )
    assert d.task_id == "abc123"
```

**Step 4: Implement schemas**

Create `src/shesha/experimental/web/schemas.py`:

```python
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
```

**Step 5: Create dependencies module**

Create `src/shesha/experimental/web/dependencies.py`:

```python
"""Shared state for the web API."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from shesha import Shesha
from shesha.config import SheshaConfig
from shesha.experimental.arxiv.cache import PaperCache
from shesha.experimental.arxiv.search import ArxivSearcher
from shesha.experimental.arxiv.topics import TopicManager
from shesha.storage.filesystem import FilesystemStorage


@dataclass
class AppState:
    """Shared application state."""

    shesha: Shesha
    topic_mgr: TopicManager
    cache: PaperCache
    searcher: ArxivSearcher
    model: str
    download_tasks: dict[str, dict[str, object]] = field(default_factory=dict)


def create_app_state(
    data_dir: Path | None = None,
    model: str | None = None,
) -> AppState:
    """Initialize all components and return shared state."""
    data_dir = data_dir or Path.home() / ".shesha-arxiv"
    shesha_data = data_dir / "shesha_data"
    cache_dir = data_dir / "paper-cache"
    shesha_data.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    config = SheshaConfig.load(storage_path=str(shesha_data))
    if model:
        config.model = model
    storage = FilesystemStorage(shesha_data)
    shesha = Shesha(config=config, storage=storage)
    cache = PaperCache(cache_dir)
    searcher = ArxivSearcher()
    topic_mgr = TopicManager(shesha=shesha, storage=storage)

    return AppState(
        shesha=shesha,
        topic_mgr=topic_mgr,
        cache=cache,
        searcher=searcher,
        model=config.model,
    )
```

**Step 6: Run tests**

Run: `pip install -e ".[dev]" && pytest tests/unit/experimental/web/test_schemas.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add pyproject.toml src/shesha/experimental/web/ tests/unit/experimental/web/
git commit -m "feat: add web extra, schemas, and dependencies module"
```

---

### Task 4: Persistent web ConversationSession

Adapts the TUI's in-memory ConversationSession for web use with JSON file persistence.

**Files:**
- Create: `src/shesha/experimental/web/session.py`
- Create: `tests/unit/experimental/web/test_session.py`

**Step 1: Write failing tests**

Create `tests/unit/experimental/web/test_session.py`:

```python
"""Tests for persistent web conversation session."""

import json
from pathlib import Path

import pytest

from shesha.experimental.web.session import WebConversationSession


@pytest.fixture
def session_dir(tmp_path):
    return tmp_path / "projects" / "test-topic"


@pytest.fixture
def session(session_dir):
    session_dir.mkdir(parents=True)
    return WebConversationSession(session_dir)


def test_empty_session_has_no_exchanges(session):
    assert session.list_exchanges() == []


def test_add_exchange(session):
    session.add_exchange(
        question="What is this?",
        answer="A test.",
        trace_id="trace-123",
        tokens={"prompt": 100, "completion": 50, "total": 150},
        execution_time=1.5,
        model="gpt-5-mini",
    )
    exchanges = session.list_exchanges()
    assert len(exchanges) == 1
    assert exchanges[0]["question"] == "What is this?"
    assert exchanges[0]["trace_id"] == "trace-123"
    assert "exchange_id" in exchanges[0]
    assert "timestamp" in exchanges[0]


def test_persistence_across_instances(session_dir):
    session_dir.mkdir(parents=True, exist_ok=True)
    s1 = WebConversationSession(session_dir)
    s1.add_exchange(
        question="Q1",
        answer="A1",
        trace_id="t1",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
    )

    s2 = WebConversationSession(session_dir)
    exchanges = s2.list_exchanges()
    assert len(exchanges) == 1
    assert exchanges[0]["question"] == "Q1"


def test_clear_history(session):
    session.add_exchange(
        question="Q",
        answer="A",
        trace_id="t",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
    )
    session.clear()
    assert session.list_exchanges() == []


def test_format_history_prefix_empty(session):
    assert session.format_history_prefix() == ""


def test_format_history_prefix_with_exchanges(session):
    session.add_exchange(
        question="What is X?",
        answer="X is Y.",
        trace_id="t1",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
    )
    prefix = session.format_history_prefix()
    assert "Previous conversation:" in prefix
    assert "What is X?" in prefix
    assert "X is Y." in prefix


def test_format_transcript(session):
    session.add_exchange(
        question="What?",
        answer="This.",
        trace_id="t1",
        tokens={"prompt": 100, "completion": 50, "total": 150},
        execution_time=1.5,
        model="gpt-5-mini",
    )
    transcript = session.format_transcript()
    assert "## Q:" in transcript or "**Q:**" in transcript
    assert "What?" in transcript
    assert "This." in transcript


def test_context_chars(session):
    """context_chars returns total character count of history."""
    assert session.context_chars() == 0
    session.add_exchange(
        question="Hello",
        answer="World",
        trace_id="t1",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
    )
    assert session.context_chars() > 0
```

**Step 2: Run tests to verify failure**

Run: `pytest tests/unit/experimental/web/test_session.py -v`
Expected: FAIL — module not found

**Step 3: Implement WebConversationSession**

Create `src/shesha/experimental/web/session.py`:

```python
"""Persistent conversation session for the web interface."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


CONVERSATION_FILE = "_conversation.json"


class WebConversationSession:
    """Manages conversation history with JSON file persistence."""

    def __init__(self, project_dir: Path) -> None:
        self._file = project_dir / CONVERSATION_FILE
        self._exchanges: list[dict[str, object]] = []
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            data = json.loads(self._file.read_text())
            self._exchanges = data.get("exchanges", [])

    def _save(self) -> None:
        self._file.write_text(
            json.dumps({"exchanges": self._exchanges}, indent=2)
        )

    def add_exchange(
        self,
        *,
        question: str,
        answer: str,
        trace_id: str | None,
        tokens: dict[str, int],
        execution_time: float,
        model: str,
    ) -> dict[str, object]:
        exchange = {
            "exchange_id": str(uuid.uuid4()),
            "question": question,
            "answer": answer,
            "trace_id": trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tokens": tokens,
            "execution_time": execution_time,
            "model": model,
        }
        self._exchanges.append(exchange)
        self._save()
        return exchange

    def list_exchanges(self) -> list[dict[str, object]]:
        return list(self._exchanges)

    def clear(self) -> None:
        self._exchanges = []
        self._save()

    def format_history_prefix(self) -> str:
        if not self._exchanges:
            return ""
        lines = ["Previous conversation:"]
        for i, ex in enumerate(self._exchanges, 1):
            lines.append(f"Q{i}: {ex['question']}")
            lines.append(f"A{i}: {ex['answer']}")
            lines.append("")
        lines.append("Current question:\n")
        return "\n".join(lines)

    def format_transcript(self) -> str:
        lines = [f"# Conversation Transcript\n"]
        lines.append(f"Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")
        for ex in self._exchanges:
            lines.append(f"**Q:** {ex['question']}\n")
            lines.append(f"**A:** {ex['answer']}\n")
            if ex.get("tokens"):
                t = ex["tokens"]
                lines.append(
                    f"*Tokens: {t.get('total', 0)} "
                    f"(prompt: {t.get('prompt', 0)}, "
                    f"completion: {t.get('completion', 0)}) | "
                    f"Time: {ex.get('execution_time', 0):.1f}s*\n"
                )
            lines.append("---\n")
        return "\n".join(lines)

    def context_chars(self) -> int:
        total = 0
        for ex in self._exchanges:
            total += len(str(ex.get("question", "")))
            total += len(str(ex.get("answer", "")))
        return total
```

**Step 4: Run tests**

Run: `pytest tests/unit/experimental/web/test_session.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/web/session.py tests/unit/experimental/web/test_session.py
git commit -m "feat: add persistent WebConversationSession for web API"
```

---

## Phase 3: Backend REST API

### Task 5: FastAPI app with Topics endpoints

**Files:**
- Create: `src/shesha/experimental/web/api.py`
- Create: `tests/unit/experimental/web/test_api_topics.py`

**Step 1: Write failing tests**

Create `tests/unit/experimental/web/test_api_topics.py`:

```python
"""Tests for topics REST endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from shesha.experimental.web.api import create_api
from shesha.experimental.web.dependencies import AppState


@pytest.fixture
def mock_state():
    state = MagicMock(spec=AppState)
    state.model = "test-model"
    state.download_tasks = {}
    return state


@pytest.fixture
def client(mock_state):
    app = create_api(mock_state)
    return TestClient(app)


def test_list_topics_empty(client, mock_state):
    mock_state.topic_mgr.list_topics.return_value = []
    resp = client.get("/api/topics")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_topics(client, mock_state):
    from datetime import datetime
    from shesha.experimental.arxiv.models import TopicInfo

    mock_state.topic_mgr.list_topics.return_value = [
        TopicInfo(
            name="Abiogenesis",
            created=datetime(2025, 1, 15),
            paper_count=5,
            size_bytes=1024000,
            project_id="2025-01-15-abiogenesis",
        ),
    ]
    resp = client.get("/api/topics")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Abiogenesis"
    assert data[0]["paper_count"] == 5


def test_create_topic(client, mock_state):
    mock_state.topic_mgr.resolve.return_value = None
    mock_state.topic_mgr.create.return_value = "2025-01-15-chess"
    resp = client.post("/api/topics", json={"name": "Chess"})
    assert resp.status_code == 201
    mock_state.topic_mgr.create.assert_called_once_with("Chess")


def test_create_topic_already_exists(client, mock_state):
    mock_state.topic_mgr.resolve.return_value = "existing-id"
    resp = client.post("/api/topics", json={"name": "Chess"})
    assert resp.status_code == 409


def test_rename_topic(client, mock_state):
    mock_state.topic_mgr.resolve.return_value = "some-id"
    resp = client.patch("/api/topics/chess", json={"new_name": "Chess 2.0"})
    assert resp.status_code == 200
    mock_state.topic_mgr.rename.assert_called_once()


def test_rename_topic_not_found(client, mock_state):
    mock_state.topic_mgr.rename.side_effect = ValueError("not found")
    resp = client.patch("/api/topics/chess", json={"new_name": "Chess 2.0"})
    assert resp.status_code == 404


def test_delete_topic(client, mock_state):
    mock_state.topic_mgr.resolve.return_value = "some-id"
    resp = client.delete("/api/topics/chess")
    assert resp.status_code == 200
    mock_state.topic_mgr.delete.assert_called_once()


def test_delete_topic_not_found(client, mock_state):
    mock_state.topic_mgr.delete.side_effect = ValueError("not found")
    resp = client.delete("/api/topics/nonexistent")
    assert resp.status_code == 404
```

**Step 2: Run tests to verify failure**

Run: `pytest tests/unit/experimental/web/test_api_topics.py -v`
Expected: FAIL — module not found

**Step 3: Implement**

Create `src/shesha/experimental/web/api.py`:

```python
"""FastAPI application for Shesha web interface."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

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
            raise HTTPException(404, str(e))
        return {"name": body.new_name}

    @app.delete("/api/topics/{name}")
    def delete_topic(name: str) -> dict[str, str]:
        try:
            state.topic_mgr.delete(name)
        except ValueError as e:
            raise HTTPException(404, str(e))
        return {"status": "deleted", "name": name}

    return app
```

**Step 4: Run tests**

Run: `pytest tests/unit/experimental/web/test_api_topics.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/web/api.py tests/unit/experimental/web/test_api_topics.py
git commit -m "feat: add topics REST endpoints"
```

---

### Task 6: Papers endpoints

Add endpoints for listing papers in a topic, multi-topic add (with download task tracking), and paper removal.

**Files:**
- Modify: `src/shesha/experimental/web/api.py`
- Create: `tests/unit/experimental/web/test_api_papers.py`

**Step 1: Write failing tests**

Create `tests/unit/experimental/web/test_api_papers.py`. Key tests:
- `test_list_papers_in_topic` — returns PaperMeta for each paper
- `test_list_papers_topic_not_found` — 404 for unknown topic
- `test_add_paper_cached` — paper already in cache, copies immediately, returns 200
- `test_add_paper_needs_download` — returns 202 with task_id
- `test_add_paper_multi_topic` — adds to multiple topics
- `test_remove_paper` — removes paper from topic
- `test_download_task_status` — returns progress of a download task

Follow the same pattern as Task 5's tests (fixture with `mock_state` and `client`).

**Step 2: Implement**

Add to `api.py` inside `create_api()`:
- `GET /api/topics/{name}/papers` — resolve topic, list documents, get meta from cache
- `POST /api/papers/add` — check cache, if cached copy to all topics immediately (200), else create background download task with `threading.Thread` (202). Use 3.1s sleep between downloads. Store task status in `state.download_tasks`.
- `DELETE /api/topics/{name}/papers/{arxiv_id}` — delete document from topic
- `GET /api/papers/tasks/{task_id}` — return task status from `state.download_tasks`

Key implementation note for downloads: use `download_paper()` and `to_parsed_document()` from `shesha.experimental.arxiv.download`, then `state.topic_mgr._storage.store_document()`. Match the pattern in `_cmd_topic_add` from `examples/arxiv_explorer.py` (lines 388-464).

**Step 3: Run tests, commit**

---

### Task 7: Search endpoints

**Files:**
- Modify: `src/shesha/experimental/web/api.py`
- Create: `tests/unit/experimental/web/test_api_search.py`

**Step 1: Write failing tests**

Key tests:
- `test_search_arxiv` — calls `state.searcher.search()`, returns results with `in_topics`
- `test_search_arxiv_with_filters` — passes author, category, sort_by, start
- `test_search_arxiv_marks_existing_papers` — papers already in topics show `in_topics`
- `test_search_local` — searches cache metadata across all topics
- `test_search_local_matches_title`
- `test_search_local_matches_author`
- `test_search_local_matches_arxiv_id`

**Step 2: Implement**

- `GET /api/search` — call `state.searcher.search()`, then for each result check which topics contain it by scanning `state.topic_mgr.list_topics()` and checking each topic's document list
- `GET /api/papers/search` — iterate all topics, get paper metas from cache, filter by substring match on title/authors/arxiv_id

**Step 3: Run tests, commit**

---

### Task 8: Traces endpoints

**Files:**
- Modify: `src/shesha/experimental/web/api.py`
- Create: `tests/unit/experimental/web/test_api_traces.py`

**Step 1: Write failing tests**

Key tests:
- `test_list_traces` — returns trace list items with metadata from JSONL headers/summaries
- `test_get_trace_full` — returns all parsed JSONL lines as structured JSON
- `test_get_trace_not_found` — 404 for unknown trace_id

**Step 2: Implement**

- `GET /api/topics/{name}/traces` — resolve topic to project_id, call `storage.list_traces(project_id)`, read first and last line of each JSONL file to extract header (question, timestamp, model) and summary (status, total_tokens, duration)
- `GET /api/topics/{name}/traces/{trace_id}` — find matching trace file, read all lines, parse each as JSON, return structured response

**Step 3: Run tests, commit**

---

### Task 9: History, Export, Model, and Context Budget endpoints

**Files:**
- Modify: `src/shesha/experimental/web/api.py`
- Create: `tests/unit/experimental/web/test_api_misc.py`

**Step 1: Write failing tests**

Key tests:
- `test_get_history` — returns conversation exchanges for topic
- `test_clear_history` — clears and returns empty
- `test_export_transcript` — returns markdown content
- `test_get_model` — returns current model name
- `test_update_model` — changes model, returns new info
- `test_context_budget` — returns estimated percentage and level

**Step 2: Implement**

- `GET /api/topics/{name}/history` — load `WebConversationSession` for topic, return exchanges
- `DELETE /api/topics/{name}/history` — clear session
- `GET /api/topics/{name}/export` — format transcript, return as `text/markdown` response
- `GET /api/model` — return `state.model` and try `litellm.get_model_info()` for context window
- `PUT /api/model` — update `state.model` and `state.shesha._config.model`
- `GET /api/topics/{name}/context-budget` — estimate tokens from documents + history + system prompt, compare to model's max input tokens. Return percentage and level (green < 50, amber < 80, red >= 80)

For context budget, use `~4 chars/token` heuristic. Calculate:
```python
doc_chars = sum(len(d.content) for d in storage.load_all_documents(project_id))
history_chars = session.context_chars()
system_chars = len(prompt_loader.render_system_prompt())
used = (doc_chars + history_chars + system_chars) // 4
```

**Step 3: Run tests, commit**

---

## Phase 4: Backend WebSocket

### Task 10: WebSocket query execution

**Files:**
- Create: `src/shesha/experimental/web/ws.py`
- Create: `tests/unit/experimental/web/test_ws.py`
- Modify: `src/shesha/experimental/web/api.py` (mount WS endpoint)

**Step 1: Write failing tests**

Create `tests/unit/experimental/web/test_ws.py`:

```python
"""Tests for WebSocket query handler."""

import json
import threading
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from shesha.experimental.web.api import create_api
from shesha.experimental.web.dependencies import AppState
from shesha.rlm.trace import StepType, TokenUsage, Trace, TraceStep


@pytest.fixture
def mock_state():
    state = MagicMock(spec=AppState)
    state.model = "test-model"
    state.download_tasks = {}
    return state


@pytest.fixture
def client(mock_state):
    app = create_api(mock_state)
    return TestClient(app)


def test_ws_query_returns_complete(client, mock_state):
    """WebSocket query returns a complete message with answer."""
    mock_project = MagicMock()
    mock_result = MagicMock()
    mock_result.answer = "The answer is 42."
    mock_result.token_usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
    mock_result.execution_time = 1.5
    mock_result.trace = Trace(steps=[])
    mock_project.query.return_value = mock_result

    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.shesha.get_project.return_value = mock_project
    mock_state.topic_mgr._storage.list_documents.return_value = ["doc1"]

    # Mock session
    with patch("shesha.experimental.web.ws.WebConversationSession") as mock_sess_cls:
        mock_session = MagicMock()
        mock_session.format_history_prefix.return_value = ""
        mock_sess_cls.return_value = mock_session

        with client.websocket_connect("/api/ws") as ws:
            ws.send_json({"type": "query", "topic": "test", "question": "What?"})
            # Collect messages until we get "complete"
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("complete", "error"):
                    break

    complete = [m for m in messages if m["type"] == "complete"]
    assert len(complete) == 1
    assert complete[0]["answer"] == "The answer is 42."


def test_ws_query_no_topic(client, mock_state):
    """Query for non-existent topic returns error."""
    mock_state.topic_mgr.resolve.return_value = None
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "query", "topic": "nope", "question": "What?"})
        msg = ws.receive_json()
    assert msg["type"] == "error"


def test_ws_cancel(client, mock_state):
    """Cancel message results in cancelled response."""
    # This tests the protocol — the actual cancellation is tested in Task 1
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "cancel"})
        msg = ws.receive_json()
    assert msg["type"] == "cancelled" or msg["type"] == "error"
```

**Step 2: Implement WebSocket handler**

Create `src/shesha/experimental/web/ws.py`:

```python
"""WebSocket handlers for query execution and citation checking."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

from fastapi import WebSocket, WebSocketDisconnect

from shesha.experimental.web.dependencies import AppState
from shesha.experimental.web.session import WebConversationSession
from shesha.rlm.trace import StepType, TokenUsage


async def websocket_handler(ws: WebSocket, state: AppState) -> None:
    """Handle WebSocket connections for queries and citation checks."""
    await ws.accept()
    cancel_event: threading.Event | None = None

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "cancel":
                if cancel_event is not None:
                    cancel_event.set()
                await ws.send_json({"type": "cancelled"})

            elif msg_type == "query":
                await _handle_query(ws, state, data)

            elif msg_type == "check_citations":
                await _handle_check(ws, state, data)

            else:
                await ws.send_json(
                    {"type": "error", "message": f"Unknown message type: {msg_type}"}
                )
    except WebSocketDisconnect:
        if cancel_event is not None:
            cancel_event.set()


async def _handle_query(
    ws: WebSocket, state: AppState, data: dict[str, object]
) -> None:
    """Execute a query and stream progress."""
    topic = str(data.get("topic", ""))
    question = str(data.get("question", ""))

    project_id = state.topic_mgr.resolve(topic)
    if not project_id:
        await ws.send_json({"type": "error", "message": f"Topic '{topic}' not found"})
        return

    docs = state.topic_mgr._storage.list_documents(project_id)
    if not docs:
        await ws.send_json({"type": "error", "message": "No papers in topic"})
        return

    project = state.shesha.get_project(project_id)
    cancel_event = threading.Event()

    # Load session for history prefix
    project_dir = state.topic_mgr._storage._project_path(project_id)
    session = WebConversationSession(project_dir)
    history_prefix = session.format_history_prefix()
    full_question = history_prefix + question if history_prefix else question

    # Use asyncio.Queue for thread-safe message passing from the query
    # thread to the async WebSocket send loop. The on_progress callback
    # runs in a worker thread and cannot call ws.send_json() directly.
    message_queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    loop = asyncio.get_event_loop()

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

    # Drain the queue in a background task, sending each message to the client
    async def drain_queue() -> None:
        while True:
            msg = await message_queue.get()
            if msg is None:
                break
            await ws.send_json(msg)

    drain_task = asyncio.create_task(drain_queue())

    # Run query in thread to avoid blocking the event loop
    result = await loop.run_in_executor(
        None,
        lambda: project.query(
            full_question, on_progress=on_progress, cancel_event=cancel_event
        ),
    )

    # Signal the drain task to stop, then wait for it
    await message_queue.put(None)
    await drain_task

    # Save to session
    trace_id = None
    traces = state.topic_mgr._storage.list_traces(project_id)
    if traces:
        trace_id = traces[-1].stem  # Most recent trace

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
    )

    await ws.send_json({
        "type": "complete",
        "answer": result.answer,
        "trace_id": trace_id,
        "tokens": {
            "prompt": result.token_usage.prompt_tokens,
            "completion": result.token_usage.completion_tokens,
            "total": result.token_usage.total_tokens,
        },
        "duration_ms": int(result.execution_time * 1000),
    })


async def _handle_check(
    ws: WebSocket, state: AppState, data: dict[str, object]
) -> None:
    """Run citation check and stream progress."""
    # Implementation follows the pattern from _cmd_check_citations
    # in examples/arxiv_explorer.py (lines 466-562).
    # Stream check_progress messages, then check_complete with full report.
    topic = str(data.get("topic", ""))
    arxiv_id = data.get("arxiv_id")

    project_id = state.topic_mgr.resolve(topic)
    if not project_id:
        await ws.send_json({"type": "error", "message": f"Topic '{topic}' not found"})
        return

    # ... citation verification logic (adapt from arxiv_explorer.py) ...
    # For each citation: send {"type": "check_progress", "current": i, "total": n}
    # At end: send {"type": "check_complete", "report": {...}}
    await ws.send_json({"type": "error", "message": "Not implemented yet"})
```

Note: The `on_progress` callback runs in a worker thread. The implementation above uses `asyncio.Queue` with `loop.call_soon_threadsafe()` and a drain task to safely pass messages from the query thread to the async WebSocket send loop.

Mount the WebSocket in `api.py`:

```python
from shesha.experimental.web.ws import websocket_handler

# Inside create_api():
@app.websocket("/api/ws")
async def ws_endpoint(ws: WebSocket):
    await websocket_handler(ws, state)
```

**Step 3: Run tests, commit**

---

## Phase 5: Frontend Foundation

### Task 11: Frontend scaffolding

**Files:**
- Create: `src/shesha/experimental/web/frontend/package.json`
- Create: `src/shesha/experimental/web/frontend/vite.config.ts`
- Create: `src/shesha/experimental/web/frontend/tsconfig.json`
- Create: `src/shesha/experimental/web/frontend/tailwind.config.ts`
- Create: `src/shesha/experimental/web/frontend/index.html`
- Create: `src/shesha/experimental/web/frontend/src/main.tsx`
- Create: `src/shesha/experimental/web/frontend/src/App.tsx`

**Step 1: Initialize project**

```bash
cd src/shesha/experimental/web
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install -D tailwindcss @tailwindcss/vite
```

**Step 2: Configure Vite proxy**

`vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        ws: true,
      },
    },
  },
})
```

**Step 3: Configure Tailwind with custom theme tokens**

`src/index.css`:

```css
@import "tailwindcss";

@theme {
  /* Dark mode (default) */
  --color-surface-0: #0b1121;
  --color-surface-1: #0f1729;
  --color-surface-2: #151d33;
  --color-border: #1e2a45;
  --color-text-primary: #e2e8f0;
  --color-text-secondary: #94a3b8;
  --color-text-dim: #5a6b8a;
  --color-accent: #2dd4bf;
  --color-accent-dim: rgba(45, 212, 191, 0.08);
  --color-green: #4caf50;
  --color-amber: #ff9800;
  --color-red: #f44336;
}

/* Light mode overrides — toggled via .light class on <html> */
.light {
  --color-surface-0: #ffffff;
  --color-surface-1: #f8f9fb;
  --color-surface-2: #eef0f4;
  --color-border: #dde1e8;
  --color-text-primary: #1a202c;
  --color-text-secondary: #4a5568;
  --color-text-dim: #9aa3b2;
  --color-accent: #0d9488;
  --color-accent-dim: rgba(13, 148, 136, 0.08);
  --color-green: #2e7d32;
  --color-amber: #e65100;
  --color-red: #c62828;
}
```

**Step 4: Create minimal App.tsx**

```tsx
export default function App() {
  return (
    <div className="h-screen flex flex-col bg-surface-0 text-text-primary font-sans">
      <header className="h-13 border-b border-border bg-surface-1 flex items-center px-4">
        <span className="text-base font-bold">Shesha</span>
        <span className="text-xs text-text-dim ml-2 font-mono">arXiv Explorer</span>
      </header>
      <main className="flex-1 flex items-center justify-center text-text-dim">
        App scaffold is working.
      </main>
    </div>
  )
}
```

**Step 5: Verify it builds**

```bash
cd src/shesha/experimental/web/frontend
npm run build
npm run dev  # manual check: open localhost:5173, see scaffold
```

**Step 6: Commit**

```bash
git add src/shesha/experimental/web/frontend/
git commit -m "feat: scaffold React frontend with Vite + TypeScript + Tailwind"
```

---

### Task 12: TypeScript types and API client

**Files:**
- Create: `src/shesha/experimental/web/frontend/src/types/index.ts`
- Create: `src/shesha/experimental/web/frontend/src/api/client.ts`
- Create: `src/shesha/experimental/web/frontend/src/api/ws.ts` — low-level WebSocket connection management (connect, reconnect, send, message dispatch)
- Create: `src/shesha/experimental/web/frontend/src/hooks/useWebSocket.ts` — React hook wrapping `api/ws.ts` for component use (exposes `connected`, `send`, `onMessage`)
- Create: `src/shesha/experimental/web/frontend/src/hooks/useTheme.ts`

**Step 1: Define TypeScript types**

`src/types/index.ts` — mirror the Pydantic schemas:

```typescript
export interface TopicInfo {
  name: string
  paper_count: number
  size: string
  project_id: string
}

export interface PaperInfo {
  arxiv_id: string
  title: string
  authors: string[]
  abstract: string
  category: string
  date: string
  arxiv_url: string
  source_type: string | null
}

export interface SearchResult {
  arxiv_id: string
  title: string
  authors: string[]
  abstract: string
  category: string
  date: string
  arxiv_url: string
  in_topics: string[]
}

export interface TraceStep {
  step_type: string
  iteration: number
  content: string
  timestamp: number
  prompt_tokens?: number
  completion_tokens?: number
  duration_ms?: number
}

export interface TraceFull {
  trace_id: string
  question: string
  model: string
  timestamp: string
  steps: TraceStep[]
  total_tokens: { prompt: number; completion: number; total: number }
  total_iterations: number
  duration_ms: number
  status: string
}

export interface Exchange {
  exchange_id: string
  question: string
  answer: string
  trace_id: string | null
  timestamp: string
  tokens: { prompt: number; completion: number; total: number }
  execution_time: number
  model: string
}

export interface ContextBudget {
  used_tokens: number
  max_tokens: number
  percentage: number
  level: 'green' | 'amber' | 'red'
}

// WebSocket message types
export type WSMessage =
  | { type: 'status'; phase: string; iteration: number; tokens?: { prompt: number; completion: number; total: number } }
  | { type: 'step'; step_type: string; iteration: number; content: string; prompt_tokens?: number; completion_tokens?: number }
  | { type: 'complete'; answer: string; trace_id: string; tokens: { prompt: number; completion: number; total: number }; duration_ms: number }
  | { type: 'error'; message: string }
  | { type: 'cancelled' }
  | { type: 'check_progress'; current: number; total: number; key: string; status?: string }
  | { type: 'check_complete'; report: object }
```

**Step 2: Implement REST API client**

`src/api/client.ts`:

```typescript
import type { TopicInfo, PaperInfo, SearchResult, TraceFull, Exchange, ContextBudget } from '../types'

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || resp.statusText)
  }
  return resp.json()
}

export const api = {
  topics: {
    list: () => request<TopicInfo[]>('/topics'),
    create: (name: string) => request<{ name: string; project_id: string }>('/topics', {
      method: 'POST', body: JSON.stringify({ name }),
    }),
    rename: (name: string, newName: string) => request<{ name: string }>(`/topics/${encodeURIComponent(name)}`, {
      method: 'PATCH', body: JSON.stringify({ new_name: newName }),
    }),
    delete: (name: string) => request<void>(`/topics/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  },
  papers: {
    list: (topic: string) => request<PaperInfo[]>(`/topics/${encodeURIComponent(topic)}/papers`),
    add: (arxivId: string, topics: string[]) => request<{ task_id?: string }>('/papers/add', {
      method: 'POST', body: JSON.stringify({ arxiv_id: arxivId, topics }),
    }),
    remove: (topic: string, arxivId: string) => request<void>(
      `/topics/${encodeURIComponent(topic)}/papers/${arxivId}`, { method: 'DELETE' },
    ),
    taskStatus: (taskId: string) => request<{ task_id: string; papers: { arxiv_id: string; status: string }[] }>(
      `/papers/tasks/${taskId}`,
    ),
    search: (q: string) => request<SearchResult[]>(`/papers/search?q=${encodeURIComponent(q)}`),
  },
  search: (params: { q: string; author?: string; category?: string; sort_by?: string; start?: number }) => {
    const qs = new URLSearchParams()
    qs.set('q', params.q)
    if (params.author) qs.set('author', params.author)
    if (params.category) qs.set('category', params.category)
    if (params.sort_by) qs.set('sort_by', params.sort_by)
    if (params.start) qs.set('start', String(params.start))
    return request<SearchResult[]>(`/search?${qs}`)
  },
  traces: {
    list: (topic: string) => request<{ trace_id: string; question: string; timestamp: string; status: string; total_tokens: number; duration_ms: number }[]>(
      `/topics/${encodeURIComponent(topic)}/traces`,
    ),
    get: (topic: string, traceId: string) => request<TraceFull>(
      `/topics/${encodeURIComponent(topic)}/traces/${traceId}`,
    ),
  },
  history: {
    get: (topic: string) => request<{ exchanges: Exchange[] }>(`/topics/${encodeURIComponent(topic)}/history`),
    clear: (topic: string) => request<void>(`/topics/${encodeURIComponent(topic)}/history`, { method: 'DELETE' }),
  },
  export: (topic: string) => fetch(`${BASE}/topics/${encodeURIComponent(topic)}/export`).then(r => r.text()),
  model: {
    get: () => request<{ model: string; max_input_tokens: number | null }>('/model'),
    update: (model: string) => request<{ model: string }>('/model', {
      method: 'PUT', body: JSON.stringify({ model }),
    }),
  },
  contextBudget: (topic: string) => request<ContextBudget>(
    `/topics/${encodeURIComponent(topic)}/context-budget`,
  ),
}
```

**Step 3: Implement WebSocket hook**

`src/hooks/useWebSocket.ts`:

```typescript
import { useEffect, useRef, useCallback, useState } from 'react'
import type { WSMessage } from '../types'

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null)
  const listenersRef = useRef<((msg: WSMessage) => void)[]>([])

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/api/ws`)

    ws.onopen = () => setConnected(true)
    ws.onclose = () => {
      setConnected(false)
      // Auto-reconnect after 2 seconds
      setTimeout(() => {
        // Re-create connection (component will remount or effect re-runs)
      }, 2000)
    }
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data) as WSMessage
      setLastMessage(msg)
      listenersRef.current.forEach(fn => fn(msg))
    }

    wsRef.current = ws
    return () => ws.close()
  }, [])

  const send = useCallback((data: object) => {
    wsRef.current?.send(JSON.stringify(data))
  }, [])

  const onMessage = useCallback((fn: (msg: WSMessage) => void) => {
    listenersRef.current.push(fn)
    return () => {
      listenersRef.current = listenersRef.current.filter(f => f !== fn)
    }
  }, [])

  return { connected, send, onMessage, lastMessage }
}
```

**Step 4: Implement theme hook**

`src/hooks/useTheme.ts`:

```typescript
import { useState, useEffect } from 'react'

export function useTheme() {
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem('shesha-theme')
    return saved ? saved === 'dark' : true  // Default dark
  })

  useEffect(() => {
    localStorage.setItem('shesha-theme', dark ? 'dark' : 'light')
    document.documentElement.classList.toggle('light', !dark)
  }, [dark])

  return { dark, toggle: () => setDark(d => !d) }
}
```

**Step 5: Verify build**

```bash
cd src/shesha/experimental/web/frontend && npm run build
```

**Step 6: Commit**

```bash
git add src/shesha/experimental/web/frontend/src/
git commit -m "feat: add TypeScript types, API client, and WebSocket/theme hooks"
```

---

## Phase 6: Frontend Components

### Task 13: App layout, Header, StatusBar, and connection/error infrastructure

Build the app shell: header with logo and action buttons, status bar at bottom, the three-panel layout (sidebar, center, optional right panel), the connection loss banner, and the general toast notification system.

**Files:**
- Modify: `src/shesha/experimental/web/frontend/src/App.tsx`
- Create: `src/shesha/experimental/web/frontend/src/components/Header.tsx`
- Create: `src/shesha/experimental/web/frontend/src/components/StatusBar.tsx`
- Create: `src/shesha/experimental/web/frontend/src/components/Toast.tsx`

Match the visual layout from `mockup.html`. Use Tailwind classes matching the design doc's color tokens.

**Header must include (left to right):**
- Logo: `<img src="/static/shesha.png">` with "S" styled fallback on load error
- Title: "Shesha" (bold) + subtitle "arXiv Explorer" (monospace, dim) + "Experimental" pill badge (small, amber border)
- Action buttons (right side): Search (toggles SearchPanel), Check (citation check), Export (download transcript), Help ("?" opens HelpPanel)
- Thin vertical divider
- Theme toggle (sun/moon icon)

**StatusBar must include:**
- Active topic name, model name (clickable for model selector), token counts, context budget with color-coded level, phase indicator with colored dot

**Toast system (general-purpose):**
- Bottom-right stack of dismissible toast notifications
- Color-coded: red for errors, amber for warnings, green for success
- Auto-dismiss after 8 seconds
- Used by all components for transient operational feedback (search timeout, arXiv unreachable, etc.)

**Connection loss banner:**
- Persistent amber banner below header when WebSocket disconnects
- Text: "Connection lost. Reconnecting..."
- Chat input disables until reconnected
- Driven by `connected` state from `useWebSocket` hook

**Commit after each component is rendered correctly in the browser.**

---

### Task 14: TopicSidebar

Collapsible sidebar with topic list, create, rename, delete.

**Files:**
- Create: `src/shesha/experimental/web/frontend/src/components/TopicSidebar.tsx`

Features:
- Fetches topics from `api.topics.list()` on mount
- Click to switch active topic (lifts state to App)
- "+" button → inline text input for new topic name
- "..." context menu → Rename (inline edit) / Delete (confirmation dialog)
- Collapsed mode: single-letter icons

---

### Task 15: PaperBar and PaperDetail

Horizontal paper chip strip and expandable paper detail view.

**Files:**
- Create: `src/shesha/experimental/web/frontend/src/components/PaperBar.tsx`
- Create: `src/shesha/experimental/web/frontend/src/components/PaperDetail.tsx`

Features:
- Fetches papers from `api.papers.list(topicName)` when active topic changes
- Chips show arXiv ID + green dot for loaded papers
- Click chip → expand PaperDetail (title, authors, abstract, metadata)
- Click again → collapse

---

### Task 16: ChatArea and ChatMessage

Main chat interface with message history, input, and thinking indicator.

**Files:**
- Create: `src/shesha/experimental/web/frontend/src/components/ChatArea.tsx`
- Create: `src/shesha/experimental/web/frontend/src/components/ChatMessage.tsx`

Features:
- Loads history from `api.history.get(topic)` on topic switch
- User messages right-aligned, assistant left-aligned
- Markdown rendering in assistant messages (use a lightweight library or simple parser)
- "View trace" link on each assistant message
- Thinking indicator during query (animated dots + phase text)
- Text input with send button, Shift+Enter for newline
- On send: `ws.send({type: "query", topic, question})`
- Listen for WebSocket messages to update status and receive answer
- Empty state when no topic/papers selected
- **Experimental banner:** On first launch, show a dismissible welcome banner above the chat area explaining this is experimental software and linking to Help. Dismiss state persisted in `localStorage`.

---

### Task 17: SearchPanel

Right panel with arXiv and My Papers tabs.

**Files:**
- Create: `src/shesha/experimental/web/frontend/src/components/SearchPanel.tsx`

Features:
- **arXiv tab:** Search input, expandable filters (Author, Category, Sort, Recent), results list with multi-topic picker (checkboxes), "Add N papers" button, "Load more" pagination
- **My Papers tab:** Local search input, instant results from `api.papers.search(q)`
- Both tabs show `in_topics` indicators on results

---

### Task 18: TraceViewer

Slide-over panel with expandable timeline of trace steps.

**Files:**
- Create: `src/shesha/experimental/web/frontend/src/components/TraceViewer.tsx`

Features:
- Fetches trace from `api.traces.get(topic, traceId)` on open
- Header: question, model, timestamp, summary stats
- Timeline of collapsible step cards with colored type icons
- Expand/collapse all, step-type filter toggles
- Syntax highlighting for code content (use a lightweight highlighter)

---

### Task 19: CitationReport

Modal dialog for citation check results.

**Files:**
- Create: `src/shesha/experimental/web/frontend/src/components/CitationReport.tsx`

Features:
- Triggered from header "Check" button → sends `check_citations` via WebSocket
- During check: shows progress ("Checking 3/34...")
- On complete: stats grid, progress bar, LLM phrase indicator, issues list
- Match the mockup's layout exactly

---

### Task 20: DownloadProgress and HelpPanel

Toast stack for downloads and help slide-over.

**Files:**
- Create: `src/shesha/experimental/web/frontend/src/components/DownloadProgress.tsx`
- Create: `src/shesha/experimental/web/frontend/src/components/HelpPanel.tsx`

DownloadProgress: bottom-right toast notifications for paper downloads. Polls `api.papers.taskStatus(taskId)`.

HelpPanel: slide-over with Quick Start Guide, FAQ, and Keyboard Shortcuts. Content from a static JSON file.

---

## Phase 7: Integration and Documentation

### Task 21: Static asset serving and entry point

**Files:**
- Create: `src/shesha/experimental/web/__main__.py`
- Modify: `src/shesha/experimental/web/api.py` (add static file mounts)
- Modify: `pyproject.toml` (add script entry point)

**Step 1: Add static file serving to api.py**

```python
# At the end of create_api(), after all routes:
from pathlib import Path

frontend_dist = Path(__file__).parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True))

# Serve logo
images_dir = Path(__file__).parent.parent.parent.parent / "images"
if images_dir.exists():
    app.mount("/static", StaticFiles(directory=str(images_dir)))
```

**Step 2: Create entry point**

`src/shesha/experimental/web/__main__.py`:

```python
"""Entry point for shesha-web."""

from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path

import uvicorn

from shesha.experimental.web.api import create_api
from shesha.experimental.web.dependencies import create_app_state


def main() -> None:
    parser = argparse.ArgumentParser(description="Shesha arXiv Web Explorer")
    parser.add_argument("--model", type=str, help="LLM model to use")
    parser.add_argument("--data-dir", type=str, help="Data directory")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser")
    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else None
    state = create_app_state(data_dir=data_dir, model=args.model)
    app = create_api(state)

    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{args.port}")).start()

    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
```

**Step 3: Add script to pyproject.toml**

```toml
[project.scripts]
shesha-web = "shesha.experimental.web.__main__:main"
```

**Step 4: Build frontend and test end-to-end**

```bash
cd src/shesha/experimental/web/frontend && npm run build
cd /path/to/project && pip install -e ".[web]"
shesha-web --no-browser --port 8000
# In another terminal: curl http://localhost:8000/api/topics
```

**Step 5: Commit**

```bash
git add src/shesha/experimental/web/__main__.py pyproject.toml
git commit -m "feat: add shesha-web entry point and static asset serving"
```

---

### Task 22: ARXIV.md setup guide

**Files:**
- Create: `ARXIV.md`

Write the researcher-facing document following the structure in the design doc (Section: ARXIV.md Setup Guide). Include:
1. What is Shesha (one paragraph)
2. Prerequisites with OS-specific install links
3. Numbered installation steps (copy-paste commands)
4. First run instructions
5. Guided first research session walkthrough
6. Troubleshooting section
7. Experimental notice

**Commit:**
```bash
git add ARXIV.md
git commit -m "docs: add ARXIV.md researcher setup guide"
```

---

### Task 23: Help content

**Files:**
- Create: `src/shesha/experimental/web/frontend/src/help-content.json`

Write the static JSON with three sections:
- Quick Start Guide (step-by-step with descriptions)
- FAQ (8-10 Q&A pairs covering the topics from the design doc)
- Keyboard Shortcuts (Enter, Shift+Enter, Escape)

**Commit:**
```bash
git add src/shesha/experimental/web/frontend/src/help-content.json
git commit -m "feat: add in-app help content"
```

---

### Task 24: Final integration and CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`

Add under `[Unreleased]`:

```markdown
### Added
- **Experimental web interface** for arXiv Explorer (`shesha-web` command)
  - React frontend with dark/light theme
  - FastAPI backend with REST API and WebSocket
  - Topic management (create, rename, delete, switch)
  - arXiv search with multi-topic paper picker
  - Local paper search across all topics
  - Query execution with live progress streaming
  - Trace viewer with expandable step timeline
  - Citation checking with streamed progress
  - Context budget indicator (warns at 50% and 80%)
  - Conversation history persisted per topic
  - Markdown transcript export
  - In-app help system
- Real query cancellation via `threading.Event` in RLM engine
- `ARXIV.md` setup guide for researchers

### Changed
- TUI cancellation now uses real `cancel_event` instead of cosmetic query-ID bump
```

**Run full test suite:**
```bash
make all
```

**Commit:**
```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for web interface"
```

---

## Task Dependency Graph

```
Task 1 (engine cancel) ─────► Task 2 (TUI cancel)
         │
         ▼
Task 3 (scaffolding) ──► Task 4 (session) ──► Task 5 (topics API)
                                                    │
         ┌──────────────────────────────────────────┘
         ▼
Task 6 (papers API) ──► Task 7 (search API) ──► Task 8 (traces API)
                                                       │
         ┌─────────────────────────────────────────────┘
         ▼
Task 9 (misc API) ──► Task 10 (WebSocket)
                           │
         ┌─────────────────┘
         ▼
Task 11 (frontend scaffold) ──► Task 12 (types + client)
                                       │
         ┌─────────────────────────────┘
         ▼
Tasks 13-20 (components, can partially parallelize)
         │
         ▼
Task 21 (integration) ──► Task 22 (ARXIV.md) ──► Task 23 (help)
                                                       │
                                                       ▼
                                                 Task 24 (CHANGELOG)
```

Tasks 13-20 (frontend components) can be worked on in parallel once
Task 12 is complete, since each component is independent. The suggested
order (13 → 14 → 15 → 16 → 17 → 18 → 19 → 20) builds from outer shell
inward, but any order works.
