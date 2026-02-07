"""Tests for script_utils shared utilities."""

import re
import sys
from pathlib import Path

import pytest

from shesha.rlm.trace import StepType, TokenUsage, Trace


class TestThinkingSpinner:
    """Tests for ThinkingSpinner class."""

    def test_start_sets_running(self) -> None:
        """Start should set _running to True and create thread."""
        from examples.script_utils import ThinkingSpinner

        spinner = ThinkingSpinner()
        assert not spinner._running
        assert spinner._thread is None

        spinner.start()
        assert spinner._running
        assert spinner._thread is not None
        assert spinner._thread.is_alive()

        spinner.stop()

    def test_stop_clears_running(self) -> None:
        """Stop should set _running to False."""
        from examples.script_utils import ThinkingSpinner

        spinner = ThinkingSpinner()
        spinner.start()
        spinner.stop()

        assert not spinner._running


class TestFormatProgress:
    """Tests for format_progress function."""

    def test_format_with_elapsed(self) -> None:
        """Format progress with elapsed time."""
        from examples.script_utils import format_progress

        result = format_progress(StepType.CODE_GENERATED, 0, "code", elapsed_seconds=1.5)
        assert "[1.5s]" in result
        assert "[Iteration 1]" in result
        assert "Generating code" in result

    def test_format_without_elapsed(self) -> None:
        """Format progress without elapsed time."""
        from examples.script_utils import format_progress

        result = format_progress(StepType.FINAL_ANSWER, 2, "answer")
        assert "[Iteration 3]" in result
        assert "Final answer" in result


class TestFormatThoughtTime:
    """Tests for format_thought_time function."""

    def test_singular_second(self) -> None:
        """One second should use singular form."""
        from examples.script_utils import format_thought_time

        result = format_thought_time(1.2)
        assert result == "[Thought for 1 second]"

    def test_plural_seconds(self) -> None:
        """Multiple seconds should use plural form."""
        from examples.script_utils import format_thought_time

        result = format_thought_time(5.7)
        assert result == "[Thought for 6 seconds]"


class TestFormatStats:
    """Tests for format_stats function."""

    def test_format_stats_output(self) -> None:
        """Format stats should include all metrics."""
        from examples.script_utils import format_stats

        token_usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
        trace = Trace(steps=[])

        result = format_stats(2.5, token_usage, trace)
        assert "Execution time: 2.50s" in result
        assert "Tokens: 150" in result
        assert "prompt: 100" in result
        assert "completion: 50" in result
        assert "Trace steps: 0" in result


class TestFormatHistoryPrefix:
    """Tests for format_history_prefix function."""

    def test_empty_history(self) -> None:
        """Empty history returns empty string."""
        from examples.script_utils import format_history_prefix

        assert format_history_prefix([]) == ""

    def test_single_exchange(self) -> None:
        """Single exchange formats correctly."""
        from examples.script_utils import format_history_prefix

        history = [("What is X?", "X is Y.", "")]
        result = format_history_prefix(history)
        assert "Previous conversation:" in result
        assert "Q1: What is X?" in result
        assert "A1: X is Y." in result
        assert "Current question:" in result


class TestIsExitCommand:
    """Tests for is_exit_command function."""

    def test_quit_is_exit(self) -> None:
        """'quit' should be recognized as exit."""
        from examples.script_utils import is_exit_command

        assert is_exit_command("quit")
        assert is_exit_command("QUIT")
        assert is_exit_command("Quit")

    def test_exit_is_exit(self) -> None:
        """'exit' should be recognized as exit."""
        from examples.script_utils import is_exit_command

        assert is_exit_command("exit")
        assert is_exit_command("EXIT")

    def test_other_not_exit(self) -> None:
        """Other inputs should not be exit commands."""
        from examples.script_utils import is_exit_command

        assert not is_exit_command("hello")
        assert not is_exit_command("question")


