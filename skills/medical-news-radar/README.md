# 医源 Skill｜Medical Source Scout

医源 Skill 帮助维护者判断一个医疗信息源是否值得长期接入 Medical News Radar，并选择 RSS、Atom、OPML、JSON、公开列表页或跳过策略。

它遵循三个原则：

1. 先选择高价值来源，再增加抓取能力。
2. 优先稳定公开 feed，不绕过登录、验证码、Cookie 或付费墙。
3. Agent 负责评估和配置，日常采集交给 GitHub Actions，展示交给 GitHub Pages。

## 使用方式

让 Agent 先完整读取 `skills/medical-news-radar/SKILL.md`，再提供候选来源的名称、主页、feed 地址、期望栏目和推荐理由。

示例：

```text
请使用医源 Skill 评估下面的医疗行业来源。对每个来源判断推荐栏目、S/A/B/C 等级、抓取策略、登录限制和维护风险；先运行安全探测，再决定是否加入 config/sources.yml。不要提交密钥、Cookie、私人 OPML 或文章全文。
```

## 接入顺序

1. 官方 RSS / Atom 和正式政策原文
2. 权威医学期刊、研究机构与企业官方公告
3. 稳定公开 JSON 或结构清晰的列表页
4. 私有 OPML 中的个人订阅
5. 只有在价值明确且接受维护成本时，才考虑自定义解析器

需要登录、动态验证码、私人邮箱正文、原始社交时间线和不稳定桥接的来源不进入公共默认配置。

## 常用命令

```bash
python scripts/source_probe.py --url "https://example.com/feed.xml" --name "候选来源"
python scripts/source_probe.py --config config/sources.yml --output data/source-probe-result.json
python scripts/update_news.py --output-dir data --window-hours 24
python scripts/build_source_registry.py
python -m pytest -q
```

## 输出与发布

`config/sources.yml` 是公开信源清单，`data/source-status.json` 是采集状态，`data/source-registry.json` 是两者合并后的前端数据。`/sources.html` 只读展示状态并链接 GitHub Issue Form，不会直接写仓库。

私有 OPML 保存为本地 `feeds/follow.opml`，或通过 `FOLLOW_OPML_B64` Secret 注入 Actions；不得提交到公开仓库。

## 安全边界

- 不提交 API Key、Token、Cookie、`.env`、私人 OPML 或邮件正文
- 不执行目标页面 JavaScript，不绕过访问限制
- 不保存或展示第三方文章完整正文
- 不生成医疗诊断建议
- 不虚构政策、临床、融资或审批事实
- 事实不确定时明确要求核验官方原文

项目架构、配置和部署说明见仓库根目录 [README.md](../../README.md)、[source-management.md](../../docs/source-management.md) 与 [source-schema.md](../../docs/source-schema.md)。
