const state = {
  itemsAi: [],
  itemsAll: [],
  itemsAllRaw: [],
  statsAi: [],
  totalAi: 0,
  totalRaw: 0,
  totalAllMode: 0,
  allDedup: true,
  allDataLoaded: false,
  allDataUrl: "data/latest-24h-all.json",
  allDataPromise: null,
  newsDataUrl: "data/latest-24h.json",
  siteFilter: "",
  query: "",
  mode: "ai",
  sourceStatus: null,
  generatedAt: null,
  dailyBrief: null,
  storiesMerged: null,
  storiesDataUrl: "data/stories-merged.json",
  activeSection: "all",
  boleView: "timeline",
  boleExpanded: false,
  listSort: "priority",
  sourceTypeFilter: "",
  signalLevelFilter: "",
  siteGroupsExpanded: false,
};

const runtimeOptions = window.MedicalRadarRuntime?.current
  || window.MedicalRadarRuntime?.parseRuntimeOptions(window.location.href, window.location.origin)
  || { view: "auto", dataUrl: "data/latest-24h.json" };
state.newsDataUrl = runtimeOptions.dataUrl;

function cacheBustedUrl(url) {
  const separator = String(url).includes("?") ? "&" : "?";
  return `${url}${separator}t=${Date.now()}`;
}

const statsEl = document.getElementById("stats");
const siteSelectEl = document.getElementById("siteSelect");
const sitePillsEl = document.getElementById("sitePills");
const newsListEl = document.getElementById("newsList");
const updatedAtEl = document.getElementById("updatedAt");
const sourceStatusPillEl = document.getElementById("sourceStatusPill");
const stickySummaryTextEl = document.getElementById("stickySummaryText");
const searchInputEl = document.getElementById("searchInput");
const resultCountEl = document.getElementById("resultCount");
const listTitleEl = document.getElementById("listTitle");
const itemTpl = document.getElementById("itemTpl");
const modeAiBtnEl = document.getElementById("modeAiBtn");
const modeAllBtnEl = document.getElementById("modeAllBtn");
const modeHintEl = document.getElementById("modeHint");
const allDedupeWrapEl = document.getElementById("allDedupeWrap");
const allDedupeToggleEl = document.getElementById("allDedupeToggle");
const allDedupeLabelEl = document.getElementById("allDedupeLabel");
const advancedSummaryEl = document.getElementById("advancedSummary");
const sourceHealthEl = document.getElementById("sourceHealth");
const sourceHealthDetailsEl = document.getElementById("sourceHealthDetails");
const sourceStatusTableEl = document.getElementById("sourceStatusTable");
const sectionSelectEl = document.getElementById("sectionSelect");
const sourceTypeSelectEl = document.getElementById("sourceTypeSelect");
const signalLevelSelectEl = document.getElementById("signalLevelSelect");

const coverageStripEl = document.getElementById("coverageStrip");
const bolePicksListEl = document.getElementById("bolePicksList");
const bolePicksMetaEl = document.getElementById("bolePicksMeta");
const bolePicksWrapEl = document.getElementById("bolePicksWrap");
const boleViewToggleEl = document.getElementById("boleViewToggle");
const boleHotBtnEl = document.getElementById("boleHotBtn");
const boleTimelineBtnEl = document.getElementById("boleTimelineBtn");
const sectionTabsEl = document.getElementById("sectionTabs");
const sectionSummaryEl = document.getElementById("sectionSummary");
const topStoriesTitleEl = document.getElementById("topStoriesTitle");
const listSortToolsEl = document.getElementById("listSortTools");

const SOURCE_KINDS = {
  official_health: { label: "官方", tone: "official" },
  medical_journals: { label: "医学期刊", tone: "aihub" },
  medical_media: { label: "医疗媒体", tone: "aihub" },
  healthtech_hub: { label: "医疗热点", tone: "hot" },
  opmlrss: { label: "OPML", tone: "newsletter" },
  community: { label: "社区", tone: "community" },
  aggregate: { label: "聚合", tone: "aggregate" },
};

const SECTION_DEFS = [
  { id: "all", label: "全部", short: "全部", description: "过去 24 小时的全部医疗行业信号" },
  { id: "policy", label: "政策监管", short: "政策", description: "医疗政策、监管文件、征求意见、司法案例与行政处罚" },
  { id: "medical_ai", label: "医疗AI", short: "医疗AI", description: "医疗大模型、临床决策支持、AI诊疗、医学影像AI与智能体" },
  { id: "primary_care", label: "基层医疗", short: "基层医疗", description: "诊所、社区卫生、乡镇卫生院、家庭医生与中医馆" },
  { id: "insurance_compliance", label: "医保合规", short: "医保合规", description: "医保支付、飞行检查、基金监管、追溯码与收费合规" },
  { id: "health_it", label: "医疗信息化", short: "信息化", description: "HIS、EMR、电子病历、互联网医院、数据治理与信息安全" },
  { id: "pharma_device", label: "医药器械", short: "医药器械", description: "药品、医疗器械、临床试验、审评审批与药品追溯" },
  { id: "company_market", label: "企业动态", short: "企业", description: "融资、并购、企业合作、产品发布、经营数据与行业竞争" },
  { id: "global_healthtech", label: "海外前沿", short: "海外", description: "海外医疗科技、数字疗法、远程医疗、国际医疗AI与监管" },
];

const SECTION_BY_ID = Object.fromEntries(SECTION_DEFS.map((section) => [section.id, section]));

const LIST_SORT_DEFS = [
  { id: "priority", label: "综合" },
  { id: "latest", label: "最新" },
  { id: "ai", label: "高分" },
  { id: "source", label: "来源" },
];

function fmtNumber(n) {
  return new Intl.NumberFormat("zh-CN").format(n || 0);
}

