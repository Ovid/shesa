# arXiv Explorer TUI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert `examples/arxiv_explorer.py` from a readline-based CLI to a Textual TUI by registering arXiv commands in the existing `SheshaTUI`, following the `examples/barsoom.py` pattern.

**Architecture:** No new widgets, screens, or subclasses. All arXiv functionality is registered as slash commands in `SheshaTUI` via `register_command()`. Output renders inline in `OutputArea` as markdown or system messages. Threaded handlers keep the UI responsive during network I/O. Conversational queries go through the RLM engine against loaded papers.

**Tech Stack:** Python 3.12, Textual, shesha TUI framework, arxiv Python library

**Design document:** `docs/plans/2026-02-11-arxiv-tui-design.md`

---

### Task 1: Add `TopicManager.rename()` method

The design requires `/topic rename <old> <new>`. This needs a new method on `TopicManager`.

**Files:**
- Test: `tests/unit/experimental/arxiv/test_topics.py`
- Modify: `src/shesha/experimental/arxiv/topics.py`

**Step 1: Write the failing test**

```python
# In tests/unit/experimental/arxiv/test_topics.py, add:

class TestTopicRename:
    """Tests for TopicManager.rename()."""

    def test_rename_updates_topic_meta(self, tmp_path: Path) -> None:
        """Renaming a topic changes the name in _topic.json."""
        from shesha.experimental.arxiv.topics import TopicManager

        storage = MagicMock()
        storage.list_projects.return_value = ["2026-01-15-old-name"]
        shesha = MagicMock()

        mgr = TopicManager(shesha=shesha, storage=storage, data_dir=tmp_path)

        # Create the project directory and _topic.json
        project_dir = tmp_path / "projects" / "2026-01-15-old-name"
        project_dir.mkdir(parents=True)
        meta = {"name": "old-name", "created": "2026-01-15T00:00:00+00:00"}
        (project_dir / "_topic.json").write_text(json.dumps(meta))

        mgr.rename("old-name", "new-name")

        updated = json.loads((project_dir / "_topic.json").read_text())
        assert updated["name"] == "new-name"

    def test_rename_not_found_raises(self, tmp_path: Path) -> None:
        """Renaming a non-existent topic raises ValueError."""
        from shesha.experimental.arxiv.topics import TopicManager

        storage = MagicMock()
        storage.list_projects.return_value = []
        shesha = MagicMock()

        mgr = TopicManager(shesha=shesha, storage=storage, data_dir=tmp_path)

        with pytest.raises(ValueError, match="Topic not found"):
            mgr.rename("nonexistent", "new-name")
```

Add `import json` and `from pathlib import Path` at the top of the test file if not already present.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/experimental/arxiv/test_topics.py::TestTopicRename -v`
Expected: FAIL with `AttributeError: 'TopicManager' object has no attribute 'rename'`

**Step 3: Write minimal implementation**

```python
# In src/shesha/experimental/arxiv/topics.py, add method to TopicManager class:

    def rename(self, old_name: str, new_name: str) -> None:
        """Rename a topic's display name (does not rename filesystem directory)."""
        project_id = self.resolve(old_name)
        if project_id is None:
            msg = f"Topic not found: {old_name}"
            raise ValueError(msg)
        new_slug = slugify(new_name)
        meta_path = self._project_path(project_id) / self.TOPIC_META_FILE
        meta = json.loads(meta_path.read_text())
        meta["name"] = new_slug
        meta_path.write_text(json.dumps(meta, indent=2))
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/experimental/arxiv/test_topics.py::TestTopicRename -v`
Expected: PASS

**Step 5: Run full suite**

Run: `make all`
Expected: All green

**Step 6: Commit**

```bash
git add tests/unit/experimental/arxiv/test_topics.py src/shesha/experimental/arxiv/topics.py
git commit -m "feat: add TopicManager.rename() for topic display name changes"
```

---

### Task 2: Add `InfoBar.update_project_name()` method

The InfoBar currently has no way to change the project name after construction. Topic switching in the TUI needs to update it.

**Files:**
- Test: `tests/unit/tui/test_info_bar.py`
- Modify: `src/shesha/tui/widgets/info_bar.py`

**Step 1: Write the failing test**

```python
# In tests/unit/tui/test_info_bar.py, add:

class TestInfoBarProjectNameUpdate:
    """Tests for updating project name after construction."""

    def test_update_project_name_changes_state(self) -> None:
        """Updating project name changes the rendered output."""
        state = InfoBarState(project_name="old-project", model="gpt-4o")
        state.project_name = "new-topic"
        line1, _ = state.render_lines()
        assert "new-topic" in line1
        assert "old-project" not in line1

    async def test_info_bar_update_project_name_widget(self) -> None:
        """InfoBar.update_project_name() updates the rendered widget text."""
        from shesha.tui.app import SheshaTUI
        from shesha.tui.widgets.info_bar import InfoBar

        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            info_bar = pilot.app.query_one(InfoBar)
            info_bar.update_project_name("new-topic")
            line1, _ = info_bar._state.render_lines()
            assert "new-topic" in line1
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/tui/test_info_bar.py::TestInfoBarProjectNameUpdate -v`
Expected: FAIL — `InfoBar` has no method `update_project_name`

**Step 3: Write minimal implementation**

```python
# In src/shesha/tui/widgets/info_bar.py, add method to InfoBar class:

    def update_project_name(self, name: str) -> None:
        """Update the displayed project name."""
        self._state.project_name = name
        self._refresh_content()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/tui/test_info_bar.py::TestInfoBarProjectNameUpdate -v`
Expected: PASS

**Step 5: Run full suite**

Run: `make all`
Expected: All green

**Step 6: Commit**

```bash
git add tests/unit/tui/test_info_bar.py src/shesha/tui/widgets/info_bar.py
git commit -m "feat: add InfoBar.update_project_name() for dynamic topic switching"
```

---

### Task 3: Scaffold TUI entry point in `examples/arxiv_explorer.py`

Rewrite `main()` to launch `SheshaTUI` instead of a readline REPL. Keep `AppState`, `parse_args()`, and `_parse_search_flags()`. Replace the REPL loop with TUI startup. Register one command (`/help`) to verify the pattern works. All other handlers migrate in subsequent tasks.

**Files:**
- Test: `tests/examples/test_arxiv.py`
- Modify: `examples/arxiv_explorer.py`

**Step 1: Write the failing test**

Replace the existing `TestMainFunction` class and add a new TUI test:

```python
# In tests/examples/test_arxiv.py, add at the top with other imports:
# (guarded import like barsoom.py)
import pytest
from unittest.mock import MagicMock, patch

