#!/usr/bin/env python3
"""Explainable medical/healthcare relevance scoring for news records."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from scripts.config_loader import load_all_configs, reset_config_cache
except ModuleNotFoundError:  # pragma: no cover - direct script imports
    from config_loader import load_all_configs, reset_config_cache

MEDICAL_KEYWORDS = [
    "clinical",
    "patient",
    "hospital",
    "doctor",
    "physician",
    "nurse",
    "surgery",
    "surgical",
    "treatment",
    "therapy",
    "diagnosis",
    "diagnostic",
    "disease",
    "disorder",
    "syndrome",
    "symptom",
    "epidemiology",
    "outbreak",
    "pandemic",
    "public health",
    "vaccine",
    "vaccination",
    "immunization",
    "drug",
    "medication",
    "pharmaceutical",
    "fda",
    "ema",
    "nmpa",
    "cdc",
    "nih",
    "who",
    "clinical trial",
    "phase i",
    "phase ii",
    "phase iii",
    "oncology",
    "cancer",
    "tumor",
    "cardiology",
    "cardiovascular",
    "neurology",
    "neuroscience",
    "infectious disease",
    "virology",
    "bacteria",
    "antibiotic",
    "antimicrobial resistance",
    "diabetes",
    "rare disease",
    "genomics",
    "precision medicine",
    "personalized medicine",
    "medical device",
    "medtech",
    "digital health",
    "telemedicine",
    "health it",
    "emr",
    "ehr",
    "medical imaging",
    "radiology",
    "pathology",
    "biotech",
    "biosimilar",
    "generic drug",
    "pharmacovigilance",
    "adverse event",
    "who",
    "cdc",
    "nih",
    "ema",
    "nmpa",
    "clinical",
    "临床",
    "患者",
    "医院",
    "医生",
    "医师",
    "护士",
    "手术",
    "治疗",
    "诊断",
    "疾病",
    "症状",
    "流行病",
    "疫情",
    "疫苗",
    "接种",
    "药物",
    "药品",
    "制药",
    "肿瘤",
    "癌症",
    "心血管",
    "神经",
    "传染病",
    "病毒",
    "抗生素",
    "耐药",
    "糖尿病",
    "罕见病",
    "基因组",
    "精准医疗",
    "医疗器械",
    "数字医疗",
    "远程医疗",
    "医疗信息化",
    "医学影像",
    "病理",
    "生物技术",
    "仿制药",
    "不良反应",
    "药监局",
    "卫健委",
    "疾控中心",
    "世界卫生",
    "美国国立卫生",
    "国立卫生研究院",
]

HEALTH_TECH_KEYWORDS = [
    "digital health",
    "health tech",
    "medtech",
    "medical device",
    "wearable",
    "telehealth",
    "telemedicine",
    "ehr",
    "emr",
    "his",
    "lis",
    "pacs",
    "interoperability",
    "fhir",
    "health data",
    "ai in healthcare",
    "medical ai",
    "diagnostic ai",
    "imaging ai",
    "cdss",
    "clinical decision support",
    "remote monitoring",
    "rpm",
    "mhealth",
    "health app",
    "patient portal",
    "himss",
    "biomedical engineering",
    "health informatics",
    "genomics",
    "sequencing",
    "crispr",
    "gene therapy",
    "cell therapy",
    "regenerative medicine",
    "数字医疗",
    "医疗科技",
    "医疗器械",
    "可穿戴",
    "远程医疗",
    "电子病历",
    "医院信息系统",
    "互联互通",
    "医疗数据",
    "医疗ai",
    "医学影像ai",
    "临床决策支持",
    "远程监测",
    "移动医疗",
    "患者门户",
    "生物医学工程",
    "健康信息学",
    "基因测序",
    "基因治疗",
    "细胞治疗",
]

NOISE_KEYWORDS = [
    "娱乐",
    "明星",
    "八卦",
    "足球",
    "篮球",
    "彩票",
    "情感",
    "旅游",
    "美食",
    "减肥",
    "美容",
    "整容",
    "养生秘方",
    "偏方",
]

COMMERCE_NOISE_KEYWORDS = [
    "淘宝",
    "天猫",
    "京东",
    "拼多多",
    "券后",
    "热销总榜",
    "促销",
    "优惠",
    "补贴",
    "下单",
    "首发价",
    "代购",
]

TOPHUB_ALLOW_KEYWORDS = [
    "丁香园",
    "医学界",
    "动脉网",
    "健康界",
    "医药魔方",
    "药智网",
    "生物探索",
    "梅斯医学",
    "中国医学论坛报",
    "medscape",
    "healthcare",
    "medical",
    "临床",
    "医院",
    "医生",
]

TOPHUB_BLOCK_KEYWORDS = [
    "热销总榜",
    "淘宝",
    "天猫",
    "京东",
    "拼多多",
    "抖音",
    "快手",
    "微博",
    "小红书",
    "娱乐",
    "体育",
    "汽车",
    "房产",
]

EN_SIGNAL_RE = re.compile(
    r"(?i)(?<![a-z0-9])(medical|health|healthcare|clinical|patient|hospital|physician|doctor|diagnosis|treatment|vaccine|drug|pharma|fda|who|cdc|nih|trial|oncology|cardiology|neurology|medtech|digital health|telemedicine)(?![a-z0-9])"
)
MEANINGFUL_EN_SIGNAL_RE = re.compile(
    r"(?i)(?<![a-z0-9])(medical|healthcare|clinical|patient|hospital|physician|doctor|diagnosis|treatment|vaccine|drug|pharma|fda|who|cdc|nih|oncology|cardiology|neurology|medtech|digital health|telemedicine)(?![a-z0-9])"
)
BROAD_MEDICAL_TERMS = {"health", "医疗", "健康", "医药"}
MEDICAL_RELEVANCE_THRESHOLD = 0.65

SOURCE_PRIORS = {
    "official_health": 0.35,
    "medical_journals": 0.18,
    "medical_media": 0.18,
    "healthtech_hub": 0.45,
    "opmlrss": 0.15,
    "xapi": 0.15,
    "socialdata_x": 0.15,
}
MEDICAL_DEFAULT_SOURCES = {"healthtech_hub"}
TRUSTED_JOURNAL_SOURCE_KEYWORDS = [
    "nejm",
    "the lancet",
    "jama",
    "bmj",
    "nature medicine",
    "cell",
    "science translational medicine",
]
TRUSTED_MEDIA_SOURCE_KEYWORDS = [
    "medscape",
    "healthcare it news",
    "himss",
    "fierce healthcare",
    "stat news",
]
RESEARCH_TERMS = [
    "paper",
    "study",
    "research",
    "journal",
    "clinical trial",
    "randomized",
    "cohort",
    "meta-analysis",
    "nejm",
    "lancet",
    "jama",
    "bmj",
    "论文",
    "研究",
    "临床试验",
    "队列",
    "荟萃分析",
]
BUSINESS_TERMS = [
    "funding",
    "raises",
    "raised",
    "startup",
    "acquire",
    "acquisition",
    "merger",
    "revenue",
    "enterprise",
    "ipo",
    "valuation",
    "partnership",
    "融资",
    "收购",
    "并购",
    "合作",
    "估值",
]

LABEL_KEYWORDS = [
    ("drug_trial", ["drug", "pharmaceutical", "medication", "clinical trial", "phase i", "phase ii", "phase iii", "nda", "bla", "approval", "药物", "药品", "临床试验", "获批", "上市", "新药"]),
    ("medical_device", ["medical device", "medtech", "wearable", "diagnostic equipment", "医疗器械", "医疗设备", "可穿戴"]),
    ("public_health", ["public health", "epidemic", "outbreak", "pandemic", "vaccination", "who", "cdc", "公共卫生", "疫情", "疫苗接种", "疾控"]),
    ("regulatory_policy", ["fda", "ema", "nmpa", "regulation", "guideline", "policy", "监管", "指南", "政策", "药监局", "批准"]),
    ("hospital_digital", ["hospital", "ehr", "emr", "his", "digital health", "telemedicine", "医院", "电子病历", "远程医疗", "数字医疗"]),
    ("research_paper", ["paper", "study", "research", "journal", "nejm", "lancet", "jama", "bmj", "论文", "研究", "期刊"]),
    ("industry_business", ["funding", "acquisition", "merger", "ipo", "partnership", "融资", "收购", "并购", "合作", "估值"]),
    ("ai_healthcare", ["ai in healthcare", "medical ai", "diagnostic ai", "imaging ai", "health ai", "医疗ai", "人工智能", "医学影像ai", "智能诊断"]),
]


_MEDICAL_CONFIG_CACHE: dict[str, dict[str, Any]] = {}


def load_medical_config(config_dir: Path | None = None, *, force_reload: bool = False) -> dict[str, Any]:
    """Load and flatten the medical configuration used by deterministic scoring."""
    cache_key = str(Path(config_dir).resolve(strict=False)) if config_dir is not None else "__default__"
    if force_reload:
        reset_config_cache()
        _MEDICAL_CONFIG_CACHE.pop(cache_key, None)
    if cache_key in _MEDICAL_CONFIG_CACHE:
        return _MEDICAL_CONFIG_CACHE[cache_key]

    loaded = load_all_configs(config_dir)
    keyword_rows: list[dict[str, Any]] = []
    for group, rows in loaded["keywords"].data.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                keyword_rows.append({**row, "group": group})

    config = {
        "categories": [row for row in loaded["categories"].data.get("categories", []) if row.get("enabled", True)],
        "keywords": keyword_rows,
        "scoring": loaded["scoring"].data,
        "tiers": loaded["source-tiers"].data.get("tiers", {}),
        "sources": loaded["sources"].data.get("sources", []),
        "errors": tuple(error for result in loaded.values() for error in result.errors),
    }
    _MEDICAL_CONFIG_CACHE[cache_key] = config
    return config


def source_authority_score(source_tier: str, config: dict[str, Any] | None = None) -> float:
    """Return the configured source authority with compatibility aliases."""
    aliases = {
        "official": "s",
        "medical_journal": "a",
        "medical_media": "a",
        "curated": "a",
        "community": "b",
        "builders": "b",
        "user_opml": "c",
        "self_media": "c",
        "advanced": "c",
        "discussion": "c",
        "other": "c",
    }
    tier_id = aliases.get(str(source_tier or "").strip().lower(), str(source_tier or "c").strip().lower())
    tiers = (config or load_medical_config()).get("tiers", {})
    row = tiers.get(tier_id) if isinstance(tiers, dict) else None
    try:
        return max(0.0, min(1.0, float((row or {}).get("authority_score", 0.38))))
    except (TypeError, ValueError):
        return 0.38


def _matching_config_keywords(text: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    haystack = text.lower()
    return [
        row
        for row in config.get("keywords", [])
        if row.get("enabled", True)
        and str(row.get("term") or "").strip()
        and str(row["term"]).lower() in haystack
    ]


def classify_medical_category(
    title: str,
    summary: str = "",
    *,
    source: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify a record into one of the eight configured medical categories."""
    cfg = config or load_medical_config()
    categories = list(cfg.get("categories") or [])
    scores = {str(row["id"]): 0.0 for row in categories}
    evidence: dict[str, list[str]] = {category_id: [] for category_id in scores}
    matches = _matching_config_keywords(f"{title} {summary}", cfg)
    for match in matches:
        try:
            weight = float(match.get("weight") or 0)
        except (TypeError, ValueError):
            weight = 0.0
        for category_id in match.get("categories") or []:
            if category_id not in scores:
                continue
            scores[category_id] += max(0.0, weight)
            term = str(match.get("term") or "")
            if term and term not in evidence[category_id]:
                evidence[category_id].append(term)

    source_meta = source or {}
    source_category = str(source_meta.get("category") or "").strip()
    if source_category in scores:
        scores[source_category] += 0.2

    category_by_id = {str(row["id"]): row for row in categories}
    if not categories:
        return {
            "category": "company_market",
            "category_label": "企业动态",
            "category_scores": {},
            "matched_keywords": [],
        }

    winner_id = max(
        scores,
        key=lambda category_id: (
            scores[category_id],
            -int(category_by_id[category_id].get("order") or 999),
        ),
    )
    if scores[winner_id] <= 0:
        winner_id = source_category if source_category in scores else "company_market"
        if winner_id not in scores:
            winner_id = str(categories[0]["id"])
    winner = category_by_id[winner_id]
    return {
        "category": winner_id,
        "category_label": str(winner.get("label") or winner_id),
        "category_scores": {key: round(max(0.0, min(1.0, value)), 4) for key, value in scores.items()},
        "matched_keywords": evidence.get(winner_id, []),
    }


