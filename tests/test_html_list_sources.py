from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.html_list_sources import HTML_LIST_PROFILES, parse_html_list_items


NOW = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)

CASES = [
    ("nhsa_policy", "nhsa.html", "https://www.nhsa.gov.cn/col/col104/index.html", ["www.nhsa.gov.cn"], "医保支持基层医疗服务通知", "https://www.nhsa.gov.cn/art/2026/7/17/art_104_1.html", datetime(2026, 7, 16, 16, 0, tzinfo=UTC)),
    ("chs_news", "chs.html", "https://www.chs.org.cn/news/list/7/", ["www.chs.org.cn"], "数智赋能基层医防融合", "https://www.chs.org.cn/news/show/501/", datetime(2026, 7, 15, 16, 0, tzinfo=UTC)),
    ("cnmia_news", "cnmia.html", "https://www.cnmia.org/Web/Article/Dynamic.aspx", ["www.cnmia.org"], "社会办医高质量发展实践", "https://www.cnmia.org/DynamicDetail_demo.html", datetime(2026, 7, 14, 16, 0, tzinfo=UTC)),
    ("chima_news", "chima.html", "https://www.chima.org.cn/Html/News/Main/53.html", ["www.chima.org.cn"], "医院AI数据治理周报", "https://www.chima.org.cn/Html/News/Articles/18000.html", datetime(2026, 7, 13, 16, 0, tzinfo=UTC)),
    ("kanyijie", "kanyijie.html", "https://www.kanyijie.com/", ["www.kanyijie.com"], "社会办医院引入基层AI服务", "https://www.kanyijie.com/details?id=2400", datetime(2026, 7, 13, 16, 0, tzinfo=UTC)),
    ("hospital_ceo", "hospital_ceo.html", "https://www.h-ceo.com/news.html", ["www.h-ceo.com"], "医院数智化运营新实践", "https://www.h-ceo.com/post/6000.html", datetime(2026, 7, 13, 8, 58, tzinfo=UTC)),
    ("mdweekly", "mdweekly.html", "https://www.mdweekly.com.cn/index/article/zt1?id=1", ["www.mdweekly.com.cn"], "基层医疗人工智能实践", "https://www.mdweekly.com.cn/index/article/ztdetail?id=65000", datetime(2026, 7, 16, 16, 0, tzinfo=UTC)),
    ("bioon", "bioon.html", "https://www.bioon.com/", ["www.bioon.com", "news.bioon.com"], "创新药审批与产业转化观察", "http://news.bioon.com/article/demo.html", datetime(2026, 7, 11, 16, 0, tzinfo=UTC)),
]


@pytest.mark.parametrize("profile,filename,base_url,hosts,title,url,published", CASES)
def test_profile_extracts_dated_list_item(profile, filename, base_url, hosts, title, url, published):
    html = (Path("tests/fixtures/html_sources") / filename).read_text(encoding="utf-8")
    item = parse_html_list_items(html, base_url=base_url, profile_id=profile, allowed_hosts=hosts, now=NOW)[0]
    assert (item.title, item.url, item.published_at) == (title, url, published)


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
