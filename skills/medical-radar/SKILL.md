---
name: medical-radar
description: Use when a user asks for current medical-industry news, healthcare policy, medical AI, primary care, insurance compliance, health IT, pharma/device, company, or global healthtech updates from Medical News Radar.
---

# Medical Radar Reader

## Overview

Read the public static JSON produced by Medical News Radar and return a concise Chinese briefing with original links. Never answer a current-news question from training memory when the radar can be checked.

Default data root:

```text
https://xavier9802.github.io/medical-news-radar/data
```

Fork owners may replace the account and repository in that URL.

## Route

| Request | File |
| --- | --- |
| Last 24 hours / category / search | `latest-24h.json` |
| All collected items | `latest-24h-all.json` |
| Major stories / multi-source events | `stories-merged.json` |
| Daily brief | `daily-brief.json` |
| Source health | `source-registry.json` and `source-status.json` |

Never load `archive.json` without telling the user it may be large and getting agreement.

## Workflow

1. Download the smallest relevant JSON to a temporary file; do not dump the full file into context.
2. Read `generated_at`. If the main file is older than 36 hours, state the exact data time before the briefing.
3. Filter `items` by `category`, title, source, matched keywords, and requested time. Legacy records may only have `medical_label`; include them when semantically relevant.
4. Rank by `importance_score`, then `medical_relevance_score`/`medical_score`, then source authority and time. Missing fields are zero, not invented.
5. Return 10–20 items by default, grouped by the eight medical categories. Every item includes source and original URL.

Category IDs: `policy`, `medical_ai`, `primary_care`, `insurance_compliance`, `health_it`, `pharma_device`, `company_market`, `global_healthtech`.

## Output Contract

```markdown
# 医疗行业情报简报 · YYYY-MM-DD
> 数据时间：...｜窗口：24小时｜来源：...

## 栏目
- **标题** — 来源
  一句话说明。[原文](URL)

> 仅作行业信息参考，不构成医疗建议。
```

Use the source's claim scope. Do not turn a headline into a clinical conclusion, policy fact, approval, financing amount, diagnosis, or treatment advice. Mark uncertain claims as needing original-source verification.

## Failure Handling

- Pages request fails: retry the matching raw GitHub `main/data/...` URL once.
- Data is stale: answer only with a visible freshness warning.
- Category is empty: say so; do not fill it with unrelated items.
- Both requests fail: explain that current data is unavailable and do not invent news.

This skill is read-only. Source additions and deployment belong to `medical-news-radar`.
