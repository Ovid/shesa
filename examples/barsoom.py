#!/usr/bin/env python3
"""Interactive Barsoom novel explorer using Shesha.

This script provides an interactive CLI for exploring Edgar Rice Burroughs'
Barsoom (Mars) novel series using Shesha's Recursive Language Model (RLM)
capabilities. The novels are in the public domain and included in the
test-datasets directory.

The Barsoom series consists of 7 novels:
    1. A Princess of Mars
    2. The Gods of Mars
    3. The Warlord of Mars
    4. Thuvia, Maid of Mars
    5. The Chessmen of Mars
    6. The Master Mind of Mars
    7. A Fighting Man of Mars

Features:
    - Automatic setup on first run (uploads all 7 novels)
    - Conversation history for follow-up questions
    - Session transcript export with "write" command
    - In-session help with "help" or "?" command
    - Verbose mode with execution stats and progress
    - Non-interactive mode for scripted queries

Usage:
    # Interactive mode (sets up on first run)
    python examples/barsoom.py

    # Force re-upload of novels
    python examples/barsoom.py --setup

    # Single query (non-interactive)
    python examples/barsoom.py --prompt "Who is Dejah Thoris?"

    # Verbose mode with execution stats
    python examples/barsoom.py --verbose

Environment Variables:
    SHESHA_API_KEY: Required. API key for your LLM provider.
    SHESHA_MODEL: Optional. Model name (default: claude-sonnet-4-20250514).

Example:
    $ export SHESHA_API_KEY="your-api-key"
    $ python examples/barsoom.py
    Setting up Barsoom project...
    Uploading: A Princess of Mars (barsoom-1.txt)
    ...
    Setup complete! 7 novels loaded.

    Ask questions about the Barsoom series. Type "quit" or "exit" to leave.

    > Who is the son of Dejah Thoris?
    [Thought for 29 seconds]
    The son of Dejah Thoris and John Carter is **Carthoris of Helium**.

    # Save session transcript
    > write                    # Auto-generates timestamped filename
    > write my-research.md     # Custom filename
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Allow importing script_utils whether running as a script or as a module.
# When run directly (python examples/barsoom.py), Python adds examples/ to sys.path
# automatically, so "from script_utils import" works. But when imported as a module
# (from examples.barsoom import ...), examples/ isn't in sys.path. This ensures
# script_utils is always findable, avoiding duplicate import lists for each mode.
sys.path.insert(0, str(Path(__file__).parent))

from script_utils import (
    ThinkingSpinner,
    format_history_prefix,
    format_progress,
    format_stats,
    format_thought_time,
    install_urllib3_cleanup_hook,
    is_exit_command,
    is_help_command,
    is_write_command,
    parse_write_command,
    should_warn_history_size,
    write_session,
)

from shesha import Shesha
from shesha.config import SheshaConfig
from shesha.exceptions import ProjectNotFoundError
from shesha.rlm.trace import StepType

INTERACTIVE_HELP = """\
Shesha Barsoom Explorer - Ask questions about the Barsoom novel series.

Commands:
  help, ?              Show this help message
  write                Save session transcript (auto-generated filename)
  write <filename>     Save session transcript to specified file
  quit, exit           Leave the session

Tip: Use --verbose flag for execution stats after each answer."""

BOOKS = {
    "barsoom-1.txt": "A Princess of Mars",
    "barsoom-2.txt": "The Gods of Mars",
    "barsoom-3.txt": "The Warlord of Mars",
    "barsoom-4.txt": "Thuvia, Maid of Mars",
    "barsoom-5.txt": "The Chessmen of Mars",
    "barsoom-6.txt": "The Master Mind of Mars",
    "barsoom-7.txt": "A Fighting Man of Mars",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments.

    Args:
        argv: Command line arguments. If None, uses sys.argv.

    Returns:
        Parsed arguments namespace with:
            - setup: Force re-upload of novels even if project exists
            - verbose: Show execution stats after each answer
            - prompt: Single query for non-interactive mode (optional)
    """
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
    """Get the path to the Barsoom test datasets directory.

    Returns:
        Path to the test-datasets/barsoom directory, relative to this script's
        location. The directory contains the 7 Barsoom novels as .txt files.
    """
    return Path(__file__).parent.parent / "test-datasets" / "barsoom"


def setup_project(shesha: Shesha) -> None:
    """Set up the Barsoom project by uploading all 7 novels.

    Creates a new project named "barsoom" and uploads each novel from the
    test-datasets directory. Progress is printed for each file uploaded.

    Args:
        shesha: Initialized Shesha instance to create the project in.

    Note:
        This overwrites any existing "barsoom" project. The novels total
        approximately 2.8 million characters across all 7 books.
    """
    print("Setting up Barsoom project...")
    project = shesha.create_project(PROJECT_NAME)
    datasets_dir = get_datasets_dir()

    for filename, title in BOOKS.items():
        filepath = datasets_dir / filename
        print(f"Uploading: {title} ({filename})")
        project.upload(filepath)

    print(f"Setup complete! {len(BOOKS)} novels loaded.")


def main() -> None:
    """Main entry point for the Barsoom explorer CLI.

    Orchestrates the complete workflow:
    1. Validates environment (SHESHA_API_KEY required)
    2. Initializes Shesha with local storage configuration
    3. Sets up the project on first run or if --setup is passed
    4. Handles single query (--prompt) or enters interactive loop

    The interactive loop maintains conversation history for follow-up
    questions and warns when history grows large.

    Raises:
        SystemExit: If SHESHA_API_KEY is not set or project cannot be loaded.
    """
    install_urllib3_cleanup_hook()
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
    except ProjectNotFoundError as e:
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

            elapsed = time.time() - query_start_time
            print(format_thought_time(elapsed))
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
    print("Ask questions about the Barsoom series.")
    print('Type "help" or "?" for commands.')
    print()

    # Conversation history for follow-up questions
    history: list[tuple[str, str, str]] = []

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

        if is_help_command(user_input):
            print(INTERACTIVE_HELP)
            print()
            continue

        if is_write_command(user_input):
            if not history:
                print("Nothing to save - no exchanges yet.")
                print()
                continue
            try:
                filename = parse_write_command(user_input)
                path = write_session(history, PROJECT_NAME, filename)
                print(f"Session saved to {path} ({len(history)} exchanges)")
            except OSError as e:
                print(f"Error saving session: {e}")
            print()
            continue

        # Check if history is getting large
        if should_warn_history_size(history):
            print(f"Warning: Conversation history is large ({len(history)} exchanges).")
            try:
                clear = input("Clear history? (y/n): ").strip().lower()
                if clear == "y":
                    history.clear()
                    print("History cleared.")
            except (EOFError, KeyboardInterrupt):
                pass  # User cancelled, continue with existing history

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

            # Prepend conversation history for context
            prefix = format_history_prefix(history)
            full_question = f"{prefix}{user_input}" if prefix else user_input
            result = project.query(full_question, on_progress=on_progress)
            spinner.stop()

            elapsed = time.time() - query_start_time
            print(format_thought_time(elapsed))
            print(result.answer)
            print()

            # Store exchange in history
            stats = format_stats(result.execution_time, result.token_usage, result.trace)
            history.append((user_input, result.answer, stats))

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