function fmtTime(iso) {
  if (!iso) return "时间未知";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

function fmtDate(iso) {
  if (!iso) return "未知日期";
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

function setStats() {
  statsEl.innerHTML = "";
  const items = state.itemsAi || [];
  const highCount = items.filter((item) => isHighPriorityItem(item)).length;
  const curatedCount = briefStories().length || Math.min(20, mergedStories().filter((story) => storyScore(story) >= 75).length);
  const status = state.sourceStatus;
  const totalSites = Array.isArray(status?.sites) ? status.sites.length : 0;
  const okSites = Number(status?.successful_sites || 0);
  const health = totalSites ? `${fmtNumber(okSites)}/${fmtNumber(totalSites)}正常` : "加载中";
  const cards = [
    ["医疗", `${fmtNumber(state.totalAi || items.length)}条`],
    ["高优", `${fmtNumber(highCount)}条`],
    ["精选", `${fmtNumber(curatedCount)}条`],
    ["源", health],
  ];
  statsEl.setAttribute(
    "aria-label",
    `过去 24 小时：医疗信号 ${fmtNumber(state.totalAi || items.length)} 条，高优先级 ${fmtNumber(highCount)} 条，精选 ${fmtNumber(curatedCount)} 条，源状态 ${totalSites ? `${fmtNumber(okSites)}/${fmtNumber(totalSites)} 源正常` : "加载中"}`,
  );

  const prefix = document.createElement("div");
  prefix.className = "stat-prefix";
  prefix.textContent = "过去 24 小时：";
  statsEl.appendChild(prefix);

  cards.forEach(([k, v]) => {
    const node = document.createElement("div");
    node.className = "stat";
    node.innerHTML = `<div class="k">${k}</div><div class="v">${v}</div>`;
    statsEl.appendChild(node);
  });
  renderStickySummary();
  renderSourceStatusPill();
}

function failedSourceCount(status = state.sourceStatus) {
  const failedSites = Array.isArray(status?.failed_sites) ? status.failed_sites.length : 0;
  const rss = status?.rss_opml || {};
  const failedFeeds = Array.isArray(rss.failed_feeds) ? rss.failed_feeds.length : 0;
  return failedSites + failedFeeds;
}

function renderSourceStatusPill(errorMessage = "") {
  if (!sourceStatusPillEl) return;
  const status = state.sourceStatus;
  sourceStatusPillEl.className = "source-status-pill";
  if (!status) {
    sourceStatusPillEl.textContent = errorMessage || "源状态加载中";
    if (errorMessage) sourceStatusPillEl.classList.add("bad");
    return;
  }
  const totalSites = Array.isArray(status.sites) ? status.sites.length : 0;
  const okSites = Number(status.successful_sites || 0);
  const failed = failedSourceCount(status);
  sourceStatusPillEl.textContent = failed
    ? `${fmtNumber(okSites)}/${fmtNumber(totalSites)} 源正常 · 失败 ${fmtNumber(failed)}`
    : `${fmtNumber(okSites)}/${fmtNumber(totalSites)} 源正常`;
  if (failed) sourceStatusPillEl.classList.add("warn");
}

function renderStickySummary() {
  if (!stickySummaryTextEl) return;
  const filteredCount = getFilteredItems().length;
  const section = SECTION_BY_ID[state.activeSection] || SECTION_BY_ID.all;
  const query = state.query.trim();
  const site = state.siteFilter
    ? (currentSiteStats().find((row) => row.site_id === state.siteFilter)?.site_name || state.siteFilter)
    : "";
  const sourceType = sourceTypeSelectEl?.selectedOptions?.[0]?.textContent || "";
  const signalLevel = signalLevelSelectEl?.selectedOptions?.[0]?.textContent || "";
  const filters = [
    state.activeSection === "all" ? "" : section.label,
    site,
    state.sourceTypeFilter ? sourceType : "",
    state.signalLevelFilter ? signalLevel : "",
    query ? `搜索“${query}”` : "",
  ].filter(Boolean);
  const mode = state.mode === "all" ? "全量" : "医疗强相关";
  stickySummaryTextEl.textContent = `${fmtNumber(filteredCount)} 条 · ${mode}${filters.length ? ` · ${filters.join(" · ")}` : ""}`;
}

function sourceKind(siteId) {
  return SOURCE_KINDS[siteId] || { label: "来源", tone: "default" };
}

function sourceSignalTone(signal) {
  const text = String(signal || "").toLowerCase();
  if (text.includes("官方") || text.includes("official")) return "official";
  if (text.includes("热点") || text.includes("精选")) return "hot";
  if (text.includes("期刊") || text.includes("媒体")) return "aihub";
  if (text.includes("社区")) return "community";
  if (text.includes("opml") || text.includes("rss") || text.includes("订阅")) return "newsletter";
  if (text.includes("聚合")) return "aggregate";
  return "default";
}

function sourceChip(label, tone = "default", className = "source-chip") {
  const chip = document.createElement("span");
  chip.className = `${className} kind-${tone}`.trim();
  const dot = document.createElement("span");
  dot.className = "source-dot";
  dot.setAttribute("aria-hidden", "true");
  const text = document.createElement("span");
  text.className = "source-chip-label";
  text.textContent = label || "来源";
  chip.append(dot, text);
  return chip;
}

function appendSourceChip(parent, label, tone = "default", className = "source-chip") {
  parent.appendChild(sourceChip(label, tone, className));
}

function siteRows() {
  return Array.isArray(state.sourceStatus?.sites) ? state.sourceStatus.sites : [];
}

function siteRow(siteId) {
  return siteRows().find((site) => site.site_id === siteId) || null;
}

function aiSiteStat(siteId) {
  const stats = Array.isArray(state.statsAi) && state.statsAi.length
    ? state.statsAi
    : computeSiteStats(state.itemsAi || []);
  return stats.find((site) => site.site_id === siteId) || null;
}

function siteAiPoolCount(siteId) {
  return Number(aiSiteStat(siteId)?.count || 0);
}

function siteRawPoolCount(siteId) {
  const stat = aiSiteStat(siteId);
  return Number(stat?.raw_count ?? stat?.count ?? 0);
}

function sourcePoolMeta(aiCount, rawCount, fallback) {
  if (rawCount && rawCount !== aiCount) return `医疗强相关 · 原始 ${fmtNumber(rawCount)} 条`;
  return fallback;
}

function paidSourceLabel(status, poolCount, activeLabel, idleLabel) {
  const connected = Boolean(status?.enabled);
  const liveCount = Number(status?.item_count || 0);
  const displayCount = liveCount || Number(poolCount || 0);
  if (connected) {
    if (displayCount) return `${activeLabel} ${fmtNumber(displayCount)}条`;
    return `${activeLabel} ${status?.skipped ? "待窗口" : "已连接暂无匹配"}`;
  }
  if (displayCount) return `${activeLabel} ${fmtNumber(displayCount)}条`;
  return idleLabel;
}

function renderCoverageCard(label, value, meta, tone = "") {
  const node = document.createElement("div");
  node.className = `coverage-card ${tone}`.trim();
  const labelEl = document.createElement("span");
  labelEl.className = "coverage-label";
  labelEl.textContent = label;
  const valueEl = document.createElement("strong");
  valueEl.textContent = value;
  const metaEl = document.createElement("span");
  metaEl.className = "coverage-meta";
  metaEl.textContent = meta;
  node.append(labelEl, valueEl, metaEl);
  return node;
}

function renderCoverageStrip(errorMessage = "") {
  if (!coverageStripEl) return;
  coverageStripEl.innerHTML = "";

  const rows = siteRows();
  const failedSites = Array.isArray(state.sourceStatus?.failed_sites) ? state.sourceStatus.failed_sites : [];
  const rss = state.sourceStatus?.rss_opml || {};
  const allCount = Number(state.sourceStatus?.items_before_topic_filter || state.totalAllMode || state.itemsAll.length || 0);
  const coverageCount = Number(state.sourceStatus?.fetched_raw_items || state.totalRaw || allCount || 0);
  const officialCount = Number(siteRow("official_health")?.item_count || 0);
  const journalCount = Number(siteRow("medical_journals")?.item_count || 0);
  const mediaCount = Number(siteRow("medical_media")?.item_count || 0);
  const hubCount = Number(siteRow("healthtech_hub")?.item_count || 0);
  const communityCount = Number(siteRow("community")?.item_count || 0);
  const totalSites = rows.length;
  const okSites = Number(state.sourceStatus?.successful_sites || 0);
  const opmlValue = rss.enabled ? `${fmtNumber(rss.ok_feeds || 0)}/${fmtNumber(rss.effective_feed_total || 0)}` : "OPML";
  const opmlMeta = rss.enabled ? "RSS / 自定义订阅已接入" : "可用 OPML 批量接入 RSS";

  const cards = [
    ["源健康", totalSites ? `${fmtNumber(okSites)}/${fmtNumber(totalSites)}` : "加载中", failedSites.length ? `${fmtNumber(failedSites.length)} 个失败源` : (errorMessage || "内置源正常"), failedSites.length ? "warn" : "ok"],
    ["今日覆盖池", `${fmtNumber(coverageCount)} 条`, allCount ? `全网抓取原始信号 · ${fmtNumber(allCount)} 条入池` : "全网抓取原始信号", "signal"],
    ["医疗强相关", `${fmtNumber(state.totalAi)} 条`, "24小时强相关信号", "signal"],
    ["官方/监管机构", `${fmtNumber(officialCount)} 条`, "WHO / FDA / NMPA 等官方节点", "official"],
    ["期刊/媒体源池", `${fmtNumber(journalCount + mediaCount)} 条`, "医学期刊与医疗媒体", "aihub"],
    ["医疗热点源池", `${fmtNumber(hubCount)} 条`, "HealthTech 热点聚合", "hot"],
    ["社区/OPML扩展", `${fmtNumber(communityCount)} 条 · ${opmlValue}`, opmlMeta, "community"],
  ];

  cards.forEach(([label, value, meta, tone]) => {
    coverageStripEl.appendChild(renderCoverageCard(label, value, meta, tone));
  });
}

function renderAdvancedSummary() {
  if (!advancedSummaryEl) return;
  const status = state.sourceStatus;
  const filteredCount = getFilteredItems().length;
  if (!status) {
    advancedSummaryEl.textContent = `${fmtNumber(filteredCount)} 条结果`;
    return;
  }
  const sites = Array.isArray(status.sites) ? status.sites : [];
  const totalSites = sites.length;
  const okSites = Number(status.successful_sites || 0);
  const failed = failedSourceCount(status);
  advancedSummaryEl.textContent = `${fmtNumber(filteredCount)} 条结果 · ${fmtNumber(okSites)}/${fmtNumber(totalSites)} 源正常${failed ? ` · 失败 ${fmtNumber(failed)}` : ""}`;
}

function computeSiteStats(items) {
  const m = new Map();
  items.forEach((item) => {
    if (!m.has(item.site_id)) {
      m.set(item.site_id, { site_id: item.site_id, site_name: item.site_name, count: 0, raw_count: 0 });
    }
    const row = m.get(item.site_id);
    row.count += 1;
    row.raw_count += 1;
  });
  return Array.from(m.values()).sort((a, b) => b.count - a.count || a.site_name.localeCompare(b.site_name, "zh-CN"));
}

function currentSiteStats() {
  if (state.mode === "ai") return state.statsAi || [];
  return computeSiteStats(state.allDedup ? (state.itemsAll || []) : (state.itemsAllRaw || []));
}

function isHighPriorityItem(item) {
  return scorePercent(item) >= 75 || itemPriorityScore(item) >= 82 || item.site_id === "official_health" || item.site_id === "healthtech_hub";
}

function isCuratedItem(item) {
  return item.site_id === "official_health" || item.site_id === "healthtech_hub" || ["s", "a", "official", "curated"].includes(item.source_tier);
}

function itemSourceType(item) {
  const siteId = item.site_id || "";
  const tier = item.source_tier || "";
  if (siteId === "official_health" || tier === "official" || tier === "s") return "official";
  if (siteId === "medical_journals" || siteId === "medical_media") return "media";
  if (siteId === "healthtech_hub") return "hot";
  if (siteId === "opmlrss" || tier === "user_opml") return "rss";
  if (siteId === "community") return "community";
  return "aggregate";
}

function multiSourceEventKeys(items) {
  const map = new Map();
  (items || []).forEach((item) => {
    const key = eventKey(item);
    if (!map.has(key)) map.set(key, new Set());
    map.get(key).add(sourceSignal(item));
  });
  return new Set(Array.from(map.entries())
    .filter(([, sources]) => sources.size > 1)
    .map(([key]) => key));
}

function itemMatchesSignalLevel(item, multiSourceKeys = new Set()) {
  if (!state.signalLevelFilter) return true;
  if (state.signalLevelFilter === "high") return isHighPriorityItem(item);
  if (state.signalLevelFilter === "curated") return isCuratedItem(item);
  if (state.signalLevelFilter === "multi") return multiSourceKeys.has(eventKey(item));
  return true;
}

function sectionStats(sectionId) {
  const items = sectionItems(modeItems(), sectionId);
  const highCount = items.filter((item) => isHighPriorityItem(item)).length;
  const sourceSet = new Set(items.map((item) => item.source || item.site_name || item.site_id).filter(Boolean));
  return { items, count: items.length, highCount, sourceCount: sourceSet.size };
}

function renderSectionTabs() {
  if (!sectionTabsEl) return;
  sectionTabsEl.innerHTML = "";
  SECTION_DEFS.forEach((section) => {
    const stats = sectionStats(section.id);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `section-tab ${state.activeSection === section.id ? "active" : ""}`;
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", state.activeSection === section.id ? "true" : "false");
    btn.dataset.section = section.id;
    btn.innerHTML = `<span>${section.label}</span><strong>${fmtNumber(stats.count)}</strong>`;
    btn.addEventListener("click", () => {
      state.activeSection = section.id;
      state.boleExpanded = false;
      renderSectionTabs();
      renderModeSwitch();
      renderSiteFilters();
      renderBolePicks();
      renderList();
    });
    sectionTabsEl.appendChild(btn);
  });
  renderSectionFilterSelect();
}

function renderSectionFilterSelect() {
  if (!sectionSelectEl) return;
  if (!sectionSelectEl.options.length) {
    SECTION_DEFS.forEach((section) => {
      const option = document.createElement("option");
      option.value = section.id;
      option.textContent = section.label;
      sectionSelectEl.appendChild(option);
    });
  }
  sectionSelectEl.value = state.activeSection;
}

function renderSectionSummary(filteredItems = null) {
  if (!sectionSummaryEl) return;
  const section = SECTION_BY_ID[state.activeSection] || SECTION_BY_ID.all;
  const items = filteredItems || getFilteredItems();
  const highCount = items.filter((item) => isHighPriorityItem(item)).length;
  const sources = new Set(items.map((item) => item.source || item.site_name || item.site_id).filter(Boolean));
  const modeText = state.mode === "all" ? (state.allDedup ? "全量去重" : "全量原始") : "医疗强相关";
  sectionSummaryEl.textContent = `过去 24 小时 · ${fmtNumber(items.length)} 条${section.id === "all" ? "" : ` ${section.label}`}信号 · ${fmtNumber(highCount)} 条高优先级 · ${fmtNumber(sources.size)} 个来源 · ${modeText}`;
  renderStickySummary();
}

function siteRatioText(siteStats) {
  const count = Number(siteStats.count || 0);
  const raw = Number(siteStats.raw_count ?? siteStats.count ?? 0);
  if (!raw) {
    const scanned = Number(siteRow(siteStats.site_id)?.item_count || 0);
    if (!count && scanned) return `24h 0 · 已扫 ${fmtNumber(scanned)}`;
    if (!count) return "已扫 0";
    return `${fmtNumber(count)} 条`;
  }
  if (raw === count) return `${fmtNumber(count)} 条`;
  return `${fmtNumber(count)}/${fmtNumber(raw)} · ${Math.round((count / raw) * 100)}%医疗`;
}

function renderSiteFilters() {
  const stats = currentSiteStats();

  siteSelectEl.innerHTML = '<option value="">全部站点</option>';
  stats.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.site_id;
    opt.textContent = `${s.site_name} (${siteRatioText(s)})`;
    siteSelectEl.appendChild(opt);
  });
  siteSelectEl.value = state.siteFilter;

  sitePillsEl.innerHTML = "";
  const allPill = document.createElement("button");
  allPill.className = `pill ${state.siteFilter === "" ? "active" : ""}`;
  allPill.textContent = "全部";
  allPill.onclick = () => {
    state.siteFilter = "";
    renderSiteFilters();
    renderBolePicks();
    renderList();
  };
  sitePillsEl.appendChild(allPill);

  stats.forEach((s) => {
    const btn = document.createElement("button");
    btn.className = `pill ${state.siteFilter === s.site_id ? "active" : ""}`;
    btn.textContent = `${s.site_name} ${siteRatioText(s)}`;
    btn.onclick = () => {
      state.siteFilter = s.site_id;
      renderSiteFilters();
      renderBolePicks();
      renderList();
    };
    sitePillsEl.appendChild(btn);
  });
}

function renderModeSwitch() {
  modeAiBtnEl.classList.toggle("active", state.mode === "ai");
  modeAllBtnEl.classList.toggle("active", state.mode === "all");
  if (allDedupeWrapEl) allDedupeWrapEl.classList.toggle("show", state.mode === "all");
  if (allDedupeToggleEl) allDedupeToggleEl.checked = state.allDedup;
  if (allDedupeLabelEl) allDedupeLabelEl.textContent = state.allDedup ? "去重开" : "去重关";
  if (state.mode === "ai") {
    modeHintEl.textContent = `医疗强相关 · ${fmtNumber(state.totalAi)} 条`;
  } else {
    const allCount = state.allDedup
      ? (state.totalAllMode || state.itemsAll.length)
      : (state.totalRaw || state.itemsAllRaw.length);
    modeHintEl.textContent = `全量 · ${state.allDedup ? "去重开" : "去重关"} · ${fmtNumber(allCount)} 条`;
  }
  if (listTitleEl) {
    listTitleEl.textContent = listTitleText();
  }
  renderAdvancedSummary();
  renderSectionSummary();
}

function listTitleText() {
  const section = SECTION_BY_ID[state.activeSection] || SECTION_BY_ID.all;
  const pool = state.mode === "all"
    ? (state.allDedup ? "情报流 · 全量去重" : "情报流 · 全量原始")
    : "情报流";
  return state.activeSection === "all" ? pool : `${section.label} · ${pool}`;
}

