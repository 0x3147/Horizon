from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from src.api.handlers import register_exception_handlers
from src.api.routes.config import router as config_router
from src.api.routes.runs import router as runs_router
from src.api.routes.schedules import router as schedules_router
from src.api.schemas import ok
from src.core.settings import AppSettings, load_settings
from src.core.task_manager import TaskManager
from src.storage.sqlite_store import SQLiteStore


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
    app.state.store = SQLiteStore(settings.db_path)
    app.state.store.initialize()
    app.state.task_manager = TaskManager()
    register_exception_handlers(app)

    @app.get("/health")
    def health() -> dict:
        return ok({"status": "ok"})

    app.include_router(config_router)
    app.include_router(schedules_router)
    app.include_router(runs_router)

    return app
