#!/usr/bin/env python3
"""Interactive Barsoom novel explorer using Shesha."""

import argparse
import os
import sys
import threading
import time
from pathlib import Path

from shesha import Shesha
from shesha.config import SheshaConfig
from shesha.rlm.trace import StepType, TokenUsage, Trace

BOOKS = {
    "barsoom-1.txt": "A Princess of Mars",
    "barsoom-2.txt": "The Gods of Mars",
    "barsoom-3.txt": "The Warlord of Mars",
    "barsoom-4.txt": "Thuvia, Maid of Mars",
    "barsoom-5.txt": "The Chessmen of Mars",
    "barsoom-6.txt": "The Master Mind of Mars",
    "barsoom-7.txt": "A Fighting Man of Mars",
}


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


def is_exit_command(user_input: str) -> bool:
    """Check if user input is an exit command."""
    return user_input.lower() in ("quit", "exit")


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
    return ""  # Minimal implementation


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Explore the Barsoom novels using Shesha RLM")
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Force re-upload of novels (even if project exists)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show execution stats after each answer",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        help="Run a single query and exit (non-interactive mode)",
    )
    return parser.parse_args(argv)


STORAGE_PATH = "./barsoom_data"
PROJECT_NAME = "barsoom"


def get_datasets_dir() -> Path:
    """Get the path to the barsoom test datasets directory."""
    return Path(__file__).parent.parent / "test-datasets" / "barsoom"


def setup_project(shesha: Shesha) -> None:
    """Set up the barsoom project by uploading novels."""
    print("Setting up Barsoom project...")
    project = shesha.create_project(PROJECT_NAME)
    datasets_dir = get_datasets_dir()

    for filename, title in BOOKS.items():
        filepath = datasets_dir / filename
        print(f"Uploading: {title} ({filename})")
        project.upload(filepath)

    print(f"Setup complete! {len(BOOKS)} novels loaded.")


def _install_urllib3_cleanup_hook() -> None:
    """Install hook to suppress harmless urllib3 cleanup errors during shutdown.

    When Python exits, objects are garbage collected in arbitrary order. If the
    underlying file handle gets closed before urllib3's HTTPResponse finalizer
    runs, it raises "ValueError: I/O operation on closed file". This is harmless
    (the connection is being closed anyway) but produces ugly output. We suppress
    only this specific error while letting other unraisable exceptions through.
    """
    original_hook = sys.unraisablehook

    def suppress_urllib3_error(unraisable: sys.UnraisableHookArgs) -> None:
        if (
            unraisable.exc_type is ValueError
            and "I/O operation on closed file" in str(unraisable.exc_value)
        ):
            return
        original_hook(unraisable)

    sys.unraisablehook = suppress_urllib3_error


def main() -> None:
    """Main entry point."""
    _install_urllib3_cleanup_hook()
    args = parse_args()

    # Check for API key
    if not os.environ.get("SHESHA_API_KEY"):
        print("Error: SHESHA_API_KEY environment variable not set.")
        print()
        print("Environment variables:")
        print("  SHESHA_API_KEY   (required) API key for your LLM provider")
        print("  SHESHA_MODEL     (optional) Model name, e.g.:")
        print("                   - claude-sonnet-4-20250514 (default, Anthropic)")
        print("                   - gpt-4o (OpenAI)")
        print("                   - gemini/gemini-1.5-pro (Google)")
        print()
        print("The provider is auto-detected from the model name via LiteLLM.")
        sys.exit(1)

    # Initialize Shesha with config from environment
    config = SheshaConfig.load(storage_path=STORAGE_PATH)
    shesha = Shesha(config=config)

    # Check if project exists
    project_exists = PROJECT_NAME in shesha.list_projects()

    # Setup if needed
    if args.setup or not project_exists:
        setup_project(shesha)

    # Get the project
    try:
        project = shesha.get_project(PROJECT_NAME)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Non-interactive mode with --prompt
    if args.prompt:
        try:
            spinner = ThinkingSpinner()
            spinner.start()
            query_start_time = time.time()

            def on_progress(step_type: StepType, iteration: int, content: str) -> None:
                if args.verbose:
                    spinner.stop()
                    elapsed = time.time() - query_start_time
                    print(format_progress(step_type, iteration, content, elapsed_seconds=elapsed))
                    spinner.start()

            result = project.query(args.prompt, on_progress=on_progress)
            spinner.stop()

            print(result.answer)
            print()

            if args.verbose:
                print(format_stats(result.execution_time, result.token_usage, result.trace))
                print()

        except Exception as e:
            spinner.stop()
            print(f"Error: {e}")
            sys.exit(1)
        return

    print()
    print('Ask questions about the Barsoom series. Type "quit" or "exit" to leave.')
    print()

    # Interactive loop
    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if is_exit_command(user_input):
            print("Goodbye!")
            break

        try:
            spinner = ThinkingSpinner()
            spinner.start()
            query_start_time = time.time()

            # Progress callback for verbose mode
            def on_progress(step_type: StepType, iteration: int, content: str) -> None:
                if args.verbose:
                    spinner.stop()
                    elapsed = time.time() - query_start_time
                    print(format_progress(step_type, iteration, content, elapsed_seconds=elapsed))
                    spinner.start()

            result = project.query(user_input, on_progress=on_progress)
            spinner.stop()

            print(result.answer)
            print()

            if args.verbose:
                print(format_stats(result.execution_time, result.token_usage, result.trace))
                print()

        except Exception as e:
            spinner.stop()
            print(f"Error: {e}")
            print('Try again or type "quit" to exit.')
            print()


if __name__ == "__main__":
    main()