function renderListSortTools() {
  if (!listSortToolsEl) return;
  const validSort = LIST_SORT_DEFS.some((item) => item.id === state.listSort);
  if (!validSort) state.listSort = "priority";
  listSortToolsEl.querySelectorAll("[data-sort]").forEach((button) => {
    const active = button.dataset.sort === state.listSort;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function itemSourceSortKey(item) {
  return [
    sourceSignal(item),
    item.site_name || item.site_id || "",
    item.source || "",
  ].join(" ").trim() || "来源";
}

function sortItemsForList(items) {
  const sorted = [...items];
  if (state.listSort === "latest") {
    return sorted.sort((a, b) => timelineMs(b) - timelineMs(a) || itemPriorityScore(b) - itemPriorityScore(a));
  }
  if (state.listSort === "ai") {
    return sorted.sort((a, b) => scorePercent(b) - scorePercent(a) || itemPriorityScore(b) - itemPriorityScore(a) || timelineMs(b) - timelineMs(a));
  }
  if (state.listSort === "source") {
    const counts = new Map();
    sorted.forEach((item) => {
      const key = itemSourceSortKey(item);
      counts.set(key, (counts.get(key) || 0) + 1);
    });
    return sorted.sort((a, b) => {
      const aKey = itemSourceSortKey(a);
      const bKey = itemSourceSortKey(b);
      const byCount = (counts.get(bKey) || 0) - (counts.get(aKey) || 0);
      if (byCount !== 0) return byCount;
      const bySource = aKey.localeCompare(bKey, "zh-CN");
      if (bySource !== 0) return bySource;
      return itemPriorityScore(b) - itemPriorityScore(a) || timelineMs(b) - timelineMs(a);
    });
  }
  return sorted.sort((a, b) => itemPriorityScore(b) - itemPriorityScore(a) || timelineMs(b) - timelineMs(a));
}

function effectiveAllItems() {
  return state.allDedup ? state.itemsAll : state.itemsAllRaw;
}

function modeItems() {
  return state.mode === "all" ? effectiveAllItems() : state.itemsAi;
}

function sectionItems(items = modeItems(), sectionId = state.activeSection) {
  const source = Array.isArray(items) ? items : [];
  if (sectionId === "all") {
    return [...source].sort((a, b) => itemPriorityScore(b) - itemPriorityScore(a) || timelineMs(b) - timelineMs(a));
  }
  return source.filter((item) => itemMatchesSection(item, sectionId));
}

function getFilteredItems() {
  const q = state.query.trim().toLowerCase();
  const preliminary = sectionItems().filter((item) => {
    if (state.siteFilter && item.site_id !== state.siteFilter) return false;
    if (state.sourceTypeFilter && itemSourceType(item) !== state.sourceTypeFilter) return false;
    if (!q) return true;
    const hay = `${item.title || ""} ${item.title_zh || ""} ${item.title_en || ""} ${item.site_name || ""} ${item.source || ""}`.toLowerCase();
    return hay.includes(q);
  });
  const multiKeys = multiSourceEventKeys(preliminary);
  return preliminary.filter((item) => itemMatchesSignalLevel(item, multiKeys));
}

function itemTitleText(item) {
  return (item.title_zh || item.title || item.title_en || "未命名更新").trim();
}

function scorePercent(item) {
  const score = Number(item.medical_score ?? item.score ?? 0);
  if (!Number.isFinite(score) || score <= 0) return 0;
  return Math.round(score <= 1 ? score * 100 : score);
}

function normalizedPercent(value) {
  const score = Number(value);
  if (!Number.isFinite(score) || score <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round(score <= 1 ? score * 100 : score)));
}

function scoreTone(score) {
  if (score >= 90) return "hot";
  if (score >= 75) return "strong";
  return "watch";
}

function itemLabelTone(item) {
  const category = Array.from(itemSections(item))[0];
  if (item.is_official || item.site_id === "official_health" || category === "policy") return "official";
  if (category === "medical_ai" || category === "health_it") return "products";
  if (category === "pharma_device") return "strong";
  if (category === "global_healthtech" || category === "primary_care") return "community";
  if (category === "company_market") return "industry";
  return "default";
}

function itemTagTone(label) {
  const text = String(label || "");
  if (text.includes("多源")) return "strong";
  if (text.includes("官方") || text.includes("政策") || text.includes("医保合规")) return "official";
  if (text.includes("精选") || text.includes("热点")) return "hot";
  if (text.includes("医药") || text.includes("器械")) return "strong";
  if (text.includes("医疗AI") || text.includes("信息化")) return "products";
  if (text.includes("基层") || text.includes("海外")) return "community";
  if (text.includes("企业")) return "industry";
  return "default";
}

function itemTagChip(label) {
  const tag = document.createElement("span");
  tag.className = `signal-tag tone-${itemTagTone(label)}`;
  tag.textContent = label;
  return tag;
}

function setSourceBadge(el, label, tone = "default", title = "") {
  el.className = `source source-chip kind-${tone}`;
  el.innerHTML = "";
  if (title) el.title = title;
  const dot = document.createElement("span");
  dot.className = "source-dot";
  dot.setAttribute("aria-hidden", "true");
  const text = document.createElement("span");
  text.className = "source-chip-label";
  text.textContent = label || "来源";
  el.append(dot, text);
}

function sourceTierPercent(item) {
  const configured = { s: 100, a: 82, b: 62, c: 38 };
  const tier = String(item.source_tier || "").toLowerCase();
  if (configured[tier] != null) return configured[tier];
  if (item.site_id === "official_health") return 100;
  if (item.site_id === "healthtech_hub") return 90;
  const rank = Number(item.source_tier_rank);
  if (!Number.isFinite(rank)) return 38;
  return Math.max(28, Math.min(86, 86 - rank * 9));
}

function editorialPercent(item) {
  const hubScore = normalizedPercent(item.curated_score);
  if (hubScore) return hubScore;
  if (item.site_id === "official_health") return 90;
  if (item.site_id === "healthtech_hub") return 78;
  const internal = scorePercent(item);
  return internal ? Math.max(45, Math.round(internal * 0.72)) : 36;
}

function freshnessPercent(item, halfLifeHours = 48) {
  const ageMs = Date.now() - timelineMs(item);
  if (!Number.isFinite(ageMs) || ageMs < 0) return 100;
  const ageHours = ageMs / 3600000;
  return Math.max(0, Math.min(100, Math.round(100 * Math.pow(0.5, ageHours / halfLifeHours))));
}

function itemPriorityScore(item) {
  const internal = scorePercent(item);
  const editorial = editorialPercent(item);
  const source = sourceTierPercent(item);
  const freshness = freshnessPercent(item);
  const signal = Array.isArray(item.medical_signals) ? Math.min(100, item.medical_signals.length * 18) : 0;
  return Math.round((editorial * 0.3) + (source * 0.22) + (internal * 0.2) + (freshness * 0.18) + (signal * 0.1));
}

function labelText(item) {
  const configuredCategory = Array.from(itemSections(item))[0];
  if (item.category_label) return String(item.category_label);
  if (SECTION_BY_ID[configuredCategory]) return SECTION_BY_ID[configuredCategory].label;
  const labels = {
    drug_trial: "药物/临床",
    medical_device: "医疗器械",
    public_health: "公共卫生",
    regulatory_policy: "监管政策",
    hospital_digital: "医院/数字医疗",
    research_paper: "研究论文",
    industry_business: "行业动态",
    ai_healthcare: "医疗 AI",
    health_tech: "医疗科技",
    medical_general: "医疗信号",
    curated_hotlist: "热点精选",
  };
  return labels[item.medical_label] || item.medical_label || "医疗信号";
}

function itemHaystack(item) {
  return [
    item.title,
    item.title_zh,
    item.title_en,
    item.title_original,
    item.source,
    item.site_name,
    item.site_id,
    item.category,
    item.category_label,
    item.medical_label,
    ...(Array.isArray(item.matched_keywords) ? item.matched_keywords : []),
    ...(Array.isArray(item.medical_signals) ? item.medical_signals : []),
  ].filter(Boolean).join(" ").toLowerCase();
}

function matchesAny(text, patterns) {
  return patterns.some((pattern) => pattern.test(text));
}

function itemSections(item) {
  const hay = itemHaystack(item);
  const configuredCategory = String(item.category || "");
  if (configuredCategory !== "all" && SECTION_BY_ID[configuredCategory]) {
    return new Set([configuredCategory]);
  }
  const label = item.medical_label || "";
  if (matchesAny(hay, [/医保基金|医保支付|飞行检查|飞检|基金监管|追溯码|处方合规|收费合规|medical insurance|reimbursement/])) {
    return new Set(["insurance_compliance"]);
  }
  if (label === "regulatory_policy" || matchesAny(hay, [/政策|监管|征求意见|行政处罚|司法案例|regulation|regulatory|guideline|policy/])) {
    return new Set(["policy"]);
  }
  if (label === "ai_healthcare" || matchesAny(hay, [/医疗\s*ai|医疗人工智能|医疗大模型|临床决策支持|辅助诊疗|ai诊疗|医学影像ai|医疗智能体|clinical decision support|medical ai/])) {
    return new Set(["medical_ai"]);
  }
  if (matchesAny(hay, [/基层医疗|家庭医生|社区卫生|乡镇卫生院|中医馆|基层医生|primary care|family doctor|community health/])) {
    return new Set(["primary_care"]);
  }
  if (label === "hospital_digital" || label === "health_tech" || matchesAny(hay, [/his|ehr|emr|电子病历|互联网医院|医院信息化|智慧医院|数据治理|医疗信息安全|telemedicine|health it/])) {
    return new Set(["health_it"]);
  }
  if (["drug_trial", "medical_device", "research_paper"].includes(label) || matchesAny(hay, [/drug|pharma|clinical trial|medical device|fda|nmpa|药品|制药|临床试验|医疗器械|药品追溯|审评|审批|ivd/])) {
    return new Set(["pharma_device"]);
  }
  if (label === "public_health" || matchesAny(hay, [/global health|digital therapeutics|overseas|who|cdc|ema|疫情|疫苗|全球卫生|海外医疗|数字疗法|远程医疗/])) {
    return new Set(["global_healthtech"]);
  }
  if (label === "industry_business" || label === "curated_hotlist" || matchesAny(hay, [/funding|raised|ipo|acquire|acquisition|partnership|融资|并购|收购|企业合作|产品发布|经营数据|估值|投资/])) {
    return new Set(["company_market"]);
  }
  return new Set(["company_market"]);
}

function sourceTierLabel(item) {
  const tier = String(item.source_tier || "").toLowerCase();
  if (["s", "a", "b", "c"].includes(tier)) return `${tier.toUpperCase()}级`;
  if (item.source_tier_label) return String(item.source_tier_label);
  return "";
}
function itemMatchesSection(item, sectionId) {
  return sectionId === "all" || itemSections(item).has(sectionId);
}

function sectionBadgeLabel(sectionId) {
  return SECTION_BY_ID[sectionId]?.short || "栏目";
}

function reasonText(item) {
  if (item.recommendation_reason) return String(item.recommendation_reason);
  const signals = Array.isArray(item.medical_signals) ? item.medical_signals.filter(Boolean).slice(0, 3) : [];
  if (signals.length) return `命中方向：${signals.join(" / ")}`;
  if (item.medical_relevance_reason) return String(item.medical_relevance_reason).replaceAll("_", " ");
  return "来源与标题信号通过筛选";
}

function timelineIso(item) {
  const published = item.published_at || "";
  const seen = item.first_seen_at || "";
  const generated = state.generatedAt || "";
  if (published && generated) {
    const publishedMs = new Date(published).getTime();
    const generatedMs = new Date(generated).getTime();
    if (Number.isFinite(publishedMs) && Number.isFinite(generatedMs) && publishedMs > generatedMs + 10 * 60 * 1000) {
      return seen || published;
    }
  }
  return published || seen;
}

function timelineMs(item) {
  const d = new Date(timelineIso(item));
  return Number.isNaN(d.getTime()) ? 0 : d.getTime();
}

function normalizedEventText(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/https?:\/\/\S+/g, "")
    .replace(/[\s\u3000]+/g, "")
    .replace(/[，。、“”‘’：:；;！!？?（）()\[\]【】《》<>·.,/\\|_-]/g, "");
}

function eventKey(item) {
  const raw = itemTitleText(item);
  const bracket = raw.match(/《([^》]{4,40})》/);
  if (bracket) return `book:${normalizedEventText(bracket[1]).slice(0, 36)}`;

  const normalized = normalizedEventText(raw);
  const model = normalized.match(/(bitcpmcann|deepseekv\d+(?:pro)?|grokv\d+(?:medium)?|gemini\d+(?:\.\d+)?(?:flash|pro)?|gpt\d+(?:\.\d+)?|llama\d+)/);
  if (model) return `entity:${model[1]}`;

  return `title:${normalized.slice(0, 34)}`;
}

function itemIdentityKeys(item) {
  const keys = new Set();
  if (!item) return keys;
  const url = item.url || item.primary_url;
  if (url) keys.add(`url:${url}`);
  if (item.id) keys.add(`id:${item.id}`);
  const title = item.title_zh || item.title || item.title_en || item.title_original;
  if (title) {
    keys.add(`event:${eventKey({ ...item, title, title_zh: item.title_zh || title })}`);
    keys.add(`title:${normalizedEventText(title).slice(0, 34)}`);
  }
  return keys;
}

function storyIdentityKeys(story) {
  const keys = new Set();
  if (!story) return keys;
  const refs = [
    { id: story.story_id, title: story.title, url: story.primary_url || story.url },
    story.primary_item,
    ...(Array.isArray(story.sources) ? story.sources : []),
    ...(Array.isArray(story.items) ? story.items : []),
  ].filter(Boolean);
  refs.forEach((ref) => {
    itemIdentityKeys(ref).forEach((key) => keys.add(key));
  });
  return keys;
}

function headlineRowIdentityKeys(row) {
  const keys = new Set();
  if (!row) return keys;
  const refs = [
    row.item,
    ...(Array.isArray(row.rows) ? row.rows.map((entry) => entry.item).filter(Boolean) : []),
  ].filter(Boolean);
  refs.forEach((ref) => {
    itemIdentityKeys(ref).forEach((key) => keys.add(key));
  });
  return keys;
}

function excludedStoryKeySet(rows) {
  const keys = new Set();
  rows.forEach((row) => {
    headlineRowIdentityKeys(row).forEach((key) => keys.add(key));
  });
  return keys;
}

function storyHasAnyKey(story, keys) {
  if (!keys || !keys.size) return false;
  for (const key of storyIdentityKeys(story)) {
    if (keys.has(key)) return true;
  }
  return false;
}

function sourceSignal(item) {
  const site = item.site_name || "";
  const source = item.source || "";
  const siteId = item.site_id || "";
  if (siteId === "healthtech_hub" || site === "MedHot") return "热点精选";
  if (siteId === "official_health") return "官方更新";
  if (siteId === "medical_journals") return "医学期刊";
  if (siteId === "medical_media") return "医疗媒体";
  if (siteId === "community") return "社区";
  if (siteId === "opmlrss") return "OPML";
  return site || source || "来源";
}

function sourcePriority(item) {
  const type = itemSourceType(item);
  if (type === "official") return 100;
  if (type === "hot") return 90;
  if (type === "media") return 80;
  if (type === "community") return 70;
  if (type === "rss") return 68;
  return 60;
}

function clusterBoleEvents(rows) {
  const clusters = new Map();
  rows.forEach((row) => {
    const key = eventKey(row.item);
    if (!clusters.has(key)) clusters.set(key, { key, rows: [], signals: new Set(), score: 0, primary: row });
    const cluster = clusters.get(key);
    cluster.rows.push(row);
    cluster.signals.add(sourceSignal(row.item));
    const currentPrimary = cluster.primary;
    const betterPrimary = sourcePriority(row.item) - sourcePriority(currentPrimary.item)
      || row.score - currentPrimary.score
      || timelineMs(row.item) - timelineMs(currentPrimary.item);
    if (betterPrimary > 0) cluster.primary = row;
  });
  return Array.from(clusters.values()).map((cluster) => {
    const signals = Array.from(cluster.signals);
    const maxScore = Math.max(...cluster.rows.map((row) => row.score));
    const sourceBonus = Math.min(12, Math.max(0, signals.length - 1) * 6);
    const candidateBonus = signals.some((s) => s === "热点精选") ? 8
      : signals.some((s) => s === "官方更新") ? 5
      : 0;
    return {
      item: cluster.primary.item,
      index: cluster.primary.index,
      rows: cluster.rows,
      sourceSignals: signals,
      sourceCount: signals.length,
      mergedCount: cluster.rows.length,
      score: Math.min(100, Math.round(maxScore + sourceBonus + candidateBonus)),
    };
  });
}

function storyTimeMs(story, key) {
  const iso = story && story[key];
  if (!iso) return 0;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? 0 : d.getTime();
}

function storyScore(story) {
  const raw = (story && (story.importance_score ?? story.score ?? story.importance)) || 0;
  const score = Number(raw);
  if (!Number.isFinite(score) || score <= 0) return 0;
  return Math.round(score <= 1 ? score * 100 : score);
}

function storyImportanceTone(label) {
  if (!label) return "watch";
  if (label.includes("重大")) return "hot";
  if (label.includes("官方")) return "official";
  if (label.includes("多源")) return "strong";
  if (label.includes("行业")) return "watch";
  return "watch";
}

function storyPrimaryTitleText(story) {
  const primary = (story && story.primary_item) || {};
  const bilingual = String(primary.title || (story && story.title) || "").trim();
  if (bilingual.includes(" / ")) {
    const [zh, en] = bilingual.split(" / ");
    return (zh || en || bilingual).trim();
  }
  return bilingual || "未命名更新";
}

function storyPrimaryEnText(story) {
  const primary = (story && story.primary_item) || {};
  const bilingual = String(primary.title || (story && story.title) || "").trim();
  if (bilingual.includes(" / ")) {
    const [, en] = bilingual.split(" / ");
    return (en || "").trim();
  }
  return "";
}

function storySourceCount(story) {
  const sources = Array.isArray(story && story.sources) ? story.sources : [];
  const explicit = Number(story && story.duplicate_count);
  if (Number.isFinite(explicit) && explicit > 0) return explicit;
  return Math.max(1, sources.length);
}

function storyDurationLabel(earliest, latest) {
  if (!earliest || !latest || earliest === latest) return "";
  const start = new Date(earliest).getTime();
  const end = new Date(latest).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end)) return "";
  const minutes = Math.round(Math.abs(end - start) / 60000);
  if (minutes < 20) return "短时集中";
  if (minutes < 60) return `发酵 ${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `发酵 ${hours}小时${rest}分` : `发酵 ${hours}小时`;
}

function formatStoryTime(story) {
  const earliest = story.earliest_at;
  const latest = story.latest_at;
  if (latest && earliest && latest !== earliest) {
    return { latest, rangeLabel: storyDurationLabel(earliest, latest) };
  }
  return { latest: latest || earliest, rangeLabel: "" };
}

function pickBoleItems(items) {
  const ranked = [...items]
    .map((item, index) => ({ item, index, score: scorePercent(item) }))
    .filter((row) => row.score > 0)
    .sort((a, b) => {
      const byScore = b.score - a.score;
      if (byScore !== 0) return byScore;
      return timelineMs(b.item) - timelineMs(a.item) || a.index - b.index;
    });

  const sorted = clusterBoleEvents(ranked).sort((a, b) => {
    const byMultiSource = b.sourceCount - a.sourceCount;
    const byScore = b.score - a.score;
    return byMultiSource || byScore || timelineMs(b.item) - timelineMs(a.item) || a.index - b.index;
  });

  const picked = [];
  const addPick = (cluster) => {
    if (cluster && !picked.includes(cluster) && picked.length < 8) picked.push(cluster);
  };
  ["官方更新", "热点精选", "医学期刊"].forEach((signal) => {
    addPick(sorted.find((cluster) => cluster.sourceSignals.includes(signal)));
  });
  sorted.forEach(addPick);
  return picked;
}

function boleReasonText(row) {
  const signals = row.sourceSignals || [];
  const sourceText = signals.length ? `来源命中：${signals.join(" / ")}` : "来源命中：单源";
  const mergeText = row.mergedCount > 1 ? `合并${row.mergedCount}条同事件` : "单条事件";
  return `${sourceText} · ${mergeText} · ${reasonText(row.item)}`;
}

function buildBoleLead(row) {
  const { item, score } = row;
  const lead = document.createElement("a");
  lead.className = "bole-lead-card";
  lead.href = item.url || "#";
  lead.target = "_blank";
  lead.rel = "noopener noreferrer";

  const top = document.createElement("div");
  top.className = "bole-lead-top";
  const kicker = document.createElement("span");
  kicker.className = "bole-kicker";
  kicker.textContent = `${labelText(item)} · ${fmtTime(timelineIso(item))}`;
  const scoreEl = document.createElement("strong");
  scoreEl.className = `bole-score-orb ${scoreTone(score)}`;
  scoreEl.innerHTML = `<span>${score}</span><small>分</small>`;
  top.append(kicker, scoreEl);

  const title = document.createElement("div");
  title.className = "bole-lead-title";
  title.textContent = itemTitleText(item);

  const reason = document.createElement("div");
  reason.className = "bole-lead-reason";
  reason.textContent = reasonText(item);

  const foot = document.createElement("div");
  foot.className = "bole-lead-foot";
  foot.innerHTML = `<span>${item.site_name || "来源"}</span><span>${item.source || "未分区"}</span>`;

  lead.append(top, title, reason, foot);
  return lead;
}

function buildBoleTimelineRow(row, rank) {
  const { item, score } = row;
  const link = document.createElement("a");
  link.className = "bole-row";
  link.href = item.url || "#";
  link.target = "_blank";
  link.rel = "noopener noreferrer";

  const time = document.createElement("time");
  time.className = "bole-row-time";
  time.textContent = fmtTime(timelineIso(item));

  const body = document.createElement("div");
  body.className = "bole-row-body";
  const meta = document.createElement("div");
  meta.className = "bole-row-meta";
  meta.innerHTML = `<span>#${rank}</span><span>${item.site_name || "来源"}</span><strong>${score}分</strong>`;
  (row.sourceSignals || []).slice(0, 4).forEach((signal) => {
    appendSourceChip(meta, signal, sourceSignalTone(signal), "source-chip source-hit");
  });
  const title = document.createElement("div");
  title.className = "bole-row-title";
  title.textContent = itemTitleText(item);
  const reason = document.createElement("div");
  reason.className = "bole-row-reason";
  reason.textContent = boleReasonText(row);
  body.append(meta, title, reason);

  link.append(time, body);
  return link;
}

