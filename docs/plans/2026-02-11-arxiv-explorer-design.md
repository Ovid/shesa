# arXiv Explorer Design

## Overview

`examples/arxiv.py` — an interactive CLI for searching arXiv, loading papers
into Shesha, and exploring them conversationally. Secondary capability:
structured citation checking via `/check-citations`.

**Primary use case:** Researchers (or the curious) search arXiv, load papers
into topics, and ask questions to follow their scientific curiosity — getting
answers with citations, exact quotes, and arXiv URLs.

**Secondary use case:** Detect potentially AI-generated papers through
structured citation verification and LLM-tell phrase detection.

## Dependencies

- `arxiv` Python package (v2.4.0, MIT, PyPI) — wraps arXiv API with built-in
  rate limiting (3s delay), pagination, retries
- `bibtexparser` — parse structured `.bib` files for citation extraction
- Standard Shesha API (`Shesha`, `SheshaConfig`, `Project`, `QueryResult`)
- Existing `examples/script_utils.py` for spinners, stats formatting, output

## User Flow

### Typical Session

```
$ python examples/arxiv.py --model claude-sonnet-4-20250514

Shesha arXiv Explorer
Answers are AI-generated and may contain errors. Always verify against primary sources.
Type /help for commands.

arxiv> /search quantum error correction 2025
Found 47 results. Showing 1-10:

  1. [2501.12345] "Topological Quantum Error Correction with..."
     Smith, Jones, Lee | cs.QI | 2025-01-15 | 12 pages
     https://arxiv.org/abs/2501.12345
  2. [2502.67890] "Scalable Decoding for Surface Codes..."
     Jones, Lee | cs.QI | 2025-02-03
     https://arxiv.org/abs/2502.67890
  ...

arxiv> /load 1 3 5
Loading 3 papers (source first, PDF fallback)...
  [cached]  2501.12345 - LaTeX source (with .bib)
  [new]     2503.11111 - LaTeX source (.bbl only)
  [new]     2502.99999 - PDF fallback (no source available)

arxiv> What are the key differences in decoding approaches across these papers?
[Shesha RLM loop runs, analyzing loaded papers]

arxiv> /check-citations
...
```

### Returning to Previous Work

```
arxiv> /history
Topics:
  1. quantum-error-correction    Created: Jan 15, 2025    3 papers   12.4 MB
  2. llm-hallucinations          Created: Feb 10, 2025    7 papers    8.7 MB
  3. protein-folding             Created: Feb 11, 2025    1 paper     2.1 MB
                                                          Total:     23.2 MB

arxiv> /topic quantum-error-correction
Switched to topic: quantum-error-correction (3 papers)

arxiv> /papers
Papers in "quantum-error-correction":
  1. [2501.12345] "Topological Quantum Error Correction with..."
     https://arxiv.org/abs/2501.12345
  2. [2503.11111] "Scalable Decoding for Surface Codes..."
     https://arxiv.org/abs/2503.11111
  3. [2502.99999] "A Survey of Quantum Error Correction"
     https://arxiv.org/abs/2502.99999
```

## Data Model

### Directory Structure

```
~/.shesha-arxiv/                     (or configurable via --data-dir)
├── paper-cache/                     # Central registry — avoids re-downloading
│   ├── 2501.12345/
│   │   ├── meta.json                # arXiv metadata (title, authors, date, URL, categories)
│   │   ├── source/                  # Extracted .tex/.bib/.bbl (if available)
│   │   └── paper.pdf                # PDF fallback (only if no source)
│   └── 2502.67890/
│       └── ...
└── shesha_data/                     # Shesha storage (projects = topics)
    └── projects/
        ├── 2025-01-15-quantum-error-correction/
        │   ├── docs/                # Copies of parsed papers
        │   └── traces/              # Query traces
        └── 2025-02-10-llm-hallucinations/
            └── ...
```

### Topic = Shesha Project

Each topic maps directly to a Shesha project. Papers loaded into a topic are
copied (not referenced) into the project's document storage. This means:

- Per-topic size on disk is accurate
- Deleting a topic has no effect on other topics
- The paper cache avoids redundant downloads/parsing, but each topic is
  self-contained

### Topic Naming

Each topic has a creation date (stored in metadata) and a slug name.

- Slug auto-generated from the first search query, or user-provided via
  `/topic my-topic-name`
- Creation date stored separately and displayed in `/history` as a
  human-readable date (e.g., "Jan 15, 2025")
- Internal project ID uses `YYYY-MM-DD-<slug>` for filesystem ordering

### Paper Cache

When `/load` is called:
1. Check cache for the arXiv ID
2. If cached: copy parsed document into current topic's project
3. If not cached: download from arXiv, parse, store in cache, then copy

Cache has no automatic expiry. Papers don't change after publication (only new
versions, which have distinct IDs like `2501.12345v2`).

## Search & Paper Loading

### Search Command

```
/search <query>                          # keyword search across all fields
/search --author "del maestro"           # author search
/search --cat cs.AI                      # category search
/search --cat cs.AI language models      # category + keywords
/search --recent 7                       # last 7 days (requires --cat)
```

Results paginated 10 at a time, `/more` for next page.

Each result shows arXiv ID, title, authors, category, date, page count (if
available), and the arXiv URL.

### Loading Papers

