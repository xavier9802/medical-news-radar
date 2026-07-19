const test = require("node:test");
const assert = require("node:assert/strict");

const { filterSources, safeHttpUrl, summarizeSources } = require("../../assets/sources.js");

const rows = [
  {
    id: "who",
    name: "WHO News",
    category: "global_healthtech",
    tier: "s",
    status: "healthy",
    enabled: true,
    region: "global",
  },
  {
    id: "media",
    name: "医疗产业媒体",
    category: "company_market",
    tier: "b",
    status: "warning",
    enabled: true,
    region: "cn",
  },
  {
    id: "paused",
    name: "Paused Source",
    category: "health_it",
    tier: "c",
    status: "disabled",
    enabled: false,
    region: "us",
  },
];

test("source filters combine query category tier and status", () => {
  assert.deepEqual(
    filterSources(rows, { query: "who", category: "global_healthtech", tier: "s", status: "healthy" }),
    [rows[0]],
  );
});

test("source search is case insensitive and covers id and region", () => {
  assert.deepEqual(filterSources(rows, { query: "PAUSED" }), [rows[2]]);
  assert.deepEqual(filterSources(rows, { query: "cn" }), [rows[1]]);
});

test("source summary returns five operator-facing counts", () => {
  assert.deepEqual(summarizeSources(rows), {
    total: 3,
    enabled: 2,
    healthy: 1,
    abnormal: 1,
    disabled: 1,
  });
});

test("source homepage links allow only http and https", () => {
  assert.equal(safeHttpUrl("https://example.com/source"), "https://example.com/source");
  assert.equal(safeHttpUrl("javascript:alert(1)"), "");
  assert.equal(safeHttpUrl("https://user:pass@example.com/source"), "");
});

test("shipped pages keep source management and runtime contracts", () => {
  const fs = require("node:fs");
  const index = fs.readFileSync("index.html", "utf8");
  const sources = fs.readFileSync("sources.html", "utf8");
  const app = fs.readFileSync("assets/app.js", "utf8");
  const sectionBlock = app.slice(app.indexOf("const SECTION_DEFS"), app.indexOf("const SECTION_BY_ID"));
  const ids = [...sectionBlock.matchAll(/\{ id: "([^"]+)"/g)].map((match) => match[1]);

  assert.deepEqual(ids, [
    "all",
    "policy",
    "medical_ai",
    "primary_care",
    "insurance_compliance",
    "health_it",
    "pharma_device",
    "company_market",
    "global_healthtech",
  ]);
  assert.ok(index.indexOf("runtime-config.js") < index.indexOf("app.js"));
  assert.match(index, /href="\.\/sources\.html"/);
  assert.match(sources, /issues\/new\?template=source-request\.yml/);
});
