#!/usr/bin/env python3
"""Deterministic medical-industry Persona scoring with an optional safe ranker."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

import requests
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PERSONA_ROOT = REPO_ROOT / "personas"
DEEPSEEK_CHAT_URL = "https://api.deepseek.com/chat/completions"


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    description: str
    focus_categories: tuple[str, ...]
    keywords: tuple[str, ...]
    weights: dict[str, float]
    instructions: str = ""


BUILTIN_PERSONAS: tuple[Persona, ...] = (
    Persona(
        id="medical-editor",
        name="医疗行业内容主编",
        description="判断医疗行业选题价值、受众点击理由、内容形态和标题方向。",
        focus_categories=(
            "policy",
            "medical_ai",
            "primary_care",
            "insurance_compliance",
            "health_it",
            "pharma_device",
            "company_market",
            "global_healthtech",
        ),
        keywords=("发布", "更新", "影响", "政策", "产品", "医院", "行业"),
        weights={"category": 0.15, "importance": 0.35, "multi_source": 0.2, "relevance": 0.2, "official": 0.1},
    ),
    Persona(
        id="policy-analyst",
        name="医疗政策分析师",
        description="核验政策性质、发布机构、适用范围、生效时间与合规影响。",
        focus_categories=("policy", "insurance_compliance", "primary_care", "pharma_device"),
        keywords=("政策", "通知", "办法", "意见", "监管", "飞行检查", "医保", "合规"),
        weights={"category": 0.3, "policy": 0.28, "official": 0.2, "importance": 0.12, "keyword": 0.07, "multi_source": 0.03},
    ),
    Persona(
        id="medical-ai-product-manager",
        name="医疗AI产品负责人",
        description="判断医疗AI产品机会、系统影响、合规价值、运营物料和竞品意义。",
        focus_categories=("medical_ai", "health_it", "insurance_compliance", "primary_care", "global_healthtech"),
        keywords=("医疗AI", "大模型", "HIS", "EMR", "电子病历", "CDSS", "辅助诊疗", "医保合规", "产品"),
        weights={"category": 0.34, "keyword": 0.22, "importance": 0.2, "relevance": 0.12, "multi_source": 0.07, "official": 0.05},
    ),
)


def _clamp(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _parse_persona(path: Path) -> Persona | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) != 3:
        return None
    try:
        metadata = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    if not isinstance(metadata, dict):
        return None
    persona_id = str(metadata.get("id") or "").strip()
    name = str(metadata.get("name") or "").strip()
    categories = metadata.get("focus_categories")
    weights = metadata.get("weights")
    if not persona_id or not name or not isinstance(categories, list) or not isinstance(weights, dict):
        return None
    cleaned_weights = {
        str(key): _clamp(value)
        for key, value in weights.items()
        if str(key) in {"category", "importance", "multi_source", "relevance", "official", "policy", "keyword"}
    }
    if not cleaned_weights:
        return None
    keywords = metadata.get("keywords") if isinstance(metadata.get("keywords"), list) else []
    return Persona(
        id=persona_id,
        name=name,
        description=str(metadata.get("description") or "").strip(),
        focus_categories=tuple(str(value).strip() for value in categories if str(value).strip()),
        keywords=tuple(str(value).strip() for value in keywords if str(value).strip()),
        weights=cleaned_weights,
        instructions=parts[2].strip(),
    )


def load_personas(directory: Path | None = None) -> list[Persona]:
    """Load valid known Persona files and fill any gap with safe defaults."""
    root = Path(directory) if directory is not None else PERSONA_ROOT
    known = {persona.id: persona for persona in BUILTIN_PERSONAS}
    loaded: dict[str, Persona] = {}
    if root.is_dir():
        for path in sorted(root.glob("*.md")):
            persona = _parse_persona(path)
            if persona and persona.id in known:
                loaded[persona.id] = persona
    return [loaded.get(persona.id, persona) for persona in BUILTIN_PERSONAS]


def _multi_source_count(record: dict[str, Any]) -> int:
    for key in ("source_count", "multi_source_count", "duplicate_count", "item_count"):
        try:
            value = int(record.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 1


def score_personas(record: dict[str, Any], personas: list[Persona] | None = None) -> dict[str, float]:
    roles = personas or load_personas()
    category = str(record.get("category") or "")
    text = f"{record.get('title') or ''} {record.get('summary') or ''}".casefold()
    importance = _clamp(record.get("importance_score"))
    relevance = _clamp(record.get("medical_relevance_score", record.get("medical_score")))
    multi_source = _clamp((_multi_source_count(record) - 1) / 3)
    signals = {
        "importance": importance,
        "relevance": relevance,
        "multi_source": multi_source,
        "official": 1.0 if record.get("is_official") else 0.0,
        "policy": 1.0 if record.get("is_policy") else 0.0,
    }
    scores: dict[str, float] = {}
    for persona in roles:
        keyword_hits = sum(1 for keyword in persona.keywords if keyword.casefold() in text)
        values = {
            **signals,
            "category": 1.0 if category in persona.focus_categories else 0.0,
            "keyword": _clamp(keyword_hits / 2),
        }
        raw_score = sum(float(weight) * values.get(signal, 0.0) for signal, weight in persona.weights.items())
        scores[persona.id] = round(_clamp(raw_score), 4)
    return scores


def build_content_angles(record: dict[str, Any], persona_scores: dict[str, float]) -> list[str]:
    """Create at most three verification-safe angles from already known fields."""
    category = str(record.get("category") or "")
    category_label = str(record.get("category_label") or category or "医疗行业")
    angles: list[str] = []
    if record.get("is_policy") or persona_scores.get("policy-analyst", 0) >= 0.55:
        angles.append("政策核验：查阅官方原文，确认发布机构、适用对象、地区与生效时间")
    if category in {"medical_ai", "health_it", "insurance_compliance", "primary_care"} and persona_scores.get("medical-ai-product-manager", 0) >= 0.35:
        angles.append("产品视角：核对其对HIS、EMR、CDSS、医保合规或运营流程的实际影响")
    if _multi_source_count(record) >= 2:
        angles.append(f"多源核验：对照{_multi_source_count(record)}个来源，区分共同事实与媒体推测")
    if record.get("is_official") and len(angles) < 3:
        angles.append("原文优先：以官方来源为事实基线，再补充行业影响和执行边界")
    if len(angles) < 3:
        angles.append(f"编辑视角：围绕“{category_label}”提炼受众价值、冲突点与可核实标题方向")
    if len(angles) < 3 and _clamp(record.get("importance_score")) >= 0.7:
        angles.append("内容形态：优先做带原文链接和事实核验项的快讯或短评")
    return list(dict.fromkeys(angles))[:3]


def enhance_persona_output(
    record: dict[str, Any],
    deterministic: dict[str, Any],
    session: Any | None = None,
) -> dict[str, Any]:
    """Optionally let DeepSeek rank local angle IDs; never accept generated facts."""
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    enabled = os.getenv("DEEPSEEK_PERSONA_ENABLED", "").strip() == "1"
    if not api_key or not enabled:
        return deterministic
    angles = [str(value) for value in deterministic.get("content_angles") or []][:3]
    if not angles:
        return deterministic
    client = session or requests.Session()
    try:
        response = client.post(
            DEEPSEEK_CHAT_URL,
            timeout=(5, 15),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": os.getenv("DEEPSEEK_PERSONA_MODEL", "deepseek-v4-flash"),
                "messages": [
                    {
                        "role": "system",
                        "content": "只对候选角度编号排序，不生成或改写事实。仅返回JSON：{\"selected_angle_indexes\":[0]}。",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "category": record.get("category"),
                                "is_policy": bool(record.get("is_policy")),
                                "is_official": bool(record.get("is_official")),
                                "importance_score": _clamp(record.get("importance_score")),
                                "candidate_angles": list(enumerate(angles)),
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                "response_format": {"type": "json_object"},
                "stream": False,
            },
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        selected = json.loads(content).get("selected_angle_indexes")
        if not isinstance(selected, list):
            return deterministic
        indexes: list[int] = []
        for value in selected:
            if isinstance(value, int) and 0 <= value < len(angles) and value not in indexes:
                indexes.append(value)
        if not indexes:
            return deterministic
        enhanced = copy.deepcopy(deterministic)
        enhanced["content_angles"] = [angles[index] for index in indexes[:3]]
        enhanced["persona_enhanced"] = True
        return enhanced
    except Exception:
        return deterministic


def apply_persona_scores(record: dict[str, Any], personas: list[Persona] | None = None) -> dict[str, Any]:
    out = dict(record)
    scores = score_personas(out, personas=personas)
    importance = _clamp(out.get("importance_score"))
    topic_value = _clamp((max(scores.values(), default=0.0) * 0.75) + (importance * 0.25))
    deterministic = {
        "persona_scores": scores,
        "topic_value": round(topic_value, 4),
        "content_angles": build_content_angles(out, scores),
        "persona_enhanced": False,
    }
    out.update(enhance_persona_output(out, deterministic))
    return out
