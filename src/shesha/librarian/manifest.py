"""Local manifest for operators and installers.

The manifest is intended to be vendor-neutral and local-first: it records how
this package was installed and how to run it, plus the last self-test result.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SelfTestStatus:
    ok: bool
    timestamp: str
    details: str
    docker_available: bool = True


@dataclass(frozen=True)
class LibrarianManifest:
    package_name: str
    package_version: str
    entrypoints: dict[str, str]
    commands: dict[str, list[str]]
    storage_path: str
    logs_path: str
    supported_modes: list[str]
    env_vars: list[str]
    self_test: SelfTestStatus | None = None
    docker_available: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "package": {"name": self.package_name, "version": self.package_version},
            "entrypoints": dict(self.entrypoints),
            "commands": {k: list(v) for k, v in self.commands.items()},
            "paths": {"storage": self.storage_path, "logs": self.logs_path},
            "modes": list(self.supported_modes),
            "env": list(self.env_vars),
            "self_test": asdict(self.self_test) if self.self_test is not None else None,
            "infra": {"docker_available": self.docker_available},
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True))

    @classmethod
    def read(cls, path: Path) -> "LibrarianManifest":
        data = json.loads(path.read_text())

        package = data.get("package") or {}
        paths = data.get("paths") or {}

        commands_raw = data.get("commands") or {}
        commands: dict[str, list[str]] = {}
        if isinstance(commands_raw, dict):
            for key, value in commands_raw.items():
                if not isinstance(key, str) or not isinstance(value, list):
                    continue
                if not all(isinstance(item, str) for item in value):
                    continue
                commands[key] = list(value)

        self_test_raw = data.get("self_test")
        self_test = None
        if isinstance(self_test_raw, dict):
            self_test = SelfTestStatus(
                ok=bool(self_test_raw.get("ok")),
                timestamp=str(self_test_raw.get("timestamp", "")),
                details=str(self_test_raw.get("details", "")),
                docker_available=bool(self_test_raw.get("docker_available", True)),
            )

        infra = data.get("infra") or {}
        docker_available = bool(infra.get("docker_available", True))

        return cls(
            package_name=str(package.get("name", "")),
            package_version=str(package.get("version", "")),
            entrypoints=dict(data.get("entrypoints") or {}),
            commands=commands,
            storage_path=str(paths.get("storage", "")),
            logs_path=str(paths.get("logs", "")),
            supported_modes=list(data.get("modes") or []),
            env_vars=list(data.get("env") or []),
            self_test=self_test,
            docker_available=docker_available,
        )
