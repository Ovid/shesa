"""Tests for exception classes."""

from shesha.exceptions import (
    AuthenticationError,
    EngineNotConfiguredError,
    RepoIngestError,
    SheshaError,
    TraceWriteError,
)


class TestRepoExceptions:
    """Tests for repository-related exceptions."""

    def test_authentication_error_message(self):
        """AuthenticationError formats message with URL."""
        err = AuthenticationError("https://github.com/org/private-repo")
        assert "private-repo" in str(err)
        assert "token" in str(err).lower()

    def test_repo_ingest_error_preserves_cause(self):
        """RepoIngestError preserves the original cause."""
        cause = RuntimeError("git clone failed")
        err = RepoIngestError("https://github.com/org/repo", cause)
        assert err.__cause__ is cause
        assert "https://github.com/org/repo" in str(err)


class TestTraceWriteError:
    """Tests for TraceWriteError."""

    def test_is_subclass_of_shesha_error(self):
        """TraceWriteError is a SheshaError subclass."""
        assert issubclass(TraceWriteError, SheshaError)

    def test_accepts_message(self):
        """TraceWriteError can take a custom message."""
        err = TraceWriteError("disk full")
        assert "disk full" in str(err)


class TestEngineNotConfiguredError:
    """Tests for EngineNotConfiguredError."""

    def test_is_subclass_of_shesha_error(self):
        """EngineNotConfiguredError is a SheshaError subclass."""
        assert issubclass(EngineNotConfiguredError, SheshaError)

    def test_default_message_mentions_engine(self):
        """EngineNotConfiguredError has default message mentioning engine."""
        err = EngineNotConfiguredError()
        assert "engine" in str(err).lower()
