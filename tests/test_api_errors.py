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
