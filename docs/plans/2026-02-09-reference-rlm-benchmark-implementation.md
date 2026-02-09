# Reference RLM Benchmark Runner — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create `oolong/run_reference_implementation.py` that runs OOLONG and OOLONG-Pairs benchmarks against the paper's reference RLM (`rlm/`), outputting results in the same CSV format as Shesha's runner for side-by-side comparison.

**Architecture:** Mirror `run_oolong_and_pairs.py` structure, replacing the Shesha call layer with `rlm.RLM.completion()`. Import scoring functions from the existing runner. Own logging to avoid collision.

**Tech Stack:** Python, reference `rlm` package (local), pandas, datasets, matplotlib

**Design doc:** `docs/plans/2026-02-09-reference-rlm-benchmark-design.md`

---

### Task 1: Install reference RLM package and verify import

**Files:**
- None created/modified

**Step 1: Install the reference RLM package in editable mode**

Run: `pip install -e rlm/`
Expected: Successful installation of `rlms` package

**Step 2: Verify the import works**

Run: `python -c "from rlm import RLM; print('OK:', RLM)"`
Expected: `OK: <class 'rlm.core.rlm.RLM'>`

**Step 3: Verify scoring imports from existing runner work**

Run: `python -c "import sys; sys.path.insert(0, 'oolong'); from run_oolong_and_pairs import score_oolong, f1_score, parse_pairs_from_text, make_pairs_tasks, plot_results, LABELS, CTX_LENS, CACHE_PATH, _human_len, _parse_labeled_context, _build_user_stats; print('OK: all imports')"`
Expected: `OK: all imports`

---

### Task 2: Create the script with imports, constants, and helpers

**Files:**
- Create: `oolong/run_reference_implementation.py`

**Step 1: Write the file with imports, constants, logging, arg parsing, model mapping, and token extraction**

```python
#!/usr/bin/env python3
"""OOLONG & OOLONG-Pairs benchmark using the paper's reference RLM.

Runs the same benchmarks as run_oolong_and_pairs.py but against the reference
RLM implementation in rlm/ instead of Shesha.  Outputs results in the same CSV
format for side-by-side comparison.

Environment variables:

  SHESHA_API_KEY        API key for the LLM provider (required).
  SHESHA_MODEL          LLM model (default: gpt-5.2, overridden by --model).
  MAX_WINDOWS_PER_LEN   Context windows per length (default: 1).
  REF_MAX_ITER          Max RLM iterations (default: 30).
  PLOT_ONLY             Set to 1 to regenerate plot from existing CSV.

Usage:

  python oolong/run_reference_implementation.py
  python oolong/run_reference_implementation.py --model openai/gpt-4o
  PLOT_ONLY=1 python oolong/run_reference_implementation.py
"""

import argparse
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — sibling script + reference RLM package
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

sys.path.insert(0, str(SCRIPT_DIR))  # for run_oolong_and_pairs
sys.path.insert(0, str(PROJECT_ROOT / "rlm"))  # for rlm package

import pandas as pd  # noqa: E402
from datasets import load_dataset  # noqa: E402
from rlm import RLM  # noqa: E402
from run_oolong_and_pairs import (  # noqa: E402
    CACHE_PATH,
    CTX_LENS,
    _build_user_stats,
    _human_len,
    _parse_labeled_context,
    f1_score,
    make_pairs_tasks,
    parse_pairs_from_text,
    plot_results,
    score_oolong,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CSV_PATH = SCRIPT_DIR / "oolong_ref_results.csv"
PLOT_PATH = SCRIPT_DIR / "oolong_ref_scaling.png"
LOG_PATH = SCRIPT_DIR / "ref-last-run.log"

BACKEND_MAP = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "gemini",
    "azure": "azure_openai",
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log = logging.getLogger("oolong_ref")
log.addHandler(logging.NullHandler())


def _setup_logging() -> None:
    """Attach file and console handlers."""
    log.setLevel(logging.DEBUG)

    fh = logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s"))
    log.addHandler(fh)

    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.ERROR)
    ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    log.addHandler(ch)


def status(msg: str) -> None:
    """Print minimal progress to stdout and log it."""
    print(msg, flush=True)
    log.info(msg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OOLONG & OOLONG-Pairs benchmark using reference RLM.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model to use (overrides SHESHA_MODEL, default: gpt-5.2)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Accepted for CLI parity — no-op for reference RLM.",
    )
    return parser.parse_args()


def _parse_model(model_arg: str) -> tuple[str, str]:
    """Split LiteLLM-style 'provider/model' into (backend, model_name)."""
    if "/" in model_arg:
        backend, model_name = model_arg.split("/", 1)
    else:
        backend, model_name = "openai", model_arg
    backend = BACKEND_MAP.get(backend, backend)
    return backend, model_name


def _extract_total_tokens(usage_summary) -> int:
    """Sum input + output tokens across all models in a UsageSummary."""
    return sum(
        u.total_input_tokens + u.total_output_tokens
        for u in usage_summary.model_usage_summaries.values()
    )


def call_ref_rlm(
    question: str, context: str, rlm_instance: RLM,
) -> tuple[str, int]:
    """Run a reference RLM query. Returns (answer_string, total_tokens)."""
    result = rlm_instance.completion(prompt=context, root_prompt=question)
    answer = result.response
    if not isinstance(answer, str):
        log.debug(
            "RLM returned non-string answer (%s), coercing: %r",
            type(answer).__name__, answer,
        )
        answer = str(answer)
    tokens = _extract_total_tokens(result.usage_summary)
    return answer, tokens
```