class TestIsHelpCommand:
    """Tests for is_help_command function."""

    def test_help_is_help(self) -> None:
        """'help' should be recognized as help command."""
        from examples.script_utils import is_help_command

        assert is_help_command("help")
        assert is_help_command("HELP")
        assert is_help_command("Help")

    def test_question_mark_is_help(self) -> None:
        """'?' should be recognized as help command."""
        from examples.script_utils import is_help_command

        assert is_help_command("?")

    def test_other_not_help(self) -> None:
        """Other inputs should not be help commands."""
        from examples.script_utils import is_help_command

        assert not is_help_command("hello")
        assert not is_help_command("help me")
        assert not is_help_command("??")


class TestShouldWarnHistorySize:
    """Tests for should_warn_history_size function."""

    def test_small_history_no_warning(self) -> None:
        """Small history should not trigger warning."""
        from examples.script_utils import should_warn_history_size

        history = [("q", "a", "") for _ in range(5)]
        assert not should_warn_history_size(history)

    def test_many_exchanges_warns(self) -> None:
        """10+ exchanges should trigger warning."""
        from examples.script_utils import should_warn_history_size

        history = [("q", "a", "") for _ in range(10)]
        assert should_warn_history_size(history)

    def test_large_chars_warns(self) -> None:
        """50k+ chars should trigger warning."""
        from examples.script_utils import should_warn_history_size

        # Create history with large content (50k+ chars total)
        large_text = "x" * 50000
        history = [("q", large_text, "")]
        assert should_warn_history_size(history)


class TestInstallUrllib3CleanupHook:
    """Tests for install_urllib3_cleanup_hook function."""

    def test_hook_installed(self) -> None:
        """Hook should be installed on sys.unraisablehook."""
        from examples.script_utils import install_urllib3_cleanup_hook

        original = sys.unraisablehook
        install_urllib3_cleanup_hook()

        # Hook should be changed
        assert sys.unraisablehook != original

        # Restore original
        sys.unraisablehook = original


class TestIsWriteCommand:
    """Tests for is_write_command function."""

    def test_write_alone_is_write_command(self) -> None:
        """'write' by itself should be recognized."""
        from examples.script_utils import is_write_command

        assert is_write_command("write")
        assert is_write_command("WRITE")
        assert is_write_command("Write")

    def test_write_with_filename_is_write_command(self) -> None:
        """'write <filename>' should be recognized."""
        from examples.script_utils import is_write_command

        assert is_write_command("write myfile.md")
        assert is_write_command("write path/to/file.md")
        assert is_write_command("WRITE session.md")

    def test_other_not_write_command(self) -> None:
        """Other inputs should not be write commands."""
        from examples.script_utils import is_write_command

        assert not is_write_command("hello")
        assert not is_write_command("writeup")
        assert not is_write_command("rewrite")
        assert not is_write_command("")

    def test_write_with_special_whitespace(self) -> None:
        """Write command should handle tabs and unicode spaces."""
        from examples.script_utils import is_write_command

        # Tab between write and filename
        assert is_write_command("write\ttest.md")
        # Non-breaking space (U+00A0)
        assert is_write_command("write\u00a0test.md")
        # Em space (U+2003)
        assert is_write_command("write\u2003test.md")


