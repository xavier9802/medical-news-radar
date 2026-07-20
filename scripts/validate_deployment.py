#!/usr/bin/env python3
"""Validate a generated Medical News Radar site before publishing it."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse

REQUIRED_STATIC_FILES = (
    "index.html",
    "sources.html",
    "assets/app.js",
    "assets/runtime-config.js",
    "assets/sources.js",
)

REQUIRED_JSON_FILES = (
    "data/latest-24h.json",
    "data/latest-24h-all.json",
    "data/source-status.json",
    "data/source-registry.json",
    "data/daily-brief.json",
    "data/stories-merged.json",
    "data/merge-log.json",
    "data/archive.json",
)


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_json(path: Path, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Invalid JSON {path}: {exc}")
        return None


def _validate_count(payload: dict[str, Any], count_key: str, items_key: str, label: str, errors: list[str]) -> None:
    items = payload.get(items_key)
    if not isinstance(items, list):
        errors.append(f"{label}.{items_key} must be a list")
        return
    count = payload.get(count_key)
    if not isinstance(count, int):
        errors.append(f"{label}.{count_key} must be an integer")
    elif count != len(items):
        errors.append(f"{label}.{count_key}={count} does not match {items_key} length {len(items)}")


def _validate_local_json_reference(root: Path, raw_value: Any, field_name: str, errors: list[str]) -> None:
    value = str(raw_value or "").strip()
    if not value:
        return
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or parsed.path.startswith("/") or ".." in Path(parsed.path).parts:
        errors.append(f"{field_name} must reference a repository-local JSON path: {value}")
        return
    target = root / parsed.path
    if target.suffix.lower() != ".json" or not target.is_file():
        errors.append(f"{field_name} references a missing JSON file: {value}")


def validate_site(
    site_root: Path,
    *,
    max_age_hours: float | None = None,
    now: datetime | None = None,
) -> list[str]:
    """Return deployment validation errors; an empty list means publishable."""
    root = Path(site_root)
    errors: list[str] = []

    for relative in REQUIRED_STATIC_FILES + REQUIRED_JSON_FILES:
        if not (root / relative).is_file():
            errors.append(f"Missing required deployment file: {relative}")

    payloads: dict[str, Any] = {}
    for relative in REQUIRED_JSON_FILES:
        path = root / relative
        if path.is_file():
            payloads[relative] = _load_json(path, errors)

    latest = payloads.get("data/latest-24h.json")
    if isinstance(latest, dict):
        _validate_count(latest, "total_items", "items", "latest-24h", errors)
        _validate_local_json_reference(root, latest.get("all_mode_data_url"), "all_mode_data_url", errors)
        _validate_local_json_reference(root, latest.get("stories_data_url"), "stories_data_url", errors)

        generated_at = _parse_timestamp(latest.get("generated_at"))
        if generated_at is None:
            errors.append("latest-24h.generated_at must be a valid ISO-8601 timestamp")
        elif max_age_hours is not None and max_age_hours > 0:
            current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
            age_hours = (current - generated_at).total_seconds() / 3600
            if age_hours < -0.25:
                errors.append(f"latest-24h.generated_at is in the future by {-age_hours:.2f} hours")
            elif age_hours > max_age_hours:
                errors.append(f"latest-24h data is stale: {age_hours:.2f} hours old")
    elif latest is not None:
        errors.append("data/latest-24h.json must contain a JSON object")

    latest_all = payloads.get("data/latest-24h-all.json")
    if isinstance(latest_all, dict):
        items_key = "items_all" if "items_all" in latest_all else "items"
        count_key = "total_items_all_mode" if "total_items_all_mode" in latest_all else "total_items"
        _validate_count(latest_all, count_key, items_key, "latest-24h-all", errors)
    elif latest_all is not None:
        errors.append("data/latest-24h-all.json must contain a JSON object")

    status = payloads.get("data/source-status.json")
    if isinstance(status, dict):
        sites = status.get("sites")
        if not isinstance(sites, list) or not sites:
            errors.append("source-status.sites must contain at least one source group")
        successful = status.get("successful_sites")
        if not isinstance(successful, int):
            errors.append("source-status.successful_sites must be an integer")
        elif successful < 1:
            errors.append("source-status reports zero successful source groups; refusing to replace production")
    elif status is not None:
        errors.append("data/source-status.json must contain a JSON object")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-root", type=Path, default=Path("."))
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=None,
        help="Reject latest-24h.json when generated_at is older than this many hours.",
    )
    args = parser.parse_args(argv)

    errors = validate_site(args.site_root, max_age_hours=args.max_age_hours)
    if errors:
        print("Deployment validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Deployment validation passed for {args.site_root.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
