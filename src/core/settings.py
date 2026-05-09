from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Horizon Trace"
DEFAULT_HOME_DIR_NAME = ".horizon"


@dataclass(frozen=True)
class AppSettings:
    data_dir: Path
    db_path: Path
    config_path: Path
    host: str
    port: int
    app_name: str = APP_NAME
    horizon_home: Path | None = None


def load_settings() -> AppSettings:
    horizon_home = _path_from_env("HORIZON_HOME", Path.home() / DEFAULT_HOME_DIR_NAME)
    data_dir = _path_from_env("HORIZON_DATA_DIR", horizon_home)
    db_path = _path_from_env("HORIZON_DB_PATH", data_dir / "horizon.db")
    config_path = _path_from_env("HORIZON_CONFIG_PATH", data_dir / "settings.json")
    host = os.getenv("HORIZON_HOST", "127.0.0.1")
    port = int(os.getenv("HORIZON_PORT", "8765"))
    return AppSettings(
        data_dir=data_dir,
        db_path=db_path,
        config_path=config_path,
        host=host,
        port=port,
        horizon_home=horizon_home,
    )


def load_environment_files(settings: AppSettings | None = None) -> AppSettings:
    return settings or load_settings()


def _path_from_env(name: str, default: Path) -> Path:
    return Path(os.getenv(name, str(default))).expanduser()
