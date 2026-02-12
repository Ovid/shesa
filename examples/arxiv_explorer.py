#!/usr/bin/env python3
"""Shesha arXiv Explorer -- search, load, and query arXiv papers."""

from __future__ import annotations

import argparse
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock

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
from shesha.experimental.arxiv.models import (
    CheckReport,
    ExtractedCitation,
    PaperMeta,
    VerificationStatus,
)
from shesha.experimental.arxiv.search import ArxivSearcher
from shesha.experimental.arxiv.topics import TopicManager
from shesha.storage.filesystem import FilesystemStorage

# Guard TUI import: textual is an optional dependency (shesha[tui]).
try:
    from shesha.tui import SheshaTUI
    from shesha.tui.widgets.info_bar import InfoBar
    from shesha.tui.widgets.output_area import OutputArea
except ModuleNotFoundError:
    if __name__ == "__main__":
        print("This example requires the TUI extra: pip install shesha[tui]")
        sys.exit(1)
    else:
        raise

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


def create_app(
    state: AppState,
    model: str | None = None,
    startup_message: str | None = None,
    startup_warning: str | None = None,
) -> SheshaTUI:
    """Create and configure the TUI app with arXiv commands."""
    if state.current_topic:
        info = state.topic_mgr.get_topic_info_by_project_id(state.current_topic)
        project_name = info.name if info else state.current_topic
        project = state.shesha.get_project(state.current_topic)
    else:
        project_name = "No topic"
        # Placeholder project -- queries require a topic, guarded in _run_query
        project = MagicMock()

    # Subclass to inject startup messages via on_mount and guard queries
    # (Textual resolves handlers from the class __dict__, so instance
    # monkey-patching won't work).
    class _ArxivTUI(SheshaTUI):
        def on_mount(self) -> None:
            super().on_mount()
            output = self.query_one(OutputArea)
            if startup_warning:
                output.add_system_message(startup_warning)
            if startup_message:
                output.add_system_message(startup_message)

        def _run_query(self, question: str) -> None:
            output = self.query_one(OutputArea)
            if state.current_topic is None:
                output.add_system_message("No topic selected. Use /topic create <name> first.")
                return
            docs = state.topic_mgr._storage.list_documents(state.current_topic)
            if not docs:
                output.add_system_message(
                    "No papers loaded. Use /search and /topic add to add papers first."
                )
                return
            super()._run_query(question)

    tui = _ArxivTUI(project=project, project_name=project_name, model=model)

    # --- /topic subcommand handlers ---

    def _cmd_topic_help(args: str) -> None:
        """Show topic subcommand usage."""
        output = tui.query_one(OutputArea)
        lines = [
            "Topic management commands:",
            "  /topic list                  List all topics",
            "  /topic switch <name|#>       Switch to a topic (by name or number)",
            "  /topic create <name>         Create a new topic",
            "  /topic delete <name>         Delete a topic",
            "  /topic rename <old> <new>    Rename a topic",
            "  /topic papers                List papers in current topic",
            "  /topic add <#|arxiv-id>...   Add papers from search results or by ID",
        ]
        output.add_system_message("\n".join(lines))

    def _cmd_topic_list(args: str) -> None:
        """List all topics (absorbs /history)."""
        output = tui.query_one(OutputArea)
        topics = state.topic_mgr.list_topics()
        if not topics:
            output.add_system_message("No topics yet. Use /search and /topic add to get started.")
            return
        header = "| # | Topic | Created | Papers | Size |"
        sep = "|---|-------|---------|--------|------|"
        lines = [header, sep]
        for i, t in enumerate(topics, 1):
            created_str = t.created.strftime("%b %d, %Y")
            papers_word = "paper" if t.paper_count == 1 else "papers"
            marker = " **\\***" if t.project_id == state.current_topic else ""
            lines.append(
                f"| {i} | {t.name}{marker} | {created_str} "
                f"| {t.paper_count} {papers_word} | {t.formatted_size} |"
            )
        output.add_system_markdown("\n".join(lines))

    def _cmd_topic_switch(args: str) -> None:
        """Switch to an existing topic by name or number."""
        output = tui.query_one(OutputArea)
        args = args.strip()
        if not args:
            output.add_system_message("Usage: /topic switch <name|#>")
            return
        if args.isdigit():
            topics = state.topic_mgr.list_topics()
            idx = int(args) - 1
            if 0 <= idx < len(topics):
                t = topics[idx]
                state.current_topic = t.project_id
                docs = state.topic_mgr._storage.list_documents(t.project_id)
                tui._project = state.shesha.get_project(t.project_id)
                tui.query_one(InfoBar).update_project_name(t.name)
                output.add_system_message(f"Switched to topic: {t.name} ({len(docs)} papers)")
            else:
                output.add_system_message(
                    f"Invalid topic number: {args}. Use /topic list to see topics."
                )
            return
        project_id = state.topic_mgr.resolve(args)
        if project_id:
            state.current_topic = project_id
            docs = state.topic_mgr._storage.list_documents(project_id)
            tui._project = state.shesha.get_project(project_id)
            tui.query_one(InfoBar).update_project_name(args)
            output.add_system_message(f"Switched to topic: {args} ({len(docs)} papers)")
        else:
            output.add_system_message(
                f"Topic '{args}' not found. Use /topic list to see topics, or /topic create <name>."
            )

    def _cmd_topic_create(args: str) -> None:
        """Create a new topic and switch to it."""
        output = tui.query_one(OutputArea)
        args = args.strip()
        if not args:
            output.add_system_message("Usage: /topic create <name>")
            return
        existing = state.topic_mgr.resolve(args)
        if existing:
            output.add_system_message(
                f"Topic '{args}' already exists. Use /topic switch {args} to switch to it."
            )
            return
        project_id = state.topic_mgr.create(args)
        state.current_topic = project_id
        tui._project = state.shesha.get_project(project_id)
        tui.query_one(InfoBar).update_project_name(args)
        output.add_system_message(f"Created topic: {args}")

    def _cmd_topic_delete(args: str) -> None:
        """Delete a topic."""
        output = tui.query_one(OutputArea)
        args = args.strip()
        if not args:
            output.add_system_message("Usage: /topic delete <name>")
            return
        try:
            deleted_project_id = state.topic_mgr.resolve(args)
            state.topic_mgr.delete(args)
            output.add_system_message(f"Deleted topic: {args}")
            if state.current_topic and state.current_topic == deleted_project_id:
                state.current_topic = None
                tui.query_one(InfoBar).update_project_name("No topic")
        except ValueError as e:
            output.add_system_message(f"Error: {e}")

    def _cmd_topic_rename(args: str) -> None:
        """Rename a topic."""
        output = tui.query_one(OutputArea)
        parts = args.strip().split(maxsplit=1)
        if len(parts) < 2:
            output.add_system_message("Usage: /topic rename <old-name> <new-name>")
            return
        old_name, new_name = parts
        try:
            state.topic_mgr.rename(old_name, new_name)
            output.add_system_message(f"Renamed topic: {old_name} -> {new_name}")
            old_project_id = state.topic_mgr.resolve(new_name)
            if old_project_id == state.current_topic:
                tui.query_one(InfoBar).update_project_name(new_name)
        except ValueError as e:
            output.add_system_message(f"Error: {e}")

    def _cmd_topic_papers(args: str) -> None:
        """List papers in current topic."""
        output = tui.query_one(OutputArea)
        if state.current_topic is None:
            output.add_system_message("No topic selected. Use /topic create <name> first.")
            return
        docs = state.topic_mgr._storage.list_documents(state.current_topic)
        if not docs:
            output.add_system_message("No papers loaded. Use /search and /topic add to add papers.")
            return
        info = state.topic_mgr.get_topic_info_by_project_id(state.current_topic)
        topic_name = info.name if info else state.current_topic
        lines = [f'**Papers in "{topic_name}":**\n']
        for i, doc_name in enumerate(docs, 1):
            meta = state.cache.get_meta(doc_name)
            if meta:
                lines.append(f'{i}. **[{meta.arxiv_id}]** "{meta.title}"')
                lines.append(f"   {meta.arxiv_url}\n")
            else:
                lines.append(f"{i}. {doc_name}")
        output.add_system_markdown("\n".join(lines))

    # --- Threaded commands (use call_from_thread for UI updates) ---

    # Guard: only one threaded command at a time
    _threaded_lock = threading.Lock()

    def _threaded_guard(handler_name: str, handler, args: str) -> None:  # type: ignore[type-arg]
        """Wrapper that enforces one-at-a-time for threaded commands."""
        if not _threaded_lock.acquire(blocking=False):
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message, "Command in progress."
            )
            return
        try:
            handler(args)
        finally:
            _threaded_lock.release()

    def _cmd_search(args: str) -> None:
        args = args.strip()
        if not args:
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                "Usage: /search <query> [--author <name>] [--cat <category>] [--recent <days>]",
            )
            return
        tui.call_from_thread(tui.query_one(InfoBar).update_thinking, 0.0)
        query, kwargs = _parse_search_flags(args)
        results = state.searcher.search(query, **kwargs)
        state.last_search_results = results
        state._search_offset = len(results)
        state._last_search_kwargs = {"query": query, **kwargs}
        if not results:
            tui.call_from_thread(tui.query_one(OutputArea).add_system_message, "No results found.")
            tui.call_from_thread(tui.query_one(InfoBar).reset_phase)
            return
        lines = [f'### Search: "{query}" ({len(results)} results)\n']
        for i, meta in enumerate(results, 1):
            authors = ", ".join(meta.authors[:3])
            if len(meta.authors) > 3:
                authors += f" +{len(meta.authors) - 3} more"
            date_str = meta.published.strftime("%Y-%m-%d")
            lines.append(f'{i}. **[{meta.arxiv_id}]** "{meta.title}"')
            lines.append(f"   {authors} | {meta.primary_category} | {date_str}")
            lines.append(f"   {meta.arxiv_url}\n")
        lines.append(
            "Use /more for next page, /topic add <numbers> to pick, /topic add to load this page."
        )
        tui.call_from_thread(tui.query_one(OutputArea).add_system_markdown, "\n".join(lines))
        tui.call_from_thread(tui.query_one(InfoBar).reset_phase)

    def _cmd_more(args: str) -> None:
        if state._last_search_kwargs is None:
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                "No previous search. Use /search first.",
            )
            return
        tui.call_from_thread(tui.query_one(InfoBar).update_thinking, 0.0)
        offset = state._search_offset
        results = state.searcher.search(**state._last_search_kwargs, max_results=10, start=offset)
        if not results:
            tui.call_from_thread(tui.query_one(OutputArea).add_system_message, "No more results.")
            tui.call_from_thread(tui.query_one(InfoBar).reset_phase)
            return
        start_index = len(state.last_search_results) + 1
        state.last_search_results.extend(results)
        state._search_offset = offset + len(results)
        lines = [f"### Results {start_index}-{start_index + len(results) - 1}\n"]
        for i, meta in enumerate(results, start_index):
            authors = ", ".join(meta.authors[:3])
            if len(meta.authors) > 3:
                authors += f" +{len(meta.authors) - 3} more"
            date_str = meta.published.strftime("%Y-%m-%d")
            lines.append(f'{i}. **[{meta.arxiv_id}]** "{meta.title}"')
            lines.append(f"   {authors} | {meta.primary_category} | {date_str}")
            lines.append(f"   {meta.arxiv_url}\n")
        tui.call_from_thread(tui.query_one(OutputArea).add_system_markdown, "\n".join(lines))
        tui.call_from_thread(tui.query_one(InfoBar).reset_phase)

    def _cmd_topic_add(args: str) -> None:
        """Add papers to current topic. Threaded."""
        if state.current_topic is None:
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                "No topic selected. Use /topic create <name> first.",
            )
            return
        args = args.strip()
        if not args:
            if not state.last_search_results:
                tui.call_from_thread(
                    tui.query_one(OutputArea).add_system_message,
                    "No search results. Use /search first.",
                )
                return
            tokens = [str(i) for i in range(1, len(state.last_search_results) + 1)]
        else:
            tokens = args.split()
        tui.call_from_thread(tui.query_one(InfoBar).update_thinking, 0.0)
        existing_docs = set(state.topic_mgr._storage.list_documents(state.current_topic))
        loaded = 0
        skipped = 0
        for i, token in enumerate(tokens):
            if i > 0 and loaded > 0:
                time.sleep(3)  # Rate limit between downloads
            meta: PaperMeta | None = None
            if token.isdigit():
                idx = int(token) - 1
                if 0 <= idx < len(state.last_search_results):
                    meta = state.last_search_results[idx]
                else:
                    tui.call_from_thread(
                        tui.query_one(OutputArea).add_system_message,
                        f"Invalid result number: {token}",
                    )
                    continue
            elif ARXIV_ID_RE.match(token):
                if state.cache.has(token):
                    meta = state.cache.get_meta(token)
                else:
                    meta = state.searcher.get_by_id(token)
                if meta is None:
                    tui.call_from_thread(
                        tui.query_one(OutputArea).add_system_message,
                        f"Paper not found: {token}",
                    )
                    continue
            else:
                tui.call_from_thread(
                    tui.query_one(OutputArea).add_system_message,
                    f"Invalid input: {token} (use a result number or arXiv ID like 2501.12345)",
                )
                continue
            if meta.arxiv_id in existing_docs:
                skipped += 1
                continue
            updated_meta = download_paper(meta, state.cache)
            doc = to_parsed_document(updated_meta.arxiv_id, state.cache)
            state.topic_mgr._storage.store_document(state.current_topic, doc)
            loaded += 1
            source_label = updated_meta.source_type or "unknown"
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                f'Loaded [{updated_meta.arxiv_id}] "{updated_meta.title}" ({source_label})',
            )
        parts = []
        if loaded:
            parts.append(f"{loaded} paper(s) loaded into topic.")
        if skipped:
            parts.append(f"{skipped} already in topic, skipped.")
        if parts:
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                " ".join(parts),
            )
        tui.call_from_thread(tui.query_one(InfoBar).reset_phase)

    def _cmd_check_citations(args: str) -> None:
        if state.current_topic is None:
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                "No topic selected. Use /topic create <name> first.",
            )
            return
        docs = state.topic_mgr._storage.list_documents(state.current_topic)
        if not docs:
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                "No papers loaded. Use /search and /topic add to add papers first.",
            )
            return
        filter_id = args.strip() if args.strip() else None
        if filter_id:
            docs = [d for d in docs if filter_id in d]
            if not docs:
                tui.call_from_thread(
                    tui.query_one(OutputArea).add_system_message,
                    f"Paper {filter_id} not found in current topic.",
                )
                return
        tui.call_from_thread(tui.query_one(InfoBar).update_thinking, 0.0)
        verifier = ArxivVerifier(searcher=state.searcher)
        for doc_name in docs:
            doc_meta = state.cache.get_meta(doc_name)
            if doc_meta is None:
                tui.call_from_thread(
                    tui.query_one(OutputArea).add_system_message,
                    f"Skipping {doc_name}: no metadata in cache",
                )
                continue
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
                try:
                    doc = state.topic_mgr._storage.get_document(state.current_topic, doc_name)
                    full_text = doc.content
                    citations.extend(extract_citations_from_text(full_text))
                except Exception:
                    full_text = ""  # No source available
            llm_phrases = detect_llm_phrases(full_text)
            arxiv_citations = [c for c in citations if c.arxiv_id is not None]
            if arxiv_citations:
                tui.call_from_thread(
                    tui.query_one(OutputArea).add_system_message,
                    f"Checking citations in {doc_meta.arxiv_id}... "
                    f"Verifying {len(arxiv_citations)} citations with arXiv IDs",
                )
            else:
                tui.call_from_thread(
                    tui.query_one(OutputArea).add_system_message,
                    f"Checking citations in {doc_meta.arxiv_id}...",
                )
            results = []
            for ci, c in enumerate(citations, 1):
                if c.arxiv_id is not None:
                    status_map = {
                        VerificationStatus.VERIFIED: "OK",
                        VerificationStatus.MISMATCH: "MISMATCH",
                        VerificationStatus.NOT_FOUND: "NOT FOUND",
                        VerificationStatus.UNRESOLVED: "?",
                    }
                    tui.call_from_thread(
                        tui.query_one(OutputArea).add_system_message,
                        f"[{ci}/{len(citations)}] {c.key}...",
                    )
                    r = verifier.verify(c)
                    tui.call_from_thread(
                        tui.query_one(OutputArea).add_system_message,
                        f"  -> {status_map[r.status]}",
                    )
                    results.append(r)
                else:
                    results.append(verifier.verify(c))
            report = CheckReport(
                arxiv_id=doc_meta.arxiv_id,
                title=doc_meta.title,
                citations=citations,
                verification_results=results,
                llm_phrases=llm_phrases,
            )
            report_text = format_check_report(report)
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                f"```\n{report_text}\n```",
            )
        tui.call_from_thread(tui.query_one(InfoBar).reset_phase)

    # Register /topic command group
    tui.register_group("/topic", "Topic management")
    tui.register_subcommand("/topic", "list", _cmd_topic_list, "List all topics")
    tui.register_subcommand("/topic", "switch", _cmd_topic_switch, "Switch to a topic")
    tui.register_subcommand("/topic", "create", _cmd_topic_create, "Create a new topic")
    tui.register_subcommand("/topic", "delete", _cmd_topic_delete, "Delete a topic")
    tui.register_subcommand("/topic", "rename", _cmd_topic_rename, "Rename a topic")
    tui.register_subcommand("/topic", "papers", _cmd_topic_papers, "List papers in current topic")
    tui.register_subcommand(
        "/topic",
        "add",
        lambda args: _threaded_guard("add", _cmd_topic_add, args),
        "Add papers from search results",
        threaded=True,
    )
    tui.set_group_help_handler("/topic", _cmd_topic_help)

    tui.register_command(
        "/search",
        lambda args: _threaded_guard("search", _cmd_search, args),
        "Search arXiv",
        threaded=True,
        usage="<query> [--author, --cat, --recent, --sort]",
    )
    tui.register_command(
        "/more",
        lambda args: _threaded_guard("more", _cmd_more, args),
        "Next page of search results",
        threaded=True,
    )
    tui.register_command(
        "/check",
        lambda args: _threaded_guard("check", _cmd_check_citations, args),
        "Verify citations",
        threaded=True,
        usage="[arxiv-id]",
    )

    return tui


def main() -> None:
    """Main entry point."""
    args = parse_args()

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
    topic_mgr = TopicManager(shesha=shesha, storage=storage)

    state = AppState(
        shesha=shesha,
        topic_mgr=topic_mgr,
        cache=cache,
        searcher=searcher,
    )

    startup_message = None
    startup_warning = None

    # Handle --topic flag
    if args.topic:
        project_id = topic_mgr.resolve(args.topic)
        if project_id:
            state.current_topic = project_id
            docs = topic_mgr._storage.list_documents(project_id)
            info = topic_mgr.get_topic_info_by_project_id(project_id)
            topic_name = info.name if info else args.topic
            startup_message = f"Switched to topic: {topic_name} ({len(docs)} papers)"
        else:
            startup_warning = (
                f"Topic '{args.topic}' not found. "
                "Use /topic list to see existing topics, or /topic create <name>."
            )

    tui = create_app(
        state,
        model=config.model,
        startup_message=startup_message,
        startup_warning=startup_warning,
    )
    tui.run()
    print("Cleaning up...")
    searcher.close()
    try:
        shesha.stop()
    except Exception:
        pass  # May not have started


if __name__ == "__main__":
    main()
