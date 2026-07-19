# Configurable Medical Source Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a configuration-driven Medical News Radar V1 with eight medical categories, explainable scoring, static source management, safe source probing, deterministic Personas, and backward-compatible GitHub Actions/Pages output.

**Architecture:** Add one defensive YAML boundary in `scripts/config_loader.py`, then feed validated configuration into the existing `update_news.py` normalization, relevance, deduplication, story merge, and JSON writers. Generate a separate source registry for the static management page, keep probing isolated behind SSRF-safe networking, and implement classic/mobile/query compatibility inside the existing static frontend without adding a server.

**Tech Stack:** Python 3.11, PyYAML 6.0.2, requests, feedparser, BeautifulSoup, pytest 8.3.4, vanilla JavaScript, CSS, GitHub Actions, GitHub Pages.

## Global Constraints

- Work only on `agent/medical-radar-source-management`; never commit directly to `main`.
- Keep the existing GitHub Repository + GitHub Actions + `data/*.json` + GitHub Pages architecture.
- Do not add PHP, databases, Redis, servers, login, cloud-function requirements, or long-running services.
- Keep OPML ingestion and all existing fetch, normalization, deduplication, story merge, source-health, JSON, and frontend contracts working.
- Keep the `*/30 * * * *` update schedule and document it as every 30 minutes.
- Keep the public repository usable without DeepSeek or any other API key.
- Never commit `feeds/follow.opml`, tokens, cookies, email bodies, private OPML, or external article full text.
- New scores are clamped to `0.0..1.0`; existing `medical_score` remains compatible.
- Unit tests must mock network access and must not contact the public internet.
- Preserve the MIT license and upstream attribution.

## Baseline and file map

- Baseline command: `.\.venv\Scripts\python.exe -m pytest -q` → `43 passed`.
- Baseline checks: `.\.venv\Scripts\python.exe -m compileall scripts`, `node --check assets/app.js`, and `git diff --check` pass.
- Hard-coded built-in sources: `scripts/update_news.py` (`OFFICIAL_HEALTH_FEEDS`, `MEDICAL_JOURNAL_FEEDS`, `MEDICAL_MEDIA_FEEDS`).
- Hard-coded relevance/keywords: `scripts/medical_relevance.py`.
- Hard-coded source tiers/importance: `scripts/update_news.py` (`SOURCE_TIER_BY_SITE`, `SOURCE_TIER_IMPORTANCE`).
- Frontend category definitions: `assets/app.js` (`SECTION_DEFS`, `itemSections`, `itemTagLabels`, `impactLabels`).
- Current source status: top-level `generated_at`, `sites`, summary counters, and `rss_opml`; individual rows have `site_id`, `site_name`, `ok`, `item_count`, `duration_ms`, and `error`.
- Generator entry: `scripts/update_news.py::main`; current outputs are `archive.json`, `latest-24h.json`, `latest-24h-all.json`, `source-status.json`, `daily-brief.json`, `stories-merged.json`, `merge-log.json`, and `title-zh-cache.json`.
- Public demo OPML has unescaped `&` in `FDA News & Events` and must be repaired to `&amp;`.

---

### Task 1: Defensive configuration foundation

**Files:**
- Create: `scripts/config_loader.py`
- Create: `config/categories.yml`
- Create: `config/keywords.yml`
- Create: `config/scoring.yml`
- Create: `config/source-tiers.yml`
- Create: `config/sources.yml`
- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`
- Modify: `feeds/follow.example.opml`
- Create: `tests/test_config_loader.py`

**Interfaces:**
- Produces: `load_config(name: str, path: Path | None = None) -> ConfigResult`, `load_all_configs(config_dir: Path | None = None) -> dict[str, ConfigResult]`, `normalize_feed_url(url: str) -> str`, `dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]`, and `reset_config_cache() -> None`.
- `ConfigResult` fields: `data: dict[str, Any]`, `used_fallback: bool`, `errors: tuple[str, ...]`, `path: Path`.
- Consumers: `scripts/medical_relevance.py`, `scripts/update_news.py`, `scripts/build_source_registry.py`, `scripts/source_probe.py`.

- [ ] **Step 1: Write failing configuration tests**

```python
from pathlib import Path

import pytest

from scripts.config_loader import (
    ConfigLoadError,
    dedupe_sources,
    load_config,
    normalize_feed_url,
    reset_config_cache,
)


def test_loads_categories_from_valid_yaml(tmp_path: Path):
    path = tmp_path / "categories.yml"
    path.write_text("categories:\n  - id: policy\n    label: 政策监管\n    order: 10\n    enabled: true\n", encoding="utf-8")
    result = load_config("categories", path)
    assert result.data["categories"][0]["id"] == "policy"
    assert result.used_fallback is False


