from datetime import datetime, timezone

from src.models import ContentItem, SourceType
from src.storage.sqlite_store import SQLiteStore


def item(item_id="rss:1", title="Example keyword", score=8.5, tags=None, metadata=None, published_at=None):
    return ContentItem(
        id=item_id,
        source_type=SourceType.RSS,
        title=title,
        url="https://example.com/post",
        content="Body",
        author="Alice",
        published_at=published_at or datetime(2026, 5, 9, tzinfo=timezone.utc),
        ai_score=score,
        ai_reason="Useful",
        ai_summary="Summary",
        ai_tags=tags or ["ai", "infra"],
        metadata=metadata or {"feed_name": "Example Feed"},
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


def test_query_items_filters_by_published_range(tmp_path):
    store = SQLiteStore(tmp_path / "horizon.db")
    store.initialize()
    store.create_run("run-1", hours=168, config_snapshot={})
    store.save_items(
        "run-1",
        [
            item("rss:old", "Old AI", 9.0, ["ai"], published_at=datetime(2026, 5, 1, tzinfo=timezone.utc)),
            item("rss:today", "Today AI", 8.0, ["ai"], published_at=datetime(2026, 5, 14, 8, tzinfo=timezone.utc)),
            item("rss:later", "Later AI", 7.0, ["ai"], published_at=datetime(2026, 5, 15, tzinfo=timezone.utc)),
        ],
        stage="filtered",
        selected=True,
    )

    rows = store.query_items(
        selected_only=True,
        published_after=datetime(2026, 5, 14, tzinfo=timezone.utc),
        published_before=datetime(2026, 5, 14, 23, 59, 59, tzinfo=timezone.utc),
        limit=50,
    )

    assert [row["id"] for row in rows] == ["rss:today"]
    assert store.count_items(
        selected_only=True,
        published_after=datetime(2026, 5, 14, tzinfo=timezone.utc),
        published_before=datetime(2026, 5, 14, 23, 59, 59, tzinfo=timezone.utc),
    ) == 1


def test_save_items_projects_enrichment_metadata_to_analysis_fields(tmp_path):
    store = SQLiteStore(tmp_path / "horizon.db")
    store.initialize()
    store.create_run("run-1", hours=24, config_snapshot={})

    store.save_items(
        "run-1",
        [
            item(
                metadata={
                    "feed_name": "Example Feed",
                    "detailed_summary_en": "Detailed English summary.",
                    "detailed_summary_zh": "中文详细总结。",
                    "background_en": "English background.",
                    "background_zh": "中文背景。",
                    "community_discussion_en": "English discussion.",
                    "community_discussion_zh": "中文讨论。",
                    "sources": [{"url": "https://example.com/source", "title": "Source title"}],
                },
            )
        ],
        stage="enriched",
        selected=True,
    )

    stored = store.get_item("rss:1")

    assert stored["detailed_summary"] == {
        "en": "Detailed English summary.",
        "zh": "中文详细总结。",
    }
    assert stored["background"] == {
        "en": "English background.",
        "zh": "中文背景。",
    }
    assert stored["community_discussion"] == {
        "en": "English discussion.",
        "zh": "中文讨论。",
    }
    assert stored["citations"] == [{"url": "https://example.com/source", "title": "Source title"}]


def test_get_item_backfills_rich_fields_from_metadata_when_analysis_columns_are_empty(tmp_path):
    store = SQLiteStore(tmp_path / "horizon.db")
    store.initialize()
    store.create_run("run-1", hours=24, config_snapshot={})
    store.save_items(
        "run-1",
        [
            item(
                metadata={
                    "feed_name": "Example Feed",
                    "detailed_summary_zh": "旧数据中文详细总结。",
                    "background_zh": "旧数据中文背景。",
                    "community_discussion_zh": "旧数据中文讨论。",
                    "sources": [{"url": "https://example.com/old", "title": "Old source"}],
                },
            )
        ],
        stage="enriched",
        selected=True,
    )
    with store.connect() as conn:
        conn.execute(
            """
            UPDATE item_analysis
            SET detailed_summary_json = '{}',
                background_json = '{}',
                community_discussion_json = '{}',
                citations_json = '[]'
            WHERE run_id = ? AND item_id = ?
            """,
            ("run-1", "rss:1"),
        )
        conn.commit()

    stored = store.get_item("rss:1")

    assert stored["detailed_summary"] == {"zh": "旧数据中文详细总结。"}
    assert stored["background"] == {"zh": "旧数据中文背景。"}
    assert stored["community_discussion"] == {"zh": "旧数据中文讨论。"}
    assert stored["citations"] == [{"url": "https://example.com/old", "title": "Old source"}]


def test_writing_artifacts_can_be_created_listed_updated_and_exported(tmp_path):
    store = SQLiteStore(tmp_path / "horizon.db")
    store.initialize()

    artifact = store.create_writing_artifact(
        artifact_type="report",
        title="今日技术动态",
        markdown="# 今日技术动态",
        params={"time_range": "today"},
        item_ids=["rss:1", "rss:2"],
    )

    listed = store.list_writing_artifacts(limit=10, offset=0)
    assert listed[0]["id"] == artifact["id"]
    assert listed[0]["title"] == "今日技术动态"
    assert listed[0]["artifact_type"] == "report"

    updated = store.update_writing_artifact(
        artifact["id"],
        title="更新标题",
        markdown="# 更新标题",
    )
    assert updated is True

    loaded = store.get_writing_artifact(artifact["id"])
    assert loaded["title"] == "更新标题"
    assert loaded["markdown"] == "# 更新标题"
    assert loaded["item_ids"] == ["rss:1", "rss:2"]
    assert loaded["params"] == {"time_range": "today"}
