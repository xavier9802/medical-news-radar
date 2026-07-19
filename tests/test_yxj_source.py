import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.yxj_source import YXJ_API_URL, YXJ_REQUEST_BODY, parse_yxj_home_items


NOW = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)


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
    with pytest.raises(ValueError, match="invalid_json_shape"):
        parse_yxj_home_items([], now=NOW)


def test_yxj_parser_rejects_naive_collection_time():
    with pytest.raises(ValueError, match="^invalid_publish_time$"):
        parse_yxj_home_items({"body": {"moduleList": []}}, now=NOW.replace(tzinfo=None))
