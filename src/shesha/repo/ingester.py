"""Git repository ingester."""

import re
from pathlib import Path
from urllib.parse import urlparse


class RepoIngester:
    """Handles git repository cloning, updating, and file extraction."""

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
