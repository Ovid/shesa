"""Tests for main Shesha class."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shesha import Shesha
from shesha.models import RepoProjectResult


@pytest.fixture
def shesha_instance(tmp_path: Path) -> Shesha:
    """Create a Shesha instance with mocked Docker for testing."""
    with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
        shesha = Shesha(model="test-model", storage_path=tmp_path)
        return shesha


class TestDockerAvailability:
    """Tests for Docker availability check at startup."""

    def test_raises_clear_error_when_docker_not_running(self, tmp_path: Path):
        """Shesha raises clear error at init when Docker is not running.

        Users should get a helpful error message immediately at startup,
        not when they first try to run a query.
        """
        from docker.errors import DockerException

        with patch("shesha.shesha.docker") as mock_docker:
            mock_docker.from_env.side_effect = DockerException(
                "Error while fetching server API version: "
                "('Connection aborted.', ConnectionRefusedError(61, 'Connection refused'))"
            )

            with pytest.raises(RuntimeError) as exc_info:
                Shesha(model="test-model", storage_path=tmp_path)

            error_msg = str(exc_info.value)
            assert "Docker" in error_msg
            assert "not running" in error_msg or "start" in error_msg.lower()

    def test_raises_helpful_error_when_socket_not_found(self, tmp_path: Path):
        """Shesha raises helpful error mentioning Podman when socket not found.

        Podman users get FileNotFoundError when DOCKER_HOST isn't set. The error
        message should guide them to set DOCKER_HOST.
        """
        from docker.errors import DockerException

        with patch("shesha.shesha.docker") as mock_docker:
            # This is the exact error pattern Podman users see
            mock_docker.from_env.side_effect = DockerException(
                "Error while fetching server API version: "
                "('Connection aborted.', FileNotFoundError(2, 'No such file or directory'))"
            )

            with pytest.raises(RuntimeError) as exc_info:
                Shesha(model="test-model", storage_path=tmp_path)

            error_msg = str(exc_info.value)
            assert "DOCKER_HOST" in error_msg
            assert "Podman" in error_msg or "podman" in error_msg


class TestShesha:
    """Tests for Shesha class."""

    def test_create_project(self, tmp_path: Path):
        """Creating a project returns a Project instance."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            shesha = Shesha(
                model="test-model",
                storage_path=tmp_path,
            )
            project = shesha.create_project("my-project")

            assert project.project_id == "my-project"

    def test_list_projects(self, tmp_path: Path):
        """List projects returns project IDs."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            shesha = Shesha(model="test-model", storage_path=tmp_path)
            shesha.create_project("project-a")
            shesha.create_project("project-b")

            projects = shesha.list_projects()
            assert "project-a" in projects
            assert "project-b" in projects

    def test_get_project(self, tmp_path: Path):
        """Get project returns existing project."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            shesha = Shesha(model="test-model", storage_path=tmp_path)
            shesha.create_project("existing")

            project = shesha.get_project("existing")
            assert project.project_id == "existing"

    def test_delete_project(self, tmp_path: Path):
        """Delete project removes it."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            shesha = Shesha(model="test-model", storage_path=tmp_path)
            shesha.create_project("to-delete")
            shesha.delete_project("to-delete")

            assert "to-delete" not in shesha.list_projects()

    def test_register_parser(self, tmp_path: Path):
        """Register custom parser adds it to the registry."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            shesha = Shesha(model="test-model", storage_path=tmp_path)

            # Create a mock custom parser
            mock_parser = MagicMock()
            mock_parser.can_parse.return_value = True

            shesha.register_parser(mock_parser)

            # The parser should now be in the registry
            assert mock_parser in shesha._parser_registry._parsers

    def test_stop_after_restart_stops_pool(self, tmp_path: Path):
        """Stop after start-stop-start cycle should stop the pool."""
        mock_pool = MagicMock()
        with (
            patch("shesha.shesha.docker"),
            patch("shesha.shesha.ContainerPool", return_value=mock_pool),
        ):
            shesha = Shesha(model="test-model", storage_path=tmp_path)

            # First cycle: start then stop
            shesha.start()
            shesha.stop()

            # Second cycle: start again
            shesha.start()

            # Reset call count to track second stop
            mock_pool.stop.reset_mock()

            # Second stop should call pool.stop()
            shesha.stop()

            mock_pool.stop.assert_called_once()

    def test_delete_project_cleans_up_remote_repo(self, tmp_path: Path):
        """delete_project removes cloned repo for remote projects by default."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha._storage.create_project("to-delete")

                shesha.delete_project("to-delete")

                mock_ingester.delete_repo.assert_called_once_with("to-delete")

    def test_delete_project_skips_cleanup_for_local_repo(self, tmp_path: Path):
        """delete_project does not call delete_repo for local repos."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "/path/to/local/repo"
                mock_ingester.is_local_path.return_value = True

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha._storage.create_project("local-project")

                shesha.delete_project("local-project")

                mock_ingester.delete_repo.assert_not_called()

    def test_delete_project_respects_cleanup_repo_false(self, tmp_path: Path):
        """delete_project skips repo cleanup when cleanup_repo=False."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha._storage.create_project("to-delete")

                shesha.delete_project("to-delete", cleanup_repo=False)

                mock_ingester.delete_repo.assert_not_called()


class TestCreateProjectFromRepo:
    """Tests for create_project_from_repo method."""

    def test_creates_new_project(self, tmp_path: Path):
        """create_project_from_repo creates project for new repo."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = None
                mock_ingester.get_local_sha.return_value = "abc123"
                mock_ingester.list_files.return_value = ["src/main.py"]
                mock_ingester.repos_dir = tmp_path / "repos"

                shesha = Shesha(model="test-model", storage_path=tmp_path)

                with patch.object(shesha._parser_registry, "find_parser") as mock_find:
                    mock_parser = MagicMock()
                    mock_parser.parse.return_value = MagicMock(
                        name="main.py",
                        content="content",
                        format="py",
                        metadata={},
                        char_count=7,
                        parse_warnings=[],
                    )
                    mock_find.return_value = mock_parser

                    result = shesha.create_project_from_repo(
                        url="/path/to/local/repo",
                        name="my-project",
                    )

                assert isinstance(result, RepoProjectResult)
                assert result.status == "created"
                assert result.project.project_id == "my-project"

    def test_unchanged_when_sha_matches(self, tmp_path: Path):
        """create_project_from_repo returns unchanged when SHAs match."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_remote_sha.return_value = "abc123"

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha._storage.create_project("my-project")

                result = shesha.create_project_from_repo(
                    url="https://github.com/org/repo",
                    name="my-project",
                )

                assert result.status == "unchanged"

    def test_updates_available_when_sha_differs(self, tmp_path: Path):
        """create_project_from_repo returns updates_available when SHAs differ."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_remote_sha.return_value = "def456"

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha._storage.create_project("my-project")

                result = shesha.create_project_from_repo(
                    url="https://github.com/org/repo",
                    name="my-project",
                )

                assert result.status == "updates_available"

    def test_apply_updates_skips_pull_for_local_repos(self, tmp_path: Path):
        """apply_updates() should not call pull() for local repositories."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                # Simulate a local repo with updates available
                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_sha_from_path.return_value = "def456"  # Different SHA
                mock_ingester.list_files_from_path.return_value = []
                mock_ingester.repos_dir = tmp_path / "repos"

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha._storage.create_project("local-project")

                result = shesha.create_project_from_repo(
                    url="/path/to/local/repo",
                    name="local-project",
                )

                assert result.status == "updates_available"

                # Apply updates
                mock_ingester.pull.reset_mock()
                result.apply_updates()

                # pull() should NOT be called for local repos
                mock_ingester.pull.assert_not_called()

    def test_saves_source_url_for_local_repo(self, tmp_path: Path):
        """create_project_from_repo saves source URL for local repos."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = None
                mock_ingester.get_sha_from_path.return_value = "abc123"
                mock_ingester.list_files_from_path.return_value = []
                mock_ingester.repos_dir = tmp_path / "repos"

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.create_project_from_repo(
                    url="/path/to/local/repo",
                    name="my-project",
                )

                mock_ingester.save_source_url.assert_called_once_with(
                    "my-project", "/path/to/local/repo"
                )

    def test_raises_for_non_git_local_path(self, tmp_path: Path):
        """create_project_from_repo raises RepoIngestError for non-git local dirs."""
        from shesha.exceptions import RepoIngestError

        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.is_git_repo.return_value = False

                shesha = Shesha(model="test-model", storage_path=tmp_path)

                with pytest.raises(RepoIngestError) as exc_info:
                    shesha.create_project_from_repo(
                        url="/path/to/non-git-dir",
                        name="my-project",
                    )

                assert "not a git repository" in str(exc_info.value).lower()


