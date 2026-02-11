# arXiv Explorer TUI Command UX Redesign

## Problem

The current command UX in `examples/arxiv_explorer.py` has several issues:

1. **Overloaded commands**: `/topic` does 5 things (show current, switch, create, delete, rename) behind one command name. Users can't discover these actions without reading code.
2. **Ambiguous naming**: `/load` sounds like "load a topic" but actually downloads papers from arXiv. `/history` lists topics, not history.
3. **Poor discoverability**: Typing `/` shows a truncated list of commands. Descriptions don't indicate which commands take arguments or what those arguments are.
4. **Autocomplete gap**: The completion popup hides as soon as a space is typed, so there's no guidance for subcommands or arguments.

## Design

### Command Structure

Reorganize around a git-style subcommand model. `/topic` becomes a command group with explicit subcommands. Global actions stay flat.

#### Topic management group

| Command | Description |
|---------|-------------|
| `/topic` | Show usage: list all subcommands |
| `/topic list` | List all topics with paper counts (absorbs `/history`) |
| `/topic switch <name\|#>` | Switch to an existing topic by name or number from list |
| `/topic create <name>` | Create a new topic and switch to it |
| `/topic delete <name>` | Delete a topic |
| `/topic rename <old> <new>` | Rename a topic |
| `/topic papers` | List papers in current topic (absorbs `/papers`) |
| `/topic add <#\|arxiv-id>...` | Add papers from search results or by arXiv ID (absorbs `/load`) |

#### Flat commands (global actions)

| Command | Description |
|---------|-------------|
| `/search <query> [--author, --cat, --recent, --sort]` | Search arXiv papers |
| `/more` | Next page of search results |
| `/check [arxiv-id]` | Verify citations (renamed from `/check-citations`) |
| `/help` | Show all commands with usage hints |
| `/write [filename]` | Save session transcript |
| `/markdown` | Toggle markdown rendering |
| `/theme` | Toggle dark/light theme |
| `/quit` | Exit |

#### Removed commands

| Old Command | Replacement |
|-------------|-------------|
| `/history` | `/topic list` |
| `/papers` | `/topic papers` |
| `/load` | `/topic add` |
| `/check-citations` | `/check` |

### Discoverability

#### 1. Bare group shows usage help

Typing `/topic` and pressing Enter (no subcommand) displays:

```
Topic management commands:
  /topic list                  List all topics
  /topic switch <name|#>       Switch to a topic (by name or number)
  /topic create <name>         Create a new topic
  /topic delete <name>         Delete a topic
  /topic rename <old> <new>    Rename a topic
  /topic papers                List papers in current topic
  /topic add <#|arxiv-id>...   Add papers from search results or by ID
```

#### 2. Two-level autocomplete

When the user types `/topic ` (with trailing space), the completion popup shows subcommands:

```
> list          List all topics
  switch        Switch to a topic
  create        Create a new topic
  delete        Delete a topic
  rename        Rename a topic
  papers        List papers in current topic
  add           Add papers from search results
```

Further typing filters: `/topic sw` narrows to `switch`.

#### 3. Improved /help output

`/help` shows argument hints for every command:

```
Available commands:
  /topic <subcommand>              Topic management (type /topic for details)
  /search <query> [--author, ...]  Search arXiv papers
  /more                            Next page of search results
  /check [arxiv-id]                Verify citations
  /write [filename]                Save session transcript
  /markdown                        Toggle markdown rendering
  /theme                           Toggle dark/light theme
  /quit                            Exit
```

#### 4. Fix popup truncation

All commands must be visible when typing `/`. Investigate and fix the CSS or rendering issue that clips the completion popup.

## Implementation

### CommandRegistry changes

Add command group support to `src/shesha/tui/commands.py`:

- `register_group(name, description)` -- registers a command group (e.g., `/topic`). The group itself acts as a command that shows usage help when invoked without a subcommand.
- `register_subcommand(group, subcommand, handler, description, threaded=False)` -- registers a subcommand under a group. The handler signature stays `(args: str) -> None`.
- `completions(prefix)` -- extended: when prefix matches `"/<group> "`, return subcommand completions filtered by text after the space.
- `resolve(text)` -- extended: for input like `/topic switch foo`, resolve to the `switch` subcommand handler with args `"foo"`.
- `list_commands()` -- returns top-level commands and groups (not individual subcommands). Groups show their description.
- `list_subcommands(group)` -- returns subcommands for a group with descriptions, used by bare-group usage help.

### CompletionPopup changes

Modify `src/shesha/tui/app.py` `on_text_area_changed`:

- Current behavior: hide popup when input contains a space.
- New behavior: if text before the first space is a registered group name, show subcommand completions filtered by text after the space. Hide popup only when text doesn't match any completion context.

### arxiv_explorer.py changes

- Register `/topic` as a command group.
- Split the monolithic `_cmd_topic` into individual subcommand handlers: `_cmd_topic_list`, `_cmd_topic_switch`, `_cmd_topic_create`, `_cmd_topic_delete`, `_cmd_topic_rename`, `_cmd_topic_papers`, `_cmd_topic_add`.
- `/topic switch` accepts a name or a number (from `/topic list` output). Does NOT auto-create.
- `/topic create` creates and switches. Errors if topic already exists.
- `/topic add` absorbs the old `/load` logic, wrapped in `_threaded_guard`. Requires a current topic.
- `/topic papers` absorbs the old `/papers` logic.
- `/topic list` absorbs the old `/history` logic.
- Register `/check` (renamed from `/check-citations`).
- Remove old `/load`, `/papers`, `/history`, `/check-citations` registrations.

### Popup truncation fix

Investigate `CompletionPopup` in `src/shesha/tui/widgets/completion_popup.py` and the CSS in `app.py`. Likely causes:
- Static widget has no scrolling -- if more items than vertical space, they clip.
- Fix: either add max-height with overflow scroll, or position the popup to ensure all items are visible (e.g., render upward from the input area).

## Testing

- Unit tests for `CommandRegistry` group/subcommand registration, resolution, and completion.
- Unit tests for each `/topic` subcommand handler (switch by name, switch by number, create, delete, rename, papers, add).
- TUI integration tests for two-level autocomplete behavior.
- TUI integration test for popup showing all commands when typing `/`.
- Test that bare `/topic` shows usage help.
- Test that old command names (`/load`, `/papers`, `/history`, `/check-citations`) are no longer registered.
