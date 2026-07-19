from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

from scripts.persona_score import (
    apply_persona_scores,
    enhance_persona_output,
    load_personas,
    score_personas,
)


EXPECTED_PERSONAS = {"medical-editor", "policy-analyst", "medical-ai-product-manager"}


def test_persona_scoring_works_without_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_PERSONA_ENABLED", raising=False)

    result = apply_persona_scores(
        {
            "title": "医保局发布飞行检查通知",
            "category": "insurance_compliance",
            "category_label": "医保合规",
            "is_policy": True,
            "is_official": True,
            "importance_score": 0.88,
        }
    )

    assert result["persona_scores"]["policy-analyst"] > 0
    assert result["content_angles"]
    assert 0 <= result["topic_value"] <= 1
    assert len(result["content_angles"]) <= 3


def test_missing_persona_directory_uses_builtin_safe_defaults(tmp_path: Path):
    personas = load_personas(tmp_path / "missing")

    assert {persona.id for persona in personas} == EXPECTED_PERSONAS


def test_invalid_persona_file_falls_back_for_that_role(tmp_path: Path):
    directory = tmp_path / "personas"
    directory.mkdir()
    (directory / "policy-analyst.md").write_text("---\nid: [\n---\n", encoding="utf-8")

    personas = load_personas(directory)

    assert {persona.id for persona in personas} == EXPECTED_PERSONAS


def test_persona_documents_contain_all_safety_rules():
    required = [
        "不虚构政策文件",
        "不虚构融资金额",
        "不虚构FDA/NMPA批准",
        "不把媒体猜测当成事实",
        "不输出医疗诊断建议",
        "需要核实",
    ]
    paths = sorted(Path("personas").glob("*.md"))

    assert len(paths) == 3
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for phrase in required:
            assert phrase in text


def test_scores_are_deterministic_and_clamped():
    record = {
        "title": "临床决策支持与电子病历产品更新",
        "category": "medical_ai",
        "importance_score": 2,
        "source_count": 12,
    }

    first = score_personas(record)
    second = score_personas(record)

    assert first == second
    assert set(first) == EXPECTED_PERSONAS
    assert all(0 <= score <= 1 for score in first.values())
    assert first["medical-ai-product-manager"] > first["policy-analyst"]


class NeverCalledSession:
    def post(self, *_args, **_kwargs):
        raise AssertionError("DeepSeek must remain disabled without both opt-in variables")


def test_optional_enhancement_is_not_called_without_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("DEEPSEEK_PERSONA_ENABLED", raising=False)
    deterministic = {"content_angles": ["角度一", "角度二"], "persona_scores": {}}

    result = enhance_persona_output({}, deterministic, session=NeverCalledSession())

    assert result == deterministic


class ErrorSession:
    def post(self, *_args, **_kwargs):
        raise RuntimeError("remote failure")


def test_optional_enhancement_failure_keeps_deterministic_output(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_PERSONA_ENABLED", "1")
    deterministic = {"content_angles": ["角度一", "角度二"], "persona_scores": {"medical-editor": 0.8}}

    result = enhance_persona_output({}, deterministic, session=ErrorSession())

    assert result == deterministic


def test_update_news_enrichment_includes_persona_fields(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from scripts.update_news import add_medical_intelligence_fields

    result = add_medical_intelligence_fields(
        {
            "title": "医疗大模型进入临床决策支持",
            "summary": "医院电子病历与辅助诊疗产品",
            "site_id": "medical_media",
            "source_tier": "a",
        }
    )

    assert set(result["persona_scores"]) == EXPECTED_PERSONAS
    assert result["content_angles"]
    assert 0 <= result["topic_value"] <= 1


def test_story_records_preserve_primary_persona_fields():
    from scripts.update_news import build_story_record

    item = {
        "id": "item-1",
        "title": "医疗AI产品更新",
        "url": "https://example.com/item-1",
        "site_id": "medical_media",
        "site_name": "Medical Media",
        "source": "Example",
        "published_at": "2026-07-19T01:00:00Z",
        "category": "medical_ai",
        "category_label": "医疗AI",
        "source_tier": "a",
        "persona_scores": {"medical-editor": 0.7},
        "topic_value": 0.72,
        "content_angles": ["产品视角：核对实际影响"],
    }

    story = build_story_record(
        "story-1",
        [item],
        datetime(2026, 7, 19, 2, 0, tzinfo=timezone.utc),
        24,
    )

    assert story["persona_scores"] == item["persona_scores"]
    assert story["topic_value"] == 0.72
    assert story["content_angles"] == item["content_angles"]
    assert story["primary_item"]["persona_scores"] == item["persona_scores"]
    assert story["sources"][0]["topic_value"] == 0.72