function buildStoryCard(story, rank) {
  const link = document.createElement("a");
  link.className = "story-row";
  const primary = story.primary_item || {};
  link.href = primary.url || story.primary_url || story.url || "#";
  link.target = "_blank";
  link.rel = "noopener noreferrer";

  const time = document.createElement("div");
  time.className = "story-time";
  const { latest, rangeLabel } = formatStoryTime(story);
  const labelEl = document.createElement("span");
  labelEl.className = "story-time-label";
  labelEl.textContent = "最新";
  const latestEl = document.createElement("span");
  latestEl.className = "story-time-latest";
  latestEl.textContent = fmtTime(latest);
  time.append(labelEl, latestEl);
  if (rangeLabel) {
    const rangeEl = document.createElement("span");
    rangeEl.className = "story-time-range";
    rangeEl.textContent = rangeLabel;
    rangeEl.title = "最早来源到最新来源的时间差，不是距离现在多久。";
    time.appendChild(rangeEl);
  }

  const body = document.createElement("div");
  body.className = "story-body";

  const meta = document.createElement("div");
  meta.className = "story-meta";
  const rankEl = document.createElement("span");
  rankEl.className = "story-rank";
  rankEl.textContent = `#${rank}`;
  meta.appendChild(rankEl);
  if (story.importance_label) {
    const imp = document.createElement("span");
    imp.className = `story-importance ${storyImportanceTone(story.importance_label)}`;
    imp.textContent = story.importance_label;
    meta.appendChild(imp);
  }
  const sourceCount = storySourceCount(story);
  const countEl = document.createElement("span");
  countEl.className = "story-count";
  countEl.textContent = `${sourceCount} 个来源`;
  meta.appendChild(countEl);
  const displayScore = storySortScore(story);
  if (displayScore > 0) {
    const scoreEl = document.createElement("strong");
    scoreEl.className = `story-score ${state.boleView === "hot" ? "heat" : ""}`.trim();
    scoreEl.title = state.boleView === "hot"
      ? "热度分 = 多源强度 × 时间衰减"
      : "编辑重要性分";
    scoreEl.innerHTML = `<span>${displayScore}</span><small>${state.boleView === "hot" ? "热度" : "分"}</small>`;
    meta.appendChild(scoreEl);
  }
  body.appendChild(meta);

  const sources = Array.isArray(story.sources) ? story.sources : [];
  if (sources.length) {
    const sourcesEl = document.createElement("div");
    sourcesEl.className = "story-sources";
    sources.slice(0, 6).forEach((src) => {
      const kind = sourceKind(src.site_id);
      const label = src.source || src.source_name || "来源";
      const tag = sourceChip(label, kind.tone, "story-source-chip source-chip");
      sourcesEl.appendChild(tag);
    });
    if (sources.length > 6) {
      const more = document.createElement("span");
      more.className = "story-source-more";
      more.textContent = `+${sources.length - 6}`;
      sourcesEl.appendChild(more);
    }
    body.appendChild(sourcesEl);
  }

  const title = document.createElement("div");
  title.className = "story-title";
  const primaryTitle = storyPrimaryTitleText(story);
  const enTitle = storyPrimaryEnText(story);
  if (enTitle && enTitle !== primaryTitle) {
    const zh = document.createElement("span");
    zh.className = "story-title-zh";
    zh.textContent = primaryTitle;
    const sub = document.createElement("span");
    sub.className = "story-title-en";
    sub.textContent = enTitle;
    title.append(zh, sub);
  } else {
    title.textContent = primaryTitle;
  }
  body.appendChild(title);

  link.append(time, body);
  return link;
}

const HOT_DECAY_HOURS = 12;
const HOT_SCORE_SCALE = 60;

function storyHotness(story) {
  const sources = storySourceCount(story);
  if (sources < 2) return 0;
  const latest = storyTimeMs(story, "latest_at") || storyTimeMs(story, "earliest_at");
  const ageHours = latest ? Math.max(0, (Date.now() - latest) / 3600000) : 24;
  return (sources - 1) * Math.exp(-ageHours / HOT_DECAY_HOURS);
}

function storyHotScore(story) {
  const raw = storyHotness(story);
  if (raw <= 0) return 0;
  return Math.max(1, Math.min(100, Math.round(raw * HOT_SCORE_SCALE)));
}

function storySortScore(story) {
  return state.boleView === "hot" ? storyHotScore(story) : storyScore(story);
}

function hotStories(stories) {
  return stories
    .filter((story) => storyHotness(story) > 0)
    .sort((a, b) => {
      const byHotScore = storyHotScore(b) - storyHotScore(a);
      if (byHotScore !== 0) return byHotScore;
      const byHotRaw = storyHotness(b) - storyHotness(a);
      if (byHotRaw !== 0) return byHotRaw;
      const byEditorial = storyScore(b) - storyScore(a);
      if (byEditorial !== 0) return byEditorial;
      return storyTimeMs(b, "latest_at") - storyTimeMs(a, "latest_at");
    });
}

function renderBoleBrief(stories) {
  bolePicksListEl.innerHTML = "";
  bolePicksListEl.className = "bole-board";

  const hot = hotStories(stories);
  const hotAvailable = hot.length >= 2;
  // 宁缺毋滥: the hot view only exists when there is real multi-source heat.
  if (boleViewToggleEl) boleViewToggleEl.hidden = !hotAvailable;
  if (!hotAvailable) state.boleView = "timeline";
  if (boleHotBtnEl) boleHotBtnEl.classList.toggle("active", state.boleView === "hot");
  if (boleTimelineBtnEl) boleTimelineBtnEl.classList.toggle("active", state.boleView !== "hot");

  let sorted;
  let metaLabel;
  if (state.boleView === "hot") {
    sorted = hot;
    metaLabel = `当前热点 · ${fmtNumber(sorted.length)} 簇 · 按热度分排序`;
  } else {
    sorted = [...stories].sort((a, b) => {
      const aLatest = storyTimeMs(a, "latest_at") || storyTimeMs(a, "earliest_at");
      const bLatest = storyTimeMs(b, "latest_at") || storyTimeMs(b, "earliest_at");
      if (aLatest !== bLatest) return bLatest - aLatest;
      return storyScore(b) - storyScore(a);
    });
    const topScore = Math.max(...sorted.map((s) => storyScore(s)));
    metaLabel = topScore > 0
      ? `故事时间线 · ${fmtNumber(sorted.length)} 条 · 最高 ${topScore} 分`
      : `故事时间线 · ${fmtNumber(sorted.length)} 条`;
  }

  const list = document.createElement("div");
  list.className = "bole-compact-list bole-timeline";
  const defaultLimit = state.boleView === "hot" ? BOLE_HOT_LIMIT : BOLE_TIMELINE_LIMIT;
  const visibleStories = state.boleExpanded ? sorted : sorted.slice(0, defaultLimit);
  visibleStories.forEach((story, index) => {
    list.appendChild(buildStoryCard(story, index + 1));
  });
  bolePicksListEl.appendChild(list);

  if (sorted.length > defaultLimit) {
    const moreBtn = document.createElement("button");
    moreBtn.type = "button";
    moreBtn.className = "bole-more-btn";
    moreBtn.textContent = state.boleExpanded
      ? "收起"
      : (state.boleView === "hot" ? "展开全部热点" : "展开完整时间线");
    moreBtn.addEventListener("click", () => {
      state.boleExpanded = !state.boleExpanded;
      renderBolePicks();
    });
    bolePicksListEl.appendChild(moreBtn);
  }

  const generatedAt = state.dailyBrief && state.dailyBrief.generated_at;
  bolePicksMetaEl.textContent = generatedAt ? `${metaLabel} · ${fmtTime(generatedAt)}` : metaLabel;
  document.dispatchEvent(new CustomEvent("aiRadar:briefRendered"));
}