def detect_noise(title: str, summary: str = "", *, config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_medical_config()
    matches = [row for row in _matching_config_keywords(f"{title} {summary}", cfg) if row.get("group") == "noise_keywords"]
    weighted = 0.0
    terms: list[str] = []
    for row in matches:
        term = str(row.get("term") or "")
        if term and term not in terms:
            terms.append(term)
        try:
            weighted += float(row.get("weight") or 0)
        except (TypeError, ValueError):
            continue
    return {
        "noise_score": round(max(0.0, min(1.0, weighted / 2)), 4),
        "matched_keywords": terms,
        "groups": ["noise_keywords"] if terms else [],
    }


def detect_policy_signal(
    title: str,
    summary: str = "",
    *,
    source: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or load_medical_config()
    source_meta = source or {}
    matches = [row for row in _matching_config_keywords(f"{title} {summary}", cfg) if row.get("group") == "policy_keywords"]
    terms = list(dict.fromkeys(str(row.get("term") or "") for row in matches if row.get("term")))
    policy_markers = ("政策", "监管", "征求意见", "行政处罚", "办法", "规定", "guideline", "regulation")
    text = f"{title} {summary}".lower()
    for marker in policy_markers:
        if marker.lower() in text and marker not in terms:
            terms.append(marker)
    tier = str(source_meta.get("tier") or source_meta.get("source_tier") or "").lower()
    is_official = bool(
        source_meta.get("official")
        or source_meta.get("is_official")
        or tier in {"s", "official"}
        or str(source_meta.get("site_id") or "") == "official_health"
    )
    supplied = metadata or source_meta.get("policy_metadata") or {}
    if not isinstance(supplied, dict):
        supplied = {}
    policy_metadata = {
        "document_number": str(supplied.get("document_number") or ""),
        "issuing_authority": str(supplied.get("issuing_authority") or ""),
        "jurisdiction": str(supplied.get("jurisdiction") or ""),
        "policy_level": str(supplied.get("policy_level") or ""),
        "publish_date": str(supplied.get("publish_date") or ""),
        "effective_date": str(supplied.get("effective_date") or ""),
        "status": str(supplied.get("status") or ""),
        "affected_entities": list(supplied.get("affected_entities") or []),
        "regions": list(supplied.get("regions") or []),
        "topics": list(supplied.get("topics") or []),
    }
    return {
        "is_policy": bool(terms),
        "is_official": is_official,
        "matched_keywords": terms,
        "policy_metadata": policy_metadata,
    }


def _recency_component(published_at: str | datetime | None, now: datetime | None = None) -> float:
    if not published_at:
        return 0.5
    if isinstance(published_at, datetime):
        published = published_at
    else:
        try:
            published = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
        except ValueError:
            return 0.5
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    age_hours = max(0.0, (reference - published.astimezone(timezone.utc)).total_seconds() / 3600)
    return max(0.0, min(1.0, 1 - age_hours / 72))


def calculate_importance_score(
    *,
    title: str,
    summary: str = "",
    source: str = "",
    source_tier: str = "c",
    published_at: str | datetime | None = None,
    multi_source_count: int = 1,
    is_official: bool = False,
    category: str | None = None,
    medical_relevance_score: float | None = None,
    impact_score: float | None = None,
    policy_metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or load_medical_config()
    category_result = classify_medical_category(title, summary, source={"category": category or ""}, config=cfg)
    selected_category = category or category_result["category"]
    policy = detect_policy_signal(
        title,
        summary,
        source={"tier": source_tier, "official": is_official, "name": source},
        metadata=policy_metadata,
        config=cfg,
    )
    noise = detect_noise(title, summary, config=cfg)
    authority = source_authority_score(source_tier, cfg)
    relevance = max(0.0, min(1.0, float(medical_relevance_score if medical_relevance_score is not None else 0.5)))
    impact_defaults = {
        "policy": 0.85,
        "medical_ai": 0.75,
        "primary_care": 0.70,
        "insurance_compliance": 0.80,
        "health_it": 0.65,
        "pharma_device": 0.75,
        "company_market": 0.55,
        "global_healthtech": 0.65,
    }
    impact = max(0.0, min(1.0, float(impact_score if impact_score is not None else impact_defaults.get(selected_category, 0.5))))
    recency = _recency_component(published_at, now)
    heat = max(0.0, min(1.0, (max(1, int(multi_source_count)) - 1) / 4))
    scoring = cfg.get("scoring", {})
    weights = scoring.get("weights", {})
    bonuses = scoring.get("bonuses", {})
    components = {
        "authority": authority,
        "medical_relevance": relevance,
        "impact": impact,
        "recency": recency,
        "multi_source_heat": heat,
    }
    base = sum(float(weights.get(name, 0)) * value for name, value in components.items())
    applied_bonuses: dict[str, float] = {}
    if policy["is_policy"] and policy["is_official"]:
        applied_bonuses["official_policy"] = float(bonuses.get("official_policy", 0))
    if policy["policy_metadata"].get("effective_date"):
        applied_bonuses["effective_date_present"] = float(bonuses.get("effective_date_present", 0))
    if policy["policy_metadata"].get("policy_level") in {"national", "国家", "国家级"}:
        applied_bonuses["national_level"] = float(bonuses.get("national_level", 0))
    if selected_category == "primary_care":
        applied_bonuses["primary_care_impact"] = float(bonuses.get("primary_care_impact", 0))
    if selected_category == "insurance_compliance":
        applied_bonuses["insurance_compliance_impact"] = float(bonuses.get("insurance_compliance_impact", 0))
    if multi_source_count >= 2:
        applied_bonuses["multi_source"] = float(bonuses.get("multi_source", 0))
    noise_penalty = float(noise["noise_score"]) * 0.35
    score = max(0.0, min(1.0, base + sum(applied_bonuses.values()) - noise_penalty))
    return {
        "impact_score": round(impact, 4),
        "importance_score": round(score, 4),
        "importance_breakdown": {
            **{key: round(value, 4) for key, value in components.items()},
            "bonuses": {key: round(value, 4) for key, value in applied_bonuses.items()},
            "noise_penalty": round(noise_penalty, 4),
        },
    }


def contains_any_keyword(haystack: str, keywords: list[str]) -> bool:
    h = haystack.lower()
    return any(k in h for k in keywords)


def matched_keywords(haystack: str, keywords: list[str]) -> list[str]:
    h = haystack.lower()
    return sorted({k for k in keywords if k in h})


def contains_meaningful_medical_signal(haystack: str) -> bool:
    h = haystack.lower()
    if MEANINGFUL_EN_SIGNAL_RE.search(h):
        return True
    return any(k in h for k in MEDICAL_KEYWORDS if k not in BROAD_MEDICAL_TERMS)


def _label_for_text(text: str, has_tech: bool) -> str:
    for label, keywords in LABEL_KEYWORDS:
        if contains_any_keyword(text, keywords):
            return label
    if has_tech:
        return "health_tech"
    return "medical_general"


def _result(
    *,
    is_medical_related: bool,
    score: float,
    label: str,
    reason: str,
    signals: list[str] | None = None,
    noise: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "is_medical_related": bool(is_medical_related),
        "score": round(max(0.0, min(1.0, score)), 2),
        "label": label,
        "reason": reason,
        "signals": signals or [],
        "noise": noise or [],
    }


def _score_base_medical_relevance(record: dict[str, Any]) -> dict[str, Any]:
    """Return the backward-compatible relevance decision before V1 enrichment."""
    site_id = str(record.get("site_id") or "")
    title = str(record.get("title") or "")
    source = str(record.get("source") or "")
    site_name = str(record.get("site_name") or "")
    url = str(record.get("url") or "")
    try:
        url_host = (urlparse(url).netloc or "").lower()
    except Exception:
        url_host = ""
    text = f"{title} {source} {site_name} {url_host}".lower()

    medical_signals = matched_keywords(text, MEDICAL_KEYWORDS)
    tech_signals = matched_keywords(text, HEALTH_TECH_KEYWORDS)
    noise = matched_keywords(text, NOISE_KEYWORDS) + matched_keywords(text, COMMERCE_NOISE_KEYWORDS)
    source_prior = SOURCE_PRIORS.get(site_id, 0.0)

    if site_id == "tophub":
        source_l = source.lower()
        if contains_any_keyword(source_l, TOPHUB_BLOCK_KEYWORDS):
            return _result(
                is_medical_related=False,
                score=0.05,
                label="noise",
                reason="tophub_blocked_channel",
                signals=medical_signals + tech_signals,
                noise=noise or matched_keywords(source_l, TOPHUB_BLOCK_KEYWORDS),
            )
        if not contains_any_keyword(source_l, TOPHUB_ALLOW_KEYWORDS):
            return _result(
                is_medical_related=False,
                score=0.12,
                label="source_scope_drop",
                reason="tophub_channel_not_in_allowlist",
                signals=medical_signals + tech_signals,
                noise=noise,
            )

    if site_id == "medical_journals":
        source_l = source.lower()
        title_l = title.lower()
        trusted_source = contains_any_keyword(source_l, TRUSTED_JOURNAL_SOURCE_KEYWORDS)
        title_has_medical = contains_meaningful_medical_signal(title_l)
        title_has_broad_medical = contains_any_keyword(title_l, list(BROAD_MEDICAL_TERMS)) or EN_SIGNAL_RE.search(title_l) is not None
        title_has_research = contains_any_keyword(title_l, RESEARCH_TERMS)

        if not (trusted_source or title_has_medical or (title_has_broad_medical and bool(tech_signals))):
            return _result(
                is_medical_related=False,
                score=source_prior + (0.28 if title_has_broad_medical else 0.0),
                label="source_scope_drop",
                reason="journal_requires_medical_title_or_trusted_journal",
                signals=medical_signals + tech_signals,
                noise=noise,
            )

        if title_has_research:
            label = "research_paper"
        elif contains_any_keyword(title_l, BUSINESS_TERMS):
            label = "industry_business"
        else:
            label = _label_for_text(text, bool(tech_signals))
        base = 0.58 if trusted_source else 0.5
        score = source_prior + base + min(0.12, 0.03 * len(medical_signals)) + min(0.08, 0.02 * len(tech_signals))
        if noise and not title_has_medical:
            score -= min(0.16, 0.04 * len(noise))
        return _result(
            is_medical_related=score >= MEDICAL_RELEVANCE_THRESHOLD,
            score=score,
            label=label,
            reason="journal_source_filter",
            signals=medical_signals + tech_signals or ([source_l] if trusted_source else []),
            noise=noise,
        )

    if site_id == "medical_media":
        source_l = source.lower()
        title_l = title.lower()
        trusted_source = contains_any_keyword(source_l, TRUSTED_MEDIA_SOURCE_KEYWORDS)
        title_has_medical = contains_meaningful_medical_signal(title_l)
        title_has_broad_medical = contains_any_keyword(title_l, list(BROAD_MEDICAL_TERMS)) or EN_SIGNAL_RE.search(title_l) is not None

        if not (trusted_source or title_has_medical or (title_has_broad_medical and bool(tech_signals))):
            return _result(
                is_medical_related=False,
                score=source_prior + (0.28 if title_has_broad_medical else 0.0),
                label="source_scope_drop",
                reason="medical_media_requires_medical_title_or_trusted_feed",
                signals=medical_signals + tech_signals,
                noise=noise,
            )

        label = _label_for_text(text, bool(tech_signals))
        base = 0.56 if trusted_source else 0.48
        score = source_prior + base + min(0.12, 0.03 * len(medical_signals)) + min(0.08, 0.02 * len(tech_signals))
        if noise and not title_has_medical:
            score -= min(0.16, 0.04 * len(noise))
        return _result(
            is_medical_related=score >= MEDICAL_RELEVANCE_THRESHOLD,
            score=score,
            label=label,
            reason="medical_media_source_filter",
            signals=medical_signals + tech_signals,
            noise=noise,
        )

    if site_id in MEDICAL_DEFAULT_SOURCES:
        return _result(
            is_medical_related=True,
            score=max(MEDICAL_RELEVANCE_THRESHOLD, 0.72 + source_prior),
            label=_label_for_text(text, bool(tech_signals)),
            reason="trusted_medical_source_default_keep",
            signals=medical_signals or [site_id],
            noise=noise,
        )

    has_medical = contains_meaningful_medical_signal(text)
    has_broad_medical = contains_any_keyword(text, list(BROAD_MEDICAL_TERMS)) or EN_SIGNAL_RE.search(text) is not None
    has_tech = bool(tech_signals)

    if not (has_medical or (has_broad_medical and has_tech)):
        return _result(
            is_medical_related=False,
            score=source_prior + (0.32 if has_broad_medical else 0.0) + (0.08 if has_tech else 0.0),
            label="not_medical",
            reason="missing_meaningful_medical_signal",
            signals=medical_signals + tech_signals,
            noise=noise,
        )

    if contains_any_keyword(text, COMMERCE_NOISE_KEYWORDS) and not has_medical:
        return _result(
            is_medical_related=False,
            score=0.25 + source_prior,
            label="commerce_noise",
            reason="commerce_noise_without_strong_medical_signal",
            signals=medical_signals + tech_signals,
            noise=noise,
        )

    if contains_any_keyword(text, NOISE_KEYWORDS) and not has_medical:
        return _result(
            is_medical_related=False,
            score=0.25 + source_prior,
            label="noise",
            reason="noise_without_strong_medical_signal",
            signals=medical_signals + tech_signals,
            noise=noise,
        )

    score = source_prior + (0.52 if has_medical else 0.34) + min(0.18, 0.04 * len(medical_signals)) + min(0.12, 0.03 * len(tech_signals))
    if noise:
        score -= min(0.18, 0.04 * len(noise))
    if has_broad_medical and has_tech and not has_medical:
        score = max(score, MEDICAL_RELEVANCE_THRESHOLD)
    if has_medical:
        score = max(score, MEDICAL_RELEVANCE_THRESHOLD)

    return _result(
        is_medical_related=True,
        score=score,
        label=_label_for_text(text, has_tech),
        reason="matched_medical_signal" if has_medical else "matched_broad_medical_plus_tech_signal",
        signals=medical_signals + tech_signals,
        noise=noise,
    )


def score_medical_relevance(record: dict[str, Any]) -> dict[str, Any]:
    """Return backward-compatible relevance fields plus medical V1 enrichment."""
    base = _score_base_medical_relevance(record)
    title = str(record.get("title") or "")
    summary = str(record.get("summary") or "")
    source_meta = dict(record.get("source_metadata") or {}) if isinstance(record.get("source_metadata"), dict) else {}
    for key in ("category", "source_tier", "tier", "official", "is_official", "site_id", "policy_metadata"):
        if key in record and key not in source_meta:
            source_meta[key] = record[key]
    source_meta.setdefault("name", str(record.get("source") or record.get("site_name") or ""))
    category = classify_medical_category(title, summary, source=source_meta)
    noise = detect_noise(title, summary)
    policy = detect_policy_signal(title, summary, source=source_meta)
    tier = str(record.get("source_tier") or record.get("tier") or ("s" if record.get("site_id") == "official_health" else "c"))
    importance = calculate_importance_score(
        title=title,
        summary=summary,
        source=str(record.get("source") or record.get("site_name") or ""),
        source_tier=tier,
        published_at=record.get("published_at"),
        multi_source_count=int(record.get("multi_source_count") or record.get("source_count") or 1),
        is_official=policy["is_official"],
        category=category["category"],
        medical_relevance_score=float(base["score"]),
        policy_metadata=policy["policy_metadata"],
    )
    return {
        **base,
        "medical_relevance_score": base["score"],
        "category": category["category"],
        "category_label": category["category_label"],
        "category_scores": category["category_scores"],
        "impact_score": importance["impact_score"],
        "importance_score": importance["importance_score"],
        "importance_breakdown": importance["importance_breakdown"],
        "is_policy": policy["is_policy"],
        "is_policy_signal": policy["is_policy"],
        "is_official": policy["is_official"],
        "policy_metadata": policy["policy_metadata"],
        "noise_score": noise["noise_score"],
        "matched_keywords": list(dict.fromkeys([*category["matched_keywords"], *base["signals"]])),
        "source_authority_score": source_authority_score(tier),
    }


def is_medical_related_record(record: dict[str, Any]) -> bool:
    return bool(score_medical_relevance(record)["is_medical_related"])


def add_medical_relevance_fields(
    record: dict[str, Any],
    source_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scoring_input = dict(record)
    if source_meta:
        scoring_input["source_metadata"] = dict(source_meta)
    relevance = score_medical_relevance(scoring_input)
    out = dict(record)
    out["medical_is_related"] = relevance["is_medical_related"]
    out["medical_score"] = relevance["score"]
    out["medical_label"] = relevance["label"]
    out["medical_relevance_reason"] = relevance["reason"]
    out["medical_signals"] = relevance["signals"]
    out["medical_noise"] = relevance["noise"]
    for key in (
        "medical_relevance_score",
        "category",
        "category_label",
        "category_scores",
        "impact_score",
        "importance_score",
        "importance_breakdown",
        "is_policy",
        "is_policy_signal",
        "is_official",
        "policy_metadata",
        "noise_score",
        "matched_keywords",
        "source_authority_score",
    ):
        out[key] = relevance[key]
    return out
