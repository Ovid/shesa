"""Main Textual application for Shesha TUI."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.timer import Timer
from textual.widgets import Static, TextArea
from textual.worker import Worker

from shesha.analysis.shortcut import try_answer_from_analysis
from shesha.rlm.trace import StepType, TokenUsage
from shesha.tui.commands import CommandRegistry
from shesha.tui.history import InputHistory
from shesha.tui.progress import step_display_name
from shesha.tui.session import ConversationSession
from shesha.tui.widgets.completion_popup import CompletionPopup
from shesha.tui.widgets.info_bar import InfoBar
from shesha.tui.widgets.input_area import InputArea, InputSubmitted
from shesha.tui.widgets.output_area import OutputArea

if TYPE_CHECKING:
    from shesha.project import Project
    from shesha.rlm.engine import QueryResult


# Brand color matching the Shesha logo
SHESHA_TEAL = "#00bcd4"


class SheshaTUI(App[None]):
    """Textual app for interactive Shesha Q&A sessions.

    Args:
        project: Shesha Project instance to query against.
        project_name: Display name for the project.
        analysis_context: Optional analysis text prepended to queries.
    """

    CSS = f"""
    Screen {{
        layout: vertical;
        border: solid {SHESHA_TEAL};
    }}
    #input-row {{
        height: auto;
        min-height: 1;
        max-height: 10;
    }}
    #input-row:focus-within {{
        border: solid {SHESHA_TEAL};
    }}
    #prompt {{
        width: 2;
        height: 1;
        color: {SHESHA_TEAL};
    }}
    #input-row InputArea {{
        width: 1fr;
    }}
    #help-bar {{
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }}
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(
        self,
        project: Project,
        project_name: str,
        analysis_context: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__()
        self._project = project
        self._project_name = project_name
        self._analysis_context = analysis_context
        self._model = model
        self._api_key = api_key
        self._command_registry = CommandRegistry()
        self._input_history = InputHistory()
        self._session = ConversationSession(project_name=project_name)
        self._query_in_progress = False
        self._query_id = 0
        self._query_start_time = 0.0
        self._last_iteration = 0
        self._last_step_name = ""
        self._cumulative_prompt_tokens = 0
        self._cumulative_completion_tokens = 0
        self._timer_handle: Timer | None = None
        self._worker_handle: Worker[object] | None = None
        self._register_builtin_commands()

    def _register_builtin_commands(self) -> None:
        """Register the default slash commands."""
        self._command_registry.register("/help", self._cmd_help, "Show available commands")
        self._command_registry.register(
            "/write", self._cmd_write, "Save session transcript [filename]"
        )
        self._command_registry.register(
            "/markdown", self._cmd_markdown, "Toggle markdown rendering"
        )
        self._command_registry.register("/theme", self._cmd_theme, "Toggle dark/light theme")
        self._command_registry.register("/quit", self._cmd_quit, "Exit")

    def register_command(
        self,
        name: str,
        handler: Callable[[str], object],
        description: str,
        *,
        threaded: bool = False,
    ) -> None:
        """Register a custom slash command.

        Args:
            name: Command name (e.g., "/analyze").
            handler: Callable receiving the argument string.
            description: Short description for help/completions.
            threaded: If True, handler runs in a worker thread to avoid
                blocking the UI. Threaded handlers must use
                ``app.call_from_thread()`` for any widget updates.
        """
        self._command_registry.register(name, handler, description, threaded=threaded)

    def compose(self) -> ComposeResult:
        """Create the app layout."""
        yield OutputArea()
        yield InfoBar(project_name=self._project_name, model=self._model or "")
        yield CompletionPopup()
        with Horizontal(id="input-row"):
            yield Static("\u276f", id="prompt")
            yield InputArea()
        yield Static(
            "Tab: switch panes \u2502 \u2191\u2193: history"
            " \u2502 Ctrl+J: newline \u2502 Esc\u00d72: cancel \u2502 /: commands",
            id="help-bar",
        )

    def on_mount(self) -> None:
        """Focus the input area on startup."""
        try:
            self.query_one(InputArea).focus()
        except NoMatches:
            pass  # InputArea not yet mounted; focus will be set later

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Update completion popup when input text changes."""
        raw_text = self.query_one(InputArea).text
        text = raw_text.strip()
        # Only complete bare slash-prefixed tokens with no spaces
        if text.startswith("/") and " " not in raw_text:
            matches = self._command_registry.completions(text)
            if matches:
                self.query_one(CompletionPopup).show_items(matches)
                self.query_one(InputArea).completion_active = True
                return
        self._hide_completions()

    def on_input_area_completion_navigate(self, event: InputArea.CompletionNavigate) -> None:
        """Handle completion navigation."""
        popup = self.query_one(CompletionPopup)
        if event.direction == "next":
            popup.select_next()
        else:
            popup.select_prev()

    def on_input_area_completion_accept(self, event: InputArea.CompletionAccept) -> None:
        """Handle completion acceptance."""
        value = self.query_one(CompletionPopup).selected_value
        self._hide_completions()
        if value:
            input_area = self.query_one(InputArea)
            filled = value + " "
            input_area.text = filled
            input_area.move_cursor((0, len(filled)))

    def on_input_area_completion_dismiss(self, event: InputArea.CompletionDismiss) -> None:
        """Handle completion dismissal."""
        self._hide_completions()

    def on_input_area_query_cancelled(self, event: InputArea.QueryCancelled) -> None:
        """Handle query cancellation from double-escape.

        Note: Worker.cancel() cannot interrupt a blocking thread — the
        underlying project.query() call keeps running to completion.
        We bump _query_id so that _on_query_complete, _on_query_error,
        and _on_progress silently discard any results whose captured
        query_id no longer matches the current one.
        """
        self._query_id += 1
        if self._worker_handle is not None:
            self._worker_handle.cancel()
            self._worker_handle = None
        self._stop_query()
        self.query_one(InfoBar).update_cancelled()
        self.query_one(OutputArea).add_system_message("Query cancelled.")

    def on_input_area_history_navigate(self, event: InputArea.HistoryNavigate) -> None:
        """Handle history navigation from InputArea."""
        input_area = self.query_one(InputArea)
        if event.direction == "prev":
            entry = self._input_history.previous()
        else:
            entry = self._input_history.next()
        text = entry or ""
        input_area.text = text
        input_area.move_cursor((0, len(text)))

    def on_input_area_focus_toggle(self, event: InputArea.FocusToggle) -> None:
        """Handle focus toggle from InputArea — move focus to OutputArea."""
        self.query_one(OutputArea).focus()

    def on_key(self, event: events.Key) -> None:
        """Handle app-level key events."""
        # Tab from OutputArea toggles focus back to InputArea
        if event.key == "tab" and self.query_one(OutputArea).has_focus:
            event.prevent_default()
            event.stop()
            self.query_one(InputArea).focus()

    def _hide_completions(self) -> None:
        """Hide the completion popup and deactivate completion mode."""
        self.query_one(CompletionPopup).hide()
        self.query_one(InputArea).completion_active = False

    def on_input_submitted(self, event: InputSubmitted) -> None:
        """Handle user input submission."""
        self._hide_completions()
        text = event.text

        # Check if it's a command
        if self._command_registry.is_command(text):
            resolved = self._command_registry.resolve(text)
            if resolved is None:
                self.query_one(OutputArea).add_system_message(
                    f"Unknown command: {text.strip().split()[0]}"
                )
            else:
                handler, args, threaded = resolved
                if threaded:
                    self.run_worker(lambda: handler(args), thread=True)
                else:
                    handler(args)
            return

        # Reject new queries while one is already running
        if self._query_in_progress:
            self.query_one(OutputArea).add_system_message(
                "A query is already running. Press Esc twice to cancel it first."
            )
            return

        # It's a query -- add to history and execute
        self._input_history.add(text)
        self.query_one(OutputArea).add_user_message(text)
        self._run_query(text)

    def _run_query(self, question: str) -> None:
        """Execute a query in a worker thread."""
        self._query_id += 1
        self._query_in_progress = True
        self.query_one(InputArea).query_in_progress = True
        self._query_start_time = time.time()
        self._last_iteration = 0

        # Start elapsed timer
        info_bar = self.query_one(InfoBar)
        info_bar.update_thinking(0.0)
        self._timer_handle = self.set_interval(0.1, self._tick_timer)

        # Build question with conversation history (used by both shortcut and RLM)
        prefix = self._session.format_history_prefix()
        question_with_history = f"{prefix}{question}" if prefix else question

        # Full question adds analysis context for the RLM path
        if self._analysis_context:
            full_question = f"{self._analysis_context}\n\n{question_with_history}"
        else:
            full_question = question_with_history

        self._worker_handle = self.run_worker(
            self._make_query_runner(full_question, question, question_with_history),
            thread=True,
            exit_on_error=False,
        )

    def _make_query_runner(
        self, full_question: str, display_question: str, question_with_history: str = ""
    ) -> Callable[[], QueryResult | None]:
        """Return a callable that runs the query (for worker thread).

        The returned function captures _query_id at creation time and
        checks it before posting results back to the main thread. If
        the ID has changed (due to cancellation or a new query), the
        stale worker's results are silently discarded. This is necessary
        because Worker.cancel() cannot interrupt a blocking
        project.query() call.
        """
        my_query_id = self._query_id

        def on_progress(
            step_type: StepType, iteration: int, content: str, token_usage: TokenUsage
        ) -> None:
            if self._query_id != my_query_id:
                return
            self._on_progress(step_type, iteration, content, token_usage)

        def run() -> QueryResult | None:
            # Try analysis shortcut before full RLM
            if self._analysis_context and self._model:
                shortcut = try_answer_from_analysis(
                    question_with_history or display_question,
                    self._analysis_context,
                    self._model,
                    self._api_key,
                )
                if shortcut is not None:
                    answer, prompt_tokens, completion_tokens = shortcut
                    if self._query_id == my_query_id:
                        self.call_from_thread(
                            self._on_shortcut_answer,
                            my_query_id,
                            answer,
                            display_question,
                            prompt_tokens,
                            completion_tokens,
                        )
                    return None

            try:
                result = self._project.query(
                    full_question,
                    on_progress=on_progress,
                )
                if self._query_id == my_query_id:
                    self.call_from_thread(
                        self._on_query_complete, my_query_id, result, display_question
                    )
                return result
            except Exception as exc:
                if self._query_id == my_query_id:
                    self.call_from_thread(self._on_query_error, my_query_id, str(exc))
                return None

        return run

    def _on_progress(
        self,
        step_type: StepType,
        iteration: int,
        content: str,
        token_usage: TokenUsage | None = None,
    ) -> None:
        """Progress callback from RLM engine (called from worker thread)."""
        if not self._query_in_progress:
            return
        elapsed = time.time() - self._query_start_time
        self._last_iteration = iteration + 1  # Convert 0-indexed to 1-indexed
        step_name = step_display_name(step_type)
        self._last_step_name = step_name
        info_bar = self.query_one(InfoBar)
        if token_usage is not None:
            self._cumulative_prompt_tokens = token_usage.prompt_tokens
            self._cumulative_completion_tokens = token_usage.completion_tokens
            self.call_from_thread(
                info_bar.update_tokens,
                token_usage.prompt_tokens,
                token_usage.completion_tokens,
            )
        self.call_from_thread(
            info_bar.update_progress,
            elapsed,
            self._last_iteration,
            step_name,
        )

    def _tick_timer(self) -> None:
        """Update elapsed time in info bar."""
        if not self._query_in_progress:
            return
        elapsed = time.time() - self._query_start_time
        info_bar = self.query_one(InfoBar)
        if self._last_iteration == 0:
            info_bar.update_thinking(elapsed)
        else:
            info_bar.update_progress(elapsed, self._last_iteration, self._last_step_name)

    def _on_query_complete(self, query_id: int, result: QueryResult, question: str) -> None:
        """Handle completed query (called on main thread)."""
        if self._query_id != query_id:
            return
        self._stop_query()

        # Update tokens
        self._cumulative_prompt_tokens += result.token_usage.prompt_tokens
        self._cumulative_completion_tokens += result.token_usage.completion_tokens
        info_bar = self.query_one(InfoBar)
        info_bar.update_tokens(self._cumulative_prompt_tokens, self._cumulative_completion_tokens)
        info_bar.update_done(result.execution_time, self._last_iteration)

        # Display response
        output = self.query_one(OutputArea)
        output.add_response(result.answer, result.execution_time)

        # Store in session
        total = result.token_usage.total_tokens
        stats = (
            f"---\n"
            f"Execution time: {result.execution_time:.2f}s\n"
            f"Tokens: {total} "
            f"(prompt: {result.token_usage.prompt_tokens}, "
            f"completion: {result.token_usage.completion_tokens})\n"
            f"Trace steps: {len(result.trace.steps)}"
        )
        self._session.add_exchange(question, result.answer, stats)

        # Reset to ready after brief delay
        self.set_timer(2.0, info_bar.reset_phase)

    def _on_query_error(self, query_id: int, error_msg: str) -> None:
        """Handle query error (called on main thread)."""
        if self._query_id != query_id:
            return
        self._stop_query()
        self.query_one(OutputArea).add_system_message(f"Error: {error_msg}")
        self.query_one(InfoBar).reset_phase()

    def _on_shortcut_answer(
        self,
        query_id: int,
        answer: str,
        question: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        """Handle answer from analysis shortcut (called on main thread)."""
        if self._query_id != query_id:
            return
        elapsed = time.time() - self._query_start_time
        self._stop_query()

        self._cumulative_prompt_tokens += prompt_tokens
        self._cumulative_completion_tokens += completion_tokens
        info_bar = self.query_one(InfoBar)
        info_bar.update_tokens(self._cumulative_prompt_tokens, self._cumulative_completion_tokens)
        info_bar.update_done(elapsed, 0)

        output = self.query_one(OutputArea)
        output.add_system_markdown(answer + "\n\n*Answered from codebase analysis.*")

        self._session.add_exchange(
            question, answer, f"---\nAnswered from analysis in {elapsed:.2f}s"
        )

        self.set_timer(2.0, info_bar.reset_phase)

    def _stop_query(self) -> None:
        """Clean up query state."""
        self._query_in_progress = False
        self.query_one(InputArea).query_in_progress = False
        if self._timer_handle is not None:
            self._timer_handle.stop()
            self._timer_handle = None

    # --- Built-in command handlers ---

    def _cmd_help(self, args: str) -> None:
        """Show help."""
        lines = ["Available commands:"]
        for name, desc in self._command_registry.list_commands():
            lines.append(f"  {name:20s} {desc}")
        self.query_one(OutputArea).add_system_message("\n".join(lines))

    def _cmd_write(self, args: str) -> None:
        """Save session transcript."""
        if self._session.exchange_count == 0:
            self.query_one(OutputArea).add_system_message("Nothing to save - no exchanges yet.")
            return
        filename = args.strip() or None
        if filename and not filename.lower().endswith(".md"):
            filename = filename + ".md"
        try:
            path = self._session.write_transcript(filename)
            self.query_one(OutputArea).add_system_message(
                f"Session saved to {path} ({self._session.exchange_count} exchanges)"
            )
        except OSError as e:
            self.query_one(OutputArea).add_system_message(f"Error saving: {e}")

    def _cmd_markdown(self, args: str) -> None:
        """Toggle markdown rendering."""
        output = self.query_one(OutputArea)
        output.markdown_enabled = not output.markdown_enabled
        state = "ON" if output.markdown_enabled else "OFF"
        output.add_system_message(f"Markdown rendering: {state}")

    def _cmd_theme(self, args: str) -> None:
        """Toggle dark/light theme."""
        self.action_toggle_dark()
        theme = "dark" if self.current_theme.dark else "light"
        self.query_one(OutputArea).add_system_message(f"Theme: {theme}")

    def _cmd_quit(self, args: str) -> None:
        """Exit the app."""
        self.exit()
