# Inline Paper Citations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the arXiv Explorer's LLM responses cite papers by arxiv ID with clickable links that open the paper detail view, instead of opaque "chunk N" references.

**Architecture:** Inject citation instructions into the user question in the websocket handler (arXiv-specific, no changes to shared prompts or engine API). Parse `[@arxiv:ID]` tokens in the frontend and render as clickable buttons that open the paper detail view.

**Tech Stack:** Python (FastAPI websocket handler), TypeScript/React (ChatMessage component), Vitest (frontend tests), pytest (backend tests)

---

### Task 1: Backend — `build_citation_instructions` helper

**Files:**
- Modify: `src/shesha/experimental/web/websockets.py`
- Test: `tests/unit/experimental/web/test_citation_instructions.py`
- Create: `tests/unit/experimental/web/test_citation_instructions.py`

**Step 1: Write the failing test**

Create `tests/unit/experimental/web/test_citation_instructions.py`:

```python
"""Tests for citation instruction builder."""

from unittest.mock import MagicMock

from shesha.experimental.web.websockets import build_citation_instructions


def test_build_citation_instructions_single_paper() -> None:
    """Single paper produces instruction block with one entry."""
    cache = MagicMock()
    meta = MagicMock()
    meta.title = "An Objective Bayesian Analysis"
    cache.get_meta.return_value = meta

    result = build_citation_instructions(["2005.09008v1"], cache)

    assert "[@arxiv:2005.09008v1]" in result
    assert "An Objective Bayesian Analysis" in result
    assert "CITATION INSTRUCTIONS" in result


def test_build_citation_instructions_multiple_papers() -> None:
    """Multiple papers listed in instruction block."""
    cache = MagicMock()

    def fake_meta(arxiv_id: str) -> MagicMock:
        m = MagicMock()
        m.title = f"Title for {arxiv_id}"
        return m

    cache.get_meta.side_effect = fake_meta

    result = build_citation_instructions(["2005.09008v1", "2401.12345"], cache)

    assert "[@arxiv:2005.09008v1]" in result
    assert "[@arxiv:2401.12345]" in result
    assert "Title for 2005.09008v1" in result
    assert "Title for 2401.12345" in result


def test_build_citation_instructions_missing_meta_uses_id() -> None:
    """When cache has no metadata, fall back to arxiv_id as title."""
    cache = MagicMock()
    cache.get_meta.return_value = None

    result = build_citation_instructions(["2005.09008v1"], cache)

    assert "[@arxiv:2005.09008v1]" in result
    # Should still produce valid instructions even without title
    assert "2005.09008v1" in result


def test_build_citation_instructions_empty_list() -> None:
    """Empty paper list returns empty string."""
    cache = MagicMock()

    result = build_citation_instructions([], cache)

    assert result == ""
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/experimental/web/test_citation_instructions.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_citation_instructions' from 'shesha.experimental.web.websockets'`

**Step 3: Write minimal implementation**

Add to `src/shesha/experimental/web/websockets.py` (after the imports, before `websocket_handler`):

```python
from shesha.experimental.arxiv.cache import PaperCache


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
```

Note: `PaperCache` is already imported indirectly via `dependencies.py`, but we need the explicit import for the type annotation. Check that `from shesha.experimental.arxiv.cache import PaperCache` doesn't duplicate — it's not currently imported in `websockets.py`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/experimental/web/test_citation_instructions.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add tests/unit/experimental/web/test_citation_instructions.py src/shesha/experimental/web/websockets.py
git commit -m "feat(web): add build_citation_instructions helper"
```

---

### Task 2: Backend — Wire citation instructions into `_handle_query`

**Files:**
- Modify: `src/shesha/experimental/web/websockets.py:124-130`

**Step 1: Write the failing test**

Add to `tests/unit/experimental/web/test_citation_instructions.py`:

```python
def test_citation_instructions_appended_to_question() -> None:
    """Verify that build_citation_instructions output follows expected structure.

    The actual wiring into _handle_query is integration-level (WebSocket +
    async + RLM engine), so we test the contract: the returned string starts
    with newlines and ends with the 'Always use' instruction.
    """
    cache = MagicMock()
    meta = MagicMock()
    meta.title = "Test Paper"
    cache.get_meta.return_value = meta

    instructions = build_citation_instructions(["2005.09008v1"], cache)

    # Starts with newlines so it appends cleanly to a question
    assert instructions.startswith("\n\n")
    # Ends with the closing instruction
    assert instructions.endswith("Always use [@arxiv:ID] when referencing a specific paper's claims or quotes.")
