"""Tests for RepoIngester."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shesha.exceptions import AuthenticationError, RepoIngestError
from shesha.repo.ingester import RepoIngester


@pytest.fixture
def ingester(tmp_path: Path) -> RepoIngester:
    return RepoIngester(storage_path=tmp_path)


class TestRepoIngester:
    """Tests for RepoIngester class."""

    def test_init_creates_repos_dir(self, ingester: RepoIngester, tmp_path: Path):
        """RepoIngester creates repos directory on init."""
        assert (tmp_path / "repos").is_dir()

    def test_is_local_path_absolute(self, ingester: RepoIngester):
        """is_local_path returns True for absolute paths."""
        assert ingester.is_local_path("/home/user/repo")

    def test_is_local_path_home(self, ingester: RepoIngester):
        """is_local_path returns True for home-relative paths."""
        assert ingester.is_local_path("~/projects/repo")

    def test_is_local_path_url(self, ingester: RepoIngester):
        """is_local_path returns False for URLs."""
        assert not ingester.is_local_path("https://github.com/org/repo")
        assert not ingester.is_local_path("git@github.com:org/repo.git")

    def test_detect_host_github(self, ingester: RepoIngester):
        """detect_host identifies GitHub URLs."""
        assert ingester.detect_host("https://github.com/org/repo") == "github.com"
        assert ingester.detect_host("git@github.com:org/repo.git") == "github.com"

    def test_detect_host_gitlab(self, ingester: RepoIngester):
        """detect_host identifies GitLab URLs."""
        assert ingester.detect_host("https://gitlab.com/org/repo") == "gitlab.com"

    def test_detect_host_bitbucket(self, ingester: RepoIngester):
        """detect_host identifies Bitbucket URLs."""
        assert ingester.detect_host("https://bitbucket.org/org/repo") == "bitbucket.org"

    def test_detect_host_local(self, ingester: RepoIngester):
        """detect_host returns None for local paths."""
        assert ingester.detect_host("/home/user/repo") is None


class TestTokenResolution:
    """Tests for token resolution logic."""

    def test_explicit_token_takes_precedence(self, ingester: RepoIngester):
        """Explicit token parameter wins over env vars."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "env_token"}):
            token = ingester.resolve_token(
                url="https://github.com/org/repo",
                explicit_token="explicit_token",
            )
            assert token == "explicit_token"

    def test_github_env_token(self, ingester: RepoIngester):
        """GITHUB_TOKEN env var used for github.com."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "gh_token"}, clear=True):
            token = ingester.resolve_token(
                url="https://github.com/org/repo",
                explicit_token=None,
            )
            assert token == "gh_token"

    def test_gitlab_env_token(self, ingester: RepoIngester):
        """GITLAB_TOKEN env var used for gitlab.com."""
        with patch.dict(os.environ, {"GITLAB_TOKEN": "gl_token"}, clear=True):
            token = ingester.resolve_token(
                url="https://gitlab.com/org/repo",
                explicit_token=None,
            )
            assert token == "gl_token"

    def test_no_token_returns_none(self, ingester: RepoIngester):
        """Returns None when no token available."""
        with patch.dict(os.environ, {}, clear=True):
            token = ingester.resolve_token(
                url="https://github.com/org/repo",
                explicit_token=None,
            )
            assert token is None


class TestGitClone:
    """Tests for git clone functionality."""

    def test_clone_creates_project_dir(self, ingester: RepoIngester, tmp_path: Path):
        """clone() creates directory for the project."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            ingester.clone(
                url="https://github.com/org/repo",
                project_id="my-project",
            )

            assert (tmp_path / "repos" / "my-project").is_dir()

    def test_clone_uses_depth_1(self, ingester: RepoIngester):
        """clone() uses shallow clone (depth=1)."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            ingester.clone(
                url="https://github.com/org/repo",
                project_id="my-project",
            )

            call_args = mock_run.call_args[0][0]
            assert "--depth=1" in call_args

    def test_clone_injects_token_into_url(self, ingester: RepoIngester):
        """clone() injects token into HTTPS URL."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            ingester.clone(
                url="https://github.com/org/repo",
                project_id="my-project",
                token="my_token",
            )

            call_args = mock_run.call_args[0][0]
            url_in_cmd = [a for a in call_args if "github.com" in a][0]
            assert "my_token@github.com" in url_in_cmd

    def test_clone_auth_failure_raises(self, ingester: RepoIngester):
        """clone() raises AuthenticationError on auth failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stderr="fatal: Authentication failed",
            )

            with pytest.raises(AuthenticationError):
                ingester.clone(
                    url="https://github.com/org/private-repo",
                    project_id="my-project",
                )

    def test_clone_other_failure_raises(self, ingester: RepoIngester):
        """clone() raises RepoIngestError on other failures."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stderr="fatal: repository not found",
            )

            with pytest.raises(RepoIngestError):
                ingester.clone(
                    url="https://github.com/org/nonexistent",
                    project_id="my-project",
                )