class TestCheckRepoForUpdates:
    """Tests for check_repo_for_updates method."""

    def test_returns_unchanged_when_no_updates(self, tmp_path: Path):
        """check_repo_for_updates returns unchanged when repo is current."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                # Cloned repo with matching SHAs
                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_remote_sha.return_value = "abc123"
                mock_ingester.resolve_token.return_value = None

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha._storage.create_project("my-project")

                result = shesha.check_repo_for_updates("my-project")

                assert result.status == "unchanged"
                assert result.project.project_id == "my-project"

    def test_returns_updates_available_when_sha_differs(self, tmp_path: Path):
        """check_repo_for_updates returns updates_available when SHAs differ."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                # Cloned repo with different SHAs
                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_remote_sha.return_value = "def456"
                mock_ingester.resolve_token.return_value = None

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha._storage.create_project("my-project")

                result = shesha.check_repo_for_updates("my-project")

                assert result.status == "updates_available"

    def test_raises_when_project_not_found(self, tmp_path: Path):
        """check_repo_for_updates raises ValueError for non-existent project."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            shesha = Shesha(model="test-model", storage_path=tmp_path)

            with pytest.raises(ValueError) as exc_info:
                shesha.check_repo_for_updates("nonexistent")

            assert "does not exist" in str(exc_info.value)

    def test_raises_when_no_repo_url(self, tmp_path: Path):
        """check_repo_for_updates raises ValueError when no repo URL stored."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                # No repo URL stored (not a cloned repo)
                mock_ingester.get_source_url.return_value = None

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha._storage.create_project("my-project")

                with pytest.raises(ValueError) as exc_info:
                    shesha.check_repo_for_updates("my-project")

                assert "No repository URL" in str(exc_info.value)

    def test_works_with_local_repo(self, tmp_path: Path):
        """check_repo_for_updates works with local repos using get_source_url."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                # Local repo - get_repo_url returns None (no cloned dir)
                # but get_source_url returns the local path
                mock_ingester.get_source_url.return_value = "/path/to/local/repo"
                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_sha_from_path.return_value = "abc123"
                mock_ingester.resolve_token.return_value = None

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha._storage.create_project("my-project")

                result = shesha.check_repo_for_updates("my-project")

                assert result.status == "unchanged"
                assert result.project.project_id == "my-project"
                # Verify it used get_source_url, not get_repo_url
                mock_ingester.get_source_url.assert_called_once_with("my-project")


class TestGetProjectInfo:
    """Tests for get_project_info method."""

    def test_returns_info_for_remote_repo(self, tmp_path: Path):
        """get_project_info returns correct info for remote repo project."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha._storage.create_project("my-project")

                info = shesha.get_project_info("my-project")

                assert info.project_id == "my-project"
                assert info.source_url == "https://github.com/org/repo"
                assert info.is_local is False
                assert info.source_exists is True

    def test_returns_info_for_existing_local_repo(self, tmp_path: Path):
        """get_project_info returns source_exists=True when local path exists."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                local_path = tmp_path / "local_repo"
                local_path.mkdir()

                mock_ingester.get_source_url.return_value = str(local_path)
                mock_ingester.is_local_path.return_value = True

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha._storage.create_project("local-project")

                info = shesha.get_project_info("local-project")

                assert info.is_local is True
                assert info.source_exists is True

    def test_returns_info_for_missing_local_repo(self, tmp_path: Path):
        """get_project_info returns source_exists=False when local path missing."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "/nonexistent/path"
                mock_ingester.is_local_path.return_value = True

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha._storage.create_project("missing-project")

                info = shesha.get_project_info("missing-project")

                assert info.is_local is True
                assert info.source_exists is False

    def test_raises_for_nonexistent_project(self, tmp_path: Path):
        """get_project_info raises ValueError for non-existent project."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            shesha = Shesha(model="test-model", storage_path=tmp_path)

            with pytest.raises(ValueError) as exc_info:
                shesha.get_project_info("nonexistent")

            assert "does not exist" in str(exc_info.value)


class TestExtractRepoName:
    """Tests for _extract_repo_name method."""

    def _make_shesha(self, tmp_path: Path, is_local: bool = False) -> Shesha:
        """Create a Shesha instance with mocked Docker and RepoIngester."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester
                mock_ingester.is_local_path.return_value = is_local
                shesha = Shesha(model="test-model", storage_path=tmp_path)
        return shesha

    def test_https_url(self, tmp_path: Path):
        """Standard HTTPS GitHub URL extracts org-repo name."""
        shesha = self._make_shesha(tmp_path)
        assert shesha._extract_repo_name("https://github.com/Ovid/shesha") == "Ovid-shesha"

    def test_https_url_trailing_slash(self, tmp_path: Path):
        """HTTPS URL with trailing slash extracts org-repo name."""
        shesha = self._make_shesha(tmp_path)
        assert shesha._extract_repo_name("https://github.com/Ovid/shesha/") == "Ovid-shesha"

    def test_https_url_dot_git(self, tmp_path: Path):
        """HTTPS URL with .git suffix extracts org-repo name."""
        shesha = self._make_shesha(tmp_path)
        assert shesha._extract_repo_name("https://github.com/Ovid/shesha.git") == "Ovid-shesha"

    def test_https_url_dot_git_trailing_slash(self, tmp_path: Path):
        """HTTPS URL with .git and trailing slash extracts org-repo name."""
        shesha = self._make_shesha(tmp_path)
        assert (
            shesha._extract_repo_name("https://github.com/Ovid/shesha.git/") == "Ovid-shesha"
        )

    def test_ssh_url(self, tmp_path: Path):
        """SSH git URL extracts org-repo name."""
        shesha = self._make_shesha(tmp_path)
        assert shesha._extract_repo_name("git@github.com:Ovid/shesha.git") == "Ovid-shesha"

    def test_gitlab_url(self, tmp_path: Path):
        """GitLab URL extracts org-repo name."""
        shesha = self._make_shesha(tmp_path)
        assert (
            shesha._extract_repo_name("https://gitlab.com/myorg/myrepo") == "myorg-myrepo"
        )

    def test_local_path_uses_parent_and_name(self, tmp_path: Path):
        """Local path extracts parent-name to avoid collisions."""
        shesha = self._make_shesha(tmp_path, is_local=True)
        assert shesha._extract_repo_name("/home/user/projects/shesha") == "projects-shesha"

    def test_local_home_relative_path(self, tmp_path: Path):
        """Home-relative local path extracts parent-name."""
        shesha = self._make_shesha(tmp_path, is_local=True)
        assert shesha._extract_repo_name("~/projects/myrepo") == "projects-myrepo"

    def test_local_path_trailing_slash(self, tmp_path: Path):
        """Local path with trailing slash extracts parent-name."""
        shesha = self._make_shesha(tmp_path, is_local=True)
        assert shesha._extract_repo_name("/home/user/projects/shesha/") == "projects-shesha"

    def test_fallback_for_unparseable_url(self, tmp_path: Path):
        """Unparseable URL falls back to unnamed-repo."""
        shesha = self._make_shesha(tmp_path)
        assert shesha._extract_repo_name("not-a-url") == "unnamed-repo"


