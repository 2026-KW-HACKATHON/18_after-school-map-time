// 'AI로 항목 채우기': 빈 칸만 채우기, 표 저장, 오류 안내, 시설 종류 바꾸면 표 비우기 (node --test tests/js/ai-prefill.test.cjs)
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(`${__dirname}/../../static/js/reports/ai-prefill.js`, "utf8");

function load() {
  const context = { module: { exports: {} }, Promise };
  vm.runInNewContext(source, context);
  return context.module.exports;
}

function element(props = {}) {
  const el = {
    value: "", tagName: "INPUT", options: [], disabled: false, textContent: "", dataset: {}, handlers: {},
    classList: { set: new Set(), add(c) { this.set.add(c); }, remove(c) { this.set.delete(c); }, contains(c) { return this.set.has(c); } },
    inserted: [],
    insertAdjacentElement(_, node) { this.inserted.push(node); node.parent = this; },
    addEventListener(name, fn) { this.handlers[name] = fn; },
    ...props,
  };
  return el;
}

function page({ values = {}, file = { name: "door.jpg" }, note = "턱 3cm" } = {}) {
  const notes = [];
  const select = (opts) => element({ tagName: "SELECT", options: opts.map((v) => ({ value: v })) });
  const elements = {
    step_height_cm: element(), step_count: element(),
    has_ramp: select(["", "true", "false"]), door_type: select(["", "미닫이", "여닫이"]),
    photo: element({ files: file ? [file] : [] }), photo_token: element(),
    note: element({ value: note }), facility_kind: element({ value: "ENTRANCE" }),
    ownership: element({ value: "PLACE" }),
    csrfmiddlewaretoken: element({ value: "csrf" }),
  };
  Object.entries(values).forEach(([k, v]) => { elements[k].value = v; });
  const marked = () => Object.values(elements).filter((e) => e.classList.contains("ai-filled"));
  const form = {
    elements,
    querySelectorAll(sel) { return sel === ".ai-filled-note" ? notes.splice(0).map((n) => ({ remove() {} })) : marked(); },
  };
  const status = element(); const token = element(); const button = element(); const selector = element();
  const box = { dataset: { url: "/report/ai-prefill/" },
    querySelector: (sel) => ({ "#ai-prefill-status": status, "#ai-prefill-token": token, "#ai-prefill-button": button })[sel] };
  const doc = {
    createElement: () => { const n = { className: "", textContent: "" }; notes.push(n); return n; },
    getElementById: (id) => ({ "report-form": form, "ai-prefill": box, "facility-selector": selector })[id],
  };
  return { form, box, doc, elements, status, token, button, selector };
}

class FakeFormData { constructor() { this.entries = []; } append(k, v) { this.entries.push([k, v]); } }
const ok = {
  ok: true, token: "signed-token", remaining: 2, warnings: ["사진만으로는 수치를 잴 수 없어요"],
  fields: {
    step_height_cm: { value: 3, certainty: "분명함", evidence: "턱 재보니 3cm" },
    step_count: { value: null, certainty: "모름", evidence: "" },
    has_ramp: { value: false, certainty: "분명함", evidence: "경사로 없음" },
    door_type: { value: "자동문", certainty: "분명함", evidence: "" },  // 선택지에 없으면 넣지 않음
  },
};
const deps = (doc, response, sent = []) => ({
  document: doc, FormData: FakeFormData,
  fetch: async (url, opts) => { sent.push([url, opts]); return { json: async () => response }; },
});

test("빈 칸만 채우고 표를 숨은 칸에 넣는다", async () => {
  const { run } = load();
  const p = page({ values: { has_ramp: "true" } });  // 주민이 이미 '있음'을 고름
  const sent = [];
  await run(p.form, p.box, deps(p.doc, ok, sent));
  assert.equal(p.elements.step_height_cm.value, "3");
  assert.equal(p.elements.has_ramp.value, "true");  // 덮어쓰지 않음
  assert.equal(p.elements.step_count.value, "");     // 모름은 비워 둠
  assert.equal(p.elements.door_type.value, "");      // 선택지에 없는 값은 넣지 않음
  assert.ok(p.elements.step_height_cm.classList.contains("ai-filled"));
  assert.match(p.elements.step_height_cm.inserted[0].textContent, /AI가 채움 · 분명함 — 턱 재보니 3cm/);
  assert.equal(p.token.value, "signed-token");
  assert.match(p.status.textContent, /AI가 1칸을 채웠어요.*오늘 2번 더/);
  const body = sent[0][1].body.entries;
  assert.deepEqual(body.map(([k]) => k), ["csrfmiddlewaretoken", "facility_kind", "note", "photo"]);
  assert.equal(p.button.disabled, false);
});

