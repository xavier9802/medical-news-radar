from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from scripts.validate_deployment import REQUIRED_JSON_FILES, REQUIRED_STATIC_FILES, validate_site


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _valid_site(root: Path, generated_at: datetime | None = None) -> Path:
    for relative in REQUIRED_STATIC_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok", encoding="utf-8")

    timestamp = (generated_at or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")
    payloads = {
        "data/latest-24h.json": {
            "generated_at": timestamp,
            "total_items": 1,
            "items": [{"title": "Medical update"}],
            "all_mode_data_url": "data/latest-24h-all.json",
            "stories_data_url": "data/stories-merged.json",
        },
        "data/latest-24h-all.json": {"total_items_all_mode": 1, "items_all": [{"title": "Medical update"}]},
        "data/source-status.json": {"successful_sites": 1, "sites": [{"site_id": "official_health", "ok": True}]},
        "data/source-registry.json": {"sources": []},
        "data/daily-brief.json": {"items": []},
        "data/stories-merged.json": {"stories": []},
        "data/merge-log.json": {"events": []},
        "data/archive.json": {"items": []},
    }
    assert set(payloads) == set(REQUIRED_JSON_FILES)
    for relative, payload in payloads.items():
        _write_json(root / relative, payload)
    return root


def test_valid_generated_site_is_publishable(tmp_path):
    root = _valid_site(tmp_path)

    assert validate_site(root, max_age_hours=6) == []


def test_missing_required_file_blocks_deployment(tmp_path):
    root = _valid_site(tmp_path)
    (root / "data/daily-brief.json").unlink()

    errors = validate_site(root)

    assert "Missing required deployment file: data/daily-brief.json" in errors


def test_zero_successful_sources_blocks_replacing_production(tmp_path):
    root = _valid_site(tmp_path)
    _write_json(root / "data/source-status.json", {"successful_sites": 0, "sites": [{"site_id": "official_health"}]})

    errors = validate_site(root)

    assert any("zero successful source groups" in error for error in errors)


def test_stale_snapshot_blocks_deployment(tmp_path):
    now = datetime(2026, 7, 20, 16, 0, tzinfo=timezone.utc)
    root = _valid_site(tmp_path, generated_at=now - timedelta(hours=7))

    errors = validate_site(root, max_age_hours=6, now=now)

    assert any("data is stale" in error for error in errors)


def test_count_mismatch_blocks_deployment(tmp_path):
    root = _valid_site(tmp_path)
    latest = json.loads((root / "data/latest-24h.json").read_text(encoding="utf-8"))
    latest["total_items"] = 2
    _write_json(root / "data/latest-24h.json", latest)

    errors = validate_site(root)

    assert any("does not match items length" in error for error in errors)
