from pathlib import Path

from src.models import AIConfig, AIProvider
from src.setup.presets import load_presets, match_sources
from src.setup.wizard import build_config


def test_local_presets_include_it_tech_news_rss_sources():
    presets_path = Path(__file__).resolve().parents[1] / "data" / "presets.json"

    presets = load_presets(str(presets_path), prefer_api=False)
    matched = match_sources("IT 科技圈 热门 新闻 AI 安全 开源", presets)
    source_names = {
        source["config"].get("name")
        for source, _score in matched
        if source.get("type") == "rss"
    }

    assert "Techmeme" in source_names
    assert "MIT Technology Review - AI" in source_names
    assert "Krebs on Security" in source_names


def test_build_config_turns_matched_tech_news_presets_into_rss_sources():
    presets_path = Path(__file__).resolve().parents[1] / "data" / "presets.json"
    presets = load_presets(str(presets_path), prefer_api=False)
    matched_sources = [source for source, _score in match_sources("科技 新闻 AI", presets)]

    config = build_config(
        AIConfig(provider=AIProvider.OPENAI, model="gpt-4.1-mini"),
        matched_sources,
    )

    rss_by_name = {source.name: source for source in config.sources.rss}
    assert str(rss_by_name["Techmeme"].url) == "https://www.techmeme.com/feed.xml"
    assert rss_by_name["Techmeme"].fetch_limit == 20
    assert str(rss_by_name["MIT Technology Review - AI"].url) == "https://www.technologyreview.com/topic/artificial-intelligence/feed"
    assert rss_by_name["MIT Technology Review - AI"].fetch_limit == 15
