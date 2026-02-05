#!/usr/bin/env python3
"""Shared utilities for Shesha example scripts."""

import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from shesha.rlm.trace import StepType, TokenUsage, Trace

if TYPE_CHECKING:
    from sys import UnraisableHookArgs

# Constants for history size warnings
HISTORY_WARN_CHARS = 50_000
HISTORY_WARN_EXCHANGES = 10


class ThinkingSpinner:
    """Animated spinner that shows 'Thinking...' with animated dots."""

    def __init__(self) -> None:
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the spinner animation."""
        self._running = True
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the spinner and clear the line."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)
        # Clear the line
        print("\r" + " " * 20 + "\r", end="", flush=True)

    def _animate(self) -> None:
        """Animation loop running in background thread."""
        dots = 0
        while self._running:
            dots = (dots % 3) + 1
            print(f"\rThinking{'.' * dots}{' ' * (3 - dots)}", end="", flush=True)
            time.sleep(0.3)


def format_progress(
    step_type: StepType, iteration: int, content: str, elapsed_seconds: float | None = None
) -> str:
    """Format a progress message for verbose output."""
    step_names = {
        StepType.CODE_GENERATED: "Generating code",
        StepType.CODE_OUTPUT: "Executing code",
        StepType.SUBCALL_REQUEST: "Sub-LLM query",
        StepType.SUBCALL_RESPONSE: "Sub-LLM response",
        StepType.FINAL_ANSWER: "Final answer",
        StepType.ERROR: "Error",
    }
    step_name = step_names.get(step_type, step_type.value)
    if elapsed_seconds is not None:
        return f"  [{elapsed_seconds:.1f}s] [Iteration {iteration + 1}] {step_name}"
    return f"  [Iteration {iteration + 1}] {step_name}"


def format_thought_time(elapsed_seconds: float) -> str:
    """Format elapsed time as '[Thought for N seconds]'."""
    seconds = round(elapsed_seconds)
    unit = "second" if seconds == 1 else "seconds"
    return f"[Thought for {seconds} {unit}]"


def format_stats(execution_time: float, token_usage: TokenUsage, trace: Trace) -> str:
    """Format verbose stats for display after an answer."""
    prompt = token_usage.prompt_tokens
    completion = token_usage.completion_tokens
    total = token_usage.total_tokens
    lines = [
        "---",
        f"Execution time: {execution_time:.2f}s",
        f"Tokens: {total} (prompt: {prompt}, completion: {completion})",
        f"Trace steps: {len(trace.steps)}",
    ]
    return "\n".join(lines)


def format_history_prefix(history: list[tuple[str, str]]) -> str:
    """Format conversation history as context for a follow-up question."""
    if not history:
        return ""

    lines = ["Previous conversation:"]
    for i, (q, a) in enumerate(history, 1):
        lines.append(f"Q{i}: {q}")
        lines.append(f"A{i}: {a}")
        lines.append("")  # blank line between exchanges

    lines.append("Current question:")
    return "\n".join(lines)


def is_exit_command(user_input: str) -> bool:
    """Check if user input is an exit command."""
    return user_input.lower() in ("quit", "exit")


def is_help_command(user_input: str) -> bool:
    """Check if user input is a help command."""
    return user_input.lower() in ("help", "?")


def is_write_command(user_input: str) -> bool:
    """Check if user input is a write command.

    Args:
        user_input: The user's input string.

    Returns:
        True if the input is 'write' or 'write <filename>'.
    """
    parts = user_input.lower().split()
    return len(parts) >= 1 and parts[0] == "write"


def parse_write_command(user_input: str) -> str | None:
    """Parse write command and extract filename.

    Args:
        user_input: The user's input string (already confirmed as write command).

    Returns:
        The filename with .md extension, or None for auto-generate.
    """
    parts = user_input.split(maxsplit=1)
    if len(parts) == 1:
        return None

    filename = parts[1].strip()
    if not filename.lower().endswith(".md"):
        filename = filename + ".md"
    return filename


def should_warn_history_size(history: list[tuple[str, str]]) -> bool:
    """Check if history is large enough to warrant a warning."""
    if len(history) >= HISTORY_WARN_EXCHANGES:
        return True
    total_chars = sum(len(q) + len(a) for q, a in history)
    return total_chars >= HISTORY_WARN_CHARS


def install_urllib3_cleanup_hook() -> None:
    """Install hook to suppress harmless urllib3 cleanup errors during shutdown.

    When Python exits, objects are garbage collected in arbitrary order. If the
    underlying file handle gets closed before urllib3's HTTPResponse finalizer
    runs, it raises "ValueError: I/O operation on closed file". This is harmless
    (the connection is being closed anyway) but produces ugly output. We suppress
    only this specific error while letting other unraisable exceptions through.
    """
    original_hook = sys.unraisablehook

    def suppress_urllib3_error(unraisable: "UnraisableHookArgs") -> None:
        if unraisable.exc_type is ValueError and "I/O operation on closed file" in str(
            unraisable.exc_value
        ):
            return
        original_hook(unraisable)

    sys.unraisablehook = suppress_urllib3_error


def generate_session_filename() -> str:
    """Generate a timestamped session filename.

    Returns:
        Filename like 'session-2026-02-05-143022.md'.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    return f"session-{timestamp}.md"


def format_session_transcript(history: list[tuple[str, str]], project_name: str) -> str:
    """Format conversation history as a markdown transcript.

    Args:
        history: List of (question, answer) tuples.
        project_name: Name or URL of the project for metadata.

    Returns:
        Formatted markdown string.
    """
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# Session Transcript",
        "",
        f"- **Date:** {date_str}",
        f"- **Project:** {project_name}",
        f"- **Exchanges:** {len(history)}",
        "",
        "---",
    ]

    for question, answer in history:
        lines.extend(
            [
                "",
                f"**User:** {question}",
                "",
                answer,
                "",
                "---",
            ]
        )

    return "\n".join(lines)


def write_session(
    history: list[tuple[str, str]],
    project_name: str,
    filename: str | None,
) -> str:
    """Write session transcript to a markdown file.

    Args:
        history: List of (question, answer) tuples.
        project_name: Name or URL of the project for metadata.
        filename: Output filename, or None to auto-generate.

    Returns:
        The path that was written to.

    Raises:
        OSError: If file cannot be written.
    """
    if filename is None:
        filename = generate_session_filename()

    filepath = Path(filename)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    content = format_session_transcript(history, project_name)
    filepath.write_text(content)

    return str(filepath)
