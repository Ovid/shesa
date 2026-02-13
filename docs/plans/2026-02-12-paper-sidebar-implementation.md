# Paper Sidebar Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move papers from the top PaperBar into collapsible sidebar lists under each topic, with selection checkboxes for query scoping and paper detail view in the main area.

**Architecture:** Papers become a collapsible tree inside `TopicSidebar`. Selection state (`Set<string>`) lives in `App.tsx` and is passed to the query layer. `PaperDetail` renders in the main area instead of the chat when a paper is clicked. The backend gains an optional `paper_ids` filter on the WebSocket query message.

**Tech Stack:** React/TypeScript (Vite), Python/FastAPI, WebSocket

---

### Task 1: Backend — Add paper_ids filter to WebSocket query handler

**Files:**
- Modify: `src/shesha/experimental/web/ws.py:42-55`
- Test: `tests/experimental/web/test_ws_paper_filter.py` (create)

**Step 1: Write the failing test**

```python
"""Test that _handle_query filters documents by paper_ids."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_state():
    state = MagicMock()
    state.topic_mgr.resolve.return_value = "proj-123"
    state.topic_mgr._storage.list_documents.return_value = [
        "2310.20260v1",
        "2010.09271v1",
        "1510.08155v1",
    ]
    state.topic_mgr._storage._project_path.return_value = MagicMock()
    state.topic_mgr._storage.list_traces.return_value = []
    state.model = "test-model"

    # Mock the project and query result
    mock_result = MagicMock()
    mock_result.answer = "test answer"
    mock_result.token_usage.prompt_tokens = 10
    mock_result.token_usage.completion_tokens = 5
    mock_result.token_usage.total_tokens = 15
    mock_result.execution_time = 1.0

    project = MagicMock()
    project.query.return_value = mock_result
    state.shesha.get_project.return_value = project

    return state


@pytest.fixture
def mock_ws():
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_handle_query_filters_by_paper_ids(mock_state, mock_ws):
    """When paper_ids is provided, only those docs should be loaded."""
    from shesha.experimental.web.ws import _handle_query

    data = {
        "type": "query",
        "topic": "chess",
        "question": "test question",
        "paper_ids": ["2310.20260v1", "1510.08155v1"],
    }

    with patch(
        "shesha.experimental.web.ws.WebConversationSession"
    ) as mock_session_cls:
        mock_session = MagicMock()
        mock_session.format_history_prefix.return_value = ""
        mock_session_cls.return_value = mock_session

        await _handle_query(mock_ws, mock_state, data)

    # Verify the project query was called
    project = mock_state.shesha.get_project.return_value
    project.query.assert_called_once()
    call_kwargs = project.query.call_args

    # The docs loaded should only be the filtered set
    # We check via the storage mock — load_all_documents should NOT be called
    # Instead, get_document should be called for each paper_id
    mock_storage = mock_state.topic_mgr._storage
    assert mock_storage.get_document.call_count == 2
    mock_storage.get_document.assert_any_call("proj-123", "2310.20260v1")
    mock_storage.get_document.assert_any_call("proj-123", "1510.08155v1")


@pytest.mark.asyncio
async def test_handle_query_no_paper_ids_loads_all(mock_state, mock_ws):
    """When paper_ids is absent, all docs should be loaded (existing behavior)."""
    from shesha.experimental.web.ws import _handle_query

    data = {
        "type": "query",
        "topic": "chess",
        "question": "test question",
    }

    with patch(
        "shesha.experimental.web.ws.WebConversationSession"
    ) as mock_session_cls:
        mock_session = MagicMock()
        mock_session.format_history_prefix.return_value = ""
        mock_session_cls.return_value = mock_session

        await _handle_query(mock_ws, mock_state, data)

    # Should load all documents via load_all_documents
    mock_storage = mock_state.topic_mgr._storage
    mock_storage.load_all_documents.assert_called_once_with("proj-123")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/experimental/web/test_ws_paper_filter.py -v`
Expected: FAIL — `_handle_query` doesn't read `paper_ids` yet.

**Step 3: Write minimal implementation**

In `src/shesha/experimental/web/ws.py`, modify `_handle_query` (lines 42-55):

