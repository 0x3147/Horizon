import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from src.ai.enricher import ContentEnricher
from src.models import ContentItem, SourceType


def _make_item(item_id: str) -> ContentItem:
    return ContentItem(
        id=item_id,
        source_type=SourceType.RSS,
        title=f"Item {item_id}",
        url="https://example.com/item",
        published_at=datetime(2026, 4, 26, tzinfo=timezone.utc),
    )


def test_enrich_batch_reports_item_progress(monkeypatch):
    enricher = ContentEnricher(SimpleNamespace())
    items = [_make_item("rss:test:1"), _make_item("rss:test:2")]
    progress = []

    async def fake_enrich_item(item):
        item.metadata["background"] = "Background"

    async def on_progress(count, item):
        progress.append((count, item.id))

    monkeypatch.setattr(enricher, "_enrich_item", fake_enrich_item)

    asyncio.run(enricher.enrich_batch(items, progress_callback=on_progress))

    assert progress == [(1, "rss:test:1"), (2, "rss:test:2")]
