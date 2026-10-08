const { test } = require("node:test");
const assert = require("node:assert/strict");
const { page, place, detail, flush } = require("./helpers/map-app-harness.cjs");

const mixedPlaces = () => [place(1, "가능 장소"),
  { ...place(2, "도움 장소"), judgment: { code: "CONDITIONAL", label: "도움 받으면", hidden_by_default: false } },
  { ...place(3, "미확인 장소"), judgment: { code: "UNKNOWN", display_code: "UNKNOWN", label: "정보 없음", hidden_by_default: true } },
  { ...place(4, "기존 어려움 장소"), judgment: { code: "DIFFICULT", display_code: "UNKNOWN", label: "정보 없음", hidden_by_default: true } }];

for (const personalized of [false, true]) {
  test(`모든 장소 기본 ON 및 OFF→ON→OFF에서 정보 없음 필터 유지 (개인화 ${personalized})`, async () => {
    const p = await page({ personalized, results: mixedPlaces() });
    assert.equal(p.nodes["show-all"].checked, true);
    assert.equal(p.nodes["place-list"].children.length, 4); assert.equal(p.map.items.length, 4);
    p.nodes["show-all"].checked = false; p.nodes["show-all"].handlers.change();
    assert.equal(p.nodes["place-list"].children.length, 2); assert.equal(p.map.items.length, 2);
    p.nodes["show-all"].checked = true; p.nodes["show-all"].handlers.change();
    assert.equal(p.nodes["place-list"].children.length, 4); assert.equal(p.map.items.length, 4);
    assert.equal(p.nodes["count-UNKNOWN"].textContent, "2곳");
    assert.equal(p.map.items.find(row => row.id === 4).className, "judge-UNKNOWN");
    p.nodes["show-all"].checked = false; p.nodes["show-all"].handlers.change();
    assert.equal(p.nodes["place-list"].children.length, 2); assert.equal(p.map.items.length, 2);
    assert.equal(p.requests.length, 1); // 토글은 재요청/재판정 없이 기존 전체 응답에서 필터링
  });
}
test("가능 장소가 없어도 빈 화면의 모든 장소 버튼으로 미확인 목록을 열 수 있다", async () => {
  const p = await page({ results: mixedPlaces().slice(2) });
  assert.equal(p.nodes["empty-state"].hidden, true);
  p.nodes["show-all"].checked = false; p.nodes["show-all"].handlers.change();
  assert.equal(p.nodes["empty-state"].hidden, false);
  p.nodes["empty-show-all"].handlers.click();
  assert.equal(p.nodes["show-all"].checked, true);
  assert.equal(p.nodes["empty-state"].hidden, true);
  assert.equal(p.map.items.length, 2);
});
test("이전 서버 응답도 OFF에서는 정보 없음·기존 어려움을 숨긴다", async () => {
  const rows = mixedPlaces();
  rows[2].judgment.hidden_by_default = false; delete rows[2].judgment.display_code;
  delete rows[3].judgment.display_code;
  const p = await page({ results: rows });
  assert.equal(p.map.items.length, 4);
  p.nodes["show-all"].checked = false; p.nodes["show-all"].handlers.change();
  assert.equal(p.map.items.length, 2);
});
test("모든 장소를 켠 상태에서 이동 조건을 바꿔도 최신 목록에 필터가 유지된다", async () => {
  const p = await page({ results: mixedPlaces() });
  p.nodes["show-all"].checked = true; p.nodes["show-all"].handlers.change();
  p.nodes["profile-chips"].children[1].handlers.click();
  p.requests[1].resolve({ results: mixedPlaces().slice(2) }); await flush();
  assert.equal(p.map.items.length, 2); assert.equal(p.nodes["show-all"].checked, true);
  p.nodes["show-all"].checked = false; p.nodes["show-all"].handlers.change();
  assert.equal(p.map.items.length, 0); assert.equal(p.nodes["empty-state"].hidden, false);
});

test("연결 실패 후 표시 조건을 바꿔도 오류와 빈 결과를 혼동하지 않는다", async () => {
  const p = await page();
  p.nodes["profile-chips"].children[1].handlers.click();
  p.requests[1].reject(new Error("서버 연결 오류"));
  await flush();
  p.nodes["show-all"].checked = true;
  p.nodes["show-all"].handlers.change();
  assert.equal(p.nodes["empty-state"].hidden, true);
  assert.equal(p.nodes["list-status"].textContent, "서버 연결 오류");
  p.nodes["profile-chips"].children[0].handlers.click();
  assert.match(p.nodes["list-status"].textContent, /불러오는 중/);
  p.requests[2].resolve({ results: [place(3, "복구된 장소")] });
  await flush();
  assert.match(p.nodes["list-status"].textContent, /1곳/);
});

