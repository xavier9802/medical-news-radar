# Medical News Radar｜医疗行业情报雷达

一个完全运行在 GitHub 上的医疗行业信源、政策、技术与选题情报系统。GitHub Actions 定时采集、校验并生成 `data/*.json`，随后通过 GitHub Pages Artifact 显式部署静态网站；不需要 PHP、数据库、登录系统或长期运行的服务器。

- 情报首页：`/index.html`
- 信源管理：`/sources.html`
- 在线站点：[xavier9802.github.io/medical-news-radar](https://xavier9802.github.io/medical-news-radar/)

本项目面向医疗内容运营、医疗 AI 产品、政策研究、基层医疗和医疗信息化从业者。它延续原有抓取、标准化、去重、多来源故事合并、健康监测和静态发布管线，并把分类、关键词、评分与信源逐步迁移为可维护配置。

## 核心能力

- 八大医疗栏目：政策监管、医疗AI、基层医疗、医保合规、医疗信息化、医药器械、企业动态、海外前沿
- 保留全部、精选、全量、当前热点、搜索、时间排序和多来源折叠
- 基于来源权威性、医疗相关性、影响、时效与多源热度的可解释评分
- S/A/B/C 四级信源和静态信源注册表
- GitHub Issue Form 推荐信源，受限的 Actions 安全检测
- 医疗行业内容主编、医疗政策分析师、医疗 AI 产品负责人三类 Persona
- DeepSeek 为可选增强；未配置密钥时规则评分和数据生成仍完整运行

## 纯 GitHub 架构

```text
config/*.yml + public feeds + optional private OPML
                         ↓
                GitHub Actions（每 30 分钟）
                         ↓
        采集 → 标准化 → 评分 → 去重 → 故事合并
                         ↓
             测试 + 数据完整性/新鲜度校验
                         ↓
                _site/ Pages Artifact
                         ↓
              actions/deploy-pages 显式发布
```

`.github/workflows/update-news.yml` 的 cron 为 `*/30 * * * *`，即计划任务每 30 分钟触发一次。GitHub 对计划任务可能存在排队延迟，实际开始时间不保证精确到分钟。也可在 Actions 页面手动运行。

定时任务只在临时 Runner 中生成快照，不再将每轮 `data/*.json` 提交回 `main`。`main` 保持为代码、配置、测试与本地回退数据分支，线上站点由经过校验的 Pages Artifact 发布。

## 快速开始

Linux / macOS：

```bash
git clone https://github.com/xavier9802/medical-news-radar.git
cd medical-news-radar
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scripts/update_news.py --output-dir data --window-hours 24
python scripts/build_source_registry.py
python scripts/validate_deployment.py --site-root .
python -m http.server 8080
```

Windows PowerShell：

```powershell
git clone https://github.com/xavier9802/medical-news-radar.git
Set-Location medical-news-radar
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python scripts/update_news.py --output-dir data --window-hours 24
python scripts/build_source_registry.py
python scripts/validate_deployment.py --site-root .
python -m http.server 8080
```

打开 `http://localhost:8080/`，信源页为 `http://localhost:8080/sources.html`。

## 配置目录

| 文件 | 用途 |
| --- | --- |
| `config/categories.yml` | 八大栏目、显示名、说明和顺序 |
| `config/keywords.yml` | 中英文强/中/噪声关键词、权重和栏目映射 |
| `config/scoring.yml` | 评分权重、阈值和加分项 |
| `config/source-tiers.yml` | S/A/B/C 等级与权威分 |
| `config/sources.yml` | 公开信源、抓取策略、过滤条件和元数据 |

配置缺失或无法解析时，加载器会返回安全默认值；单一来源失败不会让整轮任务或网站失效。字段定义见 [docs/source-schema.md](docs/source-schema.md)。

## 添加和检测信源

普通用户可在 `/sources.html` 点击“推荐新信源”，提交 GitHub Issue Form。Issue 不会自动修改 `config/sources.yml`、创建 PR 或合并代码；维护者检测并核验后，再手动编辑 `config/sources.yml`。

本地检测单个公开地址：

```bash
python scripts/source_probe.py --url "https://example.com/feed.xml" --name "示例信源"
python scripts/source_probe.py --url "https://example.com/feed.xml" --output data/source-probe-result.json
```

检测配置中的已启用信源：

```bash
python scripts/source_probe.py --config config/sources.yml --output data/source-probe-result.json
```

在 GitHub 仓库进入 **Actions → Check Medical News Source → Run workflow**，填写公开 HTTP(S) 地址即可手动运行 `source-check.yml`。外部 Issue 只做结构检查；只有仓库所有者、成员或协作者的结构化提交才会触发网络探测。

详细维护流程见 [docs/source-management.md](docs/source-management.md)。

## 私有 OPML、Secrets 与 Variables

公开示例位于 `feeds/follow.example.opml`，仅用于本地演示。个人订阅应复制到被 Git 忽略的 `feeds/follow.opml`，不要提交到仓库：

```bash
python scripts/update_news.py --output-dir data --window-hours 24 --rss-opml feeds/follow.opml
```

生产工作流只有在配置 `FOLLOW_OPML_B64` 时才启用 OPML；未配置时不会自动加载公开示例。

| 名称 | 类型 | 必需 | 作用 |
| --- | --- | --- | --- |
| `FOLLOW_OPML_B64` | Secret | 否 | 私有 OPML 的 Base64 内容；未设置时关闭 OPML 采集 |
| `RSS_MAX_FEEDS` | Variable | 否 | 限制每轮 OPML feed 数，默认 10 |
| `DEEPSEEK_API_KEY` | Secret | 否 | 可选 Persona 排序增强 |
| `DEEPSEEK_PERSONA_ENABLED` | Variable | 否 | 设为 `1` 才启用 DeepSeek Persona 排序，默认 `0` |
| `DEEPSEEK_PERSONA_MODEL` | Variable | 否 | Persona 排序模型，默认 `deepseek-v4-flash` |

PowerShell 生成 OPML Base64：

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("feeds/follow.opml")) | Set-Clipboard
```

Linux / macOS：

```bash
base64 < feeds/follow.opml
```

将 Secret 和 Variable 保存到 **Settings → Secrets and variables → Actions**。不要把密钥、Cookie、Token、私有 OPML 或邮件正文写入配置、Issue、日志或前端。

## 数据产物

- `data/latest-24h.json`：24 小时医疗强相关内容
- `data/latest-24h-all.json`：24 小时全量内容
- `data/source-status.json`：本轮来源抓取状态
- `data/source-registry.json`：信源配置与健康状态合并结果
- `data/daily-brief.json`：精选故事线
- `data/stories-merged.json`：多来源合并后的事件
- `data/merge-log.json`：合并审计信息
- `data/archive.json`：有限期历史归档

## GitHub Pages 部署

1. 在 **Settings → Pages → Build and deployment** 中将 Source 选择为 **GitHub Actions**，不要再选择 `main / (root)` 分支发布。
2. 按需配置 `FOLLOW_OPML_B64`、`RSS_MAX_FEEDS` 和 DeepSeek 相关 Secret/Variables。
3. 在 **Actions → Update and Deploy Medical News Radar** 手动运行一次。
4. 工作流会依次执行采集、注册表生成、Python/Node 测试、数据完整性与新鲜度校验、Pages Artifact 上传和显式部署。
5. 打开 `https://<你的账号>.github.io/medical-news-radar/` 和 `/sources.html` 验收。