```python
async def _handle_query(ws: WebSocket, state: AppState, data: dict[str, object]) -> threading.Event:
    """Execute a query and stream progress. Returns the cancel_event."""
    topic = str(data.get("topic", ""))
    question = str(data.get("question", ""))
    paper_ids = data.get("paper_ids")  # Optional list of arXiv IDs to filter

    project_id = state.topic_mgr.resolve(topic)
    if not project_id:
        await ws.send_json({"type": "error", "message": f"Topic '{topic}' not found"})
        return threading.Event()

    docs = state.topic_mgr._storage.list_documents(project_id)
    if not docs:
        await ws.send_json({"type": "error", "message": "No papers in topic"})
        return threading.Event()

    project = state.shesha.get_project(project_id)
    cancel_event = threading.Event()

    # Load documents — filtered if paper_ids provided, otherwise all
    if paper_ids and isinstance(paper_ids, list):
        loaded_docs = [
            state.topic_mgr._storage.get_document(project_id, pid)
            for pid in paper_ids
            if pid in docs
        ]
    else:
        loaded_docs = state.topic_mgr._storage.load_all_documents(project_id)

    if not loaded_docs:
        await ws.send_json({"type": "error", "message": "No matching papers found"})
        return threading.Event()

    # Load session for history prefix
    project_dir = state.topic_mgr._storage._project_path(project_id)
    session = WebConversationSession(project_dir)
    history_prefix = session.format_history_prefix()
    full_question = history_prefix + question if history_prefix else question
```

Then change the `project.query` call (around line 98) to use `loaded_docs` instead of calling `project.query` directly. Replace:

```python
    result = await loop.run_in_executor(
        None,
        lambda: project.query(full_question, on_progress=on_progress, cancel_event=cancel_event),
    )
```

With a direct call to the RLM engine using the filtered docs:

```python
    result = await loop.run_in_executor(
        None,
        lambda: project._rlm_engine.query(
            documents=[d.content for d in loaded_docs],
            question=full_question,
            doc_names=[d.name for d in loaded_docs],
            on_progress=on_progress,
            storage=state.topic_mgr._storage,
            project_id=project_id,
            cancel_event=cancel_event,
        ),
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/experimental/web/test_ws_paper_filter.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/web/ws.py tests/experimental/web/test_ws_paper_filter.py
git commit -m "feat(web): add paper_ids filter to WebSocket query handler"
```

---

### Task 2: TopicSidebar — Add paper fetching and collapsible list

**Files:**
- Modify: `src/shesha/experimental/web/frontend/src/components/TopicSidebar.tsx`

**Step 1: Add paper state and fetching**

Import `PaperInfo` type and `api.papers.list`. Add state for expanded topics and papers cache:

```typescript
import type { TopicInfo, PaperInfo } from '../types'

// Inside the component, add these state variables:
const [expandedTopic, setExpandedTopic] = useState<string | null>(null)
const [topicPapers, setTopicPapers] = useState<Record<string, PaperInfo[]>>({})
```

**Step 2: Add toggle handler that fetches papers on expand**

```typescript
const handleTogglePapers = async (topicName: string, e: React.MouseEvent) => {
  e.stopPropagation()
  if (expandedTopic === topicName) {
    setExpandedTopic(null)
    return
  }
  setExpandedTopic(topicName)
  // Fetch papers if not cached
  if (!topicPapers[topicName]) {
    try {
      const papers = await api.papers.list(topicName)
      setTopicPapers(prev => ({ ...prev, [topicName]: papers }))
    } catch {
      showToast('Failed to load papers', 'error')
    }
  }
}
```

**Step 3: Render the chevron and paper list under each topic**

In the topic row JSX, add a chevron button before the topic name, and render a paper list below the topic row when expanded. Each paper row shows:
- A checkbox (for selection — wired in Task 4)
- The title, truncated with CSS `truncate` class
- A `title` attribute for hover tooltip showing full title + first author + year

```tsx
{/* Chevron toggle */}
<button
  onClick={(e) => handleTogglePapers(t.name, e)}
  className="text-text-dim hover:text-text-secondary mr-1 text-[10px] w-3 shrink-0"
>
  {expandedTopic === t.name ? '▼' : '▶'}
</button>
```

Below the topic row (inside the map, after the topic div), conditionally render the paper list:

```tsx
{expandedTopic === t.name && topicPapers[t.name] && (
  <div className="bg-surface-0/50">
    {topicPapers[t.name].map(p => (
      <div
        key={p.arxiv_id}
        className="flex items-center gap-1 px-3 pl-7 py-1 text-xs text-text-secondary hover:bg-surface-2 cursor-pointer"
        title={`${p.title}\n${p.authors[0] ?? ''} · ${p.date?.slice(0, 4) ?? ''}`}
      >
        <span className="truncate">{p.title}</span>
      </div>
    ))}
  </div>
)}
```

