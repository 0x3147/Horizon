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
