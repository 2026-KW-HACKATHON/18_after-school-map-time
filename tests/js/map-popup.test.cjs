const { test } = require("node:test");
const assert = require("node:assert/strict");
const { page, place, detail, flush } = require("./helpers/map-app-harness.cjs");

test("조건 전환으로 팝업을 닫을 때 선택한 칩의 포커스를 유지한다", async () => {
  const p = await page();
  const opener = p.doc.createElement("button");
  opener.focus();
  p.map.onClick({ id: 1 });
  const chip = p.nodes["profile-chips"].children[1];
  chip.focus();
  chip.handlers.click();
  assert.equal(p.doc.activeElement, chip);
  assert.equal(p.nodes.popup.hidden, true);
});

test("명시적인 닫기와 Escape는 팝업을 연 버튼으로 포커스를 돌린다", async () => {
  const p = await page();
  const opener = p.doc.createElement("button");
  opener.focus();
  p.map.onClick({ id: 1 });
  p.nodes["popup-close"].handlers.click();
  assert.equal(p.doc.activeElement, opener);
  p.map.onClick({ id: 2 });
  p.nodes.popup.handlers.keydown({ key: "Escape" });
  assert.equal(p.doc.activeElement, opener);
});

test("개인화 조건 변경 후 이전 상세 응답으로 추가 판정을 요청하지 않는다", async () => {
  const p = await page({ personalized: true });
  p.map.onClick({ id: 1 });
  const chip = p.nodes["profile-chips"].children[1];
  chip.focus();
  chip.handlers.click();
  p.requests[1].resolve(detail("이전 장소"));
  await flush();
  assert.equal(p.requests.length, 3);
  assert.equal(p.nodes.popup.hidden, true);
  assert.equal(p.doc.activeElement, chip);
});

test("늦은 개인화 판정이 새 팝업의 내용을 덮어쓰지 않는다", async () => {
  const p = await page({ personalized: true });
  p.map.onClick({ id: 1 });
  p.requests[1].resolve(detail("첫 장소"));
  await flush();
  p.map.onClick({ id: 2 });
  p.requests[3].resolve(detail("둘째 장소"));
  await flush();
  const result = { results: [{ judgment: { code: "ACCESSIBLE", label: "들어갈 수 있어요", personalized: true, explanation: "현재 조건" } }] };
  p.requests[4].resolve(result);
  await flush();
  p.requests[2].resolve(result);
  await flush();
  assert.match(p.nodes["popup-body"].textContent, /둘째 장소/);
  assert.doesNotMatch(p.nodes["popup-body"].textContent, /첫 장소/);
});

test("다른 마커를 열면 이전 팝업 응답을 무시한다", async () => {
  const p = await page();
  p.map.onClick({ id: 1 });
  p.map.onClick({ id: 2 });
  p.requests[2].resolve(detail("둘째 장소"));
  await flush();
  p.requests[1].resolve(detail("첫 장소"));
  await flush();
  assert.match(p.nodes["popup-body"].textContent, /둘째 장소/);
  assert.doesNotMatch(p.nodes["popup-body"].textContent, /첫 장소/);
});

test("닫힌 팝업의 늦은 오류 응답을 무시한다", async () => {
  const p = await page();
  p.map.onClick({ id: 1 });
  p.nodes["popup-close"].handlers.click();
  p.requests[1].reject(new Error("늦은 팝업 오류"));
  await flush();
  assert.equal(p.nodes.popup.hidden, true);
  assert.doesNotMatch(p.nodes["popup-body"].textContent, /늦은 팝업 오류/);
});

test("조건을 바꾸면 이전 조건의 팝업을 닫고 늦은 응답을 무시한다", async () => {
  const p = await page();
  p.map.onClick({ id: 1 });
  p.nodes["profile-chips"].children[1].handlers.click();
  assert.equal(p.nodes.popup.hidden, true);
  p.requests[1].resolve(detail("첫 장소"));
  await flush();
  assert.doesNotMatch(p.nodes["popup-body"].textContent, /첫 장소/);
});