# Then add:

class TestTUIStartup:
    """Tests for the TUI-based main entry point."""

    async def test_tui_mounts_with_no_topic(self) -> None:
        """App starts with 'No topic' in info bar when no --topic passed."""
        from shesha.tui.widgets.info_bar import InfoBar
        from shesha.tui.widgets.output_area import OutputArea

        from arxiv_explorer import create_app, AppState

        state = MagicMock(spec=AppState)
        state.current_topic = None
        state.shesha = MagicMock()
        state.topic_mgr = MagicMock()
        state.cache = MagicMock()
        state.searcher = MagicMock()
        state.last_search_results = []
        state._search_offset = 0
        state._last_search_kwargs = None

        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            info_bar = pilot.app.query_one(InfoBar)
            line1, _ = info_bar._state.render_lines()
            assert "No topic" in line1

    async def test_tui_mounts_with_topic(self) -> None:
        """App starts showing topic name in info bar when topic is set."""
        from shesha.tui.widgets.info_bar import InfoBar

        from arxiv_explorer import create_app, AppState

        state = MagicMock(spec=AppState)
        state.current_topic = "2026-01-15-quantum"
        state.shesha = MagicMock()
        state.topic_mgr = MagicMock()
        state.topic_mgr.get_topic_info_by_project_id.return_value = MagicMock(name="quantum")
        state.cache = MagicMock()
        state.searcher = MagicMock()
        state.last_search_results = []
        state._search_offset = 0
        state._last_search_kwargs = None

        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            info_bar = pilot.app.query_one(InfoBar)
            line1, _ = info_bar._state.render_lines()
            assert "quantum" in line1
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/examples/test_arxiv.py::TestTUIStartup -v`
Expected: FAIL — `cannot import name 'create_app' from 'arxiv_explorer'`

**Step 3: Write minimal implementation**

Rewrite `examples/arxiv_explorer.py`. Key changes:

1. Remove `import readline`, `from collections.abc import Callable` (no longer needed)
2. Remove `dispatch_command()`, `COMMANDS` dict, `main()` REPL loop, `handle_help()` (TUI has its own /help)
3. Add guarded TUI imports (like barsoom.py)
4. Add `create_app(state, model)` function that returns a `SheshaTUI`
5. New `main()` launches the TUI

```python
# Keep: parse_args, AppState, _parse_search_flags, STARTUP_BANNER, DEFAULT_DATA_DIR, ARXIV_ID_RE
# Keep: all handle_* functions (they'll be migrated to TUI handlers in later tasks)
# Remove: handle_help, COMMANDS dict, dispatch_command, readline import
# Add:

# Guard TUI import (like barsoom.py)
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


def create_app(state: AppState, model: str | None = None) -> SheshaTUI:
    """Create and configure the TUI app with arXiv commands.

    Args:
        state: Application state with shesha, topic_mgr, cache, searcher.
        model: LLM model name for display in InfoBar.

    Returns:
        Configured SheshaTUI ready to .run().
    """
    # Determine project and project name
    if state.current_topic:
        info = state.topic_mgr.get_topic_info_by_project_id(state.current_topic)
        project_name = info.name if info else state.current_topic
        project = state.shesha.get_project(state.current_topic)
    else:
        project_name = "No topic"
        project = MagicMock()  # Placeholder — queries require a topic

    tui = SheshaTUI(
        project=project,
        project_name=project_name,
        model=model,
    )

    # Commands will be registered in subsequent tasks
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

    # Handle --topic flag (design: warn on unknown, don't auto-create)
    if args.topic:
        project_id = topic_mgr.resolve(args.topic)
        if project_id:
            state.current_topic = project_id

    tui = create_app(state, model=config.model)

    # Show startup messages after mount
    if args.topic and state.current_topic is None:
        # Unknown topic — show warning after app mounts
        tui._startup_warning = (
            f"Topic '{args.topic}' not found. "
            f"Use /history to see existing topics, or /topic <name> to create one."
        )
    elif state.current_topic:
        docs = topic_mgr._storage.list_documents(state.current_topic)
        info = topic_mgr.get_topic_info_by_project_id(state.current_topic)
        topic_name = info.name if info else args.topic
        tui._startup_message = f"Switched to topic: {topic_name} ({len(docs)} papers)"

    tui.run()
    print("Cleaning up...")
    try:
        shesha.stop()
    except Exception:
        pass  # May not have started
```

Note: The `_startup_warning` and `_startup_message` attributes are temporary — they'll need to be displayed in `on_mount()`. Since we can't subclass SheshaTUI (design constraint), we'll post these messages in a `set_timer(0.1, ...)` call right after creating the app. We'll handle this properly in Task 5 (startup flow).

For this task, the minimal implementation is just `create_app()` + the TUI launch in `main()`. Startup messages come in Task 5.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/examples/test_arxiv.py::TestTUIStartup -v`
Expected: PASS