function renderBoleFallback(picks) {
  bolePicksListEl.innerHTML = "";
  bolePicksListEl.className = "bole-board";

  const note = document.createElement("div");
  note.className = "bole-fallback-note";
  note.textContent = "故事合并数据暂未生成，先展示医疗重点候选信号。";
  bolePicksListEl.appendChild(note);

  if (!picks.length) {
    const empty = document.createElement("div");
    empty.className = "bole-empty";
    empty.textContent = "当前数据里没有可展示的评分字段。";
    bolePicksListEl.appendChild(empty);
    return;
  }

  const timelinePicks = [...picks].sort((a, b) => {
    const byTime = timelineMs(b.item) - timelineMs(a.item);
    if (byTime !== 0) return byTime;
    return b.score - a.score || a.index - b.index;
  });
  const list = document.createElement("div");
  list.className = "bole-compact-list";
  const visiblePicks = state.boleExpanded ? timelinePicks : timelinePicks.slice(0, BOLE_TIMELINE_LIMIT);
  visiblePicks.forEach((row, index) => {
    list.appendChild(buildBoleTimelineRow(row, index + 1));
  });
  bolePicksListEl.appendChild(list);
  if (timelinePicks.length > BOLE_TIMELINE_LIMIT) {
    const moreBtn = document.createElement("button");
    moreBtn.type = "button";
    moreBtn.className = "bole-more-btn";
    moreBtn.textContent = state.boleExpanded ? "收起" : "展开完整时间线";
    moreBtn.addEventListener("click", () => {
      state.boleExpanded = !state.boleExpanded;
      renderBolePicks();
    });
    bolePicksListEl.appendChild(moreBtn);
  }
  document.dispatchEvent(new CustomEvent("aiRadar:briefRendered"));
}

function storyMatchesFilteredItems(story, filteredItems) {
  if (
    state.activeSection === "all" &&
    !state.siteFilter &&
    !state.sourceTypeFilter &&
    !state.signalLevelFilter &&
    !state.query.trim()
  ) return true;
  const urls = new Set(filteredItems.map((item) => item.url).filter(Boolean));
  const ids = new Set(filteredItems.map((item) => item.id).filter(Boolean));
  const storyRefs = [
    story.primary_item,
    ...(Array.isArray(story.sources) ? story.sources : []),
    ...(Array.isArray(story.items) ? story.items : []),
  ].filter(Boolean);
  return storyRefs.some((ref) => (ref.url && urls.has(ref.url)) || (ref.id && ids.has(ref.id)));
}

function briefStories() {
  return Array.isArray(state.dailyBrief?.items) ? state.dailyBrief.items : [];
}

function mergedStories() {
  return Array.isArray(state.storiesMerged?.stories) ? state.storiesMerged.stories : [];
}

function storyStableKey(story) {
  if (!story) return "";
  return story.story_id || story.primary_url || story.url || story.primary_item?.url || story.title || "";
}

function uniqueStories(stories, excludeKeys = new Set(), excludeIdentityKeys = new Set()) {
  const seen = new Set(excludeKeys);
  return stories.filter((story) => {
    const key = storyStableKey(story);
    if (key && seen.has(key)) return false;
    if (storyHasAnyKey(story, excludeIdentityKeys)) return false;
    if (key) seen.add(key);
    return true;
  });
}

function currentStoryPools(filteredItems) {
  const brief = briefStories().filter((story) => storyMatchesFilteredItems(story, filteredItems));
  const merged = mergedStories().filter((story) => storyMatchesFilteredItems(story, filteredItems));
  const briefKeys = new Set(brief.map(storyStableKey).filter(Boolean));
  const briefIdentityKeys = new Set();
  brief.forEach((story) => storyIdentityKeys(story).forEach((key) => briefIdentityKeys.add(key)));
  return {
    brief,
    merged,
    followup: uniqueStories(merged, briefKeys, briefIdentityKeys),
  };
}

function storyRowsForPool(stories) {
  const source = Array.isArray(stories) ? stories : [];
  const pool = state.boleView === "hot"
    ? hotStories(source).slice(0, BOLE_HOT_LIMIT)
    : latestStories(source).slice(0, BOLE_TIMELINE_LIMIT);
  return pool.map(storyToBoleRow);
}

function storyCandidateCounts(stories) {
  const source = Array.isArray(stories) ? stories : [];
  const hotTotal = hotStories(source).length;
  const timelineTotal = source.length;
  return {
    hot: Math.min(BOLE_HOT_LIMIT, hotTotal),
    timeline: Math.min(BOLE_TIMELINE_LIMIT, timelineTotal),
    hotTotal,
    timelineTotal,
  };
}

function latestStories(stories) {
  return [...(Array.isArray(stories) ? stories : [])].sort((a, b) => {
    const aLatest = storyTimeMs(a, "latest_at") || storyTimeMs(a, "earliest_at");
    const bLatest = storyTimeMs(b, "latest_at") || storyTimeMs(b, "earliest_at");
    if (aLatest !== bLatest) return bLatest - aLatest;
    return storyScore(b) - storyScore(a);
  });
}

function renderStoryViewPanel(stories, excludedRows = []) {
  const panel = document.createElement("div");
  panel.className = "bole-story-panel";

  const hot = hotStories(stories);
  let baseSorted;
  let metaLabel;
  if (state.boleView === "hot") {
    baseSorted = hot;
    metaLabel = hot.length
      ? `当前热点 · ${fmtNumber(hot.length)} 簇 · 按热度分排序`
      : "当前热点 · 暂无多源聚簇";
  } else {
    baseSorted = [...stories].sort((a, b) => {
      const aLatest = storyTimeMs(a, "latest_at") || storyTimeMs(a, "earliest_at");
      const bLatest = storyTimeMs(b, "latest_at") || storyTimeMs(b, "earliest_at");
      if (aLatest !== bLatest) return bLatest - aLatest;
      return storyScore(b) - storyScore(a);
    });
    metaLabel = `故事时间线 · ${fmtNumber(baseSorted.length)} 条 · 最新优先`;
  }

  const excludeKeys = excludedStoryKeySet(excludedRows);
  const sorted = excludeKeys.size
    ? baseSorted.filter((story) => !storyHasAnyKey(story, excludeKeys))
    : baseSorted;
  const skippedCount = baseSorted.length - sorted.length;
  const rankOffset = skippedCount > 0 ? excludedRows.length : 0;
  if (skippedCount > 0) {
    metaLabel = state.boleView === "hot"
      ? `当前热点 · ${fmtNumber(baseSorted.length)} 簇 · 续看 #${rankOffset + 1} 起`
      : `故事时间线 · ${fmtNumber(baseSorted.length)} 条 · Top3 后续`;
  }

  if (boleViewToggleEl) {
    boleViewToggleEl.hidden = false;
    if (boleHotBtnEl) boleHotBtnEl.classList.toggle("active", state.boleView === "hot");
    if (boleTimelineBtnEl) boleTimelineBtnEl.classList.toggle("active", state.boleView !== "hot");
  }

  const heading = document.createElement("div");
  heading.className = "bole-story-panel-head";
  heading.textContent = metaLabel;
  panel.appendChild(heading);

  if (!sorted.length) {
    const empty = document.createElement("div");
    empty.className = "bole-empty";
    empty.textContent = skippedCount > 0
      ? "Top3 已覆盖当前筛选下的故事，可切换筛选或时间线继续查看。"
      : state.boleView === "hot"
      ? "当前筛选下没有多源热点，可切换到时间线查看最新故事。"
      : "当前筛选下没有可展示的故事时间线。";
    panel.appendChild(empty);
    return panel;
  }

  const list = document.createElement("div");
  list.className = "bole-compact-list bole-timeline";
  const defaultLimit = state.boleView === "hot" ? BOLE_HOT_LIMIT : BOLE_TIMELINE_LIMIT;
  const visibleStories = state.boleExpanded ? sorted : sorted.slice(0, defaultLimit);
  visibleStories.forEach((story, index) => {
    list.appendChild(buildStoryCard(story, rankOffset + index + 1));
  });
  panel.appendChild(list);

  if (sorted.length > defaultLimit) {
    const moreBtn = document.createElement("button");
    moreBtn.type = "button";
    moreBtn.className = "bole-more-btn";
    moreBtn.textContent = state.boleExpanded
      ? "收起"
      : (skippedCount > 0
        ? (state.boleView === "hot" ? "展开后续热点" : "展开后续时间线")
        : (state.boleView === "hot" ? "展开全部热点" : "展开完整时间线"));
    moreBtn.addEventListener("click", () => {
      state.boleExpanded = !state.boleExpanded;
      renderBolePicks();
    });
    panel.appendChild(moreBtn);
  }

  return panel;
}

function storyToBoleRow(story, index) {
  const enrichStoryItem = (entry) => ({
    ...entry,
    site_name: entry.site_name || entry.source_name || story.source_name || "",
  });
  const item = enrichStoryItem(story.primary_item || story);
  const sourceItems = [
    item,
    ...(Array.isArray(story.sources) ? story.sources.map(enrichStoryItem) : []),
  ].filter(Boolean);
  const sourceSignals = Array.from(new Set(sourceItems.map(sourceSignal)));
  return {
    item,
    index,
    story,
    rows: sourceItems.map((sourceItem) => ({ item: sourceItem })),
    sourceSignals,
    sourceCount: storySourceCount(story),
    mergedCount: Math.max(1, Number(story.duplicate_count) || sourceItems.length),
    score: storySortScore(story),
  };
}

function rankedBriefRows(stories) {
  const sorted = [...stories].sort((a, b) => {
    const aLatest = storyTimeMs(a, "latest_at") || storyTimeMs(a, "earliest_at");
    const bLatest = storyTimeMs(b, "latest_at") || storyTimeMs(b, "earliest_at");
    if (state.boleView === "hot") {
      const byHeat = storyHotScore(b) - storyHotScore(a);
      if (byHeat !== 0) return byHeat;
      const byScore = storyScore(b) - storyScore(a);
      if (byScore !== 0) return byScore;
      return bLatest - aLatest;
    }
    const byScore = storyScore(b) - storyScore(a);
    if (byScore !== 0) return byScore;
    return bLatest - aLatest;
  });
  return sorted.map(storyToBoleRow);
}

function rankedFallbackRows(items) {
  const rows = rankedClustersForItems(items);
  return state.boleView === "hot"
    ? rows.sort((a, b) => b.sourceCount - a.sourceCount || b.score - a.score || timelineMs(b.item) - timelineMs(a.item))
    : rows.sort((a, b) => timelineMs(b.item) - timelineMs(a.item) || b.score - a.score);
}

function buildBoleFollowupPanel(rows, topCount, usesStories) {
  const remaining = rows.slice(topCount);
  if (!remaining.length) return null;

  const panel = document.createElement("div");
  panel.className = "bole-story-panel";
  const heading = document.createElement("div");
  heading.className = "bole-story-panel-head";
  const viewLabel = state.boleView === "hot" ? "当前热点" : "故事时间线";
  heading.textContent = `${viewLabel} · ${fmtNumber(rows.length)} 条${usesStories ? "故事" : "候选"} · Top${topCount} 后续`;
  panel.appendChild(heading);

  const list = document.createElement("div");
  list.className = "bole-compact-list bole-timeline";
  const followupLimit = 2;
  const visibleRows = state.boleExpanded ? remaining : remaining.slice(0, followupLimit);
  visibleRows.forEach((row, index) => {
    const rank = topCount + index + 1;
    list.appendChild(row.story
      ? buildStoryCard(row.story, rank)
      : buildBoleTimelineRow(row, rank));
  });
  panel.appendChild(list);

  if (remaining.length > followupLimit) {
    const moreBtn = document.createElement("button");
    moreBtn.type = "button";
    moreBtn.className = "bole-more-btn";
    moreBtn.textContent = state.boleExpanded
      ? "收起后续"
      : `展开后续 ${fmtNumber(remaining.length - followupLimit)} 条`;
    moreBtn.addEventListener("click", () => {
      state.boleExpanded = !state.boleExpanded;
      renderBolePicks();
    });
    panel.appendChild(moreBtn);
  }
  return panel;
}

