## 1) Key architectural issues (with references), impact, and mitigations

- **~~Public API (`Shesha`) does too much and hard-binds infrastructure~~** — RESOLVED
  - `Shesha.__init__` now accepts optional DI parameters: `storage: StorageBackend`, `engine: RLMEngine`, `parser_registry: ParserRegistry`, `repo_ingester: RepoIngester`. When provided, these are used directly; otherwise defaults are created (backward-compatible). Docker check was already deferred to `start()` in a prior fix. This enables testing without Docker/filesystem and swapping backends for extensibility.

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

- **~~Testability risk: hard dependency on Docker availability at construction time~~** — RESOLVED
  - Docker check and `ContainerPool` creation moved from `__init__` to `start()`. `Shesha()` can now be constructed without Docker for ingest-only workflows. `start()` (called by `__enter__`) checks Docker, creates the pool, and sets it on the engine. `stop()` is safe to call even if `start()` was never called.

- **~~Extensibility gap: repo ingestion path produces `ParsedDocument.name` inconsistently~~** — RESOLVED
  - `Project.upload()` now computes relative paths from the upload root directory when uploading directories, and overrides `doc.name` with the posix-style relative path (e.g., `src/foo/main.py`). This mirrors the existing pattern in `Shesha._ingest_repo`. Single-file uploads continue to use the basename. Storage already supports nested paths via `parent.mkdir(parents=True)`.

## 2) Additional notable doc/code discrepancies

- **~~Docs claim sub-LLM content is wrapped in `<untrusted_document_content>` tags~~** — RESOLVED
  - Added `wrap_subcall_content()` in `src/shesha/rlm/prompts.py` for code-level enforcement. `_handle_llm_query` now wraps content before passing to template. Validator rejects `subcall.md` templates missing the security tags. Content is double-wrapped (code + template) for defense-in-depth.

- **~~Docs describe container pool acquiring/releasing per query~~** — RESOLVED (see above).
