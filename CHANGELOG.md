# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `TraceWriteError` and `EngineNotConfiguredError` exception classes
- `suppress_errors` parameter on `TraceWriter` and `IncrementalTraceWriter` for opt-in error suppression

### Changed

- `Shesha.get_project`, `get_project_info`, `get_analysis_status`, `get_analysis`, `generate_analysis`, `check_repo_for_updates` now raise `ProjectNotFoundError` instead of `ValueError`
- `Shesha.check_repo_for_updates` raises `RepoError` instead of `ValueError` when no repo URL is stored
- `Shesha._ingest_repo` now catches only `ParseError`/`NoParserError` (expected) and propagates unexpected errors as `RepoIngestError`
- `Project.query()` raises `EngineNotConfiguredError` instead of `RuntimeError`
- `TraceWriter` and `IncrementalTraceWriter` raise `TraceWriteError` by default on failure instead of silently returning `None`
- Engine passes `suppress_errors=True` to trace writers for best-effort tracing during queries
- `RLMEngine` now respects `max_traces_per_project` config setting for trace cleanup (previously hardcoded to 50)

### Added

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

### Fixed

- RLM engine now uses the container pool for queries instead of creating throwaway containers, eliminating cold-start overhead and idle resource waste

### Removed

- Removed unused `allowed_hosts` config field (containers have networking disabled; all LLM calls go through the host)

### Security

- `is_local_path` no longer uses `Path(url).exists()`; uses prefix-only matching to prevent misclassification
- Git clone tokens are now passed via `http.extraHeader` instead of being embedded in the clone URL
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
