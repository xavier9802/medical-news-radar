#!/usr/bin/env python3
"""Defensive YAML configuration loading for Medical News Radar."""

from __future__ import annotations

import copy
import ipaddress
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = REPO_ROOT / "config"

CATEGORY_DEFAULTS: list[dict[str, Any]] = [
    {
        "id": "policy",
        "label": "政策监管",
        "description": "国家及地方医疗政策、监管文件、征求意见、司法案例和行政处罚",
        "order": 10,
        "enabled": True,
    },
    {
        "id": "medical_ai",
        "label": "医疗AI",
        "description": "医疗大模型、临床决策支持、AI诊疗、医学影像AI和医疗智能体",
        "order": 20,
        "enabled": True,
    },
    {
        "id": "primary_care",
        "label": "基层医疗",
        "description": "诊所、社区卫生、乡镇卫生院、家庭医生、中医馆和基层医生",
        "order": 30,
        "enabled": True,
    },
    {
        "id": "insurance_compliance",
        "label": "医保合规",
        "description": "医保支付、飞行检查、基金监管、追溯码、处方和收费合规",
        "order": 40,
        "enabled": True,
    },
    {
        "id": "health_it",
        "label": "医疗信息化",
        "description": "HIS、EMR、电子病历、互联网医院、数据治理和医疗信息安全",
        "order": 50,
        "enabled": True,
    },
    {
        "id": "pharma_device",
        "label": "医药器械",
        "description": "药品、医疗器械、NMPA、FDA审批、药监和药品追溯",
        "order": 60,
        "enabled": True,
    },
    {
        "id": "company_market",
        "label": "企业动态",
        "description": "融资、并购、企业合作、产品发布、经营数据和行业竞争",
        "order": 70,
        "enabled": True,
    },
    {
        "id": "global_healthtech",
        "label": "海外前沿",
        "description": "海外医疗科技、数字疗法、远程医疗、国际医疗AI和海外监管",
        "order": 80,
        "enabled": True,
    },
]

DEFAULT_CONFIGS: dict[str, dict[str, Any]] = {
    "categories": {"categories": CATEGORY_DEFAULTS},
    "keywords": {
        "strong_keywords": [
            {"term": "医疗AI", "weight": 1.0, "categories": ["medical_ai"], "enabled": True},
            {"term": "医保基金", "weight": 1.0, "categories": ["insurance_compliance"], "enabled": True},
            {"term": "基层医疗", "weight": 1.0, "categories": ["primary_care"], "enabled": True},
            {"term": "医疗信息化", "weight": 1.0, "categories": ["health_it"], "enabled": True},
            {"term": "医疗器械", "weight": 1.0, "categories": ["pharma_device"], "enabled": True},
        ],
        "medium_keywords": [
            {"term": "医院", "weight": 0.45, "categories": ["health_it"], "enabled": True},
            {"term": "医生", "weight": 0.45, "categories": ["primary_care"], "enabled": True},
        ],
        "noise_keywords": [
            {"term": "明星健康", "weight": 0.8, "categories": [], "enabled": True},
            {"term": "养生偏方", "weight": 0.9, "categories": [], "enabled": True},
        ],
    },
    "scoring": {
        "weights": {
            "authority": 0.30,
            "medical_relevance": 0.25,
            "impact": 0.20,
            "recency": 0.15,
            "multi_source_heat": 0.10,
        },
        "thresholds": {"selected": 0.72, "relevant": 0.45, "minimum": 0.25},
        "bonuses": {
            "official_policy": 0.15,
            "effective_date_present": 0.05,
            "national_level": 0.08,
            "primary_care_impact": 0.08,
            "insurance_compliance_impact": 0.08,
            "multi_source": 0.05,
        },
    },
    "source-tiers": {
        "tiers": {
            "s": {"label": "S级", "authority_score": 1.0, "description": "官方政策、监管机构和原始文件"},
            "a": {"label": "A级", "authority_score": 0.82, "description": "权威期刊、行业媒体和企业官方来源"},
            "b": {"label": "B级", "authority_score": 0.62, "description": "综合科技、财经和可靠转载媒体"},
            "c": {"label": "C级", "authority_score": 0.38, "description": "聚合、社交和选题观察来源"},
        }
    },
    "sources": {"sources": []},
}

KNOWN_CONFIGS = tuple(DEFAULT_CONFIGS)
ALLOWED_SOURCE_TYPES = {
    "rss",
    "atom",
    "opml",
    "json",
    "static_page",
    "government_page",
    "journal",
    "company",
    "newsletter",
    "social_observation",
}
ALLOWED_FETCH_STRATEGIES = {"auto", "rss", "json", "html_list", "jina", "skip"}


@dataclass(frozen=True)
class ConfigResult:
    data: dict[str, Any]
    used_fallback: bool
    errors: tuple[str, ...]
    path: Path


class ConfigLoadError(ValueError):
    """Raised when strict configuration loading cannot produce valid data."""


