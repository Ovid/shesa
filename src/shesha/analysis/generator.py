"""Codebase analysis generator."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shesha import Shesha


class AnalysisGenerator:
    """Generates codebase analysis using RLM queries."""

    def __init__(self, shesha: "Shesha") -> None:
        """Initialize the generator.

        Args:
            shesha: Shesha instance for project access.
        """
        self._shesha = shesha

    def _load_prompt(self, name: str) -> str:
        """Load a prompt template from the prompts directory.

        Args:
            name: Name of the prompt file (without .md extension).

        Returns:
            The prompt content as a string.
        """
        prompts_dir = Path(__file__).parent / "prompts"
        return (prompts_dir / f"{name}.md").read_text()
