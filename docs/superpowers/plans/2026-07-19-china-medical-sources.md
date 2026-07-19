# China Medical Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 接入 9 个有真实列表发布日期的国内医疗信源，并补齐 8 个受限 HTML profile 和一个固定医学界 JSON 适配器。

**Architecture:** `config_loader.py` 只保留登记 profile 和公共域名；`html_list_sources.py`、`yxj_source.py` 承担纯解析；`update_news.py` 承担受限请求、过滤、限流、`RawItem` 转换和逐源失败隔离。所有解析测试只使用最小离线 fixture。

**Tech Stack:** Python 3.11+、requests 2.32.3、BeautifulSoup 4.12.3、python-dateutil 2.9、PyYAML 6.0.2、pytest、GitHub Actions、GitHub Pages。

## Global Constraints

- 只采列表标题、链接、真实发布日期和列表已有短摘要；不抓详情页或正文。
- 不执行 JavaScript，不发送 Cookie，不登录，不绕过 WAF、验证码或付费墙。
- 不用采集时间、图片路径或文章 ID 推断发布日期；无有效日期条目必须丢弃。
- HTML 响应最多 2,000,000 bytes，最多扫描 100 个候选节点，输出受 `max_items` 限制。
- 最终列表地址和文章链接仅允许 HTTP(S)，主机必须在 `allowed_hosts`。
- 只有 S 级政府来源可设置 `is_official: true`；同事件继续优先 S/A 来源。
- 零条有效结果以 `no_valid_items` 记为单源失败，不终止其他来源。
- 单元测试不得访问真实网络；不新增运行时依赖或 Secret。
- 通过 Draft PR 交付，不直接推送 `main`。

## File Map

| 文件 | 职责 |
| --- | --- |
| `scripts/config_loader.py` | 校验 `parser_profile` 与 `allowed_hosts` |
| `scripts/html_list_sources.py` | 8 个 HTML profile 与纯解析 |
| `scripts/yxj_source.py` | 医学界固定 JSON 字段解析 |
| `scripts/update_news.py` | 请求、策略分派、过滤限流、RawItem 与状态 |
| `tests/fixtures/html_sources/*.html` | 8 个最小 DOM fixture |
| `tests/fixtures/yxj_home.json` | 医学界最小 JSON fixture |
| `tests/test_html_list_sources.py` | HTML 解析与安全边界 |
| `tests/test_yxj_source.py` | JSON 字段与异常结构 |
| `tests/test_config_loader.py` | 配置字段与 9 来源契约 |
| `tests/test_configured_collection.py` | 集成、限流和逐源失败 |
| `config/sources.yml` | 9 个来源及过滤器 |
| `README.md`、`docs/*.md` | 采集边界、schema 与覆盖矩阵 |

---

### Task 1: Preserve restricted adapter configuration

**Files:**
- Modify: `scripts/config_loader.py:300-335`
- Modify: `scripts/update_news.py:198-245`
- Test: `tests/test_config_loader.py`

**Interfaces:**
- Consumes: `_validate_source_row(row, index)`、`configured_feed_groups(config_path)`。
- Produces: `fetch.parser_profile: str`、`fetch.allowed_hosts: list[str]`，以及 feed 中同名字段。

- [ ] **Step 1: Write the failing tests**

