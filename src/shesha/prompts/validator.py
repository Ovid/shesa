"""Prompt validation utilities."""

import re


def extract_placeholders(text: str) -> set[str]:
    """Extract placeholder names from a template string.

    Handles both {name} and {name:format_spec} patterns.
    Ignores escaped braces ({{ and }}).
    """
    # Remove escaped braces to avoid false matches
    # Python's str.format uses {{ for literal { and }} for literal }
    cleaned = text.replace("{{", "").replace("}}", "")
    pattern = r"\{([a-zA-Z_][a-zA-Z0-9_]*)(?::[^}]*)?\}"
    matches = re.findall(pattern, cleaned)
    return set(matches)