class TestParseWriteCommand:
    """Tests for parse_write_command function."""

    def test_write_alone_returns_none(self) -> None:
        """'write' by itself returns None (auto-generate filename)."""
        from examples.script_utils import parse_write_command

        assert parse_write_command("write") is None
        assert parse_write_command("WRITE") is None

    def test_write_with_filename_returns_filename(self) -> None:
        """'write <filename>' returns the filename."""
        from examples.script_utils import parse_write_command

        assert parse_write_command("write myfile.md") == "myfile.md"
        assert parse_write_command("write path/to/file.md") == "path/to/file.md"

    def test_strips_whitespace_from_filename(self) -> None:
        """Whitespace around filename should be stripped."""
        from examples.script_utils import parse_write_command

        assert parse_write_command("write   myfile.md   ") == "myfile.md"
        assert parse_write_command("WRITE    session.md") == "session.md"

    def test_adds_md_extension_if_missing(self) -> None:
        """Add .md extension if not present."""
        from examples.script_utils import parse_write_command

        assert parse_write_command("write myfile") == "myfile.md"
        assert parse_write_command("write path/to/file") == "path/to/file.md"

    def test_preserves_md_extension(self) -> None:
        """Don't double-add .md extension."""
        from examples.script_utils import parse_write_command

        assert parse_write_command("write myfile.md") == "myfile.md"
        assert parse_write_command("write FILE.MD") == "FILE.MD"


class TestGenerateSessionFilename:
    """Tests for generate_session_filename function."""

    def test_filename_format(self) -> None:
        """Filename should match session-YYYY-MM-DD-HHMMSS.md pattern."""
        from examples.script_utils import generate_session_filename

        filename = generate_session_filename()
        pattern = r"^session-\d{4}-\d{2}-\d{2}-\d{6}\.md$"
        assert re.match(pattern, filename), f"'{filename}' doesn't match expected pattern"

    def test_filename_has_md_extension(self) -> None:
        """Filename should end with .md."""
        from examples.script_utils import generate_session_filename

        filename = generate_session_filename()
        assert filename.endswith(".md")

    def test_filename_starts_with_session(self) -> None:
        """Filename should start with 'session-'."""
        from examples.script_utils import generate_session_filename

        filename = generate_session_filename()
        assert filename.startswith("session-")


class TestFormatSessionTranscript:
    """Tests for format_session_transcript function."""

    def test_empty_history(self) -> None:
        """Empty history should still produce valid markdown with header."""
        from examples.script_utils import format_session_transcript

        result = format_session_transcript([], "test-project")
        assert "# Session Transcript" in result
        assert "**Project:** test-project" in result
        assert "**Exchanges:** 0" in result

    def test_single_exchange(self) -> None:
        """Single exchange should be formatted correctly."""
        from examples.script_utils import format_session_transcript

        history = [("What is X?", "X is a variable.", "")]
        result = format_session_transcript(history, "my-project")

        assert "# Session Transcript" in result
        assert "**Project:** my-project" in result
        assert "**Exchanges:** 1" in result
        assert "**User:** What is X?" in result
        assert "X is a variable." in result

    def test_multiple_exchanges(self) -> None:
        """Multiple exchanges should be separated by horizontal rules."""
        from examples.script_utils import format_session_transcript

        history = [("Q1?", "A1.", ""), ("Q2?", "A2.", "")]
        result = format_session_transcript(history, "project")

        assert "**Exchanges:** 2" in result
        assert "**User:** Q1?" in result
        assert "A1." in result
        assert "**User:** Q2?" in result
        assert "A2." in result
        # Should have separators between exchanges
        assert result.count("---") >= 2

    def test_includes_date(self) -> None:
        """Transcript should include a date field."""
        from examples.script_utils import format_session_transcript

        result = format_session_transcript([], "project")
        assert "**Date:**" in result

    def test_includes_stats_in_transcript(self) -> None:
        """Transcript should include execution stats for each exchange."""
        from examples.script_utils import format_session_transcript

        stats = "Execution time: 2.50s\nTokens: 150 (prompt: 100, completion: 50)\nTrace steps: 3"
        history: list[tuple[str, str, str]] = [("What is X?", "X is Y.", stats)]
        result = format_session_transcript(history, "project")

        assert "**User:** What is X?" in result
        assert "X is Y." in result
        assert "Execution time: 2.50s" in result
        assert "Tokens: 150" in result
        assert "Trace steps: 3" in result

    def test_stats_appear_after_answer(self) -> None:
        """Stats should appear after the answer, not before it."""
        from examples.script_utils import format_session_transcript

        stats = "Execution time: 1.00s\nTokens: 100 (prompt: 80, completion: 20)\nTrace steps: 2"
        history: list[tuple[str, str, str]] = [("Q?", "The answer.", stats)]
        result = format_session_transcript(history, "project")

        answer_pos = result.index("The answer.")
        stats_pos = result.index("Execution time: 1.00s")
        assert stats_pos > answer_pos


