const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const helpers = require("../../static/js/mobility-settings.js");
const source = fs.readFileSync(`${__dirname}/../../static/js/mobility-settings.js`, "utf8");
const clone = (data) => JSON.parse(JSON.stringify(data));
function metadata(authenticated = false) {
  const numeric = (label, max) => ({ label, type: "number", min: 0, max, step: "0.1", unit: "cm" });
  const fields = { max_step_height_cm: numeric("턱 높이", 500), min_door_width_cm: numeric("문 폭", 1000), can_use_stairs: { label: "계단", type: "bool" } };
  const presets = ["WHEELCHAIR", "STROLLER", "WALKER", "CRUTCH"].map((key) => ({ key, label: key, profile: key,
    fields: key === "CRUTCH" ? ["max_step_height_cm", "can_use_stairs"] : Object.keys(fields), defaults: { max_step_height_cm: "2" } }));
  presets.push({ ...presets[2], key: "LIMITED_WALKING", recommendation: "초기 추천이며 실제 조건을 수정하세요." });
  presets.push({ ...presets[1], key: "WITH_CHILD", companion: true, recommendation: "실제 동반자 조건을 선택하세요." });
  presets.push({ ...presets[0], key: "ASSISTED_COMPANION", companion: true, recommendation: "실제 동반자 조건을 선택하세요." });
  return { fields, presets, rule_version: 2, authenticated, companion_options: presets.filter((p) => !p.companion), notice: "안전 보장 아님",
    settings: { version: 1, rule_version: 2, selected: ["WHEELCHAIR"], overrides: {}, companions: {} } };
}
function memoryStorage(initial = {}) {
  const saved = { ...initial };
  return { saved, getItem: (key) => saved[key] || null, setItem: (key, value) => { saved[key] = value; } };
}
function element() {
  return { handlers: {}, children: [], hidden: false, disabled: false, checked: false, open: false, value: "", textContent: "",
    addEventListener(type, fn) { this.handlers[type] = fn; },
    setAttribute(key, value) { this[key] = value; },
    appendChild(child) { this.children.push(child); },
    replaceChildren(...children) { this.children = children; },
    focus() { this.focused = true; }, showModal() { this.open = true; }, close() { this.open = false; }, reportValidity() { return true; } };
}
async function setup({ authenticated = false, storage = memoryStorage(), mode = "map", fetcher, search = "", settings } = {}) {
  const meta = metadata(authenticated), calls = [];
  if (settings) meta.settings = clone(settings);
  const nodes = Object.fromEntries(["dialog", "form", "open", "warning", "summary", "more", "preset", "companion-box", "companion", "recommendation", "fields", "multiple", "cancel", "reset", "save", "error", "result", "notice",
    "reference", "reference-search", "reference-place", "reference-reload", "reference-route-box", "reference-route", "reference-facts", "reference-step-box", "reference-step", "reference-proposal", "reference-apply", "reference-status"].map((key) => [key, element()]));
  const baseline = element(); baseline.hidden = true;
  const searchProfile = element(); searchProfile.value = "WHEELCHAIR";
  const root = { dataset: { mode, catalogueUrl: "/catalogue", preferencesUrl: "/preferences", evaluateUrl: "/evaluate", placesUrl: "/places", referenceUrl: "/reference/0/reference/", placeId: mode === "detail" ? "1" : "" },
    querySelector(selector) { return nodes[selector.replace("[data-mobility-", "").replace("]", "")]; } };
  const document = { querySelector: () => root, getElementById: () => mode === "search" ? searchProfile : null,
    querySelectorAll: () => [baseline], createElement: () => element(), dispatchEvent() {} };
  const window = {};
  vm.runInNewContext(source, { document, window, localStorage: storage, URLSearchParams, location: { search }, CustomEvent: class {},
    api: async (url, options) => {
      calls.push({ url, options: clone(options || {}) });
      if (url === "/catalogue") return clone(meta);
      if (fetcher) return fetcher(url, options);
      if (url === "/preferences") return { settings: clone(options.body) };
      return { results: [], notice: "안전 보장 아님", preferences: [] };
    } });
  await window.TeokMobility.ready();
  return { nodes, baseline, searchProfile, calls, controller: window.TeokMobility, storage, meta,
    open() { nodes.open.handlers.click(); }, submit() { return nodes.form.handlers.submit({ preventDefault() {} }); },
    select(key) { nodes.preset.value = key; nodes.preset.handlers.change(); },
    async expandReference() { nodes.reference.open = true; nodes.reference.handlers.toggle(); await new Promise(setImmediate); },
    async referencePlace(id) { nodes["reference-place"].value = String(id); await nodes["reference-place"].handlers.change(); },
    directStep(checked = true) { nodes["reference-step"].checked = checked; nodes["reference-step"].handlers.change(); },
    field(key, value) { const container = nodes.fields.children.find((c) => c.children[1].id === `mobility-field-${key}`);
      const input = container.children[1]; input.value = value; (input.handlers.input || input.handlers.change)(); } };
}