**Step 5: Run full suite**

Run: `make all`
Expected: All green (old CLI tests that test handle_* functions still pass since those functions still exist)

**Step 6: Commit**

```bash
git add examples/arxiv_explorer.py tests/examples/test_arxiv.py
git commit -m "feat: scaffold TUI entry point for arXiv explorer"
```

---

### Task 4: Register non-threaded commands (/papers, /topic, /history)

These commands don't do network I/O, so they run on the main thread. Each handler adapts the existing CLI handler to use OutputArea instead of `print()`.

**Files:**
- Test: `tests/examples/test_arxiv.py`
- Modify: `examples/arxiv_explorer.py`

**Step 1: Write the failing tests**

```python
class TestTUICommands:
    """Tests for TUI-registered slash commands."""

    async def test_papers_command_no_topic(self) -> None:
        """'/papers' with no topic shows error in OutputArea."""
        from shesha.tui.widgets.output_area import OutputArea

        from arxiv_explorer import create_app, AppState

        state = MagicMock(spec=AppState)
        state.current_topic = None
        state.shesha = MagicMock()
        state.topic_mgr = MagicMock()
        state.cache = MagicMock()
        state.searcher = MagicMock()
        state.last_search_results = []
        state._search_offset = 0
        state._last_search_kwargs = None

        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            # Directly dispatch the command
            app._command_registry.dispatch("/papers")
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            text = "\n".join(s.renderable for s in statics if hasattr(s, 'renderable'))
            assert "No topic" in text or "topic" in text.lower()

    async def test_topic_command_creates_and_switches(self) -> None:
        """'/topic quantum' creates topic and updates InfoBar."""
        from shesha.tui.widgets.info_bar import InfoBar

        from arxiv_explorer import create_app, AppState

        state = MagicMock(spec=AppState)
        state.current_topic = None
        state.shesha = MagicMock()
        state.topic_mgr = MagicMock()
        state.topic_mgr.resolve.return_value = None
        state.topic_mgr.create.return_value = "2026-02-11-quantum"
        state.cache = MagicMock()
        state.searcher = MagicMock()
        state.last_search_results = []
        state._search_offset = 0
        state._last_search_kwargs = None

        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            app._command_registry.dispatch("/topic quantum")
            await pilot.pause()
            info_bar = pilot.app.query_one(InfoBar)
            line1, _ = info_bar._state.render_lines()
            assert "quantum" in line1

    async def test_history_command_empty(self) -> None:
        """'/history' with no topics shows helpful message."""
        from shesha.tui.widgets.output_area import OutputArea

        from arxiv_explorer import create_app, AppState

        state = MagicMock(spec=AppState)
        state.current_topic = None
        state.shesha = MagicMock()
        state.topic_mgr = MagicMock()
        state.topic_mgr.list_topics.return_value = []
        state.cache = MagicMock()
        state.searcher = MagicMock()
        state.last_search_results = []
        state._search_offset = 0
        state._last_search_kwargs = None

        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            app._command_registry.dispatch("/history")
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            assert len(statics) > 0  # Shows "no topics" message

    async def test_topic_rename_command(self) -> None:
        """'/topic rename old new' calls TopicManager.rename()."""
        from arxiv_explorer import create_app, AppState

        state = MagicMock(spec=AppState)
        state.current_topic = "2026-01-15-old"
        state.shesha = MagicMock()
        state.topic_mgr = MagicMock()
        state.topic_mgr.get_topic_info_by_project_id.return_value = MagicMock(name="old")
        state.cache = MagicMock()
        state.searcher = MagicMock()
        state.last_search_results = []
        state._search_offset = 0
        state._last_search_kwargs = None

        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            app._command_registry.dispatch("/topic rename old new")
            await pilot.pause()
            state.topic_mgr.rename.assert_called_once_with("old", "new")
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/examples/test_arxiv.py::TestTUICommands -v`
Expected: FAIL — commands not registered

**Step 3: Write minimal implementation**

In `create_app()`, register the commands. Each handler is a closure over `state` and the `tui` instance:

