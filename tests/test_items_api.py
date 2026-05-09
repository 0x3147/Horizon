from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.settings import AppSettings
from src.models import ContentItem, SourceType


def settings(tmp_path):
    data_dir = tmp_path / "data"
    return AppSettings(data_dir, data_dir / "horizon.db", data_dir / "config.json", "127.0.0.1", 8765)


def item(item_id="rss:1", title="AI keyword", score=8.5, tags=None):
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
        metadata={"feed_name": "Example Feed"},
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


def test_get_item_by_id(tmp_path):
    app = create_app(settings(tmp_path))
    seed(app)
    client = TestClient(app)

    response = client.get("/items/rss:1")

    assert response.status_code == 200
    assert response.json()["data"]["title"] == "AI keyword"


def test_get_missing_item_returns_business_error(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))

    response = client.get("/items/missing")

    assert response.status_code == 404
    assert response.json()["errorCode"] == 5001
