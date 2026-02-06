"""Tests for Librarian CLI Docker installation logic."""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shesha.librarian.cli import run_install
from shesha.librarian.paths import LibrarianPaths


class TestLibrarianInstallDockerLogic:
    """Tests for Librarian install command's handling of Docker."""

    @pytest.fixture
    def paths(self, tmp_path: Path):
        home = tmp_path / "home"
        storage = tmp_path / "storage"
        logs = tmp_path / "logs"
        return LibrarianPaths(home=home, storage=storage, logs=logs)

    def test_run_install_succeeds_with_docker(self, paths: LibrarianPaths, tmp_path: Path):
        """Install succeeds when Docker is running."""
        with (
            patch("shesha.librarian.cli._self_test_mcp_server", return_value=(True, "mcp: ok")),
            patch("shesha.shesha.Shesha._is_docker_available", return_value=True),
            patch("shesha.librarian.cli._self_test_sandbox", return_value=(True, "sandbox: ok")),
            patch("shesha.librarian.cli._write_install_artifacts") as mock_write,
        ):
            result = run_install(
                paths=paths,
                manifest_dir=tmp_path,
                skip_docker=False,
                skip_sandbox=False,
            )

            assert result.ok is True
            mock_write.assert_called()
            # Verify docker_available=True was passed
            kwargs = mock_write.call_args.kwargs
            assert kwargs["docker_available"] is True
            assert kwargs["self_test"].docker_available is True

    def test_run_install_prompts_and_skips_docker(self, paths: LibrarianPaths, tmp_path: Path):
        """Install allows skipping Docker via interactive prompt."""
        with (
            patch("shesha.librarian.cli._self_test_mcp_server", return_value=(True, "mcp: ok")),
            patch("shesha.shesha.Shesha._is_docker_available", return_value=False),
            patch("shesha.librarian.cli._prompt_docker_options", return_value="skip"),
            patch("shesha.librarian.cli._write_install_artifacts") as mock_write,
        ):
            result = run_install(
                paths=paths,
                manifest_dir=tmp_path,
                skip_docker=False,
                skip_sandbox=False,
            )

            assert result.ok is True
            kwargs = mock_write.call_args.kwargs
            assert kwargs["docker_available"] is False
            assert kwargs["self_test"].docker_available is False

    def test_run_install_prompts_and_aborts(self, paths: LibrarianPaths, tmp_path: Path):
        """Install aborts if user chooses to abort when Docker is missing."""
        with (
            patch("shesha.librarian.cli._self_test_mcp_server", return_value=(True, "mcp: ok")),
            patch("shesha.shesha.Shesha._is_docker_available", return_value=False),
            patch("shesha.librarian.cli._prompt_docker_options", return_value="abort"),
            patch("shesha.librarian.cli._write_install_artifacts") as mock_write,
        ):
            result = run_install(
                paths=paths,
                manifest_dir=tmp_path,
                skip_docker=False,
                skip_sandbox=False,
            )

            assert result.ok is False
            assert "aborted" in result.details
            mock_write.assert_not_called()

    def test_run_install_fails_non_interactive_no_docker(self, paths: LibrarianPaths, tmp_path: Path):
        """Install fails gracefully if non-interactive and Docker is missing."""
        with (
            patch("shesha.librarian.cli._self_test_mcp_server", return_value=(True, "mcp: ok")),
            patch("shesha.shesha.Shesha._is_docker_available", return_value=False),
            patch("sys.stdin.isatty", return_value=False),
            patch("shesha.librarian.cli._write_install_artifacts") as mock_write,
        ):
            result = run_install(
                paths=paths,
                manifest_dir=tmp_path,
                skip_docker=False,
                skip_sandbox=False,
            )

            assert result.ok is False
            assert "Docker is not running" in result.details
            mock_write.assert_called_once()
            assert mock_write.call_args.kwargs["docker_available"] is False