function renderBolePicks() {
  if (!bolePicksListEl || !bolePicksMetaEl) return;
  bolePicksListEl.innerHTML = "";
  bolePicksListEl.className = "top-stories-grid";
  if (boleViewToggleEl) boleViewToggleEl.hidden = true;
  if (bolePicksWrapEl) bolePicksWrapEl.hidden = false;

  const section = SECTION_BY_ID[state.activeSection] || SECTION_BY_ID.all;
  const filtered = getFilteredItems();
  const storyPools = currentStoryPools(filtered);
  const availableStoryPool = storyPools.brief.length
    ? [...storyPools.brief, ...storyPools.followup]
    : storyPools.merged;
  const usesStories = availableStoryPool.length > 0;
  const candidateCounts = storyCandidateCounts(availableStoryPool);
  const hotAvailable = usesStories && candidateCounts.hot >= 2;
  if (usesStories && !hotAvailable && state.boleView === "hot") {
    state.boleView = "timeline";
  }
  const defaultLimit = state.boleView === "hot" ? BOLE_HOT_LIMIT : BOLE_TIMELINE_LIMIT;
  const rows = usesStories
    ? storyRowsForPool(availableStoryPool)
    : rankedFallbackRows(filtered).slice(0, defaultLimit);
  const top = rows.slice(0, 3);
  const remainingCount = Math.max(0, rows.length - top.length);
  if (topStoriesTitleEl) topStoriesTitleEl.textContent = state.activeSection === "all" ? "今日重点信号" : `${section.label}重点信号`;
  const storyMeta = usesStories
    ? `展示池：热点 ${fmtNumber(candidateCounts.hot)}/${fmtNumber(candidateCounts.hotTotal)} · 时间线 ${fmtNumber(candidateCounts.timeline)}/${fmtNumber(candidateCounts.timelineTotal)}`
    : `展示池：${fmtNumber(rows.length)} 条`;
  bolePicksMetaEl.textContent = storyMeta;
  if (boleViewToggleEl) {
    boleViewToggleEl.hidden = usesStories ? !hotAvailable : true;
    if (boleHotBtnEl) boleHotBtnEl.classList.toggle("active", state.boleView === "hot");
    if (boleTimelineBtnEl) boleTimelineBtnEl.classList.toggle("active", state.boleView === "timeline");
    if (boleHotBtnEl) boleHotBtnEl.textContent = `当前热点 ${fmtNumber(candidateCounts.hot)}`;
    if (boleTimelineBtnEl) boleTimelineBtnEl.textContent = `时间线 ${fmtNumber(candidateCounts.timeline)}`;
  }

  if (!top.length) {
    const empty = document.createElement("div");
    empty.className = "bole-empty";
    empty.textContent = "当前栏目和筛选条件下没有可展示的 Top 3。";
    bolePicksListEl.appendChild(empty);
  } else {
    top.forEach((row, index) => {
      bolePicksListEl.appendChild(buildTopStoryCard(row, index + 1));
    });
  }

  const followup = buildBoleFollowupPanel(rows, top.length, usesStories);
  if (followup) {
    bolePicksListEl.appendChild(followup);
  }
  document.dispatchEvent(new CustomEvent("aiRadar:briefRendered"));
}

function rankedClustersForItems(items) {
  const rows = [...items]
    .map((item, index) => ({
      item,
      index,
      score: scorePercent(item) || Math.round(itemPriorityScore(item)),
    }))
    .filter((row) => row.item && (row.score > 0 || row.item.title))
    .sort((a, b) => itemPriorityScore(b.item) - itemPriorityScore(a.item) || timelineMs(b.item) - timelineMs(a.item));

  return clusterBoleEvents(rows).sort((a, b) => {
    const byHeadlineScore = headlineClusterScore(b) - headlineClusterScore(a);
    if (byHeadlineScore !== 0) return byHeadlineScore;
    return timelineMs(b.item) - timelineMs(a.item) || a.index - b.index;
  });
}

function headlineClusterScore(cluster) {
  const base = itemPriorityScore(cluster.item);
  const sourceBoost = Math.min(18, Math.max(0, cluster.sourceCount - 1) * 9);
  const mergeBoost = Math.min(8, Math.max(0, cluster.mergedCount - 1) * 4);
  return Math.min(100, Math.round(base + sourceBoost + mergeBoost));
}

function pickTopHeadlineClusters(clusters, limit = 3) {
  return [...clusters]
    .sort((a, b) => headlineClusterScore(b) - headlineClusterScore(a) || timelineMs(b.item) - timelineMs(a.item) || a.index - b.index)
    .slice(0, limit)
    .map((cluster) => ({ ...cluster, score: headlineClusterScore(cluster) }));
}

function itemTagLabels(item, row = null) {
  const tags = [];
  const category = Array.from(itemSections(item))[0];
  tags.push(sectionBadgeLabel(category));
  if (row && (row.sourceCount > 1 || row.mergedCount > 1)) tags.push("多源验证");
  if (item.is_official || item.site_id === "official_health" || item.source_tier === "s") tags.push("官方");
  if (item.is_policy) tags.push("政策");
  return Array.from(new Set(tags)).slice(0, 3);
}

function itemSourceRefs(item, row = null) {
  const refs = [];
  const seen = new Set();
  const add = (label, tone) => {
    const clean = String(label || "").trim();
    if (!clean) return;
    const key = `${tone}:${clean}`;
    if (seen.has(key)) return;
    seen.add(key);
    refs.push({ label: clean, tone });
  };

  if (row && Array.isArray(row.sourceSignals) && row.sourceSignals.length) {
    row.sourceSignals.forEach((signal) => add(signal, sourceSignalTone(signal)));
  } else if (row && Array.isArray(row.rows) && row.rows.length) {
    row.rows.forEach((entry) => {
      const sourceItem = entry.item || {};
      const kind = sourceKind(sourceItem.site_id);
      add(sourceItem.source || sourceItem.site_name || kind.label, kind.tone);
    });
  } else {
    const kind = sourceKind(item.site_id);
    add(item.source || item.site_name || kind.label, kind.tone);
  }

  return refs.length ? refs : [{ label: "来源", tone: "default" }];
}

function priorityGrade(score) {
  if (score >= 92) return "A+";
  if (score >= 82) return "A";
  if (score >= 70) return "B";
  return "C";
}

function rowSourceCount(row) {
  const item = row.item || {};
  const refs = itemSourceRefs(item, row);
  const storyCount = row.story ? storySourceCount(row.story) : 0;
  return Math.max(1, refs.length, Number(row.sourceCount || 0), Number(row.mergedCount || 0), storyCount);
}

function signalSummaryText(row) {
  const item = row.item || {};
  const story = row.story || {};
  const label = story.importance_label || labelText(item);
  const sourceCount = rowSourceCount(row);
  const multi = row.sourceCount > 1 || row.mergedCount > 1;
  if (multi && label) return `${label}信号，已被 ${fmtNumber(sourceCount)} 个来源验证，适合优先判断是否继续深挖。`;
  const reason = reasonText(item);
  if (reason && !reason.startsWith("来源与标题")) return reason.replace(/^命中方向：/, "核心方向：");
  return `${label}方向的新近更新，已进入 24 小时医疗强相关池。`;
}

function whyImportantText(row) {
  const item = row.item || {};
  const story = row.story || {};
  const sections = itemSections(item);
  const reasons = Array.isArray(story.reasons) ? story.reasons : [];
  if (reasons.includes("official_source") && reasons.includes("multi_source")) {
    return "一手来源和聚合来源同时出现，说明它既有事实起点，也正在被外部信息流放大。";
  }
  if (sections.has("policy")) return "政策监管变化需要回到官方原文，核对适用对象、生效时间和执行边界。";
  if (sections.has("medical_ai")) return "医疗AI进展可能影响临床决策支持、诊疗工作流与产品合规边界。";
  if (sections.has("primary_care")) return "基层医疗变化会影响诊所、社区卫生、家庭医生和基层服务能力。";
  if (sections.has("insurance_compliance")) return "医保支付和基金监管变化会直接影响医疗机构的运营与合规流程。";
  if (sections.has("health_it")) return "医疗信息化变化可能影响HIS、EMR、数据治理和机构协同方式。";
  if (sections.has("pharma_device")) return "医药器械与临床试验进展需要核对审评状态、证据等级和适用范围。";
  if (sections.has("global_healthtech")) return "海外医疗科技信号可用于观察国际产品、监管和服务模式的变化。";
  if (sections.has("company_market")) return "企业、融资与合作动态反映医疗产业资源流向和竞争重点。";
  return "它在当前 24 小时窗口里同时具备相关度、新鲜度和来源权重，值得先读原文确认。";
}

function impactLabels(item) {
  const sections = itemSections(item);
  const labels = [];
  if (sections.has("policy")) labels.push("监管 / 政策");
  if (sections.has("medical_ai")) labels.push("医疗AI / 产品");
  if (sections.has("primary_care")) labels.push("基层机构 / 医生");
  if (sections.has("insurance_compliance")) labels.push("医保 / 合规");
  if (sections.has("health_it")) labels.push("医院 / 信息化");
  if (sections.has("pharma_device")) labels.push("药企 / 器械");
  if (sections.has("company_market")) labels.push("企业 / 市场");
  if (sections.has("global_healthtech")) labels.push("海外 / 前沿");
  return labels.slice(0, 3).length ? labels.slice(0, 3) : ["医疗观察者"];
}

function buildTopStoryCard(row, rank) {
  const item = row.item;
  const link = document.createElement("a");
  link.className = `top-story-card ${rank === 1 ? "lead" : "secondary"}`;
  link.href = item.url || "#";
  link.target = "_blank";
  link.rel = "noopener noreferrer";

  const rankEl = document.createElement("span");
  rankEl.className = "top-rank";
  rankEl.textContent = `#${rank}`;

  const meta = document.createElement("div");
  meta.className = "intel-meta";
  const time = document.createElement("time");
  // Brief stories keep their timeline on the story object rather than repeating
  // it on primary_item. Fall back to that aggregate time so Top 3 never shows
  // "时间未知" when the story itself has a verified latest/earliest timestamp.
  const storyTimeline = row.story?.latest_at || row.story?.earliest_at || "";
  time.textContent = fmtTime(timelineIso(item) || storyTimeline);
  const primarySource = itemSourceRefs(item, row)[0];
  const score = document.createElement("strong");
  const displayScore = row.story
    ? Math.max(row.score || 0, storyScore(row.story))
    : Math.max(row.score || 0, headlineClusterScore(row));
  score.className = `intel-score ${scoreTone(displayScore)}`;
  score.textContent = `优先级 ${priorityGrade(displayScore)}`;
  const sourceCount = document.createElement("span");
  sourceCount.className = "source-count";
  sourceCount.textContent = `${fmtNumber(rowSourceCount(row))} 个来源`;
  meta.append(rankEl, sourceChip(primarySource.label, primarySource.tone, "source-chip intel-source"), sourceCount, score, time);

  const title = document.createElement("div");
  title.className = "top-story-title";
  title.textContent = itemTitleText(item);

  const summary = document.createElement("p");
  summary.className = "top-story-summary";
  summary.textContent = signalSummaryText(row);

  const why = document.createElement("div");
  why.className = "top-story-why";
  const whyLabel = document.createElement("span");
  whyLabel.textContent = "为什么重要";
  const whyText = document.createElement("p");
  whyText.textContent = whyImportantText(row);
  why.append(whyLabel, whyText);

  const tags = document.createElement("div");
  tags.className = "intel-tags";
  itemTagLabels(item, row).forEach((label) => {
    tags.appendChild(itemTagChip(label));
  });

  const impact = document.createElement("div");
  impact.className = "impact-row";
  impactLabels(item).forEach((label) => {
    const chip = document.createElement("span");
    chip.textContent = label;
    impact.appendChild(chip);
  });

  link.append(meta, title, summary, why, tags, impact);
  return link;
}

function buildIntelCard(item, rank) {
  const card = document.createElement("article");
  card.className = "intel-card";

  const meta = document.createElement("div");
  meta.className = "intel-card-meta";
  const rankEl = document.createElement("span");
  rankEl.className = "intel-card-rank";
  rankEl.textContent = `#${rank}`;
  const time = document.createElement("time");
  time.textContent = fmtTime(timelineIso(item));
  const score = scorePercent(item);
  const scoreEl = document.createElement("strong");
  scoreEl.className = `intel-score ${scoreTone(score)}`;
  scoreEl.textContent = score ? `医疗 ${score}分` : "医疗观察";
  meta.append(rankEl, time, scoreEl);

  const title = document.createElement("a");
  title.className = "intel-title";
  title.href = item.url || "#";
  title.target = "_blank";
  title.rel = "noopener noreferrer";
  title.textContent = itemTitleText(item);

  const reason = document.createElement("p");
  reason.className = "intel-reason";
  reason.textContent = reasonText(item);

  const tags = document.createElement("div");
  tags.className = "intel-tags";
  itemTagLabels(item).forEach((label) => {
    tags.appendChild(itemTagChip(label));
  });

  const sources = document.createElement("div");
  sources.className = "intel-card-sources";
  const refs = itemSourceRefs(item);
  const count = document.createElement("strong");
  count.textContent = `${fmtNumber(refs.length)} 个来源`;
  sources.appendChild(count);
  refs.slice(0, 3).forEach((ref) => {
    sources.appendChild(sourceChip(ref.label, ref.tone, "source-chip"));
  });

  card.append(meta, title, reason, tags, sources);
  return card;
}

function feedSummaryText(item) {
  const signals = Array.isArray(item.medical_signals) ? item.medical_signals.filter(Boolean).slice(0, 2) : [];
  if (signals.length) return `相关线索：${signals.join(" / ")}。`;
  const reason = reasonText(item);
  if (reason && !reason.startsWith("来源与标题")) return reason.replace(/^命中方向：/, "相关线索：");
  return `${labelText(item)} · 医疗相关度 ${scorePercent(item) || "待评估"}。`;
}

