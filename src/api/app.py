from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from src.api.handlers import register_exception_handlers
from src.api.routes.config import router as config_router
from src.api.routes.items import router as items_router
from src.api.routes.runs import router as runs_router
from src.api.routes.schedules import router as schedules_router
from src.api.routes.summaries import router as summaries_router
from src.api.routes.writing import router as writing_router
from src.api.schemas import ApiResponse, HealthData, ok
from src.core.settings import AppSettings, load_settings
from src.core.task_manager import TaskManager
from src.core.schedule_service import SchedulerRuntime
from src.storage.sqlite_store import SQLiteStore


OPENAPI_TAGS = [
    {"name": "health", "description": "Local API health checks."},
    {"name": "config", "description": "Read, validate, and save Horizon configuration."},
    {"name": "schedules", "description": "Manage local cron schedules."},
    {"name": "runs", "description": "Start and inspect pipeline runs."},
    {"name": "items", "description": "Query persisted content items."},
    {"name": "summaries", "description": "Read generated summaries."},
    {"name": "writing", "description": "Generate reports and blog drafts from collected items."},
]


def create_app(settings: AppSettings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.scheduler_runtime.start()
        try:
            yield
        finally:
            app.state.scheduler_runtime.shutdown()

    app = FastAPI(
        title="Horizon Local API",
        description="Local-first Horizon API for the future desktop client.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.data_dir = Path(settings.data_dir)
    app.state.db_path = Path(settings.db_path)
    app.state.config_path = Path(settings.config_path)
    app.state.store = SQLiteStore(settings.db_path)
    app.state.store.initialize()
    app.state.task_manager = TaskManager()
    app.state.scheduler_runtime = SchedulerRuntime(app.state.store, settings)
    register_exception_handlers(app)

    @app.get(
        "/health",
        response_model=ApiResponse[HealthData],
        tags=["health"],
        summary="Check API health",
    )
    def health() -> dict:
        return ok({"status": "ok"})

    app.include_router(config_router)
    app.include_router(schedules_router)
    app.include_router(runs_router)
    app.include_router(items_router)
    app.include_router(summaries_router)
    app.include_router(writing_router)

    return app