class TestWriteSession:
    """Tests for write_session function."""

    def test_writes_file_to_specified_path(self, tmp_path: Path) -> None:
        """Should write transcript to specified filename."""
        from examples.script_utils import write_session

        history = [("Q?", "A.", "")]
        filepath = tmp_path / "test.md"

        result = write_session(history, "project", str(filepath))

        assert result == str(filepath)
        assert filepath.exists()
        content = filepath.read_text()
        assert "**User:** Q?" in content

    def test_auto_generates_filename(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should auto-generate filename when None provided."""
        from examples.script_utils import write_session

        # Change to tmp_path for the test
        monkeypatch.chdir(tmp_path)

        history = [("Q?", "A.", "")]
        result = write_session(history, "project", None)

        assert result.startswith("session-")
        assert result.endswith(".md")
        assert Path(result).exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create parent directories if they don't exist."""
        from examples.script_utils import write_session

        history = [("Q?", "A.", "")]
        filepath = tmp_path / "subdir" / "nested" / "test.md"

        write_session(history, "project", str(filepath))

        assert filepath.exists()

    def test_returns_path_written(self, tmp_path: Path) -> None:
        """Should return the path that was written to."""
        from examples.script_utils import write_session

        history = [("Q?", "A.", "")]
        filepath = tmp_path / "output.md"

        result = write_session(history, "project", str(filepath))

        assert result == str(filepath)


class TestAnalysisCommands:
    """Tests for analysis command detection."""

    def test_is_analysis_command_analysis(self) -> None:
        """'analysis' is recognized as analysis command."""
        from examples.script_utils import is_analysis_command

        assert is_analysis_command("analysis") is True

    def test_is_analysis_command_show_analysis(self) -> None:
        """'show analysis' is recognized as analysis command."""
        from examples.script_utils import is_analysis_command

        assert is_analysis_command("show analysis") is True

    def test_is_analysis_command_case_insensitive(self) -> None:
        """Analysis command is case insensitive."""
        from examples.script_utils import is_analysis_command

        assert is_analysis_command("ANALYSIS") is True
        assert is_analysis_command("Analysis") is True

    def test_is_analysis_command_other(self) -> None:
        """Other commands are not analysis commands."""
        from examples.script_utils import is_analysis_command

        assert is_analysis_command("help") is False
        assert is_analysis_command("quit") is False


class TestRegenerateCommands:
    """Tests for regenerate command detection."""

    def test_is_regenerate_command_analyze(self) -> None:
        """'analyze' is recognized as regenerate command."""
        from examples.script_utils import is_regenerate_command

        assert is_regenerate_command("analyze") is True

    def test_is_regenerate_command_regenerate(self) -> None:
        """'regenerate analysis' is recognized as regenerate command."""
        from examples.script_utils import is_regenerate_command

        assert is_regenerate_command("regenerate analysis") is True

    def test_is_regenerate_command_case_insensitive(self) -> None:
        """Regenerate command is case insensitive."""
        from examples.script_utils import is_regenerate_command

        assert is_regenerate_command("ANALYZE") is True

    def test_is_regenerate_command_other(self) -> None:
        """Other commands are not regenerate commands."""
        from examples.script_utils import is_regenerate_command

        assert is_regenerate_command("analysis") is False
        assert is_regenerate_command("help") is False


class TestFormatAnalysisAsContext:
    """Tests for format_analysis_as_context function."""

    def test_includes_header_and_overview(self) -> None:
        """Context string includes header and overview text."""
        from examples.script_utils import format_analysis_as_context
        from shesha.models import RepoAnalysis

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="A Python web application.",
            components=[],
            external_dependencies=[],
        )

        result = format_analysis_as_context(analysis)

        assert "=== Codebase Analysis ===" in result
        assert "A Python web application." in result
        assert result.rstrip().endswith("===")

    def test_includes_components(self) -> None:
        """Context string includes component details."""
        from examples.script_utils import format_analysis_as_context
        from shesha.models import AnalysisComponent, RepoAnalysis

        comp = AnalysisComponent(
            name="API Server",
            path="api/",
            description="REST API for user management",
            apis=[{"type": "rest", "endpoints": ["/users", "/auth"]}],
            models=["User", "Session"],
            entry_points=["api/main.py"],
            internal_dependencies=[],
        )
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test app",
            components=[comp],
            external_dependencies=[],
        )

        result = format_analysis_as_context(analysis)

        assert "Components:" in result
        assert "API Server (api/)" in result
        assert "REST API for user management" in result
        assert "APIs (rest): /users, /auth" in result
        assert "Models: User, Session" in result

    def test_includes_external_dependencies(self) -> None:
        """Context string includes external dependencies."""
        from examples.script_utils import format_analysis_as_context
        from shesha.models import AnalysisExternalDep, RepoAnalysis

        dep = AnalysisExternalDep(
            name="PostgreSQL",
            type="database",
            description="Primary data store",
            used_by=["API Server"],
            optional=False,
        )
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test",
            components=[],
            external_dependencies=[dep],
        )

        result = format_analysis_as_context(analysis)

        assert "External Dependencies:" in result
        assert "PostgreSQL (database): Primary data store" in result

    def test_empty_analysis_still_valid(self) -> None:
        """Minimal analysis with no components or deps still produces valid output."""
        from examples.script_utils import format_analysis_as_context
        from shesha.models import RepoAnalysis

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Simple app",
            components=[],
            external_dependencies=[],
        )

        result = format_analysis_as_context(analysis)

        assert "=== Codebase Analysis ===" in result
        assert "Simple app" in result
        # No Components or External Dependencies section
        assert "Components:" not in result
        assert "External Dependencies:" not in result