```python
def create_app(state: AppState, model: str | None = None) -> SheshaTUI:
    # ... (project/project_name setup from Task 3) ...

    tui = SheshaTUI(project=project, project_name=project_name, model=model)

    # --- Non-threaded commands ---

    def cmd_papers(args: str) -> None:
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
        lines = [f'### Papers in "{topic_name}"\n']
        for i, doc_name in enumerate(docs, 1):
            meta = state.cache.get_meta(doc_name)
            if meta:
                lines.append(f'{i}. **[{meta.arxiv_id}]** "{meta.title}"')
                lines.append(f"   {meta.arxiv_url}\n")
            else:
                lines.append(f"{i}. {doc_name}\n")
        output.add_system_markdown("\n".join(lines))

    def cmd_topic(args: str) -> None:
        output = tui.query_one(OutputArea)
        info_bar = tui.query_one(InfoBar)
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

        parts = args.split(maxsplit=2)

        # /topic delete <name>
        if parts[0] == "delete" and len(parts) > 1:
            name = parts[1]
            try:
                state.topic_mgr.delete(name)
                output.add_system_message(f"Deleted topic: {name}")
                if state.current_topic and name in state.current_topic:
                    state.current_topic = None
                    info_bar.update_project_name("No topic")
                    tui._project = MagicMock()
            except ValueError as e:
                output.add_system_message(f"Error: {e}")
            return

        # /topic rename <old> <new>
        if parts[0] == "rename" and len(parts) > 2:
            old_name, new_name = parts[1], parts[2]
            try:
                state.topic_mgr.rename(old_name, new_name)
                output.add_system_message(f"Renamed topic: {old_name} → {new_name}")
                # If renamed topic is the current one, update InfoBar
                if state.current_topic:
                    info = state.topic_mgr.get_topic_info_by_project_id(state.current_topic)
                    if info:
                        info_bar.update_project_name(info.name)
            except ValueError as e:
                output.add_system_message(f"Error: {e}")
            return

        # /topic <name> — switch or create
        name = args
        project_id = state.topic_mgr.resolve(name)
        if project_id:
            state.current_topic = project_id
            docs = state.topic_mgr._storage.list_documents(project_id)
            output.add_system_message(f"Switched to topic: {name} ({len(docs)} papers)")
            tui._project = state.shesha.get_project(project_id)
        else:
            project_id = state.topic_mgr.create(name)
            state.current_topic = project_id
            output.add_system_message(f"Created topic: {name}")
            tui._project = state.shesha.get_project(project_id)
        info_bar.update_project_name(name)

    def cmd_history(args: str) -> None:
        output = tui.query_one(OutputArea)
        topics = state.topic_mgr.list_topics()
        if not topics:
            output.add_system_message(
                "No topics yet. Use /search and /load to get started."
            )
            return
        lines = ["### Topics\n"]
        lines.append("| # | Name | Created | Papers | Size |")
        lines.append("|---|------|---------|--------|------|")
        for i, t in enumerate(topics, 1):
            created_str = t.created.strftime("%b %d, %Y")
            papers_word = "paper" if t.paper_count == 1 else "papers"
            marker = " **\\***" if t.project_id == state.current_topic else ""
            lines.append(
                f"| {i} | {t.name}{marker} | {created_str} "
                f"| {t.paper_count} {papers_word} | {t.formatted_size} |"
            )
        output.add_system_markdown("\n".join(lines))

    tui.register_command("/papers", cmd_papers, "List loaded papers")
    tui.register_command("/topic", cmd_topic, "Topic management")
    tui.register_command("/history", cmd_history, "List all topics")

    return tui
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/examples/test_arxiv.py::TestTUICommands -v`
Expected: PASS

**Step 5: Run full suite**

Run: `make all`
Expected: All green

**Step 6: Commit**

```bash
git add examples/arxiv_explorer.py tests/examples/test_arxiv.py
git commit -m "feat: register /papers, /topic, /history TUI commands"
```

---

### Task 5: Startup flow and `--topic` flag behavior

Implement the startup messages: topic resolved → show paper count, topic not found → show warning, no topic → silent start.

**Files:**
- Test: `tests/examples/test_arxiv.py`
- Modify: `examples/arxiv_explorer.py`

**Step 1: Write the failing tests**

```python
class TestTUIStartupMessages:
    """Tests for --topic flag behavior on startup."""

    async def test_unknown_topic_shows_warning(self) -> None:
        """Unknown --topic shows warning in OutputArea, no topic selected."""
        from shesha.tui.widgets.output_area import OutputArea

        from arxiv_explorer import create_app, AppState

        state = MagicMock(spec=AppState)
        state.current_topic = None
        state.shesha = MagicMock()
        state.topic_mgr = MagicMock()
        state.cache = MagicMock()
        state.searcher = MagicMock()
        state.last_search_results = []
        state._search_offset = 0
        state._last_search_kwargs = None

        app = create_app(state, model="gpt-4o", startup_warning="Topic 'typo' not found. Use /history to see existing topics, or /topic <name> to create one.")
        async with app.run_test() as pilot:
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.renderable) for s in statics if hasattr(s, 'renderable')]
            assert any("not found" in t for t in texts)

    async def test_known_topic_shows_message(self) -> None:
        """Known --topic shows 'Switched to topic' in OutputArea."""
        from shesha.tui.widgets.output_area import OutputArea

        from arxiv_explorer import create_app, AppState

        state = MagicMock(spec=AppState)
        state.current_topic = "2026-01-15-quantum"
        state.shesha = MagicMock()
        state.topic_mgr = MagicMock()
        state.topic_mgr.get_topic_info_by_project_id.return_value = MagicMock(name="quantum")
        state.cache = MagicMock()
        state.searcher = MagicMock()
        state.last_search_results = []
        state._search_offset = 0
        state._last_search_kwargs = None

        app = create_app(state, model="gpt-4o", startup_message="Switched to topic: quantum (3 papers)")
        async with app.run_test() as pilot:
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.renderable) for s in statics if hasattr(s, 'renderable')]
            assert any("Switched to topic" in t for t in texts)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/examples/test_arxiv.py::TestTUIStartupMessages -v`
Expected: FAIL — `create_app()` doesn't accept `startup_warning`/`startup_message`

**Step 3: Write minimal implementation**

Add `startup_message` and `startup_warning` params to `create_app()`. Use Textual's `on_mount` callback pattern — since we can't subclass SheshaTUI, we register a `set_timer(0, ...)` callback after creating the app:

```python
def create_app(
    state: AppState,
    model: str | None = None,
    startup_message: str | None = None,
    startup_warning: str | None = None,
) -> SheshaTUI:
    # ... (existing setup) ...

    tui = SheshaTUI(project=project, project_name=project_name, model=model)

    # ... (register commands) ...

    # Schedule startup messages (displayed after app mounts)
    original_on_mount = tui.on_mount

    def patched_on_mount() -> None:
        original_on_mount()
        output = tui.query_one(OutputArea)
        if startup_warning:
            output.add_system_message(startup_warning)
        if startup_message:
            output.add_system_message(startup_message)

    tui.on_mount = patched_on_mount  # type: ignore[assignment]

    return tui
```

Update `main()` to pass the right startup message/warning:

