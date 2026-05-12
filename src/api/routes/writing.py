"""Writing API routes -- report generation and blog draft creation."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request

from src.api.schemas import (
    ApiResponse,
    BlogDraftRequest,
    BlogDraftResponse,
    ReportGenerateRequest,
    ReportGenerateResponse,
    fail,
    ok,
)

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
                domain_keywords[domain["id"]] = domain.get("keywords", [])

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

    markdown = _build_report_markdown(items, payload, start, end)
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

    item = store.get_item(payload.item_id, run_id=payload.run_id)
    if not item:
        return fail(404, 40401, f"Item {payload.item_id} not found")

    title = item.get("title", "未命名")
    summary = item.get("ai_summary", "")
    tags = item.get("ai_tags", [])
    url = item.get("url", "")
    source = item.get("source_type", "")

    draft = _build_blog_draft(title, summary, tags, url, source, payload.style)
    suggestions = _suggest_titles(title, payload.style)

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


def _build_report_markdown(
    items: list[dict],
    request: ReportGenerateRequest,
    start: datetime,
    end: datetime,
) -> str:
    """Build a Markdown report from items grouped by first AI tag."""
    title = _report_title(request)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    date_line = start_str if start_str == end_str else f"{start_str} ~ {end_str}"

    lines = [f"# {title}", "", f"> {date_line} | 共 {len(items)} 篇精选", ""]

    grouped: dict[str, list[dict]] = {}
    for item in items:
        tags = item.get("ai_tags") or []
        group_key = tags[0] if tags else "其他"
        grouped.setdefault(group_key, []).append(item)

    for tag, group_items in grouped.items():
        lines.append(f"## {tag}")
        lines.append("")
        for item in group_items:
            item_title = item.get("title", "未命名")
            item_url = item.get("url", "")
            item_summary = item.get("ai_summary", "")
            item_score = item.get("ai_score", 0)
            score_stars = "⭐" * min(5, max(1, int((item_score or 0) / 2)))
            source = item.get("source_type", "")

            lines.append(f"### {item_title}")
            if item_url:
                lines.append("")
                lines.append(f"[原文链接]({item_url}) | 来源: {source} | {score_stars}")
            if item_summary:
                lines.append("")
                lines.append(f"{item_summary}")
            lines.append("")

    return "\n".join(lines)


def _build_blog_draft(
    title: str,
    summary: str,
    tags: list[str],
    url: str,
    source: str,
    style: str,
) -> str:
    """Build a structured blog draft from item data."""
    lines = [
        f"# {title}",
        "",
        f"> 本文基于 Horizon 新闻雷达自动生成，原文来源：[{source}]({url})",
        "",
        "## 背景",
        "",
        summary or "暂无摘要信息。",
        "",
        "## 核心观点",
        "",
        "（在此处展开你的分析和观点）",
        "",
        "## 影响分析",
        "",
        "（分析该事件对行业的影响）",
        "",
        "## 参考来源",
        "",
        f"- [{title}]({url})",
        "",
    ]
    if tags:
        lines.append(f"标签: {' '.join('#' + t for t in tags)}")
        lines.append("")

    return "\n".join(lines)


def _suggest_titles(title: str, style: str) -> list[str]:
    """Suggest alternative titles for the blog post."""
    style_prefix = {
        "in_depth": "深度解析：",
        "analysis": "行业分析：",
        "brief": "快讯：",
    }
    prefix = style_prefix.get(style, "")
    return [
        f"{prefix}{title}",
        f"{title} — 你需要知道的一切",
        f"解读 {title}",
    ]


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
