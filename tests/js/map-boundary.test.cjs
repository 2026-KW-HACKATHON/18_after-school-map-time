const { test } = require("node:test");
const assert = require("node:assert/strict");
const { page } = require("./helpers/map-app-harness.cjs");
const boundary = { properties: { attribution: "SGIS", boundary_date: "2026-07-01", license: "CC BY 4.0" } };

test("지도 메타 레이어·색상 범례·확대 안내 및 표시 토글은 목록을 유지한다", async () => {
  const layers = { overview: boundary, districts: {} };
  const p = await page({ boundary, layers });
  assert.equal(p.map.layers, layers);
  assert.equal(p.nodes["boundary-control"].hidden, false);
  assert.match(p.nodes["boundary-legend"].textContent, /월계1동: 빨강 · 월계2동: 파랑 · 월계3동: 초록/);
  assert.match(p.nodes["boundary-credit"].textContent, /SGIS/);
  p.map.boundaryCallback("overview");
  assert.match(p.nodes["boundary-legend"].textContent, /전체 외곽/);
  p.nodes["show-boundary"].checked = false; p.nodes["show-boundary"].handlers.change();
  assert.equal(p.map.layers, null); assert.equal(p.nodes["boundary-legend"].hidden, true);
  p.nodes["show-boundary"].checked = true; p.nodes["show-boundary"].handlers.change();
  assert.equal(p.nodes["boundary-legend"].hidden, false);
  assert.match(p.nodes["place-list"].textContent, /첫 장소/);
  assert.equal(p.map.items.length, 2);
});
test("기존 API의 단일 경계와 경계 없는 지역도 기존 지도 동작을 유지한다", async () => {
  const legacy = await page({ boundary });
  assert.equal(legacy.map.boundary, boundary); assert.equal(legacy.nodes["boundary-legend"].hidden, true);
  const empty = await page();
  assert.equal(empty.nodes["boundary-control"].hidden, true);
  assert.match(empty.nodes["boundary-status"].textContent, /아직 없어요/);
  assert.equal(empty.map.items.length, 2);
});
test("경계 실패 또는 SDK 실패도 장소 목록과 지도 마커 흐름을 막지 않는다", async () => {
  const p = await page({ boundary, layers: {}, boundaryFails: true });
  assert.equal(p.nodes["boundary-status"].hidden, false);
  assert.match(p.nodes["boundary-status"].textContent, /표시하지 못했어요/);
  assert.equal(p.nodes["boundary-legend"].hidden, true); assert.equal(p.map.items.length, 2);
  const fallback = await page({ boundary, layers: {}, mapFails: true });
  assert.equal(fallback.nodes["map-error"].hidden, false);
  assert.equal(fallback.nodes["boundary-control"].hidden, true);
  assert.match(fallback.nodes["place-list"].textContent, /첫 장소/);
});
