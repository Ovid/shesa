"""Prompt validation utilities."""

import re
from dataclasses import dataclass


@dataclass
class PromptSchema:
    """Schema for a prompt file."""

    required: set[str]
    optional: set[str]


PROMPT_SCHEMAS: dict[str, PromptSchema] = {
    "system.md": PromptSchema(
        required={"doc_count", "total_chars", "doc_sizes_list", "max_subcall_chars"},
        optional=set(),
    ),
    "subcall.md": PromptSchema(
        required={"instruction", "content"},
        optional=set(),
    ),
    "code_required.md": PromptSchema(
        required=set(),
        optional=set(),
    ),
}


class PromptValidationError(Exception):
    """Raised when prompt validation fails."""

    pass


def validate_prompt(filename: str, content: str) -> None:
    """Validate a prompt file against its schema.

    Args:
        filename: Name of the prompt file (e.g., "system.md")
        content: Content of the prompt file

    Raises:
        PromptValidationError: If validation fails
    """
    if filename not in PROMPT_SCHEMAS:
        raise PromptValidationError(f"Unknown prompt file: {filename}")

    schema = PROMPT_SCHEMAS[filename]
    found = extract_placeholders(content)

    # Check for missing required placeholders
    missing = schema.required - found
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise PromptValidationError(
            f"{filename} is missing required placeholder: {{{missing_list}}}\n\n"
            f"Required placeholders for this file: {{{', '.join(sorted(schema.required))}}}"
        )

    # Check for unknown placeholders
    allowed = schema.required | schema.optional
    unknown = found - allowed
    if unknown:
        unknown_list = ", ".join(sorted(unknown))
        raise PromptValidationError(
            f"{filename} contains unknown placeholder: {{{unknown_list}}}\n\n"
            f"Available placeholders for this file: {{{', '.join(sorted(allowed))}}}"
        )

    # Security check: subcall.md must contain untrusted content tags
    if filename == "subcall.md":
        if "<untrusted_document_content>" not in content:
            raise PromptValidationError(
                f"{filename} is missing required <untrusted_document_content> tag.\n\n"
                "The subcall prompt MUST wrap {content} in "
                "<untrusted_document_content> tags to defend against prompt injection."
            )
        if "</untrusted_document_content>" not in content:
            raise PromptValidationError(
                f"{filename} is missing required </untrusted_document_content> closing tag.\n\n"
                "The subcall prompt MUST wrap {content} in "
                "<untrusted_document_content> tags to defend against prompt injection."
            )


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
