# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Semantic verification (`--verify` flag): opt-in post-analysis adversarial review that checks whether findings are supported by evidence. For code projects, adds code-specific checks for comment-mining, test/production conflation, and language idiom misidentification. Output reformatted into verified summary + appendix. Note: significantly increases analysis time and token cost (1-2 additional LLM calls)
- Post-FINAL citation verification: after `FINAL()`, the engine mechanically checks that cited doc IDs exist in the corpus and that quoted strings actually appear in the cited documents. Results are available via `QueryResult.verification`. Zero LLM cost, fail-safe (verification errors don't affect answer delivery)
- `verify_citations` config option (default `True`, env var `SHESHA_VERIFY_CITATIONS`) to enable/disable citation verification
- `ContainerExecutor.is_alive` property to check whether executor has an active socket connection

### Changed

- `llm_query()` in sandbox now raises `ValueError` when content exceeds the sub-LLM size limit, preventing error messages from being silently captured as return values and passed to `FINAL()`

### Fixed

- RLM engine now recovers from dead executors mid-loop when a container pool is available, acquiring a fresh executor instead of wasting remaining iterations
- RLM engine exits early with a clear error when executor dies and no pool is available, instead of running all remaining iterations against a dead executor
- Oversized `llm_query()` calls no longer produce error strings that get passed to `FINAL()` as the answer; they now raise exceptions so the LLM can retry with chunked content

## [0.4.0] - 2026-02-06

### Added

- `TraceWriteError` and `EngineNotConfiguredError` exception classes
- `suppress_errors` parameter on `TraceWriter` and `IncrementalTraceWriter` for opt-in error suppression
- Sandbox namespace `reset` action to clear state between queries
- Experimental multi-repo PRD analysis (`shesha.experimental.multi_repo`)
  - `MultiRepoAnalyzer` for analyzing how PRDs impact multiple codebases
  - Four-phase workflow: recon, impact, synthesize, align
  - Example script `examples/multi_repo.py`
- `examples/multi_repo.py`: `--prd <path>` argument to read PRD from file
- `examples/multi_repo.py`: interactive repo picker with all-then-deselect across both storage locations
- External prompt files in `prompts/` directory for easier customization
- `python -m shesha.prompts` CLI tool for validating prompt files
- Support for alternate prompt directories via `SHESHA_PROMPTS_DIR` environment variable
- `prompts/README.md` documenting prompt customization
- Session write command (`write` or `write <filename>`) in example scripts (`repo.py`, `barsoom.py`) to save conversation transcripts as markdown files

### Changed

- `Shesha.__init__` now accepts optional DI parameters (`storage`, `engine`, `parser_registry`, `repo_ingester`) for testability and extensibility; defaults are backward-compatible
- `Shesha()` no longer requires Docker at construction time; Docker check and container pool creation are deferred to `start()`, enabling ingest-only workflows without a Docker daemon
- `Shesha.get_project`, `get_project_info`, `get_analysis_status`, `get_analysis`, `generate_analysis`, `check_repo_for_updates` now raise `ProjectNotFoundError` instead of `ValueError`
- `Shesha.check_repo_for_updates` raises `RepoError` instead of `ValueError` when no repo URL is stored
- `Shesha._ingest_repo` now catches only `ParseError`/`NoParserError` (expected) and propagates unexpected errors as `RepoIngestError`
- `Project.query()` raises `EngineNotConfiguredError` instead of `RuntimeError`
- `TraceWriter` and `IncrementalTraceWriter` raise `TraceWriteError` by default on failure instead of silently returning `None`
- Engine passes `suppress_errors=True` to trace writers for best-effort tracing during queries
- `TraceWriter` and `IncrementalTraceWriter` now accept `StorageBackend` protocol instead of `FilesystemStorage`
- `RLMEngine.query()` accepts `StorageBackend` protocol instead of `FilesystemStorage`
- `Project.query()` always passes storage to engine (removed `FilesystemStorage` special-casing)
- `Shesha.__init__` now uses `SheshaConfig.load()` by default, honoring env vars and config files
- `RLMEngine` now respects `max_traces_per_project` config setting for trace cleanup (previously hardcoded to 50)

### Fixed

- `Project.upload()` with directories now uses relative paths for document names, preventing silent overwrites when files in different subdirectories share the same basename (e.g., `src/foo/main.py` and `src/bar/main.py`)
- RLM engine now uses the container pool for queries instead of creating throwaway containers, eliminating cold-start overhead and idle resource waste
- Pool-backed executor cleanup no longer masks query results or leaks executors when `reset_namespace()` fails (e.g., after a protocol error closes the socket)
- `ContainerPool.acquire()` now raises `RuntimeError` when pool is stopped, preventing container creation after shutdown
- `Shesha.start()` is now idempotent — calling it twice no longer leaks orphaned container pools
- Local repo paths (`./foo`, `../bar`) are now resolved to absolute paths before saving, preventing breakage when working directory changes between sessions

### Removed

- Removed unused `allowed_hosts` config field (containers have networking disabled; all LLM calls go through the host)

### Security

- `is_local_path` no longer uses `Path(url).exists()`; uses prefix-only matching to prevent misclassification
- Git clone tokens are now passed via `GIT_ASKPASS` instead of being embedded in the clone URL, preventing exposure in process argument lists
- Enforce `<untrusted_document_content>` wrapping in code (`wrap_subcall_content()`), not just in prompt template files, closing a prompt injection defense gap for sub-LLM calls
- Validate that `subcall.md` template contains required security tags at load time

## [0.3.0] 2026-02-04

### Fixed

- Host memory exhaustion via unbounded container output buffering
- Execution hanging indefinitely when container drips output without newlines
- Oversized JSON messages from container causing memory/CPU spike
- Path traversal in repository ingestion when project_id contains path separators
- Path traversal in raw file storage when document name contains path separators

### Security

- Added protocol limits for container communication (max buffer 10MB, max line 1MB, deadline 5min)
- Applied `safe_path()` consistently to all filesystem operations in repo ingestion and storage

## [0.2.0] - 2026-02-04

### Added

- `Shesha.check_repo_for_updates()` method to check if a cloned repository has updates available
- `RepoIngester.get_repo_url()` method to retrieve the remote origin URL from a cloned repo
- `ProjectInfo` dataclass for project metadata (source URL, is_local, source_exists)
- `Shesha.get_project_info()` method to retrieve project source information
- Repo picker now shows "(missing - /path)" for local repos that no longer exist
- Repo picker supports `d<N>` command to delete projects with confirmation

### Changed

- `Shesha.delete_project()` now accepts `cleanup_repo` parameter (default `True`) to also remove cloned repository data for remote repos

### Fixed

- `--update` flag in `examples/repo.py` now works when selecting an existing project from the picker

## [0.1.0] - 2026-02-03

### Added

- Initial release of Shesha RLM library
- Core RLM loop with configurable max iterations
- Docker sandbox for secure code execution
- Document loading for PDF, DOCX, HTML, and text files
- Sub-LLM queries via `llm_query()` function
- Project-based document organization
- LiteLLM integration for multiple LLM providers
- Trace recording for debugging and analysis
- Security hardening with untrusted content tagging
- Network isolation with egress whitelist for LLM APIs
