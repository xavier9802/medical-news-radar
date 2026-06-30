#!/usr/bin/env python3
"""Explainable medical/healthcare relevance scoring for news records."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

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


def score_medical_relevance(record: dict[str, Any]) -> dict[str, Any]:
    """Return an explainable medical relevance score."""
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


def is_medical_related_record(record: dict[str, Any]) -> bool:
    return bool(score_medical_relevance(record)["is_medical_related"])


def add_medical_relevance_fields(record: dict[str, Any]) -> dict[str, Any]:
    relevance = score_medical_relevance(record)
    out = dict(record)
    out["medical_is_related"] = relevance["is_medical_related"]
    out["medical_score"] = relevance["score"]
    out["medical_label"] = relevance["label"]
    out["medical_relevance_reason"] = relevance["reason"]
    out["medical_signals"] = relevance["signals"]
    out["medical_noise"] = relevance["noise"]
    return out
