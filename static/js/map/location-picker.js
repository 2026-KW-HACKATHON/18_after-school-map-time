/** 주민·운영자 공용 위치 선택. SDK 호출은 TeokMap 어댑터에만 둔다. */
(function initializeLocationPicker() {
  // 시설 종류 전환으로 지도가 처음 추가됐을 때도 공용 초기화를 재사용한다.
  document.addEventListener("location-picker-ready", initializeLocationPicker);
  const box = document.getElementById("picker-map");
  const lat = document.getElementById("id_lat");
  const lng = document.getElementById("id_lng");
  if (!box || !lat || !lng || box.dataset.pickerReady === "true") return;
  box.dataset.pickerReady = "true";
  const status = document.getElementById("picker-status") || document.getElementById("location-status");
  const search = document.getElementById("place-search");
  const searchButton = document.getElementById("search-place");
  const results = document.getElementById("place-results");
  let map;
  let choosing = false;
  let searchVersion = 0;
  const say = (text) => { if (status) status.textContent = text; };
  const position = () => {
    if (!lat.value.trim() || !lng.value.trim()) return null;
    const pos = { lat: Number(lat.value), lng: Number(lng.value) };
    return Number.isFinite(pos.lat) && Number.isFinite(pos.lng) &&
      Math.abs(pos.lat) <= 90 && Math.abs(pos.lng) <= 180 ? pos : null;
  };
  const show = (pos) => {
    if (map) {
      map.setMarkers([{ id: 0, ...pos, className: "judge-NONE picker-marker", label: "선택한 위치" }], () => {});
      map.panTo(pos.lat, pos.lng);
    }
  };
  const select = (pos) => {
    lat.value = pos.lat.toFixed(6);
    lng.value = pos.lng.toFixed(6);
    // 공용 UI를 사용하는 화면의 change 구독자에게도 선택된 좌표를 알린다.
    choosing = true;
    try {
      lat.dispatchEvent(new Event("change", { bubbles: true }));
      lng.dispatchEvent(new Event("change", { bubbles: true }));
    } finally { choosing = false; }
    show(pos);
    say(`선택한 위치: 위도 ${lat.value}, 경도 ${lng.value}`);
  };
  [lat, lng].forEach((input) => input.addEventListener("change", () => {
    if (choosing) return;
    const pos = position();
    if (pos) select(pos);
  }));
  const locate = document.getElementById("picker-locate") || document.getElementById("use-location");
  locate?.addEventListener("click", () => {
    if (!navigator.geolocation) { say("이 브라우저는 위치를 지원하지 않아요."); return; }
    say("위치 확인 중...");
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => select({ lat: coords.latitude, lng: coords.longitude }),
      () => say("위치를 가져오지 못했어요. 장소를 검색하거나 위치 설명을 적어 주세요."),
      { timeout: 8000 },
    );
  });
  const categories = { FD6: "RESTAURANT", CE7: "CAFE", CS2: "STORE", MT1: "STORE",
    PM9: "PHARMACY", HP8: "CLINIC", PO3: "PUBLIC" };
  const fill = (id, value) => {
    const input = document.getElementById(id);
    if (input) input.value = value || "";
  };
  async function findPlaces() {
    if (!search || !results) return;
    const query = search.value.trim();
    const version = ++searchVersion;
    results.replaceChildren();
    if (!query) { say("검색할 장소 이름을 입력해 주세요."); return; }
    if (!map) { say("지도를 불러온 뒤 검색해 주세요."); return; }
    say("장소 검색 중...");
    try {
      const items = await map.searchPlaces(query);
      if (version !== searchVersion) return;
      say(items.length ? `${items.length}개 장소를 찾았어요. 주소를 확인하고 선택해 주세요.` : "검색 결과가 없어요. 다른 검색어나 지도에서 위치를 선택해 주세요.");
      items.forEach((item) => {
        const li = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn place-result";
        button.textContent = `${item.place_name} · ${item.road_address_name || item.address_name}`;
        button.addEventListener("click", () => {
          ++searchVersion;
          fill("id_suggested_name", item.place_name);
          fill("id_suggested_address", item.road_address_name || item.address_name);
          fill("id_suggested_phone", item.phone);
          fill("id_suggested_category", categories[item.category_group_code] || "ETC");
          // 검색 결과에는 층이 없으므로 다른 장소의 층을 재사용하지 않는다.
          fill("id_suggested_floor", "");
          select({ lat: Number(item.y), lng: Number(item.x) });
          results.replaceChildren();
        });
        li.append(button);
        results.append(li);
      });
    } catch (error) {
      if (version === searchVersion) say(error.message);
    }
  }
  searchButton?.addEventListener("click", findPlaces);
  search?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); findPlaces(); }
  });
  const region = { lat: Number(box.dataset?.lat), lng: Number(box.dataset?.lng) };
  const regionValid = Number.isFinite(region.lat) && Number.isFinite(region.lng) &&
    Math.abs(region.lat) <= 90 && Math.abs(region.lng) <= 180;
  const center = position() || (regionValid ? region : { lat: 37.6262, lng: 127.0587 });
  // 어댑터 자체가 로드되지 않은 경우에도 수동 좌표/현재 위치 입력은 사용할 수 있다.
  Promise.resolve().then(() => window.TeokMap.create(box, { ...center, level: 3 }))
    .then((created) => {
      map = created;
      const pos = position();
      if (pos) show(pos);
      map.onMapClick(select);
      if (searchButton) searchButton.disabled = false;
    }).catch(() => {
      box.textContent = "지도를 불러오지 못했어요. 현재 위치 버튼이나 아래 위도·경도 입력을 이용해 주세요.";
      say("지도 연결을 확인해 주세요. 위치 설명만으로도 제보할 수 있어요.");
    });
})();