```

**Step 2: Run test to verify it fails (or passes if contract already met)**

Run: `pytest tests/unit/experimental/web/test_citation_instructions.py -v`
Expected: PASS (the helper already follows this contract)

**Step 3: Wire into `_handle_query`**

In `src/shesha/experimental/web/websockets.py`, modify `_handle_query` around line 130. Change:

```python
    full_question = history_prefix + question if history_prefix else question
```

To:

```python
    citation_suffix = build_citation_instructions(
        [d.name for d in loaded_docs], state.cache
    )
    full_question = (history_prefix + question if history_prefix else question) + citation_suffix
```

**Step 4: Run all backend tests**

Run: `pytest tests/unit/experimental/web/ -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shesha/experimental/web/websockets.py tests/unit/experimental/web/test_citation_instructions.py
git commit -m "feat(web): inject citation instructions into arXiv queries"
```

---

### Task 3: Frontend — Citation rendering in `ChatMessage.tsx`

**Files:**
- Modify: `src/shesha/experimental/web/frontend/src/components/ChatMessage.tsx:40`
- Test: `src/shesha/experimental/web/frontend/src/components/__tests__/ChatMessage.test.tsx`
- Create: `src/shesha/experimental/web/frontend/src/components/__tests__/ChatMessage.test.tsx`

**Step 1: Write the failing test**

Create `src/shesha/experimental/web/frontend/src/components/__tests__/ChatMessage.test.tsx`:

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

import ChatMessage from '../ChatMessage'
import type { Exchange, PaperInfo } from '../../types'

const basePaper: PaperInfo = {
  arxiv_id: '2005.09008v1',
  title: 'An Objective Bayesian Analysis',
  authors: ['David Kipping'],
  abstract: 'Life emerged...',
  category: 'astro-ph.EP',
  date: '2020-05-18',
  arxiv_url: 'https://arxiv.org/abs/2005.09008v1',
  source_type: 'latex',
}

const baseExchange: Exchange = {
  question: 'What is abiogenesis?',
  answer: 'See [@arxiv:2005.09008v1] for details.',
  timestamp: '2026-02-13T12:00:00Z',
  tokens: { prompt: 100, completion: 50, total: 150 },
  execution_time: 5.0,
  trace_id: 'trace-1',
  paper_ids: ['2005.09008v1'],
}

describe('ChatMessage citation rendering', () => {
  it('renders [@arxiv:ID] as a clickable button', () => {
    const onPaperClick = vi.fn()
    render(
      <ChatMessage
        exchange={baseExchange}
        onViewTrace={vi.fn()}
        topicPapers={[basePaper]}
        onPaperClick={onPaperClick}
      />
    )

    const citationButton = screen.getByRole('button', { name: /2005\.09008v1/i })
    expect(citationButton).toBeDefined()
    fireEvent.click(citationButton)
    expect(onPaperClick).toHaveBeenCalledWith(basePaper)
  })

  it('renders unknown arxiv ID as plain text', () => {
    const exchange: Exchange = {
      ...baseExchange,
      answer: 'See [@arxiv:9999.99999v1] for details.',
    }
    render(
      <ChatMessage
        exchange={exchange}
        onViewTrace={vi.fn()}
        topicPapers={[basePaper]}
        onPaperClick={vi.fn()}
      />
    )

    // Should render as literal text, not a button
    expect(screen.queryByRole('button', { name: /9999\.99999v1/i })).toBeNull()
    expect(screen.getByText(/\[@arxiv:9999\.99999v1\]/)).toBeDefined()
  })

  it('renders answer without citations as plain text', () => {
    const exchange: Exchange = {
      ...baseExchange,
      answer: 'No citations here.',
    }
    render(
      <ChatMessage
        exchange={exchange}
        onViewTrace={vi.fn()}
        topicPapers={[basePaper]}
        onPaperClick={vi.fn()}
      />
    )

    expect(screen.getByText('No citations here.')).toBeDefined()
  })

  it('renders multiple citations in one answer', () => {
    const paper2: PaperInfo = {
      ...basePaper,
      arxiv_id: '2401.12345',
      title: 'Another Paper',
    }
    const exchange: Exchange = {
      ...baseExchange,
      answer: 'Compare [@arxiv:2005.09008v1] with [@arxiv:2401.12345].',
      paper_ids: ['2005.09008v1', '2401.12345'],
    }
    render(
      <ChatMessage
        exchange={exchange}
        onViewTrace={vi.fn()}
        topicPapers={[basePaper, paper2]}
        onPaperClick={vi.fn()}
      />
    )

    const buttons = screen.getAllByRole('button').filter(
      b => b.textContent?.includes('09008') || b.textContent?.includes('12345')
    )
    expect(buttons.length).toBe(2)
  })
})
```

