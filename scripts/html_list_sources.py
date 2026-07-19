#!/usr/bin/env python3
"""Pure parsers for explicitly registered public HTML news lists."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag


@dataclass(frozen=True)
class HtmlListProfile:
    item_selector: str
    link_selector: str
    date_selector: str
    link_pattern: str
    date_formats: tuple[str, ...]
    title_attribute: str = ""
    summary_selector: str = ""
    date_pattern: str = ""
    content_mode: str = "document"


@dataclass(frozen=True)
class ParsedListItem:
    title: str
    url: str
    published_at: datetime
    summary: str = ""


HTML_LIST_PROFILES = {
    "nhsa_policy": HtmlListProfile("li", "a[href*='/art/']", "span:nth-of-type(4)", r"^/art/\d{4}/\d{1,2}/\d{1,2}/art_104_\d+\.html$", ("%Y-%m-%d",), title_attribute="title", content_mode="nhsa_cdata"),
    "chs_news": HtmlListProfile("li.catlist_li", "a[href*='/news/show/']", "span.f_r", r"^/news/show/\d+/?$", ("%Y-%m-%d",), title_attribute="title"),
    "cnmia_news": HtmlListProfile(".List .Block", ".Title a[href*='DynamicDetail_']", ".Time", r"^/DynamicDetail_[a-zA-Z0-9_-]+\.html$", ("%Y-%m-%d",), title_attribute="title", summary_selector=".Text", date_pattern=r"(\d{4}-\d{2}-\d{2})"),
    "chima_news": HtmlListProfile("ul.article_xw_l > li", ".right_xw a.title_type", ".span_date_left", r"^/Html/News/Articles/\d+\.html$", ("%d %Y.%m",), title_attribute="title", summary_selector=".right_xw > p"),
    "kanyijie": HtmlListProfile("div.des", "a.h2[href*='/details?id=']", ".time", r"^/details\?id=\d+$", ("%Y-%m-%d",), title_attribute="title", summary_selector=".sub"),
    "hospital_ceo": HtmlListProfile(".paging .zlist01", "a.tit[href*='/post/']", ".time", r"^/post/\d+\.html$", ("%Y年%m月%d日 %H:%M",), summary_selector=".des"),
    "mdweekly": HtmlListProfile("ul.glob-list > li.img-li", "h1 a[href*='/index/article/ztdetail']", ".time", r"^/index/article/ztdetail\?id=\d+$", ("%Y-%m-%d",), summary_selector="p"),
    "bioon": HtmlListProfile(".composs-blog-list .item", "h2 a[href*='news.bioon.com/article/']", ".item-meta-item", r"^/article/[a-zA-Z0-9_-]+\.html$", ("%Y-%m-%d",), summary_selector="p.text-justify"),
}

SHANGHAI = ZoneInfo("Asia/Shanghai")
MAX_CANDIDATES = 100
MAX_CDATA_RECORD_CHARS = 200_000
CDATA_RECORD_RE = re.compile(
    rf"<record\b[^>]*>\s*<!\[CDATA\[(.{{0,{MAX_CDATA_RECORD_CHARS}}}?)\]\]>\s*</record>",
    re.IGNORECASE | re.DOTALL,
)


def _candidate_nodes(html: str, profile: HtmlListProfile) -> list[Tag]:
    soup = BeautifulSoup(html, "html.parser")
    if profile.content_mode != "nhsa_cdata":
        return [node for node in soup.select(profile.item_selector) if isinstance(node, Tag)][:MAX_CANDIDATES]

    nodes: list[Tag] = []
    for script in soup.select('script[type="text/xml"]'):
        raw = script.string if script.string is not None else script.decode_contents()
        for match in CDATA_RECORD_RE.finditer(str(raw)):
            fragment = BeautifulSoup(match.group(1), "html.parser")
            nodes.extend(node for node in fragment.select(profile.item_selector) if isinstance(node, Tag))
            if len(nodes) >= MAX_CANDIDATES:
                return nodes[:MAX_CANDIDATES]
    return nodes[:MAX_CANDIDATES]


def _parse_date(text: str, profile: HtmlListProfile, now: datetime) -> datetime | None:
    candidate = " ".join(text.split())
    if profile.date_pattern:
        match = re.search(profile.date_pattern, candidate)
        if not match:
            return None
        candidate = match.group(1)
    for date_format in profile.date_formats:
        try:
            parsed = datetime.strptime(candidate, date_format).replace(tzinfo=SHANGHAI)
        except ValueError:
            continue
        published = parsed.astimezone(now.tzinfo)
        return published if published <= now + timedelta(days=2) else None
    return None


def _allowed_item_url(
    raw_url: str,
    base_url: str,
    profile: HtmlListProfile,
    allowed_hosts: Sequence[str],
) -> str:
    absolute = urljoin(base_url, raw_url.strip())
    parts = urlsplit(absolute)
    host = str(parts.hostname or "").lower()
    allowed = {str(value).strip().lower().rstrip(".") for value in allowed_hosts}
    path_and_query = parts.path + (f"?{parts.query}" if parts.query else "")
    if parts.scheme not in {"http", "https"} or host not in allowed:
        return ""
    if not re.fullmatch(profile.link_pattern, path_and_query):
        return ""
    return absolute


def parse_html_list_items(
    html: str,
    *,
    base_url: str,
    profile_id: str,
    allowed_hosts: Sequence[str],
    now: datetime,
) -> list[ParsedListItem]:
    profile = HTML_LIST_PROFILES.get(profile_id)
    if profile is None:
        raise ValueError("unsupported_parser_profile")
    if now.tzinfo is None:
        raise ValueError("invalid_publish_time")

    items: list[ParsedListItem] = []
    seen_urls: set[str] = set()
    for node in _candidate_nodes(html, profile):
        link_node = node.select_one(profile.link_selector)
        date_node = node.select_one(profile.date_selector)
        if not isinstance(link_node, Tag) or not isinstance(date_node, Tag):
            continue
        title = " ".join(
            str(link_node.get(profile.title_attribute) or link_node.get_text(" ", strip=True)).split()
        )
        item_url = _allowed_item_url(str(link_node.get("href") or ""), base_url, profile, allowed_hosts)
        published = _parse_date(date_node.get_text(" ", strip=True), profile, now)
        if len(title) < 6 or not item_url or published is None or item_url in seen_urls:
            continue
        summary_node = node.select_one(profile.summary_selector) if profile.summary_selector else None
        summary = summary_node.get_text(" ", strip=True)[:500] if isinstance(summary_node, Tag) else ""
        seen_urls.add(item_url)
        items.append(ParsedListItem(title, item_url, published, summary))
    return items
