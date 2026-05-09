from __future__ import annotations

import json
import os
from pathlib import Path

from src.mcp.horizon_adapter import _load_mcp_secrets, resolve_config_path, resolve_horizon_path


def test_resolve_horizon_path_accepts_explicit_repo() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    assert resolve_horizon_path(str(repo_root)) == repo_root.resolve()


def test_resolve_config_path_defaults_to_horizon_home_settings(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    settings_path = tmp_path / ".horizon" / "settings.json"
    settings_path.parent.mkdir()
    settings_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HORIZON_HOME", raising=False)
    monkeypatch.delenv("HORIZON_DATA_DIR", raising=False)
    monkeypatch.delenv("HORIZON_CONFIG_PATH", raising=False)

    assert resolve_config_path(repo_root) == settings_path.resolve()


def test_load_mcp_secrets_loads_generic_env_keys(tmp_path: Path, monkeypatch) -> None:
    secrets_path = tmp_path / "mcp.secrets.json"
    secrets_path.write_text(
        json.dumps(
            {
                "env": {
                    "ANTHROPIC_API_KEY": "sk-ant-test",
                    "CUSTOM_TOKEN": "token-123",
                    "lowercase": "ignored",
                }
            }
        ),
        encoding="utf-8",
    )

    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("HORIZON_MCP_SECRETS_PATH", str(secrets_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CUSTOM_TOKEN", raising=False)

    _load_mcp_secrets(repo_root, override=False)

    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-test"
    assert os.environ["CUSTOM_TOKEN"] == "token-123"
    assert "lowercase" not in os.environ
