from __future__ import annotations

from pathlib import Path

import pytest

from scripts.config_loader import (
    ConfigLoadError,
    dedupe_sources,
    load_all_configs,
    load_config,
    normalize_feed_url,
    reset_config_cache,
)
from scripts.update_news import add_source_tier_fields, configured_feed_groups, dedupe_opml_feeds


EXPECTED_CATEGORY_IDS = {
    "policy",
    "medical_ai",
    "primary_care",
    "insurance_compliance",
    "health_it",
    "pharma_device",
    "company_market",
    "global_healthtech",
}


def test_loads_categories_from_valid_yaml(tmp_path: Path):
    path = tmp_path / "categories.yml"
    path.write_text(
        "categories:\n"
        "  - id: policy\n"
        "    label: 政策监管\n"
        "    description: 医疗政策\n"
        "    order: 10\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    result = load_config("categories", path)

    assert result.data["categories"] == [
        {
            "id": "policy",
            "label": "政策监管",
            "description": "医疗政策",
            "order": 10,
            "enabled": True,
        }
    ]
    assert result.used_fallback is False
    assert result.errors == ()


def test_missing_config_uses_safe_defaults(tmp_path: Path):
    result = load_config("categories", tmp_path / "missing.yml")

    assert result.used_fallback is True
    assert {row["id"] for row in result.data["categories"]} == EXPECTED_CATEGORY_IDS
    assert result.errors


def test_invalid_yaml_is_clear_in_strict_mode(tmp_path: Path):
    path = tmp_path / "sources.yml"
    path.write_text("sources: [", encoding="utf-8")

    with pytest.raises(ConfigLoadError, match="sources.yml"):
        load_config("sources", path, strict=True)


def test_invalid_yaml_falls_back_with_diagnostic(tmp_path: Path):
    path = tmp_path / "scoring.yml"
    path.write_text("weights: [", encoding="utf-8")

    result = load_config("scoring", path)

    assert result.used_fallback is True
    assert result.data["weights"]["authority"] == pytest.approx(0.30)
    assert result.errors and "scoring.yml" in result.errors[0]


def test_invalid_source_rows_are_skipped_without_discarding_valid_rows(tmp_path: Path):
    path = tmp_path / "sources.yml"
    path.write_text(
        "sources:\n"
        "  - id: who\n"
        "    name: WHO\n"
        "    homepage_url: https://www.who.int/\n"
        "    feed_url: https://www.who.int/feed.xml\n"
        "    type: rss\n"
        "    category: global_healthtech\n"
        "    tier: s\n"
        "    enabled: true\n"
        "  - id: missing-name\n"
        "    feed_url: https://example.com/feed.xml\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    result = load_config("sources", path)

    assert [row["id"] for row in result.data["sources"]] == ["who"]
    assert result.used_fallback is False
    assert any("source row 2" in error for error in result.errors)


def test_feed_url_normalization_and_dedupe_prefers_first_metadata():
    assert normalize_feed_url("HTTPS://EXAMPLE.COM:443/feed/#fragment") == "https://example.com/feed"
    assert normalize_feed_url("http://Example.com:80/feed?b=2&a=1") == "http://example.com/feed?a=1&b=2"
    sources = [
        {"id": "yaml", "feed_url": "https://example.com/feed/", "tier": "s"},
        {"id": "opml", "feed_url": "https://EXAMPLE.com:443/feed", "tier": "c"},
        {"id": "other", "feed_url": "https://example.org/feed", "tier": "b"},
    ]

    assert dedupe_sources(sources) == [sources[0], sources[2]]


def test_default_config_paths_are_repo_relative(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    reset_config_cache()
    monkeypatch.chdir(tmp_path)

    configs = load_all_configs()

    assert {row["id"] for row in configs["categories"].data["categories"]} == EXPECTED_CATEGORY_IDS
    assert configs["categories"].path.name == "categories.yml"


def test_reset_config_cache_allows_reloading_explicit_path(tmp_path: Path):
    path = tmp_path / "categories.yml"
    path.write_text("categories:\n  - id: policy\n    label: 初始\n", encoding="utf-8")
    first = load_config("categories", path)
    path.write_text("categories:\n  - id: policy\n    label: 更新\n", encoding="utf-8")

    cached = load_config("categories", path)
    reset_config_cache()
    reloaded = load_config("categories", path)

    assert first.data["categories"][0]["label"] == "初始"
    assert cached.data["categories"][0]["label"] == "初始"
    assert reloaded.data["categories"][0]["label"] == "更新"


def test_configured_feeds_group_by_legacy_site_and_keep_source_metadata(tmp_path: Path):
    path = tmp_path / "sources.yml"
    path.write_text(
        "sources:\n"
        "  - id: nhc\n"
        "    name: 国家卫生健康委员会\n"
        "    homepage_url: https://www.nhc.gov.cn/\n"
        "    feed_url: https://www.nhc.gov.cn/feed.xml\n"
        "    type: rss\n"
        "    category: policy\n"
        "    tier: s\n"
        "    enabled: true\n"
        "    fetch: {strategy: rss, max_items: 12}\n"
        "    metadata: {legacy_site_id: official_health}\n",
        encoding="utf-8",
    )

    groups, result = configured_feed_groups(path)

    assert result.used_fallback is False
    assert list(groups) == ["official_health"]
    assert groups["official_health"][0]["source_id"] == "nhc"
    assert groups["official_health"][0]["category"] == "policy"
    assert groups["official_health"][0]["source_tier"] == "s"
    assert groups["official_health"][0]["max_entries"] == 12


def test_opml_dedupe_excludes_configured_feed_url():
    feeds = [
        {"title": "Duplicate", "xml_url": "https://EXAMPLE.com:443/feed/", "html_url": ""},
        {"title": "Unique", "xml_url": "https://example.org/feed", "html_url": ""},
    ]

    kept, duplicates = dedupe_opml_feeds(feeds, {"https://example.com/feed"})

    assert [row["title"] for row in kept] == ["Unique"]
    assert [row["title"] for row in duplicates] == ["Duplicate"]


def test_configured_tier_is_preserved_with_legacy_compatibility():
    result = add_source_tier_fields({"site_id": "official_health", "source_tier": "s"})

    assert result["source_tier"] == "s"
    assert result["source_tier_legacy"] == "official"
    assert result["source_tier_rank"] == 0


def test_default_config_enables_actions_verified_replacements_and_pauses_blocked_originals():
    sources = load_config("sources", Path("config/sources.yml")).data["sources"]
    by_id = {source["id"]: source for source in sources}
    enabled_ids = {source["id"] for source in sources if source.get("enabled")}

    assert {
        "who-news",
        "fda-newsroom",
        "nih-news",
        "nejm",
        "the-lancet",
        "bmj-research",
        "medpage-today",
        "onc-health-it",
        "hit-consultant",
    } <= enabled_ids
    assert enabled_ids.isdisjoint({"medscape", "healthcare-it-news", "himss-news"})
    assert by_id["who-news"]["feed_url"] == "https://www.who.int/rss-feeds/news-english.xml"
    assert by_id["fda-newsroom"]["feed_url"].endswith("/rss-feeds/press-releases/rss.xml")
    assert by_id["nih-news"]["feed_url"].endswith("/cancer-currents-blog.rss")
    assert by_id["nejm"]["fetch"]["strategy"] == "json"
    assert by_id["the-lancet"]["fetch"]["strategy"] == "json"
    assert by_id["bmj-research"]["fetch"]["strategy"] == "json"
    assert "/journals/1756-1833/works" in by_id["bmj-research"]["feed_url"]
