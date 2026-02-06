"""Librarian CLI: installer, headless commands, and MCP front door."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import sysconfig
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import docker
from docker.errors import DockerException, ImageNotFound

from shesha import __version__
from shesha.exceptions import SheshaError
from shesha.librarian.core import LibrarianCore, ValidationError
from shesha.librarian.manifest import LibrarianManifest, SelfTestStatus
from shesha.librarian.mcp_jsonrpc import encode_message, parse_messages
from shesha.librarian.paths import LibrarianPaths, resolve_paths
from shesha.sandbox.executor import ContainerExecutor


SUPPORTED_MODES = ["cli", "mcp"]
SUPPORTED_ENV_VARS = [
    "LIBRARIAN_HOME",
    "LIBRARIAN_STORAGE_PATH",
    "LIBRARIAN_LOG_DIR",
    "SHESHA_MODEL",
    "SHESHA_API_KEY",
]


@dataclass(frozen=True)
class InstallResult:
    ok: bool
    details: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_manifest_dir() -> Path:
    return Path.cwd()


def _manifest_path(manifest_dir: Path) -> Path:
    return manifest_dir / ".librarian" / "manifest.json"


def _readme_path(manifest_dir: Path) -> Path:
    return manifest_dir / "mcp-server-readme.md"


def _scripts_dir() -> Path:
    scripts = sysconfig.get_path("scripts")
    if scripts:
        return Path(scripts).resolve()
    return Path(sys.executable).resolve().parent


def _find_console_script(name: str) -> Path | None:
    scripts_dir = _scripts_dir()
    candidates = [
        name,
        f"{name}.exe",
        f"{name}.cmd",
        f"{name}.bat",
        f"{name}-script.py",
    ]
    for candidate in candidates:
        path = scripts_dir / candidate
        if path.exists():
            return path
    return None


def _resolve_manifest_invocation() -> tuple[dict[str, str], dict[str, list[str]]]:
    python = str(Path(sys.executable).resolve())
    cli_script = _find_console_script("librarian")
    if cli_script is not None:
        cli_cmd = [str(cli_script)]
        mcp_cmd = [str(cli_script), "mcp"]
    else:
        cli_cmd = [python, "-m", "shesha.librarian"]
        mcp_cmd = [python, "-m", "shesha.librarian", "mcp"]

    entrypoints = {"cli": cli_cmd[0], "mcp": mcp_cmd[0]}
    commands = {"cli": cli_cmd, "mcp": mcp_cmd}
    return entrypoints, commands


def _sandbox_source_dir() -> Path | None:
    # Prefer installed package path when available.
    shesha_dir = Path(__file__).resolve().parents[1]
    candidate = shesha_dir / "sandbox"
    if (candidate / "Dockerfile").exists():
        return candidate

    # Fallback: repo layout (when running from a source checkout).
    candidate = Path.cwd() / "src" / "shesha" / "sandbox"
    if (candidate / "Dockerfile").exists():
        return candidate

    return None


def _ensure_sandbox_image(image: str) -> tuple[bool, str]:
    """Ensure the sandbox Docker image exists, building it if missing."""
    try:
        client = docker.from_env()
    except DockerException as e:
        return False, f"Docker unavailable: {e}"

    try:
        try:
            client.images.get(image)
            return True, "sandbox_image: present"
        except ImageNotFound:
            sandbox_dir = _sandbox_source_dir()
            if sandbox_dir is None:
                return False, "Sandbox Dockerfile not found; cannot build image automatically."

            try:
                client.images.build(
                    path=str(sandbox_dir),
                    dockerfile="Dockerfile",
                    tag=image,
                    rm=True,
                )
            except Exception as e:  # noqa: BLE001 - surfaced to operator
                return False, f"Failed to build sandbox image '{image}': {e}"
            return True, "sandbox_image: built"
    finally:
        try:
            client.close()
        except Exception:
            pass  # Client may already be closed


def _write_readme(*, path: Path, storage_path: Path, logs_path: Path, manifest_path: Path) -> None:
    content = f"""# Librarian MCP Server (Shesha RLM)

This installation provides:

- **CLI mode (headless):** run queries and manage projects from a terminal
- **MCP mode (stdio):** run as a Model Context Protocol server over stdin/stdout

## Persistent state + logs

- Storage: `{storage_path}`
- Logs: `{logs_path}`

To override defaults:

