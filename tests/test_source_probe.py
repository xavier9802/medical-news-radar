from __future__ import annotations

import json
import socket

import pytest
import requests

from scripts.source_probe import (
    ProbeLimits,
    UnsafeUrlError,
    analyze_response,
    fetch_url,
    probe_url,
    validate_public_url,
)


def public_resolver(_host, port, *_args, **_kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", port))]


def mixed_resolver(_host, port, *_args, **_kwargs):
    return [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", port)),
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.8", port)),
    ]


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/feed",
        "http://localhost/feed",
        "http://127.0.0.1/feed",
        "http://10.2.3.4/feed",
        "http://172.16.0.1/feed",
        "http://192.168.1.1/feed",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/feed",
        "http://[fc00::1]/feed",
        "https://user:pass@example.com/feed",
    ],
)
def test_rejects_non_public_targets(url):
    with pytest.raises(UnsafeUrlError):
        validate_public_url(url)


def test_accepts_public_http_url_with_injected_resolver():
    assert validate_public_url("HTTPS://example.com:443/feed", resolver=public_resolver) == "https://example.com/feed"


def test_rejects_hostname_when_any_resolved_address_is_private():
    with pytest.raises(UnsafeUrlError):
        validate_public_url("https://example.com/feed", resolver=mixed_resolver)


def test_analyzes_valid_rss_without_network():
    body = b"<?xml version='1.0'?><rss version='2.0'><channel><title>Medical</title><item><title>Medical AI diagnosis</title><link>https://example.com/a</link><pubDate>Sat, 18 Jul 2026 10:00:00 GMT</pubDate></item></channel></rss>"

    result = analyze_response(
        "https://example.com/feed",
        "https://example.com/feed",
        200,
        {"Content-Type": "application/rss+xml"},
        body,
        12,
    )

    assert result["detected_type"] == "rss"
    assert result["recommended_strategy"] == "rss"
    assert result["feed_valid"] is True
    assert result["item_count"] == 1
    assert result["has_title"] is True
    assert result["has_timestamp"] is True
    assert result["recommended_category"] == "medical_ai"
    assert 0 <= result["medical_relevance"] <= 1
    assert "body" not in result


def test_invalid_xml_is_reported_not_raised():
    result = analyze_response(
        "https://example.com/feed",
        "https://example.com/feed",
        200,
        {"Content-Type": "application/xml"},
        b"<rss>",
        12,
    )

    assert result["feed_valid"] is False
    assert result["errors"]


def test_html_login_and_feed_discovery_are_structured():
    body = b"""<html><head><title>Sign in</title>
    <link rel="alternate" type="application/atom+xml" href="/atom.xml"></head>
    <body><form><input type="password"></form></body></html>"""

    result = analyze_response(
        "https://example.com/",
        "https://example.com/",
        200,
        {"content-type": "text/html"},
        body,
        7,
    )

    assert result["detected_type"] == "html"
    assert result["requires_login"] is True
    assert result["feed_candidates"] == ["https://example.com/atom.xml"]
    assert result["recommended_strategy"] == "rss"


class FakeResponse:
    def __init__(self, *, status=200, headers=None, body=b""):
        self.status_code = status
        self.headers = headers or {}
        self._body = body

    def iter_content(self, chunk_size=65536):
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start : start + chunk_size]

    def close(self):
        return None


class FakeSession:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.responses.pop(0)


def test_redirect_target_is_validated_before_second_request():
    session = FakeSession(
        responses=[FakeResponse(status=302, headers={"Location": "http://127.0.0.1/private"})]
    )

    result = probe_url("https://example.com/feed", session=session, resolver=public_resolver)

    assert result["reachable"] is False
    assert result["errors"] == ["unsafe_redirect"]
    assert len(session.calls) == 1
    assert session.calls[0][1]["allow_redirects"] is False


def test_response_body_limit_is_enforced():
    session = FakeSession(responses=[FakeResponse(body=b"x" * 20)])

    with pytest.raises(ValueError, match="response_too_large"):
        fetch_url(
            "https://example.com/feed",
            session=session,
            resolver=public_resolver,
            limits=ProbeLimits(max_body_bytes=10),
        )


def test_declared_response_body_limit_is_enforced_before_streaming():
    session = FakeSession(responses=[FakeResponse(headers={"Content-Length": "20"}, body=b"x")])

    with pytest.raises(ValueError, match="response_too_large"):
        fetch_url(
            "https://example.com/feed",
            session=session,
            resolver=public_resolver,
            limits=ProbeLimits(max_body_bytes=10),
        )


def test_timeout_becomes_structured_error_without_secret_text():
    session = FakeSession(error=requests.Timeout("secret query value"))

    result = probe_url(
        "https://example.com/feed?token=secret-query-value",
        session=session,
        resolver=public_resolver,
    )

    rendered = json.dumps(result)
    assert result["reachable"] is False
    assert result["errors"] == ["timeout"]
    assert "secret query value" not in rendered
    assert "secret-query-value" not in rendered
