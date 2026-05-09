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