- `LIBRARIAN_STORAGE_PATH` (storage root for projects)
- `LIBRARIAN_LOG_DIR` (log directory)
- `LIBRARIAN_HOME` (base directory used when the above are not set)

Back up `{storage_path}` to preserve projects/documents.

## Canonical commands

Run MCP server (stdio):

```bash
python -m shesha.librarian mcp
```

Run headless query:

```bash
python -m shesha.librarian query --project <project_id> \"<question>\"
```

Local manifest:

- `{manifest_path}`
"""
    path.write_text(content)


def _write_install_artifacts(
    *,
    manifest_path: Path,
    readme_path: Path,
    storage_path: Path,
    logs_path: Path,
    self_test: SelfTestStatus,
    docker_available: bool = True,
) -> None:
    entrypoints, commands = _resolve_manifest_invocation()
    LibrarianManifest(
        package_name="shesha",
        package_version=__version__,
        entrypoints=entrypoints,
        commands=commands,
        storage_path=str(storage_path),
        logs_path=str(logs_path),
        supported_modes=SUPPORTED_MODES,
        env_vars=SUPPORTED_ENV_VARS,
        self_test=self_test,
        docker_available=docker_available,
    ).write(manifest_path)
    _write_readme(
        path=readme_path,
        storage_path=storage_path,
        logs_path=logs_path,
        manifest_path=manifest_path,
    )


def _prompt_docker_options() -> str:
    """Prompt user for Docker installation options if in a TTY."""
    if not sys.stdin.isatty():
        return "fail"

    print("\n" + "=" * 60)
    print("DOCKER NOT DETECTED".center(60))
    print("=" * 60)
    print("Shesha requires Docker to run code in a secure sandbox.")
    print("Without Docker, you can still manage projects and index files,")
    print("but you will NOT be able to run queries.\n")

    if sys.platform == "darwin":
        print("Suggested for macOS: Install via Homebrew")
        print("  brew install --cask docker\n")

    print("How would you like to proceed?")
    print("  1) [Guide] Show me how to install Docker")
    print("  2) [Skip] Proceed without Docker (queries will be disabled)")
    print("  3) [Abort] Stop installation")

    while True:
        try:
            choice = input("\nChoice [1-3]: ").strip()
            if choice == "1":
                return "guide"
            if choice == "2":
                return "skip"
            if choice in ("3", "q", "quit"):
                return "abort"
        except (KeyboardInterrupt, EOFError):
            return "abort"


def _show_docker_install_guide() -> None:
    """Display platform-specific Docker installation instructions."""
    print("\n" + "-" * 60)
    print("DOCKER INSTALLATION GUIDE".center(60))
    print("-" * 60)

    if sys.platform == "darwin":
        print("Option A: Docker Desktop (Recommended)")
        print("  Download from: https://www.docker.com/products/docker-desktop\n")
        print("Option B: Homebrew")
        print("  brew install --cask docker\n")
        print("Option C: Colima (Lightweight)")
        print("  brew install colima")
        print("  colima start\n")
    elif sys.platform == "linux":
        print("Follow the official guide for your distribution:")
        print("  https://docs.docker.com/engine/install/\n")
        print("Quick install script:")
        print("  curl -fsSL https://get.docker.com -o get-docker.sh")
        print("  sudo sh get-docker.sh\n")
    else:
        print("Download Docker Desktop for Windows:")
        print("  https://www.docker.com/products/docker-desktop\n")

    print("-" * 60)
    input("Press Enter once Docker is installed and running, or to continue...")


def _self_test_mcp_server(*, storage_path: Path) -> tuple[bool, str]:
    """Start MCP server and call `health` tool over stdio."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "shesha.librarian.mcp", "--storage-path", str(storage_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        input_data = b"".join(
            [
                encode_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {
                                "name": "librarian-installer",
                                "version": __version__,
                            },
                        },
                    }
                ),
                encode_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "health", "arguments": {}},
                    }
                ),
            ]
        )

        stdout, stderr = proc.communicate(input=input_data, timeout=10)
        messages = parse_messages(stdout)

        init_resp = next((m for m in messages if m.get("id") == 1), None)
        if not init_resp or "result" not in init_resp:
            return False, "Missing initialize response"

        health_resp = next((m for m in messages if m.get("id") == 2), None)
        if not health_resp or "result" not in health_resp:
            return False, "Missing health response"

        content = health_resp.get("result", {}).get("content", [])
        if not content:
            return False, "MCP health tool returned no content"

        text = str(content[0].get("text", ""))
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            return False, f"MCP health tool did not report ok: {text[:200]}"

        return True, "mcp: ok"
    except Exception as e:  # noqa: BLE001 - returned as self-test failure
        try:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=2)
        except Exception:
            stdout, stderr = b"", b""
        details = str(e)
        err_text = stderr.decode("utf-8", errors="replace").strip()
        if err_text:
            details = f"{details}\n{err_text}"
        out_text = stdout.decode("utf-8", errors="replace").strip()
        if out_text:
            details = f"{details}\n{out_text}"
        return False, details
    finally:
        if proc.poll() is None:
            proc.kill()