```python
def test_source_config_preserves_restricted_adapter_fields(tmp_path: Path):
    path = tmp_path / "sources.yml"
    path.write_text(
        "sources:\n  - id: html-source\n    name: HTML source\n"
        "    homepage_url: https://example.com/news\n    feed_url: https://example.com/news\n    type: static_page\n"
        "    fetch:\n      strategy: html_list\n      parser_profile: hospital_ceo\n"
        "      allowed_hosts: [EXAMPLE.com, news.example.com, EXAMPLE.com]\n",
        encoding="utf-8",
    )
    source = load_config("sources", path).data["sources"][0]
    feed = configured_feed_groups(path)[0]["medical_media"][0]
    assert source["fetch"]["parser_profile"] == "hospital_ceo"
    assert source["fetch"]["allowed_hosts"] == ["example.com", "news.example.com"]
    assert feed["parser_profile"] == "hospital_ceo"
    assert feed["allowed_hosts"] == ["example.com", "news.example.com"]


def test_source_config_drops_invalid_host_entries(tmp_path: Path):
    path = tmp_path / "sources.yml"
    path.write_text(
        "sources:\n  - id: bad-hosts\n    name: Bad hosts\n"
        "    homepage_url: https://example.com/\n    type: static_page\n"
        "    fetch: {strategy: html_list, parser_profile: hospital_ceo, allowed_hosts: ['https://example.com', '127.0.0.1', good.example]}\n",
        encoding="utf-8",
    )
    source = load_config("sources", path).data["sources"][0]
    assert source["fetch"]["allowed_hosts"] == ["good.example"]
```

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_config_loader.py::test_source_config_preserves_restricted_adapter_fields tests\test_config_loader.py::test_source_config_drops_invalid_host_entries -q`

Expected: FAIL because both fields are currently discarded.

- [ ] **Step 3: Implement the validated fields**

Add `import ipaddress` and `import re` beside the standard-library imports, then add beside existing scalar helpers:

```python
HOST_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _safe_public_hosts(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    hosts: list[str] = []
    for raw in value:
        host = str(raw or "").strip().lower().rstrip(".")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            continue
        if HOST_RE.fullmatch(host) and host not in hosts:
            hosts.append(host)
    return hosts
```

Add inside `_validate_source_row`'s `fetch` mapping:

```python
"parser_profile": str(fetch.get("parser_profile") or "").strip().lower(),
"allowed_hosts": _safe_public_hosts(fetch.get("allowed_hosts")),
```

Add to `configured_feed_groups`'s feed mapping:

```python
"parser_profile": str(fetch.get("parser_profile") or ""),
"allowed_hosts": list(fetch.get("allowed_hosts") or []),
```

- [ ] **Step 4: Verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_config_loader.py -q`

Expected: all loader tests PASS.

- [ ] **Step 5: Commit**

Run: `git add scripts/config_loader.py scripts/update_news.py tests/test_config_loader.py`

Run: `git commit -m "feat: preserve restricted source adapter config"`

---

### Task 2: Add pure HTML list profiles and parser

**Files:**
- Create: `scripts/html_list_sources.py`
- Create: `tests/test_html_list_sources.py`
- Create: `tests/fixtures/html_sources/{nhsa,chs,cnmia,chima,kanyijie,hospital_ceo,mdweekly,bioon}.html`

**Interfaces:**
- Produces: `HTML_LIST_PROFILES: dict[str, HtmlListProfile]`。
- Produces: `parse_html_list_items(html: str, *, base_url: str, profile_id: str, allowed_hosts: Sequence[str], now: datetime) -> list[ParsedListItem]`。
- Produces: `ParsedListItem(title: str, url: str, published_at: datetime, summary: str)`。

- [ ] **Step 1: Create exact minimal fixtures**

Use one fictional record in each file:

```html
<!-- nhsa.html -->
<script type="text/xml"><datastore><record><![CDATA[<li><span>1</span><span><a href="/art/2026/7/17/art_104_1.html" title="医保支持基层医疗服务通知">医保支持基层医疗服务通知</a></span><span>医保办函〔2026〕1号</span><span>2026-07-17</span></li>]]></record></datastore></script>
<!-- chs.html -->
<li class="catlist_li"><span class="f_r">2026-07-16</span><a href="/news/show/501/" title="数智赋能基层医防融合">数智赋能基层医防融合</a></li>
<!-- cnmia.html -->
<div class="List"><div class="Block"><div class="Title"><a href="/DynamicDetail_demo.html" title="社会办医高质量发展实践">社会办医高质量发展实践</a></div><div class="Text">民营医院运营实践摘要</div><div class="Time">发布时间：2026-07-15</div></div></div>
<!-- chima.html -->
<ul class="article_xw_l"><li><span class="span_date_left"><b>14</b> 2026.07</span><div class="right_xw"><a class="title_type" href="/Html/News/Articles/18000.html" title="医院AI数据治理周报">医院AI数据治理周报</a><p>医院信息化摘要</p></div></li></ul>
<!-- kanyijie.html -->
<div class="des"><a class="h2" href="/details?id=2400" title="社会办医院引入基层AI服务">社会办医院引入基层AI服务</a><p class="sub">社会办医摘要</p><span class="time">2026-07-14</span></div>
<!-- hospital_ceo.html -->
<div class="paging"><div class="zlist01"><a class="tit" href="/post/6000.html">医院数智化运营新实践</a><span class="time">2026年07月13日 16:58</span><div class="des">医院管理摘要</div></div></div>
<!-- mdweekly.html -->
<div class="news-left"><div class="img-right"><h1><a href="/index/article/detail?id=65000"><span>[深度报道]</span> 基层医疗人工智能实践</a></h1><p>智慧康养摘要</p><div class="time">2026-07-17</div></div></div>
<!-- bioon.html -->
<div class="composs-blog-list"><div class="item"><div class="item-content"><h2><a href="http://news.bioon.com/article/demo.html">创新药审批与产业转化观察</a></h2><p class="text-justify">创新药摘要</p><span class="item-meta-item">2026-07-12</span></div></div></div>
```

Save each commented fragment to its named file without the comment.

- [ ] **Step 2: Write the failing parser tests**

Start `tests/test_html_list_sources.py` with this setup:

```python
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.html_list_sources import HTML_LIST_PROFILES, parse_html_list_items


NOW = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
```

Then parameterize all 8 profiles with this exact table and assert exact title, absolute URL, and Asia/Shanghai-to-UTC date:

```python
CASES = [
    ("nhsa_policy", "nhsa.html", "https://www.nhsa.gov.cn/col/col104/index.html", ["www.nhsa.gov.cn"], "医保支持基层医疗服务通知", "https://www.nhsa.gov.cn/art/2026/7/17/art_104_1.html", datetime(2026, 7, 16, 16, 0, tzinfo=UTC)),
    ("chs_news", "chs.html", "https://www.chs.org.cn/news/list/7/", ["www.chs.org.cn"], "数智赋能基层医防融合", "https://www.chs.org.cn/news/show/501/", datetime(2026, 7, 15, 16, 0, tzinfo=UTC)),
    ("cnmia_news", "cnmia.html", "https://www.cnmia.org/Web/Article/Dynamic.aspx", ["www.cnmia.org"], "社会办医高质量发展实践", "https://www.cnmia.org/DynamicDetail_demo.html", datetime(2026, 7, 14, 16, 0, tzinfo=UTC)),
    ("chima_news", "chima.html", "https://www.chima.org.cn/Html/News/Main/53.html", ["www.chima.org.cn"], "医院AI数据治理周报", "https://www.chima.org.cn/Html/News/Articles/18000.html", datetime(2026, 7, 13, 16, 0, tzinfo=UTC)),
    ("kanyijie", "kanyijie.html", "https://www.kanyijie.com/", ["www.kanyijie.com"], "社会办医院引入基层AI服务", "https://www.kanyijie.com/details?id=2400", datetime(2026, 7, 13, 16, 0, tzinfo=UTC)),
    ("hospital_ceo", "hospital_ceo.html", "https://www.h-ceo.com/news.html", ["www.h-ceo.com"], "医院数智化运营新实践", "https://www.h-ceo.com/post/6000.html", datetime(2026, 7, 13, 8, 58, tzinfo=UTC)),
    ("mdweekly", "mdweekly.html", "https://www.mdweekly.com.cn/", ["www.mdweekly.com.cn"], "[深度报道] 基层医疗人工智能实践", "https://www.mdweekly.com.cn/index/article/detail?id=65000", datetime(2026, 7, 16, 16, 0, tzinfo=UTC)),
    ("bioon", "bioon.html", "https://www.bioon.com/", ["www.bioon.com", "news.bioon.com"], "创新药审批与产业转化观察", "http://news.bioon.com/article/demo.html", datetime(2026, 7, 11, 16, 0, tzinfo=UTC)),
]


@pytest.mark.parametrize("profile,filename,base_url,hosts,title,url,published", CASES)
def test_profile_extracts_dated_list_item(profile, filename, base_url, hosts, title, url, published):
    html = (Path("tests/fixtures/html_sources") / filename).read_text(encoding="utf-8")
    item = parse_html_list_items(html, base_url=base_url, profile_id=profile, allowed_hosts=hosts, now=NOW)[0]
    assert (item.title, item.url, item.published_at) == (title, url, published)
```

Add these edge tests:

```python
def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError, match="unsupported_parser_profile"):
        parse_html_list_items("<html></html>", base_url="https://example.com", profile_id="unknown", allowed_hosts=["example.com"], now=NOW)


def test_naive_collection_time_is_rejected_with_stable_category():
    with pytest.raises(ValueError, match="^invalid_publish_time$"):
        parse_html_list_items("<html></html>", base_url="https://example.com", profile_id="hospital_ceo", allowed_hosts=["example.com"], now=NOW.replace(tzinfo=None))


def test_cross_domain_and_undated_items_are_dropped():
    html = '<div class="paging"><div class="zlist01"><a class="tit" href="https://evil.example/post/1.html">跨域医院文章</a><span class="time">2026年07月13日 16:58</span></div><div class="zlist01"><a class="tit" href="/post/2.html">缺少发布日期文章</a></div></div>'
    assert parse_html_list_items(html, base_url="https://www.h-ceo.com/news.html", profile_id="hospital_ceo", allowed_hosts=["www.h-ceo.com"], now=NOW) == []


def test_html_parser_scans_at_most_one_hundred_candidates():
    rows = "".join(f'<div class="zlist01"><a class="tit" href="/post/{i}.html">医院管理文章 {i}</a><span class="time">2026年07月13日 16:58</span></div>' for i in range(105))
    items = parse_html_list_items(f'<div class="paging">{rows}</div>', base_url="https://www.h-ceo.com/news.html", profile_id="hospital_ceo", allowed_hosts=["www.h-ceo.com"], now=NOW)
    assert len(items) == 100
    assert len(HTML_LIST_PROFILES) == 8
```

- [ ] **Step 3: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_html_list_sources.py -q`

Expected: FAIL because `scripts.html_list_sources` does not exist.

- [ ] **Step 4: Implement the registry and parser**

Start `scripts/html_list_sources.py` with these imports:

```python
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag
```

Then define:

```python
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
```

Register exact profiles:

```python
HTML_LIST_PROFILES = {
    "nhsa_policy": HtmlListProfile("li", "a[href*='/art/']", "span:nth-of-type(4)", r"^/art/\d{4}/\d{1,2}/\d{1,2}/art_104_\d+\.html$", ("%Y-%m-%d",), title_attribute="title", content_mode="nhsa_cdata"),
    "chs_news": HtmlListProfile("li.catlist_li", "a[href*='/news/show/']", "span.f_r", r"^/news/show/\d+/?$", ("%Y-%m-%d",), title_attribute="title"),
    "cnmia_news": HtmlListProfile(".List .Block", ".Title a[href*='DynamicDetail_']", ".Time", r"^/DynamicDetail_[a-zA-Z0-9_-]+\.html$", ("%Y-%m-%d",), title_attribute="title", summary_selector=".Text", date_pattern=r"(\d{4}-\d{2}-\d{2})"),
    "chima_news": HtmlListProfile("ul.article_xw_l > li", ".right_xw a.title_type", ".span_date_left", r"^/Html/News/Articles/\d+\.html$", ("%d %Y.%m",), title_attribute="title", summary_selector=".right_xw > p"),
    "kanyijie": HtmlListProfile("div.des", "a.h2[href*='/details?id=']", ".time", r"^/details\?id=\d+$", ("%Y-%m-%d",), title_attribute="title", summary_selector=".sub"),
    "hospital_ceo": HtmlListProfile(".paging .zlist01", "a.tit[href*='/post/']", ".time", r"^/post/\d+\.html$", ("%Y年%m月%d日 %H:%M",), summary_selector=".des"),
    "mdweekly": HtmlListProfile(".news-left .img-right, .news-left ul.mt2 > li", "a[href*='/index/article/detail']", ".time", r"^/index/article/detail\?id=\d+$", ("%Y-%m-%d",), summary_selector="p"),
    "bioon": HtmlListProfile(".composs-blog-list .item", "h2 a[href*='news.bioon.com/article/']", ".item-meta-item", r"^/article/[a-zA-Z0-9_-]+\.html$", ("%Y-%m-%d",), summary_selector="p.text-justify"),
}
```

Add this exact parsing boundary below the registry:

```python
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
            nodes.extend(
                node for node in fragment.select(profile.item_selector) if isinstance(node, Tag)
            )
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


def _allowed_item_url(raw_url: str, base_url: str, profile: HtmlListProfile, allowed_hosts: Sequence[str]) -> str:
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
```

This keeps every field scoped to one candidate node, scans at most 100 records, never executes JavaScript, never follows detail links, and drops undated, cross-domain, malformed or more-than-two-days-future entries.

- [ ] **Step 5: Verify GREEN and commit**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_html_list_sources.py -q`

Run: `git add scripts/html_list_sources.py tests/test_html_list_sources.py tests/fixtures/html_sources`

Run: `git commit -m "feat: add restricted HTML list parsers"`

Expected: all HTML parser tests PASS and the commit is created.

---

### Task 3: Add the fixed YXJ public JSON parser

**Files:**
- Create: `scripts/yxj_source.py`
- Create: `tests/test_yxj_source.py`
- Create: `tests/fixtures/yxj_home.json`

**Interfaces:**
- Produces: `YXJ_API_URL`、`YXJ_REQUEST_BODY`。
- Produces: `parse_yxj_home_items(payload: Mapping[str, Any], *, now: datetime) -> list[ParsedYxjItem]`。

- [ ] **Step 1: Create the JSON fixture**

```json
{"code":200,"body":{"moduleList":[{"newsList":[{"articleId":505500,"title":"上海基层医疗人工智能应用落地","brief":"基层医疗AI应用摘要","publishTime":1784375308},{"articleId":505499,"title":"医院医保支付改革实践","brief":"医院支付改革摘要","publishTime":1784288908}]}]}}
```

- [ ] **Step 2: Write failing tests**

Start `tests/test_yxj_source.py` with:

```python
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.yxj_source import YXJ_API_URL, YXJ_REQUEST_BODY, parse_yxj_home_items


NOW = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
```

Then add:

```python
def test_yxj_fixture_maps_public_list_fields():
    payload = json.loads(Path("tests/fixtures/yxj_home.json").read_text(encoding="utf-8"))
    items = parse_yxj_home_items(payload, now=NOW)
    assert items[0].title == "上海基层医疗人工智能应用落地"
    assert items[0].url == "https://www.yxj.org.cn/detailPage?articleId=505500"
    assert items[0].summary == "基层医疗AI应用摘要"
    assert YXJ_API_URL == "https://pcapi.yxj.org.cn/ysz-content/web/home/news/getNewsModuleData"
    assert YXJ_REQUEST_BODY == {"categoryId": 0, "position": "HOME_PAGE_MAIN_NEWS"}


def test_yxj_parser_deduplicates_and_rejects_invalid_items():
    valid = {"articleId": 7, "title": "基层医院人工智能应用", "brief": "摘要", "publishTime": 1784375308}
    payload = {"body": {"moduleList": [{"newsList": [valid, valid, {"articleId": "bad", "title": "坏ID", "publishTime": 1784375308}, {"articleId": 8, "title": "缺少时间"}]}]}}
    assert [item.url for item in parse_yxj_home_items(payload, now=NOW)] == ["https://www.yxj.org.cn/detailPage?articleId=7"]


def test_yxj_parser_rejects_unexpected_shape():
    with pytest.raises(ValueError, match="invalid_json_shape"):
        parse_yxj_home_items({"body": {"moduleList": "bad"}}, now=NOW)


def test_yxj_parser_rejects_naive_collection_time():
    with pytest.raises(ValueError, match="^invalid_publish_time$"):
        parse_yxj_home_items({"body": {"moduleList": []}}, now=NOW.replace(tzinfo=None))
```

- [ ] **Step 3: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_yxj_source.py -q`

Expected: FAIL because the module does not exist.

- [ ] **Step 4: Implement the fixed parser**

Start `scripts/yxj_source.py` with:

```python
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
```

Then add:

```python
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
    body = payload.get("body")
    modules = body.get("moduleList") if isinstance(body, Mapping) else None
    if not isinstance(modules, list):
        raise ValueError("invalid_json_shape")
    items, seen = [], set()
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
            items.append(ParsedYxjItem(title[:300], f"https://www.yxj.org.cn/detailPage?articleId={article_id}", published, summary))
            if len(items) == 100:
                return items
    return items
```

- [ ] **Step 5: Verify GREEN and commit**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_yxj_source.py -q`

Run: `git add scripts/yxj_source.py tests/test_yxj_source.py tests/fixtures/yxj_home.json`

Run: `git commit -m "feat: add fixed YXJ list adapter"`

Expected: all YXJ parser tests PASS and the commit is created.

---

### Task 4: Integrate HTML and YXJ adapters into configured collection

**Files:**
- Modify: `scripts/update_news.py:40-65, 1146-1220, 1340-1380`
- Modify: `tests/test_configured_collection.py`

**Interfaces:**
- Consumes: `parse_html_list_items`、`parse_yxj_home_items`、`YXJ_API_URL`、`YXJ_REQUEST_BODY`。
- Produces: `fetch_html_list(...) -> list[RawItem]`、`fetch_yxj_home_json(...) -> list[RawItem]`。
- Extends: `fetch_configured_feed` dispatch for `html_list` and `yxj_home_json`。

- [ ] **Step 1: Write failing integration tests**

Add `import json` with the standard-library imports and add `import pytest` plus `import requests` with third-party imports in `tests/test_configured_collection.py`, then add fakes:

```python
class FakeListResponse:
    def __init__(self, *, text="", payload=None, url="https://www.h-ceo.com/news.html", content_type="text/html; charset=utf-8"):
        self.text = text
        self.content = text.encode("utf-8")
        self.payload = payload or {}
        self.url = url
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeAdapterSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.response

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.response


class FailingAdapterSession:
    def get(self, url, **kwargs):
        raise requests.ConnectionError("private network detail must not escape")
```

Add tests:

```python
def test_configured_html_list_is_filtered_capped_and_mapped():
    html = Path("tests/fixtures/html_sources/hospital_ceo.html").read_text(encoding="utf-8")
    feed = {"title": "中国医院院长网", "xml_url": "https://www.h-ceo.com/news.html", "html_url": "https://www.h-ceo.com/", "strategy": "html_list", "parser_profile": "hospital_ceo", "allowed_hosts": ["www.h-ceo.com"], "max_entries": 1, "include_keywords": "医院,AI", "exclude_keywords": "报名,培训班", "source_id": "cn-hospital-ceo", "category": "company_market", "source_tier": "b"}
    session = FakeAdapterSession(FakeListResponse(text=html))
    items = update_news.fetch_configured_feed(session, NOW, "medical_media", "Medical Media", feed)
    assert len(items) == 1
    assert items[0].title == "医院数智化运营新实践"
    assert items[0].meta["summary"] == "医院管理摘要"
    assert items[0].meta["source_id"] == "cn-hospital-ceo"
    assert session.calls[0][0] == "GET"


def test_configured_yxj_json_uses_fixed_post_contract():
    payload = json.loads(Path("tests/fixtures/yxj_home.json").read_text(encoding="utf-8"))
    feed = {"title": "医学界", "xml_url": "https://pcapi.yxj.org.cn/ysz-content/web/home/news/getNewsModuleData", "strategy": "json", "parser_profile": "yxj_home_json", "allowed_hosts": ["pcapi.yxj.org.cn", "www.yxj.org.cn"], "max_entries": 3, "include_keywords": "医院,医疗,基层,人工智能,AI,医保", "exclude_keywords": "用药,病例", "source_id": "cn-yxj", "category": "health_it", "source_tier": "c"}
    session = FakeAdapterSession(FakeListResponse(payload=payload, url=feed["xml_url"], content_type="application/json"))
    items = update_news.fetch_configured_feed(session, NOW, "medical_media", "Medical Media", feed)
    assert items[0].meta["source_id"] == "cn-yxj"
    assert session.calls[0][0] == "POST"
    assert session.calls[0][2]["json"] == {"categoryId": 0, "position": "HOME_PAGE_MAIN_NEWS"}


def test_adapter_zero_valid_items_is_a_per_source_failure(tmp_path: Path):
    config = tmp_path / "sources.yml"
    config.write_text("sources:\n  - id: empty-html\n    name: Empty HTML\n    feed_url: https://www.h-ceo.com/news.html\n    type: static_page\n    enabled: true\n    fetch: {strategy: html_list, parser_profile: hospital_ceo, allowed_hosts: [www.h-ceo.com]}\n", encoding="utf-8")
    items, sites, statuses = collect_all(FakeAdapterSession(FakeListResponse(text="<html></html>")), NOW, sources_config=config)
    assert items == []
    assert statuses[0]["ok"] is False
    assert statuses[0]["error"] == "no_valid_items"
    assert sites[0]["failed_source_count"] == 1


def test_configured_adapter_request_failure_uses_stable_error_category():
    feed = {"title": "中国医院院长网", "xml_url": "https://www.h-ceo.com/news.html", "html_url": "https://www.h-ceo.com/", "strategy": "html_list", "parser_profile": "hospital_ceo", "allowed_hosts": ["www.h-ceo.com"], "max_entries": 1, "source_id": "cn-hospital-ceo", "category": "company_market", "source_tier": "b"}
    with pytest.raises(ValueError, match="^request_failed$"):
        update_news.fetch_configured_feed(FailingAdapterSession(), NOW, "medical_media", "Medical Media", feed)


def test_configured_adapter_rejects_oversized_response():
    feed = {"title": "中国医院院长网", "xml_url": "https://www.h-ceo.com/news.html", "html_url": "https://www.h-ceo.com/", "strategy": "html_list", "parser_profile": "hospital_ceo", "allowed_hosts": ["www.h-ceo.com"], "max_entries": 1, "source_id": "cn-hospital-ceo", "category": "company_market", "source_tier": "b"}
    response = FakeListResponse(text="x" * (update_news.MAX_CONFIGURED_LIST_BYTES + 1))
    with pytest.raises(ValueError, match="^response_too_large$"):
        update_news.fetch_configured_feed(FakeAdapterSession(response), NOW, "medical_media", "Medical Media", feed)
```

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_configured_collection.py -q`

Expected: new tests FAIL because adapter strategies are not dispatched.

- [ ] **Step 3: Implement bounded response validation**

Add imports and constant:

```python
from scripts.html_list_sources import parse_html_list_items
from scripts.yxj_source import YXJ_API_URL, YXJ_REQUEST_BODY, parse_yxj_home_items

MAX_CONFIGURED_LIST_BYTES = 2_000_000
```

Add:

```python
def _adapter_request(call):
    try:
        return call()
    except requests.RequestException as exc:
        raise ValueError("request_failed") from exc


def _validate_adapter_response(response, expected_type: str, allowed_hosts: list[str]) -> None:
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ValueError("request_failed") from exc
    if len(response.content) > MAX_CONFIGURED_LIST_BYTES:
        raise ValueError("response_too_large")
    if expected_type not in str(response.headers.get("content-type") or "").lower():
        raise ValueError("unexpected_content_type")
    final_host = str(urlparse(str(response.url)).hostname or "").lower()
    if final_host not in set(allowed_hosts):
        raise ValueError("invalid_item_url")
```

Add a shared mapper and the two complete network boundaries:

```python
def _adapter_raw_items(parsed_items, feed, now, site_id, site_name):
    out = []
    max_entries = max(1, int(feed.get("max_entries") or 8))
    for parsed in parsed_items:
        if parsed.published_at < now - timedelta(days=MEDICAL_JOURNAL_MAX_AGE_DAYS):
            continue
        if not curated_feed_entry_allowed(feed, parsed.title, parsed.url):
            continue
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source=str(feed["title"]),
                title=parsed.title,
                url=parsed.url,
                published_at=parsed.published_at,
                meta={
                    "feed_url": str(feed["xml_url"]),
                    "feed_home": str(feed.get("html_url") or ""),
                    "summary": parsed.summary,
                    **configured_feed_meta(feed),
                },
            )
        )
        if len(out) >= max_entries:
            break
    if not out:
        raise ValueError("no_valid_items")
    return out


