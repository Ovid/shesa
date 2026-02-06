#!/usr/bin/env python3
"""Interactive git repository explorer using Shesha.

This script provides an interactive CLI for exploring git repositories using
Shesha's Recursive Language Model (RLM) capabilities. It supports both remote
repositories (GitHub, GitLab, Bitbucket) and local git repos.

Features:
    - Interactive picker for previously indexed repositories
    - Automatic update detection and application
    - Conversation history for follow-up questions
    - Session transcript export with "write" command
    - In-session help with "help" or "?" command
    - Verbose mode with execution stats and progress

Usage:
    # Explore a GitHub repository
    python examples/repo.py https://github.com/org/repo

    # Explore a local git repository
    python examples/repo.py /path/to/local/repo

    # Show picker of previously indexed repos
    python examples/repo.py

    # Auto-apply updates and show verbose stats
    python examples/repo.py https://github.com/org/repo --update --verbose

Environment Variables:
    SHESHA_API_KEY: Required. API key for your LLM provider.
    SHESHA_MODEL: Optional. Model name (default: claude-sonnet-4-20250514).

Example:
    $ export SHESHA_API_KEY="your-api-key"
    $ python examples/repo.py https://github.com/Ovid/shesha
    Loading repository: https://github.com/Ovid/shesha
    Loaded 42 files.

    Ask questions about the codebase. Type "quit" or "exit" to leave.

    > How does the sandbox execute code?
    [Thought for 15 seconds]
    The sandbox executes code in isolated Docker containers...

    # Save session transcript
    > write                    # Auto-generates timestamped filename
    > write my-notes.md        # Custom filename
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

# Allow importing script_utils whether running as a script or as a module.
# When run directly (python examples/repo.py), Python adds examples/ to sys.path
# automatically, so "from script_utils import" works. But when imported as a module
# (from examples.repo import ...), examples/ isn't in sys.path. This ensures
# script_utils is always findable, avoiding duplicate import lists for each mode.
sys.path.insert(0, str(Path(__file__).parent))

from script_utils import (
    ThinkingSpinner,
    format_analysis_as_context,
    format_analysis_for_display,
    format_history_prefix,
    format_progress,
    format_stats,
    format_thought_time,
    install_urllib3_cleanup_hook,
    is_analysis_command,
    is_exit_command,
    is_help_command,
    is_regenerate_command,
    is_write_command,
    parse_write_command,
    should_warn_history_size,
    write_session,
)

from shesha import Shesha, SheshaConfig
from shesha.exceptions import ProjectNotFoundError, RepoIngestError
from shesha.rlm.trace import StepType

# Storage path for repo projects (not "repos" - that collides with RepoIngester's subdirectory)
STORAGE_PATH = Path.home() / ".shesha" / "repo-explorer"

INTERACTIVE_HELP = """\
Shesha Repository Explorer - Ask questions about the indexed codebase.

Commands:
  help, ?              Show this help message
  analysis             Show codebase analysis
  analyze              Generate/regenerate codebase analysis
  write                Save session transcript (auto-generated filename)
  write <filename>     Save session transcript to specified file
  quit, exit           Leave the session"""

if TYPE_CHECKING:
    from shesha.models import RepoProjectResult
    from shesha.project import Project


def _looks_like_repo_url_or_path(value: str) -> bool:
    """Check if value looks like a repository URL or filesystem path.

    Args:
        value: User input string to validate.

    Returns:
        True if value looks like a URL or path, False otherwise.
    """
    # URLs
    if value.startswith(("http://", "https://", "git@")):
        return True
    # Absolute paths
    if value.startswith("/"):
        return True
    # Home-relative paths
    if value.startswith("~"):
        return True
    # Relative paths
    if value.startswith("./") or value.startswith("../"):
        return True
    return False


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments.

    Args:
        argv: Command line arguments. If None, uses sys.argv.

    Returns:
        Parsed arguments namespace with:
            - repo: Git repository URL or local path (optional)
            - update: Whether to auto-apply updates without prompting
            - verbose: Whether to show execution stats after each answer
    """
    parser = argparse.ArgumentParser(description="Explore git repositories using Shesha RLM")
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
    parser.add_argument(
        "--pristine",
        action="store_true",
        help="Skip using pre-computed analysis as query context",
    )
    return parser.parse_args(argv)


