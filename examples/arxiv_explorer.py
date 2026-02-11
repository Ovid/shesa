#!/usr/bin/env python3
"""Shesha arXiv Explorer -- search, load, and query arXiv papers."""

from __future__ import annotations

import argparse
import re
import sys
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
                output.add_system_message(
                    "No topic selected. Use /topic <name> first."
                )
                return
            docs = state.topic_mgr._storage.list_documents(state.current_topic)
            if not docs:
                output.add_system_message(
                    "No papers loaded. Use /search and /load to add papers first."
                )
                return
            super()._run_query(question)

    tui = _ArxivTUI(project=project, project_name=project_name, model=model)

    # --- Non-threaded commands ---

    def _cmd_papers(args: str) -> None:
        output = tui.query_one(OutputArea)
        if state.current_topic is None:
            output.add_system_message("No topic selected. Use /topic <name> first.")
            return
        docs = state.topic_mgr._storage.list_documents(state.current_topic)
        if not docs:
            output.add_system_message("No papers loaded. Use /search and /load to add papers.")
            return
        info = state.topic_mgr.get_topic_info_by_project_id(state.current_topic)
        topic_name = info.name if info else state.current_topic
        lines = [f'**Papers in "{topic_name}":**\n']
        for i, doc_name in enumerate(docs, 1):
            meta = state.cache.get_meta(doc_name)
            if meta:
                lines.append(
                    f"{i}. \\[{meta.arxiv_id}\\] *{meta.title}*  \n"
                    f"   {meta.arxiv_url}"
                )
            else:
                lines.append(f"{i}. {doc_name}")
        output.add_system_markdown("\n".join(lines))

    def _cmd_topic(args: str) -> None:
        output = tui.query_one(OutputArea)
        args = args.strip()
        if not args:
            if state.current_topic:
                info = state.topic_mgr.get_topic_info_by_project_id(state.current_topic)
                name = info.name if info else state.current_topic
                output.add_system_message(f"Current topic: {name}")
            else:
                output.add_system_message(
                    "No topic selected. Use /topic <name> to create or switch."
                )
            return

        parts = args.split(maxsplit=1)

        # /topic delete <name>
        if parts[0] == "delete" and len(parts) > 1:
            name = parts[1]
            try:
                state.topic_mgr.delete(name)
                output.add_system_message(f"Deleted topic: {name}")
                if state.current_topic and name in state.current_topic:
                    state.current_topic = None
                    tui.query_one(InfoBar).update_project_name("No topic")
            except ValueError as e:
                output.add_system_message(f"Error: {e}")
            return

        # /topic rename <old> <new>
        if parts[0] == "rename" and len(parts) > 1:
            rename_parts = parts[1].split(maxsplit=1)
            if len(rename_parts) < 2:
                output.add_system_message("Usage: /topic rename <old-name> <new-name>")
                return
            old_name, new_name = rename_parts
            try:
                state.topic_mgr.rename(old_name, new_name)
                output.add_system_message(f"Renamed topic: {old_name} -> {new_name}")
                # Update InfoBar if renaming current topic
                old_project_id = state.topic_mgr.resolve(new_name)
                if old_project_id == state.current_topic:
                    tui.query_one(InfoBar).update_project_name(new_name)
            except ValueError as e:
                output.add_system_message(f"Error: {e}")
            return

        # /topic <name> — switch or create
        name = args
        project_id = state.topic_mgr.resolve(name)
        if project_id:
            state.current_topic = project_id
            docs = state.topic_mgr._storage.list_documents(project_id)
            tui._project = state.shesha.get_project(project_id)
            tui.query_one(InfoBar).update_project_name(name)
            output.add_system_message(f"Switched to topic: {name} ({len(docs)} papers)")
        else:
            project_id = state.topic_mgr.create(name)
            state.current_topic = project_id
            tui._project = state.shesha.get_project(project_id)
            tui.query_one(InfoBar).update_project_name(name)
            output.add_system_message(f"Created topic: {name}")

    def _cmd_history(args: str) -> None:
        output = tui.query_one(OutputArea)
        topics = state.topic_mgr.list_topics()
        if not topics:
            output.add_system_message("No topics yet. Use /search and /load to get started.")
            return
        lines = ["| # | Topic | Created | Papers | Size |", "|---|-------|---------|--------|------|"]
        for i, t in enumerate(topics, 1):
            created_str = t.created.strftime("%b %d, %Y")
            papers_word = "paper" if t.paper_count == 1 else "papers"
            marker = " **\\***" if t.project_id == state.current_topic else ""
            lines.append(
                f"| {i} | {t.name}{marker} | {created_str} "
                f"| {t.paper_count} {papers_word} | {t.formatted_size} |"
            )
        output.add_system_markdown("\n".join(lines))

    # --- Threaded commands (use call_from_thread for UI updates) ---

    def _cmd_search(args: str) -> None:
        args = args.strip()
        if not args:
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                "Usage: /search <query> [--author <name>] [--cat <category>] [--recent <days>]",
            )
            return
        query, kwargs = _parse_search_flags(args)
        results = state.searcher.search(query, **kwargs)
        state.last_search_results = results
        state._search_offset = len(results)
        state._last_search_kwargs = {"query": query, **kwargs}
        if not results:
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message, "No results found."
            )
            return
        lines = [f"**Found {len(results)} results:**\n"]
        for i, meta in enumerate(results, 1):
            lines.append(
                f"{i}. \\[{meta.arxiv_id}\\] *{meta.title}*  \n"
                f"   {', '.join(meta.authors[:3])}"
                + (f" +{len(meta.authors) - 3} more" if len(meta.authors) > 3 else "")
                + f" | {meta.primary_category} | {meta.published.strftime('%Y-%m-%d')}  \n"
                f"   {meta.arxiv_url}"
            )
        lines.append("\nUse /more for next page, /load <numbers> to pick, /load to load this page.")
        tui.call_from_thread(tui.query_one(OutputArea).add_system_markdown, "\n".join(lines))

    def _cmd_more(args: str) -> None:
        if state._last_search_kwargs is None:
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                "No previous search. Use /search first.",
            )
            return
        offset = state._search_offset
        results = state.searcher.search(**state._last_search_kwargs, max_results=10, start=offset)
        if not results:
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message, "No more results."
            )
            return
        start_index = len(state.last_search_results) + 1
        state.last_search_results.extend(results)
        state._search_offset = offset + len(results)
        lines = [f"**Results {start_index}-{start_index + len(results) - 1}:**\n"]
        for i, meta in enumerate(results, start_index):
            lines.append(
                f"{i}. \\[{meta.arxiv_id}\\] *{meta.title}*  \n"
                f"   {', '.join(meta.authors[:3])}"
                + (f" +{len(meta.authors) - 3} more" if len(meta.authors) > 3 else "")
                + f" | {meta.primary_category} | {meta.published.strftime('%Y-%m-%d')}  \n"
                f"   {meta.arxiv_url}"
            )
        tui.call_from_thread(tui.query_one(OutputArea).add_system_markdown, "\n".join(lines))

    def _cmd_load(args: str) -> None:
        if state.current_topic is None:
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                "No topic selected. Use /topic <name> first.",
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
        loaded = 0
        for i, token in enumerate(tokens):
            if i > 0:
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
            updated_meta = download_paper(meta, state.cache)
            doc = to_parsed_document(updated_meta.arxiv_id, state.cache)
            state.topic_mgr._storage.store_document(state.current_topic, doc)
            loaded += 1
            source_label = updated_meta.source_type or "unknown"
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                f'Loaded [{updated_meta.arxiv_id}] "{updated_meta.title}" ({source_label})',
            )
        if loaded:
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                f"{loaded} paper(s) loaded into topic.",
            )

    def _cmd_check_citations(args: str) -> None:
        if state.current_topic is None:
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                "No topic selected. Use /topic <name> first.",
            )
            return
        docs = state.topic_mgr._storage.list_documents(state.current_topic)
        if not docs:
            tui.call_from_thread(
                tui.query_one(OutputArea).add_system_message,
                "No papers loaded. Use /search and /load to add papers first.",
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
                    doc = state.topic_mgr._storage.get_document(
                        state.current_topic, doc_name
                    )
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

    tui.register_command("/papers", _cmd_papers, "List papers in current topic")
    tui.register_command("/topic", _cmd_topic, "Topic management (switch/create/delete/rename)")
    tui.register_command("/history", _cmd_history, "List all topics")
    tui.register_command("/search", _cmd_search, "Search arXiv", threaded=True)
    tui.register_command("/more", _cmd_more, "Next page of search results", threaded=True)
    tui.register_command("/load", _cmd_load, "Load papers into topic", threaded=True)
    tui.register_command(
        "/check-citations",
        _cmd_check_citations,
        "Citation verification",
        threaded=True,
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
    topic_mgr = TopicManager(shesha=shesha, storage=storage, data_dir=data_dir)

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
                "Use /history to see existing topics, or /topic <name> to create one."
            )

    tui = create_app(
        state,
        model=config.model,
        startup_message=startup_message,
        startup_warning=startup_warning,
    )
    tui.run()
    print("Cleaning up...")
    try:
        shesha.stop()
    except Exception:
        pass  # May not have started


if __name__ == "__main__":
    main()
