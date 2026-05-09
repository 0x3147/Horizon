from pathlib import Path

from src.models import AIConfig, AIProvider, Config, FilteringConfig, SourcesConfig
from src.storage.manager import StorageManager


def minimal_config() -> Config:
    return Config(
        version="1.0",
        ai=AIConfig(provider=AIProvider.OPENAI, model="gpt-4", api_key="sk-local"),
        sources=SourcesConfig(),
        filtering=FilteringConfig(ai_score_threshold=7.0, time_window_hours=24),
    )


def test_storage_manager_defaults_config_file_to_settings_json(tmp_path: Path) -> None:
    storage = StorageManager(data_dir=str(tmp_path))

    assert storage.config_path == tmp_path / "settings.json"


def test_storage_manager_can_use_explicit_settings_path(tmp_path: Path) -> None:
    settings_path = tmp_path / ".horizon" / "settings.json"
    storage = StorageManager(data_dir=str(tmp_path / "data"), config_path=settings_path)

    saved_path = storage.save_config(minimal_config(), backup=False)

    assert saved_path == settings_path
    assert storage.load_config().ai.api_key == "sk-local"
