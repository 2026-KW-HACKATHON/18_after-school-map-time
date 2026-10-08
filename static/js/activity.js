/* Filters apply only to the user's recent reports already displayed on the page. */
(function () {
  const buttons = [...document.querySelectorAll("[data-activity-filter]")];
  const rows = [...document.querySelectorAll("[data-activity-status]")];
  const empty = document.querySelector("[data-activity-empty]");
  buttons.forEach((button) => button.addEventListener("click", () => {
    const selected = button.dataset.activityFilter;
    buttons.forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
    rows.forEach((row) => { row.hidden = selected !== "ALL" && row.dataset.activityStatus !== selected; });
    if (empty) empty.hidden = rows.some((row) => !row.hidden);
  }));
})();