test("불리언은 true/false 선택지로", async () => {
  const { run } = load();
  const p = page();
  await run(p.form, p.box, deps(p.doc, ok));
  assert.equal(p.elements.has_ramp.value, "false");
});

test("사진도 설명도 없으면 보내지 않는다", async () => {
  const { run } = load();
  const p = page({ file: null, note: "  " });
  const sent = [];
  await run(p.form, p.box, deps(p.doc, ok, sent));
  assert.equal(sent.length, 0);
  assert.match(p.status.textContent, /사진을 고르거나 설명을 적은 뒤/);
});

test("서버 오류 안내를 그대로 보여 주고 칸은 그대로", async () => {
  const { run } = load();
  const p = page();
  await run(p.form, p.box, deps(p.doc, { ok: false, message: "오늘 AI 채우기를 다 썼어요. 직접 입력해 주세요." }));
  assert.equal(p.status.textContent, "오늘 AI 채우기를 다 썼어요. 직접 입력해 주세요.");
  assert.equal(p.elements.step_height_cm.value, "");
  assert.equal(p.token.value, "");
});

test("네트워크가 끊겨도 버튼이 다시 살아난다", async () => {
  const { run } = load();
  const p = page();
  await run(p.form, p.box, { document: p.doc, FormData: FakeFormData, fetch: async () => { throw new Error("offline"); } });
  assert.match(p.status.textContent, /연결이 불안정해요/);
  assert.equal(p.button.disabled, false);
});

test("시설 종류를 바꾸면 이전 결과 표를 비운다", async () => {
  const { init } = load();
  const p = page();
  init(p.doc, deps(p.doc, ok));
  p.token.value = "signed-token";
  p.selector.handlers.change();
  assert.equal(p.token.value, "");
});

test("시설 종류가 같아도 소속을 바꾸면 늦은 결과와 토큰을 적용하지 않는다", async () => {
  const { init, run } = load();
  const p = page({ values: { has_ramp: "true" } });
  let resolve;
  const d = { document: p.doc, FormData: FakeFormData,
    fetch: () => new Promise((done) => { resolve = done; }) };
  init(p.doc, d);
  const running = run(p.form, p.box, d);
  p.selector.handlers.change();
  p.elements.ownership.value = "BUILDING";
  resolve({ json: async () => ok });
  await running;
  assert.equal(p.elements.step_height_cm.value, "");
  assert.equal(p.elements.has_ramp.value, "true");
  assert.equal(p.token.value, "");
  assert.equal(p.button.disabled, false);
});

test("시설 변경 뒤 이전 서버 오류도 현재 안내를 덮어쓰지 않는다", async () => {
  const { init, run } = load();
  const p = page();
  let resolve;
  const d = { document: p.doc, FormData: FakeFormData,
    fetch: () => new Promise((done) => { resolve = done; }) };
  init(p.doc, d);
  const running = run(p.form, p.box, d);
  p.selector.handlers.change();
  resolve({ json: async () => ({ ok: false, message: "이전 분석 오류" }) });
  await running;
  assert.doesNotMatch(p.status.textContent, /이전 분석 오류/);
  assert.equal(p.button.disabled, false);
});

test("분석 중 시설을 바꾸면 늦게 온 이전 시설의 결과를 적용하지 않는다", async () => {
  const { init, run } = load();
  const p = page();
  let resolve;
  const pending = new Promise((done) => { resolve = done; });
  const d = { document: p.doc, FormData: FakeFormData, fetch: () => pending };
  init(p.doc, d);
  const running = run(p.form, p.box, d);
  p.elements.facility_kind.value = "RESTROOM";
  p.selector.handlers.change();
  resolve({ json: async () => ok });
  await running;
  assert.equal(p.elements.step_height_cm.value, "");
  assert.equal(p.elements.has_ramp.value, "");
  assert.equal(p.token.value, "");
  assert.equal(p.button.disabled, false);
});

test("시설을 바꿨다가 돌아와도 이전 분석 결과를 적용하지 않는다", async () => {
  const { init, run } = load();
  const p = page();
  let resolve;
  const d = { document: p.doc, FormData: FakeFormData,
    fetch: () => new Promise((done) => { resolve = done; }) };
  init(p.doc, d);
  const running = run(p.form, p.box, d);
  p.elements.facility_kind.value = "RESTROOM";
  p.selector.handlers.change();
  p.elements.facility_kind.value = "ENTRANCE";
  p.selector.handlers.change();
  resolve({ json: async () => ok });
  await running;
  assert.equal(p.elements.step_height_cm.value, "");
  assert.equal(p.token.value, "");
});

