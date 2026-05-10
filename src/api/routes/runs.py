from uuid import uuid4

from fastapi import APIRouter, Body, Query, Request

from src.api.schemas import (
    ApiResponse,
    RunAcceptedData,
    RunCancelData,
    RunData,
    RunListData,
    RunLogListData,
    RunStartRequest,
    ok,
)
from src.core.errors import ErrorCode, HorizonApiError
from src.core.pipeline_service import PipelineService

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post(
    "",
    status_code=202,
    response_model=ApiResponse[RunAcceptedData],
    summary="Start a pipeline run",
)
async def start_run(request: Request, payload: RunStartRequest | None = Body(default=None)) -> dict:
    payload = payload or RunStartRequest()
    hours = payload.hours
    run_id = f"run-{uuid4().hex}"

    def coro_factory(cancel_event):
        pipeline = PipelineService(request.app.state.store, request.app.state.settings)
        return pipeline.run(run_id=run_id, hours=hours, cancel_event=cancel_event)

    try:
        request.app.state.task_manager.start(run_id, coro_factory)
    except ValueError as exc:
        raise HorizonApiError(ErrorCode.RUN_ALREADY_IN_PROGRESS, str(exc)) from exc

    return ok({"run_id": run_id, "status": "accepted"}, code=202)


@router.get(
    "",
    response_model=ApiResponse[RunListData],
    summary="List pipeline runs",
)
def list_runs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200, description="Maximum runs to return."),
    offset: int = Query(default=0, ge=0, description="Number of runs to skip."),
) -> dict:
    return ok({"items": request.app.state.store.list_runs(limit=limit, offset=offset)})


@router.get(
    "/{run_id}",
    response_model=ApiResponse[RunData],
    summary="Get a pipeline run",
)
def get_run(run_id: str, request: Request) -> dict:
    run = request.app.state.store.get_run(run_id)
    if run is None:
        raise HorizonApiError(ErrorCode.RUN_NOT_FOUND, "Run not found")
    return ok(run)


@router.post(
    "/{run_id}/cancel",
    response_model=ApiResponse[RunCancelData],
    summary="Cancel a running pipeline run",
)
def cancel_run(run_id: str, request: Request) -> dict:
    cancel_requested = request.app.state.task_manager.cancel(run_id)
    return ok({"run_id": run_id, "cancel_requested": cancel_requested})


@router.get(
    "/{run_id}/logs",
    response_model=ApiResponse[RunLogListData],
    summary="List run logs",
)
def list_run_logs(
    run_id: str,
    request: Request,
    limit: int = Query(default=200, ge=1, le=500, description="Maximum logs to return."),
    offset: int = Query(default=0, ge=0, description="Number of logs to skip."),
) -> dict:
    return ok({"items": request.app.state.store.list_logs(run_id, limit=limit, offset=offset)})
