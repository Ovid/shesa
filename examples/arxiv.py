#!/usr/bin/env python3
"""Shesha arXiv Explorer -- search, load, and query arXiv papers."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# script_utils lives in examples/ alongside this file
sys.path.insert(0, str(Path(__file__).parent))

from shesha.experimental.arxiv.cache import PaperCache  # noqa: E402
from shesha.experimental.arxiv.models import PaperMeta, TopicInfo  # noqa: E402
from shesha.experimental.arxiv.search import ArxivSearcher  # noqa: E402
from shesha.experimental.arxiv.topics import TopicManager  # noqa: E402

STARTUP_BANNER = """\
Shesha arXiv Explorer
Answers are AI-generated and may contain errors. Always verify against primary sources.
Type /help for commands."""

DEFAULT_DATA_DIR = Path.home() / ".shesha-arxiv"


@dataclass
class AppState:
    """Mutable application state passed to command handlers."""

    shesha: object  # Shesha instance
    topic_mgr: TopicManager
    cache: PaperCache
    searcher: ArxivSearcher
    current_topic: str | None = None  # Current project_id
    last_search_results: list[PaperMeta] = field(default_factory=list)
    _search_offset: int = 0  # Offset for /more pagination
    _last_search_kwargs: dict[str, object] | None = None  # Last search params for /more


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Shesha arXiv Explorer")
    parser.add_argument("--model", type=str, help="LLM model to use")
    parser.add_argument("--data-dir", type=str, help="Data directory")
    parser.add_argument("--topic", type=str, help="Start in a specific topic")
    return parser.parse_args(argv)


# --- Command handlers ---
# Each handler has signature: (args: str, state: AppState) -> None


def handle_help(args: str, state: AppState) -> None:
    """Print available commands."""
    commands = [
        ("/search <query>", "Search arXiv (--author, --cat, --recent)"),
        ("/more", "Show next page of search results"),
        ("/load <nums or IDs>", "Load papers into current topic"),
        ("/papers", "List papers in current topic with arXiv URLs"),
        ("/check-citations [ID]", "Citation verification with disclaimer"),
        ("/topic [name]", "Switch to / create a topic"),
        ("/topic delete <name>", "Delete a topic"),
        ("/history", "List all topics with date, paper count, size"),
        ("/help", "Show this help message"),
        ("/quit", "Exit"),
    ]
    print("\nAvailable commands:")
    for cmd, desc in commands:
        print(f"  {cmd:<30s} {desc}")
    print()


def handle_history(args: str, state: AppState) -> None:
    """List all topics with metadata."""
    topics = state.topic_mgr.list_topics()
    if not topics:
        print("No topics yet. Use /search and /load to get started.")
        return
    print("\nTopics:")
    total_size = 0
    for i, t in enumerate(topics, 1):
        created_str = t.created.strftime("%b %d, %Y")
        papers_word = "paper" if t.paper_count == 1 else "papers"
        marker = " *" if t.project_id == state.current_topic else ""
        print(
            f"  {i}. {t.name:<35s} Created: {created_str:<15s}"
            f"  {t.paper_count} {papers_word:<8s} {t.formatted_size}{marker}"
        )
        total_size += t.size_bytes
    formatted_total = TopicInfo(
        name="",
        created=topics[0].created,
        paper_count=0,
        size_bytes=total_size,
        project_id="",
    ).formatted_size
    print(f"{'':>60s} Total: {formatted_total}")
    print()


def handle_topic(args: str, state: AppState) -> None:
    """Switch to or create a topic, or delete one."""
    args = args.strip()
    if not args:
        if state.current_topic:
            info = state.topic_mgr.get_topic_info_by_project_id(state.current_topic)
            if info:
                print(f"Current topic: {info.name}")
            else:
                print(f"Current topic: {state.current_topic}")
        else:
            print("No topic selected. Use /topic <name> to create or switch.")
        return

    parts = args.split(maxsplit=1)
    if parts[0] == "delete" and len(parts) > 1:
        name = parts[1]
        try:
            state.topic_mgr.delete(name)
            print(f"Deleted topic: {name}")
            if state.current_topic and name in state.current_topic:
                state.current_topic = None
        except ValueError as e:
            print(f"Error: {e}")
        return

    # Switch to or create topic
    name = args
    project_id = state.topic_mgr.resolve(name)
    if project_id:
        state.current_topic = project_id
        docs = state.topic_mgr._storage.list_documents(project_id)
        print(f"Switched to topic: {name} ({len(docs)} papers)")
    else:
        project_id = state.topic_mgr.create(name)
        state.current_topic = project_id
        print(f"Created topic: {name}")


def handle_papers(args: str, state: AppState) -> None:
    """List papers in the current topic."""
    if state.current_topic is None:
        print("No topic selected. Use /topic <name> first.")
        return
    docs = state.topic_mgr._storage.list_documents(state.current_topic)
    if not docs:
        print("No papers loaded. Use /search and /load to add papers.")
        return
    # Get topic name for display
    info = state.topic_mgr.get_topic_info_by_project_id(state.current_topic)
    topic_name = info.name if info else state.current_topic
    print(f'\nPapers in "{topic_name}":')
    for i, doc_name in enumerate(docs, 1):
        meta = state.cache.get_meta(doc_name)
        if meta:
            print(f'  {i}. [{meta.arxiv_id}] "{meta.title}"')
            print(f"     {meta.arxiv_url}")
        else:
            print(f"  {i}. {doc_name}")
    print()


COMMANDS: dict[str, tuple[Callable[..., None], str]] = {
    "/help": (handle_help, "Show available commands"),
    "/history": (handle_history, "List topics"),
    "/topic": (handle_topic, "Topic management"),
    "/papers": (handle_papers, "List loaded papers"),
    # /search, /more, /load, /check-citations added in Tasks 9-10
}


def dispatch_command(user_input: str, state: AppState) -> bool:
    """Dispatch a slash command. Returns True if should quit."""
    parts = user_input.split(maxsplit=1)
    cmd = parts[0].lower()
    cmd_args = parts[1] if len(parts) > 1 else ""

    if cmd in ("/quit", "/exit"):
        return True

    handler_entry = COMMANDS.get(cmd)
    if handler_entry is None:
        print(f"Unknown command: {cmd}. Type /help for available commands.")
        return False

    handler, _ = handler_entry
    handler(cmd_args, state=state)
    return False


def main() -> None:
    """Main entry point."""
    _args = parse_args()
    print(STARTUP_BANNER)
    # Full initialization deferred to Tasks 9-10
    # For now, just the REPL loop skeleton


if __name__ == "__main__":
    main()
