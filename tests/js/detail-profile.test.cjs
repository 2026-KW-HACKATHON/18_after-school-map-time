const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const template = fs.readFileSync(`${__dirname}/../../places/templates/places/detail.html`, "utf8");
const source = template.match(/<script>([\s\S]*?)<\/script>/)[1];

function page(search, saved, blocked = false) {
  const keys = ["wheelchair", "stroller"];
  const chips = keys.map((profile) => ({
    dataset: { profile }, attrs: {}, handlers: {},
    setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener(k, fn) { this.handlers[k] = fn; },
  }));
  const panels = keys.map((profile) => ({ dataset: { profile }, hidden: false }));
  vm.runInNewContext(source, {
    document: { querySelectorAll: (sel) => sel === ".judge-panel" ? panels : chips, addEventListener() {} },
    window: { location: { search } }, URLSearchParams,
    localStorage: {
      getItem() { if (blocked) throw new Error("blocked"); return saved; },
      setItem() { if (blocked) throw new Error("blocked"); },
    },
  });
  return { chips, panels, selected: () => panels.filter((p) => !p.hidden).map((p) => p.dataset.profile) };
}

test("상세 링크의 이동 조건을 저장된 조건보다 우선한다", () => {
  const p = page("?profile=stroller", "wheelchair");
  assert.deepEqual(p.selected(), ["stroller"]);
  assert.equal(p.chips[1].attrs["aria-pressed"], "true");
});

test("링크의 조건이 유효하지 않으면 저장된 조건을 쓴다", () => {
  assert.deepEqual(page("?profile=invalid", "stroller").selected(), ["stroller"]);
});

test("저장소가 차단되어도 링크의 이동 조건과 전환이 동작한다", () => {
  const p = page("?profile=stroller", null, true);
  assert.deepEqual(p.selected(), ["stroller"]);
  p.chips[0].handlers.click();
  assert.deepEqual(p.selected(), ["wheelchair"]);
});

test("링크와 저장된 조건 모두 유효하지 않으면 첫 조건을 쓴다", () => {
  assert.deepEqual(page("?profile=invalid", "invalid").selected(), ["wheelchair"]);
});
