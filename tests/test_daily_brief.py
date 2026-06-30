from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.update_news import (
    add_source_tier_fields,
    build_daily_brief_payload,
    build_merge_log_payload,
    build_stories_payload,
    calculate_item_importance,
    editorial_score,
    merge_story_items,
)


NOW = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)


def make_item(
    idx: int,
    *,
    site_id: str = "official_health",
    title: str | None = None,
    hours_ago: int = 1,
    medical_score: float = 0.9,
) -> dict:
    item = {
        "id": f"item-{idx}",
        "site_id": site_id,
        "site_name": site_id.replace("_", " ").title(),
        "source": "Test Feed",
        "title": title or f"WHO reports new vaccine milestone {idx}",
        "url": f"https://example.com/news/{idx}",
        "published_at": (NOW - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z"),
        "medical_is_related": True,
        "medical_score": medical_score,
    }
    return add_source_tier_fields(item)


def test_importance_score_favors_official_relevant_recent_items():
    official = make_item(1, site_id="official_health", hours_ago=1, medical_score=0.95)
    discussion = make_item(2, site_id="aggregate", hours_ago=20, medical_score=0.65)

    official_score = calculate_item_importance(official, NOW, 24)["score"]
    discussion_score = calculate_item_importance(discussion, NOW, 24)["score"]

    assert official_score > discussion_score


def test_importance_score_uses_curated_editorial_score():
    strong = make_item(1, site_id="healthtech_hub", medical_score=0.7)
    weak = make_item(2, site_id="healthtech_hub", medical_score=0.7)
    strong["curated_score"] = 88
    weak["curated_score"] = 60

    strong_importance = calculate_item_importance(strong, NOW, 24)
    weak_importance = calculate_item_importance(weak, NOW, 24)

    assert editorial_score(strong) == 0.88
    assert strong_importance["score"] > weak_importance["score"]
    assert "editorial" in strong_importance["breakdown"]


def test_daily_brief_respects_20_cap_when_enough_distinct_stories_exist():
    # Titles must be genuinely distinct: same-cluster stories are now
    # deliberately suppressed at selection time, so near-identical titles
    # may no longer fill the brief.
    subjects = [
        "vaccine trial", "cancer therapy", "clinical guideline", "medical device",
        "public health", "hospital IT", "diagnostic imaging", "pharma merger",
        "antibiotic resistance", "gene therapy", "telemedicine", "rare disease",
        "cardiovascular outcomes", "diabetes management", "health data interoperability",
        "FDA advisory", "WHO alert", "EMR implementation", "precision medicine",
        "clinical decision support", "patient safety", "healthcare policy",
        "medical AI", "wearable diagnostics", "drug pricing",
    ]
    templates = [
        "{subject} shows promise in early trial results",
        "Researchers highlight advances in {subject}",
        "New report examines the future of {subject}",
        "Industry leaders discuss impact of {subject}",
        "Hospital systems adopt {subject} at scale",
    ]
    items = [make_item(i, title=templates[i % len(templates)].format(subject=subjects[i])) for i in range(25)]
    stories, _events = merge_story_items(items, NOW, 24, title_threshold=1.1)

    payload = build_daily_brief_payload(stories, generated_at="2026-06-02T12:00:00Z", window_hours=24)

    assert len(stories) == 25
    assert payload["total_items"] == 20
    assert len(payload["items"]) == 20


def test_daily_brief_record_supports_bole_output_contract():
    items = [
        make_item(1, title="FDA approves new oncology therapy"),
        make_item(2, site_id="healthtech_hub", title="FDA approves new oncology therapy", medical_score=0.86),
    ]
    stories, events = merge_story_items(items, NOW, 24)

    payload = build_daily_brief_payload(stories, generated_at="2026-06-02T12:00:00Z", window_hours=24)
    record = payload["items"][0]

    assert events
    assert record["title"]
    assert record["url"]
    assert record["primary_url"] == record["url"]
    assert record["source"]
    assert record["source_name"]
    assert record["source_count"] == 2
    assert record["score"] == record["importance"] == record["importance_score"]
    assert record["category"] in {"official", "multi_source", "industry", "watch"}
    assert record["reasons"]
    assert record["earliest_at"]
    assert record["latest_at"]
    assert len(record["items"]) == 2
    assert len(record["sources"]) == 2
    assert record["primary_item"]["id"] == "item-1"


def test_stories_and_merge_log_payload_shapes_are_explicit():
    items = [
        make_item(1, title="FDA approves new oncology therapy"),
        make_item(2, title="FDA approves new oncology therapy"),
    ]
    stories, events = merge_story_items(items, NOW, 24)

    stories_payload = build_stories_payload(stories, generated_at="2026-06-02T12:00:00Z", window_hours=24)
    merge_payload = build_merge_log_payload(events, generated_at="2026-06-02T12:00:00Z")

    assert stories_payload["total_stories"] == 1
    assert stories_payload["stories"][0]["story_id"]
    assert merge_payload["merge_strategy"] == "url_or_title_similarity_v0_6"
    assert merge_payload["total_events"] == len(events) == 1
