from fastapi import APIRouter, Request

from src.api.schemas import ok
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


@router.post("/validate-cron")
def validate_cron(payload: dict, request: Request) -> dict:
    result = service(request).validate_cron(payload["cron_expr"], payload["timezone"])
    return ok(result)


@router.post("", status_code=201)
def create_schedule(payload: dict, request: Request) -> dict:
    schedule = service(request).create_schedule(
        name=payload["name"],
        cron_expr=payload["cron_expr"],
        timezone_name=payload["timezone"],
        hours_window=payload.get("hours_window", 24),
        cron_label=payload.get("cron_label"),
        enabled=payload.get("enabled", True),
    )
    return ok(schedule, code=201)


@router.get("")
def list_schedules(request: Request) -> dict:
    return ok({"items": store(request).list_schedules()})


@router.delete("/{schedule_id}")
def delete_schedule(schedule_id: str, request: Request) -> dict:
    deleted = store(request).delete_schedule(schedule_id)
    if not deleted:
        raise HorizonApiError(ErrorCode.SCHEDULE_NOT_FOUND, "Schedule not found")
    return ok({"deleted": True})
