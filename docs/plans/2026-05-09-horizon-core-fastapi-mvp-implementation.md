# Horizon Core FastAPI MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 基于已审阅的中文设计草案，把 Horizon 改造成具备 FastAPI、本地 SQLite 持久化、统一响应格式、业务异常码、cron 调度和可查询运行产物的本地后端。

**Architecture:** FastAPI 作为薄接口层，Core Services 负责编排业务，SQLiteStore 负责本地持久化，现有 Horizon scraper/analyzer/enricher/summarizer 尽量复用。所有 API 返回统一 `ApiResponse[T]` 包络，业务异常通过 `HorizonApiError`、异常码表和全局异常处理器转换。

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, APScheduler, SQLite stdlib `sqlite3`, Pydantic v2, pytest, FastAPI TestClient.

---

## 前置约束

- 当前分支：`feat/horizon-core-fastapi-mvp`。
- 不实现 Electron UI。
- 不实现 OS 级后台服务。
- 不实现账号、同步、社区功能。
- 不做配置备份文件或配置历史 API。
- FastAPI 默认监听 `127.0.0.1:8765`。
- cron 只支持标准 5 段表达式。
- 开发默认数据库路径：`data/horizon.db`。
- API 必须使用统一响应格式：

```json
{
  "code": 200,
  "success": true,
  "data": {},
  "errorCode": null,
  "errorMessage": null
}
```

---

## Task 1: 添加 FastAPI 依赖和本地 API 启动骨架

**Files:**
- Modify: `pyproject.toml`
- Create: `src/api/__init__.py`
- Create: `src/api/app.py`
- Create: `src/api/server.py`
- Create: `src/core/__init__.py`
- Create: `src/core/settings.py`
- Test: `tests/test_api_health.py`

**Step 1: 写失败测试**

创建 `tests/test_api_health.py`：

```python
from fastapi.testclient import TestClient

from src.api.app import create_app


def test_health_uses_unified_response():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "success": True,
        "data": {"status": "ok"},
        "errorCode": None,
        "errorMessage": None,
    }


def test_openapi_and_swagger_are_available():
    client = TestClient(create_app())

    openapi = client.get("/openapi.json")
    docs = client.get("/docs")

    assert openapi.status_code == 200
    assert openapi.json()["info"]["title"] == "Horizon Local API"
    assert docs.status_code == 200
    assert "Swagger UI" in docs.text
```

**Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_api_health.py -q
```

Expected: FAIL，原因是 `src.api.app` 还不存在。

**Step 3: 添加依赖和脚本入口**

修改 `pyproject.toml`：

```toml
dependencies = [
    ...
    "fastapi>=0.115.0",
    "uvicorn>=0.30.0",
    "apscheduler>=3.10.4",
]
```

在 `[project.scripts]` 下新增：

```toml
horizon-api = "src.api.server:main"
```

**Step 4: 添加路径配置对象**

创建 `src/core/__init__.py`：

```python
"""Core services for Horizon local API."""
```

创建 `src/core/settings.py`：

```python
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
```

**Step 5: 添加 FastAPI app**

创建 `src/api/__init__.py`：

```python
"""FastAPI local server package for Horizon."""
```

创建 `src/api/app.py`：

```python
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
```

创建 `src/api/server.py`：

```python
from __future__ import annotations

import uvicorn

from src.api.app import create_app
from src.core.settings import load_settings


def main() -> None:
    settings = load_settings()
    print(f"HORIZON_API_READY http://{settings.host}:{settings.port}", flush=True)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
```

**Step 6: 运行测试确认通过**

Run:

```bash
uv run pytest tests/test_api_health.py -q
```

Expected: PASS。

**Step 7: 提交**

```bash
git add pyproject.toml src/api src/core tests/test_api_health.py
git commit -m "feat(api): add local FastAPI skeleton"
```

---

## Task 2: 实现统一响应模型、业务异常和异常捕获装饰器

**Files:**
- Create: `src/api/schemas.py`
- Create: `src/api/handlers.py`
- Create: `src/core/errors.py`
- Modify: `src/api/app.py`
- Test: `tests/test_api_errors.py`

**Step 1: 写失败测试**

创建 `tests/test_api_errors.py`：

```python
import asyncio

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.errors import ErrorCode, HorizonApiError, capture_service_errors


def test_business_error_uses_unified_response():
    app = create_app()
    router = APIRouter()

    @router.get("/boom")
    def boom():
        raise HorizonApiError(ErrorCode.RUN_NOT_FOUND, "Run not found")

    app.include_router(router)
    client = TestClient(app)

    response = client.get("/boom")

    assert response.status_code == 404
    assert response.json()["success"] is False
    assert response.json()["errorCode"] == 4001
    assert response.json()["errorMessage"] == "Run not found"


