from fastapi import APIRouter, Request

from src.api.schemas import (
    ApiResponse,
    CronValidationData,
    CronValidationRequest,
    DeleteResultData,
    ScheduleCreateRequest,
    ScheduleData,
    ScheduleListData,
    ok,
)
from src.core.errors import ErrorCode, HorizonApiError
from src.core.schedule_service import ScheduleService
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(prefix="/schedules", tags=["schedules"])


def store(request: Request) -> SQLiteStore:
    existing = getattr(request.app.state, "store", None)
    if existing is not None:
        return existing
    sqlite_store = SQLiteStore(request.app.state.settings.db_path)
    sqlite_store.initialize()
    return sqlite_store


def service(request: Request) -> ScheduleService:
    return ScheduleService(store(request))


@router.post(
    "/validate-cron",
    response_model=ApiResponse[CronValidationData],
    summary="Validate a cron expression",
)
def validate_cron(payload: CronValidationRequest, request: Request) -> dict:
    result = service(request).validate_cron(payload.cron_expr, payload.timezone)
    return ok(result)


@router.post(
    "",
    status_code=201,
    response_model=ApiResponse[ScheduleData],
    summary="Create a schedule",
)
def create_schedule(payload: ScheduleCreateRequest, request: Request) -> dict:
    schedule = service(request).create_schedule(
        name=payload.name,
        cron_expr=payload.cron_expr,
        timezone_name=payload.timezone,
        hours_window=payload.hours_window,
        cron_label=payload.cron_label,
        enabled=payload.enabled,
    )
    return ok(schedule, code=201)


@router.get(
    "",
    response_model=ApiResponse[ScheduleListData],
    summary="List schedules",
)
def list_schedules(request: Request) -> dict:
    return ok({"items": store(request).list_schedules()})


@router.post(
    "/{schedule_id}/delete",
    response_model=ApiResponse[DeleteResultData],
    summary="Delete a schedule",
)
def delete_schedule(schedule_id: str, request: Request) -> dict:
    deleted = store(request).delete_schedule(schedule_id)
    if not deleted:
        raise HorizonApiError(ErrorCode.SCHEDULE_NOT_FOUND, "Schedule not found")
    return ok({"deleted": True})
