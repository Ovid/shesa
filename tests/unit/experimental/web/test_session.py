"""Tests for persistent web conversation session."""

from pathlib import Path

import pytest

from shesha.experimental.web.session import WebConversationSession


@pytest.fixture
def session_dir(tmp_path: Path) -> Path:
    return tmp_path / "projects" / "test-topic"


@pytest.fixture
def session(session_dir: Path) -> WebConversationSession:
    session_dir.mkdir(parents=True)
    return WebConversationSession(session_dir)


def test_empty_session_has_no_exchanges(session: WebConversationSession) -> None:
    assert session.list_exchanges() == []


def test_add_exchange(session: WebConversationSession) -> None:
    session.add_exchange(
        question="What is this?",
        answer="A test.",
        trace_id="trace-123",
        tokens={"prompt": 100, "completion": 50, "total": 150},
        execution_time=1.5,
        model="gpt-5-mini",
    )
    exchanges = session.list_exchanges()
    assert len(exchanges) == 1
    assert exchanges[0]["question"] == "What is this?"
    assert exchanges[0]["trace_id"] == "trace-123"
    assert "exchange_id" in exchanges[0]
    assert "timestamp" in exchanges[0]


def test_persistence_across_instances(session_dir: Path) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    s1 = WebConversationSession(session_dir)
    s1.add_exchange(
        question="Q1",
        answer="A1",
        trace_id="t1",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
    )

    s2 = WebConversationSession(session_dir)
    exchanges = s2.list_exchanges()
    assert len(exchanges) == 1
    assert exchanges[0]["question"] == "Q1"


def test_clear_history(session: WebConversationSession) -> None:
    session.add_exchange(
        question="Q",
        answer="A",
        trace_id="t",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
    )
    session.clear()
    assert session.list_exchanges() == []


def test_format_history_prefix_empty(session: WebConversationSession) -> None:
    assert session.format_history_prefix() == ""


def test_format_history_prefix_with_exchanges(session: WebConversationSession) -> None:
    session.add_exchange(
        question="What is X?",
        answer="X is Y.",
        trace_id="t1",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
    )
    prefix = session.format_history_prefix()
    assert "Previous conversation:" in prefix
    assert "What is X?" in prefix
    assert "X is Y." in prefix


def test_format_transcript(session: WebConversationSession) -> None:
    session.add_exchange(
        question="What?",
        answer="This.",
        trace_id="t1",
        tokens={"prompt": 100, "completion": 50, "total": 150},
        execution_time=1.5,
        model="gpt-5-mini",
    )
    transcript = session.format_transcript()
    assert "What?" in transcript
    assert "This." in transcript


def test_context_chars(session: WebConversationSession) -> None:
    """context_chars returns total character count of history."""
    assert session.context_chars() == 0
    session.add_exchange(
        question="Hello",
        answer="World",
        trace_id="t1",
        tokens={"prompt": 10, "completion": 5, "total": 15},
        execution_time=0.5,
        model="test",
    )
    assert session.context_chars() > 0
