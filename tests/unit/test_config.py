"""Tests for configuration."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from shesha.config import SheshaConfig


def test_config_defaults():
    """Config has sensible defaults."""
    config = SheshaConfig()
    assert config.model == "claude-sonnet-4-20250514"
    assert config.pool_size == 3
    assert config.max_iterations == 20


def test_config_from_kwargs():
    """Config accepts keyword arguments."""
    config = SheshaConfig(model="gpt-4", pool_size=5)
    assert config.model == "gpt-4"
    assert config.pool_size == 5


def test_config_from_env():
    """Config reads from environment variables."""
    with patch.dict(os.environ, {"SHESHA_MODEL": "test-model"}):
        config = SheshaConfig.from_env()
        assert config.model == "test-model"


def test_config_from_yaml_file(tmp_path: Path):
    """Config reads from YAML file."""
    config_file = tmp_path / "shesha.yaml"
    config_file.write_text("model: yaml-model\npool_size: 7\n")
    config = SheshaConfig.from_file(config_file)
    assert config.model == "yaml-model"
    assert config.pool_size == 7


def test_config_from_json_file(tmp_path: Path):
    """Config reads from JSON file."""
    config_file = tmp_path / "shesha.json"
    config_file.write_text('{"model": "json-model", "max_iterations": 10}')
    config = SheshaConfig.from_file(config_file)
    assert config.model == "json-model"
    assert config.max_iterations == 10


def test_config_hierarchy(tmp_path: Path):
    """Config follows hierarchy: defaults < file < env < kwargs."""
    config_file = tmp_path / "shesha.yaml"
    config_file.write_text("model: file-model\npool_size: 5\n")
    with patch.dict(os.environ, {"SHESHA_MODEL": "env-model"}):
        config = SheshaConfig.load(
            config_path=config_file,
            model="kwarg-model",  # Highest priority
        )
        assert config.model == "kwarg-model"  # kwarg wins
        assert config.pool_size == 5  # from file


class TestMaxTracesConfig:
    """Tests for max_traces_per_project config."""

    def test_default_max_traces_is_50(self) -> None:
        """Default max_traces_per_project is 50."""
        config = SheshaConfig()
        assert config.max_traces_per_project == 50

    def test_max_traces_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SHESHA_MAX_TRACES_PER_PROJECT env var sets max_traces_per_project."""
        monkeypatch.setenv("SHESHA_MAX_TRACES_PER_PROJECT", "100")
        config = SheshaConfig.load()
        assert config.max_traces_per_project == 100


def test_config_has_no_allowed_hosts():
    """allowed_hosts was removed — config must not have it."""
    config = SheshaConfig()
    assert not hasattr(config, "allowed_hosts")
