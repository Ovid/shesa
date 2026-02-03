"""Git repository ingester."""

import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from shesha.exceptions import AuthenticationError, RepoIngestError


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

    def is_local_path(self, url: str) -> bool:
        """Check if url is a local filesystem path."""
        return url.startswith("/") or url.startswith("~") or Path(url).exists()

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
        repo_path = self.repos_dir / project_id
        repo_path.mkdir(parents=True, exist_ok=True)

        clone_url = self._inject_token(url, token) if token else url

        result = subprocess.run(
            ["git", "clone", "--depth=1", clone_url, str(repo_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            if repo_path.exists():
                shutil.rmtree(repo_path)
            if "Authentication failed" in result.stderr:
                raise AuthenticationError(url)
            raise RepoIngestError(url, RuntimeError(result.stderr))

        return repo_path

    def _inject_token(self, url: str, token: str) -> str:
        """Inject auth token into HTTPS URL."""
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https"):
            netloc = f"{token}@{parsed.netloc}"
            return urlunparse(parsed._replace(netloc=netloc))
        return url
