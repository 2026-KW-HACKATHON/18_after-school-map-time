// 외부 SDK 없이 사용자 입력·비동기 검색 흐름을 검증한다: node --test tests/js/location-picker.test.cjs
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(`${__dirname}/../../static/js/map/location-picker.js`, "utf8");

function element(value = "") {
  return { value, children: [], handlers: {}, events: [], dataset: {}, textContent: "", disabled: true,
    addEventListener(name, fn) { this.handlers[name] = fn; },
    dispatchEvent(event) { this.events.push(event); this.handlers[event.type]?.(event); },
    append(child) { this.children.push(child); },
    replaceChildren() { this.children = []; },
    fire(name, event) { return this.handlers[name](event); },
  };
}
const flush = () => new Promise((resolve) => setImmediate(resolve));
async function setup({ lat = "", lng = "", unavailable = false, common = false, noSearch = false,
                       noTools = false, dataset = {}, adapterMissing = false, searchPlaces = async () => [] } = {}) {
  const fields = Object.fromEntries(["picker-map", "id_lat", "id_lng", "location-status", "place-search",
    "search-place", "place-results", "use-location", "id_suggested_name", "id_suggested_address",
    "id_suggested_phone", "id_suggested_category", "id_suggested_floor"].map((id) => [id, element()]));
  fields.id_lat.value = lat;
  fields.id_lng.value = lng;
  fields["picker-map"].dataset = dataset;
  if (common) {
    fields["picker-status"] = fields["location-status"];
    fields["picker-locate"] = fields["use-location"];
    delete fields["location-status"];
    delete fields["use-location"];
  }
  if (noSearch) ["place-search", "search-place", "place-results"].forEach((id) => delete fields[id]);
  if (noTools) ["picker-status", "picker-locate", "location-status", "use-location"].forEach((id) => delete fields[id]);
  const map = { pins: [], pans: [], setMarkers(items) { this.pins.push([items[0].lat, items[0].lng]); },
    panTo(...pos) { this.pans.push(pos); }, onMapClick(fn) { this.click = fn; }, searchPlaces };
  let center;
  vm.runInNewContext(source, {
    document: { getElementById: (id) => fields[id], createElement: () => element() },
    window: adapterMissing ? {} : { TeokMap: { create: (box, options) => {
      center = options;
      return unavailable ? Promise.reject(new Error()) : Promise.resolve(map);
    } } },
    Event: class { constructor(type, options) { this.type = type; Object.assign(this, options); } },
    navigator: { geolocation: { getCurrentPosition: (success) => success({ coords: { latitude: 37.62, longitude: 127.05 } }) } },
  });
  await flush();
  return { fields, map, center };
}

test("저장된 좌표 복원 및 지도 클릭으로 소수점 6자리 좌표 갱신", async () => {
  const { fields, map } = await setup({ lat: "0", lng: "0" });
  assert.deepEqual(map.pins[0], [0, 0]);
  map.click({ lat: 37.6261234, lng: 127.0587891 });
  assert.equal(fields.id_lat.value, "37.626123");
  assert.equal(fields.id_lng.value, "127.058789");
  assert.match(fields["location-status"].textContent, /37.626123/);
});

test("검색 결과 선택은 이름·주소·업종·전화와 핀을 채우고 이전 층은 비운다", async () => {
  const { fields, map } = await setup({ searchPlaces: async () => [{ place_name: "<img>카페", category_group_code: "CE7",
    road_address_name: "도로명 주소", phone: "02-123", x: "127.05", y: "37.62" }] });
  fields["place-search"].value = "카페";
  fields.id_suggested_floor.value = "3";
  await fields["search-place"].fire("click");
  const button = fields["place-results"].children[0].children[0];
  assert.equal(button.textContent, "<img>카페 · 도로명 주소");
  button.fire("click");
  assert.equal(fields.id_suggested_name.value, "<img>카페");
  assert.equal(fields.id_suggested_category.value, "CAFE");
  assert.equal(fields.id_suggested_floor.value, "");
  assert.equal(fields.id_suggested_phone.value, "02-123");
  assert.equal(fields.id_suggested_address.value, "도로명 주소");
  assert.deepEqual(map.pins.at(-1), [37.62, 127.05]);
});

