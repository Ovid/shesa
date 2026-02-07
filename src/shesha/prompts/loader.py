"""Prompt loader for external markdown prompt files."""

import os
from pathlib import Path

from shesha.prompts.validator import PROMPT_SCHEMAS, validate_prompt


def get_default_prompts_dir() -> Path:
    """Get the default prompts directory.

    For development: prompts/ at project root
    For installed package: prompts/ in package data
    """
    # First try: prompts/ relative to this file (installed location)
    package_prompts = Path(__file__).parent / "prompts"
    if package_prompts.exists():
        return package_prompts

    # Second try: prompts/ at project root (development)
    project_root = Path(__file__).parent.parent.parent.parent
    project_prompts = project_root / "prompts"
    if project_prompts.exists():
        return project_prompts

    # Fallback: raise clear error
    raise FileNotFoundError(
        "Could not find prompts directory. "
        "Set SHESHA_PROMPTS_DIR environment variable to specify location."
    )


def resolve_prompts_dir(explicit_dir: Path | None = None) -> Path:
    """Resolve prompts directory from explicit arg, env var, or default.

    Priority:
    1. explicit_dir argument
    2. SHESHA_PROMPTS_DIR environment variable
    3. Default bundled prompts directory
    """
    if explicit_dir is not None:
        return explicit_dir

    env_dir = os.environ.get("SHESHA_PROMPTS_DIR")
    if env_dir:
        return Path(env_dir)

    return get_default_prompts_dir()


class PromptLoader:
    """Loads and renders prompts from markdown files."""

    def __init__(self, prompts_dir: Path | None = None) -> None:
        """Initialize loader with prompts directory.

        Args:
            prompts_dir: Directory containing prompt markdown files.
                If None, uses SHESHA_PROMPTS_DIR env var or default.

        Raises:
            PromptValidationError: If any prompt file is invalid.
            FileNotFoundError: If prompts directory or required files not found.
        """
        self.prompts_dir = resolve_prompts_dir(prompts_dir)
        self._prompts: dict[str, str] = {}
        self._load_and_validate()

    def _load_and_validate(self) -> None:
        """Load all prompt files and validate them."""
        if not self.prompts_dir.exists():
            raise FileNotFoundError(f"Prompts directory not found: {self.prompts_dir}")

        for filename in PROMPT_SCHEMAS:
            filepath = self.prompts_dir / filename
            if not filepath.exists():
                raise FileNotFoundError(
                    f"Required prompt file not found: {filepath}\n\n"
                    f"Expected files: {', '.join(sorted(PROMPT_SCHEMAS.keys()))}\n"
                    f"Prompts directory: {self.prompts_dir}"
                )

            content = filepath.read_text()
            validate_prompt(filename, content)
            self._prompts[filename] = content

    def render_system_prompt(
        self,
        doc_count: int,
        total_chars: int,
        doc_sizes_list: str,
        max_subcall_chars: int,
    ) -> str:
        """Render the system prompt with variables."""
        return self._prompts["system.md"].format(
            doc_count=doc_count,
            total_chars=total_chars,
            doc_sizes_list=doc_sizes_list,
            max_subcall_chars=max_subcall_chars,
        )

    def render_subcall_prompt(self, instruction: str, content: str) -> str:
        """Render the subcall prompt with variables."""
        return self._prompts["subcall.md"].format(
            instruction=instruction,
            content=content,
        )

    def render_code_required(self) -> str:
        """Render the code_required prompt (no variables)."""
        return self._prompts["code_required.md"]

    def render_verify_adversarial_prompt(self, findings: str, documents: str) -> str:
        """Render the adversarial verification prompt."""
        return self._prompts["verify_adversarial.md"].format(
            findings=findings,
            documents=documents,
        )

    def render_verify_code_prompt(
        self, previous_results: str, findings: str, documents: str
    ) -> str:
        """Render the code-specific verification prompt."""
        return self._prompts["verify_code.md"].format(
            previous_results=previous_results,
            findings=findings,
            documents=documents,
        )

    def get_raw_template(self, name: str) -> str:
        """Get the raw template content for a prompt file."""
        return self._prompts[name]
