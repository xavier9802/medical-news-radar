from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from scripts import update_news
from scripts.update_news import (
    RawItem,
    collect_all,
    configured_feed_groups,
    fetch_opml_rss,
    parse_curated_media_feed_items,
)


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
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    def get(self, *args, **kwargs) -> FakeResponse:
        self.calls.append((args, kwargs))
        return FakeResponse()


class FakeCrossrefResponse:
    content = b""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "message": {
                "items": [
                    {
                        "DOI": "10.1056/NEJMoa2600001",
                        "URL": "https://doi.org/10.1056/NEJMoa2600001",
                        "title": ["Clinical AI trial update"],
                        "published": {"date-parts": [[2026, 7, 18]]},
                    }
                ]
            }
        }


class FakeCrossrefSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs) -> FakeCrossrefResponse:
        self.calls.append((url, kwargs))
        return FakeCrossrefResponse()


class FakeListResponse:
    def __init__(
        self,
        *,
        text="",
        payload=None,
        url="https://www.h-ceo.com/news.html",
        content_type="text/html; charset=utf-8",
    ):
        self.text = text
        self.payload = payload or {}
        self._content = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None and not text
            else text.encode("utf-8")
        )
        self.url = url
        self.headers = {"content-type": content_type}
        self.encoding = "utf-8"
        self.closed = False

    @property
    def content(self):
        raise AssertionError("adapter responses must be consumed through bounded streaming")

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload

    def iter_content(self, chunk_size=65536):
        for offset in range(0, len(self._content), chunk_size):
            yield self._content[offset : offset + chunk_size]

    def close(self):
        self.closed = True


class FakeAdapterSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.response

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.response


class FailingAdapterSession:
    def get(self, url, **kwargs):
        raise requests.ConnectionError("private network detail must not escape")


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

    session = FakeSession()
    items, sites, configured = collect_all(session, NOW, sources_config=config)

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
    assert session.calls[0][1]["headers"]["User-Agent"].startswith("MedicalNewsRadar/")


def test_configured_crossref_strategy_is_preserved_and_parsed(tmp_path: Path):
    config = tmp_path / "sources.yml"
    config.write_text(
        "sources:\n"
        "  - id: nejm\n"
        "    name: NEJM\n"
        "    homepage_url: https://www.nejm.org/\n"
        "    feed_url: https://api.crossref.org/journals/0028-4793/works?rows=20&sort=published&order=desc\n"
        "    type: journal\n"
        "    category: pharma_device\n"
        "    tier: a\n"
        "    language: en\n"
        "    region: global\n"
        "    enabled: true\n"
        "    fetch: {strategy: json, max_items: 10, timeout_seconds: 12}\n"
        "    metadata: {legacy_site_id: medical_journals}\n",
        encoding="utf-8",
    )

    groups, _result = configured_feed_groups(config)
    session = FakeCrossrefSession()
    items, sites, statuses = collect_all(session, NOW, sources_config=config)

    assert groups["medical_journals"][0]["strategy"] == "json"
    assert len(items) == 1
    assert items[0].title == "Clinical AI trial update"
    assert items[0].url == "https://doi.org/10.1056/NEJMoa2600001"
    assert items[0].published_at == datetime(2026, 7, 18, tzinfo=UTC)
    assert items[0].meta["source_id"] == "nejm"
    assert sites[0]["ok"] is True
    assert statuses[0]["ok"] is True
    assert statuses[0]["item_count"] == 1
    assert session.calls[0][1]["headers"]["Accept"] == "application/json"


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


def test_configured_html_list_is_filtered_capped_and_mapped():
    html = Path("tests/fixtures/html_sources/hospital_ceo.html").read_text(encoding="utf-8")
    feed = {
        "title": "中国医院院长网",
        "xml_url": "https://www.h-ceo.com/news.html",
        "html_url": "https://www.h-ceo.com/",
        "strategy": "html_list",
        "parser_profile": "hospital_ceo",
        "allowed_hosts": ["www.h-ceo.com"],
        "max_entries": 1,
        "include_keywords": "医院,AI",
        "exclude_keywords": "报名,培训班",
        "source_id": "cn-hospital-ceo",
        "category": "company_market",
        "source_tier": "b",
    }
    session = FakeAdapterSession(FakeListResponse(text=html))
    items = update_news.fetch_configured_feed(session, NOW, "medical_media", "Medical Media", feed)
    assert len(items) == 1
    assert items[0].title == "医院数智化运营新实践"
    assert items[0].meta["summary"] == "医院管理摘要"
    assert items[0].meta["source_id"] == "cn-hospital-ceo"
    assert session.calls[0][0] == "GET"
    assert session.calls[0][2]["stream"] is True
    assert session.response.closed is True


