---
name: medical-news-radar
description: Use when maintaining Medical News Radar sources, medical categories, scoring, source health, GitHub Actions, static pages, OPML inputs, or GitHub Pages deployment.
---

# Medical News Radar Maintainer

## Overview

Maintain a forkable medical-industry intelligence radar without adding a server, database, login system, or required paid service. Prefer stable public sources and keep every optional integration safely degradable.

## Read First

- `README.md`
- `docs/SOURCE_COVERAGE.md`
- `docs/source-management.md`
- `docs/source-schema.md`
- `config/*.yml`
- the smallest relevant script, test, workflow, or frontend file

## Source Routing

| Candidate | Route |
| --- | --- |
| Public RSS/Atom | Probe, then add to `config/sources.yml` or private OPML |
| Stable public JSON | Use `json` only when timestamped and documented |
| Public list page | Use only when structurally stable; never bypass access controls |
| Private personal subscriptions | Keep in ignored `feeds/follow.opml` or `FOLLOW_OPML_B64` |
| Login, Cookie, captcha, paywall | Skip public ingestion |
| Newsletter/social observation | Prefer a public feed; otherwise keep optional and private |

## Maintenance Workflow

1. Run `python scripts/source_probe.py --url "URL" --name "NAME"`.
2. Verify identity, medical value, original-source quality, category, tier, timestamps, and copyright boundary.
3. Edit `config/sources.yml`; failed candidates start with `enabled: false`.
4. Generate data and `data/source-registry.json` without deleting legacy fields.
5. Add tests for behavioral changes; unit tests must not require real network access.
6. Check `/index.html` and `/sources.html` on desktop and mobile.
7. Keep changes on a feature branch and publish through a reviewed PR.

Issue submissions never directly modify configuration, create PRs, or merge. External Issue authors receive structural-only checks; network probes are limited to trusted repository roles or manual dispatch.

## Safety

- Never commit tokens, API keys, Cookies, `.env`, private OPML, mailbox contents, or full third-party articles.
- Only public HTTP(S) sources are eligible. Preserve private-IP, redirect, timeout, and response-size protections.
- Do not invent policy metadata, clinical conclusions, approval status, or financing facts.
- Do not turn news into diagnosis or treatment advice.
- DeepSeek is optional. Deterministic scoring and generation must work when it is absent or fails.

## Validate

```bash
python -m pytest -q
python -m compileall scripts
node --test tests/js/*.test.cjs
node --check assets/runtime-config.js
node --check assets/app.js
node --check assets/sources.js
git diff --check
```

For deployment, manually run `update-news.yml`, confirm `data/source-registry.json`, then verify the Pages homepage, eight category filters, source page, Issue Form, search, selected/all switch, current-hot view, sorting, and multi-source folding.
