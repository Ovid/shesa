#!/usr/bin/env python3
"""Shesha arXiv Explorer -- search, load, and query arXiv papers."""

from __future__ import annotations

import argparse
import re
import readline  # noqa: F401 — enables arrow keys and history for input()
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from shesha import Shesha
from shesha.config import SheshaConfig
from shesha.experimental.arxiv.cache import PaperCache
from shesha.experimental.arxiv.citations import (
    ArxivVerifier,
    detect_llm_phrases,
    extract_citations_from_bbl,
    extract_citations_from_bib,
    extract_citations_from_text,
    format_check_report,
)
from shesha.experimental.arxiv.download import download_paper, to_parsed_document
from shesha.experimental.arxiv.models import CheckReport, ExtractedCitation, PaperMeta, TopicInfo
from shesha.experimental.arxiv.search import ArxivSearcher, format_result
from shesha.experimental.arxiv.topics import TopicManager
from shesha.rlm.trace import StepType
from shesha.storage.filesystem import FilesystemStorage

# script_utils lives in examples/ alongside this file
sys.path.insert(0, str(Path(__file__).parent))

from script_utils import (  # noqa: E402
    ThinkingSpinner,
    format_progress,
    format_stats,
    format_thought_time,
)

STARTUP_BANNER = """\
Shesha arXiv Explorer
Answers are AI-generated and may contain errors. Always verify against primary sources.
Type /help for commands."""

DEFAULT_DATA_DIR = Path.home() / ".shesha-arxiv"

ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")


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
        ("/search <query>", "Search arXiv (--author, --cat, --recent, --sort)"),
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

    # Switch to or create topic (create is idempotent)
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


def _parse_search_flags(args_str: str) -> tuple[str, dict[str, object]]:
    """Parse --author, --cat, --recent flags from search args.

    Handles quoted author names like ``--author "del maestro"``.
    Returns ``(remaining_query, kwargs_for_searcher)``.
    """
    kwargs: dict[str, object] = {}
    remaining = args_str

    # --author "quoted name" or --author single_word
    author_match = re.search(r'--author\s+"([^"]+)"', remaining)
    if author_match:
        kwargs["author"] = author_match.group(1)
        remaining = remaining[: author_match.start()] + remaining[author_match.end() :]
    else:
        author_match = re.search(r"--author\s+(\S+)", remaining)
        if author_match:
            kwargs["author"] = author_match.group(1)
            remaining = remaining[: author_match.start()] + remaining[author_match.end() :]

    # --cat category
    cat_match = re.search(r"--cat\s+(\S+)", remaining)
    if cat_match:
        kwargs["category"] = cat_match.group(1)
        remaining = remaining[: cat_match.start()] + remaining[cat_match.end() :]

    # --recent N
    recent_match = re.search(r"--recent\s+(\d+)", remaining)
    if recent_match:
        kwargs["recent_days"] = int(recent_match.group(1))
        remaining = remaining[: recent_match.start()] + remaining[recent_match.end() :]

    # --sort relevance|date|updated
    sort_match = re.search(r"--sort\s+(\S+)", remaining)
    if sort_match:
        kwargs["sort_by"] = sort_match.group(1)
        remaining = remaining[: sort_match.start()] + remaining[sort_match.end() :]

    return remaining.strip(), kwargs


def handle_search(args: str, state: AppState) -> None:
    """Search arXiv for papers."""
    args = args.strip()
    if not args:
        print("Usage: /search <query> [--author <name>] [--cat <category>] [--recent <days>]")
        return

    query, kwargs = _parse_search_flags(args)
    results = state.searcher.search(query, **kwargs)
    state.last_search_results = results
    state._search_offset = len(results)
    state._last_search_kwargs = {"query": query, **kwargs}

    if not results:
        print("No results found.")
        return

    print(f"\nFound {len(results)} results:")
    for i, meta in enumerate(results, 1):
        print(format_result(meta, i))
    print("\nUse /more for next page, /load <numbers> to pick, /load to load this page.")


