/**
 * 공통 JS 유틸. base.html에서 모든 페이지에 로드됩니다.
 */

/** 쿠키 값 읽기 (CSRF 토큰용) */
function getCookie(name) {
  const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[2]) : null;
}

/**
 * 우리 API 호출 헬퍼. POST/PUT/DELETE에 CSRF 토큰을 자동으로 붙이고 JSON으로 주고받습니다.
 *   const data = await api("/api/places/");
 *   await api("/some/api/", { method: "POST", body: { name: "..." } });
 */
async function api(url, { method = "GET", body } = {}) {
  const headers = { Accept: "application/json" };
  if (method !== "GET") {
    headers["X-CSRFToken"] = getCookie("csrftoken");
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `요청 실패 (${res.status})`);
  }
  return data;
}

/**
 * 큰 글씨 모드 (어르신 친화). 선택은 이 브라우저에만 저장(localStorage)하고,
 * 화면이 그려지기 전에 base.html <head>의 짧은 스크립트가 먼저 적용해 깜빡임을 막는다.
 */
(function () {
  const KEY = "teokeopne-large-text";
  const button = document.getElementById("text-size-toggle");
  if (!button) return;
  const sync = () => button.setAttribute("aria-pressed", String(document.documentElement.classList.contains("large-text")));
  sync();
  button.addEventListener("click", () => {
    const on = document.documentElement.classList.toggle("large-text");
    try { localStorage.setItem(KEY, on ? "1" : "0"); } catch (e) { /* 저장이 막힌 브라우저: 이번 화면에만 적용 */ }
    sync();
  });
})();

/**
 * 사진을 불러오지 못하면(파일이 없어졌거나 연결이 끊김) 깨진 그림 대신 안내 문구로 바꾼다.
 * 입구 사진·제보 사진 공통 (class="entrance-photo")
 */
function replaceBrokenPhoto(img) {
  const note = document.createElement("p");
  note.className = "photo-missing muted small";
  note.textContent = "사진을 불러오지 못했어요.";
  const holder = img.closest("a") || img;  // 크게 보기 링크로 감싼 경우 링크째 바꿈
  holder.replaceWith(note);
}
document.addEventListener("error", (event) => {
  const img = event.target;
  if (img instanceof HTMLImageElement && img.classList.contains("entrance-photo")) replaceBrokenPhoto(img);
}, true);  // img 의 error 는 위로 전달되지 않아서 캡처 단계에서 받음
// 이 스크립트가 불러와지기 전에 이미 실패한 사진도 정리
document.querySelectorAll("img.entrance-photo").forEach((img) => {
  if (img.complete && img.naturalWidth === 0 && img.getAttribute("loading") !== "lazy") replaceBrokenPhoto(img);
});