def fetch_html_list(session, feed, now, site_id, site_name):
    allowed_hosts = list(feed.get("allowed_hosts") or [])
    response = _adapter_request(
        lambda: session.get(
            str(feed["xml_url"]),
            timeout=max(1, int(feed.get("timeout_seconds") or 20)),
            headers={"User-Agent": CONFIGURED_FEED_UA, "Accept": "text/html,application/xhtml+xml"},
        )
    )
    _validate_adapter_response(response, "text/html", allowed_hosts)
    parsed = parse_html_list_items(
        response.text,
        base_url=str(response.url),
        profile_id=str(feed.get("parser_profile") or ""),
        allowed_hosts=allowed_hosts,
        now=now,
    )
    return _adapter_raw_items(parsed, feed, now, site_id, site_name)


def fetch_yxj_home_json(session, feed, now, site_id, site_name):
    if str(feed.get("xml_url") or "") != YXJ_API_URL:
        raise ValueError("unsupported_parser_profile")
    allowed_hosts = list(feed.get("allowed_hosts") or [])
    response = _adapter_request(
        lambda: session.post(
            YXJ_API_URL,
            json=YXJ_REQUEST_BODY,
            timeout=max(1, int(feed.get("timeout_seconds") or 20)),
            headers={"User-Agent": CONFIGURED_FEED_UA, "Accept": "application/json", "Content-Type": "application/json"},
        )
    )
    _validate_adapter_response(response, "application/json", allowed_hosts)
    try:
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ValueError("invalid_json_shape") from exc
    parsed = parse_yxj_home_items(payload, now=now)
    return _adapter_raw_items(parsed, feed, now, site_id, site_name)