def handle_more(args: str, state: AppState) -> None:
    """Show next page of search results."""
    if state._last_search_kwargs is None:
        print("No previous search. Use /search first.")
        return

    offset = state._search_offset
    results = state.searcher.search(**state._last_search_kwargs, max_results=10, start=offset)

    if not results:
        print("No more results.")
        return

    start_index = len(state.last_search_results) + 1
    state.last_search_results.extend(results)
    state._search_offset = offset + len(results)

    print(f"\nResults {start_index}-{start_index + len(results) - 1}:")
    for i, meta in enumerate(results, start_index):
        print(format_result(meta, i))
    print()


def handle_load(args: str, state: AppState) -> None:
    """Load papers into the current topic."""
    if state.current_topic is None:
        print("No topic selected. Use /topic <name> first.")
        return

    args = args.strip()
    if not args:
        # Bare /load: load all current search results
        if not state.last_search_results:
            print("No search results. Use /search first.")
            return
        tokens = [str(i) for i in range(1, len(state.last_search_results) + 1)]
    else:
        tokens = args.split()
    loaded = 0
    for i, token in enumerate(tokens):
        if i > 0:
            time.sleep(3)  # Rate limit between downloads

        meta: PaperMeta | None = None

        # Try as search result number
        if token.isdigit():
            idx = int(token) - 1
            if 0 <= idx < len(state.last_search_results):
                meta = state.last_search_results[idx]
            else:
                print(f"  Invalid result number: {token}")
                continue
        # Try as arXiv ID
        elif ARXIV_ID_RE.match(token):
            if state.cache.has(token):
                meta = state.cache.get_meta(token)
            else:
                meta = state.searcher.get_by_id(token)
            if meta is None:
                print(f"  Paper not found: {token}")
                continue
        else:
            print(f"  Invalid input: {token} (use a result number or arXiv ID like 2501.12345)")
            continue

        # Download and store
        updated_meta = download_paper(meta, state.cache)
        doc = to_parsed_document(updated_meta.arxiv_id, state.cache)
        state.topic_mgr._storage.store_document(state.current_topic, doc)
        loaded += 1
        source_label = updated_meta.source_type or "unknown"
        print(f'  Loaded [{updated_meta.arxiv_id}] "{updated_meta.title}" ({source_label})')

    if loaded:
        print(f"\n{loaded} paper(s) loaded into topic.")


def handle_check_citations(args: str, state: AppState) -> None:
    """Check citations for papers in the current topic."""
    if state.current_topic is None:
        print("No topic selected. Use /topic <name> first.")
        return

    docs = state.topic_mgr._storage.list_documents(state.current_topic)
    if not docs:
        print("No papers loaded. Use /search and /load to add papers first.")
        return

    # Optionally filter by arXiv ID
    filter_id = args.strip() if args.strip() else None
    if filter_id:
        docs = [d for d in docs if filter_id in d]
        if not docs:
            print(f"Paper {filter_id} not found in current topic.")
            return

    verifier = ArxivVerifier(searcher=state.searcher)

    for doc_name in docs:
        meta = state.cache.get_meta(doc_name)
        if meta is None:
            print(f"  Skipping {doc_name}: no metadata in cache")
            continue

        # Extract citations
        citations: list[ExtractedCitation] = []
        source_files = state.cache.get_source_files(doc_name)
        full_text = ""

        if source_files is not None:
            for filename, content in source_files.items():
                full_text += content + "\n"
                if filename.endswith(".bib"):
                    citations.extend(extract_citations_from_bib(content))
                elif filename.endswith(".bbl"):
                    citations.extend(extract_citations_from_bbl(content))
        else:
            # Try to get text from the stored document (PDF fallback)
            try:
                doc = state.topic_mgr._storage.get_document(state.current_topic, doc_name)
                full_text = doc.content
                citations.extend(extract_citations_from_text(full_text))
            except Exception:
                full_text = ""  # No source available

        # Detect LLM-tell phrases
        llm_phrases = detect_llm_phrases(full_text)

        # Verify each citation
        print(f"  Checking citations in {meta.arxiv_id}...")
        results = [verifier.verify(c) for c in citations]

        report = CheckReport(
            arxiv_id=meta.arxiv_id,
            title=meta.title,
            citations=citations,
            verification_results=results,
            llm_phrases=llm_phrases,
        )
        print(format_check_report(report))
        print()


