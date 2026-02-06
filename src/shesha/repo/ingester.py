"""Git repository ingester."""

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from shesha.exceptions import AuthenticationError, RepoIngestError
from shesha.security.paths import safe_path


class RepoIngester:
    """Handles git repository cloning, updating, and file extraction."""

    # Host to environment variable mapping
    HOST_TO_ENV_VAR = {
        "github.com": "GITHUB_TOKEN",
        "gitlab.com": "GITLAB_TOKEN",
        "bitbucket.org": "BITBUCKET_TOKEN",
    }

    def __init__(self, storage_path: Path | str) -> None:
        """Initialize with storage path for cloned repos."""
        self.storage_path = Path(storage_path)
        self.repos_dir = self.storage_path / "repos"
        self.repos_dir.mkdir(parents=True, exist_ok=True)

    def _repo_path(self, project_id: str) -> Path:
        """Get safe path for a project's repo directory."""
        return safe_path(self.repos_dir, project_id)

    def is_local_path(self, url: str) -> bool:
        """Check if url is a local filesystem path."""
        return (
            url.startswith("/")
            or url.startswith("~")
            or url.startswith("./")
            or url.startswith("../")
        )

    def is_git_repo(self, path: Path) -> bool:
        """Check if path is a git repository.

        Args:
            path: Filesystem path to check.

        Returns:
            True if path exists and contains a .git directory.
        """
        return path.exists() and (path / ".git").exists()

    def detect_host(self, url: str) -> str | None:
        """Detect the git host from a URL."""
        if self.is_local_path(url):
            return None

        # Handle SSH URLs (git@github.com:org/repo.git)
        ssh_match = re.match(r"git@([^:]+):", url)
        if ssh_match:
            return ssh_match.group(1)

        # Handle HTTPS URLs
        parsed = urlparse(url)
        if parsed.netloc:
            return parsed.netloc

        return None

    def resolve_token(self, url: str, explicit_token: str | None) -> str | None:
        """Resolve authentication token for a URL.

        Priority: explicit token > env var > None (system git auth)
        """
        if explicit_token:
            return explicit_token

        host = self.detect_host(url)
        if host and host in self.HOST_TO_ENV_VAR:
            env_var = self.HOST_TO_ENV_VAR[host]
            return os.environ.get(env_var)

        return None

    def clone(
        self,
        url: str,
        project_id: str,
        token: str | None = None,
    ) -> Path:
        """Clone a git repository."""
        repo_path = self._repo_path(project_id)
        repo_path.mkdir(parents=True, exist_ok=True)

        cmd = ["git", "clone", "--depth=1", url, str(repo_path)]
        env = None

        if token:
            env, askpass_path = self._create_askpass(token)
        else:
            askpass_path = None

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        finally:
            if askpass_path is not None:
                askpass_path.unlink(missing_ok=True)

        if result.returncode != 0:
            if repo_path.exists():
                shutil.rmtree(repo_path)
            if "Authentication failed" in result.stderr:
                raise AuthenticationError(url)
            raise RepoIngestError(url, RuntimeError(result.stderr))

        return repo_path

    @staticmethod
    def _create_askpass(token: str) -> tuple[dict[str, str], Path]:
        """Create a GIT_ASKPASS script that supplies the token via stdout.

        Returns env dict and path to the temp script (caller must clean up).
        """
        fd, path = tempfile.mkstemp(suffix="_git_askpass.sh")
        try:
            with os.fdopen(fd, "w") as f:
                f.write('#!/bin/sh\necho "$GIT_TOKEN"\n')
            os.chmod(path, stat.S_IRWXU)
        except Exception:
            Path(path).unlink(missing_ok=True)
            raise

        env = os.environ.copy()
        env["GIT_ASKPASS"] = path
        env["GIT_TOKEN"] = token
        env["GIT_TERMINAL_PROMPT"] = "0"
        return env, Path(path)

    def save_sha(self, project_id: str, sha: str) -> None:
        """Save the HEAD SHA for a project."""
        repo_path = self._repo_path(project_id)
        repo_path.mkdir(parents=True, exist_ok=True)
        meta_path = repo_path / "_repo_meta.json"
        meta_path.write_text(json.dumps({"head_sha": sha}))

    def save_source_url(self, project_id: str, url: str) -> None:
        """Save the source URL for a project."""
        repo_path = self._repo_path(project_id)
        repo_path.mkdir(parents=True, exist_ok=True)
        meta_path = repo_path / "_repo_meta.json"

        # Load existing metadata or start fresh
        if meta_path.exists():
            data = json.loads(meta_path.read_text())
        else:
            data = {}

        data["source_url"] = url
        meta_path.write_text(json.dumps(data))

    def get_source_url(self, project_id: str) -> str | None:
        """Get the saved source URL for a project."""
        meta_path = self._repo_path(project_id) / "_repo_meta.json"
        if not meta_path.exists():
            return None
        data = json.loads(meta_path.read_text())
        url = data.get("source_url")
        return str(url) if url is not None else None

    def get_saved_sha(self, project_id: str) -> str | None:
        """Get the saved HEAD SHA for a project."""
        meta_path = self._repo_path(project_id) / "_repo_meta.json"
        if not meta_path.exists():
            return None
        data = json.loads(meta_path.read_text())
        sha = data.get("head_sha")
        return str(sha) if sha is not None else None

    def get_remote_sha(self, url: str, token: str | None = None) -> str | None:
        """Get the HEAD SHA from remote repository."""
        cmd = ["git", "ls-remote", url, "HEAD"]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            return None

        parts = result.stdout.strip().split()
        return parts[0] if parts else None

    def get_repo_url(self, project_id: str) -> str | None:
        """Get the remote origin URL for a cloned repo.

        Args:
            project_id: ID of the cloned repo.

        Returns:
            The remote origin URL, or None if not found.
        """
        repo_path = self._repo_path(project_id)
        if not repo_path.exists():
            return None

        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return None

        return result.stdout.strip()

    def get_local_sha(self, project_id: str) -> str | None:
        """Get the HEAD SHA from a local cloned repo."""
        repo_path = self._repo_path(project_id)
        return self.get_sha_from_path(repo_path)

    def get_sha_from_path(self, repo_path: Path) -> str | None:
        """Get the HEAD SHA from a repository at the given path."""
        if not repo_path.exists():
            return None

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return None

        return result.stdout.strip()

    def list_files(self, project_id: str, subdir: str | None = None) -> list[str]:
        """List tracked files in a cloned repository.

        Args:
            project_id: ID of the cloned repo.
            subdir: Optional subdirectory to filter to.

        Returns:
            List of relative file paths.
        """
        repo_path = self._repo_path(project_id)
        return self.list_files_from_path(repo_path, subdir)

    def list_files_from_path(self, repo_path: Path, subdir: str | None = None) -> list[str]:
        """List tracked files in a repository at the given path.

        Args:
            repo_path: Path to the git repository.
            subdir: Optional subdirectory to filter to.

        Returns:
            List of relative file paths.
        """
        cmd = ["git", "ls-files"]
        if subdir:
            cmd.append(subdir)

        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return []

        files = result.stdout.strip().split("\n")
        return [f for f in files if f]

    def fetch(self, project_id: str) -> None:
        """Fetch updates from remote."""
        repo_path = self._repo_path(project_id)

        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=repo_path,
            capture_output=True,
        )

    def pull(self, project_id: str) -> None:
        """Pull updates from remote.

        Raises:
            RepoIngestError: If pull fails.
        """
        repo_path = self._repo_path(project_id)
        url = f"repo at {repo_path}"

        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RepoIngestError(url, RuntimeError(result.stderr))

    def delete_repo(self, project_id: str) -> None:
        """Delete the cloned repository directory for a project."""
        repo_path = self._repo_path(project_id)
        if repo_path.exists():
            shutil.rmtree(repo_path)
