const test = require("node:test");
const assert = require("node:assert/strict");

const { parseRuntimeOptions } = require("../../assets/runtime-config.js");

test("safe relative data override", () => {
  assert.equal(
    parseRuntimeOptions("https://x.test/?data=data/demo.json", "https://x.test").dataUrl,
    "data/demo.json",
  );
});

test("safe same-origin absolute data override", () => {
  assert.equal(
    parseRuntimeOptions("https://x.test/?data=https%3A%2F%2Fx.test%2Fdata%2Fdemo.json", "https://x.test").dataUrl,
    "https://x.test/data/demo.json",
  );
});

for (const unsafe of [
  "file:///x",
  "../secret.json",
  "data/%2e%2e/secret.json",
  "data/%252e%252e/secret.json",
  "https://evil.test/data.json",
  "https://u:p@x.test/data.json",
  "javascript:alert(1)",
  "data/demo.txt",
]) {
  test(`rejects unsafe data override: ${unsafe}`, () => {
    const href = `https://x.test/?data=${encodeURIComponent(unsafe)}`;
    assert.equal(parseRuntimeOptions(href, "https://x.test").dataUrl, "data/latest-24h.json");
  });
}

test("view modes accept only auto, mobile, classic", () => {
  assert.equal(parseRuntimeOptions("https://x.test/?view=mobile", "https://x.test").view, "mobile");
  assert.equal(parseRuntimeOptions("https://x.test/?view=classic", "https://x.test").view, "classic");
  assert.equal(parseRuntimeOptions("https://x.test/?view=bad", "https://x.test").view, "auto");
});
