// 사진·공통 입력 보존, 종류별 제출, 비동기 응답 순서·실패를 외부 라이브러리 없이 검증한다.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(`${__dirname}/../../static/js/reports/facility-switcher.js`, "utf8");

function element(value = "") {
  return { value, disabled: false, hidden: false, handlers: {}, textContent: "", children: [],
    addEventListener(type, fn) { this.handlers[type] = fn; },
    dispatchEvent(event) { this.handlers[event.type]?.(event); },
    setAttribute(name, value) { this[name] = value; },
    replaceChildren(...children) { this.children = children; },
  };
}
function fields(names) { return names.map((name) => ({ ...element(), name })); }
function response(kind, ownership = "PLACE", targets) {
  targets ||= kind === "ENTRANCE" && ownership === "PLACE" ?
    [["default", "주 출입구"], ["new", "새 시설 제안"]] : [["new", "새 시설 제안"]];
  const keys = { ENTRANCE: ["step_height_cm"], ELEVATOR: ["facility_available", "facility_braille"],
    RAMP: ["facility_available", "facility_width_cm"] }[kind];
  return { ok: true, async json() { return { kind, ownership, label: kind, targets, target: targets[0][0],
    fields_html: keys.join(","), location_html: "지도", photo_label: `${kind} 사진`, photo_help: "시설 사진을 올려 주세요.", show_picker: true }; } };
}
function setup(fetcher = async (url) => response(url.searchParams.get("facility_kind"), url.searchParams.get("ownership"))) {
  const ids = Object.fromEntries(["facility-selector", "report-form", "id_facility_kind", "id_ownership",
    "report-kind", "report-ownership", "facility-observations", "id_target_reference", "id_facility_name",
    "facility-switch-status", "report-location", "picker-help", "id_lat", "id_photo_helptext"].map((id) => [id, element()]));
  ids.id_facility_kind.value = ids["report-kind"].value = "ENTRANCE";
  ids.id_ownership.value = ids["report-ownership"].value = "PLACE";
  ids.id_target_reference.value = "default";
  let current = fields(["step_height_cm"]);
  current[0].value = "4";
  const observations = ids["facility-observations"];
  observations.querySelectorAll = () => current;
  Object.defineProperty(observations, "innerHTML", { set(html) { current = fields(html.split(",")); } });
  const submit = element();
  const labels = [element(), element()];
  const photoLabel = element();
  const common = { photo: { files: [{ name: "입구.jpg" }] }, note: element("직접 확인"),
    phone: element("02-123-4567"), lat: ids.id_lat, lng: element("127.05"), place: element("12") };
  common.lat.value = "37.62";
  ids["report-form"].querySelector = (query) => {
    if (query === '[type="submit"]') return submit;
    if (query === 'label[for="id_photo"]') return photoLabel;
    return common[query.match(/name="([^"]+)"/)?.[1]] || null;
  };
  ids["report-form"].querySelectorAll = () => labels;
  const requests = [];
  vm.runInNewContext(source, { document: { getElementById: (id) => ids[id], createElement: () => element(), dispatchEvent() {} },
    window: { location: { href: "http://localhost/report/new/" }, dispatchEvent() {} }, URL, Map,
    Event: class { constructor(type) { this.type = type; } },
    fetch: async (url) => { requests.push(url); return fetcher(url); },
  });
  return { ids, common, requests, submit, fields: () => current,
    async change(kind, owner = "PLACE") {
      ids.id_facility_kind.value = kind;
      ids.id_ownership.value = owner;
      return ids.id_facility_kind.handlers.change();
    } };
}

