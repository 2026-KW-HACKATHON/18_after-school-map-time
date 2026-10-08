const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(`${__dirname}/../../static/js/map/kakao-adapter.js`, "utf8");

async function setup({ observer = true, sdk = true } = {}) {
  const listeners = {}, observations = [], markers = [];
  const element = { clientWidth: 600, clientHeight: 440 };
  let instance;
  class LatLng { constructor(lat, lng) { this.lat = lat; this.lng = lng; } getLat() { return this.lat; } getLng() { return this.lng; } }
  const kakao = { maps: {
    load: (fn) => fn(), LatLng, ZoomControl: class {}, ControlPosition: { RIGHT: "right" },
    Map: class {
      constructor(_element, options) { instance = this; this.center = options.center; this.layouts = 0; }
      addControl() {}
      getCenter() { return this.center; }
      relayout() { this.layouts++; this.center = new LatLng(0, 0); }
      setCenter(center) { this.center = center; }
      panTo(center) { this.center = center; }
    },
    CustomOverlay: class { constructor(options) { Object.assign(this, options); markers.push(this); } setMap(map) { this.map = map; } },
  } };
  const window = { addEventListener(name, fn) { listeners[name] = fn; } };
  if (sdk) window.kakao = kakao;
  if (observer) window.ResizeObserver = class { constructor(fn) { this.notify = fn; observations.push(this); } observe(target) { this.target = target; } };
  const document = { createElement: () => ({ attrs: {}, handlers: {},
    setAttribute(key, value) { this.attrs[key] = value; }, addEventListener(name, fn) { this.handlers[name] = fn; } }) };
  vm.runInNewContext(source, { window, kakao, document });
  const adapter = await window.TeokMap.create(element, { lat: 37.62, lng: 127.05 });
  return { adapter, map: instance, listeners, observations, markers, element };
}

test("창 크기 변경 후 사용자가 이동한 지도 중심을 보존한다", async () => {
  const p = await setup(); p.adapter.panTo(37.7, 127.1); p.listeners.resize();
  assert.equal(p.map.layouts, 1);
  assert.deepEqual(JSON.parse(JSON.stringify(p.adapter.getCenter())), { lat: 37.7, lng: 127.1 });
});
test("뒤로가기 캐시 복원에서 다시 배치하며 일반 pageshow는 중복 처리하지 않는다", async () => {
  const p = await setup(); p.listeners.pageshow({ persisted: false }); assert.equal(p.map.layouts, 0);
  p.listeners.pageshow({ persisted: true }); assert.equal(p.map.layouts, 1);
  assert.equal(p.adapter.getCenter().lat, 37.62);
});
test("패널·큰 글씨로 지도 영역 크기가 바뀌면 재배치하고 숨겨진 지도는 건너뛴다", async () => {
  const p = await setup(); assert.equal(p.observations[0].target, p.element);
  p.element.clientWidth = 0; p.observations[0].notify(); assert.equal(p.map.layouts, 0);
  p.element.clientWidth = 320; p.observations[0].notify(); assert.equal(p.map.layouts, 1);
  assert.equal(p.adapter.getCenter().lng, 127.05);
});
test("ResizeObserver가 없는 브라우저도 복귀 처리와 마커 선택 기능을 유지한다", async () => {
  const p = await setup({ observer: false }); p.listeners.pageshow({ persisted: true });
  let selected;
  p.adapter.setMarkers([{ id: 1, lat: 37, lng: 127, className: "judge-DIFFICULT", label: "테스트 장소" }], (item) => { selected = item.id; });
  assert.equal(p.markers[0].content.attrs["aria-label"], "테스트 장소");
  p.markers[0].content.handlers.click(); assert.equal(selected, 1);
  p.adapter.clearMarkers(); assert.equal(p.markers[0].map, null);
});
test("SDK 실패는 기존 목록 대체 화면으로 처리할 수 있도록 reject한다", async () => {
  await assert.rejects(setup({ sdk: false }), /SDK/);
});
