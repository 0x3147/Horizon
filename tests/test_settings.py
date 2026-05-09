from pathlib import Path

from src.core.settings import load_settings


def test_load_settings_defaults_to_horizon_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in (
        "HORIZON_HOME",
        "HORIZON_DATA_DIR",
        "HORIZON_DB_PATH",
        "HORIZON_CONFIG_PATH",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = load_settings()

    expected_home = Path(tmp_path) / ".horizon"
    assert settings.app_name == "Horizon Trace"
    assert settings.horizon_home == expected_home
    assert settings.data_dir == expected_home
    assert settings.db_path == expected_home / "horizon.db"
    assert settings.config_path == expected_home / "settings.json"


def test_load_settings_allows_explicit_overrides(tmp_path, monkeypatch):
    custom_home = tmp_path / "custom-home"
    custom_data = tmp_path / "custom-data"
    monkeypatch.setenv("HORIZON_HOME", str(custom_home))
    monkeypatch.setenv("HORIZON_DATA_DIR", str(custom_data))
    monkeypatch.setenv("HORIZON_DB_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("HORIZON_CONFIG_PATH", str(tmp_path / "settings.json"))

    settings = load_settings()

    assert settings.horizon_home == custom_home
    assert settings.data_dir == custom_data
    assert settings.db_path == tmp_path / "db.sqlite"
    assert settings.config_path == tmp_path / "settings.json"
