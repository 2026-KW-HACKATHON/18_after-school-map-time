/*
 * 사진 올리기 전에 브라우저에서 줄이기 (모든 사진 업로드 폼 공통, base.html에서 불러옴)
 *
 * 왜: 폰 사진은 3~12MB라 모바일 데이터로 올리기 느리고, 10MB를 넘으면 서버(nginx)가 413으로 막는다.
 *     서버도 어차피 긴 변 1600px JPEG로 줄여서 저장하므로(core/images.py) 미리 줄여 보내도 화질 차이가 없다.
 * 덤: 캔버스로 다시 그린 JPEG에는 EXIF(촬영 위치 GPS)가 없어서 위치 정보가 서버까지 가지도 않는다.
 *
 * - 사진 칸에서 파일을 고르면 바로 줄이고, 줄인 파일로 칸을 바꿔 둔다 (DataTransfer)
 * - 줄이는 중에 제출 버튼을 누르면 끝날 때까지 기다렸다가 제출한다
 * - 브라우저가 못 여는 사진(예: 크롬의 아이폰 HEIC)이나 옛 브라우저는 원본 그대로 보낸다 → 서버가 처리
 * - 줄여도 10MB가 넘으면 제출 전에 안내하고 막는다 (413 오류 화면 대신)
 */
(function (root) {
  "use strict";

  const MAX_PX = 1600;                       // 서버 PHOTO_MAX_PX와 같게
  const QUALITY = 0.85;                      // 서버 JPEG_QUALITY와 같게
  const SKIP_BELOW = 500 * 1024;             // 이보다 작으면 그대로 (이미 작은 사진)
  const UPLOAD_LIMIT = 9.5 * 1024 * 1024;    // nginx client_max_body_size 10M에서 다른 칸 몫을 뺀 값
  const FORM_SELECTOR = 'form[enctype="multipart/form-data"]';

  function targetSize(width, height, max = MAX_PX) {
    const scale = Math.min(1, max / Math.max(width, height));
    return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
  }

  function jpegName(name) {
    const stem = String(name || "").replace(/\.[^./\\]*$/, "");
    return `${stem || "photo"}.jpg`;
  }

  function formatMB(bytes) {
    return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
  }

  function isImage(file) {
    return /^image\//.test(file.type || "") || /\.(heic|heif)$/i.test(file.name || "");
  }

  // 사진 열기. 폰 세로 사진이 눕지 않게 EXIF 방향을 적용해서 연다
  async function decode(file) {
    if (typeof root.createImageBitmap === "function") {
      try {
        const bitmap = await root.createImageBitmap(file, { imageOrientation: "from-image" });
        return { image: bitmap, width: bitmap.width, height: bitmap.height, release: () => bitmap.close() };
      } catch (e) { /* 아래 <img> 방식으로 다시 시도 */ }
    }
    const url = root.URL.createObjectURL(file);
    const img = new root.Image();
    img.src = url;
    try {
      await img.decode();
    } catch (e) {
      root.URL.revokeObjectURL(url);
      throw e;
    }
    return { image: img, width: img.naturalWidth, height: img.naturalHeight, release: () => root.URL.revokeObjectURL(url) };
  }

  function encode(image, width, height) {
    const canvas = root.document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#fff";  // 투명한 PNG가 JPEG에서 검게 나오지 않게
    ctx.fillRect(0, 0, width, height);
    ctx.drawImage(image, 0, 0, width, height);
    return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", QUALITY));
  }

  // 파일 → { file, resized }. 줄일 수 없거나 줄여도 커지면 원본 그대로
  async function shrink(file, deps = { decode, encode }) {
    const keep = { file, resized: false };
    if (!file || !isImage(file) || file.size <= SKIP_BELOW) return keep;
    let decoded;
    try {
      decoded = await deps.decode(file);
    } catch (e) {
      return keep;  // 브라우저가 못 여는 형식 → 서버가 변환
    }
    try {
      const size = targetSize(decoded.width, decoded.height);
      const blob = await deps.encode(decoded.image, size.width, size.height);
      if (!blob || blob.size >= file.size) return keep;
      const resized = new root.File([blob], jpegName(file.name), { type: "image/jpeg", lastModified: file.lastModified });
      return { file: resized, resized: true };
    } catch (e) {
      return keep;
    } finally {
      if (decoded.release) decoded.release();
    }
  }

  function statusFor(input, doc) {
    let el = input.nextElementSibling;
    if (el && el.classList && el.classList.contains("photo-resize-status")) return el;
    el = doc.createElement("p");
    el.className = "muted small photo-resize-status";
    el.setAttribute("aria-live", "polite");
    input.insertAdjacentElement("afterend", el);
    return el;
  }

  const pending = new Map();  // form → 진행 중인 줄이기 작업들

  async function handle(input, doc, deps) {
    input.setCustomValidity("");
    const file = input.files && input.files[0];
    if (!file) return;
    const status = statusFor(input, doc);
    if (isImage(file) && file.size > SKIP_BELOW) status.textContent = "사진을 줄이는 중이에요…";
    const result = await shrink(file, deps);
    if (result.resized && typeof root.DataTransfer === "function") {
      const transfer = new root.DataTransfer();
      transfer.items.add(result.file);
      input.files = transfer.files;  // 프로그램으로 바꾸면 change 이벤트가 다시 나지 않음
      status.textContent = `사진을 줄였어요 (${formatMB(file.size)} → ${formatMB(result.file.size)})`;
    } else {
      status.textContent = "";
    }
    const finalFile = input.files && input.files[0];
    if (finalFile && finalFile.size > UPLOAD_LIMIT) {
      const message = `사진이 ${formatMB(finalFile.size)}라 올릴 수 없어요. 10MB보다 작은 사진을 골라 주세요.`;
      input.setCustomValidity(message);  // 제출하면 브라우저가 이 칸을 가리키며 막음
      status.textContent = message;
    }
  }

  function onChange(event, doc, deps) {
    const input = event.target;
    if (!input || input.type !== "file" || !input.closest || !input.closest(FORM_SELECTOR)) return;
    const form = input.closest(FORM_SELECTOR);
    const job = handle(input, doc, deps).catch(() => {});
    const jobs = pending.get(form) || new Set();
    jobs.add(job);
    pending.set(form, jobs);
    job.then(() => {
      jobs.delete(job);
      if (!jobs.size) pending.delete(form);
    });
  }

  function onSubmit(event) {
    const form = event.target;
    const jobs = pending.get(form);
    if (!jobs || !jobs.size) return;
    event.preventDefault();  // 줄이기가 끝나면 같은 버튼으로 다시 제출
    const submitter = event.submitter;
    Promise.all(jobs).then(() => {
      if (typeof form.requestSubmit === "function") form.requestSubmit(submitter || undefined);
      else form.submit();
    });
  }

  function init(doc, deps) {
    // 시설 종류 전환처럼 칸이 나중에 바뀌어도 되게 문서 전체에서 이벤트를 받는다
    doc.addEventListener("change", (event) => onChange(event, doc, deps));
    doc.addEventListener("submit", onSubmit);
  }

  const api = { MAX_PX, SKIP_BELOW, UPLOAD_LIMIT, targetSize, jpegName, formatMB, shrink, init };
  root.PhotoResize = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root.document && typeof root.document.addEventListener === "function") init(root.document);
})(typeof window !== "undefined" ? window : globalThis);