test("상세 링크 조건은 익명 저장 조건보다 우선하고 저장된 개인 수치를 보존한다", async () => {
  const settings = metadata().settings;
  settings.overrides.STROLLER = { max_step_height_cm: "4" };
  const storage = memoryStorage({ [helpers.GUEST_KEY]: JSON.stringify(settings) });
  const before = { ...storage.saved };
  const p = await setup({ storage, mode: "detail", search: "?profile=STROLLER" });
  assert.equal(p.controller.primaryProfile(), "STROLLER");
  assert.equal(p.controller.state().overrides.STROLLER.max_step_height_cm, "4");
  assert.equal(p.controller.needsEvaluation(), true);
  assert.deepEqual(storage.saved, before);
  assert.equal(p.calls.filter((c) => c.url === "/preferences").length, 0);
});

test("회원의 상세 링크는 현재 화면에만 적용하며 저장 API를 호출하지 않는다", async () => {
  const p = await setup({ authenticated: true, mode: "detail", search: "?profile=STROLLER" });
  assert.equal(p.controller.primaryProfile(), "STROLLER");
  assert.equal(p.meta.settings.selected[0], "WHEELCHAIR");
  assert.equal(p.calls.filter((c) => c.url === "/preferences").length, 0);
});

test("상세 링크가 현재 주 조건과 같으면 복수 조건과 동반자 설정을 유지한다", async () => {
  const settings = metadata().settings;
  settings.selected.push("ASSISTED_COMPANION");
  settings.companions.ASSISTED_COMPANION = "CRUTCH";
  const p = await setup({ authenticated: true, settings, mode: "detail", search: "?profile=WHEELCHAIR" });
  assert.deepEqual(clone(p.controller.state()), settings);
  assert.equal(p.controller.needsEvaluation(), true);
});

test("잘못된 상세 링크는 저장된 조건을 유지하고 지도·검색 링크는 설정을 바꾸지 않는다", async () => {
  for (const mode of ["map", "search", "detail"]) {
    const search = mode === "detail" ? "?profile=invalid" : "?profile=STROLLER";
    const p = await setup({ mode, search });
    assert.equal(p.controller.primaryProfile(), "WHEELCHAIR");
  }
});

test("상세 링크 조건은 저장소가 차단돼도 초기 발행 전에 적용한다", async () => {
  const storage = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };
  const p = await setup({ storage, mode: "detail", search: "?profile=STROLLER" });
  assert.equal(p.controller.primaryProfile(), "STROLLER");
  assert.equal(p.controller.needsEvaluation(), false);
});