def test_missing_config_uses_safe_defaults(tmp_path: Path):
    result = load_config("categories", tmp_path / "missing.yml")
    assert result.used_fallback is True
    assert {row["id"] for row in result.data["categories"]} == {
        "policy", "medical_ai", "primary_care", "insurance_compliance",
        "health_it", "pharma_device", "company_market", "global_healthtech",
    }


def test_invalid_yaml_is_clear_in_strict_mode(tmp_path: Path):
    path = tmp_path / "sources.yml"
    path.write_text("sources: [", encoding="utf-8")
    with pytest.raises(ConfigLoadError, match="sources.yml"):
        load_config("sources", path, strict=True)


def test_feed_url_normalization_and_dedupe_prefers_first_metadata():
    assert normalize_feed_url("HTTPS://EXAMPLE.COM:443/feed/#x") == "https://example.com/feed"
    sources = [
        {"id": "yaml", "feed_url": "https://example.com/feed/", "tier": "s"},
        {"id": "opml", "feed_url": "https://EXAMPLE.com:443/feed", "tier": "c"},
    ]
    assert dedupe_sources(sources) == [sources[0]]
```

- [ ] **Step 2: Run tests and verify the missing module failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_config_loader.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'scripts.config_loader'`.

- [ ] **Step 3: Implement the loader boundary**

```python
@dataclass(frozen=True)
class ConfigResult:
    data: dict[str, Any]
    used_fallback: bool
    errors: tuple[str, ...]
    path: Path


class ConfigLoadError(ValueError):
    pass


def load_config(name: str, path: Path | None = None, *, strict: bool = False) -> ConfigResult:
    target = path or REPO_ROOT / "config" / f"{name}.yml"
    try:
        payload = yaml.safe_load(target.read_text(encoding="utf-8"))
        validated = _validate_config(name, payload)
        return ConfigResult(validated, False, (), target)
    except Exception as exc:
        message = f"{target.name}: {type(exc).__name__}: {exc}"
        if strict:
            raise ConfigLoadError(message) from exc
        return ConfigResult(copy.deepcopy(DEFAULT_CONFIGS[name]), True, (message,), target)
```

Implement validators for the five known roots only, strip unsupported fields, skip invalid individual source rows, and never include source URLs or nested metadata values in error messages.

- [ ] **Step 4: Add the complete approved YAML schemas**

`config/categories.yml` contains exactly the eight ordered IDs. `keywords.yml` represents every entry as `{term, weight, categories, enabled}` and includes the user-specified Chinese strong/medium/noise terms plus English equivalents. `scoring.yml` contains the exact authority/relevance/impact/recency/heat weights, selected/relevant/minimum thresholds, and six requested bonuses. `source-tiers.yml` defines `s/a/b/c` authority scores `1.0/0.82/0.62/0.38`. `sources.yml` migrates the currently built-in WHO, CDC, FDA, NIH, NEJM, Lancet, JAMA, BMJ, Nature Medicine, Medscape, Healthcare IT News, Fierce Healthcare, and HIMSS feeds with `metadata.legacy_site_id` for compatibility; a feed that has not been verified remains `enabled: false`.

- [ ] **Step 5: Pin runtime YAML and repair public OPML XML**

Add `PyYAML==6.0.2` to `requirements.txt`, remove the duplicate from `requirements-dev.txt`, and replace both `FDA News & Events` attribute values with `FDA News &amp; Events`.

- [ ] **Step 6: Verify configuration and OPML parsing**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config_loader.py tests/test_utils.py -q
.\.venv\Scripts\python.exe -c "from pathlib import Path; from scripts.update_news import parse_opml_subscriptions; print(len(parse_opml_subscriptions(Path('feeds/follow.example.opml'))))"
```

Expected: tests pass and OPML prints a positive feed count.

- [ ] **Step 7: Commit**

```powershell
git add requirements.txt requirements-dev.txt feeds/follow.example.opml config scripts/config_loader.py tests/test_config_loader.py
git commit -m "chore: add medical radar configuration schema"
```

---

### Task 2: Explainable medical classification and importance scoring

**Files:**
- Modify: `scripts/medical_relevance.py`
- Modify: `scripts/update_news.py`
- Modify: `tests/test_medical_relevance.py`
- Modify: `tests/test_daily_brief.py`

**Interfaces:**
- Consumes: `load_all_configs()` from Task 1.
- Produces: `load_medical_config`, `classify_medical_category`, `detect_policy_signal`, `detect_noise`, `calculate_importance_score`, and backward-compatible `score_medical_relevance`.
- `classify_medical_category(...) -> dict` returns `category`, `category_label`, `category_scores`, and `matched_keywords`.
- `calculate_importance_score(...) -> dict` returns `importance_score`, `impact_score`, and `importance_breakdown`, all numeric components clamped to `0..1`.

- [ ] **Step 1: Add failing category, policy, noise, authority, and clamp tests**

```python
def test_medical_ai_classification():
    result = classify_medical_category("医疗大模型进入临床决策支持", "", source={})
    assert result["category"] == "medical_ai"


