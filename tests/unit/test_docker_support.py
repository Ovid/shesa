"""Tests for Docker-supported installation and graceful degradation."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from docker.errors import DockerException

from shesha import Shesha
from shesha.exceptions import SheshaError


class TestDockerGracefulDegradation:
    """Tests for Shesha behavior when Docker is missing."""

    def test_init_succeeds_without_docker(self, tmp_path: Path):
        """Shesha should initialize even if Docker is not running."""
        with patch("shesha.shesha.docker") as mock_docker:
            mock_docker.from_env.side_effect = DockerException("Connection refused")
            
            # This should NOT raise RuntimeError anymore
            shesha = Shesha(model="test-model", storage_path=tmp_path)
            
            assert shesha._docker_available is False
            assert shesha._pool is None

    def test_query_raises_when_docker_missing(self, tmp_path: Path):
        """Querying should raise a clear error if Docker is missing."""
        with patch("shesha.shesha.docker") as mock_docker:
            mock_docker.from_env.side_effect = DockerException("Connection refused")
            shesha = Shesha(model="test-model", storage_path=tmp_path)
            
            project = shesha.create_project("test-proj")
            
            with pytest.raises(RuntimeError) as exc_info:
                project.query("some question")
            
            assert "Docker is required for queries" in str(exc_info.value)

    def test_repo_ingestion_works_without_docker(self, tmp_path: Path):
        """Repo ingestion (parsing) should work without Docker as it's host-side."""
        with (
            patch("shesha.shesha.docker") as mock_docker,
            patch("shesha.shesha.RepoIngester") as mock_ingester_cls,
        ):
            mock_docker.from_env.side_effect = DockerException("Connection refused")
            
            mock_ingester = mock_ingester_cls.return_value
            mock_ingester.is_local_path.return_value = True
            mock_ingester.is_git_repo.return_value = True
            mock_ingester.list_files_from_path.return_value = []
            mock_ingester.get_sha_from_path.return_value = "abc"
            mock_ingester.get_source_url.return_value = "/tmp/repo"
            
            shesha = Shesha(model="test-model", storage_path=tmp_path)
            
            result = shesha.create_project_from_repo(url="/tmp/repo", name="test-repo")
            assert result.status == "created"
