/* 이동 설정은 회원 저장값 / 익명 브라우저 저장값을 분리한다. 판정 수치는 서버 Rule 기본값을 사용한다. */
(function () {
  "use strict";
  const GUEST_KEY = "teokeopne.mobility.guest.v1";
  const LEGACY_KEY = "teokeopne.profile";
  const clone = (data) => JSON.parse(JSON.stringify(data));
  const preset = (meta, key) => meta.presets.find((p) => p.key === key);
  function actualPreset(meta, data, key) {
    const p = preset(meta, key);
    return p.companion ? preset(meta, data.companions[key] || p.profile) : p;
  }
  function fieldsFor(meta, data, key) { return actualPreset(meta, data, key).fields; }
  function validateState(data, meta) {
    if (!data || Array.isArray(data) || data.version !== 1 || typeof data.version !== "number" ||
        Object.keys(data).some((k) => !["version", "rule_version", "selected", "overrides", "companions"].includes(k)) ||
        !Array.isArray(data.selected) || !data.selected.length || new Set(data.selected).size !== data.selected.length ||
        data.selected.some((k) => !preset(meta, k))) throw new Error("저장된 이동 조건을 복원할 수 없어요.");
    const overrides = data.overrides || {}, companions = data.companions || {};
    if (typeof overrides !== "object" || Array.isArray(overrides) || !overrides || typeof companions !== "object" || Array.isArray(companions) || !companions)
      throw new Error("이동 조건의 형식을 확인해 주세요.");
    Object.entries(companions).forEach(([key, value]) => {
      if (!preset(meta, key)?.companion || !preset(meta, value) || preset(meta, value).companion)
        throw new Error("동반자의 이동 조건을 확인해 주세요.");
    });
    const clean = {};
    Object.entries(overrides).forEach(([key, values]) => {
      if (!preset(meta, key) || !values || typeof values !== "object" || Array.isArray(values)) throw new Error("개인 설정을 확인해 주세요.");
      const allowed = fieldsFor(meta, { companions }, key);
      const entry = {};
      Object.entries(values).forEach(([field, value]) => {
        if (!allowed.includes(field)) throw new Error("이 Preset에서 지원하지 않는 설정이에요.");
        if (value === null) return;
        const spec = meta.fields[field];
        if (spec.type === "bool") {
          if (typeof value !== "boolean") throw new Error(`${spec.label}: 필요·가능 여부를 선택해 주세요.`);
          entry[field] = value;
        } else {
          if (!["string", "number"].includes(typeof value) || !/^\d+(?:\.\d)?$/.test(String(value)) ||
              !Number.isFinite(Number(value)) || Number(value) < spec.min || Number(value) > spec.max)
            throw new Error(`${spec.label}: ${spec.min}~${spec.max}${spec.unit} 범위의 수치를 확인해 주세요.`);
          entry[field] = String(Number(value));
        }
      });
      if (Object.keys(entry).length) clean[key] = entry;
    });
    if (data.rule_version != null && (!Number.isInteger(data.rule_version) || data.rule_version < 1)) throw new Error("기준 버전을 확인해 주세요.");
    return { version: 1, rule_version: data.rule_version ?? null, selected: [...data.selected], overrides: clean, companions: { ...companions } };
  }
  function restoreGuest(storage, meta) {
    let warning = "", settings = clone(meta.settings);
    try {
      const raw = storage.getItem(GUEST_KEY);
      if (raw) settings = validateState(JSON.parse(raw), meta);
      else {
        const old = storage.getItem(LEGACY_KEY);
        if (preset(meta, old)) settings.selected = [old];
      }
    } catch (e) { warning = "저장된 이동 조건을 복원할 수 없어 기본값을 표시해요. 저장하면 복구할 수 있어요."; }
    if (settings.rule_version !== meta.rule_version && !warning) warning = "기본 기준이 바뀌었어요. 입력한 값만 유지하고 나머지는 최신 기본값을 사용해요.";
    return { settings, warning };
  }
  function switchPreset(data, key) {
    const out = clone(data);
    out.selected = out.selected.includes(key) ? [key, ...out.selected.filter((k) => k !== key)] : [key, ...out.selected.slice(1).filter((k) => k !== key)];
    return out;
  }
  function resetPreset(data, key) { const out = clone(data); delete out.overrides[key]; return out; }
  function switchCompanion(data, key, value) {
    const out = resetPreset(data, key); out.companions[key] = value; return out;
  }
  function referenceValues(meta, data, route, directStep) {
    const out = {}, allowed = fieldsFor(meta, data, data.selected[0]);
    if (!route || route.incomplete || route.unavailable) return out;
    // 장소 관측값이 개인의 능력·필요 여부를 증명하지 않는다. 수치만 명시적으로 가져온다.
    for (const key of ["max_step_height_cm", "min_door_width_cm"]) {
      if (!allowed.includes(key) || (key === "max_step_height_cm" && !directStep)) continue;
      const value = route.values?.[key], spec = meta.fields[key];
      if (value != null && ["string", "number"].includes(typeof value) && /^\d+(?:\.\d)?$/.test(String(value)) &&
          Number.isFinite(Number(value)) && Number(value) >= spec.min && Number(value) <= spec.max) out[key] = String(Number(value));
    }
    return out;
  }
  const helpers = { GUEST_KEY, validateState, restoreGuest, switchPreset, resetPreset, switchCompanion, fieldsFor, referenceValues };
  if (typeof module !== "undefined" && module.exports) module.exports = helpers;
  if (typeof document === "undefined") return;
  const root = document.querySelector("[data-mobility]");
  if (!root) return;
  const $ = (name) => root.querySelector(`[data-mobility-${name}]`);
  const dialog = $("dialog"), form = $("form"), openButton = $("open"), warning = $("warning");
  let meta = null, settings = null, draft = null, busy = false, viewRequest = 0, persistenceWarning = "";
  let referencePlaces = null, referenceData = null, referenceRequest = 0, referenceListRequest = 0;
  const serverSearchProfile = document.getElementById("search-profile")?.value;
  const storage = () => { try { return localStorage; } catch (e) { return { getItem: () => null, setItem: () => { throw e; } }; } };
  let saveQueue = Promise.resolve();
  const text = (name, value) => { $(name).textContent = value || ""; };
  const create = (tag, content, attrs = {}) => {
    const node = document.createElement(tag);
    if (content != null) node.textContent = content;
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
  };
  function option(select, value, label) { select.appendChild(create("option", label, { value })); }
  function label() {
    return settings.selected.map((key) => {
      const p = preset(meta, key);
      return p.label + (p.companion ? ` (${actualPreset(meta, settings, key).label})` : "");
    }).join(" + ");
  }
  function needsEvaluation() {
    return settings.selected.length > 1 || settings.selected.some((key) => {
      const p = preset(meta, key);
      return p.profile !== key || Object.keys(settings.overrides[key] || {}).length > 0;
    });
  }
  function primaryProfile() { return actualPreset(meta, settings, settings.selected[0]).profile; }
  function publish() {
    const primary = preset(meta, settings.selected[0]), actual = actualPreset(meta, settings, primary.key);
    const brief = `${primary.label}${settings.selected.length > 1 ? ` 외 ${settings.selected.length - 1}개 조건` : ""}`;
    text("summary", root.dataset.mode === "map" && !needsEvaluation() ? "" : `${brief}${primary.recommendation ? ` · 적용 기준: ${actual.label}` : " · 내 조건 적용"}`);
    $("more").value = ["WITH_CHILD", "ASSISTED_COMPANION", "LIMITED_WALKING"].includes(settings.selected[0]) ? settings.selected[0] : "";
    if (root.dataset.mode === "search") document.getElementById("search-profile").value = primaryProfile();
    document.dispatchEvent(new CustomEvent("mobility:change", { detail: clone(settings) }));
    refreshView();
  }
  async function persist(data) {
    persistenceWarning = "";
    const validated = validateState(data, meta);
    validated.rule_version = meta.rule_version;
    if (meta.authenticated) {
      // 회원 설정을 익명 localStorage로 옮기지 않는다. 순서대로 저장해 이전 요청의 덮어쓰기를 방지한다.
      const saving = saveQueue.catch(() => {}).then(() => api(root.dataset.preferencesUrl, { method: "PUT", body: validated }));
      saveQueue = saving;
      return (await saving).settings;
    }
    try { storage().setItem(GUEST_KEY, JSON.stringify(validated)); }
    catch (e) { persistenceWarning = "브라우저 저장을 사용할 수 없어요. 현재 화면에서는 적용되지만 새로고침 후에는 복원되지 않아요."; }
    return validated;
  }
  async function apply(data) { settings = await persist(data); publish(); }
  async function selectPreset(key) {
    if (!meta || !preset(meta, key)) return;
    try { await apply({ ...clone(settings), selected: [key] }); text("warning", persistenceWarning); }
    catch (e) { text("warning", e.message); }
  }
  function renderDraft(resetReference = true) {
    if (resetReference) clearReference();
    const key = draft.selected[0], p = preset(meta, key), actual = actualPreset(meta, draft, key);
    $("preset").value = key;
    $("companion-box").hidden = !p.companion;
    $("companion").value = draft.companions[key] || p.profile;
    text("recommendation", p.recommendation ? `${p.recommendation} 현재 적용 기준: ${actual.label}` : "");
    $("recommendation").hidden = !p.recommendation;
    const fields = $("fields"); fields.replaceChildren();
    fieldsFor(meta, draft, key).forEach((field) => {
      const spec = meta.fields[field], current = draft.overrides[key]?.[field], defaultValue = actual.defaults[field];
      const container = create("div", null, { class: "field mobility-field" });
      const id = `mobility-field-${field}`;
      container.appendChild(create("label", `${spec.label}${spec.unit ? ` (${spec.unit})` : ""} · ${spec.preference ? "선호" : "필수 조건"}`, { for: id }));
      let input;
      if (spec.type === "number") {
        input = create("input", null, { id, type: "number", min: spec.min, max: spec.max, step: spec.step, inputmode: "decimal", placeholder: defaultValue == null ? "입력하지 않으면 기본 규칙" : `기본값 ${defaultValue}${spec.unit}` });
        input.value = current ?? "";
      } else {
        input = create("select", null, { id });
        option(input, "", "기본 규칙 사용");
        option(input, "true", field === "can_use_stairs" ? "가능" : spec.preference ? "선호" : "필요");
        option(input, "false", field === "can_use_stairs" ? "불가" : spec.preference ? "선호하지 않음" : "필요하지 않음");
        input.value = current == null ? "" : String(current);
      }
      input.setAttribute("aria-describedby", `${id}-help`);
      const update = () => {
        draft.overrides[key] ||= {};
        if (input.value === "") delete draft.overrides[key][field];
        else draft.overrides[key][field] = spec.type === "bool" ? input.value === "true" : input.value;
      };
      input.addEventListener("change", update);
      if (spec.type === "number") input.addEventListener("input", update);
      container.appendChild(input);
      container.appendChild(create("p", `${defaultValue != null ? `현재 기본 기준: ${defaultValue}${spec.unit}. ` : ""}${spec.help || "바꾸지 않은 항목은 기존 Preset 규칙을 사용해요."}`, { id: `${id}-help`, class: "muted small" }));
      fields.appendChild(container);
    });
    const multiple = $("multiple"); multiple.replaceChildren();
    meta.presets.forEach((p) => {
      const label = create("label", null, { class: "mobility-multiple-choice" });
      const input = create("input", null, { type: "checkbox" });
      input.checked = draft.selected.includes(p.key); input.disabled = p.key === key;
      input.addEventListener("change", () => { draft.selected = input.checked ? [...draft.selected, p.key] : draft.selected.filter((k) => k !== p.key); });
      label.appendChild(input); label.appendChild(create("span", p.label)); multiple.appendChild(label);
    });
  }
  function close() { clearReference(); referenceListRequest++; dialog.close(); draft = null; openButton.focus(); }
  openButton.addEventListener("click", () => {
    draft = clone(settings); text("error", ""); renderDraft(); dialog.showModal(); $("preset").focus();
    if ($("reference").open && !referencePlaces) loadReferencePlaces();
  });
  $("cancel").addEventListener("click", () => { if (!busy) close(); });
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); if (!busy) close(); });
  $("preset").addEventListener("change", () => { draft = switchPreset(draft, $("preset").value); renderDraft(); });
  $("companion").addEventListener("change", () => { draft = switchCompanion(draft, draft.selected[0], $("companion").value); renderDraft(); });
  $("reset").addEventListener("click", () => { draft = resetPreset(draft, draft.selected[0]); renderDraft(); });
  $("more").addEventListener("change", () => { if ($("more").value) selectPreset($("more").value); });

  // 등록된 장소의 확인값을 보여 주고, '참고값으로 채우기'에서만 편집 초안에 반영한다.
  function clearReference() {
    referenceRequest++; referenceData = null;
    $("reference-place").value = ""; $("reference-route-box").hidden = true;
    $("reference-step-box").hidden = true; $("reference-step").checked = false;
    $("reference-facts").replaceChildren(); text("reference-proposal", ""); text("reference-status", "");
    $("reference-apply").disabled = true;
  }
  function filterReferencePlaces() {
    const query = $("reference-search").value.trim().toLocaleLowerCase();
    const select = $("reference-place"), selected = select.value;
    const rows = (referencePlaces || []).filter((p) => `${p.name} ${p.address || ""}`.toLocaleLowerCase().includes(query));
    select.replaceChildren(); option(select, "", rows.length ? "가본 장소를 선택하세요" : "해당하는 등록 장소가 없어요");
    rows.forEach((p) => option(select, String(p.id), `${p.name}${p.address ? ` · ${p.address}` : ""}`));
    select.disabled = !rows.length;
    select.value = rows.some((p) => String(p.id) === selected) ? selected : "";
    if (selected && !select.value) clearReference();
  }
  async function loadReferencePlaces() {
    const request = ++referenceListRequest;
    clearReference(); $("reference-place").disabled = true; text("reference-status", "등록된 장소를 불러오는 중...");
    try {
      const params = new URLSearchParams({ all: "1" });
      if (root.dataset.region) params.set("region", root.dataset.region);
      const result = await api(`${root.dataset.placesUrl}?${params}`);
      if (!draft || request !== referenceListRequest) return;
      referencePlaces = result.results; filterReferencePlaces();
      text("reference-status", referencePlaces.length ? "장소의 현재 판정과 관계없이 선택할 수 있어요." : "현재 지역에 등록된 장소가 없어요.");
    } catch (e) { if (draft && request === referenceListRequest) { referencePlaces = null; text("reference-status", `${e.message} 목록 새로 불러오기로 다시 시도하세요.`); } }
  }
  function chosenReferenceRoute() { return referenceData?.routes.find((r) => r.id === $("reference-route").value); }
  function renderReferenceProposal() {
    if (!draft) return;
    const values = referenceValues(meta, draft, chosenReferenceRoute(), $("reference-step").checked);
    const lines = Object.entries(values).map(([key, value]) => `${meta.fields[key].label} ${value}${meta.fields[key].unit}`);
    text("reference-proposal", lines.length ? `채울 참고값: ${lines.join(" · ")}` : "현재 조건에 가져올 수치가 없어요. 누락 값과 이용 능력·필요 여부는 추정하지 않아요.");
    $("reference-apply").disabled = busy || !lines.length;
  }
  function renderReferenceRoute() {
    const route = chosenReferenceRoute(), facts = $("reference-facts"); facts.replaceChildren();
    $("reference-step").checked = false;
    $("reference-step-box").hidden = route?.values?.max_step_height_cm == null || !fieldsFor(meta, draft, draft.selected[0]).includes("max_step_height_cm");
    if (route) {
      route.entrances.forEach((entrance) => {
        facts.appendChild(create("strong", entrance.label));
        const list = create("dl", null, { class: "fields" });
        entrance.fields.forEach((field) => {
          const row = create("div", null, { class: "field-row" });
          row.appendChild(create("dt", field.label));
          const value = typeof field.value === "boolean"
            ? field.key === "entrance_available" ? field.value ? "이용 가능" : "이용 불가" : field.value ? "있음" : "없음"
            : field.value;
          row.appendChild(create("dd", `${value}${field.unit || ""} · 확인 ${field.checked_at.slice(0, 10)}${field.pending ? " · 새 제보 확인 중" : ""}`));
          list.appendChild(row);
        });
        facts.appendChild(list);
        if (!entrance.fields.length) facts.appendChild(create("p", "아직 확인된 입구 정보가 없어요."));
      });
      route.warnings.forEach((message) => facts.appendChild(create("p", message, { class: "muted" })));
      facts.appendChild(create("p", referenceData.notice, { class: "muted" }));
    }
    renderReferenceProposal();
  }
  async function loadReferencePlace() {
    const id = $("reference-place").value;
    clearReference(); $("reference-place").value = id;
    if (!id) return;
    const request = referenceRequest;
    text("reference-status", "입구 경로와 확인값을 불러오는 중...");
    try {
      const data = await api(root.dataset.referenceUrl.replace(/\/0\/reference\/$/, `/${encodeURIComponent(id)}/reference/`));
      if (!draft || request !== referenceRequest) return;
      referenceData = data;
      const select = $("reference-route"); select.replaceChildren(); option(select, "", "실제로 이용한 입구 경로를 선택하세요");
      data.routes.forEach((route) => option(select, route.id, route.label));
      $("reference-route-box").hidden = !data.routes.length;
      if (data.routes.length === 1) { select.value = data.routes[0].id; renderReferenceRoute(); }
      text("reference-status", !data.routes.length ? "등록된 입구 경로가 없어 참고값을 제공할 수 없어요." : data.routes.length > 1 ? "여러 입구를 섞지 않고 선택한 경로의 값만 사용해요." : "표시된 경로가 실제 이용한 입구인지 확인해 주세요.");
    } catch (e) { if (draft && request === referenceRequest) text("reference-status", e.message); }
  }
  $("reference").addEventListener("toggle", () => { if ($("reference").open && draft && !referencePlaces) loadReferencePlaces(); });
  $("reference-reload").addEventListener("click", loadReferencePlaces);
  $("reference-search").addEventListener("input", filterReferencePlaces);
  $("reference-search").addEventListener("keydown", (event) => { if (event.key === "Enter") event.preventDefault(); });
  $("reference-place").addEventListener("change", loadReferencePlace);
  $("reference-route").addEventListener("change", renderReferenceRoute);
  $("reference-step").addEventListener("change", renderReferenceProposal);
  $("reference-apply").addEventListener("click", () => {
    if (busy || !draft) return;
    const values = referenceValues(meta, draft, chosenReferenceRoute(), $("reference-step").checked);
    if (!Object.keys(values).length) return;
    const key = draft.selected[0], out = clone(draft);
    out.overrides[key] = { ...out.overrides[key], ...values };
    try {
      draft = validateState(out, meta); renderDraft(false);
      text("reference-status", "편집 중인 조건의 수치만 채웠어요. 직접 수정하거나 취소할 수 있으며, 설정 저장을 눌러야 저장돼요.");
    } catch (e) { text("reference-status", e.message); }
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault(); if (busy || !form.reportValidity()) return;
    busy = true; $("save").disabled = true; text("error", "저장 중...");
    try { await apply(draft); close(); text("warning", persistenceWarning || "설정을 저장했어요."); }
    catch (e) { text("error", e.message); }
    finally { busy = false; $("save").disabled = false; }
  });
  async function evaluate(options = {}) {
    return api(root.dataset.evaluateUrl, { method: "POST", body: { settings: clone(settings), all: true, ...options } });
  }
  async function refreshView() {
    const box = $("result");
    const request = ++viewRequest;
    const personal = needsEvaluation() || (root.dataset.mode === "search" && serverSearchProfile !== primaryProfile());
    document.querySelectorAll("[data-mobility-baseline]").forEach((node) => {
      // 상세의 기본 패널 선택은 detail의 칩 컨트롤러가 담당한다.
      if (personal || root.dataset.mode === "search") node.hidden = personal;
    });
    box.hidden = true; // 새 조건을 계산하는 동안 이전 조건의 결과를 보여 주지 않는다.
    if (root.dataset.mode === "map" || !personal) { box.hidden = true; return; }
    text("warning", "내 조건으로 확인 중...");
    try {
      const options = root.dataset.placeId ? { place_ids: [root.dataset.placeId] } : { q: new URLSearchParams(location.search).get("q") || "" };
      if (root.dataset.region) options.region = root.dataset.region;
      const data = await evaluate(options);
      if (request !== viewRequest) return;
      box.replaceChildren(create("strong", `${label()} · 내 이동 조건으로 보면`));
      const list = create("ul", null, { class: "result-list" });
      data.results.forEach((row) => {
        const status = create("span", null, { class: "result-status" });
        status.appendChild(create("span", row.judgment.icon === "hand" ? "✋" : "", { class: `judge-dot judge-${row.judgment.code}`, "aria-hidden": "true" }));
        status.appendChild(create("strong", row.judgment.label));
        if (root.dataset.mode === "search") {
          const item = create("li"), link = create("a", null, { class: "card result-card", href: `/places/${row.id}/?profile=${encodeURIComponent(primaryProfile())}` });
          link.appendChild(create("strong", row.name)); link.appendChild(status);
          link.appendChild(create("span", row.judgment.reason || row.facts || "아직 확인된 입구 정보가 없어요.", { class: "small" }));
          link.appendChild(create("span", row.last_checked ? `확인 ${row.last_checked.slice(0, 10)}` : "확인 정보 없음", { class: "muted small" }));
          item.appendChild(link); list.appendChild(item);
        } else {
          box.appendChild(status);
          box.appendChild(create("p", row.judgment.explanation, { class: "small" }));
        }
      });
      if (root.dataset.mode === "search") box.appendChild(list);
      if (!data.results.length) box.appendChild(create("p", "해당하는 장소가 없어요."));
      box.appendChild(create("p", data.notice, { class: "muted small" }));
      box.hidden = false; text("warning", data.preferences.join(" "));
    } catch (e) { if (request === viewRequest) { box.hidden = true; text("warning", e.message); } }
  }
  const ready = (async () => {
    meta = await api(root.dataset.catalogueUrl);
    const restored = meta.authenticated ? { settings: validateState(meta.settings, meta), warning: meta.warning } : restoreGuest(storage(), meta);
    settings = restored.settings;
    const linked = root.dataset.mode === "detail" ? new URLSearchParams(location.search).get("profile") : null;
    // Apply a valid linked profile for this page without overwriting saved preferences.
    if (meta.presets.some((p) => p.key === linked && p.profile === linked && !p.companion) && primaryProfile() !== linked) {
      settings = { ...settings, selected: [linked] };
    }
    text("warning", restored.warning);
    meta.presets.forEach((p) => option($("preset"), p.key, p.label));
    meta.companion_options.forEach((p) => option($("companion"), p.key, p.label));
    meta.presets.filter((p) => ["LIMITED_WALKING", "WITH_CHILD", "ASSISTED_COMPANION"].includes(p.key)).forEach((p) => option($("more"), p.key, p.label));
    text("notice", meta.notice); openButton.disabled = false; $("more").disabled = false;
    publish(); return meta;
  })();
  if (root.dataset.mode === "search") document.getElementById("search-profile")?.addEventListener("change", (event) => selectPreset(event.target.value));
  ready.catch(() => text("warning", "개인화 설정을 읽을 수 없어요. 기본 이동 조건으로 계속 이용할 수 있어요."));
  window.TeokMobility = { ready: () => ready, state: () => clone(settings), presets: () => meta.presets,
    primaryProfile, label, needsEvaluation, evaluate, selectPreset };
})();
