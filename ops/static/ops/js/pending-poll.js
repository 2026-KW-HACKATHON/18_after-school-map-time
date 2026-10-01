/**
 * 운영자 화면: 10초마다 검토 대기 수를 물어서, 새 제보·인증 신청이 들어오면 알려 준다.
 *  - 메뉴 배지(제보 검토 n, 사장님 인증 n)와 탭 제목 "(n) ..." 을 갱신
 *  - 이 화면을 연 뒤로 늘어난 만큼 "새로 검토할 일이 n건" 안내를 띄움
 *  - 탭이 안 보이는 동안은 묻지 않음 (서버 부담 줄이기), 다시 보이면 이어서
 */
(function () {
  const nav = document.querySelector(".ops-nav[data-pending-url]");
  if (!nav) return;

  const INTERVAL_MS = 10000;
  const url = nav.dataset.pendingUrl;
  const start = { pending: Number(nav.dataset.pending || 0), claims: Number(nav.dataset.claims || 0) };
  const badges = { pending: nav.querySelector('[data-badge="pending"]'), claims: nav.querySelector('[data-badge="claims"]') };
  const banner = document.getElementById("ops-new-banner");
  const bannerCount = banner && banner.querySelector("[data-new-count]");
  const baseTitle = document.title.replace(/^\(\d+\)\s*/, "");
  let timer = null;

  function render(counts) {
    for (const key of ["pending", "claims"]) {
      const badge = badges[key];
      if (!badge) continue;
      badge.textContent = String(counts[key]);
      badge.hidden = !counts[key];
    }
    const total = counts.pending + counts.claims;
    document.title = total ? `(${total}) ${baseTitle}` : baseTitle;
    const added = Math.max(0, counts.pending - start.pending) + Math.max(0, counts.claims - start.claims);
    if (banner && added > 0) {
      bannerCount.textContent = String(added);
      banner.hidden = false;
    }
  }

  async function poll() {
    timer = null;
    if (document.hidden) return;
    try {
      const res = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (!res.ok || !(res.headers.get("content-type") || "").includes("json")) return;  // 로그아웃 등 → 멈춤
      render(await res.json());
    } catch (e) {
      // 잠깐 연결이 끊긴 경우: 다음 차례에 다시 시도
    }
    schedule();
  }

  function schedule() {
    if (!timer && !document.hidden) timer = setTimeout(poll, INTERVAL_MS);
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      clearTimeout(timer);
      timer = null;
    } else {
      schedule();
    }
  });
  schedule();
})();
