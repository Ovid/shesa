# Web Interface Design — Shesha arXiv Explorer

**Date:** 2026-02-12
**Status:** Draft
**Replaces:** TUI-based `examples/arxiv_explorer.py`

> **This is experimental software.** Expect rough edges. Do not rely on it
> as your sole research tool.

## Overview

A React + FastAPI web interface for searching, downloading, organizing, and
querying arXiv papers using Shesha's Recursive Language Model engine. Replaces
the Textual TUI, which proved too limiting for the interaction patterns
researchers need (multi-topic paper management, trace inspection, long-running
query progress).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser (React SPA)                     │
│  Vite + TypeScript + Tailwind CSS                           │
│  Components: TopicSidebar, ChatArea, SearchPanel,           │
│              TraceViewer, CitationReport, Help, StatusBar    │
└──────────┬──────────────────────────────┬───────────────────┘
           │ REST (HTTP)                  │ WebSocket
           ▼                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                           │
│  REST endpoints: topics, papers, search, traces, citations  │
│  WebSocket: query execution + progress streaming            │
│  Reuses: TopicManager, ArxivSearcher, PaperCache,           │
│          RLM Engine, ConversationSession                    │
└──────────┬──────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│              Existing Shesha Backend                         │
│  Storage (filesystem) │ Docker Sandbox Pool │ LiteLLM       │
└─────────────────────────────────────────────────────────────┘
```

### Deployment Model

- **Single-user local tool** for v1 (run on your machine, open localhost).
- Architecture keeps clean API boundaries so multi-user (auth, session
  isolation) can be added later without rewriting.
- No authentication in v1.

### Project Layout

```
src/shesha/experimental/web/
├── __init__.py
├── api.py              # FastAPI app, REST routes
├── ws.py               # WebSocket query/citation handler
├── schemas.py          # Pydantic request/response models
├── dependencies.py     # Shared state (Shesha, TopicManager, etc.)
├── session.py          # Web-adapted ConversationSession (persistent)
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── tailwind.config.ts
    ├── index.html
    └── src/
        ├── App.tsx
        ├── main.tsx
        ├── api/            # REST + WebSocket client functions
        │   ├── client.ts
        │   └── ws.ts
        ├── components/
        │   ├── TopicSidebar.tsx
        │   ├── ChatArea.tsx
        │   ├── ChatMessage.tsx
        │   ├── SearchPanel.tsx
        │   ├── TraceViewer.tsx
        │   ├── CitationReport.tsx
        │   ├── PaperDetail.tsx
        │   ├── StatusBar.tsx
        │   ├── HelpPanel.tsx
        │   └── DownloadProgress.tsx
        ├── hooks/
        │   ├── useWebSocket.ts
        │   └── useTheme.ts
        └── types/
            └── index.ts     # TypeScript interfaces matching schemas.py
```

### Dependencies

New pip extra `[web]` in pyproject.toml:

```toml
web = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "websockets>=12.0",
]
```

Frontend: Vite, React 19, TypeScript, Tailwind CSS. No component library.

---

## REST API

All routes prefixed with `/api/`.

### Topics

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/topics` | List all topics (name, paper_count, size, project_id) |
| `POST` | `/api/topics` | Create topic `{name: string}` |
| `PATCH` | `/api/topics/{name}` | Rename `{new_name: string}` |
| `DELETE` | `/api/topics/{name}` | Delete topic (requires confirmation from UI) |

### Papers

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/topics/{name}/papers` | List papers in topic (PaperMeta for each) |
| `POST` | `/api/papers/add` | Multi-topic add `{arxiv_id, topics: string[]}` |
| `DELETE` | `/api/topics/{name}/papers/{arxiv_id}` | Remove paper from topic |
| `GET` | `/api/papers/tasks/{task_id}` | Poll download progress |

`POST /api/papers/add` returns 202 Accepted with a `task_id` when the paper
needs to be downloaded from arXiv. If already cached, it copies into the
requested topics immediately and returns 200.

### Search

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/search?q=...&author=...&category=...&sort_by=...&start=0` | Search arXiv |
| `GET` | `/api/papers/search?q=...` | Local search across all topics |

**arXiv search** results include an `in_topics: string[]` field per result
showing which topics already contain the paper. Results are never filtered
out — they show with indicators instead.

**Local search** matches against title, authors, and arXiv ID (substring
match). Returns results with their `in_topics` list.

Pagination: the `start` parameter offsets into results. Frontend manages
the offset and increments it on "Load more."

### Citations

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/topics/{name}/check` | Run citation check (optional `{arxiv_id}` filter) |

Citation checking streams progress via WebSocket (see below).

### Traces

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/topics/{name}/traces` | List traces (timestamp, question, status, stats) |
| `GET` | `/api/topics/{name}/traces/{trace_id}` | Full trace (all JSONL lines as structured JSON) |