def test_insurance_policy_classification():
    result = classify_medical_category("医保局开展基金飞行检查", "处方合规与追溯码", source={})
    assert result["category"] in {"insurance_compliance", "policy"}


def test_primary_care_classification():
    result = classify_medical_category("基层诊所与家庭医生签约服务", "社区卫生", source={})
    assert result["category"] == "primary_care"


def test_noise_reduces_importance_and_scores_are_clamped():
    clean = calculate_importance_score(title="基层医疗政策发布", source_tier="s", is_official=True)
    noisy = calculate_importance_score(title="明星养生偏方带货", source_tier="b", is_official=False)
    assert clean["importance_score"] > noisy["importance_score"]
    assert 0 <= clean["importance_score"] <= 1


def test_s_tier_authority_exceeds_b_tier():
    assert source_authority_score("s") > source_authority_score("b")
```

- [ ] **Step 2: Run focused tests and verify missing public functions**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_medical_relevance.py tests/test_daily_brief.py -q`

Expected: import errors for the new functions.

- [ ] **Step 3: Implement ordered eight-category scoring**

```python
def classify_medical_category(title: str, summary: str = "", *, source: dict[str, Any] | None = None) -> dict[str, Any]:
    config = load_medical_config()
    text = f"{title} {summary}".lower()
    scores = {row["id"]: 0.0 for row in config["categories"]}
    evidence: dict[str, list[str]] = {key: [] for key in scores}
    for entry in config["keywords"]:
        if entry["enabled"] and entry["term"].lower() in text:
            for category in entry["categories"]:
                if category in scores:
                    scores[category] += float(entry["weight"])
                    evidence[category].append(entry["term"])
    source_category = str((source or {}).get("category") or "")
    if source_category in scores:
        scores[source_category] += 0.2
    winner = max(config["categories"], key=lambda row: (scores[row["id"]], -row["order"]))
    return {
        "category": winner["id"],
        "category_label": winner["label"],
        "category_scores": {key: round(min(1.0, value), 4) for key, value in scores.items()},
        "matched_keywords": evidence[winner["id"]],
    }
```

Use explicit precedence so insurance/fund/flying-inspection signals outrank broad policy, and medical-AI terms outrank broad health-IT terms.

- [ ] **Step 4: Extend relevance output without breaking old keys**

Keep `is_medical_related`, `score`, `label`, `reason`, `signals`, and `noise`; add `medical_relevance_score`, eight-category fields, `impact_score`, `importance_score`, `is_policy`, `is_official`, `policy_metadata`, and `matched_keywords`. Empty policy facts remain empty strings/lists and are never inferred from a source name alone.

- [ ] **Step 5: Enrich normalized records in `update_news.py`**

Replace the current two-step relevance/tier enrichment with a compatibility helper:

```python
def add_medical_intelligence_fields(record: dict[str, Any], source_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    out = add_medical_relevance_fields(record, source_meta=source_meta)
    out = add_source_tier_fields(out)
    out.setdefault("medical_relevance_score", out.get("medical_score", 0.0))
    out.setdefault("is_official", out.get("source_tier") in {"s", "official"})
    return out
```

Update story links and primary story data to carry category, tier, official/policy flags, recommendation reason, and importance without removing existing fields.

