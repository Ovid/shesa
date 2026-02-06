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

- **Layering violation: `Project.query()` special-cases `FilesystemStorage`**
  - **Where:** `src/shesha/project.py` lines ~66–76 (casts storage to `FilesystemStorage` to enable tracing)
  - **Why problematic (impact):**
    - Breaks storage abstraction (`StorageBackend` protocol). Any alternative storage can’t support traces without modifying `Project`.
    - Makes testing/mocking harder and undermines extensibility (“pluggable storage” isn’t truly pluggable).
  - **Concrete mitigations:**
    - Extend storage abstraction with an optional tracing capability:
      - Add `TraceStorage` protocol with `get_traces_dir()/list_traces()` or more general `write_trace(project_id, data)` methods.
      - Engine (or TraceWriter) should depend on that protocol, not concrete FS storage.
    - Alternatively, move trace writing behind an injected `TraceSink` interface with a filesystem implementation.

- **Error-handling is inconsistent and bypasses the project’s own exception hierarchy**
  - **Where:**
    - `src/shesha/shesha.py`: uses `ValueError` for missing project/repo URL; catches broad `Exception` during parsing and converts to warning strings.
    - `src/shesha/storage/filesystem.py`: uses domain exceptions (`ProjectNotFoundError`, etc.).
    - `src/shesha/rlm/trace_writer.py`: swallows all exceptions and returns `None`.
    - `src/shesha/sandbox/executor.py`: returns `ExecutionResult(status="error", error=...)` instead of raising.
  - **Why problematic (impact):**
    - Callers can’t reliably handle failures (sometimes exceptions, sometimes status strings, sometimes silent `None`).
    - Makes it difficult to build a service wrapper with correct HTTP mappings and observability.
  - **Concrete mitigations:**
    - Establish a policy:
      - Domain operations raise `SheshaError` subclasses.
      - “Best-effort” operations return structured results with explicit warnings, but **do not** silently swallow unexpected errors.
    - Replace `ValueError` in `Shesha.get_project`, `get_project_info`, `check_repo_for_updates` with `ProjectNotFoundError` / `RepoError` variants.
    - For ingestion parsing loop (`Shesha._ingest_repo`), catch expected parsing exceptions (`ParseError`) but let unexpected exceptions bubble up (or wrap in `RepoIngestError` with cause).
    - In `TraceWriter.write_trace`, either raise `TraceWriteError` or accept a logger callback; avoid returning `None` silently unless explicitly configured.

- **Configuration layering exists but isn’t used consistently; some config values are unused**
  - **Where:**
    - `src/shesha/config.py` provides `load()` hierarchy.
    - `src/shesha/shesha.py` ignores `SheshaConfig.load()` and manually mutates defaults; also `allowed_hosts` is never used.
    - `TraceWriter.cleanup_old_traces(..., max_count=50)` ignores `SheshaConfig.max_traces_per_project`.
  - **Why problematic (impact):**
    - Users can’t rely on documented configuration precedence.
    - Security-relevant config (`allowed_hosts`) becomes “paper security”—documented but not enforced.
  - **Concrete mitigations:**
    - Make `Shesha.__init__` accept `config: SheshaConfig = SheshaConfig.load()` by default, and stop mutating `config` in-place (prefer constructing via `load(..., overrides)`).
    - Plumb `max_traces_per_project` into `TraceWriter.cleanup_old_traces(project_id, max_count=config.max_traces_per_project)`.
    - Either implement `allowed_hosts` enforcement (see next item) or remove it from config until supported.

- **~~Sandbox network whitelisting is documented/configured but not enforced in code~~** — RESOLVED
  - `allowed_hosts` removed from `SheshaConfig`. SECURITY.md updated to reflect that containers have networking disabled and all LLM calls go through the host.

- **~~Sandbox runner namespace persistence~~** — PARTIALLY RESOLVED
  - Added `reset` action to runner that clears user variables while preserving builtins (FINAL, llm_query, etc.). Added `reset_namespace()` method to `ContainerExecutor`.
  - Remaining: per-process execution and OS-level timeout enforcement are not yet addressed.

- **~~Repo token handling injects secrets into clone URL (leak risk)~~** — RESOLVED
  - Replaced `_inject_token()` URL embedding with `git -c http.extraHeader=Authorization: Bearer ...`. Token no longer appears in clone URL, process list, or `.git/config`.

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

- **Extensibility gap: repo ingestion path produces `ParsedDocument.name` inconsistently**
  - **Where:**
    - In repo ingest: `ParsedDocument(name=file_path, ...)` in `Shesha._ingest_repo`, where `file_path` is relative path like `src/main.py`.
    - Parser `CodeParser.parse` returns `name=path.name` (basename only) (and other parsers likely same pattern).
  - **Why problematic (impact):**
    - Document identity differs depending on ingestion path; collisions possible when uploading directories (`Project.upload`) because stored `doc.name` may be just basename (e.g., `main.py` from multiple dirs).
    - Storage supports nested paths (`safe_path(docs_dir, f"{doc.name}.json")` + parent mkdir), but upload path may not supply nested names consistently.
  - **Concrete mitigations:**
    - Define a single canonical “document id” concept:
      - For uploads, set `doc.name` to a project-relative path (posix style) when uploading directories.
      - Update parsers to accept a `file_path` override (already present in `CodeParser.parse`) and use it consistently for `name`.
    - In `Project.upload`, pass the relative path from the upload root into parser and storage.

## 2) Additional notable doc/code discrepancies

- **~~Docs claim sub-LLM content is wrapped in `<untrusted_document_content>` tags~~** — RESOLVED
  - Added `wrap_subcall_content()` in `src/shesha/rlm/prompts.py` for code-level enforcement. `_handle_llm_query` now wraps content before passing to template. Validator rejects `subcall.md` templates missing the security tags. Content is double-wrapped (code + template) for defense-in-depth.

- **~~Docs describe container pool acquiring/releasing per query~~** — RESOLVED (see above).
