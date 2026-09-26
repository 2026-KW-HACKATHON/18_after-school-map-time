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