**Step 2: Verify the file parses without errors**

Run: `python -c "import sys; sys.path.insert(0, 'oolong'); import run_reference_implementation; print('OK')"`
Expected: `OK`

**Step 3: Verify lint passes**

Run: `ruff check oolong/run_reference_implementation.py`
Expected: No errors (or only expected noqa-suppressed E402s)

---

### Task 3: Write the main() function and entry point

**Files:**
- Modify: `oolong/run_reference_implementation.py`

**Step 1: Append the main() function and entry point to the file**

Add the following after the `call_ref_rlm` function:

```python
# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    _setup_logging()
    args = _parse_args()

    # Re-plot only mode
    if os.getenv("PLOT_ONLY") == "1":
        if CSV_PATH.exists():
            plot_results(CSV_PATH, PLOT_PATH)
            status(f"Wrote {PLOT_PATH}")
        else:
            status(f"No CSV found at {CSV_PATH}")
        return

    t_start = time.monotonic()
    model = args.model or os.getenv("SHESHA_MODEL", "gpt-5.2")
    max_win = int(os.getenv("MAX_WINDOWS_PER_LEN", "1"))
    max_iter = int(os.getenv("REF_MAX_ITER", "30"))

    backend, model_name = _parse_model(model)
    log.info("=== Reference RLM Benchmark Run ===")
    log.info(
        "backend=%s  model=%s  max_windows=%d  max_iter=%d",
        backend, model_name, max_win, max_iter,
    )
    status(f"backend={backend}  model={model_name}")
    status(f"max_windows={max_win}  max_iter={max_iter}")

    # --- Reference RLM setup ---
    api_key = os.getenv("SHESHA_API_KEY")
    ref = RLM(
        backend=backend,
        backend_kwargs={"api_key": api_key, "model_name": model_name},
        environment="local",
        max_iterations=max_iter,
    )
    log.info("Reference RLM initialized")

    # --- Load dataset (cached locally after first fetch) ---
    if CACHE_PATH.exists():
        status("Loading cached trec_coarse data...")
        trec = pd.read_parquet(CACHE_PATH)
        trec = trec[trec["context_len"].isin(CTX_LENS)]
        log.info("Loaded from cache: %s (%d rows)", CACHE_PATH, len(trec))
    else:
        status("Fetching oolongbench/oolong-synth (first run, will cache)...")
        ds = load_dataset("oolongbench/oolong-synth")
        df = pd.DataFrame(ds["validation"])
        trec = df[df["dataset"].str.contains("trec", case=False, na=False)].copy()
        trec.to_parquet(CACHE_PATH)
        log.info("Cached %d trec_coarse rows to %s", len(trec), CACHE_PATH)
        trec = trec[trec["context_len"].isin(CTX_LENS)]

    log.info("trec_coarse rows after length filter: %d", len(trec))
    log.info("Context lengths present: %s", sorted(trec["context_len"].unique()))
    status(
        f"Loaded {len(trec)} trec_coarse rows, "
        f"{trec['context_len'].nunique()} context lengths"
    )

    if trec.empty:
        status("ERROR: no trec_coarse rows found")
        return

    # --- Group by context window ---
    groups = list(trec.groupby(["context_len", "context_window_id"]))
    by_len: dict[int, list] = {}
    for (ctx_len, ctx_id), g in groups:
        by_len.setdefault(ctx_len, []).append((ctx_id, g))

    results: list[dict] = []

    # --- Count total steps for progress reporting ---
    total_steps = 0
    for ctx_len in CTX_LENS:
        windows = by_len.get(ctx_len, [])[:max_win]
        for _, g in windows:
            total_steps += len(g)  # oolong questions
            total_steps += 20      # pairs tasks per window
    step = 0
    step_times: list[float] = []
    cumulative_scores: list[float] = []
    cumulative_tokens: int = 0

    def _fmt_tokens(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.0f}K"
        return str(n)

    def _progress(
        label: str, ctx: str, score: float, dur: float, tokens: int = 0,
    ) -> None:
        nonlocal step, cumulative_tokens
        step += 1
        step_times.append(dur)
        cumulative_tokens += tokens
        avg = sum(step_times) / len(step_times)
        eta_s = avg * (total_steps - step)
        eta_m, eta_sec = divmod(int(eta_s), 60)
        eta_h, eta_m = divmod(eta_m, 60)
        ts = datetime.now().strftime("%H:%M:%S")
        eta_str = f"{eta_h}h{eta_m:02d}m" if eta_h else f"{eta_m}m{eta_sec:02d}s"

        if "ool" in label:
            cumulative_scores.append(score)
        n_scored = len(cumulative_scores)
        if n_scored > 0:
            pct = 100 * sum(cumulative_scores) / n_scored
            acc_str = f"acc={pct:.0f}%({n_scored})"
        else:
            acc_str = ""

        tok_str = f"tok={_fmt_tokens(cumulative_tokens)}" if cumulative_tokens else ""

        print(
            f"  [{ts}] {step}/{total_steps}  {ctx}  {label}  "
            f"score={score:.2f}  ({dur:.0f}s)  "
            f"{acc_str}  {tok_str}  ETA {eta_str}",
            flush=True,
        )

    status(f"Total steps: {total_steps}")

    try:
        for ctx_len in CTX_LENS:
            windows = by_len.get(ctx_len, [])
            if not windows:
                continue
            windows = windows[:max_win]
            hl = _human_len(ctx_len)

            for w_idx, (ctx_id, g) in enumerate(windows, 1):
                t_win = time.monotonic()
                n_oolong = len(g)
                log.info(
                    "--- %s window %d/%d (id=%s, %d oolong questions) ---",
                    hl, w_idx, len(windows), ctx_id, n_oolong,
                )

                context = g["context_window_text"].iloc[0]
                context_labeled = g["context_window_text_with_labels"].iloc[0]

                # --- OOLONG ---
                ool_scores: list[float] = []

                for _, row in g.iterrows():
                    t_q = time.monotonic()
                    try:
                        pred, toks = call_ref_rlm(
                            row["question"], context, ref,
                        )
                        s = score_oolong(pred, row["answer"])
                        ool_scores.append(s)
                        results.append({
                            "benchmark": "oolong",
                            "model": f"ref:{model}",
                            "context_len": ctx_len,
                            "context_window_id": ctx_id,
                            "task_id": row["id"],
                            "score": s,
                        })
                        _progress("ref:ool", hl, s, time.monotonic() - t_q, toks)
                        log.debug(
                            "oolong ref id=%s score=%.1f gold=%r pred=%r",
                            row["id"], s, row["answer"], pred[:200],
                        )
                    except Exception:
                        _progress("ref:ool", hl, 0.0, time.monotonic() - t_q)
                        log.error(
                            "oolong ref id=%s FAILED:\n%s",
                            row["id"], traceback.format_exc(),
                        )

                # --- OOLONG-PAIRS ---
                entries = _parse_labeled_context(context_labeled)
                user_stats = _build_user_stats(entries)
                log.info(
                    "Labeled context: %d entries, %d users",
                    len(entries), len(user_stats),
                )
                pairs_tasks = make_pairs_tasks(user_stats)

                pairs_scores: list[float] = []

                for t_idx, (qtext, gold_pairs) in enumerate(pairs_tasks, 1):
                    t_q = time.monotonic()
                    try:
                        pred, toks = call_ref_rlm(qtext, context, ref)
                        pred_pairs = parse_pairs_from_text(pred)
                        s = f1_score(pred_pairs, gold_pairs)
                        pairs_scores.append(s)
                        results.append({
                            "benchmark": "oolong_pairs",
                            "model": f"ref:{model}",
                            "context_len": ctx_len,
                            "context_window_id": ctx_id,
                            "task_id": f"pairs_{t_idx}",
                            "score": s,
                        })
                        _progress(
                            "ref:pairs", hl, s, time.monotonic() - t_q, toks,
                        )
                        log.debug(
                            "pairs ref t=%d f1=%.3f |pred|=%d |gold|=%d",
                            t_idx, s, len(pred_pairs), len(gold_pairs),
                        )
                    except Exception:
                        _progress("ref:pairs", hl, 0.0, time.monotonic() - t_q)
                        log.error(
                            "pairs ref t=%d FAILED:\n%s",
                            t_idx, traceback.format_exc(),
                        )

                # --- Per-window status line ---
                elapsed = time.monotonic() - t_win
                parts = [f"  {hl:>4s} [{w_idx}/{len(windows)}]"]
                if ool_scores:
                    avg = 100 * sum(ool_scores) / len(ool_scores)
                    parts.append(f"ref:ool={avg:.0f}%")
                if pairs_scores:
                    avg = 100 * sum(pairs_scores) / len(pairs_scores)
                    parts.append(f"ref:pairs={avg:.0f}%")
                parts.append(f"({elapsed:.0f}s)")
                status("  ".join(parts))

    except KeyboardInterrupt:
        status("\nInterrupted — saving partial results")

    # --- Save & plot ---
    if results:
        out = pd.DataFrame(results)
        out.to_csv(CSV_PATH, index=False)
        status(f"Wrote {CSV_PATH} ({len(out)} rows)")

        try:
            plot_results(CSV_PATH, PLOT_PATH)
            status(f"Wrote {PLOT_PATH}")
        except Exception:
            log.error("Plotting failed:\n%s", traceback.format_exc())
    else:
        status("No results collected")

    elapsed_total = time.monotonic() - t_start
    status(f"Done in {elapsed_total:.0f}s  log: {LOG_PATH}")


if __name__ == "__main__":
    main()
```

