(function sourcePageModule(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) {
    root.MedicalRadarSources = api;
    if (root.document) {
      if (root.document.readyState === "loading") {
        root.document.addEventListener("DOMContentLoaded", () => api.initSourcePage(root.document));
      } else {
        api.initSourcePage(root.document);
      }
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function sourcePageFactory() {
  const STATUS_LABELS = {
    healthy: "正常",
    warning: "注意",
    failed: "异常",
    disabled: "已暂停",
    unknown: "未知",
  };

  function filterSources(sources, filters = {}) {
    const query = String(filters.query || "").trim().toLocaleLowerCase("zh-CN");
    const category = String(filters.category || "");
    const tier = String(filters.tier || "").toLowerCase();
    const status = String(filters.status || "").toLowerCase();
    return (Array.isArray(sources) ? sources : []).filter((source) => {
      if (category && category !== "all" && source.category !== category) return false;
      if (tier && tier !== "all" && String(source.tier || "").toLowerCase() !== tier) return false;
      if (status && status !== "all" && String(source.status || "unknown").toLowerCase() !== status) return false;
      if (!query) return true;
      const haystack = [
        source.id,
        source.name,
        source.type,
        source.category,
        source.category_label,
        source.tier,
        source.region,
        source.language,
        source.homepage_url,
        source.feed_url,
      ].filter(Boolean).join(" ").toLocaleLowerCase("zh-CN");
      return haystack.includes(query);
    });
  }

  function summarizeSources(sources) {
    const rows = Array.isArray(sources) ? sources : [];
    return {
      total: rows.length,
      enabled: rows.filter((row) => row.enabled !== false).length,
      healthy: rows.filter((row) => row.status === "healthy").length,
      abnormal: rows.filter((row) => ["warning", "failed", "unknown"].includes(row.status)).length,
      disabled: rows.filter((row) => row.enabled === false || row.status === "disabled").length,
    };
  }

  function safeHttpUrl(value) {
    try {
      const parsed = new URL(String(value || ""));
      if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) return "";
      return parsed.href;
    } catch {
      return "";
    }
  }

  function formatTime(value) {
    if (!value) return "暂无记录";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "暂无记录";
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(parsed);
  }

  function appendText(parent, tag, className, text) {
    const node = parent.ownerDocument.createElement(tag);
    node.className = className;
    node.textContent = text;
    parent.appendChild(node);
    return node;
  }

  function renderSummary(documentRef, rows) {
    const target = documentRef.getElementById("sourceStats");
    if (!target) return;
    const summary = summarizeSources(rows);
    const cards = [
      ["信源总数", summary.total],
      ["已启用", summary.enabled],
      ["正常", summary.healthy],
      ["异常", summary.abnormal],
      ["已暂停", summary.disabled],
    ];
    target.innerHTML = "";
    cards.forEach(([label, value]) => {
      const card = documentRef.createElement("div");
      card.className = "source-stat";
      appendText(card, "span", "source-stat-label", label);
      appendText(card, "strong", "source-stat-value", String(value));
      target.appendChild(card);
    });
  }

  function sourceCard(documentRef, source) {
    const card = documentRef.createElement("article");
    card.className = `source-card status-${source.status || "unknown"}`;
    const head = documentRef.createElement("div");
    head.className = "source-card-head";
    const titleWrap = documentRef.createElement("div");
    appendText(titleWrap, "h2", "source-card-title", source.name || source.id || "未命名信源");
    appendText(titleWrap, "p", "source-card-id", source.id || "");
    const status = appendText(head, "span", "source-card-status", STATUS_LABELS[source.status] || STATUS_LABELS.unknown);
    status.dataset.status = source.status || "unknown";
    head.prepend(titleWrap);

    const badges = documentRef.createElement("div");
    badges.className = "source-card-badges";
    [source.type, source.category_label || source.category, source.tier_label || String(source.tier || "").toUpperCase()]
      .filter(Boolean)
      .forEach((label) => appendText(badges, "span", "source-badge", label));

    const facts = documentRef.createElement("dl");
    facts.className = "source-card-facts";
    const factRows = [
      ["最近成功", formatTime(source.last_success_at)],
      ["最新内容", formatTime(source.latest_item_at)],
      ["成功率", source.success_rate == null ? "暂无历史数据" : `${Math.round(Number(source.success_rate) * 100)}%`],
      ["地区 / 语言", [source.region, source.language].filter(Boolean).join(" / ") || "未标注"],
    ];
    factRows.forEach(([label, value]) => {
      appendText(facts, "dt", "", label);
      appendText(facts, "dd", "", value);
    });

    const footer = documentRef.createElement("div");
    footer.className = "source-card-footer";
    const homepageUrl = safeHttpUrl(source.homepage_url);
    if (homepageUrl) {
      const link = documentRef.createElement("a");
      link.href = homepageUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "访问官网";
      footer.appendChild(link);
    }
    const error = String(source.error || "").trim();
    appendText(footer, "span", "source-card-error", error || "未记录异常");
    card.append(head, badges, facts, footer);
    return card;
  }

  function renderList(documentRef, rows) {
    const target = documentRef.getElementById("sourceList");
    const count = documentRef.getElementById("sourceResultCount");
    if (!target) return;
    target.innerHTML = "";
    if (count) count.textContent = `${rows.length} 个信源`;
    if (!rows.length) {
      appendText(target, "div", "source-empty", "没有符合当前筛选条件的信源。");
      return;
    }
    rows.forEach((source) => target.appendChild(sourceCard(documentRef, source)));
  }

  function initSourcePage(documentRef) {
    const list = documentRef.getElementById("sourceList");
    if (!list || typeof fetch !== "function") return;
    const state = { sources: [] };
    const controls = {
      query: documentRef.getElementById("sourceSearch"),
      category: documentRef.getElementById("sourceCategoryFilter"),
      tier: documentRef.getElementById("sourceTierFilter"),
      status: documentRef.getElementById("sourceStatusFilter"),
    };
    const render = () => {
      const filtered = filterSources(state.sources, {
        query: controls.query?.value,
        category: controls.category?.value,
        tier: controls.tier?.value,
        status: controls.status?.value,
      });
      renderList(documentRef, filtered);
    };
    Object.values(controls).filter(Boolean).forEach((control) => {
      control.addEventListener(control.tagName === "INPUT" ? "input" : "change", render);
    });
    fetch(`./data/source-registry.json?t=${Date.now()}`)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((payload) => {
        state.sources = Array.isArray(payload.sources) ? payload.sources : [];
        const updated = documentRef.getElementById("sourceUpdatedAt");
        if (updated) updated.textContent = formatTime(payload.generated_at);
        renderSummary(documentRef, state.sources);
        render();
      })
      .catch(() => {
        const updated = documentRef.getElementById("sourceUpdatedAt");
        if (updated) updated.textContent = "信源状态暂不可用";
        renderSummary(documentRef, []);
        list.innerHTML = "";
        appendText(list, "div", "source-empty source-load-error", "信源状态暂不可用，请稍后刷新或前往 GitHub 查看配置。 ");
      });
  }

  return { filterSources, safeHttpUrl, summarizeSources, initSourcePage };
});