- [ ] **Step 6: Run regression and commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_medical_relevance.py tests/test_daily_brief.py tests/test_story_merge.py tests/test_quality_fixes.py -q
.\.venv\Scripts\python.exe -m compileall scripts
```

Then commit:

```powershell
git add scripts/medical_relevance.py scripts/update_news.py tests/test_medical_relevance.py tests/test_daily_brief.py
git commit -m "feat: add medical relevance scoring"
```

---

### Task 3: Configured source collection and source registry

**Files:**
- Modify: `scripts/update_news.py`
- Create: `scripts/build_source_registry.py`
- Create: `tests/test_source_registry.py`
- Modify: `tests/test_config_loader.py`
- Create: `data/source-registry.json`

**Interfaces:**
- Consumes: validated `sources.yml`, current OPML parser, current `source-status.json`, and current archive.
- Produces: `configured_feed_groups(config_dir: Path | None = None) -> dict[str, list[dict]]`, `build_source_registry(source_config, status_payload, archive_payload, generated_at=None) -> dict`, and CLI output to `data/source-registry.json`.
- Adds `configured_sources` to `source-status.json` while preserving existing `sites` and `rss_opml` keys.

- [ ] **Step 1: Add failing registry status tests**

```python
def test_registry_merges_config_status_and_archive():
    config = {"sources": [{"id": "nhc", "name": "国家卫生健康委员会", "enabled": True, "category": "policy", "tier": "s"}]}
    status = {"generated_at": "2026-07-19T00:00:00Z", "configured_sources": [{"source_id": "nhc", "ok": True, "item_count": 3, "error": None}]}
    archive = {"items": [{"source_id": "nhc", "published_at": "2026-07-18T23:00:00Z"}]}
    result = build_source_registry(config, status, archive)
    row = result["sources"][0]
    assert row["status"] == "healthy"
    assert row["latest_item_at"] == "2026-07-18T23:00:00Z"
    assert row["success_rate"] is None


def test_missing_status_is_unknown():
    result = build_source_registry({"sources": [{"id": "x", "name": "X", "enabled": True}]}, {}, {})
    assert result["sources"][0]["status"] == "unknown"


def test_disabled_source_overrides_failed_status():
    config = {"sources": [{"id": "x", "name": "X", "enabled": False}]}
    status = {"configured_sources": [{"source_id": "x", "ok": False}]}
    assert build_source_registry(config, status, {})["sources"][0]["status"] == "disabled"
```

- [ ] **Step 2: Verify tests fail before the registry module exists**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_source_registry.py -q`

Expected: import failure for `scripts.build_source_registry`.

- [ ] **Step 3: Integrate configured sources without removing fallback tuples**

Build feed groups by `metadata.legacy_site_id`, call the existing feed parsers with configured dictionaries, attach `source_id/category/tier/language/region/is_official` through `RawItem.meta`, and append per-source status rows. If `sources.yml` falls back or yields no enabled sources, use `OFFICIAL_HEALTH_FEEDS`, `MEDICAL_JOURNAL_FEEDS`, and `MEDICAL_MEDIA_FEEDS` exactly as before. Deduplicate OPML against configured feeds by `normalize_feed_url` before network calls.

- [ ] **Step 4: Implement registry derivation**

```python
def derive_status(source: dict[str, Any], status: dict[str, Any] | None) -> str:
    if not source.get("enabled", True):
        return "disabled"
    if not status:
        return "unknown"
    if status.get("ok") is False:
        return "failed"
    if int(status.get("item_count") or 0) == 0:
        return "warning"
    return "healthy"
```

Count `total`, `enabled`, `healthy`, `warning`, `failed`, `disabled`, and `unknown`. Use category/tier labels from configuration. Use top-level status `generated_at` for `last_checked_at`; leave `last_success_at` and `success_rate` as `None` when there is no historical evidence.

- [ ] **Step 5: Generate the tracked registry fixture and verify**

Run:

```powershell
.\.venv\Scripts\python.exe scripts/build_source_registry.py --config config/sources.yml --status data/source-status.json --archive data/archive.json --output data/source-registry.json
.\.venv\Scripts\python.exe -m pytest tests/test_config_loader.py tests/test_source_registry.py tests/test_utils.py -q
```

Expected: a valid JSON registry containing every configured source; existing status groups map through `metadata.legacy_site_id`, and absent per-source status remains explicit rather than fabricated.

- [ ] **Step 6: Commit**

```powershell
git add scripts/update_news.py scripts/build_source_registry.py tests/test_config_loader.py tests/test_source_registry.py data/source-registry.json
git commit -m "feat: generate source registry data"
```

---

### Task 4: Safe source probe

**Files:**
- Create: `scripts/source_probe.py`
- Create: `tests/test_source_probe.py`

**Interfaces:**
- Produces: `validate_public_url(url, resolver=socket.getaddrinfo) -> str`, `fetch_url(url, session=None, resolver=..., limits=None) -> FetchResult`, `analyze_response(input_url, resolved_url, status_code, headers, body, elapsed_ms, name="") -> dict`, `probe_url(...) -> dict`, and `probe_config(...) -> list[dict]`.
- CLI supports `--url`, `--name`, `--config`, and `--output` exactly as requested.

- [ ] **Step 1: Write failing pure safety and parser tests**