**Step 2: Verify the complete file parses and imports correctly**

Run: `python -c "import sys; sys.path.insert(0, 'oolong'); import run_reference_implementation; print('OK')"`
Expected: `OK`

**Step 3: Verify lint passes on the complete file**

Run: `ruff check oolong/run_reference_implementation.py`
Expected: No errors

**Step 4: Verify --help works**

Run: `python oolong/run_reference_implementation.py --help`
Expected: Shows usage with --model and --fast flags

**Step 5: Commit**

```bash
git add oolong/run_reference_implementation.py
git commit -m "feat: add reference RLM benchmark runner for OOLONG comparison"
```

---

### Task 4: Smoke test with PLOT_ONLY mode

This validates the script's plumbing (arg parsing, logging, dataset loading, plot generation) without making any API calls.

**Files:**
- None modified

**Step 1: Verify PLOT_ONLY mode handles missing CSV gracefully**

Run: `PLOT_ONLY=1 python oolong/run_reference_implementation.py`
Expected: `No CSV found at .../oolong/oolong_ref_results.csv`

**Step 2: Create a minimal test CSV and verify plot generation**

Run:
```bash
python -c "
import pandas as pd
df = pd.DataFrame([
    {'benchmark': 'oolong', 'model': 'ref:test', 'context_len': 8192, 'context_window_id': 'w1', 'task_id': 't1', 'score': 0.5},
    {'benchmark': 'oolong', 'model': 'ref:test', 'context_len': 16384, 'context_window_id': 'w1', 'task_id': 't1', 'score': 0.3},
])
df.to_csv('oolong/oolong_ref_results.csv', index=False)
"
PLOT_ONLY=1 python oolong/run_reference_implementation.py
```
Expected: `Wrote .../oolong/oolong_ref_scaling.png`

