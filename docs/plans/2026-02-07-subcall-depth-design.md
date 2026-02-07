# Subcall Instruction Depth Recovery

**Date:** 2026-02-07
**Branch:** ovid/handle-larger-repos

## Problem

The structured scout/search/analyze prompt pattern (commit 7e50b7b) is 27-42%
faster with verified citations, but the sub-LLM produces shallower analysis than
the old approach. Root cause: the example `llm_query()` instructions in the
system prompt use phrasing like "with brief quotes" and "List key events", which
steers the code-generating LLM toward writing concise subcall instructions.

## Changes

All changes are in `prompts/system.md`.

### 1. Add subcall instruction quality guidance (after Phase 3 heading)

> **Subcall instruction quality**: Your `llm_query()` instruction determines
> the depth of analysis. Ask for detailed analysis with evidence (direct
> quotes), explanations of why each finding matters, and actionable mitigations
> or recommendations. Avoid asking for "concise" or "brief" output — depth and
> evidence are more valuable than brevity.

### 2. Add depth-through-quality guidance (after the above)

> **Depth through instruction quality, not additional subcalls**: Iterate freely
> to refine your search strategy, but concentrate your `llm_query()` calls.
> Gather all your evidence first, then make your subcall(s) in one go. Don't
> make follow-up subcalls to "dig deeper" on results from a previous subcall —
> instead, write a more specific initial instruction that asks for the depth you
> need upfront.

### 3. Update example instructions

| Location | Old | New |
|----------|-----|-----|
| Line 93 (single batch) | "List key events...with brief quotes..." | "Analyze key events...provide direct quotes as evidence, explain its significance..." |
| Line 102 (multi-batch) | "List key events...with quotes." | "Analyze key events...with direct quotes as evidence. Explain the significance..." |
| Line 106 (synthesis) | "Synthesize...single chronological summary. Deduplicate..." | "Synthesize...single chronological analysis. Deduplicate...explain significance...note contradictions..." |

## Non-goals

- Citation verification changes (Recommendation 2 — future work)
- Snippet extraction parameter tuning (Recommendation 4 — future work)
