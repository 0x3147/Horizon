from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    data_dir: Path
    db_path: Path
    config_path: Path
    host: str
    port: int


def load_settings() -> AppSettings:
    data_dir = Path(os.getenv("HORIZON_DATA_DIR", "data"))
    db_path = Path(os.getenv("HORIZON_DB_PATH", str(data_dir / "horizon.db")))
    config_path = Path(os.getenv("HORIZON_CONFIG_PATH", str(data_dir / "config.json")))
    host = os.getenv("HORIZON_HOST", "127.0.0.1")
    port = int(os.getenv("HORIZON_PORT", "8765"))
    return AppSettings(
        data_dir=data_dir,
        db_path=db_path,
        config_path=config_path,
        host=host,
        port=port,
    )
