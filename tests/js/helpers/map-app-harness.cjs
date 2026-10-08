const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(`${__dirname}/../../../places/static/places/js/map-app.js`, "utf8");
const flush = () => new Promise((resolve) => setImmediate(resolve));

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function element(doc) {
  return {
    dataset: {}, children: [], handlers: {}, attrs: {}, hidden: false,
    set textContent(value) { this.children = []; this.text = value; },
    get textContent() { return (this.text || "") + this.children.map((c) => c.textContent).join(""); },
    set innerHTML(value) { this.children = []; this.text = value; },
    appendChild(child) { this.children.push(child); return child; },
    setAttribute(key, value) { this.attrs[key] = value; },
    addEventListener(key, handler) { this.handlers[key] = handler; },
    focus() { doc.activeElement = this; },
    querySelector() { return this.children[0]; },
    scrollIntoView() {},
  };
}

const place = (id, name) => ({
  id, name, lat: 37, lng: 127, category_label: "카페",
  judgment: { code: "ACCESSIBLE", label: "들어갈 수 있어요", hidden_by_default: false },
});
const detail = (name) => ({
  name, place: { entrances: [] }, judgments: [
    { profile: "wheelchair", profile_label: "휠체어", code: "ACCESSIBLE", label: "들어갈 수 있어요" },
    { profile: "stroller", profile_label: "유모차", code: "CONDITIONAL", label: "도움 받으면" },
  ],
});

async function page({ mapFails = false, personalized = false, boundary = null, layers = null, boundaryFails = false, results } = {}) {
  const nodes = {};
  const handlers = {};
  const doc = {
    getElementById: (id) => nodes[id] || (nodes[id] = element(doc)),
    createElement: () => element(doc),
    createTextNode: (text) => ({ textContent: text }),
    querySelectorAll: () => Object.values(nodes).filter(node => node.dataset.count), contains: () => true,
    addEventListener: (key, fn) => { handlers[key] = fn; },
  };
  doc.getElementById("map-app").dataset = {
    region: "test", metaUrl: "/meta/", placesUrl: "/places/",
    detailUrl: "/detail/0/", detailApiUrl: "/api/detail/0/",
  };
  ["ACCESSIBLE", "CONDITIONAL", "UNKNOWN"].forEach(code => { doc.getElementById(`count-${code}`).dataset.count = code; });
  ["map-error", "popup", "empty-state"].forEach((id) => { doc.getElementById(id).hidden = true; });
  const requests = [];
  const map = { setMarkers(items, onClick) { this.items = items; this.onClick = onClick; } };
  map.setBoundary = (data) => { map.boundary = data; return !boundaryFails; };
  map.setBoundaryLayers = (data, callback) => {
    map.layers = data; map.boundaryCallback = callback;
    if (data && !boundaryFails) callback("districts");
    return !boundaryFails;
  };
  doc.getElementById("show-boundary").checked = true;
  doc.getElementById("show-all").checked = true;
  ["boundary-control", "boundary-status", "boundary-credit", "boundary-legend"].forEach(id => doc.getElementById(id).hidden = true);
  let selected = "wheelchair";
  const evaluate = (options) => {
    const request = { options, ...deferred() };
    requests.push(request);
    return request.promise;
  };
  const mobility = personalized ? {
    ready: async () => {}, state: () => ({ selected: [selected] }),
    primaryProfile: () => selected, label: () => selected,
    needsEvaluation: () => true, evaluate,
    selectPreset(key) { selected = key; handlers["mobility:change"](); },
  } : undefined;
  vm.runInNewContext(source, {
    document: doc, navigator: {}, URLSearchParams,
    localStorage: { getItem: () => null, setItem() {} },
    window: { TeokMobility: mobility, TeokMap: { create: async () => {
      if (mapFails) throw new Error("SDK unavailable");
      return map;
    } } },
    api: (url) => {
      if (url.startsWith("/meta/")) return Promise.resolve({
        region: { center: { lat: 37, lng: 127 }, map_level: 3, boundary, boundary_layers: layers },
        profiles: [{ key: "wheelchair", label: "휠체어" }, { key: "stroller", label: "유모차" }],
      });
      const request = { url, ...deferred() };
      requests.push(request);
      return request.promise;
    },
  });
  await flush();
  requests[0].resolve({ results: results || [place(1, "첫 장소"), place(2, "둘째 장소")] });
  await flush();
  return { nodes, requests, map, doc, mobility };
}


module.exports = { page, place, detail, flush };
