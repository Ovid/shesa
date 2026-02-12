# Citation Verification Upgrade Design

## Problem

The citation checker only verifies against the arXiv API. Citations from journals, conferences, books, and other non-arXiv sources are immediately marked `UNRESOLVED` — inflating noise and making legitimate papers look suspicious. Additionally, title changes between paper versions cause false positives, and there's no check for whether a citation is topically relevant to the citing paper.

## Goals

1. **Verify more citations** — add free, keyless external databases (CrossRef, OpenAlex, Semantic Scholar)
2. **Reduce false positives** — fuzzy title matching with LLM fallback for ambiguous cases
3. **Detect topical irrelevance** — LLM-based batch check for citations that exist but seem out of place
4. **Zero friction** — no API keys required; polite-pool email collected via optional browser modal
5. **Respect rate limits** — honor each API's published guidelines

## Architecture

### Cascading Verification Pipeline

```
Citation Extracted
    |
    +-- Has arXiv ID? --> ArxivVerifier
    |                      |
    |                      +-- NOT_FOUND? --> fall through to title search
    |
    +-- Has DOI? --> CrossRefVerifier (resolve DOI -> metadata -> compare)
    |
    +-- Title only? --> Title Search Chain:
                         1. OpenAlex (fastest, broadest)
                         2. Semantic Scholar (good fuzzy search)
                         3. CrossRef (title query)
                         |
                         +-- Best match found? --> Fuzzy title match
                                                    |
                                                    +-- High confidence -> VERIFIED
                                                    +-- Ambiguous -> LLM judgment
                                                    +-- No match -> UNRESOLVED
```

Each verifier implements the existing `CitationVerifier` Protocol. They are tried in order; we stop at the first confident result.

### New Verifiers

**CrossRefVerifier:**
- Resolves DOIs via `https://api.crossref.org/works/{doi}`
- Title search via `https://api.crossref.org/works?query.title={title}`
- Polite pool: `User-Agent: shesha-citation-checker/1.0 (mailto:{user_email})`

**OpenAlexVerifier:**
- Title search via `https://api.openalex.org/works?search={title}`
- Polite pool: `mailto={user_email}` query parameter
- Fastest and broadest coverage (~250M+ works)

**SemanticScholarVerifier:**
- Title search via `https://api.semanticscholar.org/graph/v1/paper/search?query={title}`
- Free tier: 1 req/sec without API key
- Good at fuzzy title matching

### Verification Statuses

Extending the current `VerificationStatus` enum:

| Status | Meaning | Severity |
|--------|---------|----------|
| `VERIFIED` | Found on arXiv, title matches | None (success) |
| `VERIFIED_EXTERNAL` | Found on CrossRef/OpenAlex/S2, title matches | None (success) |
| `MISMATCH` | Found but title differs significantly | `"warning"` |
| `NOT_FOUND` | ID present but paper not in any database | `"error"` |
| `UNRESOLVED` | No identifiers, title search found nothing | None (neutral) |
| `TOPICALLY_UNRELATED` | Exists but flagged by LLM as irrelevant | `"warning"` |

## Fuzzy Title Matching

Three-tier approach:

**Tier 1 — Exact (current, fast):**
Normalize both titles (strip LaTeX commands, punctuation, lowercase, collapse whitespace). Match if equal or one contains the other.

**Tier 2 — Fuzzy (new, fast):**
Jaccard similarity on word sets (handles reordering, subtitle additions):
- >= 0.85 -> `VERIFIED`
- < 0.50 -> no match
- 0.50 - 0.85 -> ambiguous, go to Tier 3

**Tier 3 — LLM judgment (new, only for ambiguous cases):**

```
Cited title: "Learning Chess from Text"
Found title: "LEAP: Learning to Play Chess from Textbooks"
Found abstract: "..."

Are these the same paper? Respond YES or NO with a one-sentence reason.
```

Uses the user's configured LLM model. Only fires for the ambiguous fuzzy band — small fraction of citations in practice.

## Topical Relevance Check

After existence verification, a batched LLM call per paper checks whether verified citations make sense in context.

**Prompt structure:**

```
Paper title: "Abiogenesis and Early RNA World Hypotheses"
Paper abstract: "..."

For each citation below, rate whether it is topically relevant
to this paper. Respond with a JSON array of objects with
"key", "relevant" (boolean), and "reason" (one sentence).

Citations:
1. key: "smith2023", title: "RNA Catalysis in Prebiotic Chemistry"
2. key: "jones2021", title: "Sentiment Analysis of Victorian Novels"
```

**Design choices:**
- Batched per paper (one LLM call per paper, not per citation) to keep cost proportional to papers, not references
- Only runs on citations that passed existence verification
- Generous threshold — interdisciplinary citations are legitimate; only flag clearly unrelated ones
- Uses the user's configured LLM model
- Always runs as part of the citation check pipeline

## Rate Limiting

All external APIs get polite rate limiting with backoff on 429 / `Retry-After`:

| API | Default Rate | With Polite Email |
|-----|-------------|-------------------|
| arXiv | 1 req/3sec (existing) | N/A |
| CrossRef | 1 req/sec | Up to 50 req/sec (we stay at ~2 req/sec) |
| OpenAlex | 1 req/sec | Up to 10 req/sec (we stay at ~2 req/sec) |
| Semantic Scholar | 1 req/sec | N/A (key required for higher) |

Verification runs in parallel across papers but sequential per-API to respect limits.

## Email Collection for Polite Pool

**Flow:**
1. First citation check with no email in `localStorage` -> modal appears
2. Modal explains: "CrossRef and OpenAlex offer faster access if you provide an email address. It's used only as a courtesy identifier in API requests — they never contact you. You can skip this, but checks will be slower."
3. User enters email -> saved to `localStorage`, sent to backend with citation check requests
4. User declines -> proceed without it, use conservative rate limits
5. New browser / cleared storage -> modal appears again

**Backend handling:**
- Email passed as optional parameter in the `check_citations` WebSocket message
- Backend includes it in API request headers when present
- Never stored server-side; only lives in browser `localStorage`

## UI Changes

### Report Groups

**Group 1 — "All citations verified" (green checkmark):**
- Includes papers verified via any source (arXiv or external)
- Source badge per citation: `arXiv` / `CrossRef` / `OpenAlex` / `S2`

**Group 2 — "Some citations could not be checked" (neutral dash):**
- Only for citations with no identifiers AND title search found nothing
- Label changes to: `"N verified, M not found in databases"` (we tried, not skipped)

**Group 3 — "Potential issues detected" (warning triangle):**
- Title mismatches (yellow, with "cited as" vs "found as")
- Non-existent IDs (red)
- LLM-tell phrases (purple, with line numbers)
- Topically unrelated citations (orange, with LLM's one-sentence reason)

### Progress Indicator

Updated to show verification phase:
- "Checking arXiv..."
- "Searching CrossRef..."
- "Searching OpenAlex..."
- "Checking relevance..."

### Topic Selection Fix

Papers in a topic default to **selected** when clicking the topic (currently they start unselected).

## What Doesn't Change

- Citation extraction from .bib/.bbl/text (already solid)
- LLM-tell phrase detection
- The `CitationVerifier` Protocol — new verifiers just implement it
- WebSocket message flow structure (`check_citations` -> `citation_progress` -> `citation_report`)
- Docker sandbox (citation checking doesn't use it)