```python
@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.com/feed", "http://localhost/feed",
    "http://127.0.0.1/feed", "http://10.2.3.4/feed", "http://172.16.0.1/feed",
    "http://192.168.1.1/feed", "http://169.254.169.254/latest/meta-data",
    "http://[::1]/feed", "http://[fc00::1]/feed", "https://user:pass@example.com/feed",
])
def test_rejects_non_public_targets(url):
    with pytest.raises(UnsafeUrlError):
        validate_public_url(url)


def test_analyzes_valid_rss_without_network():
    body = b"<?xml version='1.0'?><rss version='2.0'><channel><title>Medical</title><item><title>AI diagnosis</title><link>https://example.com/a</link><pubDate>Sat, 18 Jul 2026 10:00:00 GMT</pubDate></item></channel></rss>"
    result = analyze_response("https://example.com/feed", "https://example.com/feed", 200, {"Content-Type": "application/rss+xml"}, body, 12)
    assert result["detected_type"] == "rss"
    assert result["feed_valid"] is True
    assert result["item_count"] == 1


def test_invalid_xml_is_reported_not_raised():
    result = analyze_response("https://example.com/feed", "https://example.com/feed", 200, {"Content-Type": "application/xml"}, b"<rss>", 12)
    assert result["feed_valid"] is False
    assert result["errors"]


def test_timeout_becomes_structured_error(monkeypatch):
    session = FakeSession(error=requests.Timeout("secret query value"))
    result = probe_url("https://example.com/feed", session=session, resolver=public_resolver)
    assert result["reachable"] is False
    assert "secret query value" not in json.dumps(result)
```

- [ ] **Step 2: Run tests and verify the module is absent**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_source_probe.py -q`

Expected: import failure.

- [ ] **Step 3: Implement SSRF-safe URL and redirect handling**

Resolve every hostname, reject any address where `ipaddress.ip_address(address)` is not globally routable, set `allow_redirects=False`, validate each `Location`, and stop after five redirects. Use a new `requests.Session()` with `session.cookies.clear()`, `trust_env=False`, a fixed user agent, `(5, 15)` connect/read timeouts, and a 2 MiB streamed body cap.

- [ ] **Step 4: Implement pure RSS/Atom and HTML signal analysis**

Return every requested output field. Treat login/password/captcha/access-denied markers as `requires_login` or `blocked`; detect RSS/Atom from content and common `<link rel="alternate">` elements; parse only feed metadata and item title/date/link; compute medical relevance/category/tier recommendations through Task 2; never emit body text.

- [ ] **Step 5: Verify all probe tests and CLI help**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_source_probe.py -q
.\.venv\Scripts\python.exe scripts/source_probe.py --help
```

Expected: tests pass and help lists `--url`, `--name`, `--config`, and `--output`.

- [ ] **Step 6: Commit**

```powershell
git add scripts/source_probe.py tests/test_source_probe.py
git commit -m "feat: add safe medical source probe"
```

---

### Task 5: Source request Issue Form and least-privilege probe workflow

**Files:**
- Create: `.github/ISSUE_TEMPLATE/source-request.yml`
- Create: `.github/workflows/source-check.yml`
- Modify: `tests/test_source_probe.py`

**Interfaces:**
- Consumes: `scripts/source_probe.py` CLI.
- Produces: manual dispatch inputs `source_url`, `source_name`, `source_category`; Issue structural extraction; JSON/Markdown artifact; job summary.

- [ ] **Step 1: Add failing YAML contract tests**

```python
def test_issue_form_and_workflow_yaml_contracts():
    issue = yaml.safe_load(Path(".github/ISSUE_TEMPLATE/source-request.yml").read_text(encoding="utf-8"))
    workflow = yaml.safe_load(Path(".github/workflows/source-check.yml").read_text(encoding="utf-8"))
    assert len(issue["body"]) >= 10
    assert workflow[True]["workflow_dispatch"]["inputs"]["source_url"]["required"] is True
    assert workflow["permissions"] == {"contents": "read", "issues": "read"}
    assert set(workflow[True]["issues"]["types"]) == {"opened", "edited"}
```

PyYAML 1.1 may parse the key `on` as `True`; the test deliberately accepts that representation.

- [ ] **Step 2: Create the ten-field Chinese Issue Form**

Use GitHub-supported `input`, `dropdown`, and `textarea` controls. Request `labels: ["source-request"]` but do not reference the label from workflow conditions. Set the new-issue URL used by the frontend to `https://github.com/xavier9802/medical-news-radar/issues/new?template=source-request.yml`.

- [ ] **Step 3: Create the trusted-association workflow**

