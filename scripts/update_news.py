#!/usr/bin/env python3
"""Aggregate updates from multiple medical/health news sites and produce 24h snapshot data."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.utils import parseaddr
import hashlib
import json
import math
import os
import random
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from scripts.medical_relevance import add_medical_relevance_fields, score_medical_relevance
except ModuleNotFoundError:  # pragma: no cover - direct `python scripts/update_news.py`
    from medical_relevance import add_medical_relevance_fields, score_medical_relevance

try:
    from scripts.config_loader import ConfigResult, load_config, normalize_feed_url
except ModuleNotFoundError:  # pragma: no cover - direct `python scripts/update_news.py`
    from config_loader import ConfigResult, load_config, normalize_feed_url

try:
    from scripts.build_source_registry import write_source_registry
except ModuleNotFoundError:  # pragma: no cover - direct `python scripts/update_news.py`
    from build_source_registry import write_source_registry

try:
    from scripts.persona_score import apply_persona_scores
except ModuleNotFoundError:  # pragma: no cover - direct `python scripts/update_news.py`
    from persona_score import apply_persona_scores

try:
    import feedparser
except ModuleNotFoundError:
    feedparser = None

UTC = timezone.utc
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
SH_TZ = ZoneInfo("Asia/Shanghai")
RSS_FEED_REPLACEMENTS: dict[str, str] = {
    "https://rsshub.app/infoq/recommend": "https://www.infoq.cn/feed",
    "https://rsshub.app/huggingface/blog-zh": "https://huggingface.co/blog/feed.xml",
    "https://rsshub.app/readhub/daily": "https://readhub.cn/rss",
    "https://rsshub.app/36kr/hot-list": "https://36kr.com/feed",
    "https://rsshub.app/sspai/index": "https://sspai.com/feed",
    "https://rsshub.app/sspai/matrix": "https://sspai.com/feed",
    "https://rsshub.app/meituan/tech": "https://tech.meituan.com/feed",
    "https://mjg59.dreamwidth.org/data/rss": "http://mjg59.dreamwidth.org/data/rss",
}

RSS_FEED_SKIP_PREFIXES: tuple[str, ...] = (
    "https://rsshub.app/telegram/channel/",
    "https://rsshub.app/jike/",
    "https://rsshub.app/bilibili/",
    "https://rsshub.app/zhihu/",
    "https://rsshub.app/xiaoyuzhou/podcast/",
    "https://rsshub.app/xyzrank",
    "https://rsshub.app/mittrchina/hot",
    "https://wechat2rss.bestblogs.dev/",
    "https://werss.bestblogs.dev/",
    "http://47.122.94.119:18080/",
)

RSS_FEED_SKIP_EXACT: set[str] = {
    "https://rachelbythebay.com/w/atom.xml",
    "https://flak.tedunangst.com/rss",
}

OFFICIAL_HEALTH_FEEDS: tuple[dict[str, str], ...] = (
    {
        "title": "WHO News",
        "xml_url": "https://www.who.int/feeds/entity/cds/headlines/en/rss.xml",
        "html_url": "https://www.who.int/news-room/headlines",
    },
    {
        "title": "CDC Newsroom",
        "xml_url": "https://tools.cdc.gov/podcasts/feed.asp?feedid=183",
        "html_url": "https://www.cdc.gov/media/releases/index.html",
    },
    {
        "title": "FDA News",
        "xml_url": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/newsroom/rss.xml",
        "html_url": "https://www.fda.gov/news-events/fda-newsroom",
    },
    {
        "title": "NIH News",
        "xml_url": "https://www.nih.gov/news-events/news-releases/rss.xml",
        "html_url": "https://www.nih.gov/news-events/news-releases",
    },
)
OFFICIAL_HEALTH_MAX_AGE_DAYS = 45
MEDICAL_JOURNAL_MAX_AGE_DAYS = 30

MEDICAL_JOURNAL_FEEDS: tuple[dict[str, Any], ...] = (
    {
        "title": "NEJM",
        "xml_url": "https://www.nejm.org/rss/medical-articles.xml",
        "html_url": "https://www.nejm.org/medical-articles",
        "max_entries": 10,
    },
    {
        "title": "The Lancet",
        "xml_url": "https://www.thelancet.com/rssfeed/online_first.xml",
        "html_url": "https://www.thelancet.com/online-first",
        "max_entries": 10,
    },
    {
        "title": "JAMA",
        "xml_url": "https://jamanetwork.com/rss/site_3/67.xml",
        "html_url": "https://jamanetwork.com/journals/jama/latest",
        "max_entries": 10,
    },
    {
        "title": "BMJ",
        "xml_url": "https://www.bmj.com/rss/research.xml",
        "html_url": "https://www.bmj.com/research",
        "max_entries": 10,
    },
    {
        "title": "Nature Medicine",
        "xml_url": "https://www.nature.com/nm.rss",
        "html_url": "https://www.nature.com/nm",
        "max_entries": 10,
    },
)

MEDICAL_MEDIA_FEEDS: tuple[dict[str, Any], ...] = (
    {
        "title": "Medscape",
        "xml_url": "https://www.medscape.com/rss",
        "html_url": "https://www.medscape.com",
        "max_entries": 8,
    },
    {
        "title": "Healthcare IT News",
        "xml_url": "https://www.healthcareitnews.com/rss",
        "html_url": "https://www.healthcareitnews.com",
        "max_entries": 8,
    },
    {
        "title": "Fierce Healthcare",
        "xml_url": "https://www.fiercehealthcare.com/rss.xml",
        "html_url": "https://www.fiercehealthcare.com",
        "max_entries": 8,
    },
    {
        "title": "HIMSS",
        "xml_url": "https://www.himss.org/news/rss",
        "html_url": "https://www.himss.org/news",
        "max_entries": 8,
    },
)

LEGACY_SOURCE_SITE_NAMES = {
    "official_health": "Official Health Updates",
    "medical_journals": "Medical Journals",
    "medical_media": "Medical Media",
}

CONFIGURED_FEED_META_FIELDS: tuple[str, ...] = (
    "source_id",
    "category",
    "source_tier",
    "language",
    "region",
    "is_official",
    "source_metadata",
)


def configured_feed_meta(feed: dict[str, Any]) -> dict[str, Any]:
    return {key: feed[key] for key in CONFIGURED_FEED_META_FIELDS if key in feed}


def configured_feed_groups(config_path: Path | None = None) -> tuple[dict[str, list[dict[str, Any]]], ConfigResult]:
    """Translate enabled sources.yml RSS rows into existing feed-group contracts."""
    result = load_config("sources", config_path)
    if result.used_fallback:
        return {}, result
    groups: dict[str, list[dict[str, Any]]] = {}
    for source in result.data.get("sources", []):
        if not source.get("enabled", True) or not str(source.get("feed_url") or "").strip():
            continue
        fetch = source.get("fetch") if isinstance(source.get("fetch"), dict) else {}
        strategy = str(fetch.get("strategy") or "auto")
        if strategy == "skip":
            continue
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        legacy_site_id = str(metadata.get("legacy_site_id") or "").strip()
        if legacy_site_id not in LEGACY_SOURCE_SITE_NAMES:
            if source.get("type") == "journal":
                legacy_site_id = "medical_journals"
            elif source.get("type") == "government_page" or str(source.get("tier") or "") == "s":
                legacy_site_id = "official_health"
            else:
                legacy_site_id = "medical_media"
        filters = source.get("filters") if isinstance(source.get("filters"), dict) else {}
        source_meta = {
            "source_id": str(source.get("id") or ""),
            "category": str(source.get("category") or ""),
            "source_tier": str(source.get("tier") or "c"),
            "language": str(source.get("language") or ""),
            "region": str(source.get("region") or ""),
            "is_official": str(source.get("tier") or "") == "s" or source.get("type") == "government_page",
            "source_metadata": {
                "category": str(source.get("category") or ""),
                "tier": str(source.get("tier") or "c"),
                "official": str(source.get("tier") or "") == "s" or source.get("type") == "government_page",
                "source_id": str(source.get("id") or ""),
            },
        }
        feed = {
            "title": str(source.get("name") or source.get("id") or "Source"),
            "xml_url": str(source.get("feed_url") or ""),
            "html_url": str(source.get("homepage_url") or ""),
            "max_entries": max(1, int(fetch.get("max_items") or 30)),
            "timeout_seconds": max(1, int(fetch.get("timeout_seconds") or 20)),
            "include_keywords": ",".join(str(value) for value in filters.get("include_keywords", [])),
            "exclude_keywords": ",".join(str(value) for value in filters.get("exclude_keywords", [])),
            **source_meta,
        }
        groups.setdefault(legacy_site_id, []).append(feed)
    return groups, result


def dedupe_opml_feeds(
    feeds: list[dict[str, str]],
    configured_urls: set[str] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Keep OPML feeds not already represented by configured source URLs."""
    blocked = {normalize_feed_url(url) for url in (configured_urls or set()) if normalize_feed_url(url)}
    kept: list[dict[str, str]] = []
    duplicates: list[dict[str, str]] = []
    for feed in feeds:
        normalized = normalize_feed_url(str(feed.get("xml_url") or ""))
        if normalized and normalized in blocked:
            duplicates.append(feed)
        else:
            kept.append(feed)
    return kept, duplicates


@dataclass
class RawItem:
    site_id: str
    site_name: str
    source: str
    title: str
    url: str
    published_at: datetime | None
    meta: dict[str, Any]


PUBLIC_RAW_META_FIELDS: tuple[str, ...] = (
    "aihot_score",
    "aihot_category",
    "aihot_selected",
    "creator_metrics",
    "search_surface",
    "summary",
    "source_id",
    "category",
    "source_tier",
    "language",
    "region",
    "is_official",
    "source_metadata",
)


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_iso(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        dt = dtparser.parse(dt_str)
    except Exception:
        return None
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def normalize_url(raw_url: str) -> str:
    try:
        parsed = urlparse(raw_url.strip())
        if not parsed.scheme:
            return raw_url.strip()
        query = []
        for k, v in parse_qsl(parsed.query, keep_blank_values=True):
            lk = k.lower()
            if lk.startswith("utm_"):
                continue
            if lk in {
                "ref",
                "spm",
                "fbclid",
                "gclid",
                "igshid",
                "mkt_tok",
                "mc_cid",
                "mc_eid",
                "_hsenc",
                "_hsmi",
            }:
                continue
            query.append((k, v))
        parsed = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            fragment="",
            query=urlencode(query, doseq=True),
        )
        normalized = urlunparse(parsed)
        return normalized.rstrip("/")
    except Exception:
        return raw_url.strip()


def host_of_url(raw_url: str) -> str:
    try:
        return urlparse(raw_url).netloc.lower()
    except Exception:
        return ""


def first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        s = str(value).strip()
        if s:
            return s
    return ""


