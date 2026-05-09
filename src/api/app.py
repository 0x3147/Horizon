from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from src.core.settings import AppSettings, load_settings


def _response(data: dict, code: int = 200) -> dict:
    return {
        "code": code,
        "success": True,
        "data": data,
        "errorCode": None,
        "errorMessage": None,
    }


def create_app(settings: AppSettings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(
        title="Horizon Local API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.state.settings = settings
    app.state.data_dir = Path(settings.data_dir)
    app.state.db_path = Path(settings.db_path)
    app.state.config_path = Path(settings.config_path)

    @app.get("/health")
    def health() -> dict:
        return _response({"status": "ok"})

    return app
