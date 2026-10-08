const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(`${__dirname}/../../static/js/reports/report-wizard.js`, "utf8");

function node(props = {}) {
  return {
    value: "", tagName: "INPUT", hidden: false, disabled: false, dataset: {}, children: [], handlers: {},
    attributes: {}, labels: [], options: [], files: [], textContent: "",
    classList: { add() {}, toggle() {} },
    append(...nodes) { this.children.push(...nodes); },
    replaceChildren(...nodes) { this.children = nodes; },
    setAttribute(k, v) { this.attributes[k] = v; },
    getAttribute(k) { return this.attributes[k]; },
    addEventListener(k, fn) { this.handlers[k] = fn; },
    dispatchEvent(event) { this.handlers[event.type]?.(event); },
    querySelectorAll(selector) { return selector === "button" ? this.children : []; },
    querySelector() { return null; }, insertAdjacentElement() {},
    checkValidity() { return true; }, reportValidity() {}, focus() {}, scrollIntoView() {},
    ...props,
  };
}

function page({ errorStep, ready } = {}) {
  const select = (id, value) => node({ id, tagName: "SELECT", value, options: [{ value, textContent: value }], selectedOptions: [{ textContent: value }] });
  const fields = {
    facility_kind: select("id_facility_kind", "ENTRANCE"), ownership: select("id_ownership", "PLACE"),
    target_reference: select("id_target_reference", "default"), facility_name: node(),
    note: node(), location_text: node(), photo_token: node(), photo: node({ files: [{ name: "door.jpg" }] }),
    step_height_cm: node({ id: "id_step_height_cm", name: "step_height_cm", value: "0" }), observed_on: node(),
  };
  fields.photo.checkValidity = () => fields.photo.files.length > 0 || !!fields.photo_token.value;
  const stepFields = [[], [], [fields.photo], [fields.step_height_cm, fields.note], [fields.observed_on]];
  const panels = stepFields.map((inputs, index) => node({
    dataset: { reportStep: String(index + 1) },
    querySelectorAll: () => inputs,
    querySelector: (selector) => selector === ".has-error" && errorStep === index + 1 ? {} : null,
  }));
  const ids = Object.fromEntries([
    "report-heading", "report-progress", "report-next", "report-previous", "report-submit", "report-step-error",
    "report-summary", "facility-switch-status", "report-preview-image", "ai-report-review", "report-manual-fields",
    "report-manual-note", "ai-report-edit", "ai-report-accept", "ai-report-facts",
  ].map((id) => [id, node()]));
  ids["id_facility_kind"] = fields.facility_kind; ids["id_ownership"] = fields.ownership;
  ids["facility-observations"] = node({ querySelectorAll: () => [fields.step_height_cm] });
  ids["report-form"] = node({ elements: fields });
  ids["report-wizard"] = node({ querySelectorAll: () => panels, querySelector: () => node({ textContent: "카페" }) });
  const doc = node({ getElementById: (id) => ids[id], createElement: () => node(), body: node() });
  const context = {
    module: { exports: {} }, dispatchEvent() {},
    Event: class { constructor(type) { this.type = type; } },
    MutationObserver: class { observe() {} },
    PhotoResize: { ready: ready || (() => Promise.resolve()) },
  };
  vm.runInNewContext(source, context);
  context.module.exports.init(doc);
  return { ids, fields, doc, panels, next: () => ids["report-next"].handlers.click(), back: () => ids["report-previous"].handlers.click() };
}

test("사진과 0 관측값을 유지하며 앞뒤로 이동하고 최종 제출한다", async () => {
  const p = page(), originalPhoto = p.fields.photo;
  for (let i = 0; i < 4; i++) await p.next();
  assert.match(p.ids["report-progress"].textContent, /^5/);
  assert.equal(p.ids["report-submit"].hidden, false);
  assert.match(p.ids["report-summary"].children[2].children[1].textContent, /: 0/);
  p.back(); p.back();
  assert.equal(p.fields.photo, originalPhoto);
  assert.equal(p.fields.photo.files[0].name, "door.jpg");
  await p.next(); await p.next();
  let prevented = false;
  p.ids["report-form"].handlers.submit({ preventDefault() { prevented = true; } });
  assert.equal(prevented, false);
});

test("사진 없이 진행을 막고 보관된 사진은 허용한다", async () => {
  const p = page(); p.fields.photo.files = [];
  await p.next(); await p.next(); await p.next();
  assert.match(p.ids["report-progress"].textContent, /^3/);
  assert.equal(p.ids["report-step-error"].hidden, false);
  p.fields.photo_token.value = "valid-server-token";
  await p.next();
  assert.match(p.ids["report-progress"].textContent, /^4/);
});

test("사진 처리 중 중복 클릭을 막고 처리가 끝난 뒤 진행한다", async () => {
  let release;
  const p = page({ ready: () => new Promise((resolve) => { release = resolve; }) });
  await p.next(); await p.next();
  const pending = p.next(); await p.next();
  assert.match(p.ids["report-progress"].textContent, /^3/);
  assert.equal(p.ids["report-next"].disabled, true);
  release(); await pending;
  assert.match(p.ids["report-progress"].textContent, /^4/);
});

test("서버 오류가 있는 단계로 복귀하고 빈 관측값과 설명을 제출하지 않는다", async () => {
  const p = page({ errorStep: 4 }); p.fields.step_height_cm.value = "";
  await p.next();
  assert.match(p.ids["report-progress"].textContent, /^4/);
  assert.match(p.ids["report-step-error"].textContent, /하나 이상/);
  p.fields.note.value = "문이 무거워요";
  await p.next();
  assert.match(p.ids["report-progress"].textContent, /^5/);
});

test("시설 전환 중 단계 이동을 막고 AI 제안을 직접 수정할 수 있다", async () => {
  const p = page({ errorStep: 4 });
  p.ids["facility-observations"].attributes["aria-busy"] = "true";
  await p.next(); assert.match(p.ids["report-progress"].textContent, /^4/);
  p.ids["facility-observations"].attributes["aria-busy"] = "false";
  p.doc.handlers["ai-prefill:complete"]();
  assert.equal(p.ids["report-manual-fields"].hidden, true);
  assert.equal(p.ids["report-next"].hidden, true);
  p.ids["ai-report-edit"].handlers.click();
  assert.equal(p.ids["report-manual-fields"].hidden, false);
  assert.equal(p.fields.step_height_cm.value, "0");
});

test("AI 분석 중에는 확인 단계로 넘어가 오래된 요약을 만들지 않는다", async () => {
  const p = page({ errorStep: 4 });
  p.ids["ai-prefill-button"] = node({ disabled: true });
  await p.next();
  assert.match(p.ids["report-progress"].textContent, /^4/);
  assert.match(p.ids["report-step-error"].textContent, /AI/);
  p.ids["ai-prefill-button"].disabled = false;
  await p.next(); assert.match(p.ids["report-progress"].textContent, /^5/);
});