def handle_query(question: str, state: AppState) -> None:
    """Handle a conversational query about loaded papers."""
    if state.current_topic is None:
        print("No topic selected. Use /topic <name> first.")
        return

    docs = state.topic_mgr._storage.list_documents(state.current_topic)
    if not docs:
        print("No papers loaded. Use /search and /load to add papers first.")
        return

    project = state.shesha.get_project(state.current_topic)

    spinner = ThinkingSpinner()
    start_time = time.time()

    def on_progress(step_type: StepType, iteration: int, content: str, token_usage: object) -> None:
        elapsed = time.time() - start_time
        if step_type == StepType.FINAL_ANSWER:
            spinner.stop()
        else:
            msg = format_progress(step_type, iteration, content, elapsed_seconds=elapsed)
            spinner.stop()
            print(msg)
            spinner.start()

    spinner.start()
    try:
        result = project.query(question, on_progress=on_progress)
    except Exception as e:
        spinner.stop()
        print(f"Query error: {e}")
        return
    spinner.stop()

    elapsed = time.time() - start_time
    print(format_thought_time(elapsed))
    print()
    print(result.answer)
    print()
    print(format_stats(result.execution_time, result.token_usage, result.trace))


COMMANDS: dict[str, tuple[Callable[..., None], str]] = {
    "/help": (handle_help, "Show available commands"),
    "/history": (handle_history, "List topics"),
    "/topic": (handle_topic, "Topic management"),
    "/papers": (handle_papers, "List loaded papers"),
    "/search": (handle_search, "Search arXiv"),
    "/more": (handle_more, "Next page of results"),
    "/load": (handle_load, "Load papers"),
    "/check-citations": (handle_check_citations, "Citation verification"),
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
    args = parse_args()
    print(STARTUP_BANNER)

    # Set up directories
    data_dir = Path(args.data_dir) if args.data_dir else DEFAULT_DATA_DIR
    shesha_data = data_dir / "shesha_data"
    cache_dir = data_dir / "paper-cache"
    shesha_data.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Initialize components
    config = SheshaConfig.load(storage_path=str(shesha_data))
    if args.model:
        config.model = args.model
    storage = FilesystemStorage(shesha_data)
    shesha = Shesha(config=config, storage=storage)
    cache = PaperCache(cache_dir)
    searcher = ArxivSearcher()
    topic_mgr = TopicManager(shesha=shesha, storage=storage, data_dir=data_dir)

    state = AppState(
        shesha=shesha,
        topic_mgr=topic_mgr,
        cache=cache,
        searcher=searcher,
    )

    # Handle --topic flag
    if args.topic:
        project_id = topic_mgr.resolve(args.topic)
        if project_id:
            state.current_topic = project_id
            docs = topic_mgr._storage.list_documents(project_id)
            print(f"Topic: {args.topic} ({len(docs)} papers)")
        else:
            project_id = topic_mgr.create(args.topic)
            state.current_topic = project_id
            print(f"Created topic: {args.topic}")

    # REPL loop
    try:
        while True:
            try:
                user_input = input("arxiv> ").strip()
            except EOFError:
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                should_quit = dispatch_command(user_input, state)
                if should_quit:
                    break
            else:
                handle_query(user_input, state=state)
    except KeyboardInterrupt:
        print()  # Clean newline after ^C
    finally:
        print("Cleaning up...")
        try:
            shesha.stop()
        except Exception:
            pass  # May not have started


if __name__ == "__main__":
    main()
