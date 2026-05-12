from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from src.models import Config

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(description="HTTP status code mirrored in the response body.")
    success: bool = Field(description="Whether the business operation succeeded.")
    data: T | None = None
    errorCode: int | None = Field(default=None, description="Business error code. Null on success.")
    errorMessage: str | None = Field(default=None, description="Business error message. Null on success.")


class HealthData(BaseModel):
    status: str = Field(description="Service health status.", examples=["ok"])


class ConfigValidationData(BaseModel):
    valid: bool = Field(description="Whether the submitted config is valid.", examples=[True])
    config: Config


class RunStartRequest(BaseModel):
    hours: int = Field(
        default=24,
        ge=1,
        le=720,
        description="Lookback window in hours for the pipeline run.",
        examples=[24],
    )


class RunAcceptedData(BaseModel):
    run_id: str = Field(description="Created run id.", examples=["run-abc123"])
    status: str = Field(description="Accepted task status.", examples=["accepted"])


class RunData(BaseModel):
    id: str
    status: str
    hours: int
    started_at: str | None = None
    finished_at: str | None = None
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    raw_count: int = 0
    scored_count: int = 0
    filtered_count: int = 0
    enriched_count: int = 0
    error_message: str | None = None


class RunListData(BaseModel):
    items: list[RunData]


class RunCancelData(BaseModel):
    run_id: str
    cancel_requested: bool


class RunLogData(BaseModel):
    id: int
    run_id: str | None = None
    level: str
    stage: str | None = None
    message: str
    created_at: str


class RunLogListData(BaseModel):
    items: list[RunLogData]


class ItemData(BaseModel):
    id: str
    run_id: str
    source_type: str
    source_name: str | None = None
    native_id: str | None = None
    title: str
    url: str
    content: str | None = None
    author: str | None = None
    published_at: str | None = None
    fetched_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    stage: str
    is_selected: bool
    duplicate_of_item_id: str | None = None
    ai_score: float | None = None
    ai_reason: str | None = None
    ai_summary: str | None = None
    ai_tags: list[str] = Field(default_factory=list)
    detailed_summary: dict[str, Any] = Field(default_factory=dict)
    background: dict[str, Any] = Field(default_factory=dict)
    community_discussion: dict[str, Any] = Field(default_factory=dict)
    citations: list[Any] = Field(default_factory=list)


class ItemListData(BaseModel):
    items: list[ItemData]


class SummaryData(BaseModel):
    id: str
    run_id: str
    language: str
    markdown: str
    saved_path: str | None = None
    created_at: str


class SummaryListData(BaseModel):
    items: list[SummaryData]


class CronValidationRequest(BaseModel):
    cron_expr: str = Field(description="Standard 5-field cron expression.", examples=["0 8 * * *"])
    timezone: str = Field(description="IANA timezone name.", examples=["Asia/Shanghai"])


class CronValidationData(BaseModel):
    valid: bool
    next_run_at: str | None = None


class ScheduleCreateRequest(CronValidationRequest):
    name: str = Field(description="Human-readable schedule name.", examples=["Daily report"])
    hours_window: int = Field(default=24, ge=1, le=720, description="Pipeline lookback window in hours.")
    cron_label: str | None = Field(default=None, description="Optional UI label for the cron expression.")
    enabled: bool = Field(default=True, description="Whether the schedule is active.")


class ScheduleData(BaseModel):
    id: str
    name: str
    enabled: bool
    cron_expr: str
    cron_label: str | None = None
    timezone: str
    hours_window: int
    source_filter: dict[str, Any] = Field(default_factory=dict)
    last_run_id: str | None = None
    last_run_at: str | None = None
    next_run_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ScheduleListData(BaseModel):
    items: list[ScheduleData]


class DeleteResultData(BaseModel):
    deleted: bool


# ===================== Writing API Schemas =====================

