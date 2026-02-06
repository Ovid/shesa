## 1) Key architectural issues (with references), impact, and mitigations

- **Public API (`Shesha`) does too much and hard-binds infrastructure**
  - **Where:** `src/shesha/shesha.py` (`__init__`, repo ingest methods, Docker checks, storage/parser/pool/engine construction)
  - **Why problematic (impact):**
    - Tight coupling to Docker + filesystem + specific engine makes it hard to use Shesha in environments without Docker (or with alternate sandbox), hard to test (requires Docker daemon), and hard to extend (swap storage, sandbox, repo ingester, engine).
    - Violates layering: a high-level “API façade” constructs and directly depends on low-level details (`docker.from_env`, `FilesystemStorage`, `ContainerPool`, `RepoIngester`).
  - **Concrete mitigations:**
    - Introduce dependency injection and interfaces:
      - Accept `storage: StorageBackend`, `engine: RLMEngine` (or `QueryEngine` protocol), `repo_ingester`, `parser_registry`, and `sandbox_pool` (or an `ExecutorFactory`) as optional constructor args with defaults.
      - Move Docker availability checks into sandbox layer (or a `SandboxManager`) and only run them when sandbox is actually used (lazy-start).
    - Split repo features into a separate service/module: `shesha.repo.service.RepoProjectService` used by `Shesha` rather than implemented in it.

- **~~Container pool is created but not actually used by queries (design/code discrepancy)~~** — RESOLVED
  - `RLMEngine` now accepts optional `pool: ContainerPool` parameter. When provided, `query()` calls `pool.acquire()` instead of creating a throwaway executor. After each query, namespace is reset and executor is released back to the pool. `Shesha.__init__` passes its pool to the engine. Backward-compatible: without pool, engine falls back to creating/stopping its own executor.

- **~~Layering violation: `Project.query()` special-cases `FilesystemStorage`~~** — RESOLVED
  - Added `get_traces_dir()` and `list_traces()` to `StorageBackend` protocol. Changed `TraceWriter` and `IncrementalTraceWriter` to accept `StorageBackend` instead of `FilesystemStorage`. Changed `RLMEngine.query()` to accept `StorageBackend`. Removed `isinstance(self._storage, FilesystemStorage)` check from `Project.query()` — storage is now always passed directly to the engine.

- **~~Error-handling is inconsistent and bypasses the project's own exception hierarchy~~** — RESOLVED
  - Replaced all `ValueError` raises in `Shesha` API with `ProjectNotFoundError` / `RepoError`. Narrowed `_ingest_repo` broad `except Exception` to catch only `ParseError`/`NoParserError` (expected), propagating unexpected errors as `RepoIngestError`. Replaced `RuntimeError` in `Project.query()` with `EngineNotConfiguredError`. `TraceWriter` and `IncrementalTraceWriter` now raise `TraceWriteError` by default, with opt-in `suppress_errors=True` (used by engine for best-effort tracing). `executor.py` returning `ExecutionResult(status="error")` left as-is (by-design protocol boundary).

- **~~Configuration layering exists but isn't used consistently; some config values are unused~~** — RESOLVED
  - `Shesha.__init__` now uses `SheshaConfig.load()` by default, honoring the full hierarchy (defaults < file < env < kwargs). `max_traces_per_project` is plumbed from config through `RLMEngine` to `cleanup_old_traces`. `allowed_hosts` was already removed in a prior fix.

- **~~Sandbox network whitelisting is documented/configured but not enforced in code~~** — RESOLVED
  - `allowed_hosts` removed from `SheshaConfig`. SECURITY.md updated to reflect that containers have networking disabled and all LLM calls go through the host.

- **~~Sandbox runner namespace persistence~~** — PARTIALLY RESOLVED
  - Added `reset` action to runner that clears user variables while preserving builtins (FINAL, llm_query, etc.). Added `reset_namespace()` method to `ContainerExecutor`.
  - Remaining: per-process execution and OS-level timeout enforcement are not yet addressed.

- **~~Repo token handling injects secrets into clone URL (leak risk)~~** — RESOLVED
  - Replaced `_inject_token()` URL embedding with `GIT_ASKPASS` mechanism. A temporary script echoes the token from `GIT_TOKEN` env var, so it never appears in command-line arguments (invisible to `ps`/`/proc`), clone URL, or `.git/config`.

- **~~Local path detection is too permissive and can misclassify~~** — RESOLVED
  - Removed `Path(url).exists()` fallback. Now uses prefix-only matching (`/`, `~`, `./`, `../`) to prevent bare names matching existing CWD entries.

- **Testability risk: hard dependency on Docker availability at construction time**
  - **Where:** `Shesha.__init__` calls `_check_docker_available()` unconditionally (`src/shesha/shesha.py`)
  - **Why problematic (impact):**
    - Unit tests or workflows that only upload/parse/store docs (no querying) still require Docker daemon.
    - Makes library unusable in constrained environments where user wants “ingest-only” or “query via remote sandbox”.
  - **Concrete mitigations:**
    - Lazy-check Docker:
      - Move check into `start()` or into first query execution.
      - Provide `sandbox_enabled: bool` config; if false, allow non-query operations and raise a clear error only when query is attempted.
    - Provide a “NoSandboxEngine” or mock executor for tests.

- **~~Extensibility gap: repo ingestion path produces `ParsedDocument.name` inconsistently~~** — RESOLVED
  - `Project.upload()` now computes relative paths from the upload root directory when uploading directories, and overrides `doc.name` with the posix-style relative path (e.g., `src/foo/main.py`). This mirrors the existing pattern in `Shesha._ingest_repo`. Single-file uploads continue to use the basename. Storage already supports nested paths via `parent.mkdir(parents=True)`.

## 2) Additional notable doc/code discrepancies

- **~~Docs claim sub-LLM content is wrapped in `<untrusted_document_content>` tags~~** — RESOLVED
  - Added `wrap_subcall_content()` in `src/shesha/rlm/prompts.py` for code-level enforcement. `_handle_llm_query` now wraps content before passing to template. Validator rejects `subcall.md` templates missing the security tags. Content is double-wrapped (code + template) for defense-in-depth.

- **~~Docs describe container pool acquiring/releasing per query~~** — RESOLVED (see above).
