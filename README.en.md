# Medical News Radar

A medical-industry source, policy, technology, and editorial-intelligence radar that runs entirely on GitHub Actions and GitHub Pages. It requires no database, login system, or long-running server.

- Reader: `/index.html`
- Source registry and submission entry: `/sources.html`
- Hosted site: [xavier9802.github.io/medical-news-radar](https://xavier9802.github.io/medical-news-radar/)

The radar keeps the existing fetch, normalization, deduplication, multi-source story merge, source-health, and static JSON pipeline while moving categories, keywords, scoring, tiers, and public sources into `config/*.yml`.

## Coverage

Eight categories are supported: policy/regulation, medical AI, primary care, insurance compliance, health IT, pharma/devices, company/market, and global healthtech. The UI also preserves all, selected, current-hot, search, time sorting, and multi-source folding views.

## Local setup

```bash
git clone https://github.com/xavier9802/medical-news-radar.git
cd medical-news-radar
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scripts/update_news.py --output-dir data --window-hours 24
python scripts/build_source_registry.py
python -m http.server 8080
```

Open `http://localhost:8080/` and `http://localhost:8080/sources.html`.

## Automation

`.github/workflows/update-news.yml` uses `*/30 * * * *`, so GitHub schedules it every 30 minutes (actual start may be delayed by Actions queuing). It generates and commits `data/*.json`, including `source-registry.json`.

Optional settings:

- Secret `FOLLOW_OPML_B64`: base64-encoded private OPML; never commit the real file.
- Variable `RSS_MAX_FEEDS`: OPML feed cap, default 10.
- `DEEPSEEK_API_KEY` plus `DEEPSEEK_PERSONA_ENABLED=1`: optional Persona ranking only; deterministic behavior remains the default.

To deploy, enable Actions write permission, select **Settings → Pages → Deploy from a branch**, choose `main` and `/ (root)`, then manually run **Update Medical News Snapshot** once.

## Source intake

Use the “Recommend source” button or the `source-request.yml` Issue Form. Submissions never edit configuration, create PRs, or merge automatically.

```bash
python scripts/source_probe.py --url "https://example.com/feed.xml" --name "Example"
python scripts/source_probe.py --config config/sources.yml --output data/source-probe-result.json
```

Maintainers can also run **Actions → Check Medical News Source → Run workflow**. External Issues receive structural-only checks; network probes from Issues are restricted to trusted repository roles.

See [source management](docs/source-management.md), [schema reference](docs/source-schema.md), and [coverage policy](docs/SOURCE_COVERAGE.md).

## Validation

```bash
python -m pytest -q
python -m compileall scripts
node --test tests/js/*.test.cjs
node --check assets/runtime-config.js
node --check assets/app.js
node --check assets/sources.js
```

## Safety

Only public HTTP(S) sources are eligible. The probe blocks local/private/reserved addresses, revalidates redirects, and limits redirects, timeouts, and response size. The project does not bypass login, captcha, cookies, or paywalls; does not store third-party full text; and must not turn news into medical advice or invent policy, clinical, approval, or financing facts.

Adapted from [LearnPrompt/ai-news-radar](https://github.com/LearnPrompt/ai-news-radar). Licensed under [MIT](LICENSE).
