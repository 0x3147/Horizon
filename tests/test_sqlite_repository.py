from datetime import datetime, timezone

from src.models import ContentItem, SourceType
from src.storage.sqlite_store import SQLiteStore


def item(item_id="rss:1", title="Example keyword", score=8.5, tags=None):
    return ContentItem(
        id=item_id,
        source_type=SourceType.RSS,
        title=title,
        url="https://example.com/post",
        content="Body",
        author="Alice",
        published_at=datetime(2026, 5, 9, tzinfo=timezone.utc),
        ai_score=score,
        ai_reason="Useful",
        ai_summary="Summary",
        ai_tags=tags or ["ai", "infra"],
        metadata={"feed_name": "Example Feed"},
    )


def test_run_item_summary_roundtrip(tmp_path):
    store = SQLiteStore(tmp_path / "horizon.db")
    store.initialize()

    store.create_run("run-1", hours=24, config_snapshot={"version": "1.0"})
    store.update_run("run-1", status="running")
    store.add_log("run-1", "info", "fetching", "started")
    store.save_items("run-1", [item()], stage="filtered", selected=True)
    store.save_summary("run-1", "en", "# Summary")

    assert store.get_run("run-1")["status"] == "running"
    assert store.list_runs()[0]["id"] == "run-1"
    assert store.list_logs("run-1")[0]["message"] == "started"
    assert store.query_items(min_score=8.0, selected_only=True)[0]["title"] == "Example keyword"
    assert store.list_summaries("run-1")[0]["markdown"] == "# Summary"


def test_query_items_filters_and_get_item(tmp_path):
    store = SQLiteStore(tmp_path / "horizon.db")
    store.initialize()
    store.create_run("run-1", hours=24, config_snapshot={})
    store.save_items(
        "run-1",
        [
            item("rss:1", "AI infrastructure keyword", 9.0, ["ai", "infra"]),
            item("rss:2", "Gardening", 4.0, ["plants"]),
        ],
        stage="filtered",
        selected=True,
    )

    assert [row["id"] for row in store.query_items(tag="ai")] == ["rss:1"]
    assert [row["id"] for row in store.query_items(q="keyword")] == ["rss:1"]
    assert [row["id"] for row in store.query_items(max_score=5.0)] == ["rss:2"]
    assert store.get_item("rss:1")["title"] == "AI infrastructure keyword"
