from typing import Any

from fastapi import APIRouter, Body, Request

from src.api.schemas import ApiResponse, ConfigValidationData, ok
from src.core.config_service import ConfigService
from src.models import Config

router = APIRouter(prefix="/config", tags=["config"])

CONFIG_REQUEST_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/Config"},
            }
        },
    }
}


def service(request: Request) -> ConfigService:
    return ConfigService(request.app.state.settings.config_path)


@router.get(
    "",
    response_model=ApiResponse[Config],
    summary="Get current config",
)
def get_config(request: Request) -> dict:
    return ok(service(request).get_config().model_dump(mode="json"))


@router.post(
    "",
    response_model=ApiResponse[Config],
    summary="Save current config",
    openapi_extra=CONFIG_REQUEST_BODY,
)
def post_config(request: Request, payload: dict[str, Any] = Body(...)) -> dict:
    return ok(service(request).save_config(payload).model_dump(mode="json"))


@router.post(
    "/validate",
    response_model=ApiResponse[ConfigValidationData],
    summary="Validate config without saving",
    openapi_extra=CONFIG_REQUEST_BODY,
)
def validate_config(request: Request, payload: dict[str, Any] = Body(...)) -> dict:
    config = service(request).validate_config(payload)
    return ok({"valid": True, "config": config.model_dump(mode="json")})
