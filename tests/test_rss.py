import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from src.models import RSSSourceConfig
from src.scrapers.rss import RSSScraper


def test_rss_fetch_respects_per_source_fetch_limit():
    now = datetime.now(timezone.utc)
    entries = "\n".join(
        f"""
        <item>
          <guid>item-{index}</guid>
          <title>Item {index}</title>
          <link>https://example.com/items/{index}</link>
          <pubDate>{(now - timedelta(minutes=index)).strftime("%a, %d %b %Y %H:%M:%S %z")}</pubDate>
          <description>Body {index}</description>
        </item>
        """
        for index in range(5)
    )
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Example Feed</title>
        {entries}
      </channel>
    </rss>
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=feed)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    scraper = RSSScraper(
        [RSSSourceConfig(name="Example", url="https://example.com/feed.xml", fetch_limit=2)],
        client,
    )

    items = asyncio.run(scraper.fetch(now - timedelta(hours=1)))
    asyncio.run(client.aclose())

    assert [item.title for item in items] == ["Item 0", "Item 1"]


def test_rss_config_defaults_to_reasonable_fetch_limit():
    config = RSSSourceConfig(name="Example", url="https://example.com/feed.xml")

    assert config.fetch_limit == 20