```
/load 1 3 5                              # by search result numbers
/load 2501.12345 2502.67890              # by arXiv ID directly
```

### Download Strategy

1. Try LaTeX source first via arXiv `/e-print/{id}` endpoint (~90% of papers)
2. If source available: extract tar.gz, identify .tex/.bib/.bbl files
3. If no source available: download PDF, extract text
4. Parse into Shesha `ParsedDocument` format
5. Store in paper cache, copy into current topic

### Rate Limiting

- `arxiv.Client(delay_seconds=3.0)` handles search API rate limiting
- Additional 3-second delay between download requests (source/PDF)
- Single connection at a time (per arXiv ToU)

## Citation Checking

### `/check-citations [arXiv ID]`

Runs against all papers in the current topic, or a specific paper if an ID is
provided.

### Disclaimer

Displayed **every time** the command runs, before any results:

```
DISCLAIMER: This analysis is generated using AI and automated heuristics.
It is capable of making mistakes. A flagged citation does NOT mean a paper is
fraudulent -- there may be legitimate explanations (metadata lag, preprint
title changes, version differences). Always verify findings manually before
drawing conclusions.
```

### Pipeline

**Step 1: Extract citations deterministically (code, not LLM):**
- `.bib` files: `bibtexparser` produces structured dicts with author, title,
  year, DOI fields
- `.bbl` / inline `\bibitem`: regex parsing for semi-structured extraction
- PDF text: regex for reference section, best-effort field extraction

**Step 2: Verify arXiv citations against arXiv API:**
- For any citation containing an arXiv ID (pattern: `YYMM.NNNNN`), fetch that
  ID's metadata from the arXiv API
- Compare title/authors from the citation against actual metadata
- Flag: ID exists but points to unrelated paper (hallucinated reference)
- Flag: ID does not exist on arXiv

**Step 3: Check for LLM-tell phrases (deterministic string matching):**
- "as of my last knowledge update"
- "it is important to note that"
- "I cannot provide" / "I don't have access to"
- "as of my last training" / "as of my knowledge cutoff"
- Other configurable patterns (loaded from a patterns file or hardcoded list)

**Step 4: Report:**

```
DISCLAIMER: This analysis is generated using AI and automated heuristics.
...

-- Citation Check: 2501.12345 "Topological Quantum Error..." --

Citations found: 23
  OK  21 verified (arXiv ID matches title/authors)
  ?   2 unresolved (non-arXiv, could not verify)
  X   0 mismatches

LLM-tell phrases: none detected

-- Citation Check: 2502.99999 "A Survey of..." --

Citations found: 31
  OK  28 verified
  ?   1 unresolved
  X   2 MISMATCHES:
    [14] cites 2301.04567 as "Quantum Memory Architectures"
         but actual paper is "Fluid Dynamics of Turbulent Flow"
         https://arxiv.org/abs/2301.04567
    [27] cites 2298.11111 -- arXiv ID does not exist

LLM-tell phrases found:
  Line 142: "It is important to note that these results..."
  Line 387: "As of the time of writing, no comprehensive..."  <- borderline
```

### Extensibility

The verification step sits behind a simple interface:

```python
class CitationVerifier(Protocol):
    def verify(self, citation: ExtractedCitation) -> VerificationResult: ...
```

Initial implementation: `ArxivVerifier` (arXiv API only).
Future: `CrossRefVerifier`, `SemanticScholarVerifier` can be added without
changing the extraction or reporting code.

## Command Reference

| Command | Description |
|---|---|
| `/search <query>` | Search arXiv (supports `--author`, `--cat`, `--recent`) |
| `/more` | Show next page of search results |
| `/load <nums or IDs>` | Load papers into current topic |
| `/papers` | List papers in current topic with arXiv URLs |
| `/check-citations [ID]` | Citation verification with disclaimer |
| `/topic [name]` | Switch to / create a topic |
| `/topic delete <name>` | Delete a topic and its project data |
| `/history` | List all topics with date, paper count, size on disk |
| `/help` | Show available commands |
| `/quit` | Exit |

## AI Disclaimers

### Startup Banner

```
Shesha arXiv Explorer
Answers are AI-generated and may contain errors. Always verify against primary sources.
Type /help for commands.
```

### `/check-citations` Disclaimer

Displayed before every citation check report. See Citation Checking section.

## CLI Arguments

```
python examples/arxiv.py [options]

Options:
  --model MODEL          LLM model to use (default: from env SHESHA_MODEL)
  --data-dir PATH        Data directory (default: ~/.shesha-arxiv)
  --topic NAME           Start in a specific topic
```

## Implementation Notes

- Library code lives in `src/shesha/experimental/arxiv/` — cleanly separated
  from main Shesha code, but benefits from standard packaging (mypy, ruff,
  imports all work without path hacks)
- CLI entry point remains `examples/arxiv.py`, importing from
  `shesha.experimental.arxiv`
- Pattern follows `barsoom.py` and `repo.py` examples (interactive CLI with
  slash commands, progress callbacks, stats display)
- Uses `script_utils.py` for `ThinkingSpinner`, stats formatting, output
  formatting
- `arxiv` package handles API pagination and rate limiting
- `bibtexparser` for structured `.bib` parsing
- Paper cache is a simple directory structure with JSON metadata — no database
- Topic creation auto-generates dated slug from first search query
