/**
 * 운영자 위치 선택 (와이어프레임 12번 "지도에서 위치 선택").
 * #picker-map 을 누르면 #id_lat / #id_lng 칸에 좌표를 넣고 표시한다. 지도 SDK는 TeokMap 어댑터로만.
 * 지도를 못 불러오면 좌표 칸에 직접 입력하면 된다.
 */
(function () {
  const box = document.getElementById("picker-map");
  const latInput = document.getElementById("id_lat");
  const lngInput = document.getElementById("id_lng");
  if (!box || !latInput || !lngInput) return;

  // 기본 중심: 이미 입력된 좌표 → 없으면 월계1동 중심(대략)
  const start = {
    lat: parseFloat(latInput.value) || 37.6262,
    lng: parseFloat(lngInput.value) || 127.0587,
  };

  window.TeokMap.create(box, { ...start, level: 3 }).then((map) => {
    const mark = (pos) => map.setMarkers([{ id: 0, ...pos, className: "judge-NONE", label: "선택한 위치" }], () => {});
    if (latInput.value && lngInput.value) mark(start);
    map.onMapClick((pos) => {
      latInput.value = pos.lat.toFixed(6);
      lngInput.value = pos.lng.toFixed(6);
      mark(pos);
    });
  }).catch(() => {
    box.textContent = "지도를 불러오지 못했어요. 아래 위도·경도를 직접 입력해 주세요.";
  });
})();
