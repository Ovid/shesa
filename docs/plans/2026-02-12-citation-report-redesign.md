# Citation Report Redesign

## Problem

The citation check report has two issues:

1. **Display**: Results are dumped as a single plain-text string into a `<pre>` tag. The disclaimer repeats per paper, clean papers aren't separated from problematic ones, and there are no clickable links.

2. **Extraction accuracy**: The arXiv ID regex (`\d{4}\.\d{4,5}`) is too permissive. It captures DOI fragments, year/page numbers, and BibTeX keys as arXiv IDs, leading to false "does not exist" mismatches that could falsely accuse authors.

## Design

### 1. Backend: Structured JSON Response

**File: `src/shesha/experimental/web/ws.py`**

Replace the plain-text `citation_report` WebSocket message with structured JSON:

```json
{
  "type": "citation_report",
  "papers": [
    {
      "arxiv_id": "2112.02989v1",
      "title": "On the complexity of Dark Chinese Chess",
      "arxiv_url": "https://arxiv.org/abs/2112.02989v1",
      "total_citations": 2,
      "verified_count": 2,
      "unresolved_count": 0,
      "mismatch_count": 0,
      "group": "verified",
      "mismatches": [],
      "llm_phrases": []
    },
    {
      "arxiv_id": "1806.00683v2",
      "title": "Deep Pepper...",
      "arxiv_url": "https://arxiv.org/abs/1806.00683v2",
      "total_citations": 28,
      "verified_count": 8,
      "unresolved_count": 20,
      "mismatch_count": 0,
      "group": "unverifiable",
      "mismatches": [],
      "llm_phrases": []
    },
    {
      "arxiv_id": "1909.10413v1",
      "title": "Automated Chess Commentator...",
      "arxiv_url": "https://arxiv.org/abs/1909.10413v1",
      "total_citations": 33,
      "verified_count": 4,
      "unresolved_count": 23,
      "mismatch_count": 6,
      "group": "issues",
      "mismatches": [
        {
          "key": "DBLP:conf/icml/CollobertW08",
          "message": "arXiv ID 0156.13901 does not exist",
          "severity": "error",
          "arxiv_url": null
        },
        {
          "key": "DBLP:journals/corr/abs-1811-06031",
          "message": "Cites \"A Hierarchical...\" but actual is \"A Hierarchical...\"",
          "severity": "warning",
          "arxiv_url": "https://arxiv.org/abs/1811.06031v2"
        }
      ],
      "llm_phrases": [{"line": 42, "text": "It is important to note..."}]
    }
  ]
}
```

**Changes to `format_check_report()`**: Add a new `format_check_report_json()` function that returns a dict instead of a string. The plain-text formatter stays for the TUI/CLI.

### 2. Paper Grouping Logic (Three Groups)

Each paper is assigned to one of three groups:

- **`"verified"`** (green): 0 mismatches, 0 LLM-tell phrases, 0 unresolved, AND at least 1 citation extracted. Everything checks out.
- **`"unverifiable"`** (neutral): 0 mismatches, 0 LLM-tell phrases, but has unresolved (non-arXiv) citations. No problems found, just couldn't verify everything.
- **`"issues"`** (red/yellow): Any mismatches, any LLM-tell phrases, OR zero citations extracted.

### 3. Backend: Extraction Accuracy Fixes

**File: `src/shesha/experimental/arxiv/citations.py`**

**A) Stricter arXiv ID regex**

Replace:
```python
ARXIV_ID_PATTERN = re.compile(r"(?:arXiv:)?(\d{4}\.\d{4,5}(?:v\d+)?)")
```

With:
```python
# New-style arXiv IDs: YYMM.NNNNN where YY >= 07, MM is 01-12
ARXIV_ID_PATTERN = re.compile(
    r"(?:arXiv:)?((?:0[7-9]|[1-9]\d)(?:0[1-9]|1[0-2])\.\d{4,5}(?:v\d+)?)"
)
```

**B) Context requirement for text extraction**

In `extract_citations_from_text()`, only capture IDs that appear near arXiv-related tokens (`arXiv:`, `arxiv.org/abs/`, `eprint`). The `.bib`/`.bbl` extractors already have context via field names.

**C) Validate before API call**

In `ArxivVerifier.verify()`, validate the arXiv ID format before hitting the API. If the format is invalid (impossible month/year), return a distinct message: `"Not a valid arXiv identifier format (likely mis-extracted from DOI or reference key)"` with `severity: "warning"` instead of `severity: "error"`.

### 4. Backend: Mismatch Severity Classification

**File: `src/shesha/experimental/arxiv/citations.py`**

Add severity to `VerificationResult` (or compute it in the JSON formatter):

- **`"error"`**: Non-existent arXiv IDs (valid format but no paper found), real title mismatches (normalized titles genuinely differ)
- **`"warning"`**: Invalid arXiv ID format (likely mis-extracted), whitespace-only or LaTeX-formatting title differences

### 5. Frontend: Structured Report Rendering

**File: `src/shesha/experimental/web/frontend/src/components/CitationReport.tsx`**

Rewrite from `<pre>` dump to structured React components with four zones:

**Zone 1 -- Disclaimer banner (always at top)**
- Bold red text on subtle red background
- Displayed once, not repeated per paper

**Zone 2 -- Verified papers (compact list, green)**
- Header: "All citations verified (N papers)"
- Each paper: single line with checkmark, title, citation stats (`N/N verified`), arXiv link
- Hidden if no verified papers

**Zone 3 -- Unverifiable papers (compact list, neutral)**
- Header: "Some citations could not be checked (N papers)"
- Each paper: single line with info icon, title, citation stats (`N verified, M unresolved`), arXiv link
- Hidden if no unverifiable papers

**Zone 4 -- Papers with issues (detailed cards, red/yellow)**
- Header: "Potential issues detected (N papers)"
- Each paper gets a card with:
  - Title + stats + arXiv link
  - Red-styled mismatches for `severity: "error"` (non-existent valid arXiv IDs, real title mismatches)
  - Yellow-styled mismatches for `severity: "warning"` (invalid format / likely mis-extracted, whitespace/LaTeX-only diffs)
  - LLM-tell phrases if any
  - "No citations could be extracted" note for zero-citation papers
- Hidden if no issue papers

**File: `src/shesha/experimental/web/frontend/src/types/index.ts`**

Update `WSMessage` type: `citation_report` carries `papers: PaperReport[]` instead of `report: string`.

### 6. Files Changed

| File | Change |
|------|--------|
| `src/shesha/experimental/arxiv/citations.py` | Tighter regex, severity classification, JSON formatter |
| `src/shesha/experimental/arxiv/models.py` | Add `severity` field to `VerificationResult` or new dataclass |
| `src/shesha/experimental/web/ws.py` | Send structured JSON instead of plain text |
| `src/shesha/experimental/web/frontend/src/components/CitationReport.tsx` | Full rewrite to structured rendering with 4 zones |
| `src/shesha/experimental/web/frontend/src/types/index.ts` | New `PaperReport` type, updated `WSMessage` |
| `src/shesha/experimental/web/frontend/src/App.tsx` | Update state type from `string` to `PaperReport[]` |
| `tests/unit/experimental/web/test_ws_citations.py` | Update tests for new JSON format |
| `tests/unit/experimental/arxiv/test_citations.py` | Tests for stricter regex, severity classification |
