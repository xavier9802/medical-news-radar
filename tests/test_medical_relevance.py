import unittest

from scripts.medical_relevance import (
    add_medical_relevance_fields,
    calculate_importance_score,
    classify_medical_category,
    detect_noise,
    detect_policy_signal,
    is_medical_related_record,
    load_medical_config,
    score_medical_relevance,
    source_authority_score,
)


class MedicalRelevanceScoringTests(unittest.TestCase):
    def test_loads_all_eight_medical_categories(self):
        config = load_medical_config(force_reload=True)
        self.assertEqual(
            {row["id"] for row in config["categories"]},
            {
                "policy",
                "medical_ai",
                "primary_care",
                "insurance_compliance",
                "health_it",
                "pharma_device",
                "company_market",
                "global_healthtech",
            },
        )

    def test_classifies_medical_ai_news(self):
        result = classify_medical_category("医疗大模型进入临床决策支持", "医院开始试点")
        self.assertEqual(result["category"], "medical_ai")
        self.assertEqual(result["category_label"], "医疗AI")
        self.assertIn("医疗大模型", result["matched_keywords"])

    def test_classifies_insurance_policy(self):
        result = classify_medical_category("医保飞检聚焦医保基金", "检查处方合规与药品追溯")
        self.assertIn(result["category"], {"insurance_compliance", "policy"})
        self.assertGreater(result["category_scores"]["insurance_compliance"], 0)

    def test_classifies_primary_care_news(self):
        result = classify_medical_category("基层医疗推进家庭医生签约", "社区卫生与乡镇卫生院协同")
        self.assertEqual(result["category"], "primary_care")

    def test_detects_policy_without_inventing_metadata(self):
        result = detect_policy_signal("国家卫生健康委发布征求意见稿", "", source={"tier": "s", "official": True})
        self.assertTrue(result["is_policy"])
        self.assertTrue(result["is_official"])
        self.assertEqual(result["policy_metadata"]["document_number"], "")
        self.assertEqual(result["policy_metadata"]["effective_date"], "")
        self.assertEqual(result["policy_metadata"]["issuing_authority"], "")

    def test_noise_detection_penalizes_celebrity_wellness(self):
        result = detect_noise("明星健康养生偏方直播带货")
        self.assertGreater(result["noise_score"], 0)
        self.assertIn("明星健康", result["matched_keywords"])
        self.assertIn("养生偏方", result["matched_keywords"])

    def test_s_tier_authority_exceeds_b_tier(self):
        self.assertGreater(source_authority_score("s"), source_authority_score("b"))

    def test_importance_score_is_clamped_and_noise_is_lower(self):
        clean = calculate_importance_score(
            title="基层医疗政策发布",
            source_tier="s",
            is_official=True,
            category="primary_care",
            medical_relevance_score=1.0,
            multi_source_count=99,
        )
        noisy = calculate_importance_score(
            title="明星健康养生偏方带货",
            source_tier="b",
            is_official=False,
            medical_relevance_score=0.3,
        )
        self.assertGreater(clean["importance_score"], noisy["importance_score"])
        self.assertGreaterEqual(clean["importance_score"], 0)
        self.assertLessEqual(clean["importance_score"], 1)
        self.assertGreaterEqual(noisy["importance_score"], 0)
        self.assertLessEqual(noisy["importance_score"], 1)

    def test_scores_strong_medical_signal_with_reason(self):
        rec = {
            "site_id": "medical_media",
            "site_name": "Medical Media",
            "source": "Medscape",
            "title": "FDA approves new oncology drug for lung cancer",
            "url": "https://example.com/medical",
        }
        result = score_medical_relevance(rec)
        self.assertTrue(result["is_medical_related"])
        self.assertGreaterEqual(result["score"], 0.65)
        self.assertEqual(result["label"], "drug_trial")
        self.assertIn("fda", result["signals"])
        self.assertIn("medical_media_source_filter", result["reason"])

    def test_rejects_broad_health_without_medical_context(self):
        rec = {
            "site_id": "aggregate",
            "site_name": "Aggregate",
            "source": "general",
            "title": "这个商业模型终于跑通了",
            "url": "https://example.com/model",
        }
        result = score_medical_relevance(rec)
        self.assertFalse(result["is_medical_related"])
        self.assertLess(result["score"], 0.65)
        self.assertEqual(result["reason"], "missing_meaningful_medical_signal")

    def test_accepts_broad_medical_plus_tech_context(self):
        rec = {
            "site_id": "aggregate",
            "site_name": "Aggregate",
            "source": "Tech Blog",
            "title": "医疗数据平台开源框架发布",
            "url": "https://example.com/health-it",
        }
        result = score_medical_relevance(rec)
        self.assertTrue(result["is_medical_related"])
        self.assertGreaterEqual(result["score"], 0.65)
        self.assertEqual(result["reason"], "matched_broad_medical_plus_tech_signal")
        self.assertIn("医疗数据", result["signals"])

    def test_accepts_clinical_context_as_drug_trial(self):
        rec = {
            "site_id": "opmlrss",
            "site_name": "OPML RSS",
            "source": "NEJM",
            "title": "Phase III trial shows new antibody reduces cardiovascular events",
            "url": "https://example.com/cardio-trial",
        }
        result = score_medical_relevance(rec)
        self.assertTrue(result["is_medical_related"])
        self.assertGreaterEqual(result["score"], 0.65)
        self.assertEqual(result["label"], "drug_trial")

    def test_trusted_medical_source_defaults_to_keep(self):
        rec = {
            "site_id": "healthtech_hub",
            "site_name": "HealthTech Hub",
            "source": "HealthTech Hub",
            "title": "今日值得关注的医疗产品更新",
            "url": "https://example.com/healthtech/1",
        }
        result = score_medical_relevance(rec)
        self.assertTrue(result["is_medical_related"])
        self.assertGreaterEqual(result["score"], 0.65)
        self.assertEqual(result["reason"], "trusted_medical_source_default_keep")

    def test_medical_journals_keep_trusted_feed(self):
        rec = {
            "site_id": "medical_journals",
            "site_name": "Medical Journals",
            "source": "NEJM",
            "title": "Health system raises funding for enterprise workflow automation",
            "url": "https://nejm.org/example",
        }
        result = score_medical_relevance(rec)
        self.assertTrue(result["is_medical_related"])
        self.assertEqual(result["reason"], "journal_source_filter")
        self.assertEqual(result["label"], "industry_business")

    def test_medical_journal_requires_medical_title_or_trusted_source(self):
        rec = {
            "site_id": "medical_journals",
            "site_name": "Medical Journals",
            "source": "Some Journal",
            "title": "A new phone accessory launches this week",
            "url": "https://example.com/phone",
        }
        result = score_medical_relevance(rec)
        self.assertFalse(result["is_medical_related"])
        self.assertEqual(result["reason"], "journal_requires_medical_title_or_trusted_journal")

    def test_research_feed_is_research_labeled(self):
        rec = {
            "site_id": "medical_journals",
            "site_name": "Medical Journals",
            "source": "BMJ",
            "title": "A new cohort study evaluates diabetes management in primary care",
            "url": "https://bmj.com/example",
        }
        result = score_medical_relevance(rec)
        self.assertTrue(result["is_medical_related"])
        self.assertEqual(result["label"], "research_paper")

    def test_adds_public_debug_fields(self):
        rec = {
            "site_id": "official_health",
            "site_name": "Official Health Updates",
            "source": "CDC",
            "title": "CDC updates vaccination guidelines for influenza",
            "url": "https://example.com/cdc-vaccine",
        }
        out = add_medical_relevance_fields(rec)
        self.assertTrue(out["medical_is_related"])
        self.assertIn("medical_score", out)
        self.assertIn("medical_label", out)
        self.assertIn("medical_relevance_reason", out)
        self.assertIn("medical_signals", out)
        self.assertIn("medical_relevance_score", out)
        self.assertIn("category", out)
        self.assertIn("category_scores", out)
        self.assertIn("importance_score", out)
        self.assertIn("is_policy", out)
        self.assertIn("policy_metadata", out)
        self.assertTrue(is_medical_related_record(rec))


if __name__ == "__main__":
    unittest.main()
