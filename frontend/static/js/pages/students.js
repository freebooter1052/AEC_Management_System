/* Student roster: counsellors see their assigned students; administrators see everyone and assign counsellors. */
(function () {
  "use strict";
  const { api, requireAuth, $, $$, esc, toast, statusBadge, progressBar, pager, debounce, openDrawer, closeDrawer, showFieldErrors } = AEC;
  const user = requireAuth(["counsellor", "admin"]);
  if (!user) return;

  const isAdmin = user.role === "admin";
  const params = new URLSearchParams(location.search);
  const state = { page: 1, q: "", status: "", counsellor: params.get("unassigned") ? "__none__" : (params.get("counsellor_id") || "") };
  let counsellors = [];

  $("#title").textContent = isAdmin ? "Students" : "My students";
  $("#subtitle").textContent = isAdmin
    ? "Every registered student. Assign or reassign counsellors from here."
    : "Students assigned to you. Open a profile to review or update it.";
  if (!isAdmin) $("#col-counsellor").remove();

  async function load() {
    const query = { page: state.page, q: state.q, status: state.status };
    if (state.counsellor === "__none__") query.unassigned = "true";
    else if (state.counsellor) query.counsellor_id = state.counsellor;
    const rows = $("#rows");
    try {
      const data = await api("/students/", { query });
      $("#count").textContent = `${data.count} student${data.count === 1 ? "" : "s"}`;
      const cols = isAdmin ? 6 : 5;
      rows.innerHTML = data.results.length ? data.results.map((s) => `<tr>
          <td><a class="name" href="/students/${encodeURIComponent(s.id)}/">${esc(s.full_name || "(no name)")}</a><div class="small muted">${esc(s.email)}</div></td>
          <td>${esc(s.countries.join(", ") || "—")}<div class="small muted">${esc([s.degree_level, s.intake].filter(Boolean).join(" · "))}</div></td>
          <td style="min-width:140px">${progressBar(s.profile_completion)}</td>
          <td>${statusBadge(s.onboarding_status)}</td>
          ${isAdmin ? `<td>${s.counsellor_id ? esc(s.counsellor_name || "Unknown counsellor") : '<span class="badge badge-warn">Unassigned</span>'}</td>` : ""}
          <td style="text-align:right;white-space:nowrap">
            ${isAdmin ? `<button class="btn btn-outline btn-sm" data-assign="${esc(s.id)}" data-name="${esc(s.full_name)}" data-current="${esc(s.counsellor_id || "")}">${s.counsellor_id ? "Reassign" : "Assign"}</button>` : ""}
            <a class="btn btn-outline btn-sm" href="/students/${encodeURIComponent(s.id)}/">Open</a></td>
        </tr>`).join("")
        : `<tr><td colspan="${cols}" class="empty">${state.q || state.status || state.counsellor ? "No students match these filters." : (isAdmin ? "No students yet." : "No students are assigned to you yet.")}</td></tr>`;
      $$("[data-assign]").forEach((b) => b.addEventListener("click", () => openAssign(b.dataset.assign, b.dataset.name, b.dataset.current)));
      pager($("#pager"), data, (p) => { state.page = p; load(); });
    } catch (err) {
      rows.innerHTML = `<tr><td colspan="6"><div class="alert alert-error" style="margin:0">${esc(err.message)}</div></td></tr>`;
    }
  }

  function openAssign(studentId, name, current) {
    const drawer = openDrawer({
      title: current ? "Reassign counsellor" : "Assign counsellor",
      body: `<p class="muted">Student: <b>${esc(name)}</b></p>
        <form id="assign-form"><div class="field"><label for="assign-to">Counsellor</label>
        <select id="assign-to" name="counsellor_id"><option value="">Select…</option>
        ${counsellors.map((c) => `<option value="${esc(c.id)}" ${c.id === current ? "selected" : ""} ${c.workload.available === 0 && c.id !== current ? "disabled" : ""}>
          ${esc(c.name)} — ${c.workload.assigned}/${c.workload.capacity}${c.region ? " · " + esc(c.region) : ""}${c.workload.available === 0 ? " (full)" : ""}</option>`).join("")}
        </select><span class="hint">Counsellors at capacity cannot be selected.</span></div></form>
        ${counsellors.length ? "" : '<div class="alert alert-warn">No active counsellors. <a href="/counsellors/?new=1">Create one first</a>.</div>'}`,
      footer: `${current ? '<button class="btn btn-danger" id="unassign">Unassign</button>' : ""}<button class="btn btn-outline" id="cancel">Cancel</button><button class="btn btn-primary" id="save">Save</button>`,
    });
    const submit = async (counsellorId) => {
      try {
        const doc = await api(`/students/${encodeURIComponent(studentId)}/assign-counsellor/`, { method: "POST", body: { counsellor_id: counsellorId } });
        closeDrawer();
        toast(counsellorId ? `${name} assigned to ${doc.counsellor.name}` : `${name} unassigned`);
        await loadCounsellors();
        load();
      } catch (err) {
        if (err.status === 400) showFieldErrors($("#assign-form", drawer), err.data);
        toast(err.message, "error");
      }
    };
    $("#cancel", drawer).addEventListener("click", closeDrawer);
    $("#save", drawer).addEventListener("click", () => { const v = $("#assign-to", drawer).value; v ? submit(v) : toast("Choose a counsellor.", "error"); });
    $("#unassign", drawer)?.addEventListener("click", () => submit(null));
  }

  async function loadCounsellors() {
    if (!isAdmin) return;
    counsellors = await api("/counsellors/options/");
    const sel = $("#counsellor-filter");
    sel.hidden = false;
    sel.innerHTML = `<option value="">All counsellors</option><option value="__none__">Unassigned only</option>` +
      counsellors.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join("");
    sel.value = state.counsellor;
  }

  function openCreate() {
    const drawer = openDrawer({
      title: "Add student",
      body: `<form id="create-form" novalidate><div class="grid grid-2">
        <div class="field"><label for="cs-first">First name</label><input id="cs-first" name="first_name" required></div>
        <div class="field"><label for="cs-last">Last name</label><input id="cs-last" name="last_name" required></div>
        <div class="field span-2"><label for="cs-email">Email</label><input id="cs-email" name="email" type="email" required></div>
        <div class="field span-2"><label for="cs-pass">Initial password</label><input id="cs-pass" name="password" type="text" required>
          <span class="hint">Share it with the student; they can change it after signing in.</span></div>
        <div class="field span-2"><label for="cs-coun">Counsellor (optional)</label><select id="cs-coun" name="counsellor_id"><option value="">Assign later</option>
          ${counsellors.filter((c) => c.workload.available > 0).map((c) => `<option value="${esc(c.id)}">${esc(c.name)} — ${c.workload.assigned}/${c.workload.capacity}</option>`).join("")}</select></div>
        </div></form>`,
      footer: `<button class="btn btn-outline" id="cancel">Cancel</button><button class="btn btn-primary" id="save">Create student</button>`,
    });
    $("#cancel", drawer).addEventListener("click", closeDrawer);
    $("#save", drawer).addEventListener("click", async () => {
      const form = $("#create-form", drawer);
      const body = Object.fromEntries(new FormData(form).entries());
      if (!body.counsellor_id) delete body.counsellor_id;
      try {
        const doc = await api("/students/", { method: "POST", body });
        closeDrawer();
        toast(`${doc.full_name} created`);
        await loadCounsellors();
        load();
      } catch (err) {
        if (err.status === 400) showFieldErrors(form, err.data);
        toast(err.message, "error");
      }
    });
  }

  if (isAdmin) {
    $("#actions").innerHTML = `<button class="btn btn-primary" id="add-student">Add student</button>`;
    $("#add-student").addEventListener("click", openCreate);
  }

  $("#q").addEventListener("input", debounce((e) => { state.q = e.target.value.trim(); state.page = 1; load(); }));
  $("#status").addEventListener("change", (e) => { state.status = e.target.value; state.page = 1; load(); });
  $("#counsellor-filter").addEventListener("change", (e) => { state.counsellor = e.target.value; state.page = 1; load(); });

  loadCounsellors().catch((err) => toast(err.message, "error")).finally(load);
})();
