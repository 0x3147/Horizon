from uuid import uuid4

from fastapi import APIRouter, Body, Request

from src.api.schemas import ok
from src.core.errors import ErrorCode, HorizonApiError
from src.core.pipeline_service import PipelineService

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", status_code=202)
async def start_run(request: Request, payload: dict | None = Body(default=None)) -> dict:
    payload = payload or {}
    hours = int(payload.get("hours", 24))
    run_id = f"run-{uuid4().hex}"

    def coro_factory(cancel_event):
        pipeline = PipelineService(request.app.state.store, request.app.state.settings)
        return pipeline.run(run_id=run_id, hours=hours, cancel_event=cancel_event)

    try:
        request.app.state.task_manager.start(run_id, coro_factory)
    except ValueError as exc:
        raise HorizonApiError(ErrorCode.RUN_ALREADY_IN_PROGRESS, str(exc)) from exc

    return ok({"run_id": run_id, "status": "accepted"}, code=202)


@router.get("")
def list_runs(request: Request, limit: int = 20, offset: int = 0) -> dict:
    return ok({"items": request.app.state.store.list_runs(limit=limit, offset=offset)})


@router.get("/{run_id}")
def get_run(run_id: str, request: Request) -> dict:
    run = request.app.state.store.get_run(run_id)
    if run is None:
        raise HorizonApiError(ErrorCode.RUN_NOT_FOUND, "Run not found")
    return ok(run)


@router.post("/{run_id}/cancel")
def cancel_run(run_id: str, request: Request) -> dict:
    cancel_requested = request.app.state.task_manager.cancel(run_id)
    return ok({"run_id": run_id, "cancel_requested": cancel_requested})


@router.get("/{run_id}/logs")
def list_run_logs(run_id: str, request: Request, limit: int = 200, offset: int = 0) -> dict:
    return ok({"items": request.app.state.store.list_logs(run_id, limit=limit, offset=offset)})
