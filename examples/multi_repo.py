#!/usr/bin/env python3
"""Multi-repo PRD analysis using federated queries.

This script analyzes how a PRD (Product Requirements Document) impacts
multiple codebases and generates a draft HLD (High-Level Design).

Usage:
    python examples/multi_repo.py repo1_url repo2_url [repo3_url ...]

    Then paste your PRD when prompted (end with Ctrl+D or blank line).

Environment Variables:
    SHESHA_API_KEY: Required. API key for your LLM provider.
    SHESHA_MODEL: Optional. Model name (default: claude-sonnet-4-20250514).

Example:
    $ export SHESHA_API_KEY="your-api-key"
    $ python examples/multi_repo.py \\
        https://github.com/org/auth-service \\
        https://github.com/org/user-api
    Paste PRD (Ctrl+D or blank line to finish):
    ...
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from shesha import Shesha, SheshaConfig
from shesha.experimental.multi_repo import AlignmentReport, MultiRepoAnalyzer

STORAGE_PATH = Path.home() / ".shesha" / "multi-repo"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Analyze PRD impact across multiple repositories")
    parser.add_argument(
        "repos",
        nargs="*",
        help="Git repository URLs or local paths to analyze (shows picker if omitted)",
    )
    parser.add_argument(
        "--prd",
        help="Path to PRD markdown file (prompts for paste if omitted)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed progress during analysis",
    )
    return parser.parse_args(argv)


def read_multiline_input() -> str:
    """Read multiline input from stdin until EOF or blank line."""
    lines = []
    try:
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
    except EOFError:
        pass  # User pressed Ctrl+D to signal end of input
    return "\n".join(lines)


def read_prd(prd_path: str | None) -> str:
    """Read PRD from file or stdin.

    Args:
        prd_path: Path to PRD file, or None to read from stdin.

    Returns:
        PRD text content.
    """
    if prd_path is not None:
        path = Path(prd_path)
        if not path.is_file():
            print(f"Error: PRD file not found: {prd_path}")
            sys.exit(1)
        return path.read_text()

    print()
    print("Paste PRD (Ctrl+D or blank line to finish):")
    return read_multiline_input()


def main() -> None:
    """Main entry point."""
    args = parse_args()

    if not os.environ.get("SHESHA_API_KEY"):
        print("Error: SHESHA_API_KEY environment variable not set.")
        sys.exit(1)

    config = SheshaConfig.load(storage_path=STORAGE_PATH)
    shesha = Shesha(config=config)

    analyzer = MultiRepoAnalyzer(shesha)

    # Add repos
    for url in args.repos:
        print(f"Adding: {url}")
        project_id = analyzer.add_repo(url)
        if project_id:
            print(f"  -> {project_id}")
        else:
            print("  Warning: Failed to add (will continue with other repos)")

    # Check if any repos were added successfully
    if not analyzer.repos:
        print("\nError: No repositories could be added.")
        if analyzer.failed_repos:
            print("Failed repos:")
            for url in analyzer.failed_repos:
                print(f"  - {url}")
        sys.exit(1)

    # Warn about partial failures
    if analyzer.failed_repos:
        failed = len(analyzer.failed_repos)
        succeeded = len(analyzer.repos)
        print(f"\nNote: {failed} repo(s) failed, continuing with {succeeded}.")

    # Get PRD
    prd = read_prd(args.prd)

    if not prd.strip():
        print("No PRD provided. Exiting.")
        sys.exit(0)

    # Callbacks
    def on_discovery(repo_hint: str) -> str | None:
        """Prompt user to provide URL for discovered dependency."""
        print(f"\nDiscovered dependency: {repo_hint}")
        response = input("Enter repo URL to add (or press Enter to skip): ").strip()
        return response if response else None

    def on_alignment_issue(report: AlignmentReport) -> str:
        print(f"\nAlignment score: {report.alignment_score:.0%}")
        if report.gaps:
            print(f"Gaps: {len(report.gaps)}")
            for gap in report.gaps[:3]:
                print(f"  - {gap}")
        if report.scope_creep:
            print(f"Scope creep: {len(report.scope_creep)}")
            for item in report.scope_creep[:3]:
                print(f"  - {item}")
        return input("Action (revise/accept/abort): ").strip().lower()

    def on_progress(phase: str, message: str) -> None:
        if args.verbose:
            print(f"[{phase}] {message}")

    # Run analysis
    print()
    print("Analyzing...")
    hld, alignment = analyzer.analyze(
        prd,
        on_discovery=on_discovery,
        on_alignment_issue=on_alignment_issue,
        on_progress=on_progress,
    )

    # Output
    print()
    print("=" * 60)
    print("DRAFT HIGH-LEVEL DESIGN")
    print("=" * 60)
    print()
    print(hld.raw_hld)

    print()
    print("=" * 60)
    print(f"ALIGNMENT: {alignment.alignment_score:.0%} coverage")
    print(f"Recommendation: {alignment.recommendation}")
    print("=" * 60)

    # Save option
    print()
    if input("Save to file? (y/n): ").lower() == "y":
        filename = input("Filename [hld-draft.md]: ").strip() or "hld-draft.md"
        Path(filename).write_text(hld.raw_hld)
        print(f"Saved to {filename}")


if __name__ == "__main__":
    main()
