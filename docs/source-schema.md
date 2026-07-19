# 信源与评分数据结构

所有 YAML 文件使用 UTF-8。加载器会验证顶层结构；配置缺失时使用安全默认值，YAML 语法错误会报告具体文件和解析原因。

## `config/sources.yml`

顶层字段 `sources` 为数组。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 稳定、唯一、建议 kebab-case 的信源 ID |
| `name` | string | 展示名称 |
| `homepage_url` | string | 公开 HTTP(S) 主页 |
| `feed_url` | string | RSS、Atom 或 JSON 地址；没有时可为空 |
| `type` | string | `rss`、`atom`、`opml`、`json`、`static_page`、`government_page`、`journal`、`company`、`newsletter`、`social_observation` |
| `category` | string | 八大栏目 ID 之一 |
| `tier` | string | `s`、`a`、`b`、`c` |
| `language` | string | 如 `zh`、`en` |
| `region` | string | 如 `cn`、`us`、`global` |
| `enabled` | boolean | 是否参加采集；关闭后注册表为 `disabled` |
| `featured` | boolean | 是否为重点来源 |
| `fetch.strategy` | string | `auto`、`rss`、`json`、`html_list`、`jina`、`skip` |
| `fetch.interval_hours` | number | 建议采集间隔 |
| `fetch.max_items` | integer | 单轮最大条目数 |
| `fetch.timeout_seconds` | number | 单来源超时建议 |
| `fetch.parser_profile` | string | 登记过的解析器 ID：`nhsa_policy`、`chs_news`、`cnmia_news`、`chima_news`、`kanyijie`、`hospital_ceo`、`mdweekly`、`bioon`、`yxj_home_json` |
| `fetch.allowed_hosts` | string[] | 列表最终地址和文章链接允许使用的公共域名白名单 |
| `filters.include_keywords` | array | 仅保留命中词；空数组表示不额外限制 |
| `filters.exclude_keywords` | array | 排除词 |
| `metadata.source_origin` | string | 如 `builtin`、`manual` |
| `metadata.added_by` | string | 配置来源，不放邮箱或 Token |
| `metadata.legacy_site_id` | string | 与旧抓取器兼容的可选 ID |
| `metadata.notes` | string | 维护备注和暂停原因 |

当前内置 `json` 采集器仅接受 `api.crossref.org` 的期刊 works 响应，并读取 `message.items` 中的标题、DOI 链接和发布日期。它用于期刊官网 RSS 在 GitHub Actions 被 403 拦截时的元数据回退；其他 JSON 地址必须先实现明确适配器，不能按通用 feed 直接启用。

`html_list` 最多扫描 100 个候选节点、最多读取 2,000,000 bytes，缺少有效标题、URL 或发布日期的条目会被丢弃。`yxj_home_json` 只允许固定医学界主机、路径、POST 请求体和字段路径，不能用作通用 JSON 请求器。

受限适配器使用以下稳定错误类别，状态文件不会记录第三方响应正文：

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

## `config/categories.yml`

顶层 `categories` 为数组。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | `policy`、`medical_ai`、`primary_care`、`insurance_compliance`、`health_it`、`pharma_device`、`company_market`、`global_healthtech` |
| `label` | string | 中文显示名 |
| `description` | string | 栏目范围 |
| `order` | integer | 显示顺序 |
| `enabled` | boolean | 是否启用 |

“全部”是前端聚合视图，不作为内容分类写入配置。

## `config/keywords.yml`

顶层包含 `strong_keywords`、`medium_keywords`、`noise_keywords`。每项支持：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `term` | string | 中英文关键词或短语 |
| `weight` | number | 对相关性/噪声的贡献 |
| `categories` | array | 关联栏目 ID；噪声词可为空 |
| `enabled` | boolean | 是否参与规则评分 |

规则输出命中词用于解释，不应把单一宽泛词当作医疗事实证明。

## `config/scoring.yml`

- `weights`：`authority`、`medical_relevance`、`impact`、`recency`、`multi_source_heat`。
- `thresholds`：`selected`、`relevant`、`minimum`。
- `bonuses`：官方政策、生效日期、国家级、基层影响、医保合规影响和多来源加分。

最终 `medical_relevance_score`、`impact_score`、`importance_score` 和权威分均限制在 0 到 1。旧 editorial/AI relevance/source tier 字段仍保留兼容入口。

## `data/source-registry.json`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `generated_at` | ISO8601 string | 生成时间 |
| `total` | integer | 配置中信源总数 |
| `enabled` | integer | 已启用数量 |
| `healthy` | integer | 正常数量 |
| `warning` | integer | 注意数量 |
| `failed` | integer | 异常数量 |
| `disabled` | integer | 已暂停数量 |
| `unknown` | integer | 尚无状态数据的数量 |
| `sources` | array | 合并后的信源对象 |

每个 `sources[]` 包含配置字段，以及 `category_label`、`tier_label`、`status`、`last_success_at`、`last_checked_at`、`success_rate`、`latest_item_at`、`error`。`status` 只能是 `healthy`、`warning`、`failed`、`disabled`、`unknown`。状态文件缺失时，启用源为 `unknown`，禁用源为 `disabled`。

## `data/source-probe-result.json`

单地址结果包含：

- `checked_at`、`input_url`、`resolved_url`
- `reachable`、`status_code`、`content_type`、`response_ms`
- `detected_type`、`recommended_strategy`
- `feed_valid`、`item_count`、`latest_item_at`
- `has_title`、`has_timestamp`
- `requires_login`、`blocked`
- `medical_relevance`、`recommended_category`、`recommended_tier`
- `warnings`、`errors`

配置批量检测时，输出为包含多个结果的集合。探测器只返回结构化元数据，不写入响应正文；`input_url` 会去掉查询参数以降低意外泄密风险。

## 新闻条目扩展字段

在保留旧字段的基础上，条目可包含：`category`、`category_label`、`source_id`、`source_tier`、`source_authority_score`、`language`、`region`、`medical_relevance_score`、`impact_score`、`importance_score`、`is_official`、`is_policy`、`policy_metadata`、`topic_value`、`content_angles`。

无法识别的政策元数据使用空字符串或空数组。不得推测文件号、发布机构、生效日期或适用范围。
