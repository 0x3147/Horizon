from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from src.core.errors import ErrorCode, HorizonApiError, capture_service_errors
from src.models import Config


class ConfigService:
    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path)

    @capture_service_errors("config", ErrorCode.CONFIG_VALIDATION_FAILED)
    def get_config(self) -> Config:
        if not self.config_path.exists():
            raise HorizonApiError(ErrorCode.CONFIG_FILE_NOT_FOUND, "Config file not found")
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        return Config.model_validate(payload)

    @capture_service_errors("config", ErrorCode.CONFIG_VALIDATION_FAILED)
    def validate_config(self, payload: dict) -> Config:
        try:
            return Config.model_validate(payload)
        except ValidationError as exc:
            raise HorizonApiError(ErrorCode.CONFIG_VALIDATION_FAILED, "Config validation failed") from exc

    @capture_service_errors("config", ErrorCode.CONFIG_SAVE_FAILED)
    def save_config(self, payload: dict) -> Config:
        config = self.validate_config(payload)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return config
