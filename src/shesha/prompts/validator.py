"""Prompt validation utilities."""

import re


def extract_placeholders(text: str) -> set[str]:
    """Extract placeholder names from a template string.

    Handles both {name} and {name:format_spec} patterns.
    """
    pattern = r"\{([a-zA-Z_][a-zA-Z0-9_]*)(?::[^}]*)?\}"
    matches = re.findall(pattern, text)
    return set(matches)