def maybe_fix_mojibake(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return s
    # Common mojibake signature from UTF-8 bytes decoded as Latin-1.
    if re.search(r"[Ãâåèæïð]|[\x80-\x9f]|æ|ç|å|é", s) is None:
        return s
    for enc in ("latin1", "cp1252"):
        try:
            fixed = s.encode(enc).decode("utf-8")
            if fixed and fixed != s:
                return fixed
        except Exception:
            continue
    return s


def has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def is_mostly_english(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    if has_cjk(s):
        return False
    letters = re.findall(r"[A-Za-z]", s)
    return len(letters) >= max(6, len(s) // 4)


def parse_feed_entries_via_xml(feed_xml: bytes) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    try:
        root = ET.fromstring(feed_xml)
    except Exception:
        return out

    for tag in (".//item", ".//{*}item", ".//entry", ".//{*}entry"):
        for node in root.findall(tag):
            title = (
                node.findtext("title")
                or node.findtext("{*}title")
                or ""
            ).strip()
            link = ""
            link_node = node.find("link")
            if link_node is None:
                link_node = node.find("{*}link")
            if link_node is not None:
                link = (link_node.get("href") or link_node.text or "").strip()
            if not link:
                link = (node.findtext("{*}link") or node.findtext("link") or "").strip()
            published = (
                node.findtext("pubDate")
                or node.findtext("{*}pubDate")
                or node.findtext("published")
                or node.findtext("{*}published")
                or node.findtext("updated")
                or node.findtext("{*}updated")
            )
            if title and link:
                key = (title, link)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"title": title, "link": link, "published": published})
    return out


def make_item_id(site_id: str, source: str, title: str, url: str) -> str:
    key = "||".join(
        [
            site_id.strip().lower(),
            source.strip().lower(),
            title.strip().lower(),
            normalize_url(url),
        ]
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def parse_unix_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        n = float(value)
    except Exception:
        return None
    if n > 10_000_000_000:
        n /= 1000.0
    try:
        return datetime.fromtimestamp(n, tz=UTC)
    except Exception:
        return None


def parse_relative_time_zh(text: str, now: datetime) -> datetime | None:
    text = (text or "").strip()
    if not text:
        return None

    m = re.search(r"(\d+)\s*分钟前", text)
    if m:
        return now - timedelta(minutes=int(m.group(1)))

    m = re.search(r"(\d+)\s*小时前", text)
    if m:
        return now - timedelta(hours=int(m.group(1)))

    m = re.search(r"(\d+)\s*天前", text)
    if m:
        return now - timedelta(days=int(m.group(1)))

    if "刚刚" in text:
        return now

    if "昨天" in text:
        return now - timedelta(days=1)

    m = re.fullmatch(r"(?:今天)?\s*(\d{1,2}):(\d{2})", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now + timedelta(minutes=5):
            candidate -= timedelta(days=1)
        return candidate

    m = re.fullmatch(r"昨天\s*(\d{1,2}):(\d{2})", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        return (now - timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)

    m = re.fullmatch(r"(?:\d{4}年\s*)?(\d{1,2})月(\d{1,2})日", text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        year = now.year
        try:
            candidate = datetime(year, month, day, tzinfo=UTC)
            if candidate > now + timedelta(days=2):
                candidate = datetime(year - 1, month, day, tzinfo=UTC)
            return candidate
        except Exception:
            return None

    return None


def parse_date_any(value: Any, now: datetime) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.astimezone(UTC)

    if isinstance(value, (int, float)):
        return parse_unix_timestamp(value)

    s = str(value).strip()
    if not s:
        return None

    if s.startswith("$D"):
        s = s[2:]

    if re.fullmatch(r"\d{12,}", s):
        return parse_unix_timestamp(int(s))

    if re.fullmatch(r"\d{9,11}", s):
        return parse_unix_timestamp(int(s))

    dt = parse_relative_time_zh(s, now)
    if dt:
        return dt

    # TechURLs format: 2026-02-19 11:54:21AM UTC
    m = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}:\d{2}[AP]M)\s+UTC", s)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%Y-%m-%d %I:%M:%S%p")
            return dt.replace(tzinfo=UTC)
        except Exception:
            pass

    try:
        dt = dtparser.parse(s, tzinfos={"UT": 0, "UTC": 0, "GMT": 0})
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


def apply_public_raw_meta(record: dict[str, Any], raw: RawItem) -> None:
    """Promote safe source metadata needed by public scoring and UI ranking."""
    meta = raw.meta if isinstance(raw.meta, dict) else {}
    for key in PUBLIC_RAW_META_FIELDS:
        if key in meta and meta.get(key) is not None:
            record[key] = sanitize_public_value(meta.get(key))


def decode_escaped_json(raw: str) -> dict[str, Any] | None:
    s = raw.replace('\\"', '"').replace("\\/", "/")
    try:
        return json.loads(s)
    except Exception:
        return None






















def create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.8,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "POST"]),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": BROWSER_UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    return session


def extract_next_f_merged(html: str) -> str:
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', html, re.S)
    if not chunks:
        return ""
    merged = "".join(chunks)
    try:
        return bytes(merged, "utf-8").decode("unicode_escape")
    except Exception:
        return merged