**Step 4: Invalidate paper cache on refreshKey change**

Clear `topicPapers` when `refreshKey` changes (papers added/removed):

```typescript
useEffect(() => { setTopicPapers({}) }, [refreshKey])
```

**Step 5: Build and verify visually**

Run: `cd src/shesha/experimental/web/frontend && npm run build`
Expected: Build succeeds. Manually verify sidebar shows chevrons and expandable paper lists.

**Step 6: Commit**

```bash
git add src/shesha/experimental/web/frontend/src/components/TopicSidebar.tsx
git commit -m "feat(web): add collapsible paper list to topic sidebar"
```

---

### Task 3: TopicSidebar — Add selection checkboxes and All/None toggle

**Files:**
- Modify: `src/shesha/experimental/web/frontend/src/components/TopicSidebar.tsx`

This task adds the props interface changes and checkbox UI. Selection state is owned by `App.tsx` (wired in Task 5).

**Step 1: Add new props to TopicSidebarProps**

```typescript
interface TopicSidebarProps {
  activeTopic: string | null
  onSelectTopic: (name: string) => void
  onTopicsChange: () => void
  refreshKey: number
  // New props for paper management:
  selectedPapers: Set<string>
  onSelectionChange: (selected: Set<string>) => void
  onPaperClick: (paper: PaperInfo) => void
  allPapersForTopic: PaperInfo[]  // passed from App so selection state stays in sync
}
```

Wait — simpler approach: `TopicSidebar` fetches papers internally (Task 2), so it should **emit** the full paper list when loaded, and App manages selection. Add these props:

```typescript
interface TopicSidebarProps {
  activeTopic: string | null
  onSelectTopic: (name: string) => void
  onTopicsChange: () => void
  refreshKey: number
  selectedPapers: Set<string>
  onSelectionChange: (selected: Set<string>) => void
  onPaperClick: (paper: PaperInfo) => void
  onPapersLoaded: (papers: PaperInfo[]) => void
}
```

**Step 2: Call onPapersLoaded when papers are fetched**

In `handleTogglePapers`, after fetching papers, call `onPapersLoaded(papers)` so App can initialize `selectedPapers` to all IDs.

**Step 3: Add checkbox to each paper row**

```tsx
<input
  type="checkbox"
  checked={selectedPapers.has(p.arxiv_id)}
  onChange={(e) => {
    e.stopPropagation()
    const next = new Set(selectedPapers)
    if (next.has(p.arxiv_id)) {
      next.delete(p.arxiv_id)
    } else {
      next.add(p.arxiv_id)
    }
    onSelectionChange(next)
  }}
  className="shrink-0 accent-accent"
/>
```

The title text click calls `onPaperClick(p)`:

```tsx
<span
  className="truncate cursor-pointer hover:text-accent"
  onClick={(e) => { e.stopPropagation(); onPaperClick(p) }}
>
  {p.title}
</span>
```

**Step 4: Add All/None toggle row**

At the top of the expanded paper list, before the paper rows:

```tsx
<div className="flex items-center gap-2 px-3 pl-7 py-1 text-[10px] text-text-dim">
  <button
    className="hover:text-accent"
    onClick={() => {
      const allIds = new Set(topicPapers[t.name].map(p => p.arxiv_id))
      onSelectionChange(allIds)
    }}
  >All</button>
  <span>/</span>
  <button
    className="hover:text-accent"
    onClick={() => onSelectionChange(new Set())}
  >None</button>
</div>
```

**Step 5: Update topic header to show selected/total count**

Replace the static paper count with a dynamic selected/total display when some papers are deselected:

```tsx
const total = t.paper_count
const topicPaperList = topicPapers[t.name]
const selectedCount = topicPaperList
  ? topicPaperList.filter(p => selectedPapers.has(p.arxiv_id)).length
  : total
const countDisplay = selectedCount < total ? `${selectedCount}/${total}` : `${total}`
```

Then use `{countDisplay} · {t.size}` in the JSX.

**Step 6: Build and verify**