Use `OWNER`, `MEMBER`, or `COLLABORATOR` for automatic network probing. For other associations, write a structural-only report and do not call the probe URL. Pass extracted values through an environment file or JSON file, not `eval`, and never interpolate Issue text into executable shell source.

- [ ] **Step 4: Run YAML and probe tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_source_probe.py -q`

Expected: YAML contracts and all probe tests pass.

- [ ] **Step 5: Commit**

```powershell
git add .github/ISSUE_TEMPLATE/source-request.yml .github/workflows/source-check.yml tests/test_source_probe.py
git commit -m "feat: add source probe workflow"
```

---

### Task 6: Deterministic medical Personas

**Files:**
- Create: `personas/medical-editor.md`
- Create: `personas/policy-analyst.md`
- Create: `personas/medical-ai-product-manager.md`
- Create: `scripts/persona_score.py`
- Create: `tests/test_persona_score.py`
- Modify: `scripts/update_news.py`

**Interfaces:**
- Produces: `load_personas(directory: Path | None = None) -> list[Persona]`, `score_personas(record: dict, personas=None) -> dict[str, float]`, and `build_content_angles(record, persona_scores) -> list[str]`.
- Optional DeepSeek entry: `enhance_persona_output(record, deterministic, session=None) -> dict`, called only when `DEEPSEEK_API_KEY` and `DEEPSEEK_PERSONA_ENABLED=1` are both present.

- [ ] **Step 1: Write failing deterministic/fallback/safety tests**

```python
def test_persona_scoring_works_without_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    result = apply_persona_scores({"title": "医保局发布飞行检查通知", "category": "insurance_compliance", "is_policy": True})
    assert result["persona_scores"]["policy-analyst"] > 0
    assert result["content_angles"]


def test_missing_persona_directory_uses_builtin_safe_defaults(tmp_path: Path):
    personas = load_personas(tmp_path / "missing")
    assert {persona.id for persona in personas} == {"medical-editor", "policy-analyst", "medical-ai-product-manager"}


def test_persona_documents_contain_all_safety_rules():
    text = "\n".join(path.read_text(encoding="utf-8") for path in Path("personas").glob("*.md"))
    for phrase in ["不虚构政策文件", "不虚构融资金额", "不虚构FDA/NMPA批准", "不输出医疗诊断建议", "需要核实"]:
        assert phrase in text
```

- [ ] **Step 2: Implement front-matter parsing and local scoring**

Parse YAML front matter with `yaml.safe_load`. Score each role from category focus, official/policy flags, multi-source count, and importance. Emit at most three concise angles derived from verified fields only.

- [ ] **Step 3: Add the three complete Chinese Persona documents**

Each document contains the user-specified judgments and all six safety boundaries. `medical-editor` focuses topic and headline value; `policy-analyst` focuses official-document verification and affected entities; `medical-ai-product-manager` focuses product, HIS/EMR/CDSS, compliance, operations material, and competitor value.

- [ ] **Step 4: Integrate deterministic fields into generated article records**

Call `apply_persona_scores` after medical intelligence enrichment. Store `persona_scores`, `topic_value`, and `content_angles`; on any missing file, parse error, missing key, timeout, invalid JSON, or HTTP error, retain deterministic output and continue the run.

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_persona_score.py tests/test_medical_relevance.py tests/test_daily_brief.py -q
.\.venv\Scripts\python.exe -m compileall scripts
```

Commit:

```powershell
git add personas scripts/persona_score.py scripts/update_news.py tests/test_persona_score.py
git commit -m "feat: add medical industry personas"
```

---

### Task 7: Source management page and frontend compatibility

**Files:**
- Create: `sources.html`
- Create: `assets/sources.js`
- Create: `assets/sources.css`
- Create: `assets/runtime-config.js`
- Modify: `index.html`
- Modify: `assets/app.js`
- Modify: `assets/styles.css`
- Create: `tests/js/runtime-config.test.cjs`
- Create: `tests/js/sources.test.cjs`

**Interfaces:**
- Produces: `parseRuntimeOptions(href, origin) -> {view, dataUrl}` and pure source-page helpers `filterSources(sources, filters)` plus `summarizeSources(sources)`.
- Consumes: current news JSON plus `data/source-registry.json`.

- [ ] **Step 1: Write failing Node tests for query safety and source filters**

```javascript
test("safe same-origin data override", () => {
  assert.equal(parseRuntimeOptions("https://x.test/?data=data/demo.json", "https://x.test").dataUrl, "data/demo.json");
});

for (const unsafe of ["file:///x", "../secret.json", "https://evil.test/data.json", "https://u:p@x.test/data.json"]) {
  test(`rejects ${unsafe}`, () => {
    assert.equal(parseRuntimeOptions(`https://x.test/?data=${encodeURIComponent(unsafe)}`, "https://x.test").dataUrl, "data/latest-24h.json");
  });
}