test("개인화 조건 전환 중에도 로딩을 유지하고 이전 판정 응답을 무시한다", async () => {
  const p = await page({ personalized: true });
  p.nodes["profile-chips"].children[1].handlers.click();
  p.nodes["show-all"].handlers.change();
  assert.match(p.nodes["list-status"].textContent, /불러오는 중/);
  assert.equal(p.nodes["empty-state"].hidden, true);
  p.nodes["profile-chips"].children[0].handlers.click();
  p.requests[2].resolve({ results: [place(3, "최신 개인 조건")] });
  await flush();
  p.requests[1].resolve({ results: [place(4, "이전 개인 조건")] });
  await flush();
  assert.match(p.nodes["place-list"].textContent, /최신 개인 조건/);
  assert.doesNotMatch(p.nodes["place-list"].textContent, /이전 개인 조건/);
});

test("조건 변경 중에는 이전 조건의 목록과 마커를 숨긴다", async () => {
  const p = await page();
  p.nodes["profile-chips"].children[1].handlers.click();
  assert.equal(p.nodes["place-list"].children.length, 0);
  assert.equal(p.map.items.length, 0);
  assert.equal(p.nodes["empty-state"].hidden, true);
  assert.match(p.nodes["list-status"].textContent, /불러오는 중/);
  p.nodes["show-all"].handlers.change();
  assert.match(p.nodes["list-status"].textContent, /불러오는 중/);
});

test("이전 조건의 늦은 응답이 최신 조건의 장소를 덮어쓰지 않는다", async () => {
  const p = await page();
  p.nodes["profile-chips"].children[1].handlers.click();
  p.nodes["profile-chips"].children[0].handlers.click();
  p.requests[2].resolve({ results: [place(3, "최신 휠체어 장소")] });
  await flush();
  p.requests[1].resolve({ results: [place(4, "이전 유모차 장소")] });
  await flush();
  assert.match(p.nodes["place-list"].textContent, /최신 휠체어 장소/);
  assert.doesNotMatch(p.nodes["place-list"].textContent, /이전 유모차 장소/);
  assert.equal(p.map.items[0].id, 3);
});

test("이전 조건의 오류가 최신 목록의 상태를 덮어쓰지 않는다", async () => {
  const p = await page();
  p.nodes["profile-chips"].children[1].handlers.click();
  p.nodes["profile-chips"].children[0].handlers.click();
  p.requests[2].resolve({ results: [place(3, "최신 장소")] });
  await flush();
  p.requests[1].reject(new Error("이전 요청 오류"));
  await flush();
  assert.match(p.nodes["list-status"].textContent, /1곳/);
});

test("목록 요청 실패를 빈 검색 결과로 안내하지 않는다", async () => {
  const p = await page();
  p.nodes["profile-chips"].children[1].handlers.click();
  p.requests[1].reject(new Error("서버 연결 오류"));
  await flush();
  assert.equal(p.nodes["empty-state"].hidden, true);
  assert.equal(p.nodes["place-list"].children.length, 0);
  assert.equal(p.nodes["list-status"].textContent, "서버 연결 오류");
});

test("지도 SDK가 실패해도 목록과 조건 전환은 동작한다", async () => {
  const p = await page({ mapFails: true });
  assert.equal(p.nodes["map-error"].hidden, false);
  assert.match(p.nodes["place-list"].textContent, /첫 장소/);
  p.nodes["profile-chips"].children[1].handlers.click();
  p.requests[1].resolve({ results: [place(3, "유모차 장소")] });
  await flush();
  assert.match(p.nodes["place-list"].textContent, /유모차 장소/);
  assert.equal(p.nodes["search-profile"].value, "stroller");
  assert.equal(p.nodes["empty-state"].hidden, true);
});

test("최신 요청이 실제로 비었을 때만 빈 결과 안내를 보인다", async () => {
  const p = await page();
  p.nodes["profile-chips"].children[1].handlers.click();
  p.requests[1].resolve({ results: [] });
  await flush();
  assert.equal(p.nodes["empty-state"].hidden, false);
  assert.equal(p.nodes["empty-profile"].textContent, "유모차");
  assert.equal(p.nodes["list-status"].textContent, "");
});
