/* HEIC는 동일 서버에서 JPEG 미리보기만 변환한다. 원본 업로드·사진 보관은 그대로 유지. */
(function (root) {
  "use strict";
  const isHeic = (file) => /\.(heic|heif)$/i.test(file.name || "") || /^image\/hei[cf]/i.test(file.type || "");
  function init(doc) {
    const form = doc.getElementById("report-form"), box = doc.getElementById("report-photo-preview");
    if (!form || !box) return;
    const input = form.elements.photo, img = doc.getElementById("report-preview-image");
    const status = doc.getElementById("report-preview-status");
    let version = 0, url = null, controller = null;
    const clear = () => { if (url) root.URL.revokeObjectURL(url); url = null; };
    async function update() {
      const current = ++version, file = input.files[0];
      controller?.abort(); controller = null;
      clear(); img.hidden = true; img.removeAttribute("src"); status.textContent = "";
      box.setAttribute("aria-busy", "false");
      if (!file) return;
      let preview = file;
      if (isHeic(file)) {
        if (file.size > 10 * 1024 * 1024) { status.textContent = "10MB 이하의 사진을 골라 주세요."; return; }
        status.textContent = "아이폰 사진의 미리보기를 준비하고 있어요…";
        box.setAttribute("aria-busy", "true");
        controller = new root.AbortController();
        const data = new root.FormData(); data.append("photo", file);
        try {
          const response = await root.fetch(box.dataset.previewUrl, {
            method: "POST", body: data, credentials: "same-origin", signal: controller.signal,
            headers: { "X-CSRFToken": form.elements.csrfmiddlewaretoken.value },
          });
          if (!response.ok || !response.headers.get("Content-Type")?.startsWith("image/jpeg")) throw new Error("preview failed");
          preview = await response.blob();
        } catch (e) {
          if (current === version) {
            status.textContent = "미리보기를 불러오지 못했어요. 사진을 다시 고르거나 JPEG/PNG로 골라 주세요. 원본 사진은 제출할 수 있어요.";
            box.setAttribute("aria-busy", "false");
          }
          return;
        }
      }
      if (current !== version) return;
      url = root.URL.createObjectURL(preview); img.src = url; img.hidden = false;
      status.textContent = ""; box.setAttribute("aria-busy", "false");
    }
    input.addEventListener("change", update);
    img.addEventListener("error", () => { img.hidden = true; status.textContent = "이 브라우저에서 사진을 미리볼 수 없어요. 다른 사진이나 JPEG/PNG로 골라 주세요."; });
    root.addEventListener("pagehide", (event) => { if (!event.persisted) { ++version; controller?.abort(); clear(); } });
    return { update };
  }
  if (typeof module !== "undefined" && module.exports) module.exports = { init, isHeic };
  if (root.document) init(root.document);
})(typeof window !== "undefined" ? window : globalThis);