```python
    startup_message = None
    startup_warning = None

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

    tui = create_app(state, model=config.model, startup_message=startup_message, startup_warning=startup_warning)
    tui.run()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/examples/test_arxiv.py::TestTUIStartupMessages -v`
Expected: PASS

**Step 5: Run full suite**

Run: `make all`
Expected: All green

**Step 6: Commit**

```bash
git add examples/arxiv_explorer.py tests/examples/test_arxiv.py
git commit -m "feat: implement startup flow with --topic flag behavior"
```

---

### Task 6: Register threaded `/search` and `/more` commands

These do network I/O via `ArxivSearcher`, so they must run in worker threads. UI updates go through `app.call_from_thread()`.

**Files:**
- Test: `tests/examples/test_arxiv.py`
- Modify: `examples/arxiv_explorer.py`

**Step 1: Write the failing tests**

```python
class TestTUISearchCommands:
    """Tests for threaded /search and /more commands."""

    async def test_search_shows_results_in_output(self) -> None:
        """'/search quantum' shows results in OutputArea."""
        from datetime import UTC, datetime

        from shesha.tui.widgets.output_area import OutputArea

        from arxiv_explorer import create_app, AppState
        from shesha.experimental.arxiv.models import PaperMeta

        state = MagicMock(spec=AppState)
        state.current_topic = None
        state.shesha = MagicMock()
        state.topic_mgr = MagicMock()
        state.cache = MagicMock()
        state.searcher = MagicMock()
        state.last_search_results = []
        state._search_offset = 0
        state._last_search_kwargs = None

        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Quantum Test",
            authors=["Alice"],
            abstract="",
            published=datetime(2025, 1, 1, tzinfo=UTC),
            updated=datetime(2025, 1, 1, tzinfo=UTC),
            categories=["cs.AI"],
            primary_category="cs.AI",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/2501.12345",
        )
        state.searcher.search.return_value = [meta]

        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            # Run the threaded search handler directly (simulating dispatch)
            worker = app.run_worker(
                lambda: app._command_registry.resolve("/search quantum")[0]("quantum"),
                thread=True,
            )
            await worker.wait()
            await pilot.pause()
            # Verify results appeared
            assert len(state.last_search_results) == 1

    async def test_search_empty_shows_usage(self) -> None:
        """'/search' with no args shows usage in OutputArea."""
        from shesha.tui.widgets.output_area import OutputArea

        from arxiv_explorer import create_app, AppState

        state = MagicMock(spec=AppState)
        state.current_topic = None
        state.shesha = MagicMock()
        state.topic_mgr = MagicMock()
        state.cache = MagicMock()
        state.searcher = MagicMock()
        state.last_search_results = []
        state._search_offset = 0
        state._last_search_kwargs = None

        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            worker = app.run_worker(
                lambda: app._command_registry.resolve("/search ")[0](""),
                thread=True,
            )
            await worker.wait()
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            assert len(statics) > 0  # Shows usage message
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/examples/test_arxiv.py::TestTUISearchCommands -v`
Expected: FAIL — `/search` not registered

**Step 3: Write minimal implementation**

In `create_app()`, add:

```python
    def cmd_search(args: str) -> None:
        """Threaded: search arXiv."""
        output = tui.query_one(OutputArea)
        info_bar = tui.query_one(InfoBar)
        args = args.strip()
        if not args:
            tui.call_from_thread(
                output.add_system_message,
                "Usage: /search <query> [--author <name>] [--cat <category>] "
                "[--recent <days>] [--sort relevance|date|updated]",
            )
            return

        tui.call_from_thread(info_bar.update_thinking, 0.0)
        query, kwargs = _parse_search_flags(args)
        results = state.searcher.search(query, **kwargs)
        state.last_search_results = results
        state._search_offset = len(results)
        state._last_search_kwargs = {"query": query, **kwargs}

        if not results:
            tui.call_from_thread(output.add_system_message, "No results found.")
            tui.call_from_thread(info_bar.reset_phase)
            return

        lines = [f"### Search: \"{query}\" ({len(results)} results)\n"]
        for i, meta in enumerate(results, 1):
            authors = ", ".join(meta.authors[:3])
            if len(meta.authors) > 3:
                authors += f" +{len(meta.authors) - 3} more"
            date_str = meta.published.strftime("%Y-%m-%d")
            lines.append(f"{i}. **[{meta.arxiv_id}]** \"{meta.title}\"")
            lines.append(f"   {authors} | {meta.primary_category} | {date_str}")
            lines.append(f"   {meta.arxiv_url}\n")
        lines.append(
            "Use /more for next page, /load <numbers> to pick, /load to load this page."
        )
        tui.call_from_thread(output.add_system_markdown, "\n".join(lines))
        tui.call_from_thread(info_bar.reset_phase)

    def cmd_more(args: str) -> None:
        """Threaded: fetch next page of search results."""
        output = tui.query_one(OutputArea)
        info_bar = tui.query_one(InfoBar)

        if state._last_search_kwargs is None:
            tui.call_from_thread(
                output.add_system_message, "No previous search. Use /search first."
            )
            return

        tui.call_from_thread(info_bar.update_thinking, 0.0)
        offset = state._search_offset
        results = state.searcher.search(
            **state._last_search_kwargs, max_results=10, start=offset
        )

        if not results:
            tui.call_from_thread(output.add_system_message, "No more results.")
            tui.call_from_thread(info_bar.reset_phase)
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
            lines.append(f"{i}. **[{meta.arxiv_id}]** \"{meta.title}\"")
            lines.append(f"   {authors} | {meta.primary_category} | {date_str}")
            lines.append(f"   {meta.arxiv_url}\n")
        tui.call_from_thread(output.add_system_markdown, "\n".join(lines))
        tui.call_from_thread(info_bar.reset_phase)

    tui.register_command("/search", cmd_search, "Search arXiv", threaded=True)
    tui.register_command("/more", cmd_more, "Next page of results", threaded=True)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/examples/test_arxiv.py::TestTUISearchCommands -v`