def test_configured_yxj_json_uses_fixed_post_contract():
    payload = json.loads(Path("tests/fixtures/yxj_home.json").read_text(encoding="utf-8"))
    feed = {
        "title": "医学界",
        "xml_url": "https://pcapi.yxj.org.cn/ysz-content/web/home/news/getNewsModuleData",
        "strategy": "json",
        "parser_profile": "yxj_home_json",
        "allowed_hosts": ["pcapi.yxj.org.cn", "www.yxj.org.cn"],
        "max_entries": 3,
        "include_keywords": "医院,医疗,基层,人工智能,AI,医保",
        "exclude_keywords": "用药,病例",
        "source_id": "cn-yxj",
        "category": "health_it",
        "source_tier": "c",
    }
    session = FakeAdapterSession(
        FakeListResponse(payload=payload, url=feed["xml_url"], content_type="application/json")
    )
    items = update_news.fetch_configured_feed(session, NOW, "medical_media", "Medical Media", feed)
    assert items[0].meta["source_id"] == "cn-yxj"
    assert session.calls[0][0] == "POST"
    assert session.calls[0][2]["json"] == {"categoryId": 0, "position": "HOME_PAGE_MAIN_NEWS"}
    assert session.calls[0][2]["stream"] is True
    assert session.response.closed is True


def test_adapter_zero_valid_items_is_a_per_source_failure(tmp_path: Path):
    config = tmp_path / "sources.yml"
    config.write_text(
        "sources:\n  - id: empty-html\n    name: Empty HTML\n"
        "    feed_url: https://www.h-ceo.com/news.html\n    type: static_page\n    enabled: true\n"
        "    fetch: {strategy: html_list, parser_profile: hospital_ceo, allowed_hosts: [www.h-ceo.com]}\n",
        encoding="utf-8",
    )
    items, sites, statuses = collect_all(
        FakeAdapterSession(FakeListResponse(text="<html></html>")),
        NOW,
        sources_config=config,
    )
    assert items == []
    assert statuses[0]["ok"] is False
    assert statuses[0]["error"] == "no_valid_items"
    assert sites[0]["failed_source_count"] == 1


def test_adapter_with_only_well_formed_stale_items_is_a_warning_candidate(tmp_path: Path):
    config = tmp_path / "sources.yml"
    config.write_text(
        "sources:\n  - id: stale-html\n    name: Stale HTML\n"
        "    feed_url: https://www.h-ceo.com/news.html\n    type: static_page\n    enabled: true\n"
        "    fetch: {strategy: html_list, parser_profile: hospital_ceo, allowed_hosts: [www.h-ceo.com]}\n",
        encoding="utf-8",
    )
    stale_html = '<div class="paging"><div class="zlist01"><a class="tit" href="/post/1.html">医院管理历史回顾</a><span class="time">2026年05月01日 12:00</span></div></div>'
    items, sites, statuses = collect_all(
        FakeAdapterSession(FakeListResponse(text=stale_html)),
        NOW,
        sources_config=config,
    )
    assert items == []
    assert statuses[0]["ok"] is True
    assert statuses[0]["item_count"] == 0
    assert statuses[0]["error"] is None
    assert sites[0]["successful_source_count"] == 1


def test_configured_adapter_request_failure_uses_stable_error_category():
    feed = {
        "title": "中国医院院长网",
        "xml_url": "https://www.h-ceo.com/news.html",
        "html_url": "https://www.h-ceo.com/",
        "strategy": "html_list",
        "parser_profile": "hospital_ceo",
        "allowed_hosts": ["www.h-ceo.com"],
        "max_entries": 1,
        "source_id": "cn-hospital-ceo",
        "category": "company_market",
        "source_tier": "b",
    }
    with pytest.raises(ValueError, match="^request_failed$"):
        update_news.fetch_configured_feed(
            FailingAdapterSession(), NOW, "medical_media", "Medical Media", feed
        )


def test_configured_adapter_rejects_oversized_response():
    feed = {
        "title": "中国医院院长网",
        "xml_url": "https://www.h-ceo.com/news.html",
        "html_url": "https://www.h-ceo.com/",
        "strategy": "html_list",
        "parser_profile": "hospital_ceo",
        "allowed_hosts": ["www.h-ceo.com"],
        "max_entries": 1,
        "source_id": "cn-hospital-ceo",
        "category": "company_market",
        "source_tier": "b",
    }
    response = FakeListResponse(text="x" * (update_news.MAX_CONFIGURED_LIST_BYTES + 1))
    with pytest.raises(ValueError, match="^response_too_large$"):
        update_news.fetch_configured_feed(
            FakeAdapterSession(response), NOW, "medical_media", "Medical Media", feed
        )


def test_china_media_filters_keep_domain_news_and_drop_promotional_or_clinical_items():
    groups, result = configured_feed_groups(Path("config/sources.yml"))
    assert result.used_fallback is False
    feeds = {
        feed["source_id"]: feed
        for group_feeds in groups.values()
        for feed in group_feeds
    }
    article_url = "https://example.invalid/article"
    assert update_news.curated_feed_entry_allowed(
        feeds["cn-kanyijie"], "社会办医院AI应用落地", article_url
    )
    assert not update_news.curated_feed_entry_allowed(
        feeds["cn-kanyijie"], "医疗大会早鸟票报名通知", article_url
    )
    assert not update_news.curated_feed_entry_allowed(
        feeds["cn-yxj"], "儿童鼻窦炎用药指南", article_url
    )
    assert update_news.curated_feed_entry_allowed(
        feeds["cn-bioon"], "创新药获批推动产业转化", article_url
    )