test("종류가 자동 전환되고 사진·좌표·전화번호·설명과 이전 시설 입력은 보존된다", async () => {
  const state = setup();
  const photo = state.common.photo;
  const files = photo.files;
  state.ids.id_facility_name.value = "기존 입구";
  await state.change("ELEVATOR");
  assert.deepEqual(state.fields().map((field) => field.name), ["facility_available", "facility_braille"]);
  state.fields()[0].value = "false";
  state.ids.id_facility_name.value = "동쪽 E/V";
  await state.change("RAMP");
  assert.equal(state.fields()[0].value, "false");
  assert.equal(state.ids["report-kind"].value, "RAMP");
  assert.equal(state.common.photo, photo);
  assert.equal(state.common.photo.files, files);
  assert.equal(state.common.note.value, "직접 확인");
  assert.equal(state.common.phone.value, "02-123-4567");
  assert.equal(state.common.lat.value, "37.62");
  await state.change("ENTRANCE");
  assert.equal(state.fields()[0].value, "4");
  assert.equal(state.ids.id_target_reference.value, "default");
  assert.equal(state.ids.id_facility_name.value, "기존 입구");
  await state.change("ELEVATOR");
  assert.equal(state.ids.id_facility_name.value, "동쪽 E/V");
  assert.equal(state.fields()[0].value, "false");
});

test("소속이 바뀌면 해당 시설 목록과 POST 소속도 바뀌며 장소 식별자는 유지된다", async () => {
  const state = setup(async (url) => response("ELEVATOR", url.searchParams.get("ownership"),
    url.searchParams.get("ownership") === "BUILDING" ? [["facility:9", "공용 E/V"], ["new", "새 시설 제안"]] : undefined));
  await state.change("ELEVATOR", "BUILDING");
  assert.equal(state.requests[0].searchParams.get("place"), "12");
  assert.equal(state.ids["report-ownership"].value, "BUILDING");
  assert.equal(state.ids.id_target_reference.value, "facility:9");
  assert.equal(state.ids.id_target_reference.children[0].textContent, "공용 E/V");
});

test("늦게 도착한 이전 종류 응답은 최신 선택을 덮어쓰지 않는다", async () => {
  const pending = [];
  const state = setup((url) => new Promise((resolve) => pending.push({ url, resolve })));
  const first = state.change("ELEVATOR");
  const second = state.change("RAMP");
  assert.equal(state.submit.disabled, true);
  let blocked = false;
  state.ids["report-form"].handlers.submit({ preventDefault() { blocked = true; } });
  assert.equal(blocked, true);
  pending[1].resolve(response("RAMP"));
  await second;
  pending[0].resolve(response("ELEVATOR"));
  await first;
  assert.equal(state.ids["report-kind"].value, "RAMP");
  assert.equal(state.submit.disabled, false);
  assert.deepEqual(state.fields().map((field) => field.name), ["facility_available", "facility_width_cm"]);
});

test("통신 오류·로그인 만료 응답은 원래 선택·입력과 제출 기능을 복원한다", async () => {
  for (const fetcher of [async () => { throw new Error("offline"); },
    async () => ({ ok: false }), async () => ({ ok: true, async json() { throw new Error("login HTML"); } })]) {
    const state = setup(fetcher);
    await state.change("ELEVATOR");
    assert.equal(state.ids.id_facility_kind.value, "ENTRANCE");
    assert.equal(state.ids["report-kind"].value, "ENTRANCE");
    assert.equal(state.fields()[0].value, "4");
    assert.equal(state.fields()[0].disabled, false);
    assert.equal(state.submit.disabled, false);
    assert.match(state.ids["facility-switch-status"].textContent, /다시 선택/);
  }
});

test("전환 중 원래 종류를 다시 선택하면 진행 중 응답을 무시한다", async () => {
  let resolve;
  const state = setup(() => new Promise((done) => { resolve = done; }));
  const pending = state.change("ELEVATOR");
  await state.change("ENTRANCE");
  resolve(response("ELEVATOR"));
  await pending;
  assert.equal(state.ids["report-kind"].value, "ENTRANCE");
  assert.equal(state.fields()[0].value, "4");
  assert.equal(state.submit.disabled, false);
});
