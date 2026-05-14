import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.settings import AppSettings
from src.models import ContentItem, SourceType


def settings(tmp_path):
    data_dir = tmp_path / "data"
    return AppSettings(data_dir, data_dir / "horizon.db", data_dir / "config.json", "127.0.0.1", 8765)


def item(item_id: str, title: str, score: float, tags: list[str], published_at: datetime | None = None):
    return ContentItem(
        id=item_id,
        source_type=SourceType.RSS,
        title=title,
        url=f"https://example.com/{item_id.replace(':', '-')}",
        content=f"Body for {title}",
        author="Alice",
        published_at=published_at or datetime(2026, 5, 9, tzinfo=timezone.utc),
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


def test_report_generation_without_item_ids_uses_full_date_range_query(tmp_path):
    app = create_app(settings(tmp_path))
    app.state.store.create_run("run-1", hours=168, config_snapshot={})
    selected_items = [
        item(
            f"rss:{index}",
            f"Today AI {index}",
            10 - index * 0.01,
            ["ai"],
            published_at=datetime(2026, 5, 9, 12, tzinfo=timezone.utc),
        )
        for index in range(201)
    ]
    app.state.store.save_items("run-1", selected_items, stage="filtered", selected=True)
    app.state.writing_service = FakeWritingService(markdown="# Auto Report")
    client = TestClient(app)

    response = client.post(
        "/write/report",
        json={
            "time_range": "custom",
            "start_date": "2026-05-09T00:00:00+00:00",
            "end_date": "2026-05-09T23:59:59+00:00",
            "style": "professional",
            "language": "zh",
            "length": "brief",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["item_count"] == 201
    sent_items = app.state.writing_service.report_calls[0][0]
    assert len(sent_items) == 201


def test_report_generation_uses_item_ids_as_directed_report(tmp_path):
    app = create_app(settings(tmp_path))
    seed(app)
    app.state.writing_service = FakeWritingService(markdown="# Directed Report")
    client = TestClient(app)

    response = client.post(
        "/write/report",
        json={
            "time_range": "today",
            "style": "professional",
            "language": "zh",
            "item_ids": ["rss:2"],
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["item_count"] == 1
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


def test_report_generation_persists_writing_artifact(tmp_path):
    app = create_app(settings(tmp_path))
    seed(app)
    app.state.writing_service = FakeWritingService(markdown="# Saved Report")
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

    data = response.json()["data"]
    assert data["artifact_id"]
    artifact = app.state.store.get_writing_artifact(data["artifact_id"])
    assert artifact["artifact_type"] == "report"
    assert artifact["markdown"] == "# Saved Report"
    assert artifact["item_ids"] == ["rss:1"]


def test_writing_artifact_list_update_and_markdown_export(tmp_path):
    app = create_app(settings(tmp_path))
    artifact = app.state.store.create_writing_artifact(
        artifact_type="blog",
        title="Blog Title",
        markdown="# Blog Title",
        params={"style": "analysis"},
        item_ids=["rss:1"],
    )
    client = TestClient(app)

    listed = client.get("/write/artifacts").json()["data"]["items"]
    assert listed[0]["id"] == artifact["id"]

    update = client.patch(
        f"/write/artifacts/{artifact['id']}",
        json={"title": "New Title", "markdown": "# New Title"},
    )
    assert update.status_code == 200
    assert update.json()["data"]["title"] == "New Title"

    exported = client.get(f"/write/artifacts/{artifact['id']}/export", params={"format": "markdown"})
    assert exported.status_code == 200
    assert exported.json()["data"]["filename"] == "New Title.md"
    assert exported.json()["data"]["content"] == "# New Title"


def test_report_response_includes_material_limit_metadata(tmp_path):
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
        },
    )

    data = response.json()["data"]
    assert data["material_limit"] == 30
    assert data["input_item_count"] == 2


def test_report_generation_uses_enabled_domain_keywords_only(tmp_path):
    app = create_app(settings(tmp_path))
    seed(app)
    app.state.settings.config_path.parent.mkdir(parents=True, exist_ok=True)
    app.state.settings.config_path.write_text(
        json.dumps(
            {
                "domains": [
                    {"id": "ai", "label": "AI与大数据", "enabled": True, "keywords": ["ai"]},
                    {"id": "frontend", "label": "前端开发", "enabled": False, "keywords": ["frontend"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    app.state.writing_service = FakeWritingService(markdown="# Domain Report")
    client = TestClient(app)

    response = client.post(
        "/write/report",
        json={
            "time_range": "custom",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "domains": ["ai", "frontend"],
            "style": "professional",
            "language": "zh",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["item_count"] == 1
    sent_items = app.state.writing_service.report_calls[0][0]
    assert [item["id"] for item in sent_items] == ["rss:1"]


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