def test_request_validation_uses_unified_response():
    app = create_app()
    router = APIRouter()

    @router.get("/needs-int")
    def needs_int(value: int):
        return {"value": value}

    app.include_router(router)
    client = TestClient(app)

    response = client.get("/needs-int", params={"value": "bad"})

    assert response.status_code == 422
    assert response.json()["success"] is False
    assert response.json()["errorCode"] == 1001


def test_capture_service_errors_maps_unknown_exception():
    @capture_service_errors(module="test", default_error_code=ErrorCode.UNKNOWN_ERROR)
    def broken():
        raise RuntimeError("internal detail")

    with pytest.raises(HorizonApiError) as exc:
        broken()

    assert exc.value.error_code == ErrorCode.UNKNOWN_ERROR


def test_capture_service_errors_does_not_swallow_cancelled_error():
    @capture_service_errors(module="test", default_error_code=ErrorCode.UNKNOWN_ERROR)
    async def cancelled():
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cancelled())
```

**Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_api_errors.py -q
```

Expected: FAIL，原因是异常模块和 handlers 还不存在。

**Step 3: 实现响应模型**

创建 `src/api/schemas.py`：

```python
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int
    success: bool
    data: T | None = None
    errorCode: int | None = None
    errorMessage: str | None = None


def ok(data: T, code: int = 200) -> dict:
    return ApiResponse[T](
        code=code,
        success=True,
        data=data,
        errorCode=None,
        errorMessage=None,
    ).model_dump()


def fail(code: int, error_code: int, message: str) -> dict:
    return ApiResponse[None](
        code=code,
        success=False,
        data=None,
        errorCode=error_code,
        errorMessage=message,
    ).model_dump()
```

**Step 4: 实现业务异常和装饰器**

创建 `src/core/errors.py`：

```python
from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import sqlite3
from enum import IntEnum
from zoneinfo import ZoneInfoNotFoundError

from pydantic import ValidationError

logger = logging.getLogger(__name__)


class ErrorCode(IntEnum):
    UNKNOWN_ERROR = 1000
    INVALID_REQUEST = 1001
    RESOURCE_NOT_FOUND = 1002
    CONFIG_FILE_NOT_FOUND = 2001
    CONFIG_VALIDATION_FAILED = 2002
    CONFIG_SAVE_FAILED = 2003
    SCHEDULE_NOT_FOUND = 3001
    INVALID_CRON_EXPRESSION = 3002
    UNSUPPORTED_CRON_FORMAT = 3003
    INVALID_TIMEZONE = 3004
    RUN_NOT_FOUND = 4001
    RUN_ALREADY_IN_PROGRESS = 4002
    RUN_CANCELLATION_FAILED = 4003
    PIPELINE_EXECUTION_FAILED = 4004
    ITEM_NOT_FOUND = 5001
    INVALID_ITEM_QUERY = 5002
    SUMMARY_NOT_FOUND = 6001
    SUMMARY_GENERATION_FAILED = 6002
    DATABASE_UNAVAILABLE = 7001
    DATABASE_WRITE_FAILED = 7002


HTTP_STATUS_BY_CODE = {
    ErrorCode.RESOURCE_NOT_FOUND: 404,
    ErrorCode.CONFIG_FILE_NOT_FOUND: 404,
    ErrorCode.SCHEDULE_NOT_FOUND: 404,
    ErrorCode.RUN_NOT_FOUND: 404,
    ErrorCode.ITEM_NOT_FOUND: 404,
    ErrorCode.SUMMARY_NOT_FOUND: 404,
    ErrorCode.INVALID_REQUEST: 422,
    ErrorCode.CONFIG_VALIDATION_FAILED: 422,
    ErrorCode.INVALID_CRON_EXPRESSION: 200,
    ErrorCode.UNSUPPORTED_CRON_FORMAT: 200,
    ErrorCode.INVALID_TIMEZONE: 200,
}


class HorizonApiError(Exception):
    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        http_status: int | None = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.http_status = http_status or HTTP_STATUS_BY_CODE.get(error_code, 500)


def _map_exception(exc: Exception, default_error_code: ErrorCode) -> HorizonApiError:
    if isinstance(exc, HorizonApiError):
        return exc
    if isinstance(exc, FileNotFoundError):
        return HorizonApiError(ErrorCode.CONFIG_FILE_NOT_FOUND, "Config file not found")
    if isinstance(exc, ValidationError):
        return HorizonApiError(ErrorCode.CONFIG_VALIDATION_FAILED, "Config validation failed")
    if isinstance(exc, ZoneInfoNotFoundError):
        return HorizonApiError(ErrorCode.INVALID_TIMEZONE, "Invalid timezone")
    if isinstance(exc, sqlite3.OperationalError):
        return HorizonApiError(ErrorCode.DATABASE_UNAVAILABLE, "Database unavailable")
    if isinstance(exc, sqlite3.DatabaseError):
        return HorizonApiError(ErrorCode.DATABASE_WRITE_FAILED, "Database write failed")
    return HorizonApiError(default_error_code, "Unknown error")


def capture_service_errors(module: str, default_error_code: ErrorCode):
    def decorator(func):
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except asyncio.CancelledError:
                    raise
                except HorizonApiError:
                    raise
                except Exception as exc:
                    logger.exception("Service error in %s.%s", module, func.__name__)
                    raise _map_exception(exc, default_error_code) from exc
            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except HorizonApiError:
                raise
            except Exception as exc:
                logger.exception("Service error in %s.%s", module, func.__name__)
                raise _map_exception(exc, default_error_code) from exc
        return sync_wrapper

    return decorator
```

