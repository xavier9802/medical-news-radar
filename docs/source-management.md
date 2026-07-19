# 信源管理指南

Medical News Radar 使用配置文件和 Git 历史管理信源，不提供数据库后台。`/sources.html` 是只读状态页；“推荐新信源”会打开 GitHub Issue Form，最终接入仍由维护者审核并修改 `config/sources.yml`。

## 添加信源

1. 收集名称、主页、feed/API 地址、建议栏目、更新频率和推荐理由。
2. 优先寻找官方 RSS/Atom；其次是稳定公开 JSON 或无需登录的列表页。
3. 运行安全探测，核对状态码、内容类型、条目、时间、登录/拦截信号和更新新鲜度。
4. 人工核验来源身份、内容质量、版权边界、栏目和 S/A/B/C 等级。
5. 将来源加入 `config/sources.yml`，运行数据生成、注册表生成和测试。
6. 检查 `/sources.html` 和首页，不应因为新来源失败而影响其他内容。

也可在仓库 **Issues → New issue → 推荐新信源** 提交。Issue 不会自动写配置、创建 PR 或合并。

## 运行检测

单个来源：

```bash
python scripts/source_probe.py --url "https://example.com/feed.xml" --name "示例信源"
python scripts/source_probe.py --url "https://example.com/feed.xml" --output data/source-probe-result.json
```

配置中的已启用来源：

```bash
python scripts/source_probe.py --config config/sources.yml --output data/source-probe-result.json
```

GitHub 手动检测：进入 **Actions → Check Medical News Source → Run workflow**，填写公开 HTTP(S) URL、名称和栏目。结果作为 7 天 artifact 保存，并在 Job Summary 展示摘要。

`source-check.yml` 使用 `contents: read`、`issues: read`。普通外部 Issue 只做结构检查，不触发任意 URL 网络访问；所有者、成员、协作者的结构化提交才执行探测。

## 是否接入

建议接入：

- 官方、权威、可核验，并能覆盖八大栏目中的明确需求
- HTTP(S) 公开可访问，无登录、验证码、Cookie 或付费墙
- 有标题、发布时间、原文链接和稳定更新
- feed/API 结构稳定，体积和频率适合 GitHub Actions
- 不以营销、转载、养生偏方或未经证实内容为主

暂不接入或设为禁用：

- 探测失败、长期不更新或来源身份无法确认
- 只能通过浏览器登录、Cookie、验证码、动态签名或绕过限制读取
- 只有完整正文而无合理公开摘要/元数据使用方式
- 与已有更权威来源高度重复且没有新增价值

探测成功只是技术条件，不等于自动批准。政策、临床研究、药械审批和融资信息必须人工回到原始出处核验。

## 暂停信源

将对应项设为：

```yaml
enabled: false
```

保留 `id`、地址和 `metadata.notes`，说明暂停原因。重新生成注册表后状态显示 `disabled`，采集器不会把它作为启用的配置源。

## 软删除信源

V1 没有数据库软删除字段。推荐流程：

1. 先设 `enabled: false`，在 `metadata.notes` 记录日期和原因。
2. 至少观察一个维护周期，确认没有依赖和替代需求。
3. 如需彻底移除，再提交单独变更删除配置；Git 历史保留恢复依据。

不要直接改写已生成 JSON 充当删除，下一轮 Actions 会重新生成。

## 为什么不直接抓微信公众号

微信公众号正文通常涉及登录/访问控制、动态页面、版权和不稳定桥接。V1 不绕过限制，也不保存第三方完整正文。可优先使用机构官网、公开 RSS、政策原文或经维护者接受风险的观察链接。

## 为什么不支持需要登录的来源

公共 GitHub Actions 不适合保存浏览器会话和 Cookie。登录源会增加泄密、账号封禁、服务条款、稳定性和复现风险，也会让 fork 用户无法直接运行。因此公共默认源必须无需登录；私有扩展也不得把凭据写入仓库或前端。

## 故障处理

- `config/sources.yml` 缺失/损坏：修复 YAML；主流程使用安全回退，不应让全部旧源失效。
- 单一 feed 失败：查看 `data/source-status.json`，保持其他源继续运行。
- 注册表缺失：运行 `python scripts/build_source_registry.py`；前端会显示“信源状态暂不可用”。
- DeepSeek 未配置/失败：保持 `DEEPSEEK_PERSONA_ENABLED` 关闭，使用确定性 Persona 评分。
- 政府站 403/超时：不要绕过，先暂停或寻找该机构的官方公开 feed。
