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