def extract_balanced_json(decoded: str, key: str) -> Any:
    idx = decoded.find(key)
    if idx == -1:
        raise ValueError(f"Key not found: {key}")

    start = idx + len(key)
    while start < len(decoded) and decoded[start] != ":":
        start += 1
    start += 1
    while start < len(decoded) and decoded[start] not in "[{":
        start += 1

    open_ch = decoded[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    end = None

    for i, ch in enumerate(decoded[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

    if end is None:
        raise ValueError(f"Cannot parse JSON block for key: {key}")

    snippet = decoded[start:end]
    snippet = snippet.replace("$undefined", "null")
    snippet = re.sub(r'"\$D([^\"]+)"', r'"\1"', snippet)
    return json.loads(snippet)


def extract_next_data_payload(html: str) -> dict[str, Any] | None:
    m = re.search(
        r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>\s*(\{.*?\})\s*</script>',
        html,
        re.S,
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def fetch_techurls(session: requests.Session, now: datetime) -> list[RawItem]:
    site_id = "techurls"
    site_name = "TechURLs"
    r = session.get("https://techurls.com/", timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    out: list[RawItem] = []
    for block in soup.select("div.publisher-block"):
        primary = (
            block.select_one(".publisher-text .primary").get_text(strip=True)
            if block.select_one(".publisher-text .primary")
            else block.get("data-publisher", "unknown")
        )
        secondary = (
            block.select_one(".publisher-text .secondary").get_text(strip=True)
            if block.select_one(".publisher-text .secondary")
            else ""
        )
        source = f"{primary} · {secondary}" if secondary and secondary != primary else primary

        for link_row in block.select("div.publisher-link"):
            a = link_row.select_one("a.article-link")
            if not a or not a.get("href"):
                continue
            title = a.get_text(" ", strip=True)
            url = a["href"].strip()

            time_hint = ""
            aside = link_row.select_one(".aside .text")
            if aside:
                time_hint = aside.get("title", "") or aside.get_text(" ", strip=True)

            published = parse_date_any(time_hint, now)
            out.append(
                RawItem(
                    site_id=site_id,
                    site_name=site_name,
                    source=source,
                    title=title,
                    url=url,
                    published_at=published,
                    meta={"time_hint": time_hint},
                )
            )

    return out


def fetch_buzzing(session: requests.Session, now: datetime) -> list[RawItem]:
    site_id = "buzzing"
    site_name = "Buzzing"
    r = session.get("https://www.buzzing.cc/feed.json", timeout=30)
    r.raise_for_status()
    payload = r.json()
    items = payload.get("items", [])

    out: list[RawItem] = []
    for it in items:
        title = (it.get("title") or "").strip()
        url = (it.get("url") or "").strip()
        if not title or not url:
            continue
        source = first_non_empty(
            it.get("source"),
            it.get("site_name"),
            it.get("channel"),
            it.get("category"),
            host_of_url(url),
            site_name,
        )
        published = parse_date_any(it.get("date_published") or it.get("date_modified"), now)
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source=source,
                title=title,
                url=url,
                published_at=published,
                meta={"raw": {k: it.get(k) for k in ("source", "site_name", "channel", "category")}},
            )
        )
    return out


def fetch_iris(session: requests.Session, now: datetime) -> list[RawItem]:
    site_id = "iris"
    site_name = "Info Flow"

    r = session.get("https://iris.findtruman.io/web/info_flow", timeout=30)
    r.raise_for_status()
    html = r.text

    m = re.search(r"const\s+feeds\s*=\s*\[(.*?)\]\s*;", html, re.S)
    if not m:
        return []

    section = m.group(1)
    feeds = re.findall(
        r"\{\s*name:\s*'([^']+)'\s*,\s*url:\s*'([^']+)'\s*\}",
        section,
        re.S,
    )

    out: list[RawItem] = []
    for feed_name, feed_url in feeds:
        try:
            if feedparser is not None:
                parsed = feedparser.parse(feed_url)
                source_name = str(feed_name or getattr(parsed, "feed", {}).get("title") or "Iris Feed")
                for entry in parsed.entries:
                    title = str(entry.get("title", "")).strip()
                    url = str(entry.get("link", "")).strip()
                    if not title or not url:
                        continue
                    published = (
                        parse_date_any(entry.get("published"), now)
                        or parse_date_any(entry.get("updated"), now)
                        or parse_date_any(entry.get("pubDate"), now)
                    )
                    out.append(
                        RawItem(
                            site_id=site_id,
                            site_name=site_name,
                            source=source_name,
                            title=title,
                            url=url,
                            published_at=published,
                            meta={"feed_url": feed_url},
                        )
                    )
                continue

            feed_resp = session.get(feed_url, timeout=30)
            feed_resp.raise_for_status()
            entries = parse_feed_entries_via_xml(feed_resp.content)
            source_name = str(feed_name or "Iris Feed")
            for entry in entries:
                out.append(
                    RawItem(
                        site_id=site_id,
                        site_name=site_name,
                        source=source_name,
                        title=entry["title"],
                        url=entry["link"],
                        published_at=parse_date_any(entry.get("published"), now),
                        meta={"feed_url": feed_url},
                    )
                )
        except Exception:
            # Skip blocked/broken sub feeds and keep remaining feeds.
            continue
    return out


def fetch_bestblogs(session: requests.Session, now: datetime) -> list[RawItem]:
    site_id = "bestblogs"
    site_name = "BestBlogs"

    api = "https://api.bestblogs.dev/api/newsletter/list"
    out: list[RawItem] = []
    seen: set[str] = set()

    try:
        current_page = 1
        page_count = 1

        while current_page <= page_count and current_page <= 12:
            payload = {
                "currentPage": current_page,
                "pageSize": 20,
                "userLanguage": "en",
            }
            r = session.post(api, json=payload, timeout=30)
            r.raise_for_status()
            body = r.json()
            data = body.get("data", {})
            page_count = int(data.get("pageCount", 1) or 1)

            for issue in data.get("dataList", []):
                issue_id = str(issue.get("id", "")).strip()
                title = str(issue.get("title", "")).strip()
                if not issue_id or not title:
                    continue
                url = f"https://www.bestblogs.dev/en/newsletter#{issue_id}"
                if url in seen:
                    continue
                seen.add(url)

                published = parse_unix_timestamp(issue.get("createdTimestamp"))
                out.append(
                    RawItem(
                        site_id=site_id,
                        site_name=site_name,
                        source="Weekly Newsletter",
                        title=title,
                        url=url,
                        published_at=published,
                        meta={
                            "issue_id": issue_id,
                            "article_count": issue.get("articleCount"),
                        },
                    )
                )
            current_page += 1
    except Exception:
        pass

    if out:
        return out

    r = session.get("https://www.bestblogs.dev/en/newsletter", timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    for a in soup.select("a[href*='/newsletter']"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        url = href if href.startswith("http") else urljoin("https://www.bestblogs.dev", href)
        title = a.get_text(" ", strip=True)
        if len(title) < 8:
            continue
        if url in seen:
            continue
        seen.add(url)
        dt = None
        time_tag = a.select_one("time")
        if time_tag:
            dt = parse_date_any(time_tag.get("datetime") or time_tag.get_text(" ", strip=True), now)
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source="Weekly Newsletter",
                title=title,
                url=url,
                published_at=dt,
                meta={},
            )
        )

    return out


def fetch_tophub(session: requests.Session, now: datetime) -> list[RawItem]:
    site_id = "tophub"
    site_name = "TopHub"

    r = session.get("https://tophub.today/", timeout=30)
    r.raise_for_status()
    html = r.content.decode("utf-8", errors="replace")
    if "�" in html:
        for enc in ("gb18030", "utf-8"):
            try:
                candidate = r.content.decode(enc, errors="replace")
                if candidate.count("�") < html.count("�"):
                    html = candidate
            except Exception:
                continue
    soup = BeautifulSoup(html, "html.parser")

    out: list[RawItem] = []
    for block in soup.select(".cc-cd"):
        source_name_tag = block.select_one(".cc-cd-lb span")
        board_tag = block.select_one(".cc-cd-sb-st")
        source_name = source_name_tag.get_text(" ", strip=True) if source_name_tag else "TopHub"
        board_name = board_tag.get_text(" ", strip=True) if board_tag else ""
        source_name = maybe_fix_mojibake(source_name)
        board_name = maybe_fix_mojibake(board_name)
        source = f"{source_name} · {board_name}" if board_name else source_name

        for a in block.select(".cc-cd-cb-l a"):
            href = a.get("href", "").strip()
            row = a.select_one(".cc-cd-cb-ll")
            title_tag = row.select_one(".t") if row else None
            metric_tag = row.select_one(".e") if row else None

            title = (
                title_tag.get_text(" ", strip=True)
                if title_tag
                else a.get_text(" ", strip=True)
            )
            title = maybe_fix_mojibake(title)
            if not title or not href:
                continue

            full_url = href if href.startswith("http") else urljoin("https://tophub.today", href)
            row_text = row.get_text(" ", strip=True) if row else title
            published = parse_relative_time_zh(row_text, now)

            out.append(
                RawItem(
                    site_id=site_id,
                    site_name=site_name,
                    source=source,
                    title=title,
                    url=full_url,
                    published_at=published,
                    meta={"metric": metric_tag.get_text(" ", strip=True) if metric_tag else ""},
                )
            )

    return out


def fetch_zeli(session: requests.Session, now: datetime) -> list[RawItem]:
    site_id = "zeli"
    site_name = "Zeli"
    out: list[RawItem] = []

    url = "https://zeli.app/api/hacker-news?type=hot24h"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    body = r.json()
    posts = body.get("posts", [])
    for p in posts:
        title = str(p.get("title", "")).strip()
        link = str(p.get("url", "")).strip()
        if not title or not link:
            continue
        published = parse_unix_timestamp(p.get("time")) or now
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source="Hacker News · 24h最热",
                title=title,
                url=link,
                published_at=published,
                meta={"hn_id": p.get("id")},
            )
        )

    return out












def fetch_feed_as_official_items(
    session: requests.Session,
    feed: dict[str, Any],
    now: datetime,
    site_id: str = "official_health",
    site_name: str = "Official Health Updates",
) -> list[RawItem]:
    feed_url = feed["xml_url"]
    feed_title = feed["title"]

    resp = session.get(
        feed_url,
        timeout=max(1, int(feed.get("timeout_seconds") or 20)),
        headers={
            "User-Agent": BROWSER_UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    resp.raise_for_status()

    entries: list[dict[str, Any]]
    if feedparser is not None:
        parsed = feedparser.parse(resp.content)
        entries = list(parsed.entries)
    else:
        entries = parse_feed_entries_via_xml(resp.content)

    out: list[RawItem] = []
    include_keywords = [
        keyword.strip().lower()
        for keyword in str(feed.get("include_keywords") or "").split(",")
        if keyword.strip()
    ]
    for entry in entries:
        title = str(entry.get("title", "")).strip()
        link = str(entry.get("link", "")).strip()
        if not title or not link:
            continue
        if include_keywords:
            haystack = f"{title} {link}".lower()
            if not any(keyword in haystack for keyword in include_keywords):
                continue
        published = (
            parse_date_any(entry.get("published"), now)
            or parse_date_any(entry.get("updated"), now)
            or parse_date_any(entry.get("pubDate"), now)
        )
        if not published:
            continue
        if published < now - timedelta(days=OFFICIAL_HEALTH_MAX_AGE_DAYS):
            continue

        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source=feed_title,
                title=maybe_fix_mojibake(title),
                url=link,
                published_at=published,
                meta={
                    "feed_url": feed_url,
                    "feed_home": feed.get("html_url") or "",
                    **configured_feed_meta(feed),
                },
            )
        )

    return out


def feed_entry_title_link_published(entry: dict[str, Any], now: datetime) -> tuple[str, str, datetime | None]:
    title = maybe_fix_mojibake(str(entry.get("title", "")).strip())
    link = str(entry.get("link", "")).strip()
    published = (
        parse_date_any(entry.get("published"), now)
        or parse_date_any(entry.get("updated"), now)
        or parse_date_any(entry.get("pubDate"), now)
    )
    return title, link, published


def feed_keywords(feed: dict[str, Any]) -> list[str]:
    return [
        keyword.strip().lower()
        for keyword in str(feed.get("include_keywords") or "").split(",")
        if keyword.strip()
    ]


def curated_feed_entry_allowed(feed: dict[str, Any], title: str, link: str) -> bool:
    include_keywords = feed_keywords(feed)
    haystack = title.lower()
    if not feed.get("strict_title_filter"):
        haystack = f"{haystack} {link.lower()} {feed.get('title', '').lower()}"
    exclude_keywords = [
        keyword.strip().lower()
        for keyword in str(feed.get("exclude_keywords") or "").split(",")
        if keyword.strip()
    ]
    if exclude_keywords and any(keyword in haystack for keyword in exclude_keywords):
        return False
    return not include_keywords or any(keyword in haystack for keyword in include_keywords)


def parse_curated_media_feed_items(
    feed_content: bytes,
    feed: dict[str, Any],
    now: datetime,
    site_id: str,
    site_name: str,
) -> list[RawItem]:
    feed_url = str(feed["xml_url"])
    feed_title = str(feed["title"])

    if feedparser is not None:
        parsed = feedparser.parse(feed_content)
        entries = list(parsed.entries)
    else:
        entries = parse_feed_entries_via_xml(feed_content)

    out: list[RawItem] = []
    seen_urls: set[str] = set()
    max_entries = max(1, int(feed.get("max_entries") or 8))
    for entry in entries:
        title, link, published = feed_entry_title_link_published(entry, now)
        if not title or not link or not published:
            continue
        if published < now - timedelta(days=MEDICAL_JOURNAL_MAX_AGE_DAYS):
            continue
        if not curated_feed_entry_allowed(feed, title, link):
            continue
        normalized_url = normalize_url(link)
        if normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source=feed_title,
                title=title,
                url=link,
                published_at=published,
                meta={
                    "feed_url": feed_url,
                    "feed_home": feed.get("html_url") or "",
                    "research_only": bool(feed.get("research_only")),
                    "strict_title_filter": bool(feed.get("strict_title_filter")),
                    **configured_feed_meta(feed),
                },
            )
        )
        if len(out) >= max_entries:
            break

    return out


def fetch_official_health_updates(session: requests.Session, now: datetime) -> list[RawItem]:
    out: list[RawItem] = []

    for feed in OFFICIAL_HEALTH_FEEDS:
        try:
            out.extend(fetch_feed_as_official_items(session, feed, now))
        except Exception:
            continue

    if not out:
        raise ValueError("No official health update sources returned items")

    return out


def fetch_medical_journals(session: requests.Session, now: datetime) -> list[RawItem]:
    out: list[RawItem] = []
    failures: list[str] = []

    for feed in MEDICAL_JOURNAL_FEEDS:
        try:
            resp = session.get(
                str(feed["xml_url"]),
                timeout=20,
                headers={
                    "User-Agent": BROWSER_UA,
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
                },
            )
            resp.raise_for_status()
            out.extend(parse_curated_media_feed_items(resp.content, feed, now, "medical_journals", "Medical Journals"))
        except Exception:
            failures.append(str(feed.get("title") or feed.get("xml_url") or "unknown"))

    if not out and failures:
        raise ValueError(f"No medical journal items parsed; failed feeds: {', '.join(failures[:4])}")
    return out


def fetch_medical_media(session: requests.Session, now: datetime) -> list[RawItem]:
    out: list[RawItem] = []
    failures: list[str] = []

    for feed in MEDICAL_MEDIA_FEEDS:
        try:
            resp = session.get(
                str(feed["xml_url"]),
                timeout=20,
                headers={
                    "User-Agent": BROWSER_UA,
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
                },
            )
            resp.raise_for_status()
            out.extend(parse_curated_media_feed_items(resp.content, feed, now, "medical_media", "Medical Media"))
        except Exception:
            failures.append(str(feed.get("title") or feed.get("xml_url") or "unknown"))

    if not out and failures:
        raise ValueError(f"No medical media items parsed; failed feeds: {', '.join(failures[:4])}")
    return out


