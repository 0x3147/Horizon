from fastapi import APIRouter, Request

from src.api.schemas import ok

router = APIRouter(tags=["summaries"])


@router.get("/summaries")
def list_summaries(request: Request, limit: int = 50, offset: int = 0) -> dict:
    return ok({"items": request.app.state.store.list_summaries(limit=limit, offset=offset)})


@router.get("/runs/{run_id}/summaries")
def list_run_summaries(run_id: str, request: Request, limit: int = 50, offset: int = 0) -> dict:
    return ok({"items": request.app.state.store.list_summaries(run_id=run_id, limit=limit, offset=offset)})
