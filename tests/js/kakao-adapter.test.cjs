const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(`${__dirname}/../../static/js/map/kakao-adapter.js`, "utf8");

async function setup({ observer = true, sdk = true } = {}) {
  const listeners = {}, observations = [], markers = [], polygons = [];
  const element = { clientWidth: 600, clientHeight: 440 };
  let instance;
  class LatLng { constructor(lat, lng) { this.lat = lat; this.lng = lng; } getLat() { return this.lat; } getLng() { return this.lng; } }
  const kakao = { maps: {
    load: (fn) => fn(), LatLng, ZoomControl: class {}, ControlPosition: { RIGHT: "right" },
    Map: class {
      constructor(_element, options) { instance = this; this.center = options.center; this.level = options.level; this.layouts = 0; }
      getLevel() { return this.level; }
      addControl() {}
      getCenter() { return this.center; }
      relayout() { this.layouts++; this.center = new LatLng(0, 0); }
      setCenter(center) { this.center = center; }
      panTo(center) { this.center = center; }
    },
    CustomOverlay: class { constructor(options) { Object.assign(this, options); markers.push(this); } setMap(map) { this.map = map; } },
    Polygon: class { constructor(options) { Object.assign(this, options); polygons.push(this); } setMap(map) { this.map = map; } },
    event: { addListener(map, name, fn) { listeners[name] = fn; } },
  } };
  const window = { addEventListener(name, fn) { listeners[name] = fn; } };
  if (sdk) window.kakao = kakao;
  if (observer) window.ResizeObserver = class { constructor(fn) { this.notify = fn; observations.push(this); } observe(target) { this.target = target; } };
  const document = { createElement: () => ({ attrs: {}, handlers: {},
    setAttribute(key, value) { this.attrs[key] = value; }, addEventListener(name, fn) { this.handlers[name] = fn; } }) };
  vm.runInNewContext(source, { window, kakao, document });
  const adapter = await window.TeokMap.create(element, { lat: 37.62, lng: 127.05 });
  return { adapter, paths: window.TeokMap.boundaryPaths, map: instance, listeners, observations, markers, polygons, element };
}

test("창 크기 변경 후 사용자가 이동한 지도 중심을 보존한다", async () => {
  const p = await setup(); p.adapter.panTo(37.7, 127.1); p.listeners.resize();
  assert.equal(p.map.layouts, 1);
  assert.deepEqual(JSON.parse(JSON.stringify(p.adapter.getCenter())), { lat: 37.7, lng: 127.1 });
});

