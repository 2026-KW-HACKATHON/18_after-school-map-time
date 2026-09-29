/**
 * 지도에서 위치 고르기 (templates/includes/location_picker.html).
 * - 지도를 누르면 그 자리에 표시하고 같은 폼의 #id_lat / #id_lng 에 좌표를 넣는다 (주 방법)
 * - "내 위치로"는 현재 위치로 지도를 옮기고 표시한다 (보조, HTTPS에서만)
 * - 지도를 못 불러와도 "내 위치로"와 위치 설명·좌표 입력으로 대신할 수 있다
 * 지도 SDK는 TeokMap 어댑터(kakao-adapter.js)로만 부른다.
 */
(function () {
  const box = document.getElementById("picker-map");
  const latInput = document.getElementById("id_lat");
  const lngInput = document.getElementById("id_lng");
  if (!box || !latInput || !lngInput) return;
  const locateBtn = document.getElementById("picker-locate");
  const status = document.getElementById("picker-status");

  const FALLBACK = { lat: 37.6262, lng: 127.0587 };  // 지역 정보가 없을 때만 (월계1동 부근)
  const current = () => {
    const lat = parseFloat(latInput.value), lng = parseFloat(lngInput.value);
    return Number.isFinite(lat) && Number.isFinite(lng) ? { lat, lng } : null;
  };
  const center = current() || {
    lat: parseFloat(box.dataset.lat) || FALLBACK.lat,
    lng: parseFloat(box.dataset.lng) || FALLBACK.lng,
  };

  let map = null;

  function mark(pos) {
    if (map) map.setMarkers([{ id: 0, ...pos, className: "judge-NONE picker-marker", label: "선택한 위치" }], () => {});
  }

  function choose(pos, how) {
    latInput.value = pos.lat.toFixed(6);
    lngInput.value = pos.lng.toFixed(6);
    // 좌표 칸이 보이는 화면(운영자)에서도 값이 바뀐 걸 알 수 있게 change 이벤트
    latInput.dispatchEvent(new Event("change", { bubbles: true }));
    lngInput.dispatchEvent(new Event("change", { bubbles: true }));
    mark(pos);
    status.textContent = `${how} 위치를 표시했어요. (${pos.lat.toFixed(5)}, ${pos.lng.toFixed(5)}) 다시 누르면 바뀌어요.`;
  }

  if (locateBtn) {
    locateBtn.addEventListener("click", () => {
      if (!navigator.geolocation) { status.textContent = "이 브라우저는 현재 위치를 지원하지 않아요. 지도를 눌러 주세요."; return; }
      status.textContent = "현재 위치 확인 중...";
      navigator.geolocation.getCurrentPosition(
        ({ coords }) => {
          const pos = { lat: coords.latitude, lng: coords.longitude };
          if (map) map.panTo(pos.lat, pos.lng);
          choose(pos, "현재");
        },
        () => { status.textContent = "현재 위치를 가져오지 못했어요. 지도를 눌러 위치를 표시해 주세요."; },
        { timeout: 8000, enableHighAccuracy: true },
      );
    });
  }

  window.TeokMap.create(box, { ...center, level: 3 })
    .then((created) => {
      map = created;
      if (current()) {
        mark(current());
        status.textContent = "표시된 위치가 맞는지 확인해 주세요. 지도를 누르면 바뀌어요.";
      }
      map.onMapClick((pos) => choose(pos, "선택한"));
    })
    .catch(() => {
      box.textContent = "지도를 불러오지 못했어요. '내 위치로'를 누르거나 위치 설명을 적어 주세요.";
    });
})();