class TestGetProjectInfoWithAnalysis:
    """Tests for get_project_info including analysis_status."""

    def test_get_project_info_includes_analysis_status(self, shesha_instance):
        """get_project_info includes analysis_status field."""
        shesha_instance.create_project("info-with-status")

        info = shesha_instance.get_project_info("info-with-status")

        assert info.analysis_status == "missing"  # No analysis yet

    def test_get_project_info_analysis_status_current(self, shesha_instance):
        """get_project_info shows 'current' when analysis matches SHA."""
        from shesha.models import RepoAnalysis

        shesha_instance.create_project("info-current")
        shesha_instance._repo_ingester.save_sha("info-current", "sha123")
        shesha_instance._repo_ingester.save_source_url("info-current", "/fake")

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="sha123",
            overview="Test",
            components=[],
            external_dependencies=[],
        )
        shesha_instance._storage.store_analysis("info-current", analysis)

        info = shesha_instance.get_project_info("info-current")

        assert info.analysis_status == "current"

    def test_get_project_info_analysis_status_stale(self, shesha_instance):
        """get_project_info shows 'stale' when analysis SHA differs from current."""
        from shesha.models import RepoAnalysis

        shesha_instance.create_project("info-stale")
        shesha_instance._repo_ingester.save_sha("info-stale", "new_sha")
        shesha_instance._repo_ingester.save_source_url("info-stale", "/fake")

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="old_sha",  # Different from saved SHA
            overview="Test",
            components=[],
            external_dependencies=[],
        )
        shesha_instance._storage.store_analysis("info-stale", analysis)

        info = shesha_instance.get_project_info("info-stale")

        assert info.analysis_status == "stale"