function renderItemNode(item, context = {}) {
  const node = itemTpl.content.firstElementChild.cloneNode(true);
  const metaRow = node.querySelector(".meta-row");
  const siteEl = node.querySelector(".site");
  siteEl.textContent = item.source || item.site_name;
  if (context.source && context.source === item.source) {
    siteEl.hidden = true;
  }
  const kind = sourceKind(item.site_id);
  const categoryEl = node.querySelector(".category");
  categoryEl.textContent = labelText(item);
  categoryEl.classList.add(`tone-${itemLabelTone(item)}`);
  const score = scorePercent(item);
  const tagEl = document.createElement("span");
  tagEl.className = `ai-tag tone-${itemLabelTone(item)}`;
  tagEl.textContent = `相关度 ${score || "?"}分`;
  categoryEl.insertAdjacentElement("afterend", tagEl);

  const sourceEl = node.querySelector(".source");
  const sourceLabel = sourceSignal(item);
  setSourceBadge(sourceEl, sourceLabel, sourceSignalTone(sourceLabel), item.source ? `分区: ${item.source}` : "");
  if (context.source && context.source === item.source) {
    sourceEl.hidden = true;
  }

  const primaryLabel = labelText(item);
  itemTagLabels(item)
    .filter((label) => label !== primaryLabel)
    .slice(0, 3)
    .forEach((label) => {
      metaRow.insertBefore(itemTagChip(label), sourceEl);
    });

  const tierLabel = sourceTierLabel(item);
  if (tierLabel) {
    const tierEl = document.createElement("span");
    tierEl.className = "tier-meta";
    tierEl.textContent = tierLabel;
    tierEl.title = "来源等级";
    metaRow.insertBefore(tierEl, node.querySelector(".time"));
  }

  node.querySelector(".time").textContent = fmtTime(item.published_at || item.first_seen_at);

  const titleEl = node.querySelector(".title");
  const zh = (item.title_zh || "").trim();
  const en = (item.title_en || "").trim();
  titleEl.textContent = "";
  if (zh && en && zh !== en) {
    const primary = document.createElement("span");
    primary.textContent = zh;
    const sub = document.createElement("span");
    sub.className = "title-sub";
    sub.textContent = en;
    titleEl.appendChild(primary);
    titleEl.appendChild(sub);
  } else {
    titleEl.textContent = item.title || zh || en;
  }
  titleEl.href = item.url;
  const summaryEl = node.querySelector(".news-summary");
  if (summaryEl) summaryEl.textContent = feedSummaryText(item);
  return node;
}

const SOURCE_ITEM_INITIAL_LIMIT = 3;
const SITE_GROUP_INITIAL_LIMIT = 4;
const SITE_GROUP_LOAD_STEP = 4;
const SITE_SOURCE_GROUP_INITIAL_LIMIT = 4;
const SITE_SOURCE_GROUP_LOAD_STEP = 4;
const SOURCE_GROUP_INITIAL_LIMIT = 8;
const SOURCE_GROUP_LOAD_STEP = 8;
const BOLE_HOT_LIMIT = 10;
const BOLE_TIMELINE_LIMIT = 20;

function buildSourceGroupNode(source, items, rawCount = items.length) {
  const section = document.createElement("section");
  section.className = "source-group";
  const header = document.createElement("header");
  header.className = "source-group-head";
  const title = document.createElement("h3");
  title.textContent = source;
  const count = document.createElement("span");
  count.className = "group-summary";
  count.textContent = subgroupSummary(items, rawCount);
  const listEl = document.createElement("div");
  listEl.className = "source-group-list";
  header.append(title, count);
  section.append(header, listEl);

  let expanded = false;
  if (items.length > SOURCE_ITEM_INITIAL_LIMIT) {
    const moreBtn = document.createElement("button");
    moreBtn.type = "button";
    moreBtn.className = "group-more-btn";
    const renderItems = () => {
      listEl.innerHTML = "";
      const visibleItems = expanded ? items : items.slice(0, SOURCE_ITEM_INITIAL_LIMIT);
      visibleItems.forEach((item) => listEl.appendChild(renderItemNode(item, { source })));
      moreBtn.textContent = expanded
        ? `收起，仅看前 ${SOURCE_ITEM_INITIAL_LIMIT} 条`
        : `展开剩余 ${fmtNumber(items.length - SOURCE_ITEM_INITIAL_LIMIT)} 条`;
    };
    moreBtn.addEventListener("click", () => {
      expanded = !expanded;
      renderItems();
    });
    renderItems();
    section.append(moreBtn);
  } else {
    items.forEach((item) => listEl.appendChild(renderItemNode(item, { source })));
  }
  return section;
}

function displayDedupeKey(item) {
  const title = normalizedEventText(itemTitleText(item));
  // Short social-post titles still identify the same visible post within one
  // subgroup; URL query strings often only carry a rotating access token and
  // must not defeat that deduplication.
  if (title) return `title:${title}`;
  try {
    const url = new URL(item.url || "");
    return `url:${url.origin}${url.pathname}`;
  } catch {
    return `url:${item.url || item.id || "untitled"}`;
  }
}