发布门禁会在以下情况阻止覆盖线上版本：必需文件缺失、JSON 无法解析、条目计数不一致、快照超过 6 小时、引用的数据文件不存在，或所有内置信源组均失败。

## 测试

```bash
python -m pytest -q
python -m compileall -q scripts
node --test tests/js/*.test.cjs
node --check assets/runtime-config.js
node --check assets/app.js
node --check assets/sources.js
python scripts/build_source_registry.py
python scripts/validate_deployment.py --site-root .
```

单元测试使用 mock，不依赖真实外网。`.github/workflows/ci.yml` 会在 Pull Request 和 `main` 代码变更时执行测试与静态回退快照结构校验；定时发布工作流会在每次部署前重新执行完整门禁。

## 安全与内容边界

- 只采集无需登录的公开 HTTP/HTTPS 来源，不绕过验证码、付费墙或访问控制。
- 探测器阻止 localhost、私网、链路本地和保留地址，并对每次重定向重新校验。
- 不执行目标网页 JavaScript，不发送 Cookie，不保存第三方完整正文。
- 页面只展示标题、来源、时间、原文链接、摘要/推荐理由、分类和多源关系。
- 不将资讯改写为诊疗建议；不虚构政策、临床结论、融资金额或 FDA/NMPA 审批。
- Persona 输出是编辑辅助，不是医疗建议；事实不确定时必须回到官方原文核验。
- 定时生成任务使用只读仓库权限；只有独立部署 Job 获得 `pages: write` 与 `id-token: write`。

## 来源与许可证

本项目基于 [LearnPrompt/ai-news-radar](https://github.com/LearnPrompt/ai-news-radar) 改造，保留轻量抓取管线和 GitHub Pages 架构。项目继续采用 [MIT License](LICENSE)。
