/**
 * 지도 홈 (와이어프레임 1·2·3·6번). 지도 SDK는 TeokMap 어댑터(static/js/map/kakao-adapter.js)만 쓴다.
 *
 * 표시 정책 (기획 v2 3.2)
 * - "모든 장소 보기"는 기본 ON으로 정보 없음(내부 어려움 포함, 점선)까지 보인다
 * - OFF이면 "들어갈 수 있어요"·"도움 받으면"만 보인다
 * - 목록은 거리순. "접근성 낮은 순" 정렬·"어려운 곳만 보기"·어려움 개수 집계는 만들지 않는다
 * - 지도 SDK를 못 불러와도 목록·검색·제보는 동작한다 (6번 화면)
 */
(function () {
  const root = document.getElementById("map-app");
  const withId = (url, id) => url.replace(/\/0\/$/, `/${id}/`);  // 템플릿이 넘긴 ".../0/"의 0을 id로
  const urls = {
    meta: root.dataset.metaUrl,
    places: root.dataset.placesUrl,
    // 상세로 갈 때 고른 이동 조건을 붙임 → 사장님 대시보드의 조건별 조회 수 (기획 v2 4.5)
    detail: (id) => withId(root.dataset.detailUrl, id) + (state.profile ? `?profile=${encodeURIComponent(state.profile)}` : ""),
    detailApi: (id) => withId(root.dataset.detailApiUrl, id),
  };
  const region = root.dataset.region;
  const $ = (id) => document.getElementById(id);
  const els = {
    map: $("map"), mapError: $("map-error"), chips: $("profile-chips"), showAll: $("show-all"),
    list: $("place-list"), status: $("list-status"), empty: $("empty-state"), emptyProfile: $("empty-profile"),
    popup: $("popup"), popupBody: $("popup-body"), searchProfile: $("search-profile"),
  };

  const STORAGE_KEY = "teokeopne.profile";
  const state = { profiles: [], profile: null, showAll: els.showAll.checked, center: null, me: null, map: null, all: [], loading: false, error: null };
  let placesRequest = 0, popupRequest = 0;
  const mobility = () => window.TeokMobility?.state() ? window.TeokMobility : null;

  // ── 작은 도우미 ─────────────────────────────────────────
  function savedProfile() {
    try { return localStorage.getItem(STORAGE_KEY); } catch (e) { return null; }
  }
  function saveProfile(key) {
    try { localStorage.setItem(STORAGE_KEY, key); } catch (e) { /* 저장 못 해도 동작 */ }
  }
  function el(tag, attrs = {}, text) {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
    if (text != null) node.textContent = text;  // 외부 데이터는 textContent로 (XSS 방지)
    return node;
  }
  function distance(a, b) {
    const R = 6371000, rad = (d) => (d * Math.PI) / 180;
    const dLat = rad(b.lat - a.lat), dLng = rad(b.lng - a.lng);
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }
  const formatDistance = (m) => (m < 1000 ? `${Math.round(m / 10) * 10}m` : `${(m / 1000).toFixed(1)}km`);
  const profileLabel = () => mobility()?.label() || (state.profiles.find((p) => p.key === state.profile) || {}).label || "";
  const displayCode = (j) => j?.display_code || (j?.code === "DIFFICULT" ? "UNKNOWN" : j?.code);
  const judgmentClass = (p) => (p.judgment ? `judge-${displayCode(p.judgment)}` : "judge-NONE");
  const judgmentIcon = (p) => (p.judgment && p.judgment.icon === "hand" ? "✋" : "");
  // 이전 API 응답의 UNKNOWN.hidden_by_default=false도 OFF에서 숨긴다.
  const visiblePlaces = () => state.all.filter((p) => state.showAll || !p.judgment ||
    (displayCode(p.judgment) !== "UNKNOWN" && !p.judgment.hidden_by_default));

  // ── 이동 조건 칩 ───────────────────────────────────────
  function renderProfiles() {
    els.chips.innerHTML = "";
    state.profiles.forEach((p) => {
      const btn = el("button", { type: "button", class: "chip", "aria-pressed": String(p.key === state.profile) }, p.label);
      btn.addEventListener("click", () => {
        if (mobility()) { mobility().selectPreset(p.key); return; }
        state.profile = p.key;
        saveProfile(p.key);
        renderProfiles();
        loadPlaces();
      });
      els.chips.appendChild(btn);
    });
    els.searchProfile.value = state.profile || "";
  }

  // ── 상태 요약 (어려움 개수는 세지 않음) ────────────────
  function renderSummary() {
    const counts = { ACCESSIBLE: 0, CONDITIONAL: 0, UNKNOWN: 0 };
    state.all.forEach((p) => { const code = displayCode(p.judgment); if (code in counts) counts[code] += 1; });
    document.querySelectorAll("[data-count]").forEach((node) => {
      node.textContent = `${counts[node.dataset.count]}곳`;
    });
  }

  // ── 목록 ───────────────────────────────────────────────
  function renderList() {
    const origin = state.me || state.center;
    const rows = visiblePlaces()
      .map((p) => ({ ...p, dist: origin ? distance(origin, p) : null }))
      .sort((a, b) => (a.dist ?? 0) - (b.dist ?? 0) || a.name.localeCompare(b.name, "ko"));

    els.list.innerHTML = "";
    els.empty.hidden = state.loading || state.error !== null || rows.length > 0;
    els.emptyProfile.textContent = profileLabel();
    els.status.textContent = state.loading ? "불러오는 중..." : state.error !== null ? state.error
      : rows.length ? `${rows.length}곳${state.me ? " · 내 위치에서 가까운 순" : " · 가까운 순"}` : "";

    rows.forEach((p) => {
      const a = el("a", { class: "place-item", href: urls.detail(p.id) });
      a.appendChild(el("span", { class: `judge-dot ${judgmentClass(p)}`, "aria-hidden": "true" }, judgmentIcon(p)));
      const body = el("span", { class: "place-item-body" });
      body.appendChild(el("strong", {}, p.name));
      body.appendChild(el("span", { class: "muted small" },
        [p.category_label, p.dist != null ? formatDistance(p.dist) : ""].filter(Boolean).join(" · ")));
      if (p.judgment) {
        body.appendChild(el("span", { class: "small" }, p.judgment.label + (p.judgment.reason ? ` — ${p.judgment.reason}` : "")));
        if (p.judgment.improved) body.appendChild(el("span", { class: "badge-positive" }, "개선 완료"));
      }
      a.appendChild(body);
      const li = el("li");
      li.appendChild(a);
      els.list.appendChild(li);
    });
  }

  // ── 지도 마커 + 팝업 (와이어프레임 3번) ───────────────
  function renderMarkers() {
    if (!state.map) return;
    state.map.setMarkers(
      visiblePlaces().map((p) => ({
        id: p.id, lat: p.lat, lng: p.lng, className: judgmentClass(p), icon: judgmentIcon(p),
        label: `${p.name}${p.judgment ? ` · ${p.judgment.label}` : ""}`,
      })),
      (item) => openPopup(item.id),
    );
  }

  const POPUP_FIELDS = ["step_height_cm", "step_count", "has_ramp", "door_width_cm", "door_type"];

  // 팝업을 연 마커 버튼 — 닫을 때 키보드 포커스를 그 자리로 돌려준다
  let popupOpener = null;

  function closePopup(restoreFocus = true) {
    popupRequest += 1;
    els.popup.hidden = true;
    if (restoreFocus && popupOpener && document.contains(popupOpener)) popupOpener.focus();
    popupOpener = null;
  }

  async function openPopup(id) {
    const request = ++popupRequest;
    const brief = state.all.find((p) => p.id === id);
    popupOpener = document.activeElement;
    els.popup.hidden = false;
    els.popup.focus();  // 스크린리더가 팝업 내용을 바로 읽도록
    els.popupBody.textContent = "불러오는 중...";
    try {
      const d = await api(urls.detailApi(id));
      if (request !== popupRequest) return;
      let j = d.judgments.find((x) => x.profile === state.profile) || d.judgments[0];
      if (mobility()?.needsEvaluation()) {
        const data = await mobility().evaluate({ region, place_ids: [id] });
        j = { ...data.results[0].judgment, profile_label: mobility().label() };
      }
      if (request !== popupRequest) return;
      const entrance = (d.place.entrances || [])[0];
      const facts = entrance
        ? entrance.fields.filter((f) => POPUP_FIELDS.includes(f.key) && f.value != null).map((f) => `${f.label} ${f.value}${f.unit}`)
        : [];
      const origin = state.me || state.center;

      els.popupBody.innerHTML = "";
      const head = el("div", { class: "popup-head" });
      head.appendChild(el("strong", {}, d.name));
      head.appendChild(el("a", { href: urls.detail(id), class: "btn" }, "상세 보기"));
      els.popupBody.appendChild(head);
      els.popupBody.appendChild(el("p", { class: "muted small" },
        [j ? j.profile_label : "", brief && origin ? `거리 ${formatDistance(distance(origin, brief))}` : ""].filter(Boolean).join(" · ")));
      if (j) {
        const status = el("p", {});
        status.appendChild(el("span", { class: `judge-dot judge-${displayCode(j)}`, "aria-hidden": "true" }, j.icon === "hand" ? "✋" : ""));
        status.appendChild(document.createTextNode(` ${j.label}`));
        els.popupBody.appendChild(status);
        if (j.personalized) els.popupBody.appendChild(el("p", { class: "small" }, j.explanation));
      }
      els.popupBody.appendChild(el("p", { class: "small" }, facts.length ? facts.join(" · ") : "아직 확인된 입구 정보가 없어요."));
      els.popupBody.appendChild(el("p", { class: "muted small" },
        d.last_checked ? `${d.last_checked.slice(0, 10)} 확인` : "확인 정보 없음"));
    } catch (err) {
      if (request === popupRequest) els.popupBody.textContent = err.message;
    }
  }
  $("popup-close").addEventListener("click", () => closePopup());
  els.popup.addEventListener("keydown", (e) => { if (e.key === "Escape") closePopup(); });

  // ── 데이터 불러오기 ────────────────────────────────────
  async function loadPlaces() {
    const request = ++placesRequest;
    closePopup(false);
    // 전체(all=1)를 한 번 받아 화면에서 거른다 → 요약 개수와 '모든 장소 보기'를 서버 왕복 없이
    const params = new URLSearchParams({ region, all: "1" });
    if (state.profile) params.set("profile", state.profile);
    state.all = [];
    state.loading = true;
    state.error = null;
    renderSummary(); renderMarkers(); renderList();
    try {
      const data = mobility()?.needsEvaluation()
        ? await mobility().evaluate({ region })
        : await api(`${urls.places}?${params}`);
      if (request !== placesRequest) return;
      state.all = data.results;
      state.loading = false;
      renderSummary();
      renderMarkers();
      renderList();
    } catch (err) {
      if (request !== placesRequest) return;
      state.all = [];
      state.loading = false;
      state.error = err.message;
      renderSummary(); renderMarkers(); renderList();
    }
  }

  function setShowAll(value) {
    state.showAll = value;
    els.showAll.checked = value;
    renderMarkers();
    renderList();
  }

  async function init() {
    const meta = await api(`${urls.meta}?region=${encodeURIComponent(region)}`);
    state.center = meta.region.center;
    state.profiles = meta.profiles;
    try { await window.TeokMobility?.ready(); } catch (e) { /* 개인화만 실패하면 기본 서비스는 유지 */ }
    const keys = meta.profiles.map((p) => p.key);
    state.profile = mobility() ? mobility().primaryProfile() : keys.includes(savedProfile()) ? savedProfile() : keys[0] || null;
    renderProfiles();
    document.addEventListener("mobility:change", () => {
      if (!mobility()) return;
      state.profile = mobility().primaryProfile(); renderProfiles(); loadPlaces();
    });

    els.showAll.addEventListener("change", () => setShowAll(els.showAll.checked));
    $("empty-show-all").addEventListener("click", () => setShowAll(true));
    $("empty-change").addEventListener("click", () => {
      const first = els.chips.querySelector("button");
      if (first) first.focus();
      els.chips.scrollIntoView({ behavior: "smooth", block: "center" });
    });

    try {
      state.map = await window.TeokMap.create(els.map, { ...meta.region.center, level: meta.region.map_level });
    } catch (err) {
      els.mapError.hidden = false;  // 와이어프레임 6번
    }

    const boundaryToggle = $("show-boundary"), boundaryStatus = $("boundary-status"), boundaryCredit = $("boundary-credit");
    const boundaryLegend = $("boundary-legend");
    if (boundaryToggle && state.map?.setBoundary) {
      if (meta.region.boundary) {
        $("boundary-control").hidden = false;
        const layered = meta.region.boundary_layers && state.map.setBoundaryLayers;
        const boundaryFeedback = (mode) => {
          const valid = mode !== "error";
          boundaryStatus.hidden = valid;
          boundaryStatus.textContent = valid ? "" : "지역 경계를 표시하지 못했어요. 지도와 장소 목록은 계속 이용할 수 있어요.";
          boundaryLegend.hidden = !valid || !boundaryToggle.checked || !layered;
          boundaryLegend.textContent = mode === "districts"
            ? "월계1동: 보라 · 월계2동: 파랑 · 월계3동: 초록 (점선)"
            : "월계1·2·3동 전체 외곽 · 확대하면 동별 구역을 볼 수 있어요.";
        };
        const drawBoundary = () => {
          const valid = layered
            ? state.map.setBoundaryLayers(boundaryToggle.checked ? meta.region.boundary_layers : null, boundaryFeedback)
            : state.map.setBoundary(boundaryToggle.checked ? meta.region.boundary : null);
          if (!valid) boundaryFeedback("error");
          else if (!boundaryToggle.checked || !layered) boundaryFeedback("hidden");
        };
        boundaryToggle.addEventListener("change", drawBoundary);
        drawBoundary();
        const properties = meta.region.boundary.properties;
        if (properties?.attribution) {
          boundaryCredit.textContent = `${properties.attribution} · ${properties.boundary_date || ""} · ${properties.license || ""} (안내용 경계)`;
          boundaryCredit.hidden = false;
        }
      } else {
        boundaryStatus.textContent = "이 지역의 경계 정보는 아직 없어요."; boundaryStatus.hidden = false;
      }
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
