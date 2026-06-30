# Medical News Radar｜24h Medical Intelligence Radar

An auto-updating 24-hour radar for medical and healthcare intelligence.

- **For readers**: open the hosted page and scan the last 24 hours of medical, public-health, clinical-research, regulatory, and industry updates.
- **For developers/organizations**: fork this repo, plug in your own medical RSS/OPML, journal feeds, or public APIs, and deploy your own intelligence site.
- **For agents**: use the in-repo Skill to maintain sources, evaluate new feeds, and deploy to GitHub Pages.

## Quick start

Readers do not need to install anything; open the hosted page directly (replace with your GitHub Pages URL after deployment).

To run locally:

```bash
git clone https://github.com/xavier9802/medical-news-radar.git
cd medical-news-radar
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/update_news.py --output-dir data --window-hours 24
python -m http.server 8080
```

Open http://localhost:8080

## Sources

Default public medical sources (RSS/Atom):

- **Official / regulatory**: WHO, CDC, FDA, NIH, etc.
- **Medical journals**: NEJM, The Lancet, JAMA, BMJ, etc.
- **Medical media**: Medscape, Healthcare IT News, HIMSS, etc.
- **Chinese medical media**: add via the `feeds/follow.example.opml` sample

To add private sources:

```bash
cp feeds/follow.example.opml feeds/follow.opml
# edit feeds/follow.opml with your medical RSS feeds
python scripts/update_news.py --output-dir data --window-hours 24 --rss-opml feeds/follow.opml
```

## How it works

1. **Source judgment**: prefer official agencies, authoritative journals, and trusted media; filter out wellness quackery, e-commerce noise, etc.
2. **Fetch & structure**: RSS/Atom/OPML + optional public APIs.
3. **Medical relevance scoring**: score items by title, source, and keywords.
4. **Deduplication & story merging**: cluster multiple sources for the same event into a story timeline.
5. **Static site publishing**: GitHub Actions generates `data/*.json` and publishes to GitHub Pages.

## Data outputs

- `data/latest-24h.json`: medical-focused updates from the last 24 hours
- `data/latest-24h-all.json`: all updates from the last 24 hours
- `data/source-status.json`: source fetch status and health
- `data/daily-brief.json`: curated story timeline / Top 3
- `data/stories-merged.json`: full merged story set
- `data/merge-log.json`: merge audit log

## GitHub Actions auto-update

`.github/workflows/update-news.yml` is already configured:

- Runs every 30 minutes by default
- Generates and commits `data/*.json` automatically
- Private OPML can be supplied via the `FOLLOW_OPML_B64` secret

### Configure private OPML

```bash
base64 -i feeds/follow.opml | pbcopy  # copy to clipboard
# Create FOLLOW_OPML_B64 in GitHub repo Settings > Secrets and variables > Actions
```

## Project structure

```
medical-news-radar/
├── scripts/
│   ├── update_news.py          # main fetcher and data generator
│   ├── medical_relevance.py    # medical relevance scoring
│   └── ...
├── assets/
│   ├── app.js                  # frontend logic
│   └── styles.css              # styles
├── feeds/
│   └── follow.example.opml     # OPML example
├── index.html                  # main page
├── data/                       # generated JSON (auto-committed)
└── tests/                      # tests
```

## Tests

```bash
python -m py_compile scripts/update_news.py
pytest -q
node --check assets/app.js
```

## Forked from AI News Radar

This project is adapted from [LearnPrompt/ai-news-radar](https://github.com/LearnPrompt/ai-news-radar), keeping its lightweight pipeline and GitHub Pages deployment architecture while switching the topic entirely to medical and healthcare.

## License

MIT