### Conversation History

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/topics/{name}/history` | Get conversation exchanges for topic |
| `DELETE` | `/api/topics/{name}/history` | Clear conversation history |

### Export

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/topics/{name}/export` | Download markdown transcript |

### Model

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/model` | Get current model name + context window info |
| `PUT` | `/api/model` | Change model `{model: string}` |

### Context Budget

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/topics/{name}/context-budget` | Estimated context usage % |

Uses LiteLLM's `get_model_info()` for the model's max input tokens.
Estimates current usage from documents + conversation history + system prompt.

---

## WebSocket Protocol

Endpoint: `/api/ws`

Single WebSocket connection handles queries and citation checks. JSON
messages in both directions.

### Query Execution

**Client sends:**
```json
{"type": "query", "topic": "abiogenesis", "question": "What are the main hypotheses?"}
```

**Server sends a sequence:**
```json
{"type": "status", "phase": "Starting", "iteration": 0}
{"type": "step", "step_type": "code_generated", "iteration": 1,
 "content": "...", "prompt_tokens": 3200, "completion_tokens": 340}
{"type": "step", "step_type": "code_output", "iteration": 1,
 "content": "...", "duration_ms": 120}
{"type": "status", "phase": "Thinking", "iteration": 2,
 "tokens": {"prompt": 6400, "completion": 680, "total": 7080}}
{"type": "step", "step_type": "subcall_request", "iteration": 2, "content": "..."}
{"type": "step", "step_type": "subcall_response", "iteration": 2,
 "content": "...", "prompt_tokens": 800, "completion_tokens": 1200}
{"type": "step", "step_type": "final_answer", "iteration": 4, "content": "..."}
{"type": "complete", "answer": "...", "trace_id": "2025-01-15T...",
 "tokens": {"prompt": 18200, "completion": 6637, "total": 24837},
 "duration_ms": 44403}
```

Steps without LLM calls (e.g., `code_output`) omit token fields.

### Query Cancellation

**Client sends:**
```json
{"type": "cancel"}
```

**Server responds:**
```json
{"type": "cancelled"}
```

Cancellation is **flag-based between iterations**: a `threading.Event` is
set, and the RLM engine loop exits after the current step completes. This
is a real cancellation — it stops token spend and frees the container. The
user can immediately submit a new query; it will wait for the cancelled
query's current step to finish before starting.

This requires modifying `RLMEngine.query()` to accept and check a
cancellation event. The same mechanism should replace the TUI's cosmetic
cancellation (which currently lets queries run to completion in the
background).

### Citation Check Progress

**Client sends:**
```json
{"type": "check_citations", "topic": "abiogenesis", "arxiv_id": "2501.08753"}
```

**Server sends:**
```json
{"type": "check_progress", "current": 3, "total": 34, "key": "kauffman1993"}
{"type": "check_progress", "current": 4, "total": 34, "key": "orgel2004", "status": "mismatch"}
...
{"type": "check_complete", "report": { ... full CheckReport as JSON ... }}
```

### Error and Connection

```json
{"type": "error", "message": "Sandbox timeout"}
{"type": "error", "message": "Query already in progress"}
```

Only one query runs at a time. If the WebSocket connection drops, a
persistent amber banner shows "Connection lost. Reconnecting..." with
automatic retry. The chat input disables until reconnected.

---

## Frontend Components

### TopicSidebar (left, collapsible)

- Lists topics with paper counts.
- Click to switch active topic.
- "+" button opens inline text input to create a new topic (Enter to save,
  Escape to cancel).
- "..." context menu per topic: Rename, Delete.
- Rename: inline editable text field.
- Delete: confirmation dialog ("Delete 'Chess' and its 5 papers?").
- When collapsed, shows single-letter icons.
- Active topic highlighted with accent color.

### ChatArea (center)

- Scrollable message history.
- User messages: right-aligned, accent-colored bubbles.
- Assistant messages: left-aligned, surface-colored with border. Markdown
  rendered with syntax highlighting for code blocks.
- Each assistant message has a "View trace" link (uses stored `trace_id`).
- While query is running: thinking indicator with phase and iteration count.
- Empty state (no topic or no papers): centered prompt to get started.
- Text input at bottom with send button. Shift+Enter for newline.
- Input disables during query execution but unlocks immediately on cancel.
- History persists per topic in `_conversation.json` (see Storage below).

### SearchPanel (right, togglable)

Opens from the header "Search" button. Two tabs:

**arXiv tab:**
- Query input with expandable filter controls (Author, Category, Sort,
  Recent days).
- Results show title, authors, arXiv ID, category, date.
- Each result has a **multi-topic picker**: checkboxes for each topic.
  Topics that already contain the paper show as checked and disabled.
