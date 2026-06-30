"""Tests for the v0.6.x quality fixes: URL-host-only relevance matching,
same-source decay in the daily brief, and near-duplicate item suppression."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.medical_relevance import score_medical_relevance
from scripts.update_news import select_diverse_stories, suppress_near_duplicate_items


NOW = datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)


class TestUrlHostOnlyRelevance:
    def test_base64_url_path_cannot_fake_medical_signal(self):
        # Real-world case: Google News base64 path contains "drug" by accident.
        rec = {
            "site_id": "aggregate",
            "site_name": "Aggregate",
            "source": "news.google.com",
            "title": "巴勒斯坦人称，以色列定居者阻碍了村庄附近的灭火工作 - Reuters",
            "url": "https://news.google.com/rss/articles/CBMiwgFBVllmRkNCSmxQNnR6WktHcmdMQ2NuNHFjUmlEQk1nTGxsbUFCMEhRaEExWXg3?oc=5",
        }
        result = score_medical_relevance(rec)
        assert not result["is_medical_related"]
        assert result["label"] == "not_medical"

    def test_url_host_still_contributes_signal(self):
        rec = {
            "site_id": "opmlrss",
            "site_name": "OPML RSS",
            "source": "Some Blog",
            "title": "Weekly product update",
            "url": "https://fda.gov/news/weekly-update",
        }
        result = score_medical_relevance(rec)
        assert result["is_medical_related"]

    def test_dotted_medical_styled_title_keeps_signal(self):
        rec = {
            "site_id": "aggregate",
            "site_name": "Aggregate",
            "source": "news.google.com",
            "title": "FDA approves new cancer drug for lung cancer - NYT",
            "url": "https://news.google.com/rss/articles/CCC?oc=5",
        }
        result = score_medical_relevance(rec)
        assert result["is_medical_related"]


def make_story(idx: int, source: str, score: float) -> dict:
    return {
        "story_id": f"story_{idx}",
        "title": f"Story {idx}",
        "source": source,
        "score": score,
    }


class TestSelectDiverseStories:
    def test_one_prolific_source_cannot_fill_the_brief(self):
        stories = [make_story(i, "MedicalMedia", 0.81) for i in range(15)]
        stories += [make_story(100 + i, f"Official {i}", 0.78) for i in range(10)]
        picked = select_diverse_stories(stories, 20)
        medical_media = sum(1 for s in picked if s["source"] == "MedicalMedia")
        assert len(picked) == 20
        assert medical_media < 15
        assert any(s["source"].startswith("Official") for s in picked[:10])

    def test_top_story_always_survives(self):
        stories = [make_story(0, "MedicalMedia", 0.95)] + [make_story(i, f"S{i}", 0.5) for i in range(1, 5)]
        picked = select_diverse_stories(stories, 3)
        assert picked[0]["story_id"] == "story_0"


def make_dup_item(idx: int, title: str, minutes_ago: int, site_id: str = "aggregate", tier_rank: int = 5) -> dict:
    ts = (NOW - timedelta(minutes=minutes_ago)).isoformat()
    return {
        "id": f"item_{idx}",
        "site_id": site_id,
        "site_name": site_id,
        "source": "news.google.com",
        "title": title,
        "url": f"https://example.com/{idx}",
        "published_at": ts,
        "first_seen_at": ts,
        "source_tier_rank": tier_rank,
        "medical_score": 0.65,
    }


class TestSuppressNearDuplicateItems:
    def test_rewritten_syndication_collapses(self):
        a = make_dup_item(1, "FDA approves new lung cancer therapy, expands access to patients - Reuters", 10)
        b = make_dup_item(2, "FDA approves new lung cancer treatment, expands access to patients - Reuters", 9)
        out = suppress_near_duplicate_items([a, b])
        assert len(out) == 1

    def test_distinct_stories_survive(self):
        a = make_dup_item(1, "WHO releases new vaccination guidelines for seasonal flu", 10)
        b = make_dup_item(2, "CDC updates influenza prevention recommendations for hospitals", 9)
        out = suppress_near_duplicate_items([a, b])
        assert len(out) == 2

    def test_cross_site_duplicates_are_kept(self):
        a = make_dup_item(1, "FDA approves new lung cancer therapy, expands access to patients", 10, site_id="aggregate")
        b = make_dup_item(2, "FDA approves new lung cancer treatment, expands access to patients", 9, site_id="medical_media")
        out = suppress_near_duplicate_items([a, b])
        assert len(out) == 2

    def test_keeps_more_authoritative_copy(self):
        low = make_dup_item(1, "NEJM publishes latest diabetes management study in primary care", 10, tier_rank=5)
        high = make_dup_item(2, "NEJM publishes latest diabetes management study in primary care", 9, tier_rank=0)
        high["site_id"] = "aggregate"
        out = suppress_near_duplicate_items([low, high])
        assert len(out) == 1
        assert out[0]["id"] == "item_2"