test("숫자 경계값·bool은 검증하고 손상된 설정은 거부한다", () => {
  const meta = metadata();
  for (const value of [0, 500, "0.1"]) {
    const data = clone(meta.settings); data.overrides.WHEELCHAIR = { max_step_height_cm: value, can_use_stairs: false };
    assert.equal(helpers.validateState(data, meta).overrides.WHEELCHAIR.can_use_stairs, false);
  }
  for (const value of [-1, 501, "NaN", "Infinity", "0.11", true, "", "²"]) {
    const data = clone(meta.settings); data.overrides.WHEELCHAIR = { max_step_height_cm: value };
    assert.throws(() => helpers.validateState(data, meta));
  }
  for (const value of ["false", "perhaps", 0]) {
    const data = clone(meta.settings); data.overrides.WHEELCHAIR = { can_use_stairs: value };
    assert.throws(() => helpers.validateState(data, meta));
  }
});
test("익명 저장값·이전 Preset 복원 및 기준 버전 변경", () => {
  const meta = metadata(), data = clone(meta.settings);
  data.rule_version = 1; data.overrides.WHEELCHAIR = { max_step_height_cm: "4" };
  const restored = helpers.restoreGuest(memoryStorage({ [helpers.GUEST_KEY]: JSON.stringify(data) }), meta);
  assert.equal(restored.settings.overrides.WHEELCHAIR.max_step_height_cm, "4");
  assert.match(restored.warning, /최신 기본값/);
  assert.deepEqual(helpers.restoreGuest(memoryStorage({ "teokeopne.profile": "CRUTCH" }), meta).settings.selected, ["CRUTCH"]);
  for (const raw of ["{", "null", JSON.stringify({ ...data, selected: ["bad"] })]) {
    const out = helpers.restoreGuest(memoryStorage({ [helpers.GUEST_KEY]: raw }), meta);
    assert.deepEqual(out.settings, meta.settings); assert.ok(out.warning);
  }
});
test("Preset 전환·복수 조건·초기화는 다른 사람의 Override를 보존한다", () => {
  const data = metadata().settings;
  data.selected.push("ASSISTED_COMPANION"); data.overrides = { WHEELCHAIR: { max_step_height_cm: "4" }, ASSISTED_COMPANION: { min_door_width_cm: "90" } };
  const original = clone(data), out = helpers.switchCompanion(data, "ASSISTED_COMPANION", "CRUTCH");
  assert.deepEqual(data, original); assert.deepEqual(out.overrides.WHEELCHAIR, original.overrides.WHEELCHAIR);
  assert.equal(out.overrides.ASSISTED_COMPANION, undefined);
  assert.deepEqual(helpers.fieldsFor(metadata(), out, "ASSISTED_COMPANION"), ["max_step_height_cm", "can_use_stairs"]);
  assert.deepEqual(helpers.switchPreset(out, "ASSISTED_COMPANION").selected, ["ASSISTED_COMPANION", "WHEELCHAIR"]);
});
test("기본 Preset 4종은 별도 개인 판정 없이 사용할 수 있다", async () => {
  const ui = await setup();
  for (const key of ["WHEELCHAIR", "STROLLER", "WALKER", "CRUTCH"]) {
    await ui.controller.selectPreset(key); assert.equal(ui.controller.needsEvaluation(), false);
    assert.equal(ui.controller.primaryProfile(), key);
  }
});
test("Modal 취소·Esc는 변경을 저장하지 않고 포커스를 돌려준다", async () => {
  const ui = await setup(); ui.open(); ui.field("max_step_height_cm", "4");
  ui.nodes.cancel.handlers.click();
  assert.equal(ui.nodes.dialog.open, false); assert.ok(ui.nodes.open.focused);
  assert.equal(ui.storage.saved[helpers.GUEST_KEY], undefined);
  ui.open(); ui.field("max_step_height_cm", "5");
  ui.nodes.dialog.handlers.cancel({ preventDefault() {} });
  assert.deepEqual(clone(ui.controller.state().overrides), {});
});
test("저장·새로고침 복원·Preset 전환·기본값 초기화", async () => {
  const storage = memoryStorage(), ui = await setup({ storage });
  ui.open(); ui.field("max_step_height_cm", "4"); await ui.submit();
  assert.equal(ui.controller.needsEvaluation(), true);
  const restored = await setup({ storage }); assert.equal(restored.controller.state().overrides.WHEELCHAIR.max_step_height_cm, "4");
  await restored.controller.selectPreset("STROLLER"); assert.equal(restored.controller.needsEvaluation(), false);
  await restored.controller.selectPreset("WHEELCHAIR"); restored.open(); restored.nodes.reset.handlers.click(); await restored.submit();
  assert.deepEqual(clone(restored.controller.state().overrides), {});
});
test("보호자는 실제 이동 조건을 선택하며 본인의 값과 분리된다", async () => {
  const ui = await setup(); ui.open(); ui.field("max_step_height_cm", "4");
  ui.select("ASSISTED_COMPANION");
  ui.nodes.companion.value = "CRUTCH"; ui.nodes.companion.handlers.change();
  assert.equal(ui.nodes.fields.children.length, 2);
  ui.field("max_step_height_cm", "1"); await ui.submit();
  assert.equal(ui.controller.primaryProfile(), "CRUTCH");
  assert.equal(ui.controller.state().overrides.WHEELCHAIR.max_step_height_cm, "4");
  assert.equal(ui.controller.state().overrides.ASSISTED_COMPANION.max_step_height_cm, "1");
});
test("회원 저장은 익명 localStorage를 읽거나 변경하지 않는다", async () => {
  const storage = memoryStorage({ [helpers.GUEST_KEY]: "손상된 익명 값" }), ui = await setup({ authenticated: true, storage });
  ui.open(); ui.field("max_step_height_cm", "4"); await ui.submit();
  assert.equal(storage.saved[helpers.GUEST_KEY], "손상된 익명 값");
  assert.equal(ui.calls.find((c) => c.url === "/preferences").options.method, "PUT");
});
test("저장 중 중복 submit은 한 번만 처리하고 실패해도 입력을 보존한다", async () => {
  let rejectSave, count = 0;
  const ui = await setup({ authenticated: true, fetcher: () => { count++; return new Promise((resolve, reject) => { rejectSave = reject; }); } });
  ui.open(); ui.field("max_step_height_cm", "4"); const first = ui.submit(); await ui.submit();
  await Promise.resolve(); assert.equal(count, 1); rejectSave(new Error("저장 실패")); await first;
  assert.equal(ui.nodes.dialog.open, true); assert.equal(ui.nodes.save.disabled, false);
  assert.match(ui.nodes.error.textContent, /저장 실패/); assert.equal(ui.nodes.fields.children[0].children[1].value, "4");
});
test("저장이 막힌 브라우저에서도 현재 화면 적용과 안내가 가능하다", async () => {
  const ui = await setup({ storage: { getItem() { return null; }, setItem() { throw new Error("blocked"); } } });
  ui.open(); ui.field("max_step_height_cm", "4"); await ui.submit();
  assert.equal(ui.controller.state().overrides.WHEELCHAIR.max_step_height_cm, "4");
  assert.match(ui.nodes.warning.textContent, /새로고침/);
});
test("상세 기본 패널의 선택 상태를 개인화 컨트롤러가 덮어쓰지 않는다", async () => {
  const ui = await setup({ mode: "detail" });
  assert.equal(ui.baseline.hidden, true);
  await ui.controller.selectPreset("STROLLER"); assert.equal(ui.baseline.hidden, true);
});
test("초기화 뒤 늦게 도착한 개인화 결과는 표시하지 않는다", async () => {
  const pending = [];
  const ui = await setup({ mode: "detail", fetcher: () => new Promise((resolve) => pending.push(resolve)) });
  ui.open(); ui.field("max_step_height_cm", "4"); await ui.submit();
  assert.equal(pending.length, 1); ui.open(); ui.nodes.reset.handlers.click(); await ui.submit();
  pending[0]({ results: [], notice: "old", preferences: [] }); await Promise.resolve(); await Promise.resolve();
  assert.equal(ui.nodes.result.hidden, true);
});
test("검색의 이동 조건 선택값과 카드 스타일은 저장된 동반자 조건에 맞춘다", async () => {
  const data = metadata().settings; data.selected = ["WITH_CHILD"]; data.companions.WITH_CHILD = "CRUTCH";
  const ui = await setup({ mode: "search", storage: memoryStorage({ [helpers.GUEST_KEY]: JSON.stringify(data) }), fetcher: async () => ({
    results: [{ id: 1, name: "장소", facts: "입구 단차 3cm", last_checked: "2026-10-08", judgment: { code: "DIFFICULT", label: "어려움" } }], notice: "안내", preferences: [] }) });
  await Promise.resolve();
  assert.equal(ui.searchProfile.value, "CRUTCH");
  const list = ui.nodes.result.children.find((node) => node.class === "result-list");
  assert.equal(list.children[0].children[0].class, "card result-card");
  assert.equal(list.children[0].children[0].children[3].textContent, "확인 2026-10-08");
});