- Floating "Add N papers" action button when selections are made.
- "Load more" button for pagination.
- Papers needing download show progress via DownloadProgress component.

**My Papers tab:**
- Instant local search across all topics.
- Matches against title, authors, arXiv ID (substring).
- Results show which topics each paper belongs to.

### StatusBar (bottom, fixed)

Displays:
- Active topic name
- Model name (clickable to open model selector)
- Token counts: `Tokens: 24,837 (prompt: 18,200 | completion: 6,637)`
- Context budget: `Context: 42% (31K / 73K)` — amber at 50%, warning at 80%
- Phase indicator with colored dot (green=Ready, amber=Thinking,
  blue=Streaming)

Context budget is estimated from: documents + conversation history + system
prompt size, relative to the model's max input tokens (from LiteLLM's
`get_model_info()`).

### TraceViewer (slide-over panel from right)

Opens when clicking "View trace" on an assistant message.

**Header:** Question, timestamp, model, summary stats (total tokens with
prompt/completion split, duration, iteration count, status badge).

**Timeline:** Vertical sequence of collapsible cards, one per trace step.

Each card:
- **Left gutter:** Step number, colored icon by type
  - Blue gear: code_generated
  - Green terminal: code_output
  - Purple arrow: subcall_request / subcall_response
  - Red circle: error
  - Gold star: final_answer
  - Checkmark: verification / semantic_verification
- **Card header:** Step type label, iteration, time delta from start,
  token count if applicable
- **Card body (collapsed by default):** Step content with syntax
  highlighting for code. Final_answer card expanded by default.

**Controls:**
- "Expand all" / "Collapse all" buttons
- Filter toggles to show/hide step types (e.g., hide code_output to see
  just the LLM reasoning chain)

### CitationReport (modal)

Triggered from header "Check" button or per-paper.

- Stats grid: Verified, Mismatch, Not Found, Unresolved counts
- Progress bar (green/amber/red segments)
- LLM phrase detection indicator
- Issues list with citation key, status badge, detail text
- During check: live progress ("Checking citation 3/34...")

### HelpPanel (slide-over from right)

Triggered from "?" button in header.

Three sections:
- **Quick Start Guide:** Step-by-step walkthrough (create topic, search,
  add paper, ask question, view trace, run citation check)
- **FAQ:** Common questions (query duration, context budget, download
  speed, trace step types, citation checking, multi-topic papers, model
  configuration)
- **Keyboard Shortcuts:** Enter to send, Shift+Enter for newline, Escape
  to close panels

Content stored in a static JSON/markdown file for easy updates.

### DownloadProgress (toast stack, bottom-right)

Shows when papers are being downloaded from arXiv.

- Toast-style notifications anchored to bottom-right.
- "Downloading 2501.12345... (1 of 3)"
- Multiple papers queue and process sequentially with **3.1-second** delay
  between downloads (arXiv rate limit with safety margin).
- On error: toast shows error for that paper, continues with rest.
- On success: brief green toast ("Paper added to 2 topics").
- Auto-dismiss success toasts after 8 seconds.

### PaperDetail (expandable section)

Shown between paper bar and chat area when a paper chip is clicked.

- arXiv ID, category badge, date
- Title (serif font)
- Author list
- Abstract
- Close button

### Experimental Banner

- On first launch: dismissible welcome banner above the chat area
  explaining this is experimental software, linking to Help.
- Header subtitle shows "arXiv Explorer" with a small "Experimental" pill
  badge next to it.

---

## Dark/Light Theme

The mockup's CSS variable palette translates to Tailwind custom properties:

| Token | Dark | Light |
|-------|------|-------|
| `surface-0` | `#0b1121` | `#ffffff` |
| `surface-1` | `#0f1729` | `#f8f9fb` |
| `surface-2` | `#151d33` | `#eef0f4` |
| `border` | `#1e2a45` | `#dde1e8` |
| `text-primary` | `#e2e8f0` | `#1a202c` |
| `text-secondary` | `#94a3b8` | `#4a5568` |
| `text-dim` | `#5a6b8a` | `#9aa3b2` |
| `accent` | `#2dd4bf` | `#0d9488` |
| `green` | `#4caf50` | `#2e7d32` |
| `amber` | `#ff9800` | `#e65100` |
| `red` | `#f44336` | `#c62828` |

Toggle via sun/moon icon in header. Preference persisted in `localStorage`.

---

## Error Handling

Three tiers:

1. **Inline errors** — Validation failures (empty topic name, invalid arXiv
   ID). Red text below the relevant input. Clears on next interaction.

2. **Toast notifications** — Transient operational errors (download failed,
   search timed out, arXiv unreachable). Bottom-right stack, auto-dismiss
   after 8 seconds. Red for errors, amber for warnings, green for success.