class ReportGenerateRequest(BaseModel):
    """生成日报/周报请求"""
    time_range: str = Field(
        default="today",
        description="时间范围: 'today' | 'yesterday' | 'this_week' | 'last_week' | 'custom'",
        examples=["today", "this_week"],
    )
    start_date: str | None = Field(
        default=None,
        description="自定义起始日期 (ISO 格式), time_range='custom' 时必需",
        examples=["2026-05-10"],
    )
    end_date: str | None = Field(
        default=None,
        description="自定义结束日期 (ISO 格式), time_range='custom' 时必需",
        examples=["2026-05-12"],
    )
    domains: list[str] | None = Field(
        default=None,
        description="关注的领域列表, 为空则使用用户配置的所有领域",
        examples=[["ai", "frontend"]],
    )
    style: str = Field(
        default="professional",
        description="报告风格: 'professional' | 'casual' | 'data_driven'",
        examples=["professional"],
    )
    language: str = Field(
        default="zh",
        description="输出语言: 'zh' | 'en'",
        examples=["zh"],
    )


class ReportGenerateResponse(BaseModel):
    """日报/周报生成结果"""
    markdown: str = Field(description="生成的 Markdown 报告内容")
    title: str = Field(description="报告标题")
    item_count: int = Field(description="报告中包含的条目数")
    generated_at: str = Field(description="生成时间 ISO 格式")


class BlogDraftRequest(BaseModel):
    """生成博文草稿请求"""
    item_id: str = Field(description="基于哪条新闻生成博文")
    run_id: str | None = Field(
        default=None, description="所属 run_id, 不传则查最新 run"
    )
    style: str = Field(
        default="in_depth",
        description="博文风格: 'in_depth' | 'analysis' | 'brief'",
        examples=["in_depth"],
    )
    language: str = Field(
        default="zh",
        description="输出语言: 'zh' | 'en'",
    )


class BlogDraftResponse(BaseModel):
    """博文草稿生成结果"""
    markdown: str = Field(description="生成的 Markdown 博文草稿")
    title_suggestions: list[str] = Field(description="标题建议列表")
    references: list[str] = Field(description="引用的来源 URL 列表")
    generated_at: str = Field(description="生成时间 ISO 格式")


# ===================== Domain / Tag Schemas =====================

class DomainInfo(BaseModel):
    """领域定义"""
    id: str = Field(description="领域唯一标识", examples=["ai"])
    label: str = Field(description="领域显示名称", examples=["AI与大数据"])
    keywords: list[str] = Field(
        description="匹配关键词列表",
        examples=[["machine learning", "LLM", "GPT", "AI"]],
    )
    enabled: bool = Field(default=True, description="是否启用")


class DomainConfigData(BaseModel):
    """领域配置"""
    domains: list[DomainInfo] = Field(description="所有领域定义")


# ===================== Bookmark Schemas (第一期定义，第二期实现) =====================

class BookmarkCreateRequest(BaseModel):
    """收藏文章请求"""
    item_id: str = Field(description="要收藏的内容条目 ID")
    run_id: str | None = Field(default=None, description="所属 run_id")


class BookmarkData(BaseModel):
    """收藏条目数据"""
    id: str = Field(description="收藏记录 ID")
    item_id: str = Field(description="内容条目 ID")
    title: str = Field(description="文章标题")
    url: str = Field(description="文章 URL")
    source_type: str = Field(description="来源类型")
    ai_summary: str | None = Field(default=None, description="AI 摘要")
    ai_tags: list[str] | None = Field(default=None, description="AI 标签")
    note: str | None = Field(default=None, description="用户笔记")
    bookmarked_at: str = Field(description="收藏时间 ISO 格式")


class BookmarkNoteRequest(BaseModel):
    """给收藏添加笔记"""
    note: str = Field(description="笔记内容")


def ok(data: T, code: int = 200) -> dict:
    return ApiResponse[T](
        code=code,
        success=True,
        data=data,
        errorCode=None,
        errorMessage=None,
    ).model_dump()


def fail(code: int, error_code: int, message: str) -> dict:
    return ApiResponse[None](
        code=code,
        success=False,
        data=None,
        errorCode=error_code,
        errorMessage=message,
    ).model_dump()