function referenceRoute(height = "7", width = "80", id = "entrance:1") {
  return { id, label: `경로 ${id}`, values: { max_step_height_cm: height, min_door_width_cm: width }, warnings: [],
    entrances: [{ entrance_id: 1, label: "정문", fields: [{ key: "step_height_cm", label: "턱", value: height, unit: "cm", checked_at: "2026-10-08", pending: false }] }] };
}
function referenceFetcher(url, options) {
  if (url.startsWith("/places?")) return { results: [{ id: 1, name: "가본 장소", address: "월계동" }, { id: 2, name: "다른 장소", address: "골목" }] };
  if (url.startsWith("/reference/")) return { routes: [referenceRoute()], notice: "측정값이며 안전 보장 아님" };
  if (url === "/preferences") return { settings: clone(options.body) };
  return { results: [], notice: "안내", preferences: [] };
}
test("참고값은 직접 턱 통과 확인 시 높이만 추가하며 bool·미지원 필드를 추론하지 않는다", () => {
  const meta = metadata(), data = clone(meta.settings), route = referenceRoute("0", "80");
  route.values.can_use_stairs = true; route.values.min_passage_width_cm = "50";
  assert.deepEqual(helpers.referenceValues(meta, data, route, false), { min_door_width_cm: "80" });
  assert.deepEqual(helpers.referenceValues(meta, data, route, true), { max_step_height_cm: "0", min_door_width_cm: "80" });
  data.selected = ["CRUTCH"];
  assert.deepEqual(helpers.referenceValues(meta, data, route, true), { max_step_height_cm: "0" });
  for (const values of [{ max_step_height_cm: "NaN", min_door_width_cm: true }, { max_step_height_cm: "3.25", min_door_width_cm: "1001" }])
    assert.deepEqual(helpers.referenceValues(meta, meta.settings, { ...route, values }, true), {});
  assert.deepEqual(helpers.referenceValues(meta, meta.settings, { ...route, incomplete: true }, true), {});
  assert.deepEqual(helpers.referenceValues(meta, meta.settings, { ...route, unavailable: true }, true), {});
});
test("장소 선택은 기존 초안을 바꾸지 않고 적용 버튼에서만 현재 Preset 수치를 채운다", async () => {
  const ui = await setup({ fetcher: referenceFetcher }); ui.open(); ui.field("max_step_height_cm", "4");
  await ui.expandReference(); await ui.referencePlace(1);
  assert.equal(ui.nodes.fields.children[0].children[1].value, "4");
  ui.nodes["reference-apply"].handlers.click();
  assert.equal(ui.nodes.fields.children[0].children[1].value, "4");
  assert.equal(ui.nodes.fields.children[1].children[1].value, "80");
  ui.directStep(); ui.nodes["reference-apply"].handlers.click();
  assert.equal(ui.nodes.fields.children[0].children[1].value, "7");
  assert.deepEqual(clone(ui.controller.state().overrides), {});
  ui.nodes.cancel.handlers.click(); assert.equal(ui.storage.saved[helpers.GUEST_KEY], undefined);
});
test("참고값 저장·복원은 기존 저장 경로를 사용하고 방문 이력은 넣지 않는다", async () => {
  const storage = memoryStorage(), ui = await setup({ storage, fetcher: referenceFetcher }); ui.open();
  await ui.expandReference(); await ui.referencePlace(1); ui.directStep(); ui.nodes["reference-apply"].handlers.click(); await ui.submit();
  const saved = JSON.parse(storage.saved[helpers.GUEST_KEY]);
  assert.deepEqual(saved.overrides.WHEELCHAIR, { max_step_height_cm: "7", min_door_width_cm: "80" });
  assert.deepEqual(Object.keys(saved).sort(), ["companions", "overrides", "rule_version", "selected", "version"]);
  const restored = await setup({ storage }); assert.equal(restored.controller.state().overrides.WHEELCHAIR.max_step_height_cm, "7");
});
test("동반자 참고값 적용은 본인의 수치와 기존 bool 설정을 보존한다", async () => {
  const ui = await setup({ authenticated: true, fetcher: referenceFetcher }); ui.open(); ui.field("max_step_height_cm", "4");
  ui.select("ASSISTED_COMPANION"); ui.nodes.companion.value = "CRUTCH"; ui.nodes.companion.handlers.change();
  ui.field("can_use_stairs", "false"); await ui.expandReference(); await ui.referencePlace(1);
  ui.directStep(); ui.nodes["reference-apply"].handlers.click(); await ui.submit();
  const data = ui.controller.state();
  assert.equal(data.overrides.WHEELCHAIR.max_step_height_cm, "4");
  assert.deepEqual(clone(data.overrides.ASSISTED_COMPANION), { can_use_stairs: false, max_step_height_cm: "7" });
  assert.equal(data.overrides.ASSISTED_COMPANION.min_door_width_cm, undefined);
});
test("여러 입구는 사용자가 경로를 선택해야 하고 경로를 바꾸면 직접 통과 확인을 다시 받는다", async () => {
  const ui = await setup({ fetcher: (url, options) => url.startsWith("/reference/") ? { routes: [referenceRoute("1", "70", "front"), referenceRoute("7", "90", "back")], notice: "안내" } : referenceFetcher(url, options) });
  ui.open(); await ui.expandReference(); await ui.referencePlace(1);
  assert.equal(ui.nodes["reference-apply"].disabled, true);
  ui.nodes["reference-route"].value = "front"; ui.nodes["reference-route"].handlers.change(); ui.directStep();
  ui.nodes["reference-apply"].handlers.click(); assert.equal(ui.nodes.fields.children[1].children[1].value, "70");
  ui.nodes["reference-route"].value = "back"; ui.nodes["reference-route"].handlers.change();
  assert.equal(ui.nodes["reference-step"].checked, false);
  ui.directStep(); ui.nodes["reference-apply"].handlers.click();
  assert.equal(ui.nodes.fields.children[0].children[1].value, "7"); assert.equal(ui.nodes.fields.children[1].children[1].value, "90");
});
test("검색·빈 목록·입구 미등록·Enter는 기존 저장 동작을 방해하지 않는다", async () => {
  const ui = await setup({ fetcher: (url, options) => url.startsWith("/reference/") ? { routes: [], notice: "안내" } : referenceFetcher(url, options) });
  ui.open(); await ui.expandReference();
  assert.ok(ui.calls.find((c) => c.url === "/places?all=1"));
  ui.nodes["reference-search"].value = "골목"; ui.nodes["reference-search"].handlers.input();
  assert.equal(ui.nodes["reference-place"].children.length, 2);
  let prevented = false; ui.nodes["reference-search"].handlers.keydown({ key: "Enter", preventDefault() { prevented = true; } }); assert.ok(prevented);
  await ui.referencePlace(2); assert.match(ui.nodes["reference-status"].textContent, /입구 경로/);
  ui.nodes["reference-search"].value = "없는 장소"; ui.nodes["reference-search"].handlers.input();
  assert.equal(ui.nodes["reference-place"].disabled, true); assert.equal(ui.nodes["reference-apply"].disabled, true);
  ui.field("max_step_height_cm", "4"); await ui.submit(); assert.equal(ui.controller.state().overrides.WHEELCHAIR.max_step_height_cm, "4");
});
test("장소 확인값 오류는 직접 입력을 보존하며 새로 불러오기 후 재시도 가능하다", async () => {
  let fail = true;
  const ui = await setup({ fetcher: (url, options) => { if (url.startsWith("/reference/") && fail) throw new Error("장소를 찾을 수 없음"); return referenceFetcher(url, options); } });
  ui.open(); ui.field("max_step_height_cm", "4"); await ui.expandReference(); await ui.referencePlace(1);
  assert.match(ui.nodes["reference-status"].textContent, /찾을 수 없음/); assert.equal(ui.nodes["reference-apply"].disabled, true);
  assert.equal(ui.nodes.fields.children[0].children[1].value, "4");
  fail = false; await ui.nodes["reference-reload"].handlers.click(); await ui.referencePlace(1);
  assert.equal(ui.nodes["reference-apply"].disabled, false);
});
test("늦게 온 이전 장소 응답과 취소·Preset 변경 뒤 응답을 무시한다", async () => {
  const pending = [];
  const ui = await setup({ fetcher: (url, options) => url === "/reference/1/reference/" ? new Promise((resolve) => pending.push(resolve)) : referenceFetcher(url, options) });
  ui.open(); await ui.expandReference(); const first = ui.referencePlace(1); await ui.referencePlace(2);
  pending.shift()({ routes: [referenceRoute("1", "70")], notice: "old" }); await first;
  ui.directStep(); ui.nodes["reference-apply"].handlers.click(); assert.equal(ui.nodes.fields.children[1].children[1].value, "80");
  const changed = ui.referencePlace(1); ui.select("CRUTCH"); pending.shift()({ routes: [referenceRoute()], notice: "old" }); await changed;
  assert.equal(ui.nodes["reference-apply"].disabled, true);
  const cancelled = ui.referencePlace(1); ui.nodes.cancel.handlers.click(); ui.open();
  pending.shift()({ routes: [referenceRoute()], notice: "old" }); await cancelled;
  assert.equal(ui.nodes["reference-apply"].disabled, true); assert.deepEqual(clone(ui.controller.state().overrides), {});
});
