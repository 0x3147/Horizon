from fastapi import APIRouter, Query, Request

from src.api.schemas import ApiResponse, SummaryListData, ok

router = APIRouter(tags=["summaries"])


@router.get(
    "/summaries",
    response_model=ApiResponse[SummaryListData],
    summary="List summaries",
)
def list_summaries(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200, description="Maximum summaries to return."),
    offset: int = Query(default=0, ge=0, description="Number of summaries to skip."),
) -> dict:
    return ok({"items": request.app.state.store.list_summaries(limit=limit, offset=offset)})


@router.get(
    "/runs/{run_id}/summaries",
    response_model=ApiResponse[SummaryListData],
    summary="List summaries for a run",
)
def list_run_summaries(
    run_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200, description="Maximum summaries to return."),
    offset: int = Query(default=0, ge=0, description="Number of summaries to skip."),
) -> dict:
    return ok({"items": request.app.state.store.list_summaries(run_id=run_id, limit=limit, offset=offset)})
