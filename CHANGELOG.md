# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- External prompt files in `prompts/` directory for easier customization
- `python -m shesha.prompts` CLI tool for validating prompt files
- Support for alternate prompt directories via `SHESHA_PROMPTS_DIR` environment variable
- `prompts/README.md` documenting prompt customization
- Session write command (`write` or `write <filename>`) in example scripts (`repo.py`, `barsoom.py`) to save conversation transcripts as markdown files

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
