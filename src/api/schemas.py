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
