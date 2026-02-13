# Inline Paper Citations for arXiv Explorer

## Problem

When the arXiv Explorer answers queries, the RLM produces citations like "(chunk 6)" which are meaningless to users. Users must remember to ask for proper citations every time. Citations should reference papers by title and be clickable, opening the paper detail view.

## Decisions

- **Approach A chosen:** Inject citation instructions into the user question in the websocket handler. No changes to the shared system prompt (`prompts/system.md`) or the RLM engine API. This keeps the change arXiv-specific — Barsoom, CLI, and TUI are unaffected.
- **Citation format:** `[@arxiv:ID]` (e.g. `[@arxiv:2005.09008v1]`). The `arxiv:` prefix distinguishes from LaTeX/BibTeX `[@key]` patterns that appear in paper source.
- **Click action:** Opens the paper detail view (same as clicking a paper title in the sidebar).
- **Validation:** Frontend only renders a citation as a clickable link if the captured ID matches a paper in the current topic. Unknown IDs render as literal text. Two layers of protection: `arxiv:` prefix + known-ID whitelist.

## Design

### Backend: `websockets.py:_handle_query`

After loading documents and before calling `rlm_engine.query()`, build a citation instruction block and append it to `full_question`:

```
CITATION INSTRUCTIONS: When citing a source paper in your answer, use the format [@arxiv:ID] inline.
Available papers:
- [@arxiv:2005.09008v1] "An Objective Bayesian Analysis of Life's Early Start and Our Late Arrival"
- [@arxiv:2401.12345] "Another Paper Title"
Always use [@arxiv:ID] when referencing a specific paper's claims or quotes.
```

Paper titles come from `state.cache.get_meta(paper_id)` (already used by the citation checker). Map each `loaded_doc.name` to its title via the cache.

### Frontend: `ChatMessage.tsx`

Replace the plain `whitespace-pre-wrap` div with a rendering function that:

1. Uses regex `/\[@arxiv:([^\]]+)\]/g` to find citation patterns in the answer text
2. Splits text into segments: plain text and citation tokens
3. Renders citation tokens as clickable `<button>` elements (styled like existing consulted-papers badges) that call `onPaperClick(paper)` to open the paper detail view
4. Falls back to plain text if the captured arxiv_id doesn't match any paper in `topicPapers`

Plain text segments keep `whitespace-pre-wrap` styling.

## Non-goals

- Changes to `prompts/system.md` or any shared prompt templates
- Changes to the RLM engine API
- Markdown rendering for the rest of the answer text
- Citation support in the TUI, CLI, or Barsoom example
- Persisting citation metadata in the session/exchange model
