# Claude Code Notes

Before changing this project, read:

- `skills/medical-news-radar/SKILL.md`
- `docs/SOURCE_COVERAGE.md`
- `README.md`

Do not commit private OPML files, API keys, cookies, browser exports, or `.env`
values. Keep the public repo usable without secrets.

The product direction is a two-layer medical news tool:

- Default layer: curated medical-focused view for ordinary healthcare readers.
- Advanced layer: custom OPML/source configuration and source health details for maintainers.

When adding sources, prefer official RSS/Atom feeds or OPML first. Add custom
fetchers only for stable, public, high-signal sources.
