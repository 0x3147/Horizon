"""Writing API routes -- report generation and blog draft creation."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request

from src.ai.writer import create_writing_service
from src.api.schemas import (
    ApiResponse,
    BlogDraftRequest,
    BlogDraftResponse,
    ReportGenerateRequest,
    ReportGenerateResponse,
    fail,
    ok,
)
from src.core.config_service import ConfigService
from src.core.errors import ErrorCode, HorizonApiError

router = APIRouter(prefix="/write", tags=["writing"])


@router.post("/report", response_model=ApiResponse[ReportGenerateResponse])
async def generate_report(
    payload: ReportGenerateRequest,
    request: Request,
) -> dict:
    """Generate a daily or weekly report from collected items."""
    store = request.app.state.store
    settings = request.app.state.settings

    now = datetime.now(timezone.utc)

    # Resolve time window
    if payload.time_range == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif payload.time_range == "yesterday":
        yesterday = now - timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif payload.time_range == "this_week":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif payload.time_range == "last_week":
        this_monday = now - timedelta(days=now.weekday())
        start = this_monday - timedelta(days=7)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    elif payload.time_range == "custom":
        if not payload.start_date or not payload.end_date:
            return fail(400, 40001, "custom time_range requires start_date and end_date")
        start = _parse_datetime(payload.start_date)
        end = _parse_datetime(payload.end_date)
    else:
        return fail(400, 40002, f"Unknown time_range: {payload.time_range}")

    if payload.item_ids:
        items = _items_by_ids(store, payload.item_ids)
    else:
        # Fetch selected items; store.query_items lacks native date filtering so we filter in Python
        items = store.query_items(selected_only=True, limit=200)
        items = _filter_by_date(items, start, end)

    # Filter by domains if specified
    if payload.domains:
        domain_keywords: dict[str, list[str]] = {}
        config_path = settings.config_path
        if config_path.exists():
            config_raw = json.loads(config_path.read_text(encoding="utf-8"))
            for domain in config_raw.get("domains", []):
                if domain.get("enabled", True) is False:
                    continue
                domain_id = domain.get("id")
                if domain_id:
                    domain_keywords[domain_id] = domain.get("keywords", [])

        allowed_keywords: set[str] = set()
        for domain_id in payload.domains:
            allowed_keywords.update(domain_keywords.get(domain_id, []))

        if allowed_keywords:
            filtered = []
            for item in items:
                item_tags = set((t or "").lower() for t in (item.get("ai_tags") or []))
                item_text = f"{item.get('title', '')} {item.get('ai_summary', '')}".lower()
                if any(kw.lower() in item_text for kw in allowed_keywords) or \
                   item_tags & {kw.lower() for kw in allowed_keywords}:
                    filtered.append(item)
            items = filtered

    if not items:
        return ok(
            ReportGenerateResponse(
                markdown=f"# {_report_title(payload)}\n\n暂无相关内容。",
                title=_report_title(payload),
                item_count=0,
                generated_at=now.isoformat(),
            )
        )

    try:
        markdown = await _get_writing_service(request).compose_report(items, payload)
    except Exception as exc:
        raise _writing_generation_error(exc) from exc

    return ok(
        ReportGenerateResponse(
            markdown=markdown,
            title=_report_title(payload),
            item_count=len(items),
            generated_at=now.isoformat(),
        )
    )


@router.post("/blog-draft", response_model=ApiResponse[BlogDraftResponse])
async def generate_blog_draft(payload: BlogDraftRequest, request: Request) -> dict:
    """Generate a blog post draft from a specific news item."""
    store = request.app.state.store

    if payload.compile_mode:
        if not payload.item_ids:
            return fail(400, 40003, "compile_mode requires item_ids")
        items = _items_by_ids(store, payload.item_ids, run_id=payload.run_id)
        missing = [item_id for item_id in payload.item_ids if not any(i.get("id") == item_id for i in items)]
        if missing:
            return fail(404, 40401, f"Items not found: {', '.join(missing)}")
        try:
            writing_service = _get_writing_service(request)
            draft = await writing_service.compose_blog(items, payload, compile_mode=True)
            suggestions = _extract_title_suggestions(draft) or await writing_service.suggest_titles(items, payload.style)
        except Exception as exc:
            raise _writing_generation_error(exc) from exc
        return ok(
            BlogDraftResponse(
                markdown=draft,
                title_suggestions=suggestions,
                references=[item.get("url", "") for item in items if item.get("url")],
                generated_at=datetime.now(timezone.utc).isoformat(),
            )
        )

    if not payload.item_id:
        return fail(400, 40004, "item_id is required when compile_mode is false")

    item = store.get_item(payload.item_id, run_id=payload.run_id)
    if not item:
        return fail(404, 40401, f"Item {payload.item_id} not found")

    url = item.get("url", "")

    try:
        writing_service = _get_writing_service(request)
        draft = await writing_service.compose_blog([item], payload, compile_mode=False)
        suggestions = _extract_title_suggestions(draft) or await writing_service.suggest_titles([item], payload.style)
    except Exception as exc:
        raise _writing_generation_error(exc) from exc

    return ok(
        BlogDraftResponse(
            markdown=draft,
            title_suggestions=suggestions,
            references=[url] if url else [],
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
    )


# ---- helpers ----


def _report_title(request: ReportGenerateRequest) -> str:
    """Generate report title based on request params."""
    time_labels = {
        "today": "今日",
        "yesterday": "昨日",
        "this_week": "本周",
        "last_week": "上周",
        "custom": "自定义",
    }
    time_label = time_labels.get(request.time_range, request.time_range)
    style_labels = {
        "professional": "技术动态",
        "casual": "行业速览",
        "data_driven": "数据观察",
    }
    style_label = style_labels.get(request.style, request.style)
    return f"{time_label}{style_label}"


def _get_writing_service(request: Request):
    injected = getattr(request.app.state, "writing_service", None)
    if injected is not None:
        return injected

    config = ConfigService(request.app.state.config_path).get_config()
    return create_writing_service(config.ai)


def _writing_generation_error(exc: Exception) -> HorizonApiError:
    message = f"生成失败：{exc}。请检查 AI 配置 → 工作台模型后重试。"
    return HorizonApiError(ErrorCode.WRITING_GENERATION_FAILED, message, http_status=500)


def _extract_title_suggestions(markdown: str) -> list[str]:
    match = re.search(r"<!--\s*titles:\s*(\[.*?\])\s*-->", markdown, flags=re.DOTALL)
    if not match:
        return []

    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, list):
        return []
    return [str(title).strip() for title in parsed if str(title).strip()][:3]


def _items_by_ids(store, item_ids: list[str], run_id: str | None = None) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for item_id in item_ids:
        if item_id in seen:
            continue
        seen.add(item_id)
        item = store.get_item(item_id, run_id=run_id)
        if item:
            items.append(item)
    return items


def _filter_by_date(items: list[dict], start: datetime, end: datetime) -> list[dict]:
    """Client-side date filter since query_items lacks start_date/end_date params."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    result: list[dict] = []
    for item in items:
        pub_str = item.get("published_at")
        if pub_str:
            try:
                pub_date = datetime.fromisoformat(str(pub_str).replace("Z", "+00:00"))
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)
                if start <= pub_date <= end:
                    result.append(item)
            except (ValueError, TypeError):
                # Keep items whose date we cannot parse
                result.append(item)
        else:
            # Keep items without a published date
            result.append(item)
    return result


def _parse_datetime(value: str) -> datetime:
    """Parse an ISO date/datetime string, defaulting to UTC if naive."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