class TestAnalysisStatus:
    """Tests for analysis status checking."""

    def test_get_analysis_status_missing(self, shesha_instance: Shesha, tmp_path: Path):
        """get_analysis_status returns 'missing' when no analysis exists."""
        shesha_instance.create_project("no-analysis-project")
        status = shesha_instance.get_analysis_status("no-analysis-project")
        assert status == "missing"

    def test_get_analysis_status_current(self, shesha_instance: Shesha, tmp_path: Path):
        """get_analysis_status returns 'current' when analysis matches HEAD."""
        from shesha.models import RepoAnalysis

        shesha_instance.create_project("current-analysis")
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test",
            components=[],
            external_dependencies=[],
        )
        shesha_instance._storage.store_analysis("current-analysis", analysis)
        shesha_instance._repo_ingester.save_sha("current-analysis", "abc123")
        shesha_instance._repo_ingester.save_source_url("current-analysis", "/fake/path")

        status = shesha_instance.get_analysis_status("current-analysis")
        assert status == "current"

    def test_get_analysis_status_stale(self, shesha_instance: Shesha, tmp_path: Path):
        """get_analysis_status returns 'stale' when analysis SHA differs from HEAD."""
        from shesha.models import RepoAnalysis

        shesha_instance.create_project("stale-analysis")
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="old_sha_123",
            overview="Test",
            components=[],
            external_dependencies=[],
        )
        shesha_instance._storage.store_analysis("stale-analysis", analysis)
        shesha_instance._repo_ingester.save_sha("stale-analysis", "new_sha_456")
        shesha_instance._repo_ingester.save_source_url("stale-analysis", "/fake/path")

        status = shesha_instance.get_analysis_status("stale-analysis")
        assert status == "stale"

    def test_get_analysis_status_nonexistent_project_raises(self, shesha_instance: Shesha):
        """get_analysis_status raises for nonexistent project."""
        with pytest.raises(ValueError, match="does not exist"):
            shesha_instance.get_analysis_status("no-such-project")


