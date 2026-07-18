#!/usr/bin/env python3
"""Safely probe public medical-news sources without storing article bodies."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import ipaddress
import json
from pathlib import Path
import socket
import time
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from dateutil import parser as date_parser
import requests

try:
    from scripts.config_loader import load_config
    from scripts.medical_relevance import classify_medical_category, score_medical_relevance
except ModuleNotFoundError:  # pragma: no cover - direct `python scripts/source_probe.py`
    from config_loader import load_config
    from medical_relevance import classify_medical_category, score_medical_relevance


UTC = timezone.utc
Resolver = Callable[..., list[Any]]
REDIRECT_CODES = {301, 302, 303, 307, 308}
FEED_CONTENT_TYPES = {
    "application/atom+xml",
    "application/feed+json",
    "application/rss+xml",
    "application/xml",
    "text/xml",
}
PROBE_USER_AGENT = "MedicalNewsRadar-SourceProbe/1.0 (+https://github.com/xavier9802/medical-news-radar)"


class UnsafeUrlError(ValueError):
    """Raised when a URL can reach a non-public network target."""


class UnsafeRedirectError(UnsafeUrlError):
    """Raised when a redirect changes the request to an unsafe target."""


class ResponseTooLargeError(ValueError):
    """Raised when a response exceeds the configured streamed-body limit."""


@dataclass(frozen=True)
class ProbeLimits:
    connect_timeout_seconds: int = 5
    read_timeout_seconds: int = 15
    max_redirects: int = 5
    max_body_bytes: int = 2 * 1024 * 1024


@dataclass(frozen=True)
class FetchResult:
    input_url: str
    resolved_url: str
    status_code: int
    headers: dict[str, str]
    body: bytes
    elapsed_ms: int
    redirect_count: int


def utc_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _redact_url(url: str) -> str:
    """Keep only public routing information; queries may contain API secrets."""
    try:
        parts = urlsplit(str(url or ""))
    except ValueError:
        return ""
    if not parts.scheme or not parts.netloc:
        return ""
    host = parts.hostname or ""
    if not host:
        return ""
    host_rendered = f"[{host}]" if ":" in host and not host.startswith("[") else host
    try:
        port = parts.port
    except ValueError:
        port = None
    if port and not ((parts.scheme.lower() == "https" and port == 443) or (parts.scheme.lower() == "http" and port == 80)):
        host_rendered = f"{host_rendered}:{port}"
    return urlunsplit((parts.scheme.lower(), host_rendered.lower(), parts.path or "/", "", ""))


def _resolver_addresses(host: str, port: int, resolver: Resolver) -> list[str]:
    try:
        records = resolver(host, port, type=socket.SOCK_STREAM)
    except TypeError:
        records = resolver(host, port)
    except OSError as exc:
        raise UnsafeUrlError("host_unresolved") from exc
    addresses: list[str] = []
    for record in records or []:
        try:
            address = str(record[4][0]).split("%", 1)[0]
        except (IndexError, TypeError):
            continue
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise UnsafeUrlError("host_unresolved")
    return addresses


def validate_public_url(url: str, resolver: Resolver = socket.getaddrinfo) -> str:
    """Normalize a URL and reject any non-global DNS answer or literal IP."""
    text = str(url or "").strip()
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError as exc:
        raise UnsafeUrlError("invalid_url") from exc
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise UnsafeUrlError("unsupported_scheme")
    if parts.username is not None or parts.password is not None:
        raise UnsafeUrlError("credentials_forbidden")
    host = str(parts.hostname or "").strip().rstrip(".").lower()
    if not host or any(char.isspace() for char in host):
        raise UnsafeUrlError("invalid_host")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan", ".home")):
        raise UnsafeUrlError("local_host_forbidden")
    if port is None:
        port = 443 if scheme == "https" else 80

    try:
        literal = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        try:
            ascii_host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise UnsafeUrlError("invalid_host") from exc
        addresses = _resolver_addresses(ascii_host, port, resolver)
    else:
        ascii_host = host
        addresses = [str(literal)]

    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as exc:
            raise UnsafeUrlError("invalid_dns_answer") from exc
        if not parsed.is_global:
            raise UnsafeUrlError("non_public_address")

    rendered_host = f"[{ascii_host}]" if ":" in ascii_host else ascii_host
    if not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        rendered_host = f"{rendered_host}:{port}"
    return urlunsplit((scheme, rendered_host, parts.path or "/", parts.query, ""))


def _configure_session(session: Any) -> None:
    if hasattr(session, "cookies") and hasattr(session.cookies, "clear"):
        session.cookies.clear()
    if hasattr(session, "trust_env"):
        session.trust_env = False
    if hasattr(session, "headers") and hasattr(session.headers, "update"):
        session.headers.update({"User-Agent": PROBE_USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/html;q=0.9, */*;q=0.5"})


def _header(headers: dict[str, Any], name: str) -> str:
    target = name.casefold()
    for key, value in headers.items():
        if str(key).casefold() == target:
            return str(value)
    return ""


def _read_limited_body(response: Any, max_bytes: int) -> bytes:
    content_length = _header(dict(response.headers or {}), "content-length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = 0
        if declared_length > max_bytes:
            raise ResponseTooLargeError("response_too_large")
    body = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        body.extend(chunk)
        if len(body) > max_bytes:
            raise ResponseTooLargeError("response_too_large")
    return bytes(body)


def fetch_url(
    url: str,
    session: Any | None = None,
    resolver: Resolver = socket.getaddrinfo,
    limits: ProbeLimits | None = None,
) -> FetchResult:
    """Fetch a bounded public URL while manually validating every redirect."""
    effective_limits = limits or ProbeLimits()
    client = session or requests.Session()
    _configure_session(client)
    input_url = validate_public_url(url, resolver=resolver)
    current_url = input_url
    started = time.perf_counter()
    redirect_count = 0

    while True:
        response = client.get(
            current_url,
            allow_redirects=False,
            stream=True,
            timeout=(effective_limits.connect_timeout_seconds, effective_limits.read_timeout_seconds),
            headers={"User-Agent": PROBE_USER_AGENT},
        )
        try:
            status_code = int(response.status_code)
            response_headers = {str(key): str(value) for key, value in dict(response.headers or {}).items()}
            if status_code in REDIRECT_CODES:
                location = _header(response_headers, "location")
                if not location:
                    body = _read_limited_body(response, effective_limits.max_body_bytes)
                    break
                if redirect_count >= effective_limits.max_redirects:
                    raise ValueError("too_many_redirects")
                candidate = urljoin(current_url, location)
                try:
                    current_url = validate_public_url(candidate, resolver=resolver)
                except UnsafeUrlError as exc:
                    raise UnsafeRedirectError("unsafe_redirect") from exc
                redirect_count += 1
                continue
            body = _read_limited_body(response, effective_limits.max_body_bytes)
            break
        finally:
            if hasattr(response, "close"):
                response.close()

    return FetchResult(
        input_url=input_url,
        resolved_url=current_url,
        status_code=status_code,
        headers=response_headers,
        body=body,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        redirect_count=redirect_count,
    )


def _local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1].lower()


def _child_text(node: ET.Element, names: set[str]) -> str:
    for child in node.iter():
        if _local_name(child.tag) in names and str(child.text or "").strip():
            return str(child.text or "").strip()
    return ""


def _entry_link(node: ET.Element) -> str:
    for child in node.iter():
        if _local_name(child.tag) != "link":
            continue
        href = str(child.attrib.get("href") or "").strip()
        text = str(child.text or "").strip()
        if href or text:
            return href or text
    return ""


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = date_parser.parse(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _base_result(input_url: str, resolved_url: str, status_code: int, headers: dict[str, Any], elapsed_ms: int, name: str) -> dict[str, Any]:
    return {
        "checked_at": utc_iso(),
        "name": str(name or ""),
        "input_url": _redact_url(input_url),
        "resolved_url": _redact_url(resolved_url),
        "reachable": 200 <= int(status_code) < 500,
        "status_code": int(status_code),
        "content_type": _header(headers, "content-type").split(";", 1)[0].strip().lower(),
        "response_ms": max(0, int(elapsed_ms)),
        "detected_type": "unknown",
        "recommended_strategy": "skip",
        "feed_valid": False,
        "item_count": 0,
        "latest_item_at": None,
        "has_title": False,
        "has_timestamp": False,
        "is_stale": None,
        "requires_login": False,
        "blocked": False,
        "medical_relevance": 0.0,
        "recommended_category": "company_market",
        "recommended_tier": "c",
        "feed_candidates": [],
        "warnings": [],
        "errors": [],
    }


def analyze_response(
    input_url: str,
    resolved_url: str,
    status_code: int,
    headers: dict[str, Any],
    body: bytes,
    elapsed_ms: int,
    name: str = "",
) -> dict[str, Any]:
    """Analyze bounded response bytes and emit metadata only."""
    result = _base_result(input_url, resolved_url, status_code, headers, elapsed_ms, name)
    sample = body[:512 * 1024].decode("utf-8", errors="replace")
    lowered = sample.casefold()
    result["requires_login"] = any(marker in lowered for marker in ("type=\"password\"", "type='password'", "sign in", "log in", "登录"))
    marker_blocked = any(marker in lowered for marker in ("captcha", "验证码", "access denied", "forbidden", "robot check", "too many requests"))
    result["blocked"] = int(status_code) in {401, 403, 429, 503} or marker_blocked
    if result["requires_login"]:
        result["warnings"].append("requires_login")
    if result["blocked"]:
        result["warnings"].append("access_blocked")
    if int(status_code) >= 400:
        result["errors"].append(f"http_status_{int(status_code)}")

    titles: list[str] = []
    dates: list[datetime] = []
    content_type = result["content_type"]
    looks_xml = content_type in FEED_CONTENT_TYPES or lowered.lstrip().startswith(("<?xml", "<rss", "<feed", "<rdf"))
    root: ET.Element | None = None
    if looks_xml:
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            result["errors"].append("invalid_xml")

    if root is not None:
        root_name = _local_name(root.tag)
        if root_name in {"rss", "rdf"}:
            result["detected_type"] = "rss"
            entries = [node for node in root.iter() if _local_name(node.tag) == "item"]
        elif root_name == "feed":
            result["detected_type"] = "atom"
            entries = [node for node in root.iter() if _local_name(node.tag) == "entry"]
        else:
            entries = []
        if result["detected_type"] in {"rss", "atom"}:
            result["feed_valid"] = True
            result["recommended_strategy"] = "rss"
            for entry in entries:
                title = _child_text(entry, {"title"})
                published = _child_text(entry, {"pubdate", "published", "updated", "date"})
                if title:
                    titles.append(title)
                parsed_date = _parse_date(published)
                if parsed_date:
                    dates.append(parsed_date)
                _entry_link(entry)  # Parsed deliberately, but item URLs/bodies are not emitted.
            result["item_count"] = len(entries)
            feed_title = _child_text(root, {"title"})
            result["has_title"] = bool(feed_title or titles)
            result["has_timestamp"] = bool(dates)

    if result["detected_type"] == "unknown" and ("html" in content_type or "<html" in lowered):
        result["detected_type"] = "html"
        soup = BeautifulSoup(sample, "html.parser")
        result["has_title"] = bool(soup.title and soup.title.get_text(" ", strip=True))
        candidates: list[str] = []
        for link in soup.find_all("link"):
            rel = {str(value).casefold() for value in (link.get("rel") or [])}
            media_type = str(link.get("type") or "").split(";", 1)[0].casefold()
            href = str(link.get("href") or "").strip()
            if "alternate" not in rel or media_type not in FEED_CONTENT_TYPES or not href:
                continue
            candidate = urljoin(resolved_url, href)
            if urlsplit(candidate).scheme in {"http", "https"} and candidate not in candidates:
                candidates.append(candidate)
        result["feed_candidates"] = candidates[:10]
        result["recommended_strategy"] = "rss" if candidates else "html_list"

    if result["detected_type"] == "unknown" and ("json" in content_type or lowered.lstrip().startswith(("{", "["))):
        try:
            payload = json.loads(sample)
        except json.JSONDecodeError:
            result["errors"].append("invalid_json")
        else:
            result["detected_type"] = "json"
            result["recommended_strategy"] = "json"
            result["item_count"] = len(payload) if isinstance(payload, list) else 1
            result["has_title"] = isinstance(payload, dict) and bool(payload.get("title"))

    if dates:
        latest = max(dates)
        result["latest_item_at"] = latest.isoformat().replace("+00:00", "Z")
        result["is_stale"] = latest < datetime.now(UTC) - timedelta(days=90)
        if result["is_stale"]:
            result["warnings"].append("stale_feed")

    scoring_text = " ".join(titles[:20]) or str(name or "")
    if scoring_text:
        relevance = score_medical_relevance({"title": scoring_text, "summary": str(name or "")})
        category = classify_medical_category(scoring_text, str(name or ""))
        result["medical_relevance"] = round(float(relevance.get("score") or 0), 4)
        result["recommended_category"] = str(category.get("category") or "company_market")
    if result["feed_valid"] and not result["blocked"] and not result["requires_login"]:
        result["recommended_tier"] = "a"
    elif result["reachable"] and not result["blocked"]:
        result["recommended_tier"] = "b"
    if result["detected_type"] == "unknown" and not result["errors"]:
        result["warnings"].append("unsupported_content")
    return result


def _failed_result(url: str, name: str, error_code: str) -> dict[str, Any]:
    result = _base_result(url, url, 0, {}, 0, name)
    result["reachable"] = False
    result["status_code"] = None
    result["errors"] = [error_code]
    return result


def probe_url(
    url: str,
    name: str = "",
    *,
    session: Any | None = None,
    resolver: Resolver = socket.getaddrinfo,
    limits: ProbeLimits | None = None,
) -> dict[str, Any]:
    try:
        fetched = fetch_url(url, session=session, resolver=resolver, limits=limits)
    except UnsafeRedirectError:
        return _failed_result(url, name, "unsafe_redirect")
    except UnsafeUrlError:
        return _failed_result(url, name, "unsafe_url")
    except requests.Timeout:
        return _failed_result(url, name, "timeout")
    except ResponseTooLargeError:
        return _failed_result(url, name, "response_too_large")
    except requests.RequestException:
        return _failed_result(url, name, "network_error")
    except (OSError, ValueError):
        return _failed_result(url, name, "probe_failed")
    result = analyze_response(
        fetched.input_url,
        fetched.resolved_url,
        fetched.status_code,
        fetched.headers,
        fetched.body,
        fetched.elapsed_ms,
        name=name,
    )
    result["redirect_count"] = fetched.redirect_count
    return result


def probe_config(
    config: str | Path,
    *,
    session: Any | None = None,
    resolver: Resolver = socket.getaddrinfo,
    limits: ProbeLimits | None = None,
) -> list[dict[str, Any]]:
    source_result = load_config("sources", Path(config), strict=True)
    results: list[dict[str, Any]] = []
    for source in source_result.data.get("sources", []):
        if not source.get("enabled", True):
            continue
        url = str(source.get("feed_url") or source.get("homepage_url") or "").strip()
        if not url:
            continue
        result = probe_url(
            url,
            str(source.get("name") or source.get("id") or ""),
            session=session,
            resolver=resolver,
            limits=limits,
        )
        result["source_id"] = str(source.get("id") or "")
        results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely inspect a public medical news source")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--url", help="Public HTTP(S) source or feed URL")
    target.add_argument("--config", help="Probe enabled entries from a sources.yml file")
    parser.add_argument("--name", default="", help="Optional source name")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    args = parser.parse_args()

    payload: dict[str, Any] | list[dict[str, Any]]
    if args.config:
        payload = probe_config(args.config)
    else:
        payload = probe_url(str(args.url or ""), args.name)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered)
    if isinstance(payload, dict) and payload.get("errors"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