Expected: PASS

**Step 5: Run full suite**

Run: `make all`
Expected: All green

**Step 6: Commit**

```bash
git add examples/arxiv_explorer.py tests/examples/test_arxiv.py
git commit -m "feat: register threaded /search and /more TUI commands"
```

---

### Task 7: Register threaded `/load` command

This downloads papers (network I/O + disk I/O), so it runs threaded. Shows per-paper progress in OutputArea.

**Files:**
- Test: `tests/examples/test_arxiv.py`
- Modify: `examples/arxiv_explorer.py`

**Step 1: Write the failing test**

```python
class TestTUILoadCommand:
    """Tests for threaded /load command."""

    @patch("arxiv_explorer.download_paper")
    @patch("arxiv_explorer.to_parsed_document")
    async def test_load_by_number(
        self, mock_to_doc: MagicMock, mock_download: MagicMock
    ) -> None:
        """'/load 1' loads the first search result."""
        from datetime import UTC, datetime

        from arxiv_explorer import create_app, AppState
        from shesha.experimental.arxiv.models import PaperMeta
        from shesha.models import ParsedDocument

        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Test Paper",
            authors=["A"],
            abstract="",
            published=datetime(2025, 1, 1, tzinfo=UTC),
            updated=datetime(2025, 1, 1, tzinfo=UTC),
            categories=["cs.AI"],
            primary_category="cs.AI",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/2501.12345",
            source_type="latex",
        )
        mock_download.return_value = meta
        mock_to_doc.return_value = ParsedDocument(
            name="2501.12345", content="c", format="latex", metadata={}, char_count=1
        )

        state = MagicMock(spec=AppState)
        state.current_topic = "2026-01-15-test"
        state.shesha = MagicMock()
        state.topic_mgr = MagicMock()
        state.topic_mgr.get_topic_info_by_project_id.return_value = MagicMock(name="test")
        state.cache = MagicMock()
        state.searcher = MagicMock()
        state.last_search_results = [meta]
        state._search_offset = 1
        state._last_search_kwargs = {"query": "test"}

        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            worker = app.run_worker(
                lambda: app._command_registry.resolve("/load 1")[0]("1"),
                thread=True,
            )
            await worker.wait()
            await pilot.pause()
            state.topic_mgr._storage.store_document.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/examples/test_arxiv.py::TestTUILoadCommand -v`
Expected: FAIL — `/load` not registered

**Step 3: Write minimal implementation**

```python
    def cmd_load(args: str) -> None:
        """Threaded: load papers into current topic."""
        output = tui.query_one(OutputArea)
        info_bar = tui.query_one(InfoBar)

        if state.current_topic is None:
            tui.call_from_thread(
                output.add_system_message, "No topic selected. Use /topic <name> first."
            )
            return

        args = args.strip()
        if not args:
            if not state.last_search_results:
                tui.call_from_thread(
                    output.add_system_message, "No search results. Use /search first."
                )
                return
            tokens = [str(i) for i in range(1, len(state.last_search_results) + 1)]
        else:
            tokens = args.split()

        tui.call_from_thread(info_bar.update_thinking, 0.0)
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
                        output.add_system_message, f"Invalid result number: {token}"
                    )
                    continue
            elif ARXIV_ID_RE.match(token):
                if state.cache.has(token):
                    meta = state.cache.get_meta(token)
                else:
                    meta = state.searcher.get_by_id(token)
                if meta is None:
                    tui.call_from_thread(
                        output.add_system_message, f"Paper not found: {token}"
                    )
                    continue
            else:
                tui.call_from_thread(
                    output.add_system_message,
                    f"Invalid input: {token} (use a result number or arXiv ID like 2501.12345)",
                )
                continue

            tui.call_from_thread(
                output.add_system_message,
                f"Loading [{loaded + 1}/{len(tokens)}] {meta.arxiv_id}...",
            )
            updated_meta = download_paper(meta, state.cache)
            doc = to_parsed_document(updated_meta.arxiv_id, state.cache)
            state.topic_mgr._storage.store_document(state.current_topic, doc)
            loaded += 1
            source_label = updated_meta.source_type or "unknown"
            tui.call_from_thread(
                output.add_system_message,
                f'Loaded [{updated_meta.arxiv_id}] "{updated_meta.title}" ({source_label})',
            )

        if loaded:
            tui.call_from_thread(
                output.add_system_message,
                f"\n{loaded} paper(s) loaded into topic.",
            )
        tui.call_from_thread(info_bar.reset_phase)

    tui.register_command("/load", cmd_load, "Load papers", threaded=True)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/examples/test_arxiv.py::TestTUILoadCommand -v`
Expected: PASS

**Step 5: Run full suite**

Run: `make all`
Expected: All green

**Step 6: Commit**

```bash
git add examples/arxiv_explorer.py tests/examples/test_arxiv.py
git commit -m "feat: register threaded /load TUI command"
```

---

### Task 8: Register threaded `/check-citations` command

Citation checking with per-citation progress in OutputArea.

**Files:**
- Test: `tests/examples/test_arxiv.py`
- Modify: `examples/arxiv_explorer.py`

**Step 1: Write the failing test**