3. **Connection loss** — Persistent amber banner below header: "Connection
   lost. Reconnecting..." with automatic WebSocket retry. Chat input
   disables until reconnected.

No silent failures. Every user action gets visible feedback.

---

## Storage

All v1 storage is filesystem-based. No database.

### Chat History

Each topic stores conversation in `_conversation.json` within its project
directory:

```json
{
  "exchanges": [
    {
      "exchange_id": "uuid",
      "question": "What are the main hypotheses?",
      "answer": "Based on the papers...",
      "trace_id": "2025-01-15T10-30-00-123_a1b2c3d4",
      "timestamp": "2025-01-15T10:30:00Z",
      "tokens": {
        "prompt": 18200,
        "completion": 6637,
        "total": 24837
      },
      "execution_time": 44.403,
      "model": "gpt-5-mini"
    }
  ]
}
```

### Existing Storage (unchanged)

- **Traces:** JSONL files in `<project>/traces/` (header, steps, summary)
- **Paper cache:** `~/.shesha-arxiv/paper-cache/<arxiv_id>/` (meta.json,
  paper.pdf, source/)
- **Topic metadata:** `_topic.json` in project directory
- **Documents:** `<project>/docs/<doc_name>.json`

---

## Query Cancellation (Engine Change)

Modify `RLMEngine.query()` to accept an optional `cancel_event:
threading.Event` parameter:

1. Check `cancel_event.is_set()` at the top of each iteration in the main
   loop.
2. If set, exit the loop cleanly: write a partial trace with status
   `"interrupted"`, release the container, return a partial `QueryResult`.
3. The WebSocket handler creates the event, passes it to `query()`, and
   sets it when receiving `{"type": "cancel"}`.
4. After cancellation, the next query can start immediately — it will
   acquire a container from the pool (or wait for one to become available
   if the pool is exhausted).

This replaces the TUI's cosmetic cancellation. The TUI's double-Esc handler
should be updated to use the same `cancel_event` mechanism instead of just
bumping a query ID.

---

## Context Budget

The status bar shows estimated context usage as a percentage.

**Calculation:**
- `max_tokens` = LiteLLM `get_model_info(model)["max_input_tokens"]`
- `used_tokens` = estimated from: system prompt chars + all document chars
  in topic + conversation history chars (using ~4 chars/token heuristic)
- `budget_pct` = `used_tokens / max_tokens * 100`

**Thresholds:**
- 0-49%: green indicator
- 50-79%: amber indicator
- 80%+: red warning with message suggesting starting a fresh conversation
  or exporting the transcript

---

## ARXIV.md Setup Guide

A researcher-facing document at the project root. Written for someone who
may never have used a terminal.

### Structure

1. **What is Shesha?** — One-paragraph explanation of what it does and why
   a researcher would want it.
2. **Prerequisites** — What to install, with links to installers per OS:
   - Python 3.11+
   - Docker Desktop (with explanation: "runs code safely in isolation")
   - Node.js 20+
   - An LLM API key (how to get one, where to set it)
3. **Installation** — Numbered copy-paste terminal commands:
   - Clone/download the project
   - Create virtual environment
   - `pip install -e ".[web]"`
   - Build frontend (`cd frontend && npm install && npm run build`)
   - Set API key environment variable
4. **First Run** — Launch command (`shesha-web` or `python -m
   shesha.experimental.web`), what to expect in the browser.
5. **Your First Research Session** — Guided walkthrough with expected
   output:
   - Create a topic
   - Search for a known paper
   - Add it to the topic
   - Ask a question
   - View the trace
   - Run a citation check
6. **Troubleshooting** — Common issues: Docker not running, API key not
   set, port in use, arXiv search returning nothing, downloads failing.
7. **Experimental Notice** — Clear statement that this is experimental
   software.

---

## Deliverables

1. **FastAPI backend** — `src/shesha/experimental/web/` (api.py, ws.py,
   schemas.py, dependencies.py, session.py)
2. **React frontend** — `src/shesha/experimental/web/frontend/`
3. **Engine cancellation** — `threading.Event` support in `RLMEngine.query()`
4. **TUI cancellation update** — Use same `cancel_event` mechanism
5. **pip extra** — `[web]` in pyproject.toml
6. **ARXIV.md** — Researcher-facing setup guide at project root
7. **Help content** — Static FAQ/guide content for in-app help panel
8. **Experimental banner** — In-app and in-docs notices

---

## Out of Scope for v1

- Multi-user authentication and session isolation
- Database storage (SQLite/PostgreSQL)
- Mid-step cancellation (interrupting blocking LLM calls)
- Full-text search across paper content
- Paper annotations or highlighting
- Collaborative features
- Mobile/responsive layout
- Deployment to cloud infrastructure
