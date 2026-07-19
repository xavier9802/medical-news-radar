#!/usr/bin/env python3
"""Pure parser for the fixed public YXJ homepage news response."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


YXJ_API_URL = "https://pcapi.yxj.org.cn/ysz-content/web/home/news/getNewsModuleData"
YXJ_REQUEST_BODY = {"categoryId": 0, "position": "HOME_PAGE_MAIN_NEWS"}


@dataclass(frozen=True)
class ParsedYxjItem:
    title: str
    url: str
    published_at: datetime
    summary: str = ""


def parse_yxj_home_items(payload: Mapping[str, Any], *, now: datetime) -> list[ParsedYxjItem]:
    if now.tzinfo is None:
        raise ValueError("invalid_publish_time")
    if not isinstance(payload, Mapping):
        raise ValueError("invalid_json_shape")
    body = payload.get("body")
    modules = body.get("moduleList") if isinstance(body, Mapping) else None
    if not isinstance(modules, list):
        raise ValueError("invalid_json_shape")
    items: list[ParsedYxjItem] = []
    seen: set[int] = set()
    for module in modules:
        rows = module.get("newsList") if isinstance(module, Mapping) else None
        for row in rows if isinstance(rows, list) else []:
            article_id = row.get("articleId") if isinstance(row, Mapping) else None
            title = " ".join(str(row.get("title") or "").split()) if isinstance(row, Mapping) else ""
            stamp = row.get("publishTime") if isinstance(row, Mapping) else None
            if not isinstance(article_id, int) or article_id <= 0 or article_id in seen or len(title) < 6 or not isinstance(stamp, (int, float)):
                continue
            try:
                published = datetime.fromtimestamp(stamp, tz=timezone.utc)
            except (OSError, OverflowError, ValueError):
                continue
            if published.year < 2000 or published > now + timedelta(days=2):
                continue
            seen.add(article_id)
            summary = " ".join(str(row.get("brief") or "").replace("[图片信息]", " ").split())[:500]
            items.append(
                ParsedYxjItem(
                    title[:300],
                    f"https://www.yxj.org.cn/detailPage?articleId={article_id}",
                    published,
                    summary,
                )
            )
            if len(items) == 100:
                return items
    return items
