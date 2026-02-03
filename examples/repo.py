#!/usr/bin/env python3
"""Interactive git repository explorer using Shesha."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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


if __name__ == "__main__":
    pass