def fetch_configured_feed(
    session: requests.Session,
    now: datetime,
    site_id: str,
    site_name: str,
    feed: dict[str, Any],
) -> list[RawItem]:
    if site_id == "official_health":
        return fetch_feed_as_official_items(session, feed, now, site_id=site_id, site_name=site_name)
    response = session.get(
        str(feed["xml_url"]),
        timeout=max(1, int(feed.get("timeout_seconds") or 20)),
        headers={
            "User-Agent": BROWSER_UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    response.raise_for_status()
    return parse_curated_media_feed_items(response.content, feed, now, site_id, site_name)


def collect_configured_sources(
    session: requests.Session,
    now: datetime,
    groups: dict[str, list[dict[str, Any]]],
) -> tuple[list[RawItem], list[dict[str, Any]], list[dict[str, Any]]]:
    raw_items: list[RawItem] = []
    sites: list[dict[str, Any]] = []
    source_statuses: list[dict[str, Any]] = []
    for site_id, feeds in groups.items():
        site_name = LEGACY_SOURCE_SITE_NAMES[site_id]
        site_start = time.perf_counter()
        site_items: list[RawItem] = []
        site_errors: list[str] = []
        successful_sources = 0
        for feed in feeds:
            start = time.perf_counter()
            error: str | None = None
            items: list[RawItem] = []
            try:
                items = fetch_configured_feed(session, now, site_id, site_name, feed)
                successful_sources += 1
                site_items.extend(items)
            except Exception as exc:
                error = str(exc)
                site_errors.append(f"{feed.get('title') or feed.get('source_id')}: {error}")
            source_statuses.append(
                {
                    "source_id": str(feed.get("source_id") or ""),
                    "source_name": str(feed.get("title") or feed.get("source_id") or ""),
                    "legacy_site_id": site_id,
                    "feed_url": str(feed.get("xml_url") or ""),
                    "ok": error is None,
                    "item_count": len(items),
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "error": error,
                }
            )
        raw_items.extend(site_items)
        failed_sources = len(feeds) - successful_sources
        sites.append(
            {
                "site_id": site_id,
                "site_name": site_name,
                "ok": successful_sources > 0,
                "item_count": len(site_items),
                "duration_ms": int((time.perf_counter() - site_start) * 1000),
                "error": "; ".join(site_errors[:4]) if site_errors else None,
                "source_count": len(feeds),
                "successful_source_count": successful_sources,
                "failed_source_count": failed_sources,
            }
        )
    return raw_items, sites, source_statuses


def collect_all(
    session: requests.Session,
    now: datetime,
    sources_config: Path | None = None,
) -> tuple[list[RawItem], list[dict[str, Any]], list[dict[str, Any]]]:
    configured_groups, _config_result = configured_feed_groups(sources_config)
    if configured_groups:
        return collect_configured_sources(session, now, configured_groups)

    tasks = [
        ("official_health", "Official Health Updates", fetch_official_health_updates),
        ("medical_journals", "Medical Journals", fetch_medical_journals),
        ("medical_media", "Medical Media", fetch_medical_media),
    ]

    raw_items: list[RawItem] = []
    statuses: list[dict[str, Any]] = []

    for site_id, site_name, fn in tasks:
        start = time.perf_counter()
        error = None
        count = 0
        try:
            items = fn(session, now)
            count = len(items)
            raw_items.extend(items)
        except Exception as exc:
            error = str(exc)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        statuses.append(
            {
                "site_id": site_id,
                "site_name": site_name,
                "ok": error is None,
                "item_count": count,
                "duration_ms": elapsed_ms,
                "error": error,
            }
        )

    return raw_items, statuses, []


def parse_opml_subscriptions(opml_path: Path) -> list[dict[str, str]]:
    root = ET.parse(opml_path).getroot()
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    for outline in root.findall(".//outline"):
        xml_url = str(outline.attrib.get("xmlUrl") or "").strip()
        if not xml_url:
            continue
        if xml_url in seen:
            continue
        seen.add(xml_url)
        title = first_non_empty(
            outline.attrib.get("title"),
            outline.attrib.get("text"),
            host_of_url(xml_url),
            xml_url,
        )
        html_url = str(outline.attrib.get("htmlUrl") or "").strip()
        out.append(
            {
                "title": title,
                "xml_url": xml_url,
                "html_url": html_url,
            }
        )
    return out


def resolve_official_rss_url(feed_url: str) -> tuple[str | None, str | None]:
    src = (feed_url or "").strip()
    if not src:
        return None, "empty_url"
    if src in RSS_FEED_SKIP_EXACT:
        return None, "no_official_rss_or_unreachable"
    for prefix in RSS_FEED_SKIP_PREFIXES:
        if src.startswith(prefix):
            return None, "no_official_rss_for_source_type"
    replaced = RSS_FEED_REPLACEMENTS.get(src)
    if replaced:
        return replaced, "official_replacement"
    return src, None


def resolve_opml_bridge_source(feed_url: str, html_url: str = "") -> dict[str, str] | None:
    src = (feed_url or "").strip()
    parsed = urlparse(src)
    path = parsed.path.strip("/")
    parts = [p for p in path.split("/") if p]

    if parsed.netloc == "rsshub.app" and len(parts) >= 3 and parts[:2] == ["telegram", "channel"]:
        slug = parts[2]
        return {
            "bridge_type": "telegram",
            "bridge_slug": slug,
            "url": f"https://t.me/s/{slug}",
        }

    if parsed.netloc == "rsshub.app" and len(parts) >= 3 and parts[0] == "jike":
        kind = parts[1]
        ident = parts[2]
        if kind == "topic":
            return {
                "bridge_type": "jike",
                "bridge_kind": "topic",
                "bridge_slug": ident,
                "url": f"https://m.okjike.com/topics/{ident}",
            }
        if kind == "user":
            return {
                "bridge_type": "jike",
                "bridge_kind": "user",
                "bridge_slug": ident,
                "url": f"https://m.okjike.com/users/{ident}",
            }

    html = (html_url or "").strip()
    if html.startswith("https://t.me/s/"):
        slug = html.rstrip("/").split("/")[-1]
        return {"bridge_type": "telegram", "bridge_slug": slug, "url": html}
    if html.startswith("https://m.okjike.com/topics/"):
        ident = html.rstrip("/").split("/")[-1]
        return {"bridge_type": "jike", "bridge_kind": "topic", "bridge_slug": ident, "url": html}
    if html.startswith("https://m.okjike.com/users/"):
        ident = html.rstrip("/").split("/")[-1]
        return {"bridge_type": "jike", "bridge_kind": "user", "bridge_slug": ident, "url": html}

    return None


def compact_title(text: str, limit: int = 96) -> str:
    s = re.sub(r"\s+", " ", text or "").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1].rstrip() + "…"


def parse_telegram_public_items(
    html: str,
    *,
    now: datetime,
    source_name: str,
    slug: str,
) -> list[RawItem]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[RawItem] = []
    for msg in soup.select(".tgme_widget_message"):
        data_post = str(msg.get("data-post") or "").strip()
        if not data_post:
            continue
        text_node = msg.select_one(".tgme_widget_message_text")
        text = text_node.get_text(" ", strip=True) if text_node else ""
        if not text:
            preview_title = msg.select_one(".tgme_widget_message_link_preview_title")
            text = preview_title.get_text(" ", strip=True) if preview_title else ""
        if not text:
            continue
        time_node = msg.select_one("time[datetime]")
        published = parse_date_any(time_node.get("datetime") if time_node else None, now)
        if not published:
            continue
        url = f"https://t.me/{data_post}"
        out.append(
            RawItem(
                site_id="opmlrss",
                site_name="OPML RSS",
                source=source_name,
                title=compact_title(text),
                url=url,
                published_at=published,
                meta={"bridge_type": "telegram", "bridge_slug": slug, "feed_home": f"https://t.me/s/{slug}"},
            )
        )
    return out


def parse_jike_public_items(
    html: str,
    *,
    now: datetime,
    source_name: str,
    source_url: str,
) -> list[RawItem]:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None or not script.string:
        return []
    try:
        payload = json.loads(script.string)
    except Exception:
        return []
    page_props = payload.get("props", {}).get("pageProps", {})
    posts = page_props.get("posts") or []
    out: list[RawItem] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        post_id = str(post.get("id") or "").strip()
        text = str(post.get("content") or "").strip()
        if not post_id or not text:
            continue
        published = parse_date_any(post.get("createdAt") or post.get("actionTime"), now)
        if not published:
            continue
        out.append(
            RawItem(
                site_id="opmlrss",
                site_name="OPML RSS",
                source=source_name,
                title=compact_title(text),
                url=f"https://m.okjike.com/originalPosts/{post_id}",
                published_at=published,
                meta={"bridge_type": "jike", "feed_home": source_url},
            )
        )
    return out


def fetch_opml_rss(
    now: datetime,
    opml_path: Path,
    max_feeds: int = 0,
    configured_urls: set[str] | None = None,
) -> tuple[list[RawItem], dict[str, Any], list[dict[str, Any]]]:
    all_feeds = parse_opml_subscriptions(opml_path)
    feeds, duplicate_feeds = dedupe_opml_feeds(all_feeds, configured_urls)
    if max_feeds > 0:
        feeds = feeds[:max_feeds]

    out: list[RawItem] = []
    feed_statuses: list[dict[str, Any]] = []
    for feed in duplicate_feeds:
        original_url = feed["xml_url"]
        feed_id = hashlib.sha1(original_url.encode("utf-8")).hexdigest()[:10]
        feed_statuses.append(
            {
                "site_id": f"opmlrss:{feed_id}",
                "site_name": "OPML RSS",
                "feed_title": feed["title"],
                "feed_url": original_url,
                "effective_feed_url": None,
                "ok": True,
                "item_count": 0,
                "duration_ms": 0,
                "error": None,
                "skipped": True,
                "skip_reason": "configured_source_duplicate",
                "replaced": False,
            }
        )
    resolved_feeds: list[dict[str, str]] = []

    for feed in feeds:
        original_url = feed["xml_url"]
        bridge = resolve_opml_bridge_source(original_url, feed.get("html_url") or "")
        if bridge:
            record = dict(feed)
            record["xml_url_original"] = original_url
            record["xml_url"] = bridge["url"]
            record["replaced"] = True
            record.update(bridge)
            resolved_feeds.append(record)
            continue

        resolved_url, skip_reason = resolve_official_rss_url(original_url)
        if not resolved_url:
            feed_id = hashlib.sha1(original_url.encode("utf-8")).hexdigest()[:10]
            feed_statuses.append(
                {
                    "site_id": f"opmlrss:{feed_id}",
                    "site_name": "OPML RSS",
                    "feed_title": feed["title"],
                    "feed_url": original_url,
                    "effective_feed_url": None,
                    "ok": True,
                    "item_count": 0,
                    "duration_ms": 0,
                    "error": None,
                    "skipped": True,
                    "skip_reason": skip_reason or "skipped",
                    "replaced": False,
                }
            )
            continue
        record = dict(feed)
        record["xml_url_original"] = original_url
        record["xml_url"] = resolved_url
        record["replaced"] = bool(resolved_url != original_url)
        resolved_feeds.append(record)

    def fetch_single_feed(feed: dict[str, str]) -> tuple[list[RawItem], dict[str, Any]]:
        feed_url = feed["xml_url"]
        original_feed_url = str(feed.get("xml_url_original") or feed_url)
        feed_title = feed["title"]
        feed_id = hashlib.sha1(feed_url.encode("utf-8")).hexdigest()[:10]
        start = time.perf_counter()
        error = None
        local_items: list[RawItem] = []

        try:
            resp = requests.get(
                feed_url,
                timeout=12,
                headers={
                    "User-Agent": BROWSER_UA,
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            )
            resp.raise_for_status()

            bridge_type = str(feed.get("bridge_type") or "")
            if bridge_type == "telegram":
                local_items = parse_telegram_public_items(
                    resp.text,
                    now=now,
                    source_name=feed_title,
                    slug=str(feed.get("bridge_slug") or ""),
                )
            elif bridge_type == "jike":
                local_items = parse_jike_public_items(
                    resp.text,
                    now=now,
                    source_name=feed_title,
                    source_url=feed_url,
                )
            elif feedparser is not None:
                parsed = feedparser.parse(resp.content)
                source_name = first_non_empty(
                    feed_title,
                    getattr(parsed, "feed", {}).get("title"),
                    host_of_url(feed_url),
                )
                entries = parsed.entries
                for entry in entries:
                    title = str(entry.get("title", "")).strip()
                    link = str(entry.get("link", "")).strip()
                    if not title or not link:
                        continue
                    published = (
                        parse_date_any(entry.get("published"), now)
                        or parse_date_any(entry.get("updated"), now)
                        or parse_date_any(entry.get("pubDate"), now)
                    )
                    if not published:
                        continue
                    local_items.append(
                        RawItem(
                            site_id="opmlrss",
                            site_name="OPML RSS",
                            source=source_name,
                            title=title,
                            url=link,
                            published_at=published,
                            meta={
                                "feed_url": feed_url,
                                "feed_home": feed.get("html_url") or "",
                            },
                        )
                    )
            else:
                source_name = first_non_empty(feed_title, host_of_url(feed_url))
                entries = parse_feed_entries_via_xml(resp.content)
                for entry in entries:
                    published = parse_date_any(entry.get("published"), now)
                    if not published:
                        continue
                    local_items.append(
                        RawItem(
                            site_id="opmlrss",
                            site_name="OPML RSS",
                            source=source_name,
                            title=entry.get("title", ""),
                            url=entry.get("link", ""),
                            published_at=published,
                            meta={
                                "feed_url": feed_url,
                                "feed_home": feed.get("html_url") or "",
                            },
                        )
                    )
        except Exception as exc:
            error = str(exc)

        duration_ms = int((time.perf_counter() - start) * 1000)
        status = {
            "site_id": f"opmlrss:{feed_id}",
            "site_name": "OPML RSS",
            "feed_title": feed_title,
            "feed_url": original_feed_url,
            "effective_feed_url": feed_url,
            "ok": error is None,
            "item_count": len(local_items),
            "duration_ms": duration_ms,
            "error": error,
            "skipped": False,
            "skip_reason": None,
            "replaced": bool(original_feed_url != feed_url),
            "bridge_type": feed.get("bridge_type"),
        }
        return local_items, status

    if resolved_feeds:
        worker_count = min(20, max(4, len(resolved_feeds)))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(fetch_single_feed, feed) for feed in resolved_feeds]
            for future in as_completed(futures):
                items, status = future.result()
                out.extend(items)
                feed_statuses.append(status)

    feed_statuses.sort(key=lambda x: str(x.get("feed_title") or x.get("feed_url") or ""))
    total_duration_ms = sum(int(s.get("duration_ms") or 0) for s in feed_statuses)
    ok_feeds = sum(1 for s in feed_statuses if s["ok"])
    failed_feeds = sum(1 for s in feed_statuses if not s["ok"])
    skipped_feeds = sum(1 for s in feed_statuses if s.get("skipped"))
    replaced_feeds = sum(1 for s in feed_statuses if s.get("replaced"))

    summary_status = {
        "site_id": "opmlrss",
        "site_name": "OPML RSS",
        "ok": ok_feeds > 0,
        "partial_failures": failed_feeds,
        "item_count": len(out),
        "duration_ms": total_duration_ms,
        "error": None if failed_feeds == 0 else f"{failed_feeds} feeds failed",
        "feed_count": len(all_feeds),
        "effective_feed_count": len(resolved_feeds),
        "ok_feed_count": ok_feeds,
        "failed_feed_count": failed_feeds,
        "skipped_feed_count": skipped_feeds,
        "replaced_feed_count": replaced_feeds,
    }
    return out, summary_status, feed_statuses


def load_archive(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    items = payload.get("items", [])
    out: dict[str, dict[str, Any]] = {}
    if isinstance(items, list):
        for it in items:
            item_id = it.get("id")
            if item_id:
                out[item_id] = it
    elif isinstance(items, dict):
        for item_id, it in items.items():
            if isinstance(it, dict):
                it["id"] = item_id
                out[item_id] = it
    return out


def event_time(record: dict[str, Any]) -> datetime | None:
    # RSS sources must rely on the source's publish time only.
    # first_seen_at is fetch time and would falsely mark historical items as "24h".
    if str(record.get("site_id") or "") == "opmlrss":
        return parse_iso(record.get("published_at"))
    return parse_iso(record.get("published_at")) or parse_iso(record.get("first_seen_at"))


SOURCE_TIER_BY_SITE: dict[str, tuple[str, str, int]] = {
    "official_health": ("official", "官方一手源", 0),
    "medical_journals": ("medical_journal", "医学期刊", 2),
    "medical_media": ("medical_media", "医疗媒体", 2),
    "opmlrss": ("user_opml", "RSS/OPML", 3),
    "techurls": ("discussion", "热议参考", 5),
    "buzzing": ("discussion", "热议参考", 5),
    "iris": ("discussion", "热议参考", 5),
    "tophub": ("discussion", "热议参考", 5),
    "zeli": ("discussion", "热议参考", 5),
    "bestblogs": ("discussion", "热议参考", 5),
    "newsnow": ("discussion", "热议参考", 5),
}

SOURCE_TIER_IMPORTANCE = {
    "s": 1.0,
    "a": 0.82,
    "b": 0.62,
    "c": 0.38,
    "official": 1.0,
    "medical_journal": 0.58,
    "medical_media": 0.58,
    "community": 0.54,
    "builders": 0.62,
    "user_opml": 0.5,
    "self_media": 0.48,
    "advanced": 0.45,
    "discussion": 0.32,
    "other": 0.25,
}

CONFIGURED_SOURCE_TIERS: dict[str, tuple[str, int, float]] = {
    "s": ("S级", 0, 1.0),
    "a": ("A级", 1, 0.82),
    "b": ("B级", 2, 0.62),
    "c": ("C级", 3, 0.38),
}

TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "for",
    "from",
    "in",
    "into",
    "is",
    "new",
    "of",
    "on",
    "the",
    "to",
    "with",
    "发布",
    "推出",
    "上线",
    "更新",
}

VENDOR_ALIASES = {
    "openai": "openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "google": "google",
    "deepmind": "google",
    "gemini": "google",
    "microsoft": "microsoft",
    "github": "github",
    "huggingface": "huggingface",
    "hugging face": "huggingface",
    "meta": "meta",
    "llama": "meta",
    "deepseek": "deepseek",
    "mistral": "mistral",
    "xai": "xai",
    "grok": "xai",
}

MODEL_RE = re.compile(
    r"(?i)\b("
    r"gpt[-\s]?\d+(?:\.\d+)?[a-z]*|"
    r"claude(?:[-\s]?(?:opus|sonnet|haiku))?[-\s]?\d+(?:\.\d+)?|"
    r"gemini[-\s]?\d+(?:\.\d+)?|"
    r"llama[-\s]?\d+(?:\.\d+)?|"
    r"deepseek[-\s]?[a-z0-9.]+|"
    r"grok[-\s]?\d+(?:\.\d+)?|"
    r"mistral[-\s]?[a-z0-9.]+"
    r")\b"
)


def source_tier_for_site(site_id: str) -> dict[str, Any]:
    sid = str(site_id or "").strip().lower()
    if sid.startswith("opmlrss"):
        sid = "opmlrss"
    tier, label, rank = SOURCE_TIER_BY_SITE.get(sid, ("other", "其他来源", 9))
    return {"source_tier": tier, "source_tier_label": label, "source_tier_rank": rank}


def add_source_tier_fields(record: dict[str, Any]) -> dict[str, Any]:
    out = dict(record)
    legacy = source_tier_for_site(str(out.get("site_id") or ""))
    configured_tier = str(out.get("source_tier") or "").strip().lower()
    if configured_tier in CONFIGURED_SOURCE_TIERS:
        label, rank, authority = CONFIGURED_SOURCE_TIERS[configured_tier]
        out.update(
            {
                "source_tier": configured_tier,
                "source_tier_label": label,
                "source_tier_rank": rank,
                "source_tier_legacy": legacy["source_tier"],
                "source_authority_score": out.get("source_authority_score", authority),
            }
        )
    else:
        out.update(legacy)
        out.setdefault("source_tier_legacy", legacy["source_tier"])
    return out


def add_medical_intelligence_fields(
    record: dict[str, Any],
    source_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add V1 medical fields while retaining the existing public contract."""
    out = add_medical_relevance_fields(record, source_meta=source_meta)
    out = add_source_tier_fields(out)
    signals = [str(value) for value in out.get("matched_keywords", []) if str(value).strip()][:3]
    category_label = str(out.get("category_label") or "医疗情报")
    out["recommendation_reason"] = (
        f"{category_label}：命中 {' / '.join(signals)}" if signals else f"{category_label}：通过医疗相关性规则筛选"
    )
    return apply_persona_scores(out)


def source_tier_sort_key(record: dict[str, Any]) -> tuple[int, float, str]:
    tier = add_source_tier_fields(record)
    ts = event_time(record)
    return (int(tier["source_tier_rank"]), -(ts.timestamp() if ts else 0), str(record.get("title") or ""))


EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
SECRET_LIKE_RE = re.compile(r"\b(sk-(?!hynix\b)[A-Za-z0-9_-]{12,}|(?:api[_-]?key|secret|token)=([^\s&]{6,}))\b", re.I)


def redact_public_text(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    text = EMAIL_RE.sub("[redacted-email]", text)
    return SECRET_LIKE_RE.sub("[redacted-secret]", text)


def sanitize_public_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_public_text(value)
    if isinstance(value, list):
        return [sanitize_public_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_public_value(val) for key, val in value.items()}
    return value


def sanitize_public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return sanitize_public_value(payload)


















def env_flag(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def env_flag_default(name: str, default: bool) -> bool:
    """Three-state toggle: unset/blank -> default; explicit truthy/falsey wins.

    Used for the *_ENABLED switches so API-key presence is the primary driver
    (key in env -> source runs) while ENABLED stays available as an explicit
    kill switch: set it to 0/false/no/off to force a paid source off even when a
    key is present."""
    raw = str(os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name) or default).strip() or default)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(str(os.environ.get(name) or default).strip() or default)
    except ValueError:
        return default




















































def is_credible_xiaohongshu_published_at(published: datetime | None, now: datetime) -> bool:
    if not published:
        return False
    return datetime(2013, 1, 1, tzinfo=UTC) <= published <= now.astimezone(UTC)










def tikhub_raw_item_key(item: RawItem) -> str:
    post_id = str((item.meta or {}).get("post_id") or "").strip()
    if post_id:
        return f"{item.site_id}:{post_id}"
    return f"{item.site_id}:{normalize_url(item.url)}:{item.title.strip()}"






def has_mojibake_noise(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"(Ã|Â|â€|æ·|�)", text))


def normalize_source_for_display(site_id: str, source: str, url: str) -> str:
    src = (source or "").strip()
    if not src:
        host = host_of_url(url)
        if host.startswith("www."):
            host = host[4:]
        return host or "未分区"
    if site_id == "buzzing" and src.lower() == "buzzing":
        host = host_of_url(url)
        if host.startswith("www."):
            host = host[4:]
        return host or src
    return src


def is_medical_related_record(record: dict[str, Any]) -> bool:
    if has_mojibake_noise(str(record.get("source") or "")) or has_mojibake_noise(str(record.get("title") or "")):
        return False
    return bool(score_medical_relevance(record)["is_medical_related"])


def load_title_zh_cache(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if str(k).strip() and str(v).strip()}
    except Exception:
        pass
    return {}


def translate_to_zh_cn(session: requests.Session, text: str) -> str | None:
    s = (text or "").strip()
    if not s:
        return None
    try:
        r = session.get(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "gtx",
                "sl": "auto",
                "tl": "zh-CN",
                "dt": "t",
                "q": s,
            },
            timeout=12,
        )
        r.raise_for_status()
        payload = r.json()
        if not isinstance(payload, list) or not payload:
            return None
        segs = payload[0]
        if not isinstance(segs, list):
            return None
        translated = "".join(str(seg[0]) for seg in segs if isinstance(seg, list) and seg and seg[0])
        translated = translated.strip()
        if translated and translated != s:
            return translated
    except Exception:
        return None
    return None


def add_bilingual_fields(
    items_medical: list[dict[str, Any]],
    items_all: list[dict[str, Any]],
    session: requests.Session,
    cache: dict[str, str],
    max_new_translations: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    zh_by_url: dict[str, str] = {}
    for it in items_all:
        title = str(it.get("title") or "").strip()
        url = normalize_url(str(it.get("url") or ""))
        if title and url and has_cjk(title):
            zh_by_url[url] = title

    translated_now = 0

    def enrich(item: dict[str, Any], allow_translate: bool) -> dict[str, Any]:
        nonlocal translated_now
        out = dict(item)
        title = str(out.get("title") or "").strip()
        url = normalize_url(str(out.get("url") or ""))

        out["title_original"] = title
        out["title_en"] = None
        out["title_zh"] = None
        out["title_bilingual"] = title

        if has_cjk(title):
            out["title_zh"] = title
            return out

        if not is_mostly_english(title):
            return out

        out["title_en"] = title

        zh_title = zh_by_url.get(url)
        if not zh_title:
            zh_title = cache.get(title)
        if not zh_title and allow_translate and translated_now < max_new_translations:
            tr = translate_to_zh_cn(session, title)
            if tr and has_cjk(tr):
                zh_title = tr
                cache[title] = tr
                translated_now += 1

        if zh_title:
            out["title_zh"] = zh_title
            out["title_bilingual"] = f"{zh_title} / {title}"
        return out

    medical_out = [enrich(it, allow_translate=True) for it in items_medical]
    all_out = [enrich(it, allow_translate=False) for it in items_all]
    return medical_out, all_out, cache


def dedupe_items_by_title_url(items: list[dict[str, Any]], random_pick: bool = True) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        site_id = str(item.get("site_id") or "").strip().lower()
        title = str(item.get("title_original") or item.get("title") or "").strip().lower()
        url = normalize_url(str(item.get("url") or ""))
        key = f"{title}||{url}"
        groups.setdefault(key, []).append(item)

    out: list[dict[str, Any]] = []
    for values in groups.values():
        if random_pick:
            out.append(random.choice(values))
        else:
            chosen = min(values, key=source_tier_sort_key)
            out.append(chosen)

    out.sort(key=source_tier_sort_key)
    return out


def suppress_near_duplicate_items(
    items: list[dict[str, Any]],
    window_hours: float = 6.0,
    similarity_threshold: float = 0.9,
) -> list[dict[str, Any]]:
    """Collapse near-identical items from the same site (rewritten syndication,
    e.g. "推出法案" vs "推出立法") that exact title||url dedup cannot catch.
    Keeps the more authoritative copy (tier, then medical_score, then earliest)."""

    def quality(item: dict[str, Any]) -> tuple:
        tier_rank = item.get("source_tier_rank")
        try:
            tier_rank = int(tier_rank)
        except Exception:
            tier_rank = 99
        try:
            score = float(item.get("medical_score") or 0)
        except Exception:
            score = 0.0
        ts = event_time(item) or datetime.max.replace(tzinfo=UTC)
        return (-tier_rank, score, -ts.timestamp())

    by_site: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_site.setdefault(str(item.get("site_id") or ""), []).append(item)

    dropped_ids: set[str] = set()
    for site_items in by_site.values():
        ordered = sorted(site_items, key=lambda x: event_time(x) or datetime.min.replace(tzinfo=UTC))
        kept: list[tuple[dict[str, Any], str, set[str], datetime | None]] = []
        for item in ordered:
            title = normalized_story_title(item)
            tokens = title_tokens(title)
            ts = event_time(item)
            if not title_is_mergeable(title):
                kept.append((item, title, tokens, ts))
                continue
            duplicate_of = None
            for kept_entry in reversed(kept[-60:]):
                other, other_title, other_tokens, other_ts = kept_entry
                if ts and other_ts and abs((ts - other_ts).total_seconds()) / 3600 > window_hours:
                    continue
                if not tokens or not other_tokens:
                    continue
                jaccard = len(tokens & other_tokens) / len(tokens | other_tokens)
                if jaccard < 0.5:
                    continue
                if title_similarity(title, other_title) >= similarity_threshold and story_titles_can_merge(title, other_title):
                    duplicate_of = kept_entry
                    break
            if duplicate_of is None:
                kept.append((item, title, tokens, ts))
                continue
            other = duplicate_of[0]
            if quality(item) > quality(other):
                dropped_ids.add(str(other.get("id") or id(other)))
                kept[kept.index(duplicate_of)] = (item, title, tokens, ts)
            else:
                dropped_ids.add(str(item.get("id") or id(item)))

    return [item for item in items if str(item.get("id") or id(item)) not in dropped_ids]


def canonical_story_url(raw_url: str) -> str:
    normalized = normalize_url(raw_url)
    try:
        parsed = urlparse(normalized)
    except Exception:
        return normalized
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if query_pairs:
        identity_keys = {"id", "item", "p"}
        kept = [(k, v) for k, v in query_pairs if k.lower() in identity_keys]
        parsed = parsed._replace(query=urlencode(kept, doseq=True))
    return urlunparse(parsed).rstrip("/")


def title_tokens(title: str) -> set[str]:
    compact = re.sub(r"https?://\S+", " ", str(title or "").lower())
    tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", compact)
    return {tok for tok in tokens if tok not in TITLE_STOPWORDS and len(tok) >= 2}


def normalized_story_title(item: dict[str, Any]) -> str:
    title = str(item.get("title_original") or item.get("title") or "").strip().lower()
    if item.get("title_bilingual"):
        title = re.sub(r"\s*/\s*.+$", "", title)
    return re.sub(r"\s+", " ", title)


def title_is_mergeable(title: str) -> bool:
    tokens = title_tokens(title)
    return len(tokens) >= 4 and len(str(title or "").strip()) >= 18


def title_similarity(a: str, b: str) -> float:
    ta = title_tokens(a)
    tb = title_tokens(b)
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / len(ta | tb)
    sequence = SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return round(max(sequence, (sequence * 0.6) + (jaccard * 0.4)), 4)


def title_entities(title: str) -> tuple[set[str], set[str]]:
    lower = str(title or "").lower()
    vendors = {canonical for alias, canonical in VENDOR_ALIASES.items() if alias in lower}
    models = {re.sub(r"\s+", "-", match.group(1).lower()) for match in MODEL_RE.finditer(lower)}
    return vendors, models


def story_titles_can_merge(a: str, b: str) -> bool:
    vendors_a, models_a = title_entities(a)
    vendors_b, models_b = title_entities(b)
    if vendors_a and vendors_b and vendors_a.isdisjoint(vendors_b):
        return False
    if models_a and models_b and models_a.isdisjoint(models_b):
        return False
    return True


def recency_score(record: dict[str, Any], now: datetime, window_hours: int) -> float:
    ts = event_time(record)
    if not ts:
        return 0.0
    age_hours = max(0.0, (now - ts).total_seconds() / 3600)
    return max(0.0, min(1.0, (float(window_hours) - age_hours) / max(1.0, float(window_hours))))


def headline_freshness_score(record: dict[str, Any], now: datetime, half_life_hours: float = 48.0) -> float:
    ts = event_time(record)
    if not ts:
        return 0.0
    age_hours = max(0.0, (now - ts).total_seconds() / 3600)
    return max(0.0, min(1.0, 0.5 ** (age_hours / max(1.0, half_life_hours))))


def medical_relevance_score(record: dict[str, Any]) -> float:
    value = record.get("medical_relevance_score")
    if value is None:
        value = record.get("medical_score")
    if value is None and isinstance(record.get("medical_relevance"), dict):
        value = record["medical_relevance"].get("score")
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 1.0 if record.get("medical_is_related") else 0.0




def editorial_score(record: dict[str, Any]) -> float:
    """External or internal editorial strength used by the headline ranker."""
    value = record.get("curated_score")
    try:
        if value is not None:
            score = float(value)
            return max(0.0, min(1.0, score / 100 if score > 1 else score))
    except Exception:
        pass
    site_id = str(record.get("site_id") or "")
    if site_id == "official_health":
        return 0.9
    if record.get("medical_is_related"):
        return max(0.45, medical_relevance_score(record) * 0.72)
    return medical_relevance_score(record) * 0.6


def story_id_for_item(item: dict[str, Any]) -> str:
    url = canonical_story_url(str(item.get("url") or ""))
    title = normalized_story_title(item)
    basis = url or title or str(item.get("id") or "")
    return "story_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def calculate_item_importance(
    item: dict[str, Any],
    now: datetime,
    window_hours: int,
    duplicate_count: int = 1,
) -> dict[str, Any]:
    tier = str(item.get("source_tier") or source_tier_for_site(str(item.get("site_id") or "")).get("source_tier"))
    source_score = SOURCE_TIER_IMPORTANCE.get(tier, SOURCE_TIER_IMPORTANCE["other"])
    relevance = medical_relevance_score(item)
    recency = headline_freshness_score(item, now)
    editorial = editorial_score(item)
    heat = min(1.0, max(0, duplicate_count - 1) / 4)
    score = (editorial * 0.3) + (source_score * 0.22) + (relevance * 0.2) + (recency * 0.18) + (heat * 0.1)
    return {
        "score": round(max(0.0, min(1.0, score)), 4),
        "breakdown": {
            "editorial": round(editorial, 4),
            "source_tier": round(source_score, 4),
            "medical_relevance": round(relevance, 4),
            "recency": round(recency, 4),
            "story_heat": round(heat, 4),
        },
    }


def story_category(score: float, primary_item: dict[str, Any], duplicate_count: int) -> str:
    tier = str(primary_item.get("source_tier") or source_tier_for_site(str(primary_item.get("site_id") or "")).get("source_tier"))
    if tier in {"s", "official"}:
        return "official"
    if duplicate_count >= 3:
        return "multi_source"
    if score >= 0.72:
        return "industry"
    return "watch"


def importance_label(category: str) -> str:
    return {
        "official": "官方更新",
        "multi_source": "多源热议",
        "industry": "行业动态",
        "watch": "值得关注",
    }.get(category, "值得关注")


def choose_primary_story_item(
    items: list[dict[str, Any]],
    now: datetime,
    window_hours: int,
) -> dict[str, Any]:
    def key(item: dict[str, Any]) -> tuple[int, float, float, str]:
        tier_rank = int(add_source_tier_fields(item).get("source_tier_rank", 9))
        importance = calculate_item_importance(item, now, window_hours, duplicate_count=len(items))["score"]
        ts = event_time(item)
        return (tier_rank, -importance, -(ts.timestamp() if ts else 0), str(item.get("title") or ""))

    return min(items, key=key)


def story_item_link(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "title": item.get("title_bilingual") or item.get("title"),
        "url": item.get("url"),
        "source": item.get("source"),
        "source_name": item.get("site_name"),
        "site_id": item.get("site_id"),
        "published_at": item.get("published_at"),
        "category": item.get("category"),
        "category_label": item.get("category_label"),
        "source_tier": item.get("source_tier"),
        "source_authority_score": item.get("source_authority_score"),
        "is_official": item.get("is_official"),
        "is_policy": item.get("is_policy"),
        "importance_score": item.get("importance_score"),
        "recommendation_reason": item.get("recommendation_reason"),
        "persona_scores": item.get("persona_scores"),
        "topic_value": item.get("topic_value"),
        "content_angles": item.get("content_angles"),
    }


def story_reasons(primary: dict[str, Any], score: float, duplicate_count: int) -> list[str]:
    reasons: list[str] = []
    tier = add_source_tier_fields(primary)
    if tier["source_tier"] in {"s", "official"}:
        reasons.append("official_source")
    if duplicate_count >= 2:
        reasons.append("multi_source")
    if medical_relevance_score(primary) >= 0.8:
        reasons.append("high_medical_relevance")
    if score >= 0.75:
        reasons.append("high_importance")
    if not reasons:
        reasons.append("recent_medical_signal")
    return reasons


def build_story_record(
    story_id: str,
    items: list[dict[str, Any]],
    now: datetime,
    window_hours: int,
) -> dict[str, Any]:
    sorted_items = sorted(items, key=source_tier_sort_key)
    primary = choose_primary_story_item(sorted_items, now, window_hours)
    importance = calculate_item_importance(primary, now, window_hours, duplicate_count=len(items))
    score = importance["score"]
    category = story_category(score, primary, len(items))
    times = [ts for ts in (event_time(item) for item in sorted_items) if ts]
    source_refs = [story_item_link(item) for item in sorted_items]
    source_names = sorted({str(item.get("source") or item.get("site_name") or "") for item in sorted_items if item.get("source") or item.get("site_name")})
    title = primary.get("title_bilingual") or primary.get("title")
    url = primary.get("url")
    return {
        "story_id": story_id,
        "title": title,
        "url": url,
        "primary_url": url,
        "source": primary.get("source"),
        "source_name": primary.get("site_name"),
        "sources": source_refs,
        "source_count": len(source_refs),
        "source_names": source_names,
        "items": source_refs,
        "item_count": len(sorted_items),
        "duplicate_count": len(sorted_items),
        "score": score,
        "importance": score,
        "importance_score": score,
        "importance_label": importance_label(category),
        "importance_breakdown": importance["breakdown"],
        "category": category,
        "medical_category": primary.get("category"),
        "category_label": primary.get("category_label"),
        "source_tier": primary.get("source_tier"),
        "source_authority_score": primary.get("source_authority_score"),
        "is_official": primary.get("is_official"),
        "is_policy": primary.get("is_policy"),
        "recommendation_reason": primary.get("recommendation_reason"),
        "persona_scores": primary.get("persona_scores"),
        "topic_value": primary.get("topic_value"),
        "content_angles": primary.get("content_angles"),
        "reasons": story_reasons(primary, score, len(sorted_items)),
        "earliest_at": iso(min(times)) if times else None,
        "latest_at": iso(max(times)) if times else None,
        "primary_item": {
            "id": primary.get("id"),
            "title": title,
            "url": url,
            "source": primary.get("source"),
            "source_name": primary.get("site_name"),
            "category": primary.get("category"),
            "category_label": primary.get("category_label"),
            "source_tier": primary.get("source_tier"),
            "is_official": primary.get("is_official"),
            "is_policy": primary.get("is_policy"),
            "recommendation_reason": primary.get("recommendation_reason"),
            "persona_scores": primary.get("persona_scores"),
            "topic_value": primary.get("topic_value"),
            "content_angles": primary.get("content_angles"),
        },
    }


def merge_story_items(
    items: list[dict[str, Any]],
    now: datetime,
    window_hours: int,
    title_window_hours: int = 6,
    title_threshold: float = 0.86,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    group_titles: dict[str, str] = {}
    group_times: dict[str, datetime | None] = {}
    canonical_to_story: dict[str, str] = {}
    events: list[dict[str, Any]] = []

    ordered = sorted(items, key=lambda item: event_time(item) or datetime.min.replace(tzinfo=UTC))
    for item in ordered:
        item_id = str(item.get("id") or "")
        canonical_url = canonical_story_url(str(item.get("url") or ""))
        title = normalized_story_title(item)
        item_time = event_time(item)
        story_id: str | None = None
        reason = ""
        similarity = 0.0

        if canonical_url and canonical_url in canonical_to_story:
            story_id = canonical_to_story[canonical_url]
            reason = "canonical_url"
            similarity = 1.0
        elif title_is_mergeable(title):
            for candidate_id, candidate_title in group_titles.items():
                candidate_time = group_times.get(candidate_id)
                if item_time and candidate_time:
                    delta_hours = abs((item_time - candidate_time).total_seconds()) / 3600
                    if delta_hours > title_window_hours:
                        continue
                sim = title_similarity(title, candidate_title)
                if sim >= title_threshold and story_titles_can_merge(title, candidate_title):
                    story_id = candidate_id
                    reason = "title_similarity"
                    similarity = sim
                    break

        if story_id is None:
            story_id = story_id_for_item(item)
            groups[story_id] = []
            group_titles[story_id] = title
            group_times[story_id] = item_time
            if canonical_url:
                canonical_to_story[canonical_url] = story_id
        else:
            events.append(
                {
                    "story_id": story_id,
                    "item_id": item_id,
                    "merged_into": story_id,
                    "reason": reason,
                    "similarity": round(similarity, 4),
                }
            )
            if canonical_url:
                canonical_to_story[canonical_url] = story_id

        groups.setdefault(story_id, []).append(item)

    stories = [build_story_record(story_id, group_items, now, window_hours) for story_id, group_items in groups.items()]
    stories.sort(key=lambda story: (-float(story.get("score") or 0), str(story.get("latest_at") or ""), str(story.get("title") or "")))
    return stories, events


BRIEF_SCORE_GATE = 0.72


def story_passes_brief_gate(story: dict[str, Any]) -> bool:
    """宁缺毋滥: a story earns a brief slot via multi-source confirmation or a
    strong score. Quiet days produce a short (possibly empty) brief instead of
    a padded one."""
    try:
        sources = int(story.get("source_count") or 1)
    except Exception:
        sources = 1
    try:
        score = float(story.get("score") or 0)
    except Exception:
        score = 0.0
    return sources >= 2 or score >= BRIEF_SCORE_GATE


def select_diverse_stories(
    stories: list[dict[str, Any]],
    limit: int,
    same_source_penalty: float = 0.03,
) -> list[dict[str, Any]]:
    """Greedy top-N by score with a per-source decay so one prolific source
    cannot fill the brief, plus same-cluster suppression across the whole
    window: a story whose title near-duplicates an already picked one is
    skipped, so an event reposted hours apart (outside the merge window)
    still occupies only one slot."""
    candidates = sorted(stories, key=lambda story: (-float(story.get("score") or 0), str(story.get("title") or "")))
    picked: list[dict[str, Any]] = []
    picked_titles: list[tuple[str, set[str]]] = []
    picked_per_source: dict[str, int] = {}
    remaining = list(candidates)

    def near_duplicate_of_picked(story: dict[str, Any]) -> bool:
        title = normalized_story_title(story)
        if not title_is_mergeable(title):
            return False
        tokens = title_tokens(title)
        for other_title, other_tokens in picked_titles:
            if not tokens or not other_tokens:
                continue
            if len(tokens & other_tokens) / len(tokens | other_tokens) < 0.4:
                continue
            if title_similarity(title, other_title) >= 0.86 and story_titles_can_merge(title, other_title):
                return True
        return False

    while remaining and len(picked) < limit:
        best_idx = -1
        best_eff = float("-inf")
        for idx, story in enumerate(remaining):
            source = str(story.get("source") or story.get("source_name") or "")
            eff = float(story.get("score") or 0) - same_source_penalty * picked_per_source.get(source, 0)
            if eff > best_eff:
                best_eff = eff
                best_idx = idx
        if best_idx < 0:
            break
        chosen = remaining.pop(best_idx)
        if near_duplicate_of_picked(chosen):
            continue
        source = str(chosen.get("source") or chosen.get("source_name") or "")
        picked_per_source[source] = picked_per_source.get(source, 0) + 1
        picked.append(chosen)
        picked_titles.append((normalized_story_title(chosen), title_tokens(normalized_story_title(chosen))))
    return picked


def build_daily_brief_payload(
    stories: list[dict[str, Any]],
    generated_at: str,
    window_hours: int,
    max_items: int = 20,
) -> dict[str, Any]:
    gated = [story for story in stories if story_passes_brief_gate(story)]
    items = select_diverse_stories(gated, max_items)
    return {
        "generated_at": generated_at,
        "window_hours": window_hours,
        "total_items": len(items),
        "items": items,
    }


def build_stories_payload(
    stories: list[dict[str, Any]],
    generated_at: str,
    window_hours: int,
) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "window_hours": window_hours,
        "total_stories": len(stories),
        "stories": stories,
    }


def build_merge_log_payload(events: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "merge_strategy": "url_or_title_similarity_v0_6",
        "total_events": len(events),
        "events": events,
    }




def build_latest_payloads(latest_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split initial medical payload from bulky all-mode lists for lazy browser loading."""
    slim_payload = dict(latest_payload)
    all_payload = {
        "generated_at": latest_payload.get("generated_at"),
        "window_hours": latest_payload.get("window_hours"),
        "topic_filter": latest_payload.get("topic_filter"),
        "medical_relevance_threshold": latest_payload.get("medical_relevance_threshold"),
        "total_items_raw": latest_payload.get("total_items_raw"),
        "total_items_all_mode": latest_payload.get("total_items_all_mode"),
        "items_all": latest_payload.get("items_all", []),
        "items_all_raw": latest_payload.get("items_all_raw", []),
    }
    slim_payload.pop("items_all", None)
    slim_payload.pop("items_all_raw", None)
    slim_payload["all_mode_data_url"] = "data/latest-24h-all.json"
    slim_payload["stories_data_url"] = "data/stories-merged.json"
    return slim_payload, all_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate medical/health news updates from multiple sources")
    parser.add_argument("--output-dir", default="data", help="Directory for output JSON files")
    parser.add_argument("--window-hours", type=int, default=24, help="24h window size")
    parser.add_argument("--archive-days", type=int, default=21, help="Keep archive for N days")
    parser.add_argument("--translate-max-new", type=int, default=80, help="Max new EN->ZH title translations per run")
    parser.add_argument("--sources-config", default="config/sources.yml", help="Configured source registry YAML")
    parser.add_argument("--rss-opml", default="", help="Optional OPML file path to include RSS sources")
    parser.add_argument("--rss-max-feeds", type=int, default=0, help="Optional max OPML RSS feeds to fetch (0 means all)")
    args = parser.parse_args()

    now = utc_now()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    archive_path = output_dir / "archive.json"
    latest_path = output_dir / "latest-24h.json"
    latest_all_path = output_dir / "latest-24h-all.json"
    status_path = output_dir / "source-status.json"
    source_registry_path = output_dir / "source-registry.json"
    daily_brief_path = output_dir / "daily-brief.json"
    stories_merged_path = output_dir / "stories-merged.json"
    merge_log_path = output_dir / "merge-log.json"
    title_cache_path = output_dir / "title-zh-cache.json"

    archive = load_archive(archive_path)

    session = create_session()
    sources_config_path = Path(args.sources_config).expanduser()
    raw_items, statuses, configured_source_statuses = collect_all(
        session,
        now,
        sources_config=sources_config_path,
    )
    configured_feed_urls = {
        str(row.get("feed_url") or "")
        for row in configured_source_statuses
        if str(row.get("feed_url") or "").strip()
    }
    rss_feed_statuses: list[dict[str, Any]] = []
    agentmail_status: dict[str, Any] = {"enabled": False}
    x_api_status: dict[str, Any] = {"enabled": False}
    socialdata_status: dict[str, Any] = {"enabled": False}
    tikhub_status: dict[str, Any] = {"enabled": False}

    if args.rss_opml:
        opml_path = Path(args.rss_opml).expanduser()
        if opml_path.exists():
            rss_items, rss_summary_status, rss_feed_statuses = fetch_opml_rss(
                now,
                opml_path,
                max_feeds=max(0, int(args.rss_max_feeds)),
                configured_urls=configured_feed_urls,
            )
            raw_items.extend(rss_items)
            statuses.append(rss_summary_status)
        else:
            statuses.append(
                {
                    "site_id": "opmlrss",
                    "site_name": "OPML RSS",
                    "ok": False,
                    "item_count": 0,
                    "duration_ms": 0,
                    "error": f"OPML not found: {opml_path}",
                    "feed_count": 0,
                    "ok_feed_count": 0,
                    "failed_feed_count": 0,
                }
            )

    seen_this_run: set[str] = set()

    for raw in raw_items:
        title = raw.title.strip()
        url = normalize_url(raw.url)
        if not title or not url:
            continue
        if not url.startswith("http"):
            continue

        item_id = make_item_id(raw.site_id, raw.source, title, url)
        seen_this_run.add(item_id)

        existing = archive.get(item_id)
        if existing is None:
            archive[item_id] = {
                "id": item_id,
                "site_id": raw.site_id,
                "site_name": raw.site_name,
                "source": raw.source,
                "title": title,
                "url": url,
                "published_at": iso(raw.published_at),
                "first_seen_at": iso(now),
                "last_seen_at": iso(now),
            }
            apply_public_raw_meta(archive[item_id], raw)
        else:
            existing["site_id"] = raw.site_id
            existing["site_name"] = raw.site_name
            existing["source"] = raw.source
            existing["title"] = title
            existing["url"] = url
            if raw.published_at:
                # OPML RSS may fix previously wrong publish times; allow overwrite.
                if raw.site_id == "opmlrss" or not existing.get("published_at"):
                    existing["published_at"] = iso(raw.published_at)
            existing["last_seen_at"] = iso(now)
            apply_public_raw_meta(existing, raw)

    # Prune old archive
    keep_after = now - timedelta(days=args.archive_days)
    pruned: dict[str, dict[str, Any]] = {}
    for item_id, record in archive.items():
        ts = (
            parse_iso(record.get("last_seen_at"))
            or parse_iso(record.get("published_at"))
            or parse_iso(record.get("first_seen_at"))
            or now
        )
        if ts >= keep_after:
            pruned[item_id] = record
    archive = pruned

    # 24h view
    window_start = now - timedelta(hours=args.window_hours)
    latest_items_all: list[dict[str, Any]] = []
    for record in archive.values():
        ts = event_time(record)
        if not ts:
            continue
        if ts >= window_start:
            normalized = dict(record)
            normalized["title"] = maybe_fix_mojibake(str(normalized.get("title") or ""))
            normalized["source"] = maybe_fix_mojibake(normalize_source_for_display(
                str(normalized.get("site_id") or ""),
                str(normalized.get("source") or ""),
                str(normalized.get("url") or ""),
            ))
            normalized = add_medical_intelligence_fields(normalized)
            latest_items_all.append(normalized)

    latest_items_all.sort(key=lambda x: event_time(x) or datetime.min.replace(tzinfo=UTC), reverse=True)
    latest_items = [record for record in latest_items_all if record.get("medical_is_related", is_medical_related_record(record))]
    title_cache = load_title_zh_cache(title_cache_path)
    latest_items, latest_items_all, title_cache = add_bilingual_fields(
        latest_items,
        latest_items_all,
        session,
        title_cache,
        max_new_translations=max(0, args.translate_max_new),
    )
    latest_items_medical_dedup = suppress_near_duplicate_items(dedupe_items_by_title_url(latest_items, random_pick=False))
    latest_items_all_dedup = dedupe_items_by_title_url(latest_items_all, random_pick=True)
    stories, merge_events = merge_story_items(latest_items_medical_dedup, now=now, window_hours=args.window_hours)
    generated_at = iso(now)
    daily_brief_payload = build_daily_brief_payload(stories, generated_at=generated_at, window_hours=args.window_hours)
    stories_merged_payload = build_stories_payload(stories, generated_at=generated_at, window_hours=args.window_hours)
    merge_log_payload = build_merge_log_payload(merge_events, generated_at=generated_at)

    # site stats
    site_stat: dict[str, dict[str, Any]] = {}
    raw_count_by_site: dict[str, int] = {}
    for record in latest_items_all:
        sid = record["site_id"]
        raw_count_by_site[sid] = raw_count_by_site.get(sid, 0) + 1

    site_name_by_id: dict[str, str] = {}
    for record in latest_items_all:
        site_name_by_id[record["site_id"]] = record["site_name"]
    for s in statuses:
        sid = s["site_id"]
        if sid not in site_name_by_id:
            site_name_by_id[sid] = s.get("site_name") or sid

    for record in latest_items_medical_dedup:
        sid = record["site_id"]
        if sid not in site_stat:
            site_stat[sid] = {
                "site_id": sid,
                "site_name": record["site_name"],
                "count": 0,
                "raw_count": raw_count_by_site.get(sid, 0),
            }
        site_stat[sid]["count"] += 1

    for sid, site_name in site_name_by_id.items():
        if sid in site_stat:
            continue
        site_stat[sid] = {
            "site_id": sid,
            "site_name": site_name,
            "count": 0,
            "raw_count": raw_count_by_site.get(sid, 0),
        }

    latest_payload = {
        "generated_at": generated_at,
        "window_hours": args.window_hours,
        "total_items": len(latest_items_medical_dedup),
        "total_items_ai_raw": len(latest_items),
        "total_items_raw": len(latest_items_all),
        "total_items_all_mode": len(latest_items_all_dedup),
        "topic_filter": "medical_relevance_scoring_v0_1",
        "medical_relevance_threshold": 0.65,
        "archive_total": len(archive),
        "site_count": len(site_stat),
        "source_count": len({f"{i['site_id']}::{i['source']}" for i in latest_items_medical_dedup}),
        "site_stats": sorted(site_stat.values(), key=lambda x: x["count"], reverse=True),
        "items": latest_items_medical_dedup,
        "items_ai": latest_items_medical_dedup,
        "items_all_raw": latest_items_all,
        "items_all": latest_items_all_dedup,
    }

    archive_payload = {
        "generated_at": generated_at,
        "total_items": len(archive),
        "items": sorted(
            archive.values(),
            key=lambda x: parse_iso(x.get("last_seen_at")) or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        ),
    }

    status_payload = {
        "generated_at": generated_at,
        "sites": statuses,
        "configured_sources": configured_source_statuses,
        "successful_sites": sum(1 for s in statuses if s["ok"]),
        "failed_sites": [s["site_id"] for s in statuses if not s["ok"]],
        "zero_item_sites": [
            s["site_id"]
            for s in statuses
            if s.get("ok")
            and int(s.get("item_count") or 0) == 0
            and not s.get("skipped")
        ],
        "empty_advanced_sources": [],
        "fetched_raw_items": len(raw_items),
        "items_before_topic_filter": len(latest_items_all),
        "items_in_24h": len(latest_items_medical_dedup),
        "rss_opml": {
            "enabled": bool(args.rss_opml),
            "path": "configured" if args.rss_opml else None,
            "feed_total": len(rss_feed_statuses),
            "effective_feed_total": sum(1 for s in rss_feed_statuses if not s.get("skipped")),
            "ok_feeds": sum(1 for s in rss_feed_statuses if s["ok"] and not s.get("skipped")),
            "failed_feeds": [s.get("effective_feed_url") or s["feed_url"] for s in rss_feed_statuses if not s["ok"]],
            "zero_item_feeds": [
                s.get("effective_feed_url") or s["feed_url"]
                for s in rss_feed_statuses
                if s["ok"] and not s.get("skipped") and int(s.get("item_count") or 0) == 0
            ],
            "skipped_feeds": [
                {"feed_url": s["feed_url"], "reason": s.get("skip_reason")}
                for s in rss_feed_statuses
                if s.get("skipped")
            ],
            "replaced_feeds": [
                {"from": s["feed_url"], "to": s.get("effective_feed_url")}
                for s in rss_feed_statuses
                if s.get("replaced") and s.get("effective_feed_url")
            ],
            "feeds": rss_feed_statuses,
        },
    }

    source_config_result = load_config("sources", sources_config_path)
    write_source_registry(
        source_registry_path,
        source_config_result.data,
        status_payload,
        archive_payload,
        generated_at=generated_at,
    )

    latest_payload, latest_all_payload = build_latest_payloads(latest_payload)

    latest_path.write_text(json.dumps(sanitize_public_payload(latest_payload), ensure_ascii=False, indent=2), encoding="utf-8")
    latest_all_path.write_text(json.dumps(sanitize_public_payload(latest_all_payload), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    daily_brief_path.write_text(
        json.dumps(sanitize_public_payload(daily_brief_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    stories_merged_path.write_text(
        json.dumps(sanitize_public_payload(stories_merged_payload), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    merge_log_path.write_text(
        json.dumps(sanitize_public_payload(merge_log_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    archive_path.write_text(
        json.dumps(sanitize_public_payload(archive_payload), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    status_path.write_text(json.dumps(sanitize_public_payload(status_payload), ensure_ascii=False, indent=2), encoding="utf-8")
    title_cache_path.write_text(json.dumps(sanitize_public_payload(title_cache), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote: {latest_path} ({len(latest_items)} items)")
    print(f"Wrote: {latest_all_path} ({len(latest_items_all_dedup)} all-mode items)")
    print(f"Wrote: {daily_brief_path} ({daily_brief_payload.get('total_items', 0)} brief items)")
    print(f"Wrote: {stories_merged_path} ({stories_merged_payload.get('total_stories', 0)} stories)")
    print(f"Wrote: {merge_log_path} ({len(merge_events)} merge events)")
    print(f"Wrote: {archive_path} ({len(archive)} items)")
    print(f"Wrote: {status_path}")
    print(f"Wrote: {title_cache_path} ({len(title_cache)} entries)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