test("view modes accept only auto, mobile, classic", () => {
  assert.equal(parseRuntimeOptions("https://x.test/?view=mobile", "https://x.test").view, "mobile");
  assert.equal(parseRuntimeOptions("https://x.test/?view=bad", "https://x.test").view, "auto");
});

test("source filters combine category tier status and search", () => {
  const rows = [{name:"WHO", category:"global_healthtech", tier:"s", status:"healthy"}, {name:"媒体", category:"company_market", tier:"b", status:"warning"}];
  assert.deepEqual(filterSources(rows, {query:"who", category:"global_healthtech", tier:"s", status:"healthy"}), [rows[0]]);
});
```

- [ ] **Step 2: Implement pure runtime and filtering helpers**

Use a small UMD wrapper so helpers attach to `window` in Pages and export through `module.exports` in Node. Same-origin absolute URLs are allowed; only `http:`/`https:` schemes pass; credentials and decoded `..` path segments fail.

- [ ] **Step 3: Replace old sections with all plus eight medical categories**

Set `SECTION_DEFS` to virtual `all` followed by `policy`, `medical_ai`, `primary_care`, `insurance_compliance`, `health_it`, `pharma_device`, `company_market`, and `global_healthtech`. Keep hot as the current `boleView` and preserve the medical/full mode switch. `itemSections()` first trusts `item.category`; for legacy records it maps existing `medical_label` and keyword patterns to the eight IDs.

- [ ] **Step 4: Preserve hot, curated, search, time, and multi-source behavior**

Keep `briefStories`, `mergedStories`, `boleView`, list sort `latest`, search, and source grouping. Add category, official, policy, and source-tier tags to the existing card metadata, limiting default visible tags to category plus official/policy; show tier in weak metadata or expanded/source areas.

- [ ] **Step 5: Add `view` and `data` runtime behavior**

Load `assets/runtime-config.js` before `assets/app.js`, set `document.documentElement.dataset.view`, and use `runtime.dataUrl` in `loadNewsData()`. Add `.view-mobile` single-column and touch-size rules plus `.view-classic` fixed desktop-density rules; `auto` leaves existing media queries unchanged.

- [ ] **Step 6: Build the static source page**

Implement header/back/recommend buttons, generated time, five requested summary cards, four filters, responsive source rows/cards, and the “信源状态暂不可用” fallback. A registry load failure must not affect `index.html` because the pages load independently.

- [ ] **Step 7: Add homepage source-management entry**

Add `<a class="hero-link" href="./sources.html">信源管理</a>` beside the GitHub link without changing section tabs.

- [ ] **Step 8: Run JavaScript checks and commit**

Run:

```powershell
node --test tests/js/runtime-config.test.cjs tests/js/sources.test.cjs
node --check assets/runtime-config.js
node --check assets/app.js
node --check assets/sources.js
```

Commit:

```powershell
git add index.html sources.html assets/app.js assets/styles.css assets/runtime-config.js assets/sources.js assets/sources.css tests/js
git commit -m "feat: add source management page and medical navigation"
```

---

### Task 8: Actions integration and operator documentation

**Files:**
- Modify: `.github/workflows/update-news.yml`
- Modify: `README.md`
- Create: `docs/source-management.md`
- Create: `docs/source-schema.md`
- Modify: `docs/SOURCE_COVERAGE.md`
- Modify: `skills/medical-news-radar/README.md`

**Interfaces:**
- Consumes: registry builder and all previous CLI paths.
- Produces: truthful deployment/source-management instructions and registry generation in every update run.

- [ ] **Step 1: Add registry generation to the update workflow**

After `update_news.py`, run:

```yaml
- name: Build source registry
  run: |
    python scripts/build_source_registry.py \
      --config config/sources.yml \
      --status data/source-status.json \
      --archive data/archive.json \
      --output data/source-registry.json
