from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from src.api.handlers import register_exception_handlers
from src.api.routes.config import router as config_router
from src.api.schemas import ok
from src.core.settings import AppSettings, load_settings


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
    register_exception_handlers(app)

    @app.get("/health")
    def health() -> dict:
        return ok({"status": "ok"})

    app.include_router(config_router)

    return app
