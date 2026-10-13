/* University search skeleton (SRS 4.4): search, filter by country/ranking, paginate. */
(function () {
  "use strict";
  const { api, requireAuth, $, $$, esc, pager, debounce, toast } = AEC;
  const user = requireAuth();
  if (!user) return;

  const state = { page: 1, page_size: 12, q: "", country: "", max_rank: "", sort: "rank" };
  let preferred = [];

  function card(u) {
    const isPreferred = preferred.some((c) => c.toLowerCase() === String(u.country).toLowerCase());
    return `<article class="card uni">
      <div class="rank">#${esc(u.rank ?? "—")} world ranking</div>
      <h3>${esc(u.name)}</h3>
      <div class="meta"><span class="badge">${esc(u.country)}</span>${isPreferred ? '<span class="badge badge-brand">In your target countries</span>' : ""}</div>
      <div class="foot"><button class="btn btn-outline btn-sm" data-id="${esc(u.id)}">View courses</button></div>
    </article>`;
  }

  async function load() {
    const results = $("#results");
    try {
      const data = await api("/universities/", { query: state });
      $("#count").textContent = `${data.count} universit${data.count === 1 ? "y" : "ies"}`;
      results.innerHTML = data.results.length ? data.results.map(card).join("") : `<p class="empty" style="grid-column:1/-1">No universities match these filters.</p>`;
      $$("[data-id]", results).forEach((b) => b.addEventListener("click", () => showCourses(b.dataset.id)));
      pager($("#pager"), data, (p) => { state.page = p; load(); window.scrollTo({ top: 0, behavior: "smooth" }); });
    } catch (err) {
      results.innerHTML = `<div class="alert alert-error" style="grid-column:1/-1">${esc(err.message)}</div>`;
    }
  }

  async function showCourses(id) {
    try {
      const u = await api(`/universities/${encodeURIComponent(id)}/`);
      AEC.openDrawer({
        title: u.name,
        body: `<p class="muted">${esc(u.country)} · World ranking #${esc(u.rank ?? "—")}</p>
          ${u.courses.length
            ? `<ul>${u.courses.map((c) => `<li>${esc(c.name)}${c.level ? ` <span class="badge">${esc(c.level)}</span>` : ""}</li>`).join("")}</ul>`
            : `<div class="alert alert-info">Course and intake data for this university has not been added yet. Course management is planned for the next sprint.</div>`}`,
      });
    } catch (err) { toast(err.message, "error"); }
  }

  async function init() {
    const countries = await api("/universities/countries/");
    $("#country").insertAdjacentHTML("beforeend", countries.map((c) => `<option value="${esc(c.country)}">${esc(c.country)} (${c.count})</option>`).join(""));

    if (user.role === "student") {
      try {
        const me = await api("/students/me/");
        const p = me.preferences || {};
        preferred = p.countries || [];
        const bar = $("#context");
        bar.classList.remove("hidden");
        bar.innerHTML = `<span>Searching for <b>${esc(me.full_name)}</b></span>
          ${me.academic?.cgpa ? `<span>CGPA <b>${esc(me.academic.cgpa)}</b>${me.academic.gpa_scale ? ` / ${esc(me.academic.gpa_scale)}` : ""}</span>` : ""}
          <span>Targets <b>${esc(preferred.join(", ") || "not set")}</b></span>
          ${p.intake ? `<span>Intake <b>${esc(p.intake)}</b></span>` : ""}
          ${p.budget?.max ? `<span>Budget <b>${esc(`${p.budget.min ?? 0}–${p.budget.max} ${p.budget.currency}`)}</b></span>` : ""}
          <a href="/profile/" style="margin-left:auto">Edit preferences →</a>`;
      } catch (e) { /* context bar is optional */ }
    }
  }

  $("#q").addEventListener("input", debounce((e) => { state.q = e.target.value.trim(); state.page = 1; load(); }));
  for (const id of ["country", "max_rank", "sort"]) {
    $("#" + id).addEventListener("change", (e) => { state[id] = e.target.value; state.page = 1; load(); });
  }

  init().catch((err) => toast(err.message, "error")).finally(load);
})();