```python
class TestTUICheckCitations:
    """Tests for threaded /check-citations command."""

    @patch("arxiv_explorer.ArxivVerifier")
    async def test_check_citations_runs_pipeline(
        self, mock_verifier_cls: MagicMock
    ) -> None:
        """'/check-citations' runs the full verification pipeline."""
        from datetime import UTC, datetime

        from shesha.tui.widgets.output_area import OutputArea

        from arxiv_explorer import create_app, AppState
        from shesha.experimental.arxiv.models import (
            PaperMeta,
            VerificationResult,
            VerificationStatus,
        )

        meta = PaperMeta(
            arxiv_id="2501.12345",
            title="Test Paper",
            authors=["A"],
            abstract="",
            published=datetime(2025, 1, 1, tzinfo=UTC),
            updated=datetime(2025, 1, 1, tzinfo=UTC),
            categories=["cs.AI"],
            primary_category="cs.AI",
            pdf_url="",
            arxiv_url="https://arxiv.org/abs/2501.12345",
            source_type="latex",
        )

        state = MagicMock(spec=AppState)
        state.current_topic = "2026-01-15-test"
        state.shesha = MagicMock()
        state.topic_mgr = MagicMock()
        state.topic_mgr.get_topic_info_by_project_id.return_value = MagicMock(name="test")
        state.topic_mgr._storage.list_documents.return_value = ["2501.12345"]
        state.cache = MagicMock()
        state.cache.get_meta.return_value = meta
        state.cache.get_source_files.return_value = {
            "refs.bib": "@article{a, author={A}, title={Paper A}, year={2023}, eprint={2301.00001}}"
        }
        state.searcher = MagicMock()
        state.last_search_results = []
        state._search_offset = 0
        state._last_search_kwargs = None

        mock_verifier = MagicMock()
        mock_verifier_cls.return_value = mock_verifier
        mock_verifier.verify.return_value = VerificationResult(
            citation_key="a",
            status=VerificationStatus.VERIFIED,
        )

        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            worker = app.run_worker(
                lambda: app._command_registry.resolve("/check-citations ")[0](""),
                thread=True,
            )
            await worker.wait()
            await pilot.pause()
            mock_verifier.verify.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/examples/test_arxiv.py::TestTUICheckCitations -v`
Expected: FAIL — `/check-citations` not registered

**Step 3: Write minimal implementation**

```python
    def cmd_check_citations(args: str) -> None:
        """Threaded: check citations for papers in current topic."""
        output = tui.query_one(OutputArea)
        info_bar = tui.query_one(InfoBar)

        if state.current_topic is None:
            tui.call_from_thread(
                output.add_system_message,
                "No topic selected. Use /topic <name> first.",
            )
            return

        docs = state.topic_mgr._storage.list_documents(state.current_topic)
        if not docs:
            tui.call_from_thread(
                output.add_system_message,
                "No papers loaded. Use /search and /load to add papers first.",
            )
            return

        filter_id = args.strip() if args.strip() else None
        if filter_id:
            docs = [d for d in docs if filter_id in d]
            if not docs:
                tui.call_from_thread(
                    output.add_system_message,
                    f"Paper {filter_id} not found in current topic.",
                )
                return

        tui.call_from_thread(info_bar.update_thinking, 0.0)
        verifier = ArxivVerifier(searcher=state.searcher)

        for doc_name in docs:
            meta = state.cache.get_meta(doc_name)
            if meta is None:
                tui.call_from_thread(
                    output.add_system_message,
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
                    full_text = ""

            llm_phrases = detect_llm_phrases(full_text)

            arxiv_citations = [c for c in citations if c.arxiv_id is not None]
            if arxiv_citations:
                tui.call_from_thread(
                    output.add_system_message,
                    f"Checking {meta.arxiv_id}... "
                    f"Verifying {len(arxiv_citations)} citations with arXiv IDs",
                )

            results = []
            for i, c in enumerate(citations, 1):
                if c.arxiv_id is not None:
                    tui.call_from_thread(
                        output.add_system_message,
                        f"  [{i}/{len(citations)}] {c.key}...",
                    )
                    r = verifier.verify(c)
                    status_icon = {
                        VerificationStatus.VERIFIED: "OK",
                        VerificationStatus.MISMATCH: "MISMATCH",
                        VerificationStatus.NOT_FOUND: "NOT FOUND",
                        VerificationStatus.UNRESOLVED: "?",
                    }[r.status]
                    tui.call_from_thread(
                        output.add_system_message,
                        f"  [{i}/{len(citations)}] {c.key}... {status_icon}",
                    )
                    results.append(r)
                else:
                    results.append(verifier.verify(c))

            report = CheckReport(
                arxiv_id=meta.arxiv_id,
                title=meta.title,
                citations=citations,
                verification_results=results,
                llm_phrases=llm_phrases,
            )
            tui.call_from_thread(
                output.add_system_markdown,
                "```\n" + format_check_report(report) + "\n```",
            )

        tui.call_from_thread(info_bar.reset_phase)

    tui.register_command(
        "/check-citations", cmd_check_citations, "Citation verification", threaded=True
    )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/examples/test_arxiv.py::TestTUICheckCitations -v`
Expected: PASS

**Step 5: Run full suite**

Run: `make all`
Expected: All green

**Step 6: Commit**

```bash
git add examples/arxiv_explorer.py tests/examples/test_arxiv.py
git commit -m "feat: register threaded /check-citations TUI command"
```

---

### Task 9: Handle conversational queries through the TUI

When the user types text without a `/` prefix, it should go through the RLM engine against the current topic's documents — but only if a topic is selected with papers loaded. The TUI already handles this for barsoom, but we need to ensure `tui._project` is updated when topics switch and that no-topic gives a helpful error.

**Files:**
- Test: `tests/examples/test_arxiv.py`
- Modify: `examples/arxiv_explorer.py`

**Step 1: Write the failing test**