```

Replace `fetch_configured_feed` with this dispatch order, retaining the existing Crossref and RSS bodies exactly:

```python
def fetch_configured_feed(
    session: requests.Session,
    now: datetime,
    site_id: str,
    site_name: str,
    feed: dict[str, Any],
) -> list[RawItem]:
    strategy = str(feed.get("strategy") or "auto")
    profile = str(feed.get("parser_profile") or "")
    if strategy == "html_list":
        return fetch_html_list(session, feed, now, site_id, site_name)
    if strategy == "json" and profile == "yxj_home_json":
        return fetch_yxj_home_json(session, feed, now, site_id, site_name)
    if strategy == "json":
        feed_url = str(feed["xml_url"])
        if urlparse(feed_url).hostname != "api.crossref.org":
            raise ValueError("Unsupported configured JSON feed")
        response = session.get(
            feed_url,
            timeout=max(1, int(feed.get("timeout_seconds") or 20)),
            headers={"User-Agent": CONFIGURED_FEED_UA, "Accept": "application/json"},
        )
        response.raise_for_status()
        return parse_crossref_json_items(response.json(), feed, now, site_id, site_name)
    if site_id == "official_health":
        return fetch_feed_as_official_items(session, feed, now, site_id=site_id, site_name=site_name)
    response = session.get(
        str(feed["xml_url"]),
        timeout=max(1, int(feed.get("timeout_seconds") or 20)),
        headers={
            "User-Agent": CONFIGURED_FEED_UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    response.raise_for_status()
    return parse_curated_media_feed_items(response.content, feed, now, site_id, site_name)
```

- [ ] **Step 4: Verify GREEN and regressions**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_configured_collection.py tests\test_html_list_sources.py tests\test_yxj_source.py tests\test_config_loader.py -q`

Expected: all selected tests PASS, including Crossref.

- [ ] **Step 5: Commit**

Run: `git add scripts/update_news.py tests/test_configured_collection.py`

Run: `git commit -m "feat: collect restricted HTML and YXJ sources"`

---

### Task 5: Configure nine China medical sources and filters

**Files:**
- Modify: `config/sources.yml`
- Modify: `tests/test_config_loader.py`
- Modify: `tests/test_configured_collection.py`

**Interfaces:**
- Consumes: Tasks 1-4 adapter contracts.
- Produces: 9 enabled source rows with exact profile, tier, category, cap and filters.

- [ ] **Step 1: Write the failing config contract**

```python
def test_default_config_contains_nine_dated_china_sources():
    by_id = {row["id"]: row for row in load_config("sources", Path("config/sources.yml")).data["sources"]}
    expected = {
        "cn-nhsa-policy": ("html_list", "nhsa_policy", "s", "insurance_compliance", 8),
        "cn-chs-news": ("html_list", "chs_news", "a", "primary_care", 6),
        "cn-cnmia-news": ("html_list", "cnmia_news", "a", "company_market", 6),
        "cn-chima-news": ("html_list", "chima_news", "a", "health_it", 6),
        "cn-kanyijie": ("html_list", "kanyijie", "b", "company_market", 5),
        "cn-hospital-ceo": ("html_list", "hospital_ceo", "b", "company_market", 5),
        "cn-mdweekly": ("html_list", "mdweekly", "b", "primary_care", 4),
        "cn-yxj": ("json", "yxj_home_json", "c", "health_it", 3),
        "cn-bioon": ("html_list", "bioon", "c", "pharma_device", 3),
    }
    for source_id, contract in expected.items():
        row = by_id[source_id]
        assert row["enabled"] is True
        assert row["language"] == "zh" and row["region"] == "cn"
        assert row["fetch"]["allowed_hosts"]
        assert (row["fetch"]["strategy"], row["fetch"]["parser_profile"], row["tier"], row["category"], row["fetch"]["max_items"]) == contract
    assert "cn-medtrend" not in by_id
```

Add this exact filter contract to `tests/test_configured_collection.py`:

```python
def test_china_media_filters_keep_domain_news_and_drop_promotional_or_clinical_items():
    groups, result = configured_feed_groups(Path("config/sources.yml"))
    assert result.used_fallback is False
    feeds = {
        feed["source_id"]: feed
        for group_feeds in groups.values()
        for feed in group_feeds
    }
    article_url = "https://example.invalid/article"
    assert update_news.curated_feed_entry_allowed(feeds["cn-kanyijie"], "社会办医院AI应用落地", article_url)
    assert not update_news.curated_feed_entry_allowed(feeds["cn-kanyijie"], "医疗大会早鸟票报名通知", article_url)
    assert not update_news.curated_feed_entry_allowed(feeds["cn-yxj"], "儿童鼻窦炎用药指南", article_url)
    assert update_news.curated_feed_entry_allowed(feeds["cn-bioon"], "创新药获批推动产业转化", article_url)
```

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_config_loader.py::test_default_config_contains_nine_dated_china_sources tests\test_configured_collection.py::test_china_media_filters_keep_domain_news_and_drop_promotional_or_clinical_items -q`

Expected: FAIL because the source IDs do not exist.

- [ ] **Step 3: Append exact YAML rows**

Append these complete rows under the existing `sources:` array:

```yaml
  - id: cn-nhsa-policy
    name: 国家医保局政策法规
    homepage_url: https://www.nhsa.gov.cn/col/col104/index.html
    feed_url: https://www.nhsa.gov.cn/col/col104/index.html
    type: government_page
    category: insurance_compliance
    tier: s
    language: zh
    region: cn
    enabled: true
    featured: true
    fetch: {strategy: html_list, interval_hours: 3, max_items: 8, timeout_seconds: 20, parser_profile: nhsa_policy, allowed_hosts: [www.nhsa.gov.cn]}
    filters: {include_keywords: [], exclude_keywords: []}
    metadata: {source_origin: manual, added_by: system, legacy_site_id: official_health, notes: 国家医保局公开政策法规列表}

  - id: cn-chs-news
    name: 中国社区卫生协会
    homepage_url: https://www.chs.org.cn/news/
    feed_url: https://www.chs.org.cn/news/list/7/
    type: static_page
    category: primary_care
    tier: a
    language: zh
    region: cn
    enabled: true
    featured: true
    fetch: {strategy: html_list, interval_hours: 6, max_items: 6, timeout_seconds: 20, parser_profile: chs_news, allowed_hosts: [www.chs.org.cn]}
    filters: {include_keywords: [], exclude_keywords: [培训班, 报名]}
    metadata: {source_origin: manual, added_by: system, legacy_site_id: medical_media, notes: 中国社区卫生协会分支机构列表}

  - id: cn-cnmia-news
    name: 中国非公立医疗机构协会
    homepage_url: https://www.cnmia.org/
    feed_url: https://www.cnmia.org/Web/Article/Dynamic.aspx
    type: static_page
    category: company_market
    tier: a
    language: zh
    region: cn
    enabled: true
    featured: true
    fetch: {strategy: html_list, interval_hours: 6, max_items: 6, timeout_seconds: 20, parser_profile: cnmia_news, allowed_hosts: [www.cnmia.org]}
    filters: {include_keywords: [], exclude_keywords: [培训班, 报名, 招商]}
    metadata: {source_origin: manual, added_by: system, legacy_site_id: medical_media, notes: 非公立医疗机构协会公开动态}

  - id: cn-chima-news
    name: CHIMA
    homepage_url: https://www.chima.org.cn/
    feed_url: https://www.chima.org.cn/Html/News/Main/53.html
    type: static_page
    category: health_it
    tier: a
    language: zh
    region: cn
    enabled: true
    featured: true
    fetch: {strategy: html_list, interval_hours: 6, max_items: 6, timeout_seconds: 20, parser_profile: chima_news, allowed_hosts: [www.chima.org.cn]}
    filters: {include_keywords: [], exclude_keywords: [培训班, 报名]}
    metadata: {source_origin: manual, added_by: system, legacy_site_id: medical_media, notes: 医院信息化联盟公开新闻}

  - id: cn-kanyijie
    name: 看医界
    homepage_url: https://www.kanyijie.com/
    feed_url: https://www.kanyijie.com/
    type: social_observation
    category: company_market
    tier: b
    language: zh
    region: cn
    enabled: true
    featured: false
    fetch: {strategy: html_list, interval_hours: 3, max_items: 5, timeout_seconds: 20, parser_profile: kanyijie, allowed_hosts: [www.kanyijie.com]}
    filters: {include_keywords: [医院, 诊所, 社会办医, 民营, 医疗, 医保, 医共体, 基层, AI, 人工智能], exclude_keywords: [报名, 早鸟票, 招商, 招聘, 课程, 培训班, 会议通知, 直播预告, 广告]}
    metadata: {source_origin: manual, added_by: system, legacy_site_id: medical_media, notes: 社会办医行业媒体}

  - id: cn-hospital-ceo
    name: 中国医院院长网
    homepage_url: https://www.h-ceo.com/
    feed_url: https://www.h-ceo.com/news.html
    type: social_observation
    category: company_market
    tier: b
    language: zh
    region: cn
    enabled: true
    featured: false
    fetch: {strategy: html_list, interval_hours: 3, max_items: 5, timeout_seconds: 20, parser_profile: hospital_ceo, allowed_hosts: [www.h-ceo.com]}
    filters: {include_keywords: [医院, 医疗, 医保, 医共体, AI, 人工智能, 数智化, 运营, 管理], exclude_keywords: [报名, 早鸟票, 招商, 招聘, 课程, 培训班, 会议通知, 直播预告, 广告]}
    metadata: {source_origin: manual, added_by: system, legacy_site_id: medical_media, notes: 医院管理和数智化媒体}

  - id: cn-mdweekly
    name: 医师报
    homepage_url: https://www.mdweekly.com.cn/
    feed_url: https://www.mdweekly.com.cn/
    type: social_observation
    category: primary_care
    tier: b
    language: zh
    region: cn
    enabled: true
    featured: false
    fetch: {strategy: html_list, interval_hours: 3, max_items: 4, timeout_seconds: 20, parser_profile: mdweekly, allowed_hosts: [www.mdweekly.com.cn]}
    filters: {include_keywords: [医院, 医疗, 基层, 卫生院, 医共体, 人工智能, AI, 医保, 健康管理], exclude_keywords: [病例, 用药, 症状, 诊疗指南, 报名, 招商, 招聘, 课程, 培训班, 直播预告, 广告]}
    metadata: {source_origin: manual, added_by: system, legacy_site_id: medical_media, notes: 医师报公开行业新闻}

  - id: cn-yxj
    name: 医学界
    homepage_url: https://www.yxj.org.cn/
    feed_url: https://pcapi.yxj.org.cn/ysz-content/web/home/news/getNewsModuleData
    type: json
    category: health_it
    tier: c
    language: zh
    region: cn
    enabled: true
    featured: false
    fetch: {strategy: json, interval_hours: 3, max_items: 3, timeout_seconds: 20, parser_profile: yxj_home_json, allowed_hosts: [pcapi.yxj.org.cn, www.yxj.org.cn]}
    filters: {include_keywords: [医院, 医疗, 医保, 医共体, 基层, AI, 人工智能, 政策], exclude_keywords: [病例, 用药, 症状, 诊疗指南, 报名, 招商, 招聘, 课程, 培训班, 直播预告, 广告]}
    metadata: {source_origin: manual, added_by: system, legacy_site_id: medical_media, notes: 医学界公开首页列表接口}

  - id: cn-bioon
    name: 生物谷
    homepage_url: https://www.bioon.com/
    feed_url: https://www.bioon.com/
    type: social_observation
    category: pharma_device
    tier: c
    language: zh
    region: cn
    enabled: true
    featured: false
    fetch: {strategy: html_list, interval_hours: 6, max_items: 3, timeout_seconds: 20, parser_profile: bioon, allowed_hosts: [www.bioon.com, news.bioon.com]}
    filters: {include_keywords: [创新药, 医疗器械, 医药产业, 人工智能, AI, 获批, 审批, 临床试验, 转化, 研发], exclude_keywords: [报名, 早鸟票, 招商, 招聘, 课程, 培训班, 会议通知, 直播预告, 广告]}
    metadata: {source_origin: manual, added_by: system, legacy_site_id: medical_media, notes: 生物医药新媒体公开列表}
```

- [ ] **Step 4: Verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_config_loader.py tests\test_configured_collection.py -q`

Expected: all config/filter/collection tests PASS.

- [ ] **Step 5: Commit**

Run: `git add config/sources.yml tests/test_config_loader.py tests/test_configured_collection.py`

Run: `git commit -m "feat: configure nine China medical sources"`

---

### Task 6: Document boundaries and coverage

**Files:**
- Modify: `README.md`
- Modify: `docs/source-schema.md`
- Modify: `docs/CONFIG_REFERENCE.md`
- Modify: `docs/SOURCE_COVERAGE.md`

**Interfaces:**
- Documents the exact configuration and operational behavior implemented in Tasks 1-5.

- [ ] **Step 1: Add the README boundary**

```markdown
### 国内列表级信源

国内政策、协会和行业媒体使用公开 RSS、静态 HTML 列表或登记过的公开 JSON 列表接口。采集器只读取标题、原文链接、发布日期和列表已有短摘要，不执行 JavaScript、不发送 Cookie、不访问详情页，也不绕过登录、验证码、WAF 或付费墙。

S/A 级来源用于政策与行业依据；B/C 级医疗媒体只作为线索发现层，并应用主题过滤和单源限流。同一事件优先展示更高等级来源。
```

- [ ] **Step 2: Document schema fields and profiles**

Add to `docs/source-schema.md` and `docs/CONFIG_REFERENCE.md`:

```markdown
| `fetch.parser_profile` | string | 登记过的解析器 ID：`nhsa_policy`、`chs_news`、`cnmia_news`、`chima_news`、`kanyijie`、`hospital_ceo`、`mdweekly`、`bioon`、`yxj_home_json` |
| `fetch.allowed_hosts` | string[] | 列表最终地址和文章链接允许使用的公共域名白名单 |

`html_list` 最多扫描 100 个候选节点、最多读取 2,000,000 bytes，缺少有效标题、URL 或发布日期的条目会被丢弃。`yxj_home_json` 只允许固定医学界主机、路径、POST 请求体和字段路径，不能用作通用 JSON 请求器。
```

List stable errors exactly:

```text
unsupported_parser_profile
request_failed
response_too_large
unexpected_content_type
no_valid_items
invalid_json_shape
invalid_item_url
invalid_publish_time
```

- [ ] **Step 3: Add the coverage matrix**

```markdown
| 领域 | S/A 级核心来源 | B/C 级发现来源 |
| --- | --- | --- |
| 医保政策与合规 | 国家医保局 | 中国医院院长网、医学界 |
| 基层与社区卫生 | 中国社区卫生协会 | 医师报、看医界 |
| 社会办医 | 中国非公立医疗机构协会 | 看医界、中国医院院长网 |
| 医疗 AI 与信息化 | CHIMA | 医学界、中国医院院长网、医师报 |
| 医药器械与科研转化 | — | 生物谷 |
```

- [ ] **Step 4: Verify docs**

Run: `rg -n "parser_profile|allowed_hosts|no_valid_items|列表级信源" README.md docs/source-schema.md docs/CONFIG_REFERENCE.md docs/SOURCE_COVERAGE.md`

Run: `rg -n "cn-nhsa-policy|cn-chs-news|cn-cnmia-news|cn-chima-news|cn-kanyijie|cn-hospital-ceo|cn-mdweekly|cn-yxj|cn-bioon" config/sources.yml`

Expected: all required terms and all 9 source IDs appear.

- [ ] **Step 5: Commit**

Run: `git add README.md docs/source-schema.md docs/CONFIG_REFERENCE.md docs/SOURCE_COVERAGE.md`

Run: `git commit -m "docs: explain China medical source coverage"`

---

### Task 7: Full verification and Draft PR delivery

**Files:**
- Verify: all changed files
- Inspect generated output only: `data/source-status.json`、`data/source-registry.json`、`data/latest-24h.json`

**Interfaces:**
- Produces: pushed feature branch and Draft PR; does not merge `main`.

- [ ] **Step 1: Run all offline verification**

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Run: `.\.venv\Scripts\python.exe -m compileall scripts`

Run: `node --check assets/app.js`

Run: `node --check assets/sources.js`

Run: `git diff --check`

Expected: original 107 tests plus all new tests PASS; compilation, JavaScript syntax and whitespace checks exit 0.

- [ ] **Step 2: Verify config and fixture integrity**

Run:

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; from scripts.config_loader import load_config; rows=load_config('sources', Path('config/sources.yml')).data['sources']; ids={r['id'] for r in rows}; expected={'cn-nhsa-policy','cn-chs-news','cn-cnmia-news','cn-chima-news','cn-kanyijie','cn-hospital-ceo','cn-mdweekly','cn-yxj','cn-bioon'}; assert expected <= ids; print('china_sources=9')"
```

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_html_list_sources.py tests\test_yxj_source.py -q`

Expected: `china_sources=9` and all fixture tests PASS.

- [ ] **Step 3: Review scope and secrets**

Run: `git status --short --branch`

Run: `git diff origin/main...HEAD --stat`

Run: `git diff origin/main...HEAD --check`

Run: `git diff origin/main...HEAD -- config/sources.yml scripts/config_loader.py scripts/html_list_sources.py scripts/yxj_source.py scripts/update_news.py`

Expected: only planned code, tests, config, design/plan and docs; no token, Cookie, private OPML, full webpage dump or article body.

- [ ] **Step 4: Push the feature branch**

```powershell
$env:GCM_INTERACTIVE = 'Never'
git push -u origin feature/china-medical-sources
Remove-Item Env:GCM_INTERACTIVE -ErrorAction SilentlyContinue
```

Expected: branch push succeeds without credential output.

- [ ] **Step 5: Create the Draft PR**

Title: `feat: add China medical sources and media adapters`

Body:

```markdown
## Summary
- add 9 dated China medical policy, association, hospital and industry sources
- add 8 restricted HTML list profiles and one fixed YXJ public JSON adapter
- add per-source filtering, caps, failure isolation and offline fixtures

## Safety
- no login, Cookie, JavaScript execution, WAF bypass or detail-page scraping
- fixed hosts, response cap, valid publication dates and media source downgrading

## Verification
- full pytest suite
- Python compileall
- frontend node syntax checks
- GitHub Actions source/update verification
```

Expected: Draft PR URL is returned; do not merge.

- [ ] **Step 6: Run GitHub Actions on the feature branch**

Dispatch the repository update workflow on `feature/china-medical-sources`, wait for completion, and inspect output for:

```text
workflow conclusion is success
all 9 IDs appear in configured source status
one failed source does not cancel other sources
no fabricated publication time exists
B/C media respect 5/5/4/3/3 caps
NHSA wins duplicate policy events over media
```

If the workflow creates a normal generated-data commit, run `git pull --ff-only`, inspect only `data/`, and rerun Step 1 before updating the Draft PR.

- [ ] **Step 7: Report the handoff**

Report the Draft PR URL, final SHA, total tests, Actions run URL/conclusion, new-source healthy/warning/failed counts, and any disabled source with its exact public-access reason. Do not claim production Pages deployment before merge and a successful post-merge workflow.