class TestFormatVerifiedOutput:
    """Tests for format_verified_output()."""

    def test_formats_summary_and_appendix(self) -> None:
        """Output contains both verified findings and appendix."""
        from examples.script_utils import format_verified_output
        from shesha.rlm.semantic_verification import (
            FindingVerification,
            SemanticVerificationReport,
        )

        report = SemanticVerificationReport(
            findings=[
                FindingVerification(
                    finding_id="P1.1",
                    original_claim="Real issue",
                    confidence="high",
                    reason="Confirmed by code.",
                    evidence_classification="code_analysis",
                    flags=[],
                ),
                FindingVerification(
                    finding_id="P0.1",
                    original_claim="False alarm",
                    confidence="low",
                    reason="Standard idiom.",
                    evidence_classification="code_analysis",
                    flags=["standard_idiom"],
                ),
            ],
            content_type="code",
        )
        original_answer = "## P1.1: Real issue\nDetails.\n\n## P0.1: False alarm\nMore details."
        output = format_verified_output(original_answer, report)

        assert "Verified Findings" in output
        assert "Verification Appendix" in output
        assert "P1.1" in output
        assert "P0.1" in output
        assert "standard_idiom" in output

    def test_no_high_confidence_shows_message(self) -> None:
        """When no findings are high/medium confidence, shows appropriate message."""
        from examples.script_utils import format_verified_output
        from shesha.rlm.semantic_verification import (
            FindingVerification,
            SemanticVerificationReport,
        )

        report = SemanticVerificationReport(
            findings=[
                FindingVerification(
                    finding_id="P0.1",
                    original_claim="Bogus",
                    confidence="low",
                    reason="Not real.",
                    evidence_classification="code_analysis",
                    flags=[],
                ),
            ],
            content_type="general",
        )
        output = format_verified_output("Original", report)
        assert "0" in output or "no verified findings" in output.lower() or "None" in output

    def test_all_high_confidence_no_appendix_content(self) -> None:
        """When all findings are high confidence, appendix says none filtered."""
        from examples.script_utils import format_verified_output
        from shesha.rlm.semantic_verification import (
            FindingVerification,
            SemanticVerificationReport,
        )

        report = SemanticVerificationReport(
            findings=[
                FindingVerification(
                    finding_id="P1.1",
                    original_claim="Good finding",
                    confidence="high",
                    reason="Confirmed.",
                    evidence_classification="code_analysis",
                    flags=[],
                ),
            ],
            content_type="code",
        )
        output = format_verified_output("Original", report)
        assert "Verified Findings" in output
        assert (
            "0 findings filtered" in output
            or "no findings filtered" in output.lower()
            or "Appendix" in output
        )


