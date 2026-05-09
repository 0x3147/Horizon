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
