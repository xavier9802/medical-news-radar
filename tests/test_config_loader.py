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


def test_source_config_preserves_restricted_adapter_fields(tmp_path: Path):
    path = tmp_path / "sources.yml"
    path.write_text(
        "sources:\n  - id: html-source\n    name: HTML source\n"
        "    homepage_url: https://example.com/news\n    feed_url: https://example.com/news\n    type: static_page\n"
        "    fetch:\n      strategy: html_list\n      parser_profile: hospital_ceo\n"
        "      allowed_hosts: [EXAMPLE.com, news.example.com, EXAMPLE.com]\n",
        encoding="utf-8",
    )
    source = load_config("sources", path).data["sources"][0]
    feed = configured_feed_groups(path)[0]["medical_media"][0]
    assert source["fetch"]["parser_profile"] == "hospital_ceo"
    assert source["fetch"]["allowed_hosts"] == ["example.com", "news.example.com"]
    assert feed["parser_profile"] == "hospital_ceo"
    assert feed["allowed_hosts"] == ["example.com", "news.example.com"]


def test_source_config_drops_invalid_host_entries(tmp_path: Path):
    path = tmp_path / "sources.yml"
    path.write_text(
        "sources:\n  - id: bad-hosts\n    name: Bad hosts\n"
        "    homepage_url: https://example.com/\n    type: static_page\n"
        "    fetch: {strategy: html_list, parser_profile: hospital_ceo, allowed_hosts: ['https://example.com', '127.0.0.1', good.example]}\n",
        encoding="utf-8",
    )
    source = load_config("sources", path).data["sources"][0]
    assert source["fetch"]["allowed_hosts"] == ["good.example"]


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


def test_default_config_contains_nine_dated_china_sources():
    by_id = {
        row["id"]: row
        for row in load_config("sources", Path("config/sources.yml")).data["sources"]
    }
    expected = {
        "cn-nhsa-policy": ("html_list", "nhsa_policy", "s", "insurance_compliance", 8),
        "cn-chs-news": ("html_list", "chs_news", "a", "primary_care", 6),
        "cn-cnmia-news": ("html_list", "cnmia_news", "a", "company_market", 6),
        "cn-chima-news": ("html_list", "chima_news", "a", "health_it", 6),
        "cn-kanyijie": ("html_list", "kanyijie", "b", "company_market", 5),
        "cn-hospital-ceo": ("html_list", "hospital_ceo", "b", "company_market", 5),
        "cn-healthcare": ("html_list", "cn_healthcare", "b", "primary_care", 4),
        "cn-yxj": ("json", "yxj_home_json", "c", "health_it", 3),
        "cn-bioon": ("html_list", "bioon", "c", "pharma_device", 3),
    }
    for source_id, contract in expected.items():
        row = by_id[source_id]
        assert row["enabled"] is True
        assert row["language"] == "zh" and row["region"] == "cn"
        assert row["fetch"]["allowed_hosts"]
        assert (
            row["fetch"]["strategy"],
            row["fetch"]["parser_profile"],
            row["tier"],
            row["category"],
            row["fetch"]["max_items"],
        ) == contract
    assert by_id["cn-healthcare"]["feed_url"] == "https://www.cn-healthcare.com/?logo=1"
    assert by_id["cn-bioon"]["feed_url"] == "https://www.bioon.com/BioMedical"
    assert "细胞外囊泡" in by_id["cn-bioon"]["filters"]["include_keywords"]
    assert {"cn-medtrend", "cn-mdweekly"}.isdisjoint(by_id)
