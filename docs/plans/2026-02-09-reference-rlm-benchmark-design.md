# Design: Reference RLM Benchmark Runner

**Date:** 2026-02-09
**File:** `oolong/run_reference_implementation.py`

## Purpose

Run the OOLONG and OOLONG-Pairs benchmarks against the paper's reference RLM
implementation (`rlm/` directory) to produce results in the same CSV format as
Shesha's `run_oolong_and_pairs.py`. This enables direct side-by-side comparison
to determine whether poor OOLONG scores are caused by the test harness or by
Shesha's RLM implementation.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Environment | Local REPL | Simplest, no Docker, fastest results |
| Scope | Both OOLONG + OOLONG-Pairs | Full parity for complete comparison |
| Scoring code | Import from `run_oolong_and_pairs` | Guarantees identical scoring, DRY |
| Model config | Same defaults + `--model` flag | Apples-to-apples comparison by default |
| Output files | Separate CSV/PNG/log | No risk of overwriting Shesha results |
| RLM lifecycle | One instance for entire run | Each `completion()` call is independent |

## Architecture

### Call Layer Mapping

**Shesha (existing):**
```python
sh = Shesha(config=cfg)
project = sh.create_project(name)
project.upload("context.txt")
result = project.query(question)
answer, tokens = result.answer, result.token_usage.total_tokens
```

**Reference RLM (new):**
```python
ref = RLM(
    backend="openai",
    backend_kwargs={"api_key": api_key, "model_name": model_name},
    environment="local",
    max_iterations=max_iter,
)
result = ref.completion(prompt=context_text, root_prompt=question)
answer = result.response
tokens = sum(
    u.total_input_tokens + u.total_output_tokens
    for u in result.usage_summary.model_usage_summaries.values()
)
```

### Model Name Mapping

The `--model` flag uses LiteLLM format (`provider/model` or bare `model`). The
reference RLM uses separate `backend` + `model_name` parameters.

```python
if "/" in model_arg:
    backend, model_name = model_arg.split("/", 1)
else:
    backend, model_name = "openai", model_arg

BACKEND_MAP = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "gemini",
    "azure": "azure_openai",
}
backend = BACKEND_MAP.get(backend, backend)
```

## Import Path Handling

Both `run_oolong_and_pairs.py` and `run_reference_implementation.py` are sibling
scripts in `oolong/` — there is no `__init__.py` (not a package). The reference
RLM package lives at `rlm/rlm/` and may or may not be pip-installed.

**Solution:** Add both directories to `sys.path` at the top of the file:

```python
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

sys.path.insert(0, str(SCRIPT_DIR))       # for run_oolong_and_pairs
sys.path.insert(0, str(PROJECT_ROOT / "rlm"))  # for rlm package
```

Then import normally:
```python
from rlm import RLM
from run_oolong_and_pairs import (
    score_oolong, f1_score, parse_pairs_from_text,
    make_pairs_tasks, _parse_labeled_context, _build_user_stats,
    plot_results, LABELS, CTX_LENS, CACHE_PATH, _human_len,
)
```

**Side effect note:** Importing `run_oolong_and_pairs` triggers
`matplotlib.use("Agg")` at module level. This is harmless (we want the Agg
backend anyway).

## Logging

The imported `status()` function uses the shared `oolong` logger, whose file
handler points to `last-run.log`. To avoid collision:

- Define our own `log` logger (`logging.getLogger("oolong_ref")`) and our own
  `status()` function that uses it.
- Do NOT import `status` or `_setup_logging` from `run_oolong_and_pairs`.
- Set up a file handler pointing to `ref-last-run.log`.

## File Layout

```
oolong/run_reference_implementation.py

Imports:
  - from rlm import RLM
  - from run_oolong_and_pairs import (
      score_oolong, f1_score, parse_pairs_from_text,
      make_pairs_tasks, _parse_labeled_context, _build_user_stats,
      plot_results, LABELS, CTX_LENS, CACHE_PATH, _human_len,
  )
  - stdlib: argparse, os, sys, time, logging, traceback
  - pandas, datasets

Constants:
  - CSV_PATH  = SCRIPT_DIR / "oolong_ref_results.csv"
  - PLOT_PATH = SCRIPT_DIR / "oolong_ref_scaling.png"
  - LOG_PATH  = SCRIPT_DIR / "ref-last-run.log"

Functions:
  - _setup_logging()           — own logger to ref-last-run.log
  - status(msg)                — own status function using oolong_ref logger
  - _parse_args()              — --model, --fast (no-op for reference)
  - _extract_total_tokens(us)  — sum input+output across all models
  - call_ref_rlm(question, context, rlm_instance) -> (answer, tokens)
  - main()                     — mirrors run_oolong_and_pairs.main()
```

### main() Structure

1. Parse args, setup logging (to `ref-last-run.log`)
2. Load dataset (reuses same parquet cache at `CACHE_PATH`)
3. Create single `RLM` instance
4. Loop: context lengths → windows → oolong questions + pairs tasks
5. Save CSV (`oolong_ref_results.csv`), generate plot (`oolong_ref_scaling.png`)

The main loop body is structurally identical to the existing runner. The CSV
format is identical: `benchmark, model, context_len, context_window_id, task_id,
score`. Model values use `ref:` prefix (e.g., `ref:gpt-5.2`).

### Environment Variables

| Var | Meaning | Default |
|-----|---------|---------|
| `SHESHA_API_KEY` | API key for LLM provider | required |
| `SHESHA_MODEL` | Default model (overridden by `--model`) | `gpt-5.2` |
| `MAX_WINDOWS_PER_LEN` | Windows to evaluate per context length | `1` |
| `REF_MAX_ITER` | Max RLM iterations | `30` (reference default) |
| `PLOT_ONLY` | Skip eval, regenerate plot from CSV | `0` |

### CLI

```bash
# Default: reference RLM with gpt-5.2
python oolong/run_reference_implementation.py

# Specific model
python oolong/run_reference_implementation.py --model openai/gpt-4o

# Re-plot
PLOT_ONLY=1 python oolong/run_reference_implementation.py
```

## Out of Scope

- **`--fast` flag** — Accepted for CLI parity but is a no-op. The reference
  RLM's `llm_query_batched()` is always concurrent.
- **Base mode** — No `RUN_BASE` env var. This runner only tests the reference
  RLM. The existing runner covers base mode.
- **Docker** — Local REPL only.
- **RLMLogger** — No trajectory logging. Progress output + CSV is sufficient.
  `verbose=False` to avoid flooding stdout.
- **Combined plotting** — Separate output files. Merging CSVs for a combined
  plot is a separate step if needed.
- **Shesha imports** — This file does NOT import from `shesha`. Only from
  `run_oolong_and_pairs` (scoring) and `rlm` (reference package).
