from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts import update_news
from scripts.update_news import RawItem, collect_all, fetch_opml_rss, parse_curated_media_feed_items


UTC = timezone.utc
NOW = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test feed</title><item>
<title>Medical AI policy update</title>
<link>https://example.com/item-1</link>
<pubDate>Sun, 19 Jul 2026 07:00:00 GMT</pubDate>
</item></channel></rss>"""


class FakeResponse:
    content = RSS
    text = RSS.decode("utf-8")

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def get(self, *_args, **_kwargs) -> FakeResponse:
        return FakeResponse()


def test_configured_metadata_survives_feed_parsing():
    feed = {
        "title": "Configured source",
        "xml_url": "https://example.com/feed.xml",
        "html_url": "https://example.com/",
        "source_id": "configured-source",
        "category": "medical_ai",
        "source_tier": "s",
        "language": "en",
        "region": "global",
        "is_official": True,
        "source_metadata": {"source_id": "configured-source", "tier": "s"},
    }

    items = parse_curated_media_feed_items(RSS, feed, NOW, "official_health", "Official Health Updates")

    assert len(items) == 1
    assert items[0].meta["source_id"] == "configured-source"
    assert items[0].meta["category"] == "medical_ai"
    assert items[0].meta["source_tier"] == "s"
    assert items[0].meta["is_official"] is True


def test_collect_all_uses_valid_source_config_and_emits_per_source_status(tmp_path: Path):
    config = tmp_path / "sources.yml"
    config.write_text(
        "sources:\n"
        "  - id: configured-source\n"
        "    name: Configured source\n"
        "    homepage_url: https://example.com/\n"
        "    feed_url: https://example.com/feed.xml\n"
        "    type: rss\n"
        "    category: medical_ai\n"
        "    tier: s\n"
        "    language: en\n"
        "    region: global\n"
        "    enabled: true\n"
        "    fetch: {strategy: rss, max_items: 5, timeout_seconds: 7}\n"
        "    metadata: {legacy_site_id: official_health}\n",
        encoding="utf-8",
    )

    items, sites, configured = collect_all(FakeSession(), NOW, sources_config=config)

    assert len(items) == 1
    assert items[0].meta["source_id"] == "configured-source"
    assert sites == [
        {
            "site_id": "official_health",
            "site_name": "Official Health Updates",
            "ok": True,
            "item_count": 1,
            "duration_ms": sites[0]["duration_ms"],
            "error": None,
            "source_count": 1,
            "successful_source_count": 1,
            "failed_source_count": 0,
        }
    ]
    assert configured[0]["source_id"] == "configured-source"
    assert configured[0]["ok"] is True
    assert configured[0]["item_count"] == 1
    assert configured[0]["feed_url"] == "https://example.com/feed.xml"


def test_collect_all_falls_back_when_source_config_is_missing(monkeypatch, tmp_path: Path):
    expected = RawItem(
        site_id="official_health",
        site_name="Official Health Updates",
        source="Fallback",
        title="Fallback item",
        url="https://example.com/fallback",
        published_at=NOW,
        meta={},
    )
    monkeypatch.setattr(update_news, "fetch_official_health_updates", lambda _session, _now: [expected])
    monkeypatch.setattr(update_news, "fetch_medical_journals", lambda _session, _now: [])
    monkeypatch.setattr(update_news, "fetch_medical_media", lambda _session, _now: [])

    items, sites, configured = collect_all(FakeSession(), NOW, sources_config=tmp_path / "missing.yml")

    assert items == [expected]
    assert len(sites) == 3
    assert configured == []


def test_fetch_opml_skips_urls_already_managed_by_source_config(tmp_path: Path):
    opml = tmp_path / "feeds.opml"
    opml.write_text(
        '<?xml version="1.0"?><opml version="2.0"><body>'
        '<outline title="Duplicate" xmlUrl="https://example.com/feed.xml" />'
        "</body></opml>",
        encoding="utf-8",
    )

    items, summary, statuses = fetch_opml_rss(
        NOW,
        opml,
        configured_urls={"https://EXAMPLE.com:443/feed.xml/"},
    )

    assert items == []
    assert summary["feed_count"] == 1
    assert summary["effective_feed_count"] == 0
    assert statuses[0]["skipped"] is True
    assert statuses[0]["skip_reason"] == "configured_source_duplicate"
