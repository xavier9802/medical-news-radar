#!/usr/bin/env python3
"""Build the static source registry consumed by sources.html."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.config_loader import load_config
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from config_loader import load_config


UTC = timezone.utc


def utc_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _safe_error(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"https?://[^\s?]+\?[^\s]+", "[request failed]", text, flags=re.I)
    return text[:240]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _source_status_maps(status_payload: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_source_id: dict[str, dict[str, Any]] = {}
    for row in status_payload.get("configured_sources") or []:
        if isinstance(row, dict) and str(row.get("source_id") or "").strip():
            by_source_id[str(row["source_id"])] = row
    by_site_id: dict[str, dict[str, Any]] = {}
    for row in status_payload.get("sites") or []:
        if isinstance(row, dict) and str(row.get("site_id") or "").strip():
            by_site_id[str(row["site_id"])] = row
    return by_source_id, by_site_id


def _archive_latest_map(archive_payload: dict[str, Any]) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    by_source_id: dict[str, tuple[datetime, str]] = {}
    by_legacy_name: dict[tuple[str, str], tuple[datetime, str]] = {}
    rows = archive_payload.get("items") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        raw_time = row.get("published_at") or row.get("first_seen_at") or row.get("last_seen_at")
        parsed = _parse_time(raw_time)
        if not parsed:
            continue
        rendered = str(raw_time)
        source_id = str(row.get("source_id") or "").strip()
        if source_id and (source_id not in by_source_id or parsed > by_source_id[source_id][0]):
            by_source_id[source_id] = (parsed, rendered)
        legacy_key = (
            str(row.get("site_id") or "").strip(),
            str(row.get("source") or row.get("site_name") or "").strip().casefold(),
        )
        if all(legacy_key) and (legacy_key not in by_legacy_name or parsed > by_legacy_name[legacy_key][0]):
            by_legacy_name[legacy_key] = (parsed, rendered)
    return (
        {key: value[1] for key, value in by_source_id.items()},
        {key: value[1] for key, value in by_legacy_name.items()},
    )


def derive_status(source: dict[str, Any], status: dict[str, Any] | None) -> str:
    if not source.get("enabled", True):
        return "disabled"
    if not status:
        return "unknown"
    if status.get("ok") is False:
        return "failed"
    if int(status.get("item_count") or 0) == 0:
        return "warning"
    return "healthy"


def build_source_registry(
    source_config: dict[str, Any],
    status_payload: dict[str, Any] | None,
    archive_payload: dict[str, Any] | None,
    *,
    categories_config: dict[str, Any] | None = None,
    tiers_config: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    status_data = status_payload if isinstance(status_payload, dict) else {}
    archive_data = archive_payload if isinstance(archive_payload, dict) else {}
    categories = categories_config or load_config("categories").data
    tiers = tiers_config or load_config("source-tiers").data
    category_labels = {
        str(row.get("id") or ""): str(row.get("label") or row.get("id") or "")
        for row in categories.get("categories") or []
        if isinstance(row, dict)
    }
    tier_labels = {
        str(tier_id): str(row.get("label") or str(tier_id).upper())
        for tier_id, row in (tiers.get("tiers") or {}).items()
        if isinstance(row, dict)
    }
    by_source_id, by_site_id = _source_status_maps(status_data)
    latest_by_id, latest_by_legacy = _archive_latest_map(archive_data)
    checked_at = str(status_data.get("generated_at") or "") or None
    rows: list[dict[str, Any]] = []

    for source in source_config.get("sources") or []:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("id") or "").strip()
        if not source_id:
            continue
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        legacy_site_id = str(metadata.get("legacy_site_id") or "").strip()
        status = by_source_id.get(source_id) or by_site_id.get(legacy_site_id)
        source_status = derive_status(source, status)
        source_name = str(source.get("name") or source_id)
        latest_item_at = latest_by_id.get(source_id)
        if latest_item_at is None and legacy_site_id:
            latest_item_at = latest_by_legacy.get((legacy_site_id, source_name.casefold()))
        item_count = int((status or {}).get("item_count") or 0) if status else 0
        rows.append(
            {
                "id": source_id,
                "name": source_name,
                "homepage_url": str(source.get("homepage_url") or ""),
                "feed_url": str(source.get("feed_url") or ""),
                "type": str(source.get("type") or ""),
                "category": str(source.get("category") or ""),
                "category_label": category_labels.get(str(source.get("category") or ""), str(source.get("category") or "")),
                "tier": str(source.get("tier") or "c"),
                "tier_label": tier_labels.get(str(source.get("tier") or "c"), str(source.get("tier") or "c").upper()),
                "language": str(source.get("language") or ""),
                "region": str(source.get("region") or ""),
                "enabled": bool(source.get("enabled", True)),
                "featured": bool(source.get("featured", False)),
                "status": source_status,
                "item_count": item_count,
                "last_success_at": (str((status or {}).get("last_success_at") or "") or (checked_at if status and status.get("ok") else None)),
                "last_checked_at": str((status or {}).get("last_checked_at") or "") or checked_at,
                "success_rate": (status or {}).get("success_rate") if status else None,
                "latest_item_at": latest_item_at,
                "response_ms": (status or {}).get("duration_ms") if status else None,
                "error": _safe_error((status or {}).get("error")) if status else "",
            }
        )

    rows.sort(key=lambda row: (not row["featured"], row["category"], row["tier"], row["name"].casefold()))
    statuses = ("healthy", "warning", "failed", "disabled", "unknown")
    counts = {status: sum(1 for row in rows if row["status"] == status) for status in statuses}
    return {
        "generated_at": generated_at or checked_at or utc_iso(),
        "total": len(rows),
        "enabled": sum(1 for row in rows if row["enabled"]),
        **counts,
        "sources": rows,
    }


def write_source_registry(
    output: Path,
    source_config: dict[str, Any],
    status_payload: dict[str, Any] | None,
    archive_payload: dict[str, Any] | None,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    payload = build_source_registry(
        source_config,
        status_payload,
        archive_payload,
        generated_at=generated_at,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Medical News Radar source registry JSON")
    parser.add_argument("--config", default="config/sources.yml", help="Path to sources.yml")
    parser.add_argument("--status", default="data/source-status.json", help="Path to source-status.json")
    parser.add_argument("--archive", default="data/archive.json", help="Path to archive.json")
    parser.add_argument("--output", default="data/source-registry.json", help="Output JSON path")
    args = parser.parse_args()

    source_result = load_config("sources", Path(args.config))
    output = Path(args.output)
    payload = write_source_registry(
        output,
        source_result.data,
        _load_json(Path(args.status)),
        _load_json(Path(args.archive)),
    )
    print(f"Wrote: {output} ({payload['total']} sources)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