def _self_test_sandbox(*, image: str = "shesha-sandbox") -> tuple[bool, str]:
    """Validate the sandbox image can start and respond to a ping."""
    try:
        ok, details = _ensure_sandbox_image(image)
        if not ok:
            hint = ""
            sandbox_dir = _sandbox_source_dir()
            if sandbox_dir is not None:
                dockerfile = sandbox_dir / "Dockerfile"
                hint = (
                    "\n\nBuild the sandbox image manually:\n"
                    f"  docker build -t {image} -f {dockerfile} {sandbox_dir}"
                )
            return False, f"{details}{hint}"

        executor = ContainerExecutor(image=image)
        executor.start()
        # Private protocol: runner.py supports {"action": "ping"}.
        result: dict[str, Any] = executor._send_command({"action": "ping"})
        executor.stop()
        if result.get("status") != "ok":
            return False, f"Sandbox ping returned: {result}"
        return True, "Sandbox container responded to ping"
    except Exception as e:  # noqa: BLE001 - returned as failure
        return False, f"Sandbox self-test failed: {e}"


def run_install(
    *,
    paths: LibrarianPaths,
    manifest_dir: Path,
    skip_docker: bool,
    skip_sandbox: bool,
) -> InstallResult:
    paths.ensure_dirs()

    manifest_path = _manifest_path(manifest_dir)
    readme_path = _readme_path(manifest_dir)

    # 1) MCP loopback self-test (server starts and responds).
    print("Self-test: MCP stdio (initialize + health)…")
    mcp_ok, mcp_details = _self_test_mcp_server(storage_path=paths.storage)
    if not mcp_ok:
        status = SelfTestStatus(
            ok=False, timestamp=_utc_now_iso(), details=f"MCP self-test failed: {mcp_details}"
        )
        _write_install_artifacts(
            manifest_path=manifest_path,
            readme_path=readme_path,
            storage_path=paths.storage,
            logs_path=paths.logs,
            self_test=status,
        )
        return InstallResult(ok=False, details=status.details)
    print(f"  {mcp_details}")

    # 2) Docker/sandbox validation (required for queries).
    docker_available = False
    if not skip_docker:
        print("Self-test: Docker daemon…")
        from shesha.shesha import Shesha as SheshaClass

        if SheshaClass._is_docker_available():
            docker_available = True
            print("  docker: ok")
        else:
            choice = _prompt_docker_options()
            if choice == "guide":
                _show_docker_install_guide()
                # Re-check after guide
                if SheshaClass._is_docker_available():
                    docker_available = True
                    print("  docker: ok (after install)")
                else:
                    print("  docker: still not detected. Proceeding with Docker disabled.")
            elif choice == "abort":
                return InstallResult(ok=False, details="Installation aborted by user (Docker missing)")
            elif choice == "skip":
                print("  docker: skipped by user")
            else:
                # Non-interactive or fallback
                msg = "Docker is not running. Please start Docker and try again."
                status = SelfTestStatus(
                    ok=False,
                    timestamp=_utc_now_iso(),
                    details=f"Docker check failed: {msg}",
                    docker_available=False,
                )
                _write_install_artifacts(
                    manifest_path=manifest_path,
                    readme_path=readme_path,
                    storage_path=paths.storage,
                    logs_path=paths.logs,
                    self_test=status,
                    docker_available=False,
                )
                return InstallResult(ok=False, details=status.details)
    else:
        print("Self-test: Docker daemon… skipped")

    if docker_available and not skip_sandbox:
        print("Self-test: sandbox image + ping…")
        sandbox_ok, sandbox_details = _self_test_sandbox()
        if not sandbox_ok:
            status = SelfTestStatus(
                ok=False,
                timestamp=_utc_now_iso(),
                details=sandbox_details,
                docker_available=True,
            )
            _write_install_artifacts(
                manifest_path=manifest_path,
                readme_path=readme_path,
                storage_path=paths.storage,
                logs_path=paths.logs,
                self_test=status,
                docker_available=True,
            )
            return InstallResult(ok=False, details=status.details)
        print("  sandbox: ok")
    elif not skip_sandbox:
        print("Self-test: sandbox image + ping… skipped (no Docker)")
    else:
        print("Self-test: sandbox image + ping… skipped")

    # 3) Write manifest + readme.
    docker_status = "docker: skip" if not docker_available else "docker: ok"
    sandbox_status = "sandbox: skipped" if not docker_available or skip_sandbox else "sandbox: ok"
    details = "; ".join([mcp_details, docker_status, sandbox_status])
    status = SelfTestStatus(
        ok=True,
        timestamp=_utc_now_iso(),
        details=details,
        docker_available=docker_available,
    )
    _write_install_artifacts(
        manifest_path=manifest_path,
        readme_path=readme_path,
        storage_path=paths.storage,
        logs_path=paths.logs,
        self_test=status,
        docker_available=docker_available,
    )

    return InstallResult(ok=True, details=status.details)