function dedupeSubgroupItems(items) {
  const seen = new Set();
  return sortItemsForList(items).filter((item) => {
    const key = displayDedupeKey(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function subgroupSortValue(items) {
  if (!items.length) return 0;
  if (state.listSort === "latest") return Math.max(...items.map(timelineMs));
  if (state.listSort === "ai") return Math.max(...items.map(scorePercent));
  if (state.listSort === "source") return items.length;
  const leading = [...items]
    .sort((a, b) => itemPriorityScore(b) - itemPriorityScore(a))
    .slice(0, 3);
  return Math.round(leading.reduce((sum, item) => sum + itemPriorityScore(item), 0) / leading.length);
}

function subgroupSummary(items, rawCount = items.length) {
  const count = `${fmtNumber(items.length)} 条`;
  const merged = rawCount - items.length;
  let ranking = "";
  if (state.listSort === "priority") ranking = `综合 ${subgroupSortValue(items)}`;
  if (state.listSort === "latest") ranking = `最新 ${fmtTime(timelineIso(items[0]))}`;
  if (state.listSort === "ai") ranking = `最高医疗 ${subgroupSortValue(items)}分`;
  const mergedLabel = merged > 0 ? `合并 ${fmtNumber(merged)} 条重复` : "";
  return [count, ranking, mergedLabel].filter(Boolean).join(" · ");
}

function sourceGroupEntries(items) {
  const groupMap = new Map();
  items.forEach((item) => {
    const key = item.source || "未分区";
    if (!groupMap.has(key)) {
      groupMap.set(key, []);
    }
    groupMap.get(key).push(item);
  });

  return Array.from(groupMap.entries())
    .map(([source, rawItems]) => ({
      source,
      rawCount: rawItems.length,
      items: dedupeSubgroupItems(rawItems),
    }))
    .filter((group) => group.items.length)
    .sort((a, b) => {
      const byScore = subgroupSortValue(b.items) - subgroupSortValue(a.items);
      if (byScore !== 0) return byScore;
      const byCount = b.items.length - a.items.length;
      if (byCount !== 0) return byCount;
      return a.source.localeCompare(b.source, "zh-CN");
    });
}

// Mobile-safe async rendering: avoid blocking the main thread on large lists.
// We chunk site-groups and yield between each chunk so the browser can paint
// and respond to touch events while the list is being built.
let _renderListToken = 0;

function buildSiteGroupNode(site) {
  const siteSection = document.createElement("section");
  siteSection.className = "site-group";
  const header = document.createElement("header");
  header.className = "site-group-head";
  const title = document.createElement("h3");
  title.textContent = site.siteName;
  const count = document.createElement("span");
  count.className = "group-summary";
  count.textContent = subgroupSummary(site.items, site.rawCount);
  const siteListEl = document.createElement("div");
  siteListEl.className = "site-group-list";
  header.append(title, count);
  siteSection.append(header, siteListEl);

  const sourceGroups = site.sourceGroups;
  let expanded = false;
  let moreBtn = null;
  const renderSourceGroups = () => {
    siteListEl.innerHTML = "";
    if (moreBtn) moreBtn.remove();
    const visibleGroups = expanded
      ? sourceGroups
      : sourceGroups.slice(0, SITE_SOURCE_GROUP_INITIAL_LIMIT);
    const frag = document.createDocumentFragment();
    visibleGroups.forEach((group) => {
      frag.appendChild(buildSourceGroupNode(group.source, group.items, group.rawCount));
    });
    siteListEl.appendChild(frag);
    if (sourceGroups.length > SITE_SOURCE_GROUP_INITIAL_LIMIT) {
      const hiddenCount = sourceGroups.length - SITE_SOURCE_GROUP_INITIAL_LIMIT;
      moreBtn = addLoadMoreButton(
        siteSection,
        expanded
          ? `收起，仅看前 ${SITE_SOURCE_GROUP_INITIAL_LIMIT} 个分区`
          : `展开其余 ${fmtNumber(hiddenCount)} 个分区`,
        () => {
          expanded = !expanded;
          renderSourceGroups();
        },
      );
    }
  };
  renderSourceGroups();
  return siteSection;
}

function renderLoadingNotice(label, count) {
  const loading = document.createElement("div");
  loading.className = "list-loading";
  loading.textContent = `正在整理 ${label} · ${fmtNumber(count)} 条`;
  newsListEl.appendChild(loading);
}

function currentFilterLabel(filtered) {
  if (state.siteFilter) {
    const item = filtered[0];
    const stat = currentSiteStats().find((s) => s.site_id === state.siteFilter);
    return `${listTitleText()} · ${item?.site_name || stat?.site_name || state.siteFilter}`;
  }
  return listTitleText();
}

function groupedSites(items) {
  const siteMap = new Map();
  items.forEach((item) => {
    if (!siteMap.has(item.site_id)) {
      siteMap.set(item.site_id, { siteName: item.site_name || item.site_id, rawItems: [] });
    }
    siteMap.get(item.site_id).rawItems.push(item);
  });

  return Array.from(siteMap.entries())
    .map(([siteId, site]) => {
      const sourceGroups = sourceGroupEntries(site.rawItems);
      return [siteId, {
        siteName: site.siteName,
        rawCount: site.rawItems.length,
        sourceGroups,
        items: sourceGroups.flatMap((group) => group.items),
      }];
    })
    .filter(([, site]) => site.items.length)
    .sort((a, b) => {
      const byScore = subgroupSortValue(b[1].items) - subgroupSortValue(a[1].items);
      if (byScore !== 0) return byScore;
      const byCount = b[1].items.length - a[1].items.length;
      if (byCount !== 0) return byCount;
      return a[1].siteName.localeCompare(b[1].siteName, "zh-CN");
    });
}

function addLoadMoreButton(parent, label, onClick) {
  const moreBtn = document.createElement("button");
  moreBtn.type = "button";
  moreBtn.className = "list-more-btn";
  moreBtn.textContent = label;
  moreBtn.addEventListener("click", onClick);
  parent.appendChild(moreBtn);
  return moreBtn;
}

function renderSiteGroups(items) {
  const groups = groupedSites(items);
  const visibleGroups = state.siteGroupsExpanded
    ? groups
    : groups.slice(0, SITE_GROUP_INITIAL_LIMIT);
  visibleGroups.forEach(([, site]) => {
    newsListEl.appendChild(buildSiteGroupNode(site));
  });

  if (groups.length > SITE_GROUP_INITIAL_LIMIT) {
    const hiddenCount = groups.length - SITE_GROUP_INITIAL_LIMIT;
    addLoadMoreButton(
      newsListEl,
      state.siteGroupsExpanded
        ? `收起，仅看前 ${SITE_GROUP_INITIAL_LIMIT} 个来源`
        : `展开其余 ${fmtNumber(hiddenCount)} 个来源`,
      () => {
        state.siteGroupsExpanded = !state.siteGroupsExpanded;
        renderList();
      },
    );
  }
  document.dispatchEvent(new CustomEvent("aiRadar:listRendered"));
}

function renderList() {
  const filtered = getFilteredItems();
  renderListSortTools();
  resultCountEl.textContent = `${fmtNumber(filtered.length)} 条`;
  renderSectionSummary(filtered);

  newsListEl.innerHTML = "";
  _renderListToken += 1;           // invalidate any in-flight render
  const token = _renderListToken;

  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "当前筛选条件下没有结果。";
    newsListEl.appendChild(empty);
    return;
  }

  renderLoadingNotice(currentFilterLabel(filtered), filtered.length);
  requestAnimationFrame(() => {
    if (token !== _renderListToken) return;   // stale render, abort
    const sorted = sortItemsForList(filtered);
    newsListEl.innerHTML = "";
    renderSiteGroups(sorted);
  });
}

function rerenderCurrentView() {
  state.boleExpanded = false;
  state.siteGroupsExpanded = false;
  renderSectionTabs();
  renderModeSwitch();
  renderSiteFilters();
  renderBolePicks();
  renderList();
}

function renderMetric(label, value, tone = "", options = {}) {
  const interactive = typeof options.onClick === "function";
  const node = document.createElement(interactive ? "button" : "div");
  node.className = `health-metric ${interactive ? "health-metric-button" : ""} ${tone}`.trim();
  if (interactive) {
    node.type = "button";
    node.title = options.title || "查看详情";
    node.setAttribute("aria-expanded", String(Boolean(options.expanded)));
    node.addEventListener("click", options.onClick);
  }
  const labelEl = document.createElement("span");
  labelEl.className = "health-label";
  labelEl.textContent = label;
  const valueEl = document.createElement("strong");
  valueEl.textContent = value;
  node.append(labelEl, valueEl);
  return node;
}

function renderIssueList(title, items) {
  const wrap = document.createElement("div");
  wrap.className = "health-issue";
  const titleEl = document.createElement("div");
  titleEl.className = "health-issue-title";
  titleEl.textContent = title;
  const list = document.createElement("ul");
  items.slice(0, 6).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = typeof item === "string" ? item : JSON.stringify(item);
    list.appendChild(li);
  });
  if (items.length > 6) {
    const li = document.createElement("li");
    li.textContent = `另有 ${fmtNumber(items.length - 6)} 项`;
    list.appendChild(li);
  }
  wrap.append(titleEl, list);
  return wrap;
}

function renderSourceHealthSummaryNode(status, errorMessage = "") {
  const node = document.createElement("div");
  node.className = "source-health-summary";
  if (!status) {
    node.classList.add(errorMessage ? "bad" : "warn");
    node.innerHTML = `<strong>${errorMessage ? "源状态异常" : "源状态未生成"}</strong><span>${errorMessage || "等待 source-status.json"}</span>`;
    return node;
  }
  const sites = Array.isArray(status.sites) ? status.sites : [];
  const okSites = Number(status.successful_sites || 0);
  const failed = failedSourceCount(status);
  const fetched = Number(status.fetched_raw_items || state.totalRaw || status.items_before_topic_filter || 0);
  node.classList.toggle("warn", failed > 0);
  node.innerHTML = `<strong>${fmtNumber(okSites)}/${fmtNumber(sites.length)} 源正常</strong><span>今日采集 ${fmtNumber(fetched)} 条 · 失败 ${fmtNumber(failed)}</span>`;
  return node;
}

function renderSourceStatusTable(status) {
  if (!sourceStatusTableEl) return;
  sourceStatusTableEl.innerHTML = "";
  if (!status || !Array.isArray(status.sites) || !status.sites.length) return;

  const rows = status.sites
    .map((site) => {
      const ai = aiSiteStat(site.site_id);
      const aiCount = Number(ai?.count || 0);
      const rawCount = Number(ai?.raw_count ?? site.item_count ?? 0);
      const scanned = Number(site.item_count || rawCount || 0);
      const ratioBase = rawCount || scanned;
      const ratio = ratioBase ? Math.round((aiCount / ratioBase) * 100) : 0;
      return { ...site, aiCount, rawCount: ratioBase, ratio };
    })
    .sort((a, b) => b.aiCount - a.aiCount || b.rawCount - a.rawCount || String(a.site_name).localeCompare(String(b.site_name), "zh-CN"))
    .slice(0, 12);

  const table = document.createElement("div");
  table.className = "source-table";
  const header = document.createElement("div");
  header.className = "source-table-row source-table-head";
  header.innerHTML = "<span>来源</span><span>医疗 / 原始</span><span>医疗占比</span><span>状态</span>";
  table.appendChild(header);
  rows.forEach((site) => {
    const row = document.createElement("div");
    row.className = "source-table-row";
    const statusText = site.ok ? "正常" : "异常";
    row.innerHTML = `
      <span>${site.site_name || site.site_id}</span>
      <span>${fmtNumber(site.aiCount)} / ${fmtNumber(site.rawCount)}</span>
      <span>${fmtNumber(site.ratio)}%</span>
      <span class="${site.ok ? "ok" : "bad"}">${statusText}</span>
    `;
    table.appendChild(row);
  });
  sourceStatusTableEl.appendChild(table);
}

function renderSourceHealth(errorMessage = "") {
  if (!sourceHealthEl) return;
  sourceHealthEl.innerHTML = "";
  if (sourceHealthDetailsEl) sourceHealthDetailsEl.innerHTML = "";
  if (sourceStatusTableEl) sourceStatusTableEl.innerHTML = "";

  const status = state.sourceStatus;
  if (!status) {
    sourceHealthEl.appendChild(renderSourceHealthSummaryNode(null, errorMessage));
    renderSourceStatusPill(errorMessage);
    renderAdvancedSummary();
    setStats();
    return;
  }

  const sites = Array.isArray(status.sites) ? status.sites : [];
  const failedSites = Array.isArray(status.failed_sites) ? status.failed_sites : [];
  const zeroSites = Array.isArray(status.zero_item_sites) ? status.zero_item_sites : [];
  const rss = status.rss_opml || {};
  const failedFeeds = Array.isArray(rss.failed_feeds) ? rss.failed_feeds : [];
  const skippedFeeds = Array.isArray(rss.skipped_feeds) ? rss.skipped_feeds : [];
  const replacedFeeds = Array.isArray(rss.replaced_feeds) ? rss.replaced_feeds : [];

  const metricGrid = document.createElement("div");
  metricGrid.className = "health-grid";
  metricGrid.append(
    renderMetric("内置源", `${fmtNumber(status.successful_sites || 0)}/${fmtNumber(sites.length)}`, failedSites.length ? "warn" : "ok"),
    renderMetric("RSS", rss.enabled ? `${fmtNumber(rss.ok_feeds || 0)}/${fmtNumber(rss.effective_feed_total || 0)}` : "未启用"),
    renderMetric("医疗强相关", `${fmtNumber(state.totalAi)}条`, state.totalAi ? "ok" : ""),
    renderMetric("失败源", fmtNumber(failedSites.length + failedFeeds.length), failedSites.length || failedFeeds.length ? "bad" : "ok"),
    renderMetric("替换/跳过", `${fmtNumber(replacedFeeds.length)}/${fmtNumber(skippedFeeds.length)}`),
  );
  sourceHealthEl.appendChild(renderSourceHealthSummaryNode(status, errorMessage));
  const detailTarget = sourceHealthDetailsEl || sourceHealthEl;
  detailTarget.appendChild(metricGrid);

  const issues = document.createElement("div");
  issues.className = "health-issues";
  if (failedSites.length) issues.appendChild(renderIssueList("失败站点", failedSites));
  if (zeroSites.length) issues.appendChild(renderIssueList("零结果站点", zeroSites));
  if (failedFeeds.length) issues.appendChild(renderIssueList("失败 RSS", failedFeeds));
  if (skippedFeeds.length) {
    issues.appendChild(renderIssueList("跳过 RSS", skippedFeeds.map((item) => `${item.feed_url} · ${item.reason || "skipped"}`)));
  }

  if (issues.childElementCount) {
    detailTarget.appendChild(issues);
  } else {
    const ok = document.createElement("div");
    ok.className = "health-ok";
    ok.textContent = "详细源状态正常";
    detailTarget.appendChild(ok);
  }
  renderSourceStatusTable(status);
  renderSourceStatusPill(errorMessage);
  renderAdvancedSummary();
  setStats();
}

async function loadNewsData() {
  const res = await fetch(cacheBustedUrl(state.newsDataUrl));
  if (!res.ok) throw new Error(`加载 latest-24h.json 失败: ${res.status}`);
  return res.json();
}

async function loadAllModeData() {
  if (state.allDataLoaded) return;
  if (!state.allDataPromise) {
    state.allDataPromise = fetch(cacheBustedUrl(state.allDataUrl))
      .then((res) => {
        if (!res.ok) throw new Error(`加载 latest-24h-all.json 失败: ${res.status}`);
        return res.json();
      })
      .then((payload) => {
        state.itemsAllRaw = payload.items_all_raw || payload.items_all || state.itemsAi;
        state.itemsAll = payload.items_all || state.itemsAi;
        state.totalRaw = payload.total_items_raw || state.itemsAllRaw.length;
        state.totalAllMode = payload.total_items_all_mode || state.itemsAll.length;
        state.allDataLoaded = true;
      })
      .catch((err) => {
        state.allDataPromise = null;
        throw err;
      });
  }
  return state.allDataPromise;
}

async function loadSourceStatusData() {
  const res = await fetch(`./data/source-status.json?t=${Date.now()}`);
  if (!res.ok) throw new Error(`加载 source-status.json 失败: ${res.status}`);
  return res.json();
}

async function loadDailyBriefData() {
  const res = await fetch(`./data/daily-brief.json?t=${Date.now()}`);
  if (!res.ok) throw new Error(`加载 daily-brief.json 失败: ${res.status}`);
  return res.json();
}

async function loadStoriesData() {
  const res = await fetch(cacheBustedUrl(state.storiesDataUrl));
  if (!res.ok) throw new Error(`加载 stories-merged.json 失败: ${res.status}`);
  return res.json();
}

async function init() {
  const [newsResult, statusResult, briefResult, storiesResult] = await Promise.allSettled([
    loadNewsData(),
    loadSourceStatusData(),
    loadDailyBriefData(),
    loadStoriesData(),
  ]);

  if (briefResult.status === "fulfilled") {
    state.dailyBrief = briefResult.value;
  } else {
    state.dailyBrief = null;
  }

  if (storiesResult.status === "fulfilled") {
    state.storiesMerged = storiesResult.value;
  } else {
    state.storiesMerged = null;
  }

  if (newsResult.status === "fulfilled") {
    const payload = newsResult.value;
    const loadedStoriesDataUrl = state.storiesDataUrl;
    state.itemsAi = payload.items_ai || payload.items || [];
    state.itemsAllRaw = payload.items_all_raw || payload.items_all || [];
    state.itemsAll = payload.items_all || [];
    state.statsAi = payload.site_stats || [];
    state.totalAi = payload.total_items || state.itemsAi.length;
    state.totalRaw = payload.total_items_raw || state.itemsAllRaw.length;
    state.totalAllMode = payload.total_items_all_mode || state.itemsAll.length;
    state.allDataUrl = payload.all_mode_data_url || state.allDataUrl;
    state.storiesDataUrl = payload.stories_data_url || state.storiesDataUrl;
    if (state.storiesDataUrl !== loadedStoriesDataUrl) {
      try {
        state.storiesMerged = await loadStoriesData();
      } catch {
        state.storiesMerged = null;
      }
    }
    state.allDataLoaded = Boolean(payload.items_all || payload.items_all_raw);
    state.generatedAt = payload.generated_at;

    setStats();
    renderSectionTabs();
    renderModeSwitch();
    renderListSortTools();
    renderCoverageStrip();
    renderSiteFilters();
    renderBolePicks();
    renderList();
    updatedAtEl.textContent = fmtTime(state.generatedAt);
  } else {
    updatedAtEl.textContent = "新闻数据加载失败";
    newsListEl.innerHTML = `<div class="empty">${newsResult.reason.message}</div>`;
    renderCoverageStrip(newsResult.reason.message);
  }

  if (statusResult.status === "fulfilled") {
    state.sourceStatus = statusResult.value;
    renderSourceHealth();
    renderCoverageStrip();
  } else {
    renderSourceHealth(statusResult.reason.message);
    renderCoverageStrip(statusResult.reason.message);
  }

  document.dispatchEvent(new CustomEvent("aiRadar:ready"));
}

searchInputEl.addEventListener("input", (e) => {
  state.query = e.target.value;
  renderBolePicks();
  renderList();
});

siteSelectEl.addEventListener("change", (e) => {
  state.siteFilter = e.target.value;
  state.siteGroupsExpanded = false;
  renderSiteFilters();
  renderBolePicks();
  renderList();
});

if (sectionSelectEl) {
  sectionSelectEl.addEventListener("change", (e) => {
    state.activeSection = e.target.value || "all";
    rerenderCurrentView();
  });
}

if (sourceTypeSelectEl) {
  sourceTypeSelectEl.addEventListener("change", (e) => {
    state.sourceTypeFilter = e.target.value;
    state.siteFilter = "";
    rerenderCurrentView();
  });
}

if (signalLevelSelectEl) {
  signalLevelSelectEl.addEventListener("change", (e) => {
    state.signalLevelFilter = e.target.value;
    rerenderCurrentView();
  });
}

modeAiBtnEl.addEventListener("click", () => {
  state.mode = "ai";
  rerenderCurrentView();
});

modeAllBtnEl.addEventListener("click", async () => {
  state.mode = "all";
  renderModeSwitch();
  newsListEl.innerHTML = "";
  const loading = document.createElement("div");
  loading.className = "empty";
  loading.textContent = "正在加载全量更新...";
  newsListEl.appendChild(loading);
  try {
    await loadAllModeData();
    rerenderCurrentView();
  } catch (err) {
    newsListEl.innerHTML = "";
    const failed = document.createElement("div");
    failed.className = "empty";
    failed.textContent = err.message;
    newsListEl.appendChild(failed);
  }
});

if (allDedupeToggleEl) {
  allDedupeToggleEl.addEventListener("change", (e) => {
    state.allDedup = Boolean(e.target.checked);
    rerenderCurrentView();
  });
}

if (listSortToolsEl) {
  listSortToolsEl.addEventListener("click", (event) => {
    const target = event.target;
    const button = target instanceof Element ? target.closest("[data-sort]") : null;
    if (!button || !listSortToolsEl.contains(button)) return;
    const nextSort = button.dataset.sort;
    if (!LIST_SORT_DEFS.some((item) => item.id === nextSort) || nextSort === state.listSort) return;
    state.listSort = nextSort;
    renderListSortTools();
    renderList();
  });
}

if (boleHotBtnEl) {
  boleHotBtnEl.addEventListener("click", () => {
    state.boleView = "hot";
    state.boleExpanded = false;
    renderBolePicks();
  });
}

if (boleTimelineBtnEl) {
  boleTimelineBtnEl.addEventListener("click", () => {
    state.boleView = "timeline";
    state.boleExpanded = false;
    renderBolePicks();
  });
}

init();