class TestGetAnalysis:
    """Tests for get_analysis method."""

    def test_get_analysis_returns_stored_analysis(self, shesha_instance: Shesha):
        """get_analysis returns the stored analysis."""
        from shesha.models import AnalysisComponent, RepoAnalysis

        shesha_instance.create_project("get-analysis-project")
        comp = AnalysisComponent(
            name="API",
            path="api/",
            description="REST API",
            apis=[],
            models=["User"],
            entry_points=["main.py"],
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
        shesha_instance._storage.store_analysis("get-analysis-project", analysis)

        result = shesha_instance.get_analysis("get-analysis-project")
        assert result is not None
        assert result.overview == "Test app"
        assert len(result.components) == 1

    def test_get_analysis_returns_none_when_missing(self, shesha_instance: Shesha):
        """get_analysis returns None when no analysis exists."""
        shesha_instance.create_project("no-analysis")
        result = shesha_instance.get_analysis("no-analysis")
        assert result is None

    def test_get_analysis_nonexistent_project_raises(self, shesha_instance: Shesha):
        """get_analysis raises for nonexistent project."""
        with pytest.raises(ValueError, match="does not exist"):
            shesha_instance.get_analysis("no-such-project")


class TestGenerateAnalysis:
    """Tests for generate_analysis method."""

    def test_generate_analysis_stores_result(self, shesha_instance):
        """generate_analysis stores the generated analysis."""
        from shesha.models import RepoAnalysis

        # Create a project
        shesha_instance.create_project("gen-analysis")
        shesha_instance._repo_ingester.save_sha("gen-analysis", "sha123")

        # Mock the generator
        mock_analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="sha123",
            overview="Generated analysis",
            components=[],
            external_dependencies=[],
        )

        with patch("shesha.shesha.AnalysisGenerator") as mock_generator:
            mock_generator.return_value.generate.return_value = mock_analysis

            result = shesha_instance.generate_analysis("gen-analysis")

            assert result.overview == "Generated analysis"
            # Verify it was stored
            stored = shesha_instance._storage.load_analysis("gen-analysis")
            assert stored is not None
            assert stored.overview == "Generated analysis"

    def test_generate_analysis_returns_analysis(self, shesha_instance):
        """generate_analysis returns the generated RepoAnalysis."""
        from shesha.models import RepoAnalysis

        shesha_instance.create_project("return-analysis")

        mock_analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc",
            overview="Test",
            components=[],
            external_dependencies=[],
        )

        with patch("shesha.shesha.AnalysisGenerator") as mock_generator:
            mock_generator.return_value.generate.return_value = mock_analysis

            result = shesha_instance.generate_analysis("return-analysis")

            assert isinstance(result, RepoAnalysis)
            assert result.overview == "Test"

    def test_generate_analysis_nonexistent_project_raises(self, shesha_instance):
        """generate_analysis raises for nonexistent project."""
        with pytest.raises(ValueError, match="does not exist"):
            shesha_instance.generate_analysis("no-such-project")
