from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.settings import AppSettings
from src.models import ContentItem, SourceType


def settings(tmp_path):
    data_dir = tmp_path / "data"
    return AppSettings(data_dir, data_dir / "horizon.db", data_dir / "config.json", "127.0.0.1", 8765)


def item(item_id: str, title: str, score: float, tags: list[str]):
    return ContentItem(
        id=item_id,
        source_type=SourceType.RSS,
        title=title,
        url=f"https://example.com/{item_id.replace(':', '-')}",
        content=f"Body for {title}",
        author="Alice",
        published_at=datetime(2026, 5, 9, tzinfo=timezone.utc),
        ai_score=score,
        ai_reason="Useful",
        ai_summary=f"Summary for {title}",
        ai_tags=tags,
        metadata={"feed_name": "Example Feed"},
    )


def seed(app):
    app.state.store.create_run("run-1", hours=24, config_snapshot={})
    app.state.store.save_items(
        "run-1",
        [
            item("rss:1", "AI infrastructure", 8.5, ["ai", "infra"]),
            item("rss:2", "Frontend release", 7.5, ["frontend"]),
        ],
        stage="filtered",
        selected=True,
    )


def test_report_generation_uses_explicit_item_ids(tmp_path):
    app = create_app(settings(tmp_path))
    seed(app)
    app.state.writing_service = FakeWritingService(markdown="# Report")
    client = TestClient(app)

    response = client.post(
        "/write/report",
        json={
            "time_range": "custom",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "style": "professional",
            "language": "zh",
            "item_ids": ["rss:2"],
            "length": "brief",
            "custom_prompt": "强调工程影响",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["item_count"] == 1
    assert data["markdown"] == "# Report"
    sent_items = app.state.writing_service.report_calls[0][0]
    assert [item["id"] for item in sent_items] == ["rss:2"]


def test_blog_compile_generation_accepts_item_ids_without_single_item_id(tmp_path):
    app = create_app(settings(tmp_path))
    seed(app)
    app.state.writing_service = FakeWritingService(markdown="# Compile")
    client = TestClient(app)

    response = client.post(
        "/write/blog-draft",
        json={
            "item_ids": ["rss:1", "rss:2"],
            "compile_mode": True,
            "style": "analysis",
            "language": "zh",
            "length": "medium",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["markdown"] == "# Compile"
    sent_items, _params, compile_mode = app.state.writing_service.blog_calls[0]
    assert [item["id"] for item in sent_items] == ["rss:1", "rss:2"]
    assert compile_mode is True
    assert data["references"] == [
        "https://example.com/rss-1",
        "https://example.com/rss-2",
    ]


class FakeWritingService:
    def __init__(self, *, markdown="# AI generated", error: Exception | None = None):
        self.markdown = markdown
        self.error = error
        self.report_calls = []
        self.blog_calls = []

    async def compose_report(self, items, params):
        self.report_calls.append((items, params))
        if self.error:
            raise self.error
        return self.markdown

    async def compose_blog(self, items, params, compile_mode=False):
        self.blog_calls.append((items, params, compile_mode))
        if self.error:
            raise self.error
        return self.markdown

    async def suggest_titles(self, items, style):
        return ["AI title", "Second title", "Third title"]


def test_report_generation_uses_writing_service_instead_of_template(tmp_path):
    app = create_app(settings(tmp_path))
    seed(app)
    app.state.writing_service = FakeWritingService(markdown="# AI-only report")
    client = TestClient(app)

    response = client.post(
        "/write/report",
        json={
            "time_range": "custom",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "style": "professional",
            "language": "zh",
            "item_ids": ["rss:1"],
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["markdown"] == "# AI-only report"
    assert len(app.state.writing_service.report_calls) == 1


def test_writing_service_failure_returns_actionable_500(tmp_path):
    app = create_app(settings(tmp_path))
    seed(app)
    app.state.writing_service = FakeWritingService(error=RuntimeError("model unavailable"))
    client = TestClient(app)

    response = client.post(
        "/write/report",
        json={
            "time_range": "custom",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "style": "professional",
            "language": "zh",
            "item_ids": ["rss:1"],
        },
    )

    assert response.status_code == 500
    assert response.json()["success"] is False
    assert response.json()["errorCode"] == 50001
    assert "请检查 AI 配置" in response.json()["errorMessage"]