```

Retain `schedule`, `workflow_dispatch`, `FOLLOW_OPML_B64`, `RSS_MAX_FEEDS`, `permissions: contents: write`, `git add data/`, and the no-change exit exactly.

- [ ] **Step 2: Rewrite README around the final product contract**

Document Medical News Radar positioning, GitHub-only architecture, actual 30-minute schedule, all five config files, source request flow, `/sources.html`, manual `source-check.yml`, required/optional Secrets, Windows/Linux local commands, Pages setup, and medical/content security boundaries. State that DeepSeek is optional and deterministic scoring is the default.

- [ ] **Step 3: Write source operations and schemas**

`docs/source-management.md` covers add/probe/accept/pause/soft-delete, Issue review, workflow dispatch, why WeChat full text and login-gated sources are excluded, and how to keep OPML private. `docs/source-schema.md` lists every field and type for sources, categories, scoring, registry, and probe results, including nullable/historical limitations.

- [ ] **Step 4: Correct stale AI-era source/Skill copy touched by this feature**

Update the first-screen/source model descriptions to the eight-category medical system and remove claims that the current public page is an AI-news page. Keep advanced private-source safety guidance intact.

- [ ] **Step 5: Validate YAML, docs commands, and commit**

Run:

```powershell
.\.venv\Scripts\python.exe -c "import yaml, pathlib; [yaml.safe_load(p.read_text(encoding='utf-8')) for p in pathlib.Path('.github').rglob('*.yml')]; print('workflow yaml ok')"
.\.venv\Scripts\python.exe -m pytest -q
```

Commit:

```powershell
git add .github/workflows/update-news.yml README.md docs/source-management.md docs/source-schema.md docs/SOURCE_COVERAGE.md skills/medical-news-radar/README.md
git commit -m "docs: document source management and deployment"
```

---

### Task 9: Full regression, generated output, remote delivery, and Draft PR

**Files:**
- Modify only files required by failures discovered in this verification task.
- Verify: all tracked changes and generated `data/source-registry.json`.

**Interfaces:**
- Produces: green local verification, pushed branch, Draft PR titled `feat: add configurable medical source management`.

- [ ] **Step 1: Run the complete deterministic verification suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall scripts
node --test tests/js/runtime-config.test.cjs tests/js/sources.test.cjs
node --check assets/runtime-config.js
node --check assets/app.js
node --check assets/sources.js
git diff --check
```

Expected: every command exits `0`; pytest count is greater than the 43-test baseline.

- [ ] **Step 2: Run offline-safe generation checks**

Use mocked unit tests for network behavior. Run registry generation against tracked data and parse every shipped JSON/YAML file:

```powershell
.\.venv\Scripts\python.exe scripts/build_source_registry.py --config config/sources.yml --status data/source-status.json --archive data/archive.json --output data/source-registry.json
.\.venv\Scripts\python.exe -c "import json, pathlib; [json.loads(p.read_text(encoding='utf-8')) for p in pathlib.Path('data').glob('*.json')]; print('json ok')"
.\.venv\Scripts\python.exe -c "import yaml, pathlib; [yaml.safe_load(p.read_text(encoding='utf-8')) for p in list(pathlib.Path('config').glob('*.yml')) + list(pathlib.Path('.github').rglob('*.yml'))]; print('yaml ok')"
```

- [ ] **Step 3: Inspect repository safety and scope**

```powershell
git status --short
git diff --stat origin/main...HEAD
git log --oneline origin/main..HEAD
rg -n "github_pat_|ghp_|BEGIN.*PRIVATE KEY|FOLLOW_OPML_B64=" . -g '!docs/superpowers/**'
```

Expected: no secrets/private OPML, no unintended binary output, and all commits are on the feature branch.

- [ ] **Step 4: Commit any final test-only corrections**

```powershell
git add tests data/source-registry.json
git commit -m "test: cover medical radar configuration and probing"
```

Skip the commit only when there are no remaining changes.

- [ ] **Step 5: Push the feature branch**

```powershell
git push -u origin agent/medical-radar-source-management
```

- [ ] **Step 6: Create the required Draft PR**

Create a Draft PR with title `feat: add configurable medical source management`. The body includes implemented scope, explicit non-goals, all new config files, new Pages entry, both Actions changes, exact test results, optional Secrets, Pages deployment/acceptance steps, and known limitations such as no historical success rate and no Issue-to-config automation.

- [ ] **Step 7: Verify remote checks without merging**

```powershell
gh pr checks --watch
gh pr view --json url,isDraft,headRefName,baseRefName,statusCheckRollup
```

Expected: PR remains Draft, head is `agent/medical-radar-source-management`, base is `main`, and no merge is performed.

## Self-review results

- Spec coverage: all 20 acceptance criteria map to Tasks 1–9.
- Placeholder scan: no deferred implementation markers are present.
- Type consistency: configuration, scoring, registry, probe, Persona, and runtime interfaces are named once and reused by later tasks.
- Scope control: Issue-to-config automation, automatic PRs, user accounts, WeChat full-text scraping, login automation, paid-API dependency, and server infrastructure remain excluded.
