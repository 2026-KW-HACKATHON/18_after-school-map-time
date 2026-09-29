/**
 * 지도 어댑터 (카카오맵). 카카오맵 SDK 호출은 이 파일에만 둔다.
 * 다른 지도로 바꿀 때는 같은 모양(TeokMap.create → { setMarkers, clearMarkers, panTo, getCenter, showMyLocation })의
 * 파일을 새로 만들어 이 파일 대신 불러오면 된다 (기획 v2 8장 "지도 SDK 교체").
 *
 * 마커 모양·색은 CSS 클래스(.map-marker.judge-XXX)로만 정한다 → 색만으로 구분하지 않고 모양·아이콘도 같이 (기획 v2 3.1)
 */
(function () {
  function create(element, { lat, lng, level }) {
    return new Promise((resolve, reject) => {
      if (!window.kakao || !window.kakao.maps) {
        reject(new Error("카카오맵 SDK를 불러오지 못했어요."));
        return;
      }
      kakao.maps.load(() => {
        const map = new kakao.maps.Map(element, {
          center: new kakao.maps.LatLng(lat, lng),
          level: level || 4,
        });
        map.addControl(new kakao.maps.ZoomControl(), kakao.maps.ControlPosition.RIGHT);
        // 화면 크기가 바뀌면(폰 가로·세로 전환, 패널 접힘) 지도 크기를 다시 계산 → 타일이 일부만 그려지는 문제 방지
        window.addEventListener("resize", () => map.relayout());
        let overlays = [];
        let myLocation = null;

        resolve({
          /** items: [{ id, lat, lng, className, label, icon }] */
          setMarkers(items, onClick) {
            this.clearMarkers();
            overlays = items.map((item) => {
              const el = document.createElement("button");
              el.type = "button";
              el.className = `map-marker ${item.className || ""}`;
              el.setAttribute("aria-label", item.label);
              el.title = item.label;
              if (item.icon) el.textContent = item.icon;
              el.addEventListener("click", () => onClick(item));
              const overlay = new kakao.maps.CustomOverlay({
                position: new kakao.maps.LatLng(item.lat, item.lng),
                content: el,
                yAnchor: 0.5,
              });
              overlay.setMap(map);
              return overlay;
            });
          },
          clearMarkers() {
            overlays.forEach((o) => o.setMap(null));
            overlays = [];
          },
          panTo(lat, lng) {
            map.panTo(new kakao.maps.LatLng(lat, lng));
          },
          getCenter() {
            const c = map.getCenter();
            return { lat: c.getLat(), lng: c.getLng() };
          },
          showMyLocation(lat, lng) {
            if (myLocation) myLocation.setMap(null);
            const el = document.createElement("div");
            el.className = "my-location";
            el.setAttribute("aria-label", "내 위치");
            myLocation = new kakao.maps.CustomOverlay({ position: new kakao.maps.LatLng(lat, lng), content: el });
            myLocation.setMap(map);
          },
        });
      });
    });
  }

  window.TeokMap = { create };
})();
