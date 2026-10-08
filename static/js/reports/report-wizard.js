/* Keep every input mounted while navigating the five report steps. */
(function (root) {
  "use strict";
  const steps = [
    ["장소 선택", "어느 장소를 확인하셨나요?", "이 장소 선택하기"],
    ["시설 선택", "무엇을 확인했나요?", "사진 추가하기"],
    ["사진 추가", "시설이 잘 보이는 사진을 올려주세요.", "사진 선택 후 다음"],
    ["직접 확인한 정보", "아는 항목만 알려주세요.", "제보 내용 확인"],
    ["제출 전 확인", "제보 내용을 확인해 주세요.", "제보 제출하기"],
  ];

  function fieldText(field) {
    if (field.tagName === "SELECT") return field.selectedOptions[0]?.textContent || "";
    return field.value.trim();
  }

  function init(doc) {
    const wizard = doc.getElementById("report-wizard");
    const form = doc.getElementById("report-form");
    if (!wizard || !form) return;
    const panels = [...wizard.querySelectorAll("[data-report-step]")];
    const heading = doc.getElementById("report-heading");
    const progress = doc.getElementById("report-progress");
    const next = doc.getElementById("report-next");
    const previous = doc.getElementById("report-previous");
    const submit = doc.getElementById("report-submit");
    const message = doc.getElementById("report-step-error");
    const summary = doc.getElementById("report-summary");
    let current = 1, advancing = false, reviewingAI = false;

    function reviewAI(active) {
      reviewingAI = active;
      const box = doc.getElementById("ai-report-review");
      if (!box) return;
      box.hidden = !active;
      doc.getElementById("report-manual-fields").hidden = active;
      // Text-only facts still need the reporter's explanation during AI review.
      doc.getElementById("report-manual-note").hidden = false;
      doc.body.classList.toggle("ai-review-mode", active);
      next.hidden = active || current === steps.length;
      heading.textContent = active ? "사진에서 확인할 내용을 정리했어요" : steps[current - 1][1];
    }

    doc.addEventListener("ai-prefill:complete", () => {
      if (current !== 4) return;
      const facts = doc.getElementById("ai-report-facts");
      facts.replaceChildren(...[...doc.getElementById("facility-observations").querySelectorAll(".ai-filled")].map((field) => {
        const line = doc.createElement("p");
        line.textContent = `${doc.querySelector(`label[for="${field.id}"]`)?.textContent || field.name}: ${fieldText(field)}`;
        return line;
      }));
      if (!facts.children.length) facts.textContent = "AI가 확실히 알 수 있는 빈 칸이 없었어요. 직접 입력해 주세요.";
      reviewAI(true);
    });
    doc.getElementById("ai-report-edit")?.addEventListener("click", () => reviewAI(false));
    doc.getElementById("ai-report-accept")?.addEventListener("click", () => {
      reviewAI(false);
      advance();
    });

    ["id_ownership", "id_facility_kind"].forEach((id) => {
      const select = doc.getElementById(id);
      const choices = doc.createElement("div");
      choices.className = "choice-grid";
      choices.setAttribute("role", "group");
      choices.setAttribute("aria-label", select.labels[0]?.textContent || "시설 선택");
      const sync = () => choices.querySelectorAll("button").forEach((button) => {
        button.setAttribute("aria-pressed", String(button.dataset.value === select.value));
      });
      [...select.options].forEach((option) => {
        const button = doc.createElement("button");
        button.type = "button"; button.className = "chip"; button.dataset.value = option.value;
        button.textContent = option.textContent;
        button.addEventListener("click", () => { select.value = option.value; select.dispatchEvent(new Event("change", { bubbles: true })); sync(); });
        choices.append(button);
      });
      select.insertAdjacentElement("afterend", choices);
      select.hidden = true;
      select.addEventListener("change", sync);
      // Failed switches restore the native select asynchronously.
      new MutationObserver(sync).observe(doc.getElementById("facility-switch-status"), { childList: true, subtree: true, characterData: true });
      sync();
    });

    function summarize() {
      const blocks = [];
      function add(title, value) {
        if (!value) return;
        const dl = doc.createElement("dl"), dt = doc.createElement("dt"), dd = doc.createElement("dd");
        dl.className = "card"; dt.textContent = title; dd.textContent = value;
        dl.append(dt, dd); blocks.push(dl);
      }
      const place = wizard.querySelector("[data-report-place]");
      add("장소", place?.textContent || form.elements.suggested_name?.value);
      const kind = doc.getElementById("id_facility_kind"), owner = doc.getElementById("id_ownership");
      add("시설", [fieldText(owner), fieldText(kind), fieldText(form.elements.target_reference), form.elements.facility_name.value].filter(Boolean).join(" / "));
      const facts = [...doc.getElementById("facility-observations").querySelectorAll("input, select, textarea")]
        .filter((field) => field.value !== "")
        .map((field) => `${doc.querySelector(`label[for="${field.id}"]`)?.textContent || field.name}: ${fieldText(field)}`);
      add("직접 확인한 정보", facts.length ? facts.join("\n") : "입력한 관측값 없음");
      add("추가 설명", form.elements.note.value);
      add("위치 설명", form.elements.location_text.value);
      add("사진", form.elements.photo.files[0]?.name || (form.elements.photo_token.value ? "보관된 사진" : "선택되지 않음"));
      summary.replaceChildren(...blocks);
      summary.hidden = false;
    }

    function show(step, focus = true) {
      current = Math.max(1, Math.min(steps.length, step));
      if (reviewingAI) reviewAI(false);
      panels.forEach((panel) => { panel.hidden = Number(panel.dataset.reportStep) !== current; });
      progress.hidden = false;
      progress.textContent = `${current} / ${steps.length} · ${steps[current - 1][0]}`;
      heading.textContent = steps[current - 1][1];
      previous.hidden = current === 1;
      next.hidden = current === steps.length;
      submit.hidden = current !== steps.length;
      next.textContent = steps[current - 1][2];
      message.hidden = true;
      if (current === steps.length) summarize();
      // Maps created in a hidden step need their visible size recalculated.
      root.dispatchEvent(new Event("resize"));
      if (focus) {
        heading.focus({ preventScroll: true });
        wizard.scrollIntoView({ block: "start", behavior: "instant" });
      }
    }

    function error(text, input) {
      message.textContent = text; message.hidden = false;
      if (input) { input.focus(); input.reportValidity(); }
      return false;
    }

    function validateStep(step) {
      if (doc.getElementById("facility-observations").getAttribute("aria-busy") === "true")
        return error("시설 종류에 맞는 항목을 불러오는 중이에요. 잠시 후 다시 눌러 주세요.");
      if (step === 4 && doc.getElementById("ai-prefill-button")?.disabled)
        return error("AI가 내용을 확인하고 있어요. 확인이 끝난 뒤 계속해 주세요.");
      const inputs = panels.filter((panel) => Number(panel.dataset.reportStep) === step)
        .flatMap((panel) => [...panel.querySelectorAll("input, select, textarea")]);
      for (const input of inputs) {
        if (!input.disabled && !input.checkValidity()) return error("표시된 항목을 확인해 주세요.", input);
      }
      if (step === 1) {
        const name = form.elements.suggested_name;
        if (name) doc.getElementById("report-new-place").open = true;
        if (name && !name.value.trim()) return error("장소 이름을 입력해 주세요.", name);
        const lat = form.elements.lat, lng = form.elements.lng;
        if (lat && lng && Boolean(lat.value) !== Boolean(lng.value)) return error("위도와 경도를 함께 입력해 주세요.", lat.value ? lng : lat);
        if (name && !lat?.value && !form.elements.location_text.value.trim())
          return error("지도를 눌러 위치를 표시하거나 위치 설명을 적어 주세요.", form.elements.location_text);
      }
      if (step === 4) {
        const hasFact = [...doc.getElementById("facility-observations").querySelectorAll("input, select, textarea")].some((input) => input.value !== "");
        if (!hasFact && !form.elements.note.value.trim()) return error("확인한 항목을 하나 이상 입력하거나 추가 설명을 적어 주세요.", form.elements.note);
      }
      return true;
    }

    async function advance() {
      if (advancing) return;
      advancing = true; next.disabled = true;
      try {
        if (current === 3 && root.PhotoResize?.ready) await root.PhotoResize.ready(form);
        if (validateStep(current)) show(current + 1);
      } finally { advancing = false; next.disabled = false; }
    }

    next.addEventListener("click", advance);
    previous.addEventListener("click", () => show(current - 1));
    form.noValidate = true;
    form.addEventListener("invalid", (event) => {
      const panel = event.target.closest("[data-report-step]");
      if (panel && panel.hidden) show(Number(panel.dataset.reportStep));
    }, true);
    form.addEventListener("submit", (event) => {
      if (current !== steps.length) { event.preventDefault(); advance(); return; }
      for (let step = 1; step <= steps.length; step++) {
        if (!validateStep(step)) { event.preventDefault(); show(step); validateStep(step); return; }
      }
    });
    const invalidPanel = panels.find((panel) => panel.querySelector(".has-error"));
    wizard.classList.add("is-enhanced");
    show(invalidPanel ? Number(invalidPanel.dataset.reportStep) : doc.getElementById("report-errors") ? 5 : 1, false);
    const finder = doc.getElementById("report-place-finder");
    if (finder) {
      const query = doc.getElementById("report-place-query"), status = doc.getElementById("report-place-status");
      const results = doc.getElementById("report-place-results"), button = doc.getElementById("report-place-find");
      let request = 0;
      async function find() {
        const text = query.value.trim(), version = ++request;
        results.replaceChildren();
        if (!text) { status.textContent = "장소 이름이나 주소를 입력해 주세요."; return; }
        button.disabled = true; status.textContent = "등록된 장소를 찾고 있어요…";
        try {
          const url = new URL(finder.dataset.placesUrl, root.location.origin);
          if (finder.dataset.region) url.searchParams.set("region", finder.dataset.region);
          url.searchParams.set("all", "1");
          const response = await root.fetch(url, { headers: { Accept: "application/json" } });
          if (!response.ok) throw new Error("search failed");
          const data = await response.json();
          if (request !== version || query.value.trim() !== text) return;
          const matches = data.results.filter((place) => `${place.name} ${place.address}`.toLocaleLowerCase().includes(text.toLocaleLowerCase()));
          matches.forEach((place) => {
            const item = doc.createElement("li"), link = doc.createElement("a");
            const target = new URL(finder.dataset.reportUrl, root.location.origin);
            target.searchParams.set("place", place.id); link.href = target.href;
            link.className = "card result-card"; link.textContent = `${place.name} · ${place.address || "주소 정보 없음"}`;
            item.append(link); results.append(item);
          });
          status.textContent = matches.length ? `${matches.length}곳을 찾았어요. 제보할 장소를 선택해 주세요.` : "등록된 장소가 없어요. 아래에서 새 장소로 제안해 주세요.";
        } catch (e) { if (request === version) status.textContent = "장소 목록을 불러오지 못했어요. 다시 검색하거나 새 장소로 제안해 주세요."; }
        finally { if (request === version) button.disabled = false; }
      }
      button.addEventListener("click", find);
      query.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); find(); } });
    }
  }
  if (typeof module !== "undefined" && module.exports) module.exports = { init, fieldText };
  if (root.document) init(root.document);
})(typeof window !== "undefined" ? window : globalThis);