def show_picker(shesha: Shesha) -> tuple[str, bool] | None:
    """Show interactive repository picker for previously indexed repos.

    Displays a numbered list of previously indexed repositories and prompts
    the user to either select one by number, delete one with 'd<N>', or
    enter a new URL/path.

    Args:
        shesha: Initialized Shesha instance to query for existing projects.

    Returns:
        None: If no projects exist in storage.
        tuple[str, True]: If user selected an existing project (project name).
        tuple[str, False]: If user entered a new URL/path to index.

    Example:
        Available repositories:
          1. org-repo
          2. another-project (missing - /old/path)

        Enter number, 'd<N>' to delete, or new URL: 1
        -> Returns ("org-repo", True)

        Enter number, 'd<N>' to delete, or new URL: https://github.com/new/repo
        -> Returns ("https://github.com/new/repo", False)
    """
    while True:
        projects = shesha.list_projects()
        if not projects:
            return None

        print("Available repositories:")
        project_infos = []
        for i, name in enumerate(projects, 1):
            info = shesha.get_project_info(name)
            project_infos.append(info)
            if info.is_local and not info.source_exists:
                print(f"  {i}. {name} (missing - {info.source_url})")
            else:
                print(f"  {i}. {name}")
        print()

        user_input = input("Enter number, 'd<N>' to delete, or new URL: ").strip()

        # Check for delete command
        if user_input.lower().startswith("d"):
            try:
                num = int(user_input[1:])
                if 1 <= num <= len(projects):
                    project_name = projects[num - 1]
                    info = project_infos[num - 1]

                    # Determine confirmation message
                    if info.is_local or info.source_url is None:
                        msg = f"Delete '{project_name}'? This will remove all indexed data. (y/n): "
                    else:
                        msg = (
                            f"Delete '{project_name}'? "
                            "This will remove indexed data and cloned repository. (y/n): "
                        )

                    confirm = input(msg).strip().lower()
                    if confirm == "y":
                        shesha.delete_project(project_name)
                        print(f"Deleted '{project_name}'.")
                    print()
                    continue  # Re-show picker
            except ValueError:
                pass  # Not a valid "d<N>" command, fall through to other handlers

        # Check if it's a number selecting an existing project
        try:
            num = int(user_input)
            if 1 <= num <= len(projects):
                return (projects[num - 1], True)
        except ValueError:
            pass  # Not a number, treat as URL/path below

        # Check for exit commands
        if is_exit_command(user_input):
            return ("", False)

        # Validate that input looks like a URL or path
        if _looks_like_repo_url_or_path(user_input):
            return (user_input, False)

        # Invalid input - show error and reprompt
        print(f"Invalid input: '{user_input}'")
        print("Enter a number, 'd<N>' to delete, URL, or local path.")
        print()


def prompt_for_repo() -> str:
    """Prompt user to enter a repository URL or local path.

    Called when no previously indexed repositories exist, prompting the user
    to provide a new repository to index.

    Returns:
        User-provided repository URL or local filesystem path, stripped of
        leading/trailing whitespace.
    """
    print("No repositories loaded yet.")
    return input("Enter repo URL or local path: ").strip()


def handle_updates(result: RepoProjectResult, auto_update: bool) -> RepoProjectResult:
    """Handle repository update detection and application.

    When a repository has been previously indexed and changes are detected
    (new commits), this function either automatically applies updates or
    prompts the user for confirmation.

    Args:
        result: The result from create_project_from_repo() containing the
            project and its current status.
        auto_update: If True, applies updates without prompting. If False,
            asks the user whether to apply available updates.

    Returns:
        The original result if no updates were available or user declined,
        or a new RepoProjectResult with updated files if updates were applied.
    """
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


def check_and_prompt_analysis(shesha: Shesha, project_id: str) -> None:
    """Check analysis status and prompt user if needed.

    Args:
        shesha: Shesha instance.
        project_id: Project to check.
    """
    try:
        status = shesha.get_analysis_status(project_id)
    except ProjectNotFoundError:
        return  # Project may not exist yet; skip analysis check gracefully

    if status == "missing":
        print("Note: No codebase analysis exists for this repository.")
        try:
            response = input("Generate analysis? (y/n): ").strip().lower()
            if response == "y":
                print("Generating analysis (this may take a minute)...")
                analysis = shesha.generate_analysis(project_id)
                print("Analysis complete.\n")
                print(format_analysis_for_display(analysis))
                print()
        except (EOFError, KeyboardInterrupt):
            print()  # Clean line after interrupt
    elif status == "stale":
        print("Note: Codebase analysis is outdated (HEAD has moved).")
        try:
            response = input("Regenerate analysis? (y/n): ").strip().lower()
            if response == "y":
                print("Regenerating analysis...")
                analysis = shesha.generate_analysis(project_id)
                print("Analysis updated.\n")
                print(format_analysis_for_display(analysis))
                print()
        except (EOFError, KeyboardInterrupt):
            print()  # Clean line after interrupt