def _print_install_summary(*, paths: LibrarianPaths, manifest_dir: Path) -> None:
    manifest_path = _manifest_path(manifest_dir)
    readme_path = _readme_path(manifest_dir)
    print("Librarian install complete.\n")
    print("State + logs:")
    print(f"  storage: {paths.storage}")
    print(f"  logs:    {paths.logs}\n")
    try:
        manifest = LibrarianManifest.read(manifest_path)
        if manifest.self_test is not None:
            print("Self-test:")
            print(f"  ok:      {manifest.self_test.ok}")
            print(f"  details: {manifest.self_test.details}\n")
    except Exception:
        pass
    print("To override defaults:")
    print("  LIBRARIAN_STORAGE_PATH, LIBRARIAN_LOG_DIR, or LIBRARIAN_HOME\n")
    print("Back up:")
    print(f"  {paths.storage}\n")
    print("Next steps:")
    print("  MCP (stdio):")
    print("    python -m shesha.librarian mcp")
    print("  Headless query:")
    print('    python -m shesha.librarian query --project <project_id> "<question>"\n')
    print("Local outputs:")
    print(f"  manifest: {manifest_path}")
    print(f"  readme:   {readme_path}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="librarian",
        description="Librarian (Shesha RLM) tool + MCP server",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    install = sub.add_parser(
        "install",
        help="Initialize state, run self-test, and write local manifest/readme",
    )
    install.add_argument(
        "--storage-path",
        type=Path,
        default=None,
        help="Override storage directory",
    )
    install.add_argument(
        "--log-dir",
        type=Path,
        default=None,
        help="Override logs directory",
    )
    install.add_argument(
        "--manifest-dir",
        type=Path,
        default=None,
        help="Directory to write .librarian/manifest.json and mcp-server-readme.md (default: cwd)",
    )
    install.add_argument(
        "--skip-docker",
        action="store_true",
        help="Skip Docker daemon availability check",
    )
    install.add_argument(
        "--skip-sandbox",
        action="store_true",
        help="Skip sandbox container ping test",
    )

    mcp = sub.add_parser("mcp", help="Run as an MCP server over stdio")
    mcp.add_argument("--storage-path", type=Path, default=None, help="Override storage directory")
    mcp.add_argument("--log-dir", type=Path, default=None, help="Override logs directory")
    mcp.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override SHESHA_MODEL for queries",
    )
    mcp.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Override SHESHA_API_KEY for queries",
    )

    query = sub.add_parser("query", help="Headless query against a project")
    query.add_argument("--project", required=True, help="Project ID")
    query.add_argument("question", help="Question to ask")
    query.add_argument(
        "--storage-path",
        type=Path,
        default=None,
        help="Override storage directory",
    )
    query.add_argument("--model", type=str, default=None, help="Override SHESHA_MODEL")
    query.add_argument("--api-key", type=str, default=None, help="Override SHESHA_API_KEY")

    projects = sub.add_parser("projects", help="Manage projects")
    proj_sub = projects.add_subparsers(dest="projects_cmd", required=True)
    proj_sub.add_parser("list", help="List projects").add_argument(
        "--storage-path",
        type=Path,
        default=None,
        help="Override storage directory",
    )
    create = proj_sub.add_parser("create", help="Create a project")
    create.add_argument("project_id")
    create.add_argument(
        "--storage-path",
        type=Path,
        default=None,
        help="Override storage directory",
    )

    delete = proj_sub.add_parser("delete", help="Delete a project")
    delete.add_argument("project_id")
    delete.add_argument(
        "--storage-path",
        type=Path,
        default=None,
        help="Override storage directory",
    )

    upload = sub.add_parser("upload", help="Upload files into a project")
    upload.add_argument("--project", required=True, help="Project ID")
    upload.add_argument("path", type=Path, help="File or directory to upload")
    upload.add_argument("--recursive", action="store_true", help="Recurse into directories")
    upload.add_argument(
        "--storage-path",
        type=Path,
        default=None,
        help="Override storage directory",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    cmd = args.cmd

    resolved = resolve_paths()

    if cmd == "install":
        paths = LibrarianPaths(
            home=resolved.home,
            storage=args.storage_path if args.storage_path is not None else resolved.storage,
            logs=args.log_dir if args.log_dir is not None else resolved.logs,
        )
        manifest_dir = (
            args.manifest_dir if args.manifest_dir is not None else _default_manifest_dir()
        )

        print("Installing Librarian (Shesha RLM)…\n")
        print("Planned state + outputs:")
        print(f"  storage:  {paths.storage}")
        print(f"  logs:     {paths.logs}")
        print(f"  manifest: {_manifest_path(manifest_dir)}")
        print(f"  readme:   {_readme_path(manifest_dir)}\n")

        result = run_install(
            paths=paths,
            manifest_dir=manifest_dir,
            skip_docker=bool(args.skip_docker),
            skip_sandbox=bool(args.skip_sandbox),
        )
        if not result.ok:
            print(result.details, file=sys.stderr)
            return 1
        _print_install_summary(paths=paths, manifest_dir=manifest_dir)
        return 0

    if cmd == "mcp":
        from shesha.librarian.mcp import main as mcp_main

        mcp_args = []
        if args.storage_path is not None:
            mcp_args += ["--storage-path", str(args.storage_path)]
        if args.log_dir is not None:
            mcp_args += ["--log-dir", str(args.log_dir)]
        if args.model is not None:
            mcp_args += ["--model", args.model]
        if args.api_key is not None:
            mcp_args += ["--api-key", args.api_key]
        return mcp_main(mcp_args)

    if cmd == "query":
        storage_path = args.storage_path if args.storage_path is not None else resolved.storage
        core = LibrarianCore(storage_path=storage_path, model=args.model, api_key=args.api_key)
        try:
            answer = core.query(args.project, args.question)
        except (RuntimeError, SheshaError, ValidationError, ValueError) as e:
            print(str(e), file=sys.stderr)
            return 2
        print(answer)
        return 0

    if cmd == "projects":
        storage_path = getattr(args, "storage_path", None) or resolved.storage
        core = LibrarianCore(storage_path=storage_path)
        if args.projects_cmd == "list":
            print(json.dumps({"projects": core.list_projects()}, indent=2))
            return 0
        if args.projects_cmd == "create":
            try:
                core.create_project(args.project_id)
            except (SheshaError, ValidationError, ValueError) as e:
                print(str(e), file=sys.stderr)
                return 2
            print(json.dumps({"status": "created", "project_id": args.project_id}, indent=2))
            return 0
        if args.projects_cmd == "delete":
            try:
                core.delete_project(args.project_id)
            except (SheshaError, ValidationError, ValueError) as e:
                print(str(e), file=sys.stderr)
                return 2
            print(json.dumps({"status": "deleted", "project_id": args.project_id}, indent=2))
            return 0

    if cmd == "upload":
        storage_path = args.storage_path if args.storage_path is not None else resolved.storage
        core = LibrarianCore(storage_path=storage_path)
        try:
            uploaded = core.upload(args.project, args.path, recursive=bool(args.recursive))
        except (SheshaError, ValidationError, ValueError) as e:
            print(str(e), file=sys.stderr)
            return 2
        print(json.dumps({"uploaded": uploaded}, indent=2))
        return 0

    raise RuntimeError(f"Unhandled command: {cmd}")
