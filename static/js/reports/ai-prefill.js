/*
 * 제보 작성 중 'AI로 항목 채우기' (reports.views.ai_prefill)
 *
 * - 주민이 버튼을 눌렀을 때만 고른 사진(브라우저에서 줄인 것)과 '추가 설명'을 서버로 보낸다.
 *   서버가 EXIF를 지우고 얼굴을 가린 뒤 AI로 보내고, 빈 칸 후보를 돌려준다.
 * - 주민이 이미 적은 칸은 덮어쓰지 않는다. 채운 칸에는 'AI가 채움 — 근거'를 붙여 확인하게 한다.
 * - 돌려받은 표(token)는 숨은 칸에 넣어 두고 제출할 때 함께 보낸다 → 서버가 그 결과를 제보에 연결
 * - 시설 종류를 바꾸면 항목이 달라지므로 표를 비운다
 */
(function (root) {
  "use strict";

  const MARK_CLASS = "ai-filled";
  const NOTE_CLASS = "ai-filled-note";
  const revisions = new WeakMap();

  function clearMarks(form) {
    form.querySelectorAll("." + NOTE_CLASS).forEach((el) => el.remove());
    form.querySelectorAll("." + MARK_CLASS).forEach((el) => el.classList.remove(MARK_CLASS));
  }

  function asFieldValue(value) {
    if (typeof value === "boolean") return value ? "true" : "false";
    return String(value);
  }

  // 후보로 빈 칸만 채운다 → 채운 항목 이름들
  function fillForm(form, fields, doc) {
    const filled = [];
    Object.keys(fields).forEach((key) => {
      const field = fields[key];
      if (!field || field.value === null || field.value === undefined) return;
      const el = form.elements[key];
      if (!el || el.value !== "") return;  // 주민이 적은 값은 그대로
      const value = asFieldValue(field.value);
      if (el.tagName === "SELECT" && !Array.from(el.options).some((o) => o.value === value)) return;
      el.value = value;
      el.classList.add(MARK_CLASS);
      const note = doc.createElement("p");
      note.className = NOTE_CLASS;
      note.textContent = `AI가 채움 · ${field.certainty}${field.evidence ? " — " + field.evidence : ""}`;
      el.insertAdjacentElement("afterend", note);
      filled.push(key);
    });
    return filled;
  }

  function message(data, filled) {
    const parts = [];
    if (filled.length) parts.push(`AI가 ${filled.length}칸을 채웠어요. 사진·현장과 다르면 고쳐 주세요.`);
    else parts.push("AI가 확실히 알 수 있는 빈 칸이 없었어요. 직접 입력해 주세요.");
    if (data.warnings && data.warnings.length) parts.push(`참고: ${data.warnings.join(", ")}.`);
    parts.push(`오늘 ${data.remaining}번 더 쓸 수 있어요.`);
    return parts.join(" ");
  }

  async function run(form, box, deps) {
    const status = box.querySelector("#ai-prefill-status");
    const tokenInput = box.querySelector("#ai-prefill-token");
    const button = box.querySelector("#ai-prefill-button");
    if (button.disabled) return;
    const observations = deps.document.getElementById("facility-observations");
    if (observations && observations.getAttribute("aria-busy") === "true") {
      status.textContent = "입력 항목을 바꾸고 있어요. 전환이 끝난 뒤 다시 눌러 주세요.";
      return;
    }
    const photoInput = form.elements.photo;
    const file = photoInput && photoInput.files && photoInput.files[0];
    const keptPhoto = form.elements.photo_token && form.elements.photo_token.value;
    const note = form.elements.note ? form.elements.note.value : "";
    if (!file && !keptPhoto && !note.trim()) {
      status.textContent = "사진을 고르거나 설명을 적은 뒤 눌러 주세요.";
      return;
    }
    const revision = (revisions.get(form) || 0) + 1;
    revisions.set(form, revision);
    const facilityKind = form.elements.facility_kind ? form.elements.facility_kind.value : "ENTRANCE";
    const ownership = form.elements.ownership ? form.elements.ownership.value : null;
    const isCurrent = () => revisions.get(form) === revision &&
      (!form.elements.facility_kind || form.elements.facility_kind.value === facilityKind) &&
      (!form.elements.ownership || form.elements.ownership.value === ownership);
    const body = new deps.FormData();
    body.append("csrfmiddlewaretoken", form.elements.csrfmiddlewaretoken.value);
    body.append("facility_kind", facilityKind);
    body.append("note", note);
    if (file) body.append("photo", file);
    else if (keptPhoto) body.append("photo_token", keptPhoto);

    button.disabled = true;
    status.textContent = "AI가 사진과 설명을 보고 있어요…";
    try {
      const response = await deps.fetch(box.dataset.url, { method: "POST", body, credentials: "same-origin" });
      const data = await response.json();
      // A facility change invalidates both the fields and the signed result.
      if (!isCurrent()) return;
      if (!data.ok) {
        status.textContent = data.message || "AI가 값을 채우지 못했어요. 직접 입력해 주세요.";
        return;
      }
      clearMarks(form);
      const filled = fillForm(form, data.fields, deps.document);
      tokenInput.value = data.token;
      status.textContent = message(data, filled);
    } catch (e) {
      if (isCurrent()) status.textContent = "연결이 불안정해요. 잠시 뒤 다시 누르거나 직접 입력해 주세요.";
    } finally {
      button.disabled = false;
    }
  }

  function init(doc, deps) {
    const form = doc.getElementById("report-form");
    const box = doc.getElementById("ai-prefill");
    if (!form || !box) return;
    box.querySelector("#ai-prefill-button").addEventListener("click", () => run(form, box, deps));
    // 시설 종류를 바꾸면 항목이 달라짐 → 이전 결과 표는 쓰지 않음
    const selector = doc.getElementById("facility-selector");
    if (selector) {
      selector.addEventListener("change", () => {
        revisions.set(form, (revisions.get(form) || 0) + 1);
        box.querySelector("#ai-prefill-token").value = "";
        box.querySelector("#ai-prefill-status").textContent = "시설이 바뀌어 이전 AI 결과는 적용하지 않아요. 직접 입력하거나 다시 분석해 주세요.";
        clearMarks(form);
      });
    }
  }

  const api = { fillForm, clearMarks, message, run, init };
  root.AIPrefill = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root.document && typeof root.document.getElementById === "function" && typeof root.fetch === "function") {
    init(root.document, { fetch: root.fetch.bind(root), FormData: root.FormData, document: root.document });
  }
})(typeof window !== "undefined" ? window : globalThis);
