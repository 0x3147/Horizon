import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.settings import AppSettings
from src.models import ContentItem, SourceType


def settings(tmp_path):
    data_dir = tmp_path / "data"
    return AppSettings(data_dir, data_dir / "horizon.db", data_dir / "config.json", "127.0.0.1", 8765)


def item(item_id="rss:1", title="AI keyword", score=8.5, tags=None, metadata=None):
    return ContentItem(
        id=item_id,
        source_type=SourceType.RSS,
        title=title,
        url="https://example.com/post",
        content="Body keyword",
        author="Alice",
        published_at=datetime(2026, 5, 9, tzinfo=timezone.utc),
        ai_score=score,
        ai_reason="Useful",
        ai_summary="Summary keyword",
        ai_tags=tags or ["ai", "infra"],
        metadata=metadata or {"feed_name": "Example Feed"},
    )


def seed(app):
    app.state.store.create_run("run-1", hours=24, config_snapshot={})
    app.state.store.save_items(
        "run-1",
        [
            item("rss:1", "AI keyword", 8.5, ["ai", "infra"]),
            item("rss:2", "Gardening", 4.0, ["plants"]),
        ],
        stage="filtered",
        selected=True,
    )


def test_query_items_by_score_tag_and_text(tmp_path):
    app = create_app(settings(tmp_path))
    seed(app)
    client = TestClient(app)

    score = client.get("/items", params={"min_score": 8, "selected_only": True})
    tag = client.get("/items", params={"tag": "ai"})
    text = client.get("/items", params={"q": "keyword"})

    assert score.json()["data"]["items"][0]["id"] == "rss:1"
    assert tag.json()["data"]["items"][0]["id"] == "rss:1"
    assert text.json()["data"]["items"][0]["id"] == "rss:1"


def test_query_items_by_domain_uses_enabled_config_only(tmp_path):
    app = create_app(settings(tmp_path))
    seed(app)
    app.state.config_path.parent.mkdir(parents=True, exist_ok=True)
    app.state.config_path.write_text(
        json.dumps(
            {
                "domains": [
                    {"id": "ai", "label": "AI与大数据", "enabled": True, "keywords": ["ai"]},
                    {"id": "plants", "label": "植物", "enabled": False, "keywords": ["gardening"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(app)

    enabled = client.get("/items", params={"domain": "ai"})
    disabled = client.get("/items", params={"domain": "plants"})

    assert [item["id"] for item in enabled.json()["data"]["items"]] == ["rss:1"]
    assert disabled.json()["data"]["items"] == []


def test_get_item_by_id(tmp_path):
    app = create_app(settings(tmp_path))
    seed(app)
    client = TestClient(app)

    response = client.get("/items/rss:1")

    assert response.status_code == 200
    assert response.json()["data"]["title"] == "AI keyword"


def test_get_item_returns_per_item_enrichment_fields(tmp_path):
    app = create_app(settings(tmp_path))
    app.state.store.create_run("run-1", hours=24, config_snapshot={})
    app.state.store.save_items(
        "run-1",
        [
            item(
                metadata={
                    "feed_name": "Example Feed",
                    "detailed_summary_zh": "这条新闻的详细总结。",
                    "background_zh": "这条新闻的背景。",
                    "community_discussion_zh": "这条新闻的评论讨论。",
                    "sources": [{"url": "https://example.com/source", "title": "Source title"}],
                },
            )
        ],
        stage="enriched",
        selected=True,
    )
    client = TestClient(app)

    response = client.get("/items/rss:1")

    assert response.status_code == 200
    assert response.json()["data"]["detailed_summary"] == {"zh": "这条新闻的详细总结。"}
    assert response.json()["data"]["background"] == {"zh": "这条新闻的背景。"}
    assert response.json()["data"]["community_discussion"] == {"zh": "这条新闻的评论讨论。"}
    assert response.json()["data"]["citations"] == [
        {"url": "https://example.com/source", "title": "Source title"}
    ]


def test_get_missing_item_returns_business_error(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))

    response = client.get("/items/missing")

    assert response.status_code == 404
    assert response.json()["errorCode"] == 5001
