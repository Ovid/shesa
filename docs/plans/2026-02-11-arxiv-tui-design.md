# arXiv Explorer TUI Design

**Goal:** Convert `examples/arxiv_explorer.py` from a readline-based CLI to a Textual TUI by registering arXiv commands in the existing `SheshaTUI`, following the `examples/barsoom.py` pattern.

**Architecture:** No new widgets, screens, or subclasses. All arXiv functionality is registered as slash commands in `SheshaTUI` via `CommandRegistry`. Output renders inline in `OutputArea` as markdown or system messages. Threaded handlers keep the UI responsive during network I/O.

## Approach

Register arXiv-specific commands in the existing `SheshaTUI`, exactly as `barsoom.py` registers `/clear`. The TUI's built-in commands (`/help`, `/write`, `/markdown`, `/theme`, `/quit`) remain. Conversational queries (no `/` prefix) go through the RLM engine against loaded papers, same as barsoom.

No new files in `src/shesha/tui/`. All changes in `examples/arxiv_explorer.py` and its tests. Library code in `src/shesha/experimental/arxiv/` is untouched except for adding `TopicManager.rename()`.

## Commands

| Command | Threaded? | Output |
|---------|-----------|--------|
| `/search <query> [--author, --cat, --recent, --sort]` | Yes | Numbered markdown list in OutputArea |
| `/more` | Yes | Next page appended to OutputArea |
| `/load [nums or IDs]` | Yes | Per-paper progress messages, summary |
| `/papers` | No | Markdown list of loaded papers |
| `/check-citations [ID]` | Yes | Per-citation progress, formatted report |
| `/topic [name]` | No | Create/switch topic, update InfoBar |
| `/topic delete <name>` | No | Delete topic |
| `/topic rename <old> <new>` | No | Rename topic display name |
| `/history` | No | Markdown table of all topics |

## Search Results Display

Search results render as a numbered markdown list in the conversation flow via `OutputArea.add_system_markdown()`. Example:

```
### Search: "abiogenesis" (10 results)

1. **[2503.18217v1]** "The Abiogenesis Timescale"
   Daniel P. Whitmire | astro-ph.EP | 2025-03-23
   https://arxiv.org/abs/2503.18217v1

2. **[2504.05993v1]** "Strong Evidence That Abiogenesis Is..."
   ...

Use /more for next page, /load <numbers> to pick, /load to load this page.
```

The `/load` command references numbers from the last search, same as the CLI.

## Threaded Command Pattern

Threaded handlers run on a background thread. UI updates go through `app.call_from_thread()`:

- `app.call_from_thread(output.add_system_message, "Loading [1/5] 2501.12345...")` for progress
- `app.call_from_thread(output.add_system_markdown, formatted_report)` for final output
- `app.call_from_thread(info_bar.update, ...)` for InfoBar phase updates

Only one threaded command at a time. If the user types a command while one is running, reject with "Command in progress."

InfoBar shows command activity:
- "Searching..." / "Downloading papers..." / "Checking citations..." during execution
- "Ready" after completion (with 2s delay, matching existing behavior)

## Topic Management

- `/topic <name>`: creates or switches topic. InfoBar updates to show topic name where project name normally goes.
- `/topic delete <name>`: deletes topic.
- `/topic rename <old> <new>`: changes the display name in `_topic.json` metadata only. Does NOT rename the filesystem directory (the date-prefixed project ID stays stable). New `TopicManager.rename()` method.
- `/topic` (bare): shows current topic name.
- `/history`: lists all topics as markdown table.

When topic switches, `SheshaTUI._project` is updated so conversational queries run against the new topic's documents.

## Startup Flow

- `--topic <name>` flag: if topic resolves, switch to it and show `"Switched to topic: <name> (N papers)"` in OutputArea.
- `--topic <name>` flag with unknown name: do NOT auto-create. Show warning: `"Topic '<name>' not found. Use /history to see existing topics, or /topic <name> to create one."` No topic selected.
- No `--topic` flag: start with no topic. InfoBar shows "No topic". User creates/switches with `/topic <name>`.
- `/search` works without a topic (searching doesn't require a topic, only `/load` does).

## Migration

`examples/arxiv_explorer.py` is rewritten. Handler logic stays largely the same but I/O changes:

- `print(...)` → `app.call_from_thread(output.add_system_message, ...)`
- `print(formatted_markdown)` → `app.call_from_thread(output.add_system_markdown, ...)`
- `input()` disappears — TUI handles input
- `readline` import removed
- `argparse` retained for `--model`, `--data-dir`, `--topic`

`_parse_search_flags()` unchanged (pure string parsing).

`tests/examples/test_arxiv.py` updated:
- Tests using `capsys` → Textual `async with app.run_test() as pilot:` pattern
- Pure logic tests (flag parsing, state management) stay the same
- Textual pilot pattern already used in Shesha's test suite

## New Library Feature

`TopicManager.rename(old_name, new_name)`:
1. Resolve old name to project ID
2. Read `_topic.json`
3. Update `name` field to `slugify(new_name)`
4. Write back `_topic.json`
5. Raise `ValueError` if old name not found
