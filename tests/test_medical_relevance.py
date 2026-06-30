import unittest

from scripts.medical_relevance import (
    add_medical_relevance_fields,
    is_medical_related_record,
    score_medical_relevance,
)


class MedicalRelevanceScoringTests(unittest.TestCase):
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
        self.assertTrue(is_medical_related_record(rec))


if __name__ == "__main__":
    unittest.main()