def run_interactive_loop(
    project: Project,
    verbose: bool,
    project_name: str,
    shesha: Shesha,
    analysis_context: str | None = None,
) -> None:
    """Run the interactive question-answer loop for querying the codebase.

    Provides a REPL-style interface where users can ask questions about the
    indexed repository. Maintains conversation history for follow-up questions
    and warns when history grows large.

    Args:
        project: The Shesha project containing the indexed repository.
        verbose: If True, displays execution stats (time, tokens, trace)
            and progress updates during query processing.
        project_name: Name or URL of the project for session transcript metadata.
        shesha: Shesha instance for analysis commands.
        analysis_context: Pre-formatted analysis text to prepend to queries.
            When set, each query includes this context so the LLM has structural
            knowledge of the codebase. Pass None to skip (equivalent to --pristine).

    Note:
        The loop continues until the user types "quit", "exit", or presses
        Ctrl+C/Ctrl+D. Conversation history is maintained in memory and
        prepended to each query for context.
    """
    if analysis_context:
        print("Using codebase analysis as context. Use --pristine to disable.")
    print()
    print("Ask questions about the codebase.")
    print('Type "help" or "?" for commands.')
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

        if is_help_command(user_input):
            print(INTERACTIVE_HELP)
            print()
            continue

        if is_analysis_command(user_input):
            analysis = shesha.get_analysis(project.project_id)
            if analysis is None:
                print("No analysis exists. Use 'analyze' to generate one.")
            else:
                print(format_analysis_for_display(analysis))
            print()
            continue

        if is_regenerate_command(user_input):
            print("Generating analysis (this may take a minute)...")
            try:
                shesha.generate_analysis(project.project_id)
                print("Analysis complete. Use 'analysis' to view.")
            except Exception as e:
                print(f"Error generating analysis: {e}")
            print()
            continue

        if is_write_command(user_input):
            if not history:
                print("Nothing to save - no exchanges yet.")
                print()
                continue
            try:
                filename = parse_write_command(user_input)
                path = write_session(history, project_name, filename)
                print(f"Session saved to {path} ({len(history)} exchanges)")
            except OSError as e:
                print(f"Error saving session: {e}")
            print()
            continue

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
            if analysis_context and prefix:
                full_question = f"{analysis_context}\n\n{prefix}{user_input}"
            elif analysis_context:
                full_question = f"{analysis_context}\n\n{user_input}"
            elif prefix:
                full_question = f"{prefix}{user_input}"
            else:
                full_question = user_input
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
    """Main entry point for the repository explorer CLI.

    Orchestrates the complete workflow:
    1. Validates environment (SHESHA_API_KEY required)
    2. Initializes Shesha with storage configuration
    3. Determines repository source (argument, picker, or prompt)
    4. Loads or creates the repository project
    5. Handles any available updates
    6. Enters the interactive query loop

    Raises:
        SystemExit: If SHESHA_API_KEY is not set or Docker is unavailable.
    """
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
    try:
        shesha = Shesha(config=config)
    except RuntimeError as e:
        if "Docker" in str(e):
            print(f"Error: {e}")
            print()
            print("To build the sandbox container, run:")
            print("  docker build -t shesha-sandbox sandbox/")
            sys.exit(1)
        raise

    # Determine which repo to use
    project = None
    if args.repo:
        repo_url = args.repo
    else:
        # Interactive picker mode
        picker_result = show_picker(shesha)
        if picker_result is None:
            repo_url = prompt_for_repo()
        elif picker_result[1]:
            # User selected existing project by number - check for updates
            project_name = picker_result[0]
            print(f"Loading project: {project_name}")
            result = shesha.check_repo_for_updates(project_name)

            # Handle status
            if result.status == "unchanged":
                print(f"Using cached repository ({result.files_ingested} files).")

            result = handle_updates(result, args.update)

            if result.status == "created":
                print(f"Updated: {result.files_ingested} files.")

            project = result.project
        else:
            # User entered a new URL/path
            repo_url = picker_result[0]

        if project is None and not repo_url:
            print("No repository specified. Exiting.")
            sys.exit(0)

    # Load or create project from URL if not already loaded
    if project is None:
        print(f"Loading repository: {repo_url}")
        try:
            result = shesha.create_project_from_repo(repo_url)
        except RepoIngestError as e:
            print(f"Error: {e}")
            sys.exit(1)

        # Handle status
        if result.status == "created":
            print(f"Loaded {result.files_ingested} files.")
        elif result.status == "unchanged":
            print(f"Using cached repository ({result.files_ingested} files).")

        result = handle_updates(result, args.update)

        if result.status == "created":
            print(f"Updated: {result.files_ingested} files.")

        project = result.project

    # Check analysis status
    check_and_prompt_analysis(shesha, project.project_id)

    # Load analysis context for query injection
    analysis_context = None
    if not args.pristine:
        analysis = shesha.get_analysis(project.project_id)
        if analysis:
            analysis_context = format_analysis_as_context(analysis)

    # Enter interactive loop
    run_interactive_loop(project, args.verbose, project.project_id, shesha, analysis_context)


if __name__ == "__main__":
    main()