**Step 3: Verify the plot and log files were created**

Run: `ls -la oolong/oolong_ref_scaling.png oolong/ref-last-run.log`
Expected: Both files exist with recent timestamps

**Step 4: Clean up test artifacts**

Run: `rm -f oolong/oolong_ref_results.csv oolong/oolong_ref_scaling.png oolong/ref-last-run.log`

---

### Task 5: Live benchmark run

This is the real validation — run the benchmark against the reference RLM with an actual API key.

**Files:**
- None modified

**Step 1: Run the benchmark (8K context, 1 window)**

Run:
```bash
export SHESHA_API_KEY="<your-api-key>"
python oolong/run_reference_implementation.py --model openai/gpt-5-mini
```
Expected: Progress output showing ref:ool and ref:pairs scores, then CSV + plot written.

**Step 2: Verify output files exist and have correct format**

Run:
```bash
head -5 oolong/oolong_ref_results.csv
```
Expected: CSV with columns `benchmark,model,context_len,context_window_id,task_id,score` and model values starting with `ref:`.

**Step 3: Check the log for traces**

Run: `wc -l oolong/ref-last-run.log`
Expected: Non-trivial number of log lines (100+)

**Step 4: Compare with Shesha results (if available)**

If `oolong/oolong_results.csv` exists from a prior Shesha run:
```bash
python -c "
import pandas as pd
ref = pd.read_csv('oolong/oolong_ref_results.csv')
shesha = pd.read_csv('oolong/oolong_results.csv')
print('=== Reference RLM ===')
print(ref.groupby('benchmark')['score'].agg(['mean', 'count']))
print()
print('=== Shesha RLM ===')
print(shesha.groupby('benchmark')['score'].agg(['mean', 'count']))
"
```
Expected: Side-by-side comparison of mean scores.

---

### Task 6: Final commit with any fixes from live testing

**Files:**
- Modify: `oolong/run_reference_implementation.py` (if any fixes needed)

**Step 1: Fix any issues discovered during live testing**

Apply fixes as needed.

**Step 2: Run lint one final time**

Run: `ruff check oolong/run_reference_implementation.py && ruff format --check oolong/run_reference_implementation.py`
Expected: No errors

**Step 3: Commit fixes (if any)**

```bash
git add oolong/run_reference_implementation.py
git commit -m "fix: address issues from live benchmark testing"
```
