from fastapi import APIRouter, Request

from src.api.schemas import ok
from src.core.errors import ErrorCode, HorizonApiError

router = APIRouter(prefix="/items", tags=["items"])


@router.get("")
def list_items(
    request: Request,
    run_id: str | None = None,
    source_type: str | None = None,
    min_score: float | None = None,
    max_score: float | None = None,
    selected_only: bool = False,
    stage: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    items = request.app.state.store.query_items(
        run_id=run_id,
        source_type=source_type,
        min_score=min_score,
        max_score=max_score,
        selected_only=selected_only,
        stage=stage,
        tag=tag,
        q=q,
        limit=limit,
        offset=offset,
    )
    return ok({"items": items})


@router.get("/{item_id}")
def get_item(item_id: str, request: Request, run_id: str | None = None) -> dict:
    item = request.app.state.store.get_item(item_id, run_id=run_id)
    if item is None:
        raise HorizonApiError(ErrorCode.ITEM_NOT_FOUND, "Item not found")
    return ok(item)
