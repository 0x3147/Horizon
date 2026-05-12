import json

from fastapi import APIRouter, Query, Request

from src.api.schemas import ApiResponse, ItemData, ItemListData, ok
from src.core.errors import ErrorCode, HorizonApiError

router = APIRouter(prefix="/items", tags=["items"])


@router.get(
    "",
    response_model=ApiResponse[ItemListData],
    summary="List stored content items",
)
def list_items(
    request: Request,
    run_id: str | None = Query(default=None, description="Filter by run id."),
    source_type: str | None = Query(default=None, description="Filter by source type."),
    min_score: float | None = Query(default=None, ge=0, le=10, description="Minimum AI score."),
    max_score: float | None = Query(default=None, ge=0, le=10, description="Maximum AI score."),
    selected_only: bool = Query(default=False, description="Only return selected items."),
    stage: str | None = Query(default=None, description="Filter by pipeline stage."),
    tag: str | None = Query(default=None, description="Filter by AI tag."),
    q: str | None = Query(default=None, description="Search title, content, and AI summary."),
    domain: str | None = Query(default=None, description="Filter by domain (resolves to keyword matching)."),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum items to return."),
    offset: int = Query(default=0, ge=0, description="Number of items to skip."),
) -> dict:
    keywords = None
    if domain:
        config_path = request.app.state.config_path
        if config_path.exists():
            config = json.loads(config_path.read_text())
            for d in config.get("domains", []):
                if d.get("id") == domain:
                    keywords = d.get("keywords")
                    break
    items = request.app.state.store.query_items(
        run_id=run_id,
        source_type=source_type,
        min_score=min_score,
        max_score=max_score,
        selected_only=selected_only,
        stage=stage,
        tag=tag,
        q=q,
        keywords=keywords,
        limit=limit,
        offset=offset,
    )
    return ok({"items": items})


@router.get(
    "/{item_id}",
    response_model=ApiResponse[ItemData],
    summary="Get a content item",
)
def get_item(
    item_id: str,
    request: Request,
    run_id: str | None = Query(default=None, description="Optional run id for disambiguation."),
) -> dict:
    item = request.app.state.store.get_item(item_id, run_id=run_id)
    if item is None:
        raise HorizonApiError(ErrorCode.ITEM_NOT_FOUND, "Item not found")
    return ok(item)
