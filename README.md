# Medical News Radar｜24 小时医疗情报雷达

自动更新的 24 小时医疗健康情报雷达。

- **普通读者**：直接打开网页，看最近 24 小时医疗、公共卫生、临床研究、监管政策和行业动态。
- **开发者/机构**：fork 本仓库，接入自己的医学 RSS/OPML、期刊 feed、公开 API，部署为独立的医疗情报站点。
- **Agent 用户**：可通过项目内置 Skill 继续维护信源、判断新来源质量、部署 GitHub Pages。

## 快速开始

普通用户不用安装，直接打开在线页面即可（部署后替换为你的 GitHub Pages 地址）。

本地运行：

```bash
git clone https://github.com/xavier9802/medical-news-radar.git
cd medical-news-radar
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/update_news.py --output-dir data --window-hours 24
python -m http.server 8080
```

打开 http://localhost:8080

## 数据源

默认内置公开医疗源（RSS/Atom）：

- **官方/监管机构**：WHO、CDC、FDA、NIH 等
- **医学期刊**：NEJM、The Lancet、JAMA、BMJ 等
- **医疗媒体**：Medscape、Healthcare IT News、HIMSS 等
- **中文医疗媒体**：通过 `feeds/follow.example.opml` 示例接入

需要添加私有源时：

```bash
cp feeds/follow.example.opml feeds/follow.opml
# 编辑 feeds/follow.opml 加入你的医学 RSS
python scripts/update_news.py --output-dir data --window-hours 24 --rss-opml feeds/follow.opml
```

## 核心机制

1. **信源判断**：优先接入官方机构、权威期刊、可信媒体；避免养生偏方、电商促销等噪音。
2. **抓取与结构化**：RSS/Atom/OPML + 可选公开 API。
3. **医疗相关性评分**：基于标题、来源、关键词判断是否为高价值医疗信号。
4. **去重与故事线合并**：同一事件多个来源聚合成一个故事线。
5. **静态页面发布**：GitHub Actions 自动生成 `data/*.json` 并发布到 GitHub Pages。

## 数据产物

- `data/latest-24h.json`：最近 24 小时医疗强相关消息
- `data/latest-24h-all.json`：最近 24 小时全量消息
- `data/source-status.json`：来源抓取状态与健康度
- `data/daily-brief.json`：精选故事线 / Top 3
- `data/stories-merged.json`：合并后的完整事件集合
- `data/merge-log.json`：合并审计日志

## GitHub Actions 自动更新

`.github/workflows/update-news.yml` 已配置：

- 默认每 30 分钟运行一次
- 自动生成并提交 `data/*.json`
- 通过 `FOLLOW_OPML_B64` secret 可接入私有 OPML

### 配置私有 OPML

```bash
base64 -i feeds/follow.opml | pbcopy  # 复制到剪贴板
# 在 GitHub 仓库 Settings > Secrets and variables > Actions 中新建 FOLLOW_OPML_B64
```

## 项目结构

```
medical-news-radar/
├── scripts/
│   ├── update_news.py          # 主抓取与数据生成
│   ├── medical_relevance.py    # 医疗相关性评分
│   └── ...
├── assets/
│   ├── app.js                  # 前端逻辑
│   └── styles.css              # 样式
├── feeds/
│   └── follow.example.opml     # OPML 示例
├── index.html                  # 主页面
├── data/                       # 生成的 JSON（自动提交）
└── tests/                      # 测试
```

## 测试

```bash
python -m py_compile scripts/update_news.py
pytest -q
node --check assets/app.js
```

## 从 AI News Radar 改造而来

本项目基于 [LearnPrompt/ai-news-radar](https://github.com/LearnPrompt/ai-news-radar) 改造，保留其轻量化 pipeline 与 GitHub Pages 部署架构，将主题全面切换为医疗健康。

## License

MIT
