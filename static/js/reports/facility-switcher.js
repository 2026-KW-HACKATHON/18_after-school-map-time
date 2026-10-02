/** 시설 종류만 전환한다. 사진·지도·공통 입력의 DOM은 유지해 작성 내용을 보호한다. */
(function () {
  const selector = document.getElementById("facility-selector");
  const form = document.getElementById("report-form");
  if (!selector || !form) return;
  const kind = document.getElementById("id_facility_kind");
  const ownership = document.getElementById("id_ownership");
  const savedKind = document.getElementById("report-kind");
  const savedOwnership = document.getElementById("report-ownership");
  const observations = document.getElementById("facility-observations");
  const target = document.getElementById("id_target_reference");
  const name = document.getElementById("id_facility_name");
  const status = document.getElementById("facility-switch-status");
  const submit = form.querySelector('[type="submit"]');
  const values = new Map();
  const targets = new Map();
  let version = 0;
  let pending = false;
  const key = () => `${savedKind.value}:${savedOwnership.value}`;
  const controls = () => observations.querySelectorAll("input, select, textarea");
  const remember = () => {
    controls().forEach((field) => values.set(field.name, field.value));
    targets.set(key(), { target: target.value, name: name.value });
  };
  const busy = (active) => {
    pending = active;
    submit.disabled = active;
    observations.setAttribute("aria-busy", String(active));
    // 전환 중에는 이전 시설 칸을 편집하지 못하게 하고 값은 메모리에 보관한다.
    controls().forEach((field) => { field.disabled = active; });
    target.disabled = active;
    name.disabled = active;
  };
  async function change() {
    if (kind.value === savedKind.value && ownership.value === savedOwnership.value) {
      ++version; // 원래 종류를 다시 선택한 경우에도 이전 응답을 무시한다.
      busy(false);
      status.textContent = "시설 종류에 맞는 입력 항목을 표시하고 있어요.";
      return;
    }
    if (!pending) remember();
    const requestVersion = ++version;
    busy(true);
    status.textContent = "입력 항목을 바꾸고 있어요…";
    const url = new URL(window.location.href);
    url.searchParams.set("facility_kind", kind.value);
    url.searchParams.set("ownership", ownership.value);
    url.searchParams.set("partial", "facility-fields");
    url.searchParams.delete("target_reference");
    // POST 오류 화면의 URL에 장소·건물이 없어도 숨겨진 입력으로 소속을 유지한다.
    ["place", "building"].forEach((fieldName) => {
      const input = form.querySelector(`[name="${fieldName}"]`);
      if (input) url.searchParams.set(fieldName, input.value);
    });
    try {
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("switch failed");
      const data = await response.json();
      if (requestVersion !== version) return;
      // 로그인이 만료되거나 응답이 잘못되면 원래 입력 항목을 유지한다.
      if (data.kind !== kind.value || data.ownership !== ownership.value ||
          typeof data.fields_html !== "string" || typeof data.location_html !== "string" ||
          !Array.isArray(data.targets)) throw new Error("invalid response");
      observations.innerHTML = data.fields_html;
      controls().forEach((field) => {
        if (values.has(field.name)) field.value = values.get(field.name);
      });
      target.replaceChildren(...data.targets.map(([value, label]) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        return option;
      }));
      savedKind.value = data.kind;
      savedOwnership.value = data.ownership;
      const previous = targets.get(key());
      target.value = previous && data.targets.some(([value]) => value === previous.target) ? previous.target : data.target;
      name.value = previous ? previous.name : "";
      form.querySelectorAll("[data-facility-label]").forEach((label) => { label.textContent = data.label; });
      const photoLabel = form.querySelector('label[for="id_photo"]');
      const photoHelp = document.getElementById("id_photo_helptext");
      if (photoLabel) photoLabel.textContent = data.photo_label;
      if (photoHelp) photoHelp.textContent = data.photo_help;
      const location = document.getElementById("report-location");
      if (!document.getElementById("picker-map")) {
        location.innerHTML = data.location_html;
        document.dispatchEvent(new Event("location-picker-ready"));
      }
      location.hidden = !data.show_picker;
      const help = document.getElementById("picker-help");
      if (help) help.textContent = `지도를 눌러 정확한 ${data.label} 위치를 표시해 주세요.`;
      // 숨겨졌던 지도 크기는 공용 어댑터의 resize 처리로 다시 계산한다.
      window.dispatchEvent(new Event("resize"));
      const latitude = document.getElementById("id_lat");
      if (latitude?.value) latitude.dispatchEvent(new Event("change", { bubbles: true }));
      status.textContent = `${data.label} 입력 항목을 표시했어요. 사진과 작성한 내용은 유지돼요.`;
    } catch (error) {
      if (requestVersion !== version) return;
      kind.value = savedKind.value;
      ownership.value = savedOwnership.value;
      status.textContent = "입력 항목을 바꾸지 못했어요. 기존 내용은 유지돼요. 종류를 다시 선택해 주세요.";
    } finally {
      if (requestVersion === version) busy(false);
    }
  }
  kind.addEventListener("change", change);
  ownership.addEventListener("change", change);
  selector.addEventListener("submit", (event) => { event.preventDefault(); change(); });
  form.addEventListener("submit", (event) => { if (pending) event.preventDefault(); });
})();