class TestFormatAnalysisForDisplay:
    """Tests for analysis display formatting."""

    def test_format_analysis_includes_header(self) -> None:
        """Formatted analysis includes header with date."""
        from examples.script_utils import format_analysis_for_display
        from shesha.models import RepoAnalysis

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123def456",
            overview="A test application.",
            components=[],
            external_dependencies=[],
        )

        output = format_analysis_for_display(analysis)

        assert "2026-02-06" in output
        assert "abc123de" in output  # First 8 chars of SHA

    def test_format_analysis_includes_overview(self) -> None:
        """Formatted analysis includes overview section."""
        from examples.script_utils import format_analysis_for_display
        from shesha.models import RepoAnalysis

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="This is a complex microservices application.",
            components=[],
            external_dependencies=[],
        )

        output = format_analysis_for_display(analysis)

        assert "Overview" in output
        assert "This is a complex microservices application." in output

    def test_format_analysis_includes_components(self) -> None:
        """Formatted analysis includes components."""
        from examples.script_utils import format_analysis_for_display
        from shesha.models import AnalysisComponent, RepoAnalysis

        comp = AnalysisComponent(
            name="API Server",
            path="api/",
            description="REST API for user management",
            apis=[{"type": "rest", "endpoints": ["/users", "/auth"]}],
            models=["User", "Session"],
            entry_points=["api/main.py"],
            internal_dependencies=[],
        )
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test",
            components=[comp],
            external_dependencies=[],
        )

        output = format_analysis_for_display(analysis)

        assert "API Server" in output
        assert "api/" in output
        assert "REST API for user management" in output
        assert "User" in output

    def test_format_analysis_includes_caveats(self) -> None:
        """Formatted analysis includes caveats warning."""
        from examples.script_utils import format_analysis_for_display
        from shesha.models import RepoAnalysis

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test",
            components=[],
            external_dependencies=[],
            caveats="This may be wrong.",
        )

        output = format_analysis_for_display(analysis)

        assert "This may be wrong." in output

    def test_format_analysis_includes_external_dependencies(self) -> None:
        """Formatted analysis includes external dependencies."""
        from examples.script_utils import format_analysis_for_display
        from shesha.models import AnalysisExternalDep, RepoAnalysis

        dep = AnalysisExternalDep(
            name="PostgreSQL",
            type="database",
            description="Primary data store",
            used_by=["API Server"],
            optional=False,
        )
        dep_optional = AnalysisExternalDep(
            name="Redis",
            type="cache",
            description="Session cache",
            used_by=["API Server"],
            optional=True,
        )
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test",
            components=[],
            external_dependencies=[dep, dep_optional],
        )

        output = format_analysis_for_display(analysis)

        assert "External Dependencies" in output
        assert "PostgreSQL" in output
        assert "(optional)" in output
        assert "Redis" in output