**Step 2: Run test to verify it fails**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run src/components/__tests__/ChatMessage.test.tsx`
Expected: FAIL — citations render as plain text, no button with arxiv ID text found

**Step 3: Write minimal implementation**

Modify `src/shesha/experimental/web/frontend/src/components/ChatMessage.tsx`.

Replace line 40:
```tsx
          <div className="whitespace-pre-wrap">{exchange.answer}</div>
```

With:
```tsx
          <div className="whitespace-pre-wrap">{renderAnswerWithCitations(exchange.answer, topicPapers, onPaperClick)}</div>
```

Add this function before the `ChatMessage` component (after the `formatTime` function):

```tsx
const CITATION_RE = /\[@arxiv:([^\]]+)\]/g

function renderAnswerWithCitations(
  text: string,
  topicPapers?: PaperInfo[],
  onPaperClick?: (paper: PaperInfo) => void,
): React.ReactNode[] {
  const parts: React.ReactNode[] = []
  let lastIndex = 0

  for (const match of text.matchAll(CITATION_RE)) {
    const arxivId = match[1]
    const matchStart = match.index!

    // Add text before this match
    if (matchStart > lastIndex) {
      parts.push(text.slice(lastIndex, matchStart))
    }

    // Look up paper — only render as button if found in topicPapers
    const paper = topicPapers?.find(p => p.arxiv_id === arxivId)
    if (paper) {
      parts.push(
        <button
          key={`cite-${matchStart}`}
          onClick={() => onPaperClick?.(paper)}
          className="text-xs text-accent hover:underline bg-accent/5 rounded px-1 py-0.5 mx-0.5 inline"
          title={paper.title}
        >
          {paper.arxiv_id}
        </button>
      )
    } else {
      // Unknown ID — render as literal text
      parts.push(match[0])
    }

    lastIndex = matchStart + match[0].length
  }

  // Add remaining text after last match
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }

  return parts.length > 0 ? parts : [text]
}
```

Add `import type React from 'react'` at the top if not already imported (check — it may be implicitly available with the JSX transform).

**Step 4: Run test to verify it passes**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run src/components/__tests__/ChatMessage.test.tsx`
Expected: All 4 tests PASS

**Step 5: Run all frontend tests**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/shesha/experimental/web/frontend/src/components/ChatMessage.tsx src/shesha/experimental/web/frontend/src/components/__tests__/ChatMessage.test.tsx
git commit -m "feat(web): render inline paper citations as clickable links"
```

---

### Task 4: Full test suite + lint

**Step 1: Run backend tests**

Run: `pytest tests/ -v --timeout=30`
Expected: All PASS

**Step 2: Run mypy**

Run: `mypy src/shesha`
Expected: No errors

**Step 3: Run ruff**

Run: `ruff check src tests && ruff format --check src tests`
Expected: No errors

**Step 4: Run frontend tests**

Run: `cd src/shesha/experimental/web/frontend && npx vitest run`
Expected: All PASS

**Step 5: Commit any fixups if needed, then final commit**

```bash
git add -A && git commit -m "chore: lint and type fixes for inline citations"
```

(Only if there were fixups. Skip if everything was clean.)

---

### Task 5: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add entry under `[Unreleased]`**

Under the `## [Unreleased]` section, add to `### Added`:

```markdown
- Inline paper citations in arXiv Explorer — LLM responses now cite papers by arxiv ID with clickable links that open the paper detail view
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add inline citations to changelog"
```
