"""Tests for WebSocket query handler."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from shesha.experimental.web.api import create_api
from shesha.rlm.trace import TokenUsage, Trace


@pytest.fixture
def mock_state() -> MagicMock:
    state = MagicMock()
    state.model = "test-model"
    state.download_tasks = {}
    return state


@pytest.fixture
def client(mock_state: MagicMock) -> TestClient:
    app = create_api(mock_state)
    return TestClient(app)


def test_ws_query_returns_complete(
    client: TestClient, mock_state: MagicMock
) -> None:
    """WebSocket query returns a complete message with answer."""
    mock_project = MagicMock()
    mock_result = MagicMock()
    mock_result.answer = "The answer is 42."
    mock_result.token_usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
    mock_result.execution_time = 1.5
    mock_result.trace = Trace(steps=[])
    mock_project.query.return_value = mock_result

    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.shesha.get_project.return_value = mock_project
    mock_state.topic_mgr._storage.list_documents.return_value = ["doc1"]
    mock_state.topic_mgr._storage.list_traces.return_value = []

    with patch("shesha.experimental.web.ws.WebConversationSession") as mock_sess_cls:
        mock_session = MagicMock()
        mock_session.format_history_prefix.return_value = ""
        mock_sess_cls.return_value = mock_session

        with client.websocket_connect("/api/ws") as ws:
            ws.send_json({"type": "query", "topic": "test", "question": "What?"})
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("complete", "error"):
                    break

    complete = [m for m in messages if m["type"] == "complete"]
    assert len(complete) == 1
    assert complete[0]["answer"] == "The answer is 42."


def test_ws_query_no_topic(client: TestClient, mock_state: MagicMock) -> None:
    """Query for non-existent topic returns error."""
    mock_state.topic_mgr.resolve.return_value = None
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "query", "topic": "nope", "question": "What?"})
        msg = ws.receive_json()
    assert msg["type"] == "error"


def test_ws_cancel(client: TestClient, mock_state: MagicMock) -> None:
    """Cancel message when no query is running returns cancelled."""
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "cancel"})
        msg = ws.receive_json()
    assert msg["type"] == "cancelled"
