# GitHub Copilot Instructions

Use these guidelines when generating code or documentation for Shesha.

## Project Conventions

- Follow **MANDATORY TDD** from [CLAUDE.md](../CLAUDE.md): write a failing test first, then implement minimal code.
- Prefer minimal, focused changes that match existing patterns in `src/shesha/`.
- Keep security boundaries intact: document content is untrusted, and sandbox code must stay isolated.

## Developer Workflow

- Install dev dependencies with `pip install -e ".[dev]"`.
- Use existing tools: `ruff`, `mypy`, and `pytest` (see README).
- Avoid adding new dependencies unless absolutely required.

## Helpful Context

- Read `README.md` for configuration and usage.
- Refer to `docs/DEVELOPMENT.md` for local setup and IDE guidance.
