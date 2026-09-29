/**
 * 지도 화면. 지도 SDK는 직접 부르지 않고 TeokMap 어댑터(static/js/map/kakao-adapter.js)만 쓴다.
 *
 * 표시 정책 (기획 v2 3.2)
 * - 이동 조건을 고르면 기본으로 "들어갈 수 있어요"·"도움 받으면 들어갈 수 있어요"만 보인다
 * - "모든 장소 보기"를 켜면 어려움(회색)·미확인(점선)도 보인다
 * - 목록은 거리순. "접근성 낮은 순" 정렬이나 "어려운 곳만 보기"는 만들지 않는다
 * - 지도 SDK를 못 불러와도(키 없음 등) 목록은 동작한다
 */
(function () {
  const root = document.getElementById("map-app");
  const urls = {
    meta: root.dataset.metaUrl,
    places: root.dataset.placesUrl,
    // 템플릿이 넘겨준 "/places/0/"의 마지막 0을 실제 id로
    detail: (id) => root.dataset.detailUrl.replace(/\/0\/$/, `/${id}/`),
  };
  const region = root.dataset.region;

  const els = {
    map: document.getElementById("map"),
    profiles: document.getElementById("profile-chips"),
    showAll: document.getElementById("show-all"),
    list: document.getElementById("place-list"),
    status: document.getElementById("list-status"),
  };

  const STORAGE_KEY = "teokeopne.profile";
  const state = { profile: null, showAll: false, center: null, me: null, map: null, places: [] };

  function savedProfile() {
    try { return localStorage.getItem(STORAGE_KEY); } catch (e) { return null; }
  }
  function saveProfile(key) {
    try { localStorage.setItem(STORAGE_KEY, key); } catch (e) { /* 저장 못 해도 동작 */ }
  }

  // 두 좌표 사이 거리(m) — 목록 거리순 정렬용
  function distance(a, b) {
    const R = 6371000;
    const toRad = (d) => (d * Math.PI) / 180;
    const dLat = toRad(b.lat - a.lat);
    const dLng = toRad(b.lng - a.lng);
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }
  function formatDistance(m) {
    return m < 1000 ? `${Math.round(m / 10) * 10}m` : `${(m / 1000).toFixed(1)}km`;
  }

  function renderProfiles(profiles) {
    els.profiles.innerHTML = "";
    profiles.forEach((p) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chip";
      btn.textContent = p.label;
      btn.setAttribute("aria-pressed", String(p.key === state.profile));
      btn.addEventListener("click", () => {
        state.profile = p.key;
        saveProfile(p.key);
        renderProfiles(profiles);
        loadPlaces();
      });
      els.profiles.appendChild(btn);
    });
  }

  function judgmentClass(place) {
    return place.judgment ? `judge-${place.judgment.code}` : "judge-NONE";
  }
  function judgmentIcon(place) {
    return place.judgment && place.judgment.icon === "hand" ? "✋" : "";
  }

  function renderList() {
    const origin = state.me || state.center;
    const rows = state.places
      .map((p) => ({ ...p, dist: origin ? distance(origin, p) : null }))
      .sort((a, b) => (a.dist ?? 0) - (b.dist ?? 0) || a.name.localeCompare(b.name, "ko"));

    els.list.innerHTML = "";
    els.status.textContent = rows.length
      ? `${rows.length}곳${state.me ? " · 내 위치에서 가까운 순" : ""}`
      : state.showAll ? "이 지역에 등록된 장소가 아직 없어요." : "조건에 맞는 장소가 아직 없어요. '모든 장소 보기'를 켜 보세요.";

    rows.forEach((p) => {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.className = "place-item";
      a.href = urls.detail(p.id);

      const badge = document.createElement("span");
      badge.className = `judge-dot ${judgmentClass(p)}`;
      badge.textContent = judgmentIcon(p);
      badge.setAttribute("aria-hidden", "true");

      const body = document.createElement("span");
      body.className = "place-item-body";
      const name = document.createElement("strong");
      name.textContent = p.name;  // 외부 데이터는 textContent로 (XSS 방지)
      const meta = document.createElement("span");
      meta.className = "muted small";
      meta.textContent = [p.category_label, p.dist != null ? formatDistance(p.dist) : ""].filter(Boolean).join(" · ");
      body.append(name, meta);
      if (p.judgment) {
        const label = document.createElement("span");
        label.className = "small";
        label.textContent = p.judgment.label + (p.judgment.reason ? ` — ${p.judgment.reason}` : "");
        body.append(label);
        if (p.judgment.improved) {
          const improved = document.createElement("span");
          improved.className = "badge-positive";
          improved.textContent = "개선 완료";
          body.append(improved);
        }
      }
      a.append(badge, body);
      li.appendChild(a);
      els.list.appendChild(li);
    });
  }

  function renderMarkers() {
    if (!state.map) return;
    state.map.setMarkers(
      state.places.map((p) => ({
        id: p.id,
        lat: p.lat,
        lng: p.lng,
        className: judgmentClass(p),
        icon: judgmentIcon(p),
        label: `${p.name}${p.judgment ? ` · ${p.judgment.label}` : ""}`,
      })),
      (item) => { window.location.href = urls.detail(item.id); },
    );
  }

  async function loadPlaces() {
    const params = new URLSearchParams({ region });
    if (state.profile) params.set("profile", state.profile);
    if (state.showAll) params.set("all", "1");
    els.status.textContent = "불러오는 중...";
    try {
      const data = await api(`${urls.places}?${params}`);
      state.places = data.results;
      renderMarkers();
      renderList();
    } catch (err) {
      els.status.textContent = err.message;
    }
  }

  async function init() {
    const meta = await api(`${urls.meta}?region=${encodeURIComponent(region)}`);
    state.center = meta.region.center;
    const keys = meta.profiles.map((p) => p.key);
    state.profile = keys.includes(savedProfile()) ? savedProfile() : keys[0] || null;
    renderProfiles(meta.profiles);

    els.showAll.addEventListener("change", () => {
      state.showAll = els.showAll.checked;
      loadPlaces();
    });

    try {
      state.map = await window.TeokMap.create(els.map, { ...meta.region.center, level: meta.region.map_level });
    } catch (err) {
      els.map.classList.add("map-unavailable");
      els.map.textContent = "지도를 불러오지 못했어요. 아래 목록으로 볼 수 있어요.";
    }

    // 현재 위치 (HTTPS 또는 localhost에서만 동작). 거부해도 지역 중심 기준으로 동작
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        ({ coords }) => {
          state.me = { lat: coords.latitude, lng: coords.longitude };
          if (state.map) state.map.showMyLocation(state.me.lat, state.me.lng);
          renderList();
        },
        () => {},
        { timeout: 8000 },
      );
    }
    loadPlaces();
  }

  init().catch((err) => { els.status.textContent = err.message; });
})();