```python
class TestTUIConversationalQuery:
    """Tests for conversational queries (non-command input)."""

    async def test_query_no_topic_shows_error(self) -> None:
        """Typing a question with no topic shows error."""
        from shesha.tui.widgets.input_area import InputArea
        from shesha.tui.widgets.output_area import OutputArea

        from arxiv_explorer import create_app, AppState

        state = MagicMock(spec=AppState)
        state.current_topic = None
        state.shesha = MagicMock()
        state.topic_mgr = MagicMock()
        state.cache = MagicMock()
        state.searcher = MagicMock()
        state.last_search_results = []
        state._search_offset = 0
        state._last_search_kwargs = None

        app = create_app(state, model="gpt-4o")
        async with app.run_test() as pilot:
            # Type a question
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "What is this paper about?"
            await pilot.press("enter")
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.renderable) for s in statics if hasattr(s, 'renderable')]
            # Should show error about needing a topic
            assert any("topic" in t.lower() for t in texts)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/examples/test_arxiv.py::TestTUIConversationalQuery -v`
Expected: FAIL — the TUI submits query to the mock project instead of intercepting

**Step 3: Write minimal implementation**

We need to intercept query submission when no topic is selected or no papers are loaded. The cleanest approach: monkey-patch `tui._run_query` to check state before proceeding.

```python
# In create_app(), after creating the tui:

    original_run_query = tui._run_query

    def guarded_run_query(question: str) -> None:
        output = tui.query_one(OutputArea)
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
        original_run_query(question)

    tui._run_query = guarded_run_query  # type: ignore[assignment]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/examples/test_arxiv.py::TestTUIConversationalQuery -v`
Expected: PASS

**Step 5: Run full suite**

Run: `make all`
Expected: All green

**Step 6: Commit**

```bash
git add examples/arxiv_explorer.py tests/examples/test_arxiv.py
git commit -m "feat: guard conversational queries against missing topic/papers"
```

---

### Task 10: Clean up old CLI code and fix tests

Remove dead CLI code: `handle_help()`, `handle_query()`, `COMMANDS` dict, `dispatch_command()`, `readline` import, old `handle_*` functions that have been replaced by TUI command closures. Update or remove old tests that were testing CLI-specific behavior (capsys-based tests).

**Files:**
- Modify: `examples/arxiv_explorer.py`
- Modify: `tests/examples/test_arxiv.py`

**Step 1: Identify dead code**

The following are replaced by TUI closures and should be removed from the module level:
- `handle_help()` — TUI has built-in `/help`
- `handle_history()` — replaced by `cmd_history` closure
- `handle_topic()` — replaced by `cmd_topic` closure
- `handle_papers()` — replaced by `cmd_papers` closure
- `handle_search()` — replaced by `cmd_search` closure
- `handle_more()` — replaced by `cmd_more` closure
- `handle_load()` — replaced by `cmd_load` closure
- `handle_check_citations()` — replaced by `cmd_check_citations` closure
- `handle_query()` — replaced by guarded_run_query
- `COMMANDS` dict
- `dispatch_command()`
- `import readline`
- `from collections.abc import Callable`
- `STARTUP_BANNER` (TUI doesn't print a banner)

Keep:
- `parse_args()`, `AppState`, `_parse_search_flags()`, `ARXIV_ID_RE`, `DEFAULT_DATA_DIR`
- All imports used by the TUI command closures
- `create_app()`, `main()`

**Step 2: Remove the dead code from arxiv_explorer.py**

Remove all functions listed above and the `COMMANDS` dict/`dispatch_command()`.

**Step 3: Update tests**

Remove or rewrite tests that reference removed functions:
- `TestCommandDispatch` — remove entirely (no more `dispatch_command`)
- `TestHistoryCommand` — remove (tested via TUI now)
- `TestTopicCommand` — remove (tested via TUI now)
- `TestPapersCommand` — remove (tested via TUI now)
- `TestStartupBanner` — remove (no more banner)
- `TestDispatchQuit` — remove (no more `dispatch_command`)
- `TestSearchCommand` — keep `_parse_search_flags` tests, remove `handle_search` tests
- `TestMoreCommand` — remove (tested via TUI now)
- `TestLoadCommand` — remove (tested via TUI now)
- `TestCheckCitationsCommand` — remove (tested via TUI now)
- `TestConversationalQuery` — remove (tested via TUI now)
- `TestMainFunction` — remove (main() now launches TUI)
- `TestEdgeCases` — move the `_parse_search_flags` test to a dedicated class, remove rest

Keep:
- `TestParseArgs` — still tests `parse_args()` (unchanged)
- `_parse_search_flags` tests — move to a `TestParseSearchFlags` class
- All new `TestTUI*` classes from Tasks 3-9

**Step 4: Run full suite**

Run: `make all`
Expected: All green

**Step 5: Commit**

```bash
git add examples/arxiv_explorer.py tests/examples/test_arxiv.py
git commit -m "refactor: remove dead CLI code, keep TUI commands"
```

---

### Task 11: Update CHANGELOG.md

Add an entry under `[Unreleased]` documenting the TUI conversion.

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add changelog entry**

Under `[Unreleased]`, add:

```markdown
### Added
- arXiv Explorer now uses a Textual TUI with the Shesha look-and-feel
  - Search results and citations render as markdown in the conversation flow
  - Threaded commands keep the UI responsive during network I/O
  - `/topic rename <old> <new>` renames a topic's display name
  - InfoBar shows current topic name, updates dynamically on topic switch
  - `--topic` flag on startup warns on unknown topics instead of auto-creating
- `TopicManager.rename()` method for renaming topic display names
- `InfoBar.update_project_name()` method for dynamic topic switching
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add arXiv TUI conversion to changelog"
```
