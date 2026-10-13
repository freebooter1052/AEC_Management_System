/* Counsellors: administrators manage all counsellors; a counsellor edits their own profile. */
(function () {
  "use strict";
  const { api, requireAuth, $, $$, esc, toast, progressBar, pager, debounce, openDrawer, closeDrawer, showFieldErrors, initials } = AEC;
  const user = requireAuth(["counsellor", "admin"]);
  if (!user) return;
  const view = $("#view");

  const profileFields = (c = {}, { admin = false, create = false } = {}) => `<div class="grid grid-2">
    <div class="field span-2"><label for="f-name">Full name</label><input id="f-name" name="name" value="${esc(c.name || "")}" required></div>
    ${create ? `<div class="field span-2"><label for="f-email">Email (sign-in)</label><input id="f-email" name="email" type="email" required></div>
      <div class="field span-2"><label for="f-pass">Initial password</label><input id="f-pass" name="password" type="text" required>
      <span class="hint">At least 8 characters with letters and numbers.</span></div>` : ""}
    <div class="field"><label for="f-phone">Phone</label><input id="f-phone" name="phone" value="${esc(c.phone || "")}" placeholder="+91 98765 43210"></div>
    <div class="field"><label for="f-region">Hub / region</label><input id="f-region" name="region" value="${esc(c.region || "")}" placeholder="South Asia Hub"></div>
    <div class="field span-2"><label for="f-spec">Specialization</label><input id="f-spec" name="specialization" value="${esc(c.specialization || "")}" placeholder="UK & Ireland postgraduate"></div>
    ${admin ? `<div class="field"><label for="f-max">Student capacity</label><input id="f-max" name="max_students" type="number" min="1" max="500" value="${esc(c.max_students || 25)}"></div>
      ${create ? "" : `<div class="field" style="justify-content:flex-end"><label class="checkbox"><input type="checkbox" name="is_active" ${c.is_active !== false ? "checked" : ""}> Active</label></div>`}` : ""}
  </div>`;

  function readForm(form) {
    const body = {};
    $$("[name]", form).forEach((el) => {
      if (el.type === "checkbox") body[el.name] = el.checked;
      else if (el.type === "number") body[el.name] = el.value === "" ? undefined : Number(el.value);
      else body[el.name] = el.value.trim();
    });
    return body;
  }

  // ============================================================ counsellor (self)
  async function renderSelf() {
    $("#title").textContent = "My counsellor profile";
    $("#subtitle").textContent = "How students and administrators see you.";
    const c = await api("/counsellors/me/");
    const w = c.workload;
    view.innerHTML = `<div class="layout-2">
      <div class="card"><h3>Profile</h3><form id="self-form" novalidate>${profileFields(c)}
        <div class="field"><label>Email (sign-in)</label><input value="${esc(c.email)}" readonly></div>
        <div class="form-actions"><span class="status"></span><button class="btn btn-primary" type="submit">Save profile</button></div></form></div>
      <div class="stack">
        <div class="card counsellor-dock"><div class="row"><div class="avatar">${esc(initials(c.name))}</div>
          <div><div style="font-weight:600">${esc(c.name)}</div><div class="small muted">${esc(c.region || "")}</div></div></div>
          <h3>Workload</h3>${progressBar(w.utilisation_pct, `${w.assigned}/${w.capacity}`)}
          <p class="small muted" style="margin-top:.6rem">${w.available} open slot(s). Capacity is set by an administrator.</p>
          <a class="btn btn-outline btn-sm" href="/students/">View my students</a></div>
      </div></div>`;
    const form = $("#self-form");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("/counsellors/me/", { method: "PATCH", body: readForm(form) });
        showFieldErrors(form, null);
        $(".status", form).textContent = "Saved ✓";
        toast("Profile saved");
      } catch (err) {
        if (err.status === 400) showFieldErrors(form, err.data);
        toast(err.message, "error");
      }
    });
  }

  // ============================================================ admin
  const state = { page: 1, q: "", active: "" };

  function renderAdminShell() {
    $("#title").textContent = "Counsellors";
    $("#subtitle").textContent = "Create counsellor accounts, set capacity and watch workload.";
    $("#actions").innerHTML = `<button class="btn btn-primary" id="add">Add counsellor</button>`;
    $("#add").addEventListener("click", () => openEditor(null));
    view.innerHTML = `<div class="card">
      <div class="card-head"><div class="toolbar">
        <input type="search" id="q" placeholder="Search name, email, region…" aria-label="Search counsellors">
        <select id="active" aria-label="Filter by status"><option value="">All</option><option value="true">Active</option><option value="false">Inactive</option></select>
      </div><span class="small muted" id="count"></span></div>
      <div class="table-wrap"><table><thead><tr><th>Counsellor</th><th>Specialization</th><th>Region</th><th style="width:22%">Workload</th><th>Status</th><th></th></tr></thead>
      <tbody id="rows"><tr><td colspan="6" class="loading">Loading…</td></tr></tbody></table></div>
      <div class="pager" id="pager"></div></div>`;
    $("#q").addEventListener("input", debounce((e) => { state.q = e.target.value.trim(); state.page = 1; loadList(); }));
    $("#active").addEventListener("change", (e) => { state.active = e.target.value; state.page = 1; loadList(); });
  }

  let current = [];
  async function loadList() {
    try {
      const data = await api("/counsellors/", { query: state });
      current = data.results;
      $("#count").textContent = `${data.count} counsellor${data.count === 1 ? "" : "s"}`;
      $("#rows").innerHTML = data.results.length ? data.results.map((c) => `<tr>
          <td><span class="name">${esc(c.name)}</span><div class="small muted">${esc(c.email)}</div></td>
          <td>${esc(c.specialization || "—")}</td><td>${esc(c.region || "—")}</td>
          <td>${progressBar(c.workload.utilisation_pct, `${c.workload.assigned}/${c.workload.capacity}`)}</td>
          <td>${c.is_active ? '<span class="badge badge-ok">Active</span>' : '<span class="badge">Inactive</span>'}</td>
          <td style="text-align:right;white-space:nowrap"><a class="btn btn-outline btn-sm" href="/students/?counsellor_id=${encodeURIComponent(c.id)}">Students</a>
            <button class="btn btn-outline btn-sm" data-edit="${esc(c.id)}">Edit</button></td></tr>`).join("")
        : `<tr><td colspan="6" class="empty">${state.q || state.active ? "No counsellors match." : "No counsellors yet — add the first one."}</td></tr>`;
      $$("[data-edit]").forEach((b) => b.addEventListener("click", () => openEditor(current.find((c) => c.id === b.dataset.edit))));
      pager($("#pager"), data, (p) => { state.page = p; loadList(); });
    } catch (err) {
      $("#rows").innerHTML = `<tr><td colspan="6"><div class="alert alert-error" style="margin:0">${esc(err.message)}</div></td></tr>`;
    }
  }

  function openEditor(c) {
    const create = !c;
    const drawer = openDrawer({
      title: create ? "Add counsellor" : `Edit ${c.name}`,
      body: `<form id="edit-form" novalidate>${profileFields(c || {}, { admin: true, create })}</form>
        ${create ? "" : `<p class="small muted">Sign-in email: ${esc(c.email)} · ${c.workload.assigned} student(s) assigned</p>`}`,
      footer: `${create ? "" : '<button class="btn btn-danger" id="delete" style="margin-right:auto">Delete</button>'}
        <button class="btn btn-outline" id="cancel">Cancel</button><button class="btn btn-primary" id="save">${create ? "Create counsellor" : "Save changes"}</button>`,
    });
    const form = $("#edit-form", drawer);
    $("#cancel", drawer).addEventListener("click", closeDrawer);
    $("#save", drawer).addEventListener("click", async () => {
      try {
        const saved = await api(create ? "/counsellors/" : `/counsellors/${encodeURIComponent(c.id)}/`, { method: create ? "POST" : "PATCH", body: readForm(form) });
        closeDrawer();
        toast(create ? `${saved.name} can now sign in to the counsellor portal` : "Counsellor updated");
        loadList();
      } catch (err) {
        if (err.status === 400) showFieldErrors(form, err.data);
        toast(err.message, "error");
      }
    });
    $("#delete", drawer)?.addEventListener("click", async () => {
      if (!confirm(`Delete ${c.name} and their sign-in account? This cannot be undone.`)) return;
      try {
        await api(`/counsellors/${encodeURIComponent(c.id)}/`, { method: "DELETE" });
        closeDrawer(); toast("Counsellor deleted"); loadList();
      } catch (err) { toast(err.message, "error"); }
    });
  }

  if (user.role === "admin") {
    renderAdminShell();
    loadList();
    if (new URLSearchParams(location.search).get("new")) openEditor(null);
  } else {
    renderSelf().catch((err) => { view.innerHTML = `<div class="alert alert-error">${esc(err.message)}</div>`; });
  }
})();
