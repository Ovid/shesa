# Paper Sidebar Design

## Problem

The paper bar at the top of the web interface shows papers as chips labeled with raw arXiv IDs (e.g. `2310.20260v1`). These are meaningless to users. With 30 papers in a topic, most chips are off-screen and require blind clicking to discover what each paper is. The useful metadata (title, authors, date) only appears after clicking.

## Design

### Sidebar Paper List

Remove the top `PaperBar` entirely. Papers move into the `TopicSidebar` as a collapsible tree under each topic.

Each topic row gains a chevron toggle (`▶` / `▼`), always visible:

```
▼ chess         27/30 · 6.4 MB
  ☑ On the complexity of Dark Chinese Ch...
  ☑ Monte Carlo Tree Search for Asymmetr...
  ☑ AlphaZero: Shedding New Light on Ch...
  ☐ Deep Learning for Real-Time Atari Ga...
  ...
```

- **Title only** per row, truncated with ellipsis to fit sidebar width
- **Hover tooltip** shows full title + first author + year
- **Checkboxes** for selection — all checked by default
- Topic header shows `selected/total` count when papers are deselected (e.g. `27/30`)
- **All / None** toggle at the top of the expanded paper list

### Click Interactions

Two distinct click targets per paper row:

- **Checkbox** (left): toggles selection. No side effects.
- **Title text** (right): opens paper detail view in the main content area.

### Paper Detail View

When a paper title is clicked, the main area shows the full detail instead of the chat:

- Full title, authors, abstract
- Category, date, arXiv link
- Remove button, Back button
- Chat input hidden while detail view is open
- Sidebar stays visible and interactive for clicking through papers

Reuses the existing `PaperDetail` component, rendered full-width.

### Selection & Query Integration

- Selection state: `Set<string>` of arXiv IDs, stored in `App` component
- Default: all papers selected when topic loaded
- Ephemeral: resets to "all" on topic switch or reload
- Selected IDs sent with query; if all selected, backend behaves as today (backwards compatible)
- Backend query endpoint gains optional `paper_ids: string[]` parameter

### Structural Changes

| Component | Change |
|-----------|--------|
| `PaperBar` | **Deleted** |
| `PaperDetail` | Kept, rendered in main area (replaces chat when active) |
| `TopicSidebar` | Gains paper list, checkboxes, collapsible tree, paper click/selection events |
| `App.tsx` | Adds `selectedPapers` and `viewingPaper` state, conditional rendering |
| Backend query endpoint | Adds optional `paper_ids` filter parameter |

No new components created.