Run: `cd src/shesha/experimental/web/frontend && npm run build`
Expected: Build succeeds (TypeScript errors expected in App.tsx until Task 5 wires the props — that's fine, `npm run build` may fail here. In that case, just check the file for syntax errors and move on to Task 4.)

**Step 7: Commit**

```bash
git add src/shesha/experimental/web/frontend/src/components/TopicSidebar.tsx
git commit -m "feat(web): add selection checkboxes and All/None toggle to paper list"
```

---

### Task 4: PaperDetail — Adapt for full-width main area rendering

**Files:**
- Modify: `src/shesha/experimental/web/frontend/src/components/PaperDetail.tsx`

**Step 1: Add Back button and full-width layout**

The existing `PaperDetail` is a compact inline panel. Change it to a full-page view suitable for the main content area:

```tsx
import type { PaperInfo } from '../types'

interface PaperDetailProps {
  paper: PaperInfo | null
  topicName: string
  onRemove: (arxivId: string) => void
  onClose: () => void
}

export default function PaperDetail({ paper, topicName, onRemove, onClose }: PaperDetailProps) {
  if (!paper) return null

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0">
      {/* Top bar with Back button */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-border bg-surface-1">
        <button
          onClick={onClose}
          className="text-sm text-text-secondary hover:text-accent transition-colors"
        >
          &larr; Back
        </button>
        <span className="text-xs text-text-dim font-mono">{paper.arxiv_id}</span>
      </div>

      {/* Paper content */}
      <div className="flex-1 overflow-y-auto px-6 py-6 max-w-3xl">
        <h1 className="text-xl font-semibold text-text-primary leading-tight">
          {paper.title}
        </h1>
        <p className="text-sm text-text-secondary mt-2">
          {paper.authors.join(', ')}
        </p>
        <div className="flex items-center gap-3 mt-3 text-xs text-text-dim font-mono">
          <span>{paper.category}</span>
          <span>{paper.date}</span>
          <a
            href={paper.arxiv_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent hover:underline"
          >
            View on arXiv
          </a>
        </div>
        <div className="mt-6 text-sm text-text-secondary leading-relaxed">
          {paper.abstract}
        </div>

        {/* Actions */}
        <div className="mt-8 flex gap-3">
          <button
            onClick={() => {
              if (confirm(`Remove paper ${paper.arxiv_id} from "${topicName}"?`)) {
                onRemove(paper.arxiv_id)
              }
            }}
            className="px-3 py-1.5 text-xs text-red border border-red/30 rounded hover:bg-red/10 transition-colors"
          >
            Remove from topic
          </button>
        </div>
      </div>
    </div>
  )
}
```

**Step 2: Build and verify**

Run: `cd src/shesha/experimental/web/frontend && npm run build`
Expected: Build succeeds (component interface unchanged — same props).

**Step 3: Commit**

```bash
git add src/shesha/experimental/web/frontend/src/components/PaperDetail.tsx
git commit -m "feat(web): adapt PaperDetail for full-width main area rendering"
```

---

### Task 5: App.tsx — Wire selection state, paper detail view, remove PaperBar

**Files:**
- Modify: `src/shesha/experimental/web/frontend/src/App.tsx`

This is the integration task that ties everything together.

**Step 1: Add new state variables**

```typescript
const [selectedPapers, setSelectedPapers] = useState<Set<string>>(new Set())
const [viewingPaper, setViewingPaper] = useState<PaperInfo | null>(null)
const [topicPapersList, setTopicPapersList] = useState<PaperInfo[]>([])
```

**Step 2: Add handlers**

```typescript
const handlePapersLoaded = useCallback((papers: PaperInfo[]) => {
  setTopicPapersList(papers)
  setSelectedPapers(new Set(papers.map(p => p.arxiv_id)))
}, [])

const handlePaperClick = useCallback((paper: PaperInfo) => {
  setViewingPaper(paper)
}, [])

const handlePaperRemove = useCallback(async (arxivId: string) => {
  if (!activeTopic) return
  try {
    await api.papers.remove(activeTopic, arxivId)
    setPapersVersion(v => v + 1)
    setViewingPaper(null)
    // Remove from selection
    setSelectedPapers(prev => {
      const next = new Set(prev)
      next.delete(arxivId)
      return next
    })
    showToast('Paper removed', 'success')
  } catch {
    showToast('Failed to remove paper', 'error')
  }
}, [activeTopic])
```

**Step 3: Reset state on topic change**

In `handleTopicSelect`, reset paper-related state:

```typescript
const handleTopicSelect = useCallback((name: string) => {
  setActiveTopic(name)
  setViewingPaper(null)
  setSelectedPapers(new Set())
  setTopicPapersList([])
  api.contextBudget(name).then(setBudget).catch(() => {})
}, [])
```

**Step 4: Remove PaperBar import and rendering**

Delete the `import PaperBar` line and remove `<PaperBar ... />` from JSX.

**Step 5: Update TopicSidebar props**

```tsx
<TopicSidebar
  activeTopic={activeTopic}
  onSelectTopic={handleTopicSelect}
  onTopicsChange={() => {}}
  refreshKey={papersVersion}
  selectedPapers={selectedPapers}
  onSelectionChange={setSelectedPapers}
  onPaperClick={handlePaperClick}
  onPapersLoaded={handlePapersLoaded}
/>
```

**Step 6: Conditional main area rendering**

Replace the center column content:

```tsx
{/* Center column */}
<div className="flex-1 flex flex-col min-w-0 min-h-0">
  {viewingPaper ? (
    <PaperDetail
      paper={viewingPaper}
      topicName={activeTopic ?? ''}
      onRemove={handlePaperRemove}
      onClose={() => setViewingPaper(null)}
    />
  ) : (
    <ChatArea
      topicName={activeTopic}
      connected={connected}
      wsSend={send}
      wsOnMessage={onMessage}
      onViewTrace={handleViewTrace}
      onClearHistory={handleClearHistory}
      historyVersion={historyVersion}
    />
  )}
</div>
```

**Step 7: Pass selectedPapers to the WebSocket query**

In `ChatArea.tsx`, add `selectedPapers` to props and include `paper_ids` in the WS message. Update the `handleSend` in `ChatArea`:

```typescript
// In ChatAreaProps:
selectedPapers?: Set<string>

// In handleSend:
const msg: Record<string, unknown> = { type: 'query', topic: topicName, question }
if (selectedPapers && selectedPapers.size > 0) {
  msg.paper_ids = Array.from(selectedPapers)
}
wsSend(msg)
```

In `App.tsx`, pass the prop:
```tsx
<ChatArea
  ...
  selectedPapers={selectedPapers}
/>
```

**Step 8: Build and verify**

Run: `cd src/shesha/experimental/web/frontend && npm run build`
Expected: Build succeeds. No TypeScript errors.

**Step 9: Commit**

```bash
git add src/shesha/experimental/web/frontend/src/App.tsx \
       src/shesha/experimental/web/frontend/src/components/ChatArea.tsx \
       src/shesha/experimental/web/frontend/src/components/TopicSidebar.tsx
git commit -m "feat(web): wire paper selection state and detail view in App"
```

---

### Task 6: Delete PaperBar component

**Files:**
- Delete: `src/shesha/experimental/web/frontend/src/components/PaperBar.tsx`

**Step 1: Delete the file**

```bash
rm src/shesha/experimental/web/frontend/src/components/PaperBar.tsx
```

**Step 2: Verify no remaining imports**

Search for any remaining `PaperBar` references:

```bash
grep -r "PaperBar" src/shesha/experimental/web/frontend/src/
```

Expected: No results (the import was already removed in Task 5).

**Step 3: Build to confirm**

Run: `cd src/shesha/experimental/web/frontend && npm run build`
Expected: Build succeeds.

**Step 4: Commit**

```bash
git add -A src/shesha/experimental/web/frontend/src/components/PaperBar.tsx
git commit -m "refactor(web): delete PaperBar component"
```

---

### Task 7: Run backend tests and final build

**Files:** None (verification only)

**Step 1: Run the backend paper filter test**

Run: `pytest tests/experimental/web/test_ws_paper_filter.py -v`
Expected: PASS

**Step 2: Run full backend test suite**

Run: `make all`
Expected: All checks pass (format, lint, typecheck, tests).

**Step 3: Run frontend build**

Run: `cd src/shesha/experimental/web/frontend && npm run build`
Expected: Build succeeds.

**Step 4: Commit any final fixups**

If any tests or linting issues were found in Steps 1-3, fix and commit.

---

### Task 8: Update CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add entry under [Unreleased]**

```markdown
### Changed
- Web interface: moved papers from top chip bar into collapsible sidebar lists under each topic with title display, selection checkboxes, and All/None toggle
- Web interface: clicking a paper title opens full detail view in the main content area
- Web queries can now be scoped to selected papers via optional `paper_ids` filter
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for paper sidebar redesign"
```
