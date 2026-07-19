# 医疗雷达 Skill

一个只读 Medical News Radar 公开静态 JSON 的简报 Skill。它适合回答“过去 24 小时医疗行业有什么值得关注”“医保政策有什么变化”“医疗 AI、基层医疗、医疗信息化最近有什么”等问题。

## 特点

- 零 API Key、零登录、零写操作
- 默认读取 GitHub Pages 上的 `data/latest-24h.json`
- 支持八大医疗栏目、多来源故事、日报和信源健康
- 每条保留原始来源链接，并明确标注数据时间
- 数据过期、类别为空或网络失败时如实说明，不编造内容

## 使用

安装到支持 Agent Skill 的工具后，可直接说：

```text
请用医疗雷达整理过去 24 小时最重要的医疗行业情报，按八大栏目分组，每条带原文链接。
```

默认数据地址：

```text
https://xavier9802.github.io/medical-news-radar/data
```

Fork 用户可把地址替换为自己的 GitHub Pages。

## 安全边界

- 只读取公开静态文件，不接收 Token、Cookie 或 API Key
- 不抓取登录页，不绕过付费墙
- 不把新闻改写为诊断或治疗建议
- 不虚构政策、临床结论、药械审批或融资事实
- 当前数据不可用时不使用训练记忆冒充实时新闻

维护信源、运行探测和部署 Pages 请使用相邻的 `skills/medical-news-radar/` 维护 Skill。
