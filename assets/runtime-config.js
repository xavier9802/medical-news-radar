(function runtimeConfigModule(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) {
    root.MedicalRadarRuntime = api;
    if (root.location && root.document) {
      const runtime = api.parseRuntimeOptions(root.location.href, root.location.origin);
      api.current = runtime;
      root.document.documentElement.dataset.view = runtime.view;
      root.document.documentElement.classList.remove("view-mobile", "view-classic");
      if (runtime.view !== "auto") root.document.documentElement.classList.add(`view-${runtime.view}`);
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function runtimeConfigFactory() {
  const DEFAULT_DATA_URL = "data/latest-24h.json";
  const VALID_VIEWS = new Set(["auto", "mobile", "classic"]);

  function hasParentSegment(rawValue) {
    let value = String(rawValue || "").split(/[?#]/, 1)[0].replaceAll("\\", "/");
    for (let pass = 0; pass < 3; pass += 1) {
      try {
        const decoded = decodeURIComponent(value);
        if (decoded === value) break;
        value = decoded.replaceAll("\\", "/");
      } catch {
        return true;
      }
    }
    return value.split("/").some((segment) => segment === "..");
  }

  function safeDataUrl(rawValue, origin) {
    const raw = String(rawValue || "").trim();
    if (!raw || hasParentSegment(raw)) return DEFAULT_DATA_URL;
    let base;
    let candidate;
    try {
      base = new URL(origin);
      candidate = new URL(raw, `${base.origin}/`);
    } catch {
      return DEFAULT_DATA_URL;
    }
    if (!['http:', 'https:'].includes(candidate.protocol)) return DEFAULT_DATA_URL;
    if (candidate.origin !== base.origin || candidate.username || candidate.password || candidate.hash) return DEFAULT_DATA_URL;
    if (!candidate.pathname.toLowerCase().endsWith(".json")) return DEFAULT_DATA_URL;
    const absoluteInput = /^[a-z][a-z0-9+.-]*:/i.test(raw);
    if (absoluteInput) return candidate.href;
    const path = raw.startsWith("/") ? candidate.pathname : candidate.pathname.replace(/^\//, "");
    return `${path}${candidate.search}`;
  }

  function parseRuntimeOptions(href, origin) {
    let page;
    try {
      page = new URL(href, origin);
    } catch {
      return { view: "auto", dataUrl: DEFAULT_DATA_URL };
    }
    const requestedView = String(page.searchParams.get("view") || "auto").toLowerCase();
    return {
      view: VALID_VIEWS.has(requestedView) ? requestedView : "auto",
      dataUrl: safeDataUrl(page.searchParams.get("data"), origin),
    };
  }

  return { DEFAULT_DATA_URL, parseRuntimeOptions, safeDataUrl };
});