const layers = () => ({ detail_max_level: 5,
  overview: { type: "Feature", geometry: { type: "Polygon", coordinates: [ring] } },
  districts: { type: "FeatureCollection", features: ["#7b4fc9", "#245ccc", "#16804a"].map((color) =>
    ({ type: "Feature", properties: { display_color: color }, geometry: { type: "Polygon", coordinates: [ring] } })) },
});
test("확대하면 세 동 색상·2.6px 점선을 표시하고 축소하면 외곽 하나만 표시한다", async () => {
  const p = await setup(), modes = [];
  assert.equal(p.adapter.setBoundaryLayers(layers(), (mode) => modes.push(mode)), true);
  assert.deepEqual(p.polygons.map(x => x.strokeColor), ["#7b4fc9", "#245ccc", "#16804a"]);
  assert.ok(p.polygons.every(x => x.strokeWeight === 2.6 && x.strokeStyle === "dash" && x.fillOpacity === 0));
  p.map.level = 5; p.listeners.zoom_changed(); assert.equal(p.polygons.length, 3);
  p.map.level = 6; p.listeners.zoom_changed();
  assert.equal(p.polygons.filter(x => x.map === p.map).length, 1);
  p.map.level = 7; p.listeners.zoom_changed(); assert.equal(p.polygons.length, 4);
  p.map.level = 5; p.listeners.zoom_changed();
  assert.equal(p.polygons.filter(x => x.map === p.map).length, 3);
  assert.deepEqual(modes, ["districts", "overview", "districts"]);
  assert.equal(p.adapter.getCenter().lat, 37.62);
});
test("축소 초기화·토글 끄기·다시 켜기는 현재 확대 단계와 마커를 보존한다", async () => {
  const p = await setup(); p.map.level = 6;
  p.adapter.setMarkers([{id:1,lat:37,lng:127,label:"장소"}], () => {});
  p.adapter.setBoundaryLayers(layers());
  assert.equal(p.polygons.filter(x => x.map === p.map).length, 1);
  p.adapter.setBoundaryLayers(null); p.map.level = 4; p.listeners.zoom_changed();
  assert.equal(p.polygons.filter(x => x.map === p.map).length, 0);
  p.adapter.setBoundaryLayers(layers());
  assert.equal(p.polygons.filter(x => x.map === p.map).length, 3);
  assert.equal(p.markers[0].map, p.map);
  p.adapter.setBoundary({type:"Polygon",coordinates:[ring]}); p.map.level = 6; p.listeners.zoom_changed();
  assert.equal(p.polygons.filter(x => x.map === p.map).length, 1);
});
test("잘못된 레이어는 일부 경계만 남기지 않으며 이후 정상 표시가 가능하다", async () => {
  const p = await setup();
  for (const invalid of [{...layers(), overview:null}, {...layers(), detail_max_level:"5"},
    {...layers(), districts:{type:"FeatureCollection",features:[]}}]) {
    assert.equal(p.adapter.setBoundaryLayers(invalid), false);
    assert.equal(p.polygons.filter(x => x.map === p.map).length, 0);
  }
  assert.equal(p.adapter.setBoundaryLayers(layers()), true);
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

const ring = [[127, 37], [128, 37], [128, 38], [127, 37]];
test("GeoJSON 경위도 순서와 Polygon 내부 고리를 보존한다", async () => {
  const p = await setup();
  assert.equal(p.adapter.setBoundary({type:"Feature", geometry:{type:"Polygon",coordinates:[ring,ring]}}),true);
  assert.equal(p.polygons.length,1); assert.equal(p.polygons[0].path.length,2);
  assert.equal(p.polygons[0].path[0][0].getLat(),37);assert.equal(p.polygons[0].path[0][0].getLng(),127);
  assert.equal(p.polygons[0].fillOpacity,0);assert.equal(p.polygons[0].strokeStyle,"dash");
});
test("MultiPolygon·FeatureCollection은 여러 경계를 그리며 지도 중심을 바꾸지 않는다", async () => {
  const p=await setup();
  const multi={type:"MultiPolygon",coordinates:[[ring],[ring]]};
  assert.equal(p.adapter.setBoundary({type:"FeatureCollection",features:[{type:"Feature",geometry:multi}]}),true);
  assert.equal(p.polygons.length,2);assert.equal(p.adapter.getCenter().lat,37.62);
});
test("경계 토글과 교체는 마커를 지우지 않는다", async()=>{
  const p=await setup();p.adapter.setMarkers([{id:1,lat:37,lng:127,label:"장소"}],()=>{});
  p.adapter.setBoundary({type:"Polygon",coordinates:[ring]});p.adapter.setBoundary(null);
  assert.equal(p.polygons[0].map,null);assert.equal(p.markers[0].map,p.map);
  p.adapter.setBoundary({type:"Polygon",coordinates:[ring]});p.adapter.clearMarkers();
  assert.equal(p.polygons[1].map,p.map);
});
test("잘못된 경계·좌표·빈 데이터는 지도 동작을 깨뜨리지 않는다",async()=>{
  const p=await setup();
  for(const data of [{type:"Point",coordinates:[127,37]},{type:"Polygon",coordinates:[]},
    {type:"Polygon",coordinates:[[[999,37],[128,37],[128,38],[999,37]]]},
    {type:"Polygon",coordinates:[[[127,37],[128,37],[128,38]]]},
    {type:"MultiPolygon",coordinates:"bad"},{type:"FeatureCollection",features:[null]}]) {
    assert.equal(p.adapter.setBoundary(data),false);
  }
  p.adapter.panTo(37.7,127.1);assert.equal(p.adapter.getCenter().lat,37.7);
});