test("이전 검색 응답이 최신 결과를 덮어쓰지 않는다", async () => {
  const pending = [];
  const { fields } = await setup({ searchPlaces: () => new Promise((resolve) => pending.push(resolve)) });
  fields["place-search"].value = "첫 검색";
  const first = fields["search-place"].fire("click");
  fields["place-search"].value = "다음 검색";
  const second = fields["search-place"].fire("click");
  pending[1]([]);
  await second;
  pending[0]([{ place_name: "옛 결과" }]);
  await first;
  assert.equal(fields["place-results"].children.length, 0);
  assert.match(fields["location-status"].textContent, /검색 결과가 없어요/);
});

test("지도 실패 시에도 현재 위치 입력 가능", async () => {
  const { fields } = await setup({ unavailable: true });
  assert.match(fields["picker-map"].textContent, /지도를 불러오지 못했어요/);
  fields["use-location"].fire("click");
  assert.equal(fields.id_lat.value, "37.620000");
  assert.equal(fields.id_lng.value, "127.050000");
});

test("직접 입력은 지도와 동기화하고 잘못된 좌표는 지도에 전달하지 않는다", async () => {
  const { fields, map } = await setup();
  fields.id_lat.value = "37.5";
  fields.id_lng.value = "127.1";
  fields.id_lng.fire("change");
  assert.deepEqual(map.pins.at(-1), [37.5, 127.1]);
  fields.id_lat.value = "91";
  fields.id_lat.fire("change");
  assert.equal(map.pins.length, 1);
});

test("검색 오류를 안내하고 Enter가 제보 제출로 이어지지 않는다", async () => {
  const { fields } = await setup({ searchPlaces: async () => { throw new Error("검색 실패"); } });
  fields["place-search"].value = "약국";
  let prevented = false;
  fields["place-search"].fire("keydown", { key: "Enter", preventDefault() { prevented = true; } });
  await flush();
  assert.equal(prevented, true);
  assert.equal(fields["location-status"].textContent, "검색 실패");
});

test("develop 공용 UI는 지역 중심과 같은 marker API를 사용하고 좌표 변경을 알린다", async () => {
  const { fields, map, center } = await setup({ common: true, noSearch: true,
    dataset: { lat: "35.123456", lng: "129.123456" } });
  assert.equal(center.lat, 35.123456);
  assert.equal(center.lng, 129.123456);
  map.click({ lat: 35.1, lng: 129.1 });
  assert.equal(map.pins.length, 1);
  assert.match(fields["picker-status"].textContent, /35.100000/);
  assert.equal(fields.id_lat.events[0].type, "change");
  assert.equal(fields.id_lng.events[0].bubbles, true);
  fields["picker-locate"].fire("click");
  assert.deepEqual(map.pins.at(-1), [37.62, 127.05]);
});

test("기존 운영자 UI에 검색·현재 위치 도구가 없어도 지도 클릭과 직접 좌표 입력이 동작한다", async () => {
  const { fields, map } = await setup({ noSearch: true, noTools: true });
  map.click({ lat: 37.6, lng: 127.1 });
  assert.equal(fields.id_lat.value, "37.600000");
  fields.id_lng.value = "127.2";
  fields.id_lng.fire("change");
  assert.deepEqual(map.pins.at(-1), [37.6, 127.2]);
});

test("입력된 좌표가 지역 중심보다 우선하고 지역 중심 0도 유효하다", async () => {
  let setupResult = await setup({ lat: "37", lng: "127", dataset: { lat: "0", lng: "0" } });
  assert.equal(setupResult.center.lat, 37);
  setupResult = await setup({ dataset: { lat: "0", lng: "0" } });
  assert.equal(setupResult.center.lat, 0);
  assert.equal(setupResult.center.lng, 0);
});

test("어댑터가 로드되지 않아도 공용 현재 위치 버튼은 좌표를 채운다", async () => {
  const { fields } = await setup({ common: true, adapterMissing: true });
  assert.match(fields["picker-map"].textContent, /지도를 불러오지 못했어요/);
  fields["picker-locate"].fire("click");
  assert.equal(fields.id_lat.value, "37.620000");
});