_CONFIG_CACHE: dict[tuple[str, str], ConfigResult] = {}
HOST_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def reset_config_cache() -> None:
    _CONFIG_CACHE.clear()


def _safe_bool(value: Any, default: bool = True) -> bool:
    return value if isinstance(value, bool) else default


def _safe_int(value: Any, default: int, *, minimum: int = 0) -> int:
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float, *, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        return max(minimum, min(maximum, float(value)))
    except (TypeError, ValueError):
        return default


def _safe_public_hosts(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    hosts: list[str] = []
    for raw in value:
        host = str(raw or "").strip().lower().rstrip(".")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            continue
        if HOST_RE.fullmatch(host) and host not in hosts:
            hosts.append(host)
    return hosts


def _require_mapping(payload: Any, root: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ConfigLoadError(f"{root} must be a mapping")
    return payload


def _validate_categories(payload: Any) -> tuple[dict[str, Any], list[str]]:
    root = _require_mapping(payload, "categories")
    rows = root.get("categories")
    if not isinstance(rows, list):
        raise ConfigLoadError("categories must be a list")
    out: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"category row {index} must be a mapping")
            continue
        category_id = str(row.get("id") or "").strip()
        label = str(row.get("label") or "").strip()
        if not category_id or not label or category_id in seen:
            errors.append(f"category row {index} requires a unique id and label")
            continue
        seen.add(category_id)
        out.append(
            {
                "id": category_id,
                "label": label,
                "description": str(row.get("description") or "").strip(),
                "order": _safe_int(row.get("order"), index * 10),
                "enabled": _safe_bool(row.get("enabled"), True),
            }
        )
    if not out:
        raise ConfigLoadError("categories contains no valid rows")
    out.sort(key=lambda row: (row["order"], row["id"]))
    return {"categories": out}, errors


def _validate_keyword_entry(row: Any, group: str, index: int) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(row, dict):
        return None, f"{group} row {index} must be a mapping"
    term = str(row.get("term") or "").strip()
    if not term:
        return None, f"{group} row {index} requires term"
    categories = row.get("categories")
    if not isinstance(categories, list):
        categories = []
    return (
        {
            "term": term,
            "weight": _safe_float(row.get("weight"), 0.5),
            "categories": [str(value).strip() for value in categories if str(value).strip()],
            "enabled": _safe_bool(row.get("enabled"), True),
        },
        None,
    )


def _validate_keywords(payload: Any) -> tuple[dict[str, Any], list[str]]:
    root = _require_mapping(payload, "keywords")
    out: dict[str, list[dict[str, Any]]] = {}
    errors: list[str] = []
    for group, rows in root.items():
        if not isinstance(group, str) or not group.endswith("_keywords") or not isinstance(rows, list):
            continue
        validated: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            entry, error = _validate_keyword_entry(row, group, index)
            if error:
                errors.append(error)
            elif entry:
                validated.append(entry)
        out[group] = validated
    if not out:
        raise ConfigLoadError("keywords contains no keyword groups")
    return out, errors


def _merge_numeric_sections(defaults: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(defaults)
    for section, default_values in defaults.items():
        supplied = payload.get(section)
        if not isinstance(supplied, dict):
            continue
        for key, default_value in default_values.items():
            out[section][key] = _safe_float(supplied.get(key), float(default_value))
    return out


def _validate_scoring(payload: Any) -> tuple[dict[str, Any], list[str]]:
    root = _require_mapping(payload, "scoring")
    return _merge_numeric_sections(DEFAULT_CONFIGS["scoring"], root), []


def _validate_source_tiers(payload: Any) -> tuple[dict[str, Any], list[str]]:
    root = _require_mapping(payload, "source-tiers")
    tiers = root.get("tiers")
    if not isinstance(tiers, dict):
        raise ConfigLoadError("tiers must be a mapping")
    out: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for tier_id, row in tiers.items():
        key = str(tier_id or "").strip().lower()
        if not key or not isinstance(row, dict):
            errors.append("tier rows require an id and mapping")
            continue
        out[key] = {
            "label": str(row.get("label") or key.upper()).strip(),
            "authority_score": _safe_float(row.get("authority_score"), 0.38),
            "description": str(row.get("description") or "").strip(),
        }
    if not out:
        raise ConfigLoadError("tiers contains no valid rows")
    return {"tiers": out}, errors


def _validate_source_row(row: Any, index: int) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(row, dict):
        return None, f"source row {index} must be a mapping"
    source_id = str(row.get("id") or "").strip()
    name = str(row.get("name") or "").strip()
    if not source_id or not name:
        return None, f"source row {index} requires id and name"
    source_type = str(row.get("type") or "rss").strip().lower()
    if source_type not in ALLOWED_SOURCE_TYPES:
        return None, f"source row {index} has unsupported type"
    fetch = row.get("fetch") if isinstance(row.get("fetch"), dict) else {}
    strategy = str(fetch.get("strategy") or "auto").strip().lower()
    if strategy not in ALLOWED_FETCH_STRATEGIES:
        strategy = "skip"
    filters = row.get("filters") if isinstance(row.get("filters"), dict) else {}
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    out = {
        "id": source_id,
        "name": name,
        "homepage_url": str(row.get("homepage_url") or "").strip(),
        "feed_url": str(row.get("feed_url") or "").strip(),
        "type": source_type,
        "category": str(row.get("category") or "").strip(),
        "tier": str(row.get("tier") or "c").strip().lower(),
        "language": str(row.get("language") or "").strip(),
        "region": str(row.get("region") or "").strip(),
        "enabled": _safe_bool(row.get("enabled"), True),
        "featured": _safe_bool(row.get("featured"), False),
        "fetch": {
            "strategy": strategy,
            "interval_hours": _safe_int(fetch.get("interval_hours"), 24, minimum=1),
            "max_items": _safe_int(fetch.get("max_items"), 30, minimum=1),
            "timeout_seconds": _safe_int(fetch.get("timeout_seconds"), 20, minimum=1),
            "parser_profile": str(fetch.get("parser_profile") or "").strip().lower(),
            "allowed_hosts": _safe_public_hosts(fetch.get("allowed_hosts")),
        },
        "filters": {
            "include_keywords": [str(value).strip() for value in filters.get("include_keywords", []) if str(value).strip()]
            if isinstance(filters.get("include_keywords", []), list)
            else [],
            "exclude_keywords": [str(value).strip() for value in filters.get("exclude_keywords", []) if str(value).strip()]
            if isinstance(filters.get("exclude_keywords", []), list)
            else [],
        },
        "metadata": {
            str(key): value
            for key, value in metadata.items()
            if str(key) in {"source_origin", "added_by", "notes", "legacy_site_id"}
        },
    }
    if out["enabled"] and not (out["homepage_url"] or out["feed_url"]):
        return None, f"source row {index} requires a public URL when enabled"
    return out, None


def _validate_sources(payload: Any) -> tuple[dict[str, Any], list[str]]:
    root = _require_mapping(payload, "sources")
    rows = root.get("sources")
    if not isinstance(rows, list):
        raise ConfigLoadError("sources must be a list")
    out: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(rows, start=1):
        source, error = _validate_source_row(row, index)
        if error:
            errors.append(error)
            continue
        assert source is not None
        if source["id"] in seen_ids:
            errors.append(f"source row {index} has a duplicate id")
            continue
        seen_ids.add(source["id"])
        out.append(source)
    return {"sources": out}, errors


VALIDATORS = {
    "categories": _validate_categories,
    "keywords": _validate_keywords,
    "scoring": _validate_scoring,
    "source-tiers": _validate_source_tiers,
    "sources": _validate_sources,
}


def load_config(name: str, path: Path | None = None, *, strict: bool = False) -> ConfigResult:
    if name not in KNOWN_CONFIGS:
        raise KeyError(f"unknown configuration: {name}")
    target = Path(path) if path is not None else CONFIG_ROOT / f"{name}.yml"
    cache_key = (name, str(target.resolve(strict=False)))
    if not strict and cache_key in _CONFIG_CACHE:
        return _CONFIG_CACHE[cache_key]

    try:
        raw = target.read_text(encoding="utf-8")
        try:
            payload = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise ConfigLoadError(f"{target.name}: invalid YAML") from exc
        data, errors = VALIDATORS[name](payload)
        result = ConfigResult(data=data, used_fallback=False, errors=tuple(errors), path=target)
    except Exception as exc:
        message = str(exc) if isinstance(exc, ConfigLoadError) else f"{target.name}: unavailable or invalid"
        if target.name not in message:
            message = f"{target.name}: {message}"
        if strict:
            raise ConfigLoadError(message) from exc
        result = ConfigResult(
            data=copy.deepcopy(DEFAULT_CONFIGS[name]),
            used_fallback=True,
            errors=(message,),
            path=target,
        )

    if not strict:
        _CONFIG_CACHE[cache_key] = result
    return result


def load_all_configs(config_dir: Path | None = None) -> dict[str, ConfigResult]:
    root = Path(config_dir) if config_dir is not None else CONFIG_ROOT
    return {name: load_config(name, root / f"{name}.yml") for name in KNOWN_CONFIGS}


def normalize_feed_url(raw_url: str) -> str:
    text = str(raw_url or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return text
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if not scheme or not host:
        return text
    try:
        port = parts.port
    except ValueError:
        return text
    netloc = host
    if ":" in host and not host.startswith("["):
        netloc = f"[{host}]"
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        netloc = f"{netloc}:{port}"
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((scheme, netloc, path, query, ""))


def dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        feed_url = normalize_feed_url(str(source.get("feed_url") or ""))
        if feed_url:
            if feed_url in seen:
                continue
            seen.add(feed_url)
        out.append(source)
    return out