test("시설 변경 후 이전 분석의 실패 안내를 표시하지 않는다", async () => {
  const { init, run } = load();
  const p = page();
  let reject;
  const d = { document: p.doc, FormData: FakeFormData,
    fetch: () => new Promise((_, fail) => { reject = fail; }) };
  init(p.doc, d);
  const running = run(p.form, p.box, d);
  p.elements.facility_kind.value = "RESTROOM";
  p.selector.handlers.change();
  reject(new Error("old request"));
  await running;
  assert.doesNotMatch(p.status.textContent, /연결이 불안정해요/);
  assert.equal(p.button.disabled, false);
});

test("시설 입력 항목을 전환하는 중에는 이전 시설로 분석을 시작하지 않는다", async () => {
  const { run } = load();
  const p = page();
  const originalGet = p.doc.getElementById;
  p.doc.getElementById = (id) => id === "facility-observations"
    ? { getAttribute: () => "true" } : originalGet(id);
  const sent = [];
  await run(p.form, p.box, deps(p.doc, ok, sent));
  assert.equal(sent.length, 0);
  assert.equal(p.token.value, "");
  assert.match(p.status.textContent, /전환이 끝난 뒤/);
  assert.equal(p.button.disabled, false);
});

test("분석 중 다시 실행해도 중복 요청을 보내거나 버튼을 풀지 않는다", async () => {
  const { run } = load();
  const p = page();
  let resolve;
  let calls = 0;
  const d = { document: p.doc, FormData: FakeFormData,
    fetch: () => { calls += 1; return new Promise((done) => { resolve = done; }); } };
  const running = run(p.form, p.box, d);
  await run(p.form, p.box, d);
  assert.equal(calls, 1);
  assert.equal(p.button.disabled, true);
  resolve({ json: async () => ok });
  await running;
  assert.equal(p.button.disabled, false);
});

test("사진만으로는 알 수 없어 비운 칸은 '추가 설명'에 적으라고 안내한다", async () => {
  const { run } = load();
  const response = { ...ok, fields: { ...ok.fields, step_height_cm: { value: null, certainty: "모름", evidence: "" } },
    needs_text: [{ key: "step_height_cm", label: "입구 단차" }, { key: "entrance_available", label: "입구 이용 가능 여부" }] };
  const p = page();
  await run(p.form, p.box, deps(p.doc, response));
  assert.equal(p.elements.step_height_cm.value, "");
  assert.match(p.elements.step_height_cm.inserted[0].textContent, /사진만으로는 알 수 없어요/);
  // 화면에 없는 칸은 건너뛰고, 안내 문구에는 붙인 칸만
  assert.match(p.status.textContent, /입구 단차은\(는\) 사진만으로는 알 수 없어요/);
  assert.doesNotMatch(p.status.textContent, /입구 이용 가능 여부/);
});

test("주민이 이미 적은 칸에는 '설명 필요' 안내를 붙이지 않는다", async () => {
  const { run } = load();
  const response = { ...ok, fields: { ...ok.fields, step_height_cm: { value: null, certainty: "모름", evidence: "" } },
    needs_text: [{ key: "step_height_cm", label: "입구 단차" }] };
  const p = page({ values: { step_height_cm: "4" } });
  await run(p.form, p.box, deps(p.doc, response));
  assert.equal(p.elements.step_height_cm.inserted.length, 0);
  assert.doesNotMatch(p.status.textContent, /사진만으로는 알 수 없어요/);
});

test("분석 중 사진을 바꾸면 이전 사진 결과와 서명 표를 사용하지 않는다", async () => {
  const { init, run } = load();
  const p = page();
  let resolve;
  const d = { document: p.doc, FormData: FakeFormData,
    fetch: () => new Promise((done) => { resolve = done; }) };
  init(p.doc, d);
  p.token.value = "previous-token";
  const running = run(p.form, p.box, d);
  p.elements.photo.files = [{ name: "new-door.jpg" }];
  p.elements.photo.handlers.change();
  resolve({ json: async () => ok });
  await running;
  assert.equal(p.elements.step_height_cm.value, "");
  assert.equal(p.token.value, "");
  assert.match(p.status.textContent, /사진이 바뀌어/);
});
