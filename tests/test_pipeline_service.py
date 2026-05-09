import asyncio
from datetime import datetime, timezone

import pytest

from src.core.errors import HorizonApiError
from src.core.pipeline_service import PipelineService
from src.core.settings import AppSettings
from src.models import ContentItem, SourceType
from src.storage.sqlite_store import SQLiteStore


def settings(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    config_path = data_dir / "config.json"
    config_path.write_text(
        """
        {
          "version": "1.0",
          "ai": {
            "provider": "openai",
            "model": "gpt-4",
            "api_key_env": "OPENAI_API_KEY",
            "languages": ["en"]
          },
          "sources": {
            "github": [],
            "hackernews": {"enabled": false},
            "rss": [],
            "reddit": {"enabled": false, "subreddits": [], "users": []},
            "telegram": {"enabled": false, "channels": []}
          },
          "filtering": {"ai_score_threshold": 7.0, "time_window_hours": 24}
        }
        """,
        encoding="utf-8",
    )
    return AppSettings(data_dir, data_dir / "horizon.db", config_path, "127.0.0.1", 8765)


def make_item(score=None):
    return ContentItem(
        id="rss:1",
        source_type=SourceType.RSS,
        title="Example",
        url="https://example.com/post",
        content="Body",
        author="Alice",
        published_at=datetime(2026, 5, 9, tzinfo=timezone.utc),
        ai_score=score,
        metadata={"feed_name": "Example Feed"},
    )


class FakeOrchestrator:
    async def fetch_all_sources(self, since):
        return [make_item()]

    def merge_cross_source_duplicates(self, items):
        return items

    async def merge_topic_duplicates(self, items):
        return items

    async def _expand_twitter_discussion(self, items):
        return None

    async def _enrich_important_items(self, items):
        for item in items:
            item.metadata["background"] = "Background"


class FailingOrchestrator(FakeOrchestrator):
    async def fetch_all_sources(self, since):
        raise RuntimeError("network down")


class FakeAnalyzer:
    async def analyze_batch(self, items):
        for item in items:
            item.ai_score = 8.5
            item.ai_reason = "Useful"
            item.ai_summary = "Summary"
            item.ai_tags = ["ai"]
        return items


class FakeSummarizer:
    async def generate_summary(self, items, date, total_fetched, language="en"):
        return "# Summary"


def service(tmp_path, orchestrator=None):
    s = settings(tmp_path)
    store = SQLiteStore(s.db_path)
    return PipelineService(
        store=store,
        settings=s,
        orchestrator_factory=lambda config, storage: orchestrator or FakeOrchestrator(),
        analyzer_factory=lambda config: FakeAnalyzer(),
        summarizer_factory=lambda: FakeSummarizer(),
    )


def test_pipeline_persists_stages_and_succeeds(tmp_path):
    pipeline = service(tmp_path)

    result = asyncio.run(pipeline.run(run_id="run-1", hours=24))

    run = pipeline.store.get_run("run-1")
    assert result["run_id"] == "run-1"
    assert run["status"] == "succeeded"
    assert run["raw_count"] == 1
    assert run["scored_count"] == 1
    assert run["filtered_count"] == 1
    assert run["enriched_count"] == 1
    assert pipeline.store.query_items(run_id="run-1", selected_only=True)[0]["ai_score"] == 8.5
    assert pipeline.store.list_summaries("run-1")[0]["markdown"] == "# Summary"


def test_pipeline_marks_failed_and_logs_errors(tmp_path):
    pipeline = service(tmp_path, orchestrator=FailingOrchestrator())

    with pytest.raises(HorizonApiError) as exc:
        asyncio.run(pipeline.run(run_id="run-1", hours=24))

    assert int(exc.value.error_code) == 4004
    assert pipeline.store.get_run("run-1")["status"] == "failed"
    assert pipeline.store.list_logs("run-1")[-1]["level"] == "error"


def test_pipeline_cancel_event_marks_cancelled(tmp_path):
    pipeline = service(tmp_path)
    cancel_event = asyncio.Event()
    cancel_event.set()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(pipeline.run(run_id="run-1", hours=24, cancel_event=cancel_event))

    assert pipeline.store.get_run("run-1")["status"] == "cancelled"
