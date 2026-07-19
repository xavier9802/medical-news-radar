from __future__ import annotations

import json

from scripts.build_source_registry import build_source_registry, write_source_registry


def source(source_id: str = "nhc", **overrides):
    row = {
        "id": source_id,
        "name": "国家卫生健康委员会",
        "homepage_url": "https://www.nhc.gov.cn/",
        "feed_url": "https://www.nhc.gov.cn/feed.xml",
        "type": "government_page",
        "category": "policy",
        "tier": "s",
        "language": "zh",
        "region": "cn",
        "enabled": True,
        "featured": True,
        "metadata": {"legacy_site_id": "official_health"},
    }
    row.update(overrides)
    return row


def test_registry_merges_config_status_and_archive():
    config = {"sources": [source()]}
    status = {
        "generated_at": "2026-07-19T00:00:00Z",
        "configured_sources": [
            {"source_id": "nhc", "ok": True, "item_count": 3, "error": None}
        ],
    }
    archive = {
        "items": [
            {
                "source_id": "nhc",
                "published_at": "2026-07-18T23:00:00Z",
                "title": "政策更新",
            }
        ]
    }

    result = build_source_registry(config, status, archive)
    row = result["sources"][0]

    assert row["status"] == "healthy"
    assert row["category_label"] == "政策监管"
    assert row["tier_label"] == "S级"
    assert row["latest_item_at"] == "2026-07-18T23:00:00Z"
    assert row["last_checked_at"] == "2026-07-19T00:00:00Z"
    assert row["success_rate"] is None
    assert result["total"] == result["enabled"] == result["healthy"] == 1


def test_missing_status_is_unknown():
    result = build_source_registry({"sources": [source("x")]}, {}, {})

    assert result["sources"][0]["status"] == "unknown"
    assert result["unknown"] == 1


def test_disabled_source_overrides_failed_status():
    config = {"sources": [source("x", enabled=False)]}
    status = {"configured_sources": [{"source_id": "x", "ok": False, "error": "403"}]}

    result = build_source_registry(config, status, {})

    assert result["sources"][0]["status"] == "disabled"
    assert result["disabled"] == 1
    assert result["failed"] == 0


def test_zero_items_warn_and_failure_is_failed():
    config = {"sources": [source("zero"), source("bad")]}
    status = {
        "configured_sources": [
            {"source_id": "zero", "ok": True, "item_count": 0, "error": None},
            {"source_id": "bad", "ok": False, "item_count": 0, "error": "timeout"},
        ]
    }

    result = build_source_registry(config, status, {})
    by_id = {row["id"]: row for row in result["sources"]}

    assert by_id["zero"]["status"] == "warning"
    assert by_id["bad"]["status"] == "failed"
    assert by_id["bad"]["error"] == "timeout"
    assert result["warning"] == 1
    assert result["failed"] == 1


def test_legacy_group_status_is_used_when_per_source_status_is_absent():
    config = {"sources": [source()]}
    status = {
        "generated_at": "2026-07-19T00:00:00Z",
        "sites": [
            {
                "site_id": "official_health",
                "site_name": "Official Health Updates",
                "ok": True,
                "item_count": 4,
                "duration_ms": 25,
                "error": None,
            }
        ],
    }

    result = build_source_registry(config, status, {})

    assert result["sources"][0]["status"] == "healthy"
    assert result["sources"][0]["item_count"] == 4


def test_archive_legacy_source_name_can_supply_latest_item_time():
    config = {"sources": [source()]}
    archive = {
        "items": [
            {
                "site_id": "official_health",
                "source": "国家卫生健康委员会",
                "published_at": "2026-07-18T12:00:00Z",
            }
        ]
    }

    result = build_source_registry(config, {}, archive)

    assert result["sources"][0]["latest_item_at"] == "2026-07-18T12:00:00Z"


def test_write_source_registry_creates_static_json(tmp_path):
    output = tmp_path / "data" / "source-registry.json"

    payload = write_source_registry(
        output,
        {"sources": [source()]},
        {"generated_at": "2026-07-19T00:00:00Z"},
        {},
        generated_at="2026-07-19T00:00:00Z",
    )

    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert payload["sources"][0]["id"] == "nhc"
