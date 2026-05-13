"""LLM-backed writing service for reports and blog drafts."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.ai.client import AIClient, create_ai_client
from src.ai.prompts import (
    BLOG_COMPILE_USER_PROMPT_TEMPLATE,
    BLOG_SYSTEM_PROMPT,
    BLOG_USER_PROMPT_TEMPLATE,
    REPORT_SYSTEM_PROMPT,
    REPORT_USER_PROMPT_TEMPLATE,
)
from src.models import AIConfig


MAX_WRITING_ITEMS = 30

LENGTH_LABELS = {
    "brief": "简短（约 300 字）",
    "medium": "中等长度（约 800 字）",
    "deep": "深度（约 2000 字以上）",
}

LENGTH_TOKENS = {
    "brief": 900,
    "medium": 1800,
    "deep": 3600,
}

REPORT_STYLE_LABELS = {
    "professional": "专业",
    "casual": "轻松",
    "data_driven": "数据驱动",
}

BLOG_STYLE_LABELS = {
    "in_depth": "深度解析",
    "analysis": "行业分析",
    "brief": "快讯",
}

TIME_RANGE_LABELS = {
    "today": "今日",
    "yesterday": "昨日",
    "this_week": "本周",
    "last_week": "上周",
    "custom": "自定义时间段",
}

LANGUAGE_LABELS = {
    "zh": "简体中文",
    "en": "English",
}


@dataclass(frozen=True)
class WritingPrompts:
    report_system: str = REPORT_SYSTEM_PROMPT
    report_user_template: str = REPORT_USER_PROMPT_TEMPLATE
    blog_system: str = BLOG_SYSTEM_PROMPT
    blog_user_template: str = BLOG_USER_PROMPT_TEMPLATE
    blog_compile_user_template: str = BLOG_COMPILE_USER_PROMPT_TEMPLATE


def build_writing_ai_config(config: AIConfig) -> AIConfig:
    """Return an AIConfig for writing, falling back to the primary AI config."""
    return config.model_copy(
        update={
            "provider": config.writing_provider or config.provider,
            "model": config.writing_model or config.model,
            "api_key": config.writing_api_key or config.api_key,
            "api_key_env": config.writing_api_key_env or config.api_key_env,
        }
    )


def create_writing_service(config: AIConfig) -> "WritingService":
    return WritingService(create_ai_client(build_writing_ai_config(config)))


class WritingService:
    def __init__(self, ai_client: AIClient, prompts: WritingPrompts | None = None):
        self.ai = ai_client
        self.prompts = prompts or WritingPrompts()

    async def compose_report(self, items: list[dict], params: Any) -> str:
        item_payloads = _compact_items(items, include_deep_context=getattr(params, "length", "medium") == "deep")
        user_prompt = self.prompts.report_user_template.format(
            item_count=len(item_payloads),
            length_label=_length_label(getattr(params, "length", "medium")),
            style_label=REPORT_STYLE_LABELS.get(getattr(params, "style", ""), getattr(params, "style", "专业")),
            time_range_label=TIME_RANGE_LABELS.get(getattr(params, "time_range", ""), getattr(params, "time_range", "今日")),
            language_label=LANGUAGE_LABELS.get(getattr(params, "language", ""), getattr(params, "language", "简体中文")),
            custom_prompt_block=_custom_prompt_block(getattr(params, "custom_prompt", None)),
            items_json=_json(item_payloads),
        )

        return await self.ai.complete(
            system=self.prompts.report_system,
            user=user_prompt,
            max_tokens=_max_tokens(getattr(params, "length", "medium")),
            response_format="text",
        )

    async def compose_blog(self, items: list[dict], params: Any, compile_mode: bool = False) -> str:
        item_payloads = _compact_items(items, include_deep_context=getattr(params, "length", "medium") == "deep")
        template = self.prompts.blog_compile_user_template if compile_mode else self.prompts.blog_user_template
        user_prompt = template.format(
            item_count=len(item_payloads),
            length_label=_length_label(getattr(params, "length", "medium")),
            style_label=BLOG_STYLE_LABELS.get(getattr(params, "style", ""), getattr(params, "style", "深度解析")),
            language_label=LANGUAGE_LABELS.get(getattr(params, "language", ""), getattr(params, "language", "简体中文")),
            custom_prompt_block=_custom_prompt_block(getattr(params, "custom_prompt", None)),
            items_json=_json(item_payloads if compile_mode else item_payloads[:1]),
        )

        return await self.ai.complete(
            system=self.prompts.blog_system,
            user=user_prompt,
            max_tokens=_max_tokens(getattr(params, "length", "medium")),
            response_format="text",
        )

    async def suggest_titles(self, items: list[dict], style: str) -> list[str]:
        if not items:
            return ["Horizon 写作草稿"]

        first_title = items[0].get("title") or "Horizon 写作草稿"
        if len(items) == 1:
            prefix = BLOG_STYLE_LABELS.get(style, "")
            return [
                f"{prefix}：{first_title}" if prefix else first_title,
                f"{first_title} 的关键影响",
                f"为什么要关注 {first_title}",
            ]

        return [
            f"{first_title} 等 {len(items)} 条动态",
            "本期技术趋势汇编",
            "值得关注的技术信号",
        ]


def _compact_items(items: list[dict], include_deep_context: bool = False) -> list[dict[str, Any]]:
    compacted = []
    for item in items[:MAX_WRITING_ITEMS]:
        payload: dict[str, Any] = {
            "title": item.get("title"),
            "url": item.get("url"),
            "source_type": item.get("source_type"),
            "score": item.get("ai_score"),
            "ai_summary": item.get("ai_summary"),
            "ai_tags": item.get("ai_tags") or [],
            "published_at": item.get("published_at"),
        }

        if include_deep_context:
            detailed = item.get("detailed_summary") or item.get("metadata", {}).get("detailed_summary")
            background = item.get("background") or item.get("metadata", {}).get("background")
            if detailed:
                payload["detailed_summary"] = detailed
            if background:
                payload["background"] = background

        compacted.append(payload)
    return compacted


def _custom_prompt_block(custom_prompt: str | None) -> str:
    if not custom_prompt:
        return ""
    return f"\nAdditional user requirements:\n{custom_prompt.strip()}\n"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _length_label(length: str | None) -> str:
    return LENGTH_LABELS.get(length or "medium", LENGTH_LABELS["medium"])


def _max_tokens(length: str | None) -> int:
    return LENGTH_TOKENS.get(length or "medium", LENGTH_TOKENS["medium"])
