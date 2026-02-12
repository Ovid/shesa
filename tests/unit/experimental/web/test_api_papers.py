"""Tests for papers REST endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from shesha.experimental.web.api import create_api


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


def test_list_papers_in_topic(client: TestClient, mock_state: MagicMock) -> None:
    from datetime import datetime

    from shesha.experimental.arxiv.models import PaperMeta

    mock_state.topic_mgr.resolve.return_value = "proj-id"
    mock_state.topic_mgr._storage.list_documents.return_value = ["2501.08753"]

    meta = MagicMock(spec=PaperMeta)
    meta.arxiv_id = "2501.08753"
    meta.title = "Test Paper"
    meta.authors = ["Author A"]
    meta.abstract = "Abstract"
    meta.primary_category = "q-bio.PE"
    meta.published = datetime(2025, 1, 15)
    meta.arxiv_url = "https://arxiv.org/abs/2501.08753"
    meta.source_type = "latex"
    mock_state.cache.get_meta.return_value = meta

    resp = client.get("/api/topics/test-topic/papers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["arxiv_id"] == "2501.08753"
    assert data[0]["title"] == "Test Paper"


def test_list_papers_topic_not_found(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.resolve.return_value = None
    resp = client.get("/api/topics/nonexistent/papers")
    assert resp.status_code == 404


def test_add_paper_cached(client: TestClient, mock_state: MagicMock) -> None:
    """Paper already in cache copies immediately, returns 200."""
    mock_state.cache.has.return_value = True
    mock_state.topic_mgr.resolve.side_effect = lambda name: f"proj-{name}"

    mock_doc = MagicMock()
    with patch("shesha.experimental.web.api.to_parsed_document", return_value=mock_doc):
        resp = client.post(
            "/api/papers/add",
            json={"arxiv_id": "2501.08753", "topics": ["Chess"]},
        )

    assert resp.status_code == 200
    mock_state.topic_mgr._storage.store_document.assert_called_once()


def test_add_paper_needs_download(client: TestClient, mock_state: MagicMock) -> None:
    """Paper not cached returns 202 with task_id."""
    mock_state.cache.has.return_value = False
    mock_state.topic_mgr.resolve.side_effect = lambda name: f"proj-{name}"

    resp = client.post(
        "/api/papers/add",
        json={"arxiv_id": "2501.08753", "topics": ["Chess"]},
    )

    assert resp.status_code == 202
    data = resp.json()
    assert "task_id" in data


def test_add_paper_multi_topic_cached(client: TestClient, mock_state: MagicMock) -> None:
    """Cached paper added to multiple topics."""
    mock_state.cache.has.return_value = True
    mock_state.topic_mgr.resolve.side_effect = lambda name: f"proj-{name}"

    mock_doc = MagicMock()
    with patch("shesha.experimental.web.api.to_parsed_document", return_value=mock_doc):
        resp = client.post(
            "/api/papers/add",
            json={"arxiv_id": "2501.08753", "topics": ["Chess", "Education"]},
        )

    assert resp.status_code == 200
    assert mock_state.topic_mgr._storage.store_document.call_count == 2


def test_remove_paper(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.resolve.return_value = "proj-id"
    resp = client.delete("/api/topics/chess/papers/2501.08753")
    assert resp.status_code == 200
    mock_state.topic_mgr._storage.delete_document.assert_called_once_with("proj-id", "2501.08753")


def test_remove_paper_topic_not_found(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.topic_mgr.resolve.return_value = None
    resp = client.delete("/api/topics/nonexistent/papers/2501.08753")
    assert resp.status_code == 404


def test_download_task_status(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.download_tasks = {
        "task-123": {
            "papers": [{"arxiv_id": "2501.08753", "status": "downloading"}],
        }
    }
    resp = client.get("/api/papers/tasks/task-123")
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "task-123"


def test_download_task_not_found(client: TestClient, mock_state: MagicMock) -> None:
    mock_state.download_tasks = {}
    resp = client.get("/api/papers/tasks/nonexistent")
    assert resp.status_code == 404
