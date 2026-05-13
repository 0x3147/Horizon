from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from src.ai.writer import WritingService, build_writing_ai_config
from src.api.schemas import BlogDraftRequest, ReportGenerateRequest
from src.models import AIConfig, AIProvider


class FakeAIClient:
    def __init__(self, response: str = "# Generated"):
        self.response = response
        self.calls: list[dict] = []

    async def complete(
        self,
        system: str,
        user: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: str = "json",
    ) -> str:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": response_format,
            }
        )
        return self.response


def item(**overrides):
    data = {
        "id": "rss:1",
        "title": "AI infrastructure",
        "url": "https://example.com/ai",
        "source_type": "rss",
        "published_at": datetime(2026, 5, 13, tzinfo=timezone.utc).isoformat(),
        "ai_score": 8.5,
        "ai_summary": "Summary",
        "ai_tags": ["ai", "infra"],
        "content": "Full article body should not be sent in MVP prompts.",
        "detailed_summary": {"zh": "Detailed summary"},
        "background": {"text": "Background text"},
    }
    data.update(overrides)
    return data


def test_report_composition_calls_ai_for_markdown_without_full_content():
    ai = FakeAIClient("# AI report")
    service = WritingService(ai)

    result = asyncio.run(
        service.compose_report(
            [item()],
            ReportGenerateRequest(
                time_range="today",
                style="professional",
                language="zh",
                length="brief",
                custom_prompt="强调工程影响",
            ),
        )
    )

    assert result == "# AI report"
    assert ai.calls[0]["response_format"] == "text"
    assert ai.calls[0]["max_tokens"] == 900
    assert "AI infrastructure" in ai.calls[0]["user"]
    assert "Full article body should not be sent" not in ai.calls[0]["user"]
    assert "强调工程影响" in ai.calls[0]["user"]


def test_blog_compile_composition_uses_compile_prompt_and_deep_context():
    ai = FakeAIClient("# Compile blog")
    service = WritingService(ai)

    result = asyncio.run(
        service.compose_blog(
            [item(), item(id="rss:2", title="Frontend release", url="https://example.com/frontend")],
            BlogDraftRequest(
                item_ids=["rss:1", "rss:2"],
                compile_mode=True,
                style="analysis",
                language="en",
                length="deep",
            ),
            compile_mode=True,
        )
    )

    assert result == "# Compile blog"
    assert ai.calls[0]["response_format"] == "text"
    assert ai.calls[0]["max_tokens"] == 3600
    assert "common theme" in ai.calls[0]["user"].lower()
    assert "Detailed summary" in ai.calls[0]["user"]
    assert "Background text" in ai.calls[0]["user"]


def test_build_writing_ai_config_prefers_writing_overrides():
    config = AIConfig(
        provider=AIProvider.OPENAI,
        model="gpt-4.1-mini",
        api_key="score-key",
        api_key_env="OPENAI_API_KEY",
        writing_provider=AIProvider.ANTHROPIC,
        writing_model="claude-sonnet-4.5",
        writing_api_key="write-key",
        writing_api_key_env="ANTHROPIC_API_KEY",
    )

    writing_config = build_writing_ai_config(config)

    assert writing_config.provider == AIProvider.ANTHROPIC
    assert writing_config.model == "claude-sonnet-4.5"
    assert writing_config.api_key == "write-key"
    assert writing_config.api_key_env == "ANTHROPIC_API_KEY"
