(function () {
  "use strict";
  const { api, requireAuth, $, esc, statusBadge, progressBar } = AEC;
  const user = requireAuth();
  if (!user) return;

  const root = $("#dashboard");
  const kpi = (label, value, sub = "") =>
    `<div class="kpi"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div><div class="sub">${sub}</div></div>`;

  function counsellorCard(c) {
    if (!c) {
      return `<div class="card counsellor-dock"><h3>Your counsellor</h3>
        <p class="muted">No counsellor has been assigned yet. An administrator will match you with a counsellor
        once your profile is underway.</p></div>`;
    }
    return `<div class="card counsellor-dock"><h3>Your counsellor</h3>
      <div class="row"><div class="avatar">${esc(AEC.initials(c.name))}</div>
        <div><div style="font-weight:600">${esc(c.name)}</div><div class="small muted">${esc(c.specialization || "Education counsellor")}</div></div></div>
      <dl><dt>Email</dt><dd><a href="mailto:${esc(c.email)}">${esc(c.email)}</a></dd>
        <dt>Phone</dt><dd>${esc(c.phone || "—")}</dd><dt>Hub</dt><dd>${esc(c.region || "—")}</dd></dl></div>`;
  }

  function renderStudent(d) {
    $("#greeting").textContent = `Welcome, ${d.full_name.split(" ")[0] || "there"}`;
    $("#subtitle").textContent = "Your application readiness at a glance.";
    $("#actions").innerHTML = `<a class="btn btn-primary" href="/profile/">Update profile</a>`;
    const comp = d.profile_completion || {};
    const prefs = d.preferences || {};
    const missing = (comp.missing || []).slice(0, 8);
    root.innerHTML = `
      <div class="kpis">
        ${kpi("Profile readiness", (comp.overall ?? 0) + "%", statusBadge(d.onboarding_status))}
        ${kpi("Counsellor", d.counsellor ? "Assigned" : "Pending", esc(d.counsellor?.name || "Awaiting assignment"))}
        ${kpi("Target countries", (prefs.countries || []).length, esc((prefs.countries || []).join(", ") || "Not set"))}
        ${kpi("Applications", d.applications.total, "Application tracking arrives next sprint")}
      </div>
      <div class="layout-2">
        <div class="stack">
          <div class="card">
            <div class="card-head"><h3>Profile sections</h3><a href="/profile/" class="small">Open profile →</a></div>
            ${["personal", "academic", "preferences"].map((s) =>
              `<div style="margin-bottom:.8rem"><div class="small" style="font-weight:600;text-transform:capitalize;margin-bottom:.3rem">${s}</div>${progressBar(comp[s])}</div>`).join("")}
          </div>
          <div class="card">
            <h3>${missing.length ? "Still needed to reach 100%" : "Profile complete"}</h3>
            ${missing.length
              ? `<ul class="missing-list">${missing.map((m) => `<li>${esc(m.label)}</li>`).join("")}</ul>`
              : `<p class="muted">Every required field is filled in. Your counsellor can now shortlist programmes.</p>`}
          </div>
        </div>
        <div class="stack">
          ${counsellorCard(d.counsellor)}
          <div class="card"><h3>Preferences</h3>
            <dl class="counsellor-dock" style="display:grid;grid-template-columns:auto 1fr;gap:.3rem .8rem;margin:0;font-size:.86rem">
              <dt class="muted">Level</dt><dd style="margin:0">${esc(prefs.degree_level || "—")}</dd>
              <dt class="muted">Intake</dt><dd style="margin:0">${esc(prefs.intake || "—")}</dd>
              <dt class="muted">Courses</dt><dd style="margin:0">${esc((prefs.course_areas || []).join(", ") || "—")}</dd>
              <dt class="muted">Budget</dt><dd style="margin:0">${prefs.budget?.max ? esc(`${prefs.budget.min ?? 0}–${prefs.budget.max} ${prefs.budget.currency}`) : "—"}</dd>
            </dl>
          </div>
        </div>
      </div>`;
  }

  function rosterTable(rows) {
    if (!rows.length) return `<p class="empty">No students assigned yet.</p>`;
    return `<div class="table-wrap"><table><thead><tr><th>Student</th><th>Targets</th><th>Readiness</th><th>Status</th></tr></thead><tbody>
      ${rows.map((s) => `<tr><td><a class="name" href="/students/${encodeURIComponent(s.id)}/">${esc(s.full_name)}</a><div class="small muted">${esc(s.email)}</div></td>
        <td>${esc(s.countries.join(", ") || "—")}<div class="small muted">${esc(s.intake || "")}</div></td>
        <td style="min-width:140px">${progressBar(s.profile_completion)}</td><td>${statusBadge(s.onboarding_status)}</td></tr>`).join("")}
      </tbody></table></div>`;
  }

  function renderCounsellor(d) {
    $("#greeting").textContent = `Good to see you, ${d.name.split(" ")[0]}`;
    $("#subtitle").textContent = "Your caseload and the students who need attention first.";
    $("#actions").innerHTML = `<a class="btn btn-primary" href="/students/">Open roster</a>`;
    const w = d.workload || { assigned: 0, capacity: 0, available: 0, utilisation_pct: 0 };
    const by = d.students_by_status || {};
    root.innerHTML = `
      <div class="kpis">
        ${kpi("Assigned students", w.assigned, `of ${w.capacity} capacity`)}
        ${kpi("Ready to apply", by.ready || 0, "Profile complete & assigned")}
        ${kpi("In progress", (by.in_progress || 0) + (by.registered || 0), "Profiles still being completed")}
        ${kpi("Open slots", w.available, progressBar(w.utilisation_pct, w.utilisation_pct + "% used"))}
      </div>
      <div class="card"><div class="card-head"><h3>Needs attention — lowest profile readiness</h3><a class="small" href="/students/">All students →</a></div>
        ${rosterTable(d.needs_attention)}</div>`;
  }

  function renderAdmin(d) {
    const t = d.totals;
    $("#greeting").textContent = "Administrator console";
    $("#subtitle").textContent = "Agency-wide totals and counsellor workload.";
    $("#actions").innerHTML = `<a class="btn btn-outline" href="/students/?unassigned=1">Assign students</a><a class="btn btn-primary" href="/counsellors/?new=1">Add counsellor</a>`;
    const rows = d.counsellor_workload;
    root.innerHTML = `
      <div class="kpis">
        ${kpi("Students", t.students, `${t.unassigned_students} awaiting a counsellor`)}
        ${kpi("Counsellors", t.counsellors, `${t.active_counsellors} active`)}
        ${kpi("Universities", t.universities, "In the CouchDB catalogue")}
        ${kpi("User accounts", t.users, "All roles")}
      </div>
      ${t.unassigned_students ? `<div class="alert alert-warn">${t.unassigned_students} student(s) have no counsellor. <a href="/students/?unassigned=1">Assign them now →</a></div>` : ""}
      <div class="card"><div class="card-head"><h3>Counsellor workload</h3><a class="small" href="/counsellors/">Manage counsellors →</a></div>
        ${rows.length ? `<div class="table-wrap"><table><thead><tr><th>Counsellor</th><th>Assigned</th><th style="width:40%">Utilisation</th></tr></thead><tbody>
          ${rows.map((c) => `<tr><td class="name">${esc(c.name)}</td><td>${c.assigned} / ${c.capacity}</td>
            <td>${progressBar(c.utilisation_pct)}</td></tr>`).join("")}</tbody></table></div>`
          : `<p class="empty">No counsellors yet. <a href="/counsellors/?new=1">Add the first one</a>.</p>`}
      </div>`;
  }

  api("/dashboard/").then((d) => {
    if (d.role === "student") renderStudent(d);
    else if (d.role === "counsellor") renderCounsellor(d);
    else renderAdmin(d);
  }).catch((err) => { root.innerHTML = `<div class="alert alert-error">${esc(err.message)}</div>`; });
})();
