/* Reuse the existing rejection action; no additional report state is created. */
(function () {
  const panel = document.getElementById("ops-reject-panel");
  if (!panel) return;
  document.querySelector("[data-ops-reject]")?.addEventListener("click", (event) => {
    event.preventDefault();
    panel.open = true;
    panel.scrollIntoView({ block: "start" });
    panel.querySelector("textarea")?.focus({ preventScroll: true });
  });
})();