**Step 5: 实现 FastAPI 异常处理器**

创建 `src/api/handlers.py`：

```python
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.api.schemas import fail
from src.core.errors import ErrorCode, HorizonApiError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HorizonApiError)
    async def horizon_error_handler(request: Request, exc: HorizonApiError):
        return JSONResponse(
            status_code=exc.http_status,
            content=fail(exc.http_status, int(exc.error_code), exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=fail(422, int(ErrorCode.INVALID_REQUEST), "Invalid request"),
        )

    @app.exception_handler(Exception)
    async def unknown_error_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content=fail(500, int(ErrorCode.UNKNOWN_ERROR), "Unknown error"),
        )
```

**Step 6: 接入 app**

修改 `src/api/app.py`：

```python
from src.api.handlers import register_exception_handlers
from src.api.schemas import ok

# create_app 内
register_exception_handlers(app)

# health 返回
return ok({"status": "ok"})
```

移除 Task 1 中的临时 `_response`。

**Step 7: 运行测试**

Run:

```bash
uv run pytest tests/test_api_health.py tests/test_api_errors.py -q
```

Expected: PASS。

**Step 8: 提交**

```bash
git add src/api src/core/errors.py tests/test_api_errors.py tests/test_api_health.py
git commit -m "feat(api): add unified responses and business errors"
```

---

## Task 3: 实现 SQLite schema 和基础仓储

**Files:**
- Create: `src/storage/sqlite_store.py`
- Test: `tests/test_sqlite_store.py`

**Step 1: 写失败测试**

创建 `tests/test_sqlite_store.py`：

```python
import sqlite3

from src.storage.sqlite_store import SQLiteStore


def tables(db_path):
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def test_initialize_creates_schema(tmp_path):
    db_path = tmp_path / "horizon.db"
    store = SQLiteStore(db_path)

    store.initialize()

    assert {
        "schema_migrations",
        "runs",
        "items",
        "item_analysis",
        "summaries",
        "run_logs",
        "schedules",
    }.issubset(tables(db_path))


def test_initialize_is_idempotent(tmp_path):
    store = SQLiteStore(tmp_path / "horizon.db")

    store.initialize()
    store.initialize()

    assert "runs" in tables(tmp_path / "horizon.db")
```

**Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_sqlite_store.py -q
```

Expected: FAIL，原因是 `SQLiteStore` 不存在。

**Step 3: 实现 schema**

创建 `src/storage/sqlite_store.py`，至少包含：

```python
from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        hours INTEGER NOT NULL,
        started_at TEXT,
        finished_at TEXT,
        config_snapshot_json TEXT,
        raw_count INTEGER NOT NULL DEFAULT 0,
        scored_count INTEGER NOT NULL DEFAULT 0,
        filtered_count INTEGER NOT NULL DEFAULT 0,
        enriched_count INTEGER NOT NULL DEFAULT 0,
        error_message TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS items (
        id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_name TEXT,
        native_id TEXT,
        title TEXT NOT NULL,
        url TEXT NOT NULL,
        content TEXT,
        author TEXT,
        published_at TEXT,
        fetched_at TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        stage TEXT NOT NULL DEFAULT 'raw',
        is_selected INTEGER NOT NULL DEFAULT 0,
        duplicate_of_item_id TEXT,
        PRIMARY KEY (run_id, id),
        FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS item_analysis (
        run_id TEXT NOT NULL,
        item_id TEXT NOT NULL,
        ai_score REAL,
        ai_reason TEXT,
        ai_summary TEXT,
        ai_tags_json TEXT NOT NULL DEFAULT '[]',
        detailed_summary_json TEXT NOT NULL DEFAULT '{}',
        background_json TEXT NOT NULL DEFAULT '{}',
        community_discussion_json TEXT NOT NULL DEFAULT '{}',
        citations_json TEXT NOT NULL DEFAULT '[]',
        PRIMARY KEY (run_id, item_id),
        FOREIGN KEY (run_id, item_id) REFERENCES items(run_id, id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS summaries (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        language TEXT NOT NULL,
        markdown TEXT NOT NULL,
        saved_path TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT,
        level TEXT NOT NULL,
        stage TEXT,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS schedules (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        cron_expr TEXT NOT NULL,
        cron_label TEXT,
        timezone TEXT NOT NULL,
        hours_window INTEGER NOT NULL DEFAULT 24,
        source_filter_json TEXT,
        last_run_id TEXT,
        last_run_at TEXT,
        next_run_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
)


class SQLiteStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            for statement in SCHEMA_SQL:
                conn.execute(statement)
            conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (1)")
            conn.commit()
```

**Step 4: 运行测试**

Run:

```bash
uv run pytest tests/test_sqlite_store.py -q
```

Expected: PASS。

**Step 5: 提交**

```bash
git add src/storage/sqlite_store.py tests/test_sqlite_store.py
git commit -m "feat(storage): add sqlite schema"
```

---

## Task 4: 实现 ConfigService 和 Config API

**Files:**
- Create: `src/core/config_service.py`
- Create: `src/api/routes/__init__.py`
- Create: `src/api/routes/config.py`
- Modify: `src/api/app.py`
- Test: `tests/test_config_api.py`

**Step 1: 写失败测试**

创建 `tests/test_config_api.py`：

```python
import json

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.settings import AppSettings


def settings(tmp_path):
    data_dir = tmp_path / "data"
    return AppSettings(
        data_dir=data_dir,
        db_path=data_dir / "horizon.db",
        config_path=data_dir / "config.json",
        host="127.0.0.1",
        port=8765,
    )


def minimal_config():
    return {
        "version": "1.0",
        "ai": {
            "provider": "openai",
            "model": "gpt-4",
            "api_key_env": "OPENAI_API_KEY",
        },
        "sources": {
            "github": [],
            "hackernews": {"enabled": False},
            "rss": [],
            "reddit": {"enabled": False, "subreddits": [], "users": []},
            "telegram": {"enabled": False, "channels": []},
        },
        "filtering": {"ai_score_threshold": 7.0, "time_window_hours": 24},
    }


def test_get_config(tmp_path):
    s = settings(tmp_path)
    s.data_dir.mkdir()
    s.config_path.write_text(json.dumps(minimal_config()), encoding="utf-8")
    client = TestClient(create_app(s))

    response = client.get("/config")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["ai"]["model"] == "gpt-4"


def test_put_config_validates_and_saves(tmp_path):
    s = settings(tmp_path)
    s.data_dir.mkdir()
    s.config_path.write_text(json.dumps(minimal_config()), encoding="utf-8")
    client = TestClient(create_app(s))
    updated = minimal_config()
    updated["filtering"]["ai_score_threshold"] = 8.0

    response = client.put("/config", json=updated)

    assert response.status_code == 200
    assert response.json()["data"]["filtering"]["ai_score_threshold"] == 8.0
    saved = json.loads(s.config_path.read_text(encoding="utf-8"))
    assert saved["filtering"]["ai_score_threshold"] == 8.0


def test_validate_config_rejects_invalid_payload(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))

    response = client.post("/config/validate", json={"bad": "payload"})

    assert response.status_code == 422
    assert response.json()["success"] is False
    assert response.json()["errorCode"] == 2002
```

**Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_config_api.py -q
```

Expected: FAIL，原因是 config service/routes 不存在。

**Step 3: 实现 ConfigService**

创建 `src/core/config_service.py`：

```python
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
```

**Step 4: 实现 route**

创建 `src/api/routes/__init__.py`：

```python
"""FastAPI route modules."""
```

创建 `src/api/routes/config.py`：

```python
from fastapi import APIRouter, Request

from src.api.schemas import ok
from src.core.config_service import ConfigService

router = APIRouter(prefix="/config", tags=["config"])


def service(request: Request) -> ConfigService:
    return ConfigService(request.app.state.settings.config_path)


@router.get("")
def get_config(request: Request) -> dict:
    return ok(service(request).get_config().model_dump(mode="json"))


@router.put("")
def put_config(payload: dict, request: Request) -> dict:
    return ok(service(request).save_config(payload).model_dump(mode="json"))


@router.post("/validate")
def validate_config(payload: dict, request: Request) -> dict:
    config = service(request).validate_config(payload)
    return ok({"valid": True, "config": config.model_dump(mode="json")})
```

修改 `src/api/app.py`：

```python
from src.api.routes.config import router as config_router

app.include_router(config_router)
```

**Step 5: 运行测试**

Run:

```bash
uv run pytest tests/test_config_api.py tests/test_api_errors.py -q
```

Expected: PASS。

**Step 6: 提交**

```bash
git add src/core/config_service.py src/api/routes src/api/app.py tests/test_config_api.py
git commit -m "feat(api): add config endpoints"
```

---

## Task 5: 实现 SQLite 仓储读写方法

**Files:**
- Modify: `src/storage/sqlite_store.py`
- Test: `tests/test_sqlite_repository.py`

**Step 1: 写失败测试**

创建 `tests/test_sqlite_repository.py`，覆盖：

- `create_run`
- `update_run`
- `list_runs`
- `add_log`
- `list_logs`
- `save_items`
- `query_items`
- `save_summary`
- `list_summaries`

关键测试示例：

```python
from datetime import datetime, timezone

from src.models import ContentItem, SourceType
from src.storage.sqlite_store import SQLiteStore


def item(score=8.5):
    return ContentItem(
        id="rss:1",
        source_type=SourceType.RSS,
        title="Example",
        url="https://example.com/post",
        content="Body",
        author="Alice",
        published_at=datetime(2026, 5, 9, tzinfo=timezone.utc),
        ai_score=score,
        ai_reason="Useful",
        ai_summary="Summary",
        ai_tags=["ai", "infra"],
        metadata={"feed_name": "Example Feed"},
    )


def test_run_item_summary_roundtrip(tmp_path):
    store = SQLiteStore(tmp_path / "horizon.db")
    store.initialize()

    store.create_run("run-1", hours=24, config_snapshot={"version": "1.0"})
    store.update_run("run-1", status="running")
    store.add_log("run-1", "info", "fetching", "started")
    store.save_items("run-1", [item()], stage="filtered", selected=True)
    store.save_summary("run-1", "en", "# Summary")

    assert store.get_run("run-1")["status"] == "running"
    assert store.list_logs("run-1")[0]["message"] == "started"
    assert store.query_items(min_score=8.0, selected_only=True)[0]["title"] == "Example"
    assert store.list_summaries("run-1")[0]["markdown"] == "# Summary"
```

**Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_sqlite_repository.py -q
```

Expected: FAIL，仓储方法未实现。

**Step 3: 实现仓储方法**

在 `src/storage/sqlite_store.py` 中实现测试覆盖的方法。实现要求：

- 所有 JSON 字段使用 `json.dumps(..., ensure_ascii=False)`。
- `query_items` 支持 `run_id/source_type/min_score/max_score/selected_only/stage/tag/q/limit/offset`。
- `get_item` 必须按 `item_id` 精确查询，不能用列表遍历。
- 数据库异常可以先自然抛出，后续 service 装饰器统一映射。

**Step 4: 运行测试**

Run:

```bash
uv run pytest tests/test_sqlite_store.py tests/test_sqlite_repository.py -q
```

Expected: PASS。

**Step 5: 提交**

```bash
git add src/storage/sqlite_store.py tests/test_sqlite_repository.py
git commit -m "feat(storage): persist run artifacts"
```

---

## Task 6: 实现 ScheduleService 和 Schedule API

**Files:**
- Create: `src/core/schedule_service.py`
- Create: `src/api/routes/schedules.py`
- Modify: `src/api/app.py`
- Modify: `src/storage/sqlite_store.py`
- Test: `tests/test_schedule_service.py`
- Test: `tests/test_schedules_api.py`

**Step 1: 写 service 测试**

创建 `tests/test_schedule_service.py`：

```python
import pytest

from src.core.errors import HorizonApiError
from src.core.schedule_service import ScheduleService
from src.storage.sqlite_store import SQLiteStore


def test_validate_five_field_cron(tmp_path):
    service = ScheduleService(SQLiteStore(tmp_path / "horizon.db"))

    result = service.validate_cron("0 8 * * *", "Asia/Shanghai")

    assert result["valid"] is True
    assert result["next_run_at"]


def test_reject_six_field_cron(tmp_path):
    service = ScheduleService(SQLiteStore(tmp_path / "horizon.db"))

    with pytest.raises(HorizonApiError) as exc:
        service.validate_cron("0 0 8 * * *", "Asia/Shanghai")

    assert int(exc.value.error_code) == 3003


def test_create_schedule_persists(tmp_path):
    store = SQLiteStore(tmp_path / "horizon.db")
    store.initialize()
    service = ScheduleService(store)

    schedule = service.create_schedule(
        name="Daily",
        cron_expr="0 8 * * *",
        timezone_name="Asia/Shanghai",
        hours_window=24,
        cron_label="daily_8am",
        enabled=True,
    )

    assert store.get_schedule(schedule["id"])["name"] == "Daily"
```

**Step 2: 写 API 测试**

创建 `tests/test_schedules_api.py`：

```python
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.settings import AppSettings


def settings(tmp_path):
    data_dir = tmp_path / "data"
    return AppSettings(data_dir, data_dir / "horizon.db", data_dir / "config.json", "127.0.0.1", 8765)


def test_validate_cron_endpoint(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))

    response = client.post(
        "/schedules/validate-cron",
        json={"cron_expr": "0 8 * * *", "timezone": "Asia/Shanghai"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["valid"] is True


def test_create_and_list_schedule(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))

    response = client.post(
        "/schedules",
        json={
            "name": "Daily",
            "cron_expr": "0 8 * * *",
            "cron_label": "daily_8am",
            "timezone": "Asia/Shanghai",
            "hours_window": 24,
            "enabled": True,
        },
    )

    assert response.status_code == 201
    schedule_id = response.json()["data"]["id"]
    list_response = client.get("/schedules")
    assert list_response.json()["data"]["items"][0]["id"] == schedule_id
```

**Step 3: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_schedule_service.py tests/test_schedules_api.py -q
```

Expected: FAIL。

**Step 4: 实现 ScheduleService**

创建 `src/core/schedule_service.py`：

```python
from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger

from src.core.errors import ErrorCode, HorizonApiError, capture_service_errors
from src.storage.sqlite_store import SQLiteStore


class ScheduleService:
    def __init__(self, store: SQLiteStore):
        self.store = store

    @capture_service_errors("schedule", ErrorCode.INVALID_CRON_EXPRESSION)
    def validate_cron(self, cron_expr: str, timezone_name: str) -> dict:
        parts = cron_expr.split()
        if len(parts) != 5:
            raise HorizonApiError(ErrorCode.UNSUPPORTED_CRON_FORMAT, "Unsupported cron format")
        try:
            tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise HorizonApiError(ErrorCode.INVALID_TIMEZONE, "Invalid timezone") from exc
        try:
            trigger = CronTrigger.from_crontab(cron_expr, timezone=tz)
            next_run = trigger.get_next_fire_time(None, datetime.now(tz))
        except ValueError as exc:
            raise HorizonApiError(ErrorCode.INVALID_CRON_EXPRESSION, "Invalid cron expression") from exc
        return {"valid": True, "next_run_at": next_run.isoformat() if next_run else None}

    def create_schedule(
        self,
        name: str,
        cron_expr: str,
        timezone_name: str,
        hours_window: int,
        cron_label: str | None = None,
        enabled: bool = True,
    ) -> dict:
        validation = self.validate_cron(cron_expr, timezone_name)
        schedule = {
            "id": f"schedule-{uuid4().hex}",
            "name": name,
            "enabled": enabled,
            "cron_expr": cron_expr,
            "cron_label": cron_label,
            "timezone": timezone_name,
            "hours_window": hours_window,
            "next_run_at": validation["next_run_at"],
        }
        self.store.save_schedule(schedule)
        return schedule
```

**Step 5: 实现 route 和 store 方法**

在 `SQLiteStore` 中添加 `save_schedule/list_schedules/get_schedule/delete_schedule`。

创建 `src/api/routes/schedules.py`，用 `ok(...)` 包装返回。创建接口：

- `POST /schedules/validate-cron`
- `POST /schedules`
- `GET /schedules`
- `DELETE /schedules/{schedule_id}`

删除接口可返回 204 或统一响应；若前端需要一致包络，建议返回 200 + `ok({"deleted": True})`。

修改 `src/api/app.py` include router。

**Step 6: 运行测试**

Run:

```bash
uv run pytest tests/test_schedule_service.py tests/test_schedules_api.py -q
```

Expected: PASS。

**Step 7: 提交**

```bash
git add src/core/schedule_service.py src/api/routes/schedules.py src/api/app.py src/storage/sqlite_store.py tests/test_schedule_service.py tests/test_schedules_api.py
git commit -m "feat(api): add cron schedules"
```

---

## Task 7: 实现 PipelineService 阶段持久化

**Files:**
- Create: `src/core/pipeline_service.py`
- Test: `tests/test_pipeline_service.py`

**Step 1: 写 fake-based 测试**

创建 `tests/test_pipeline_service.py`，使用 fake orchestrator/fake analyzer，避免真实网络和 AI。测试必须验证：

- 创建 run。
- 保存 raw/scored/filtered/enriched items。
- 保存 summary。
- run 最终 `succeeded`。
- 出错时 run `failed` 并写日志。
- cancel event 设置时 run `cancelled`。

**Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_pipeline_service.py -q
```

Expected: FAIL。

**Step 3: 实现 PipelineService**

创建 `src/core/pipeline_service.py`。实现要求：

- 构造时接受 `SQLiteStore`、`settings`。
- 默认从 `ConfigService` 读取配置。
- 默认构造 `StorageManager` 和 `HorizonOrchestrator`。
- 可注入 `orchestrator_factory/analyzer_factory` 方便测试。
- 每个阶段写入 `run_logs`。
- 每个阶段更新 `runs.status`。
- 阶段产物写入 SQLite。
- `asyncio.CancelledError` 标记 cancelled 后继续抛出。
- 其他异常标记 failed 并抛出 `HorizonApiError(4004)`。

**Step 4: 运行测试**

Run:

```bash
uv run pytest tests/test_pipeline_service.py tests/test_sqlite_repository.py -q
```

Expected: PASS。

**Step 5: 提交**

```bash
git add src/core/pipeline_service.py tests/test_pipeline_service.py
git commit -m "feat(core): persist pipeline stages"
```

---

## Task 8: 实现 Run API 和后台任务管理

**Files:**
- Create: `src/core/task_manager.py`
- Create: `src/api/routes/runs.py`
- Modify: `src/api/app.py`
- Test: `tests/test_runs_api.py`

**Step 1: 写失败测试**

创建 `tests/test_runs_api.py`，测试：

- `POST /runs` 返回统一响应，状态码 202，包含 run_id。
- `GET /runs` 返回列表。
- `GET /runs/{id}` 不存在时返回 `errorCode=4001`。
- `GET /runs/{id}/logs` 返回日志。
- `POST /runs/{id}/cancel` 返回取消请求结果。

测试中应 monkeypatch task manager，避免真的跑 pipeline。

**Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_runs_api.py -q
```

Expected: FAIL。

**Step 3: 实现 TaskManager**

创建 `src/core/task_manager.py`：

- 保存 `run_id -> asyncio.Task`。
- 保存 `run_id -> asyncio.Event`。
- `start(run_id, coro_factory)`。
- `cancel(run_id)`。
- 任务完成后自动清理。

**Step 4: 实现 Run routes**

创建 `src/api/routes/runs.py`：

- `POST /runs`
- `GET /runs`
- `GET /runs/{run_id}`
- `POST /runs/{run_id}/cancel`
- `GET /runs/{run_id}/logs`

所有返回都使用 `ok(...)`。

**Step 5: 接入 app**

修改 `src/api/app.py`：

- 初始化 `SQLiteStore` 并 `initialize()`。
- 初始化 `TaskManager`。
- include runs router。

**Step 6: 运行测试**

Run:

```bash
uv run pytest tests/test_runs_api.py tests/test_api_health.py -q
```

Expected: PASS。

**Step 7: 提交**

```bash
git add src/core/task_manager.py src/api/routes/runs.py src/api/app.py tests/test_runs_api.py
git commit -m "feat(api): add run management"
```

---

## Task 9: 实现 Item API 和 Summary API

**Files:**
- Create: `src/api/routes/items.py`
- Create: `src/api/routes/summaries.py`
- Modify: `src/api/app.py`
- Test: `tests/test_items_api.py`
- Test: `tests/test_summaries_api.py`

**Step 1: 写失败测试**

`tests/test_items_api.py` 覆盖：

- `GET /items?min_score=8&selected_only=true`
- `GET /items?tag=ai`
- `GET /items?q=keyword`
- `GET /items/{item_id}`
- item 不存在返回 `errorCode=5001`

`tests/test_summaries_api.py` 覆盖：

- `GET /summaries`
- `GET /runs/{run_id}/summaries`
- summary 不存在场景按设计返回空列表或 `6001`，二选一并保持一致。

**Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_items_api.py tests/test_summaries_api.py -q
```

Expected: FAIL。

**Step 3: 实现 routes**

创建 `src/api/routes/items.py` 和 `src/api/routes/summaries.py`。所有返回使用统一响应包络。

**Step 4: 接入 app**

修改 `src/api/app.py` include routers。

**Step 5: 运行测试**

Run:

```bash
uv run pytest tests/test_items_api.py tests/test_summaries_api.py -q
```

Expected: PASS。

**Step 6: 提交**

```bash
git add src/api/routes/items.py src/api/routes/summaries.py src/api/app.py tests/test_items_api.py tests/test_summaries_api.py
git commit -m "feat(api): expose item and summary queries"
```

---

## Task 10: 接入 APScheduler 运行时

**Files:**
- Modify: `src/core/schedule_service.py`
- Modify: `src/api/app.py`
- Test: `tests/test_scheduler_runtime.py`

**Step 1: 写失败测试**

创建 `tests/test_scheduler_runtime.py`：

```python
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.settings import AppSettings


def test_app_exposes_scheduler_runtime(tmp_path):
    data_dir = tmp_path / "data"
    app = create_app(AppSettings(data_dir, data_dir / "horizon.db", data_dir / "config.json", "127.0.0.1", 8765))

    assert hasattr(app.state, "scheduler_runtime")


def test_lifespan_health_still_works(tmp_path):
    data_dir = tmp_path / "data"
    app = create_app(AppSettings(data_dir, data_dir / "horizon.db", data_dir / "config.json", "127.0.0.1", 8765))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
```

**Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_scheduler_runtime.py -q
```

Expected: FAIL。

**Step 3: 实现 SchedulerRuntime**

在 `src/core/schedule_service.py` 添加：

- `SchedulerRuntime`
- `start()`
- `shutdown()`
- `reload()`
- `_run_schedule(schedule)`

要求：

- 使用 `AsyncIOScheduler`。
- 对 enabled schedules 建 job。
- `max_instances=1`。
- `coalesce=True`。
- 定时触发调用 `PipelineService.run(hours=schedule["hours_window"])`。

**Step 4: 接入 FastAPI lifespan**

修改 `src/api/app.py`：

- 创建 `SchedulerRuntime`。
- 在 lifespan start。
- 在 lifespan shutdown。

**Step 5: 运行测试**

Run:

```bash
uv run pytest tests/test_scheduler_runtime.py tests/test_schedules_api.py -q
```

Expected: PASS。

**Step 6: 提交**

```bash
git add src/core/schedule_service.py src/api/app.py tests/test_scheduler_runtime.py
git commit -m "feat(core): run schedules in api process"
```

---

## Task 11: 文档更新和本地 API smoke test

**Files:**
- Create: `docs/api.md`
- Modify: `README.md`
- Modify: `README_zh.md`
- Test: no dedicated test required

**Step 1: 写 API 文档**

创建 `docs/api.md`，包含：

- 启动命令：`uv run horizon-api`
- 默认地址：`http://127.0.0.1:8765`
- Swagger：`/docs`
- OpenAPI：`/openapi.json`
- 统一响应格式
- 业务异常码范围
- 主要 endpoint 列表
- cron 5 段示例
- 环境变量：
  - `HORIZON_DATA_DIR`
  - `HORIZON_DB_PATH`
  - `HORIZON_CONFIG_PATH`
  - `HORIZON_HOST`
  - `HORIZON_PORT`

**Step 2: 更新 README**

在 `README.md` 和 `README_zh.md` 增加本地 API 简短说明，链接到 `docs/api.md`。

**Step 3: 运行测试**

Run:

```bash
uv run pytest -q
```

Expected: PASS。

**Step 4: 手动 smoke test**

Run:

```bash
uv run horizon-api
```

另开终端：

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/openapi.json
curl http://127.0.0.1:8765/schedules
```

Expected:

- `/health` 返回统一响应。
- `/openapi.json` 返回 schema。
- `/schedules` 返回统一响应。

**Step 5: 提交**

```bash
git add docs/api.md README.md README_zh.md
git commit -m "docs: document local api"
```

---

## Task 12: 最终验证

**Files:**
- No new files expected.

**Step 1: 全量测试**

Run:

```bash
uv run pytest -q
```

Expected: PASS。

**Step 2: 检查新增 API 文档**

Run:

```bash
Get-Content -Encoding UTF8 docs\api.md | Select-Object -First 40
```

Expected: 文档可读，包含启动命令、Swagger、统一响应格式。

**Step 3: 检查 git 状态**

Run:

```bash
git status --short
```

Expected: clean working tree after task commits.

**Step 4: 可选端到端手动运行**

如果本地 `.env` 和 `data/config.json` 可用：

```bash
uv run horizon-api
```

然后通过 Swagger `POST /runs` 触发一次运行。

Expected:

- 创建 run。
- 可查询 logs。
- 可查询 items。
- 可查询 summaries。

---

## 执行注意事项

- 每个 task 完成后单独提交，避免大块变更难以 review。
- 所有 API route 返回必须使用统一 `ApiResponse`。
- 所有业务异常必须使用已登记的 `ErrorCode`。
- 新增业务异常点必须先更新异常码表和测试。
- 不要在 route 中直接写复杂业务逻辑。
- 不要让测试访问真实网络或真实 AI。
- 不要把 API key、token、完整堆栈返回给前端。
- 开发默认使用 `data/`，但代码必须支持环境变量覆盖路径。
