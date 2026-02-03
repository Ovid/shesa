#!/usr/bin/env python3
"""Interactive git repository explorer using Shesha."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from shesha import Shesha, SheshaConfig
from shesha.rlm.trace import StepType

# Storage path for repo projects
STORAGE_PATH = Path.home() / ".shesha" / "repos"

# Support both running as script and importing as module
if __name__ == "__main__":
    from script_utils import (
        ThinkingSpinner,
        format_history_prefix,
        format_progress,
        format_stats,
        format_thought_time,
        install_urllib3_cleanup_hook,
        is_exit_command,
        should_warn_history_size,
    )
else:
    from .script_utils import (
        ThinkingSpinner,
        format_history_prefix,
        format_progress,
        format_stats,
        format_thought_time,
        install_urllib3_cleanup_hook,
        is_exit_command,
        should_warn_history_size,
    )

if TYPE_CHECKING:
    from shesha.storage.project import Project

    from shesha import Shesha
    from shesha.models import RepoProjectResult


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Explore git repositories using Shesha RLM"
    )
    parser.add_argument(
        "repo",
        nargs="?",
        help="Git repository URL or local path (shows picker if omitted)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Auto-apply updates without prompting",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show execution stats after each answer",
    )
    return parser.parse_args(argv)


def show_picker(shesha: Shesha) -> str | None:
    """Show interactive repo picker. Returns project name, URL, or None if no projects."""
    projects = shesha.list_projects()
    if not projects:
        return None

    print("Available repositories:")
    for i, name in enumerate(projects, 1):
        print(f"  {i}. {name}")
    print()

    user_input = input("Enter number or new repo URL: ").strip()

    # Check if it's a number
    try:
        num = int(user_input)
        if 1 <= num <= len(projects):
            return projects[num - 1]
    except ValueError:
        pass

    # Otherwise treat as URL/path
    return user_input


def prompt_for_repo() -> str:
    """Prompt user to enter a repo URL or path."""
    print("No repositories loaded yet.")
    return input("Enter repo URL or local path: ").strip()


def handle_updates(result: RepoProjectResult, auto_update: bool) -> RepoProjectResult:
    """Handle update prompting. Returns updated result if applied."""
    if result.status != "updates_available":
        return result

    if auto_update:
        print("Applying updates...")
        return result.apply_updates()

    print(f"Updates available for {result.project.project_id}.")
    response = input("Apply updates? (y/n): ").strip().lower()

    if response == "y":
        print("Applying updates...")
        return result.apply_updates()

    return result


def run_interactive_loop(project: Project, verbose: bool) -> None:
    """Run the interactive question-answer loop."""
    print()
    print('Ask questions about the codebase. Type "quit" or "exit" to leave.')
    print()

    history: list[tuple[str, str]] = []

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

            def on_progress(step_type: StepType, iteration: int, content: str) -> None:
                if verbose:
                    spinner.stop()
                    elapsed = time.time() - query_start_time
                    print(format_progress(step_type, iteration, content, elapsed_seconds=elapsed))
                    spinner.start()

            prefix = format_history_prefix(history)
            full_question = f"{prefix}{user_input}" if prefix else user_input
            result = project.query(full_question, on_progress=on_progress)
            spinner.stop()

            elapsed = time.time() - query_start_time
            print(format_thought_time(elapsed))
            print(result.answer)
            print()

            history.append((user_input, result.answer))

            if verbose:
                print(format_stats(result.execution_time, result.token_usage, result.trace))
                print()

        except Exception as e:
            spinner.stop()
            print(f"Error: {e}")
            print('Try again or type "quit" to exit.')
            print()


def main() -> None:
    """Main entry point."""
    install_urllib3_cleanup_hook()
    args = parse_args()

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

    config = SheshaConfig.load(storage_path=STORAGE_PATH)
    shesha = Shesha(config=config)

    # Determine which repo to use
    if args.repo:
        repo_url = args.repo
    else:
        # Interactive picker mode
        repo_url = show_picker(shesha)
        if repo_url is None:
            repo_url = prompt_for_repo()
        if not repo_url:
            print("No repository specified. Exiting.")
            sys.exit(0)

    # Load or create project
    print(f"Loading repository: {repo_url}")
    result = shesha.create_project_from_repo(repo_url)

    # Handle status
    if result.status == "created":
        print(f"Loaded {result.files_ingested} files.")
    elif result.status == "unchanged":
        print(f"Using cached repository ({result.files_ingested} files).")

    result = handle_updates(result, args.update)

    if result.status == "created":
        print(f"Updated: {result.files_ingested} files.")

    # Enter interactive loop
    run_interactive_loop(result.project, args.verbose)


if __name__ == "__main__":
    main()
