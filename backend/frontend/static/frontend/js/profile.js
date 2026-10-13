/* Student profile: the student's own (/profile/) or, for staff, /students/<id>/. */
(function () {
  "use strict";
  const { api, requireAuth, $, $$, esc, toast, statusBadge, progressBar, showFieldErrors, initials, formatDate } = AEC;

  const match = location.pathname.match(/^\/students\/([^/]+)\/?$/);
  const studentId = match ? decodeURIComponent(match[1]) : null;
  const user = requireAuth(studentId ? ["counsellor", "admin"] : ["student"]);
  if (!user) return;

  const endpoint = studentId ? `/students/${encodeURIComponent(studentId)}/` : "/students/me/";
  let doc = null;

  // ------------------------------------------------------------ chips input
  function setupChips(box) {
    const input = document.createElement("input");
    input.setAttribute("aria-label", box.closest(".field").querySelector("label").textContent);
    if (box.dataset.list) input.setAttribute("list", box.dataset.list);
    box.appendChild(input);
    box._values = [];
    box._render = () => {
      $$(".chip", box).forEach((c) => c.remove());
      box._values.forEach((v, i) => {
        const chip = document.createElement("span");
        chip.className = "chip";
        chip.innerHTML = `${esc(v)}<button type="button" aria-label="Remove ${esc(v)}">&times;</button>`;
        chip.querySelector("button").addEventListener("click", () => { box._values.splice(i, 1); box._render(); });
        box.insertBefore(chip, input);
      });
    };
    const add = () => {
      const v = input.value.trim().replace(/,$/, "");
      if (v && !box._values.some((x) => x.toLowerCase() === v.toLowerCase()) && box._values.length < 10) box._values.push(v);
      input.value = "";
      box._render();
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); }
      else if (e.key === "Backspace" && !input.value && box._values.length) { box._values.pop(); box._render(); }
    });
    input.addEventListener("change", add);
    input.addEventListener("blur", add);
  }

  // ------------------------------------------------------------ form <-> doc
  const get = (obj, path) => path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
  function set(obj, path, value) {
    const keys = path.split(".");
    keys.slice(0, -1).reduce((o, k) => (o[k] ??= {}), obj)[keys.at(-1)] = value;
  }

  function fill(form) {
    $$("[name]", form).forEach((el) => {
      const v = get(doc, el.name);
      if (el.type === "checkbox") el.checked = !!v;
      else el.value = v ?? (el.tagName === "SELECT" && el.name.endsWith("currency") ? "USD" : "");
    });
    $$(".chips", form).forEach((box) => { box._values = [...(get(doc, box.dataset.name) || [])]; box._render(); });
  }

  function collect(form) {
    const out = {};
    $$("[name]", form).forEach((el) => {
      if (el.readOnly) return;
      let v;
      if (el.dataset.type === "bool") v = el.checked;
      else if (el.dataset.type === "number") v = el.value === "" ? null : Number(el.value);
      else if (el.dataset.type === "date") v = el.value || null;
      else v = el.value.trim();
      set(out, el.name, v);
    });
    $$(".chips", form).forEach((box) => { $("input", box).dispatchEvent(new Event("change")); set(out, box.dataset.name, box._values); });
    return out;
  }

  // ------------------------------------------------------------ sidebar
  function renderSide() {
    const comp = doc.profile_completion || {};
    $("#gauge").style.setProperty("--pct", comp.overall || 0);
    $("#gauge-value").textContent = (comp.overall || 0) + "%";
    $("#section-bars").innerHTML = ["personal", "academic", "preferences"].map((s) =>
      `<div style="margin-top:.6rem"><div class="small" style="font-weight:600;text-transform:capitalize">${s}</div>${progressBar(comp[s])}</div>`).join("");
    const missing = comp.missing || [];
    $("#missing-title").textContent = missing.length ? `Missing for 100% (${missing.length})` : "All required fields complete";
    $("#missing").innerHTML = missing.length
      ? missing.map((m) => `<li><a href="#" data-goto="${esc(m.section)}" data-field="${esc(m.field)}">${esc(m.label)}</a></li>`).join("")
      : `<li class="done muted">Nothing left to add.</li>`;
    $$("#missing a").forEach((a) => a.addEventListener("click", (e) => {
      e.preventDefault(); showTab(a.dataset.goto);
      const el = document.querySelector(`[name="${CSS.escape(a.dataset.field)}"]`) || document.querySelector(`[data-name="${CSS.escape(a.dataset.field)}"] input`);
      el?.focus();
    }));
    $("#head-badges").innerHTML = statusBadge(doc.onboarding_status) + `<span class="badge">Updated ${esc(formatDate(doc.updated_at))}</span>`;
    $("#json").textContent = JSON.stringify(doc, null, 2);
    renderCounsellor();
  }

  async function renderCounsellor() {
    const card = $("#counsellor-card");
    const c = doc.counsellor;
    const info = c
      ? `<div class="row"><div class="avatar">${esc(initials(c.name))}</div><div><div style="font-weight:600">${esc(c.name)}</div>
           <div class="small muted">${esc(c.specialization || "Education counsellor")}</div></div></div>
         <dl><dt>Email</dt><dd><a href="mailto:${esc(c.email)}">${esc(c.email)}</a></dd><dt>Phone</dt><dd>${esc(c.phone || "—")}</dd>
           <dt>Hub</dt><dd>${esc(c.region || "—")}</dd><dt>Since</dt><dd>${esc(formatDate(doc.counsellor_assigned_at))}</dd></dl>`
      : `<p class="muted" style="margin:0">No counsellor assigned yet.</p>`;
    card.innerHTML = `<h3>Assigned counsellor</h3>${info}`;

    if (user.role !== "admin") return;
    card.insertAdjacentHTML("beforeend", `<div class="field" style="margin:1rem 0 .5rem"><label for="assign-select">${c ? "Reassign to" : "Assign to"}</label>
      <select id="assign-select"><option value="">Loading…</option></select></div>
      <div class="toolbar"><button class="btn btn-primary btn-sm" id="assign-btn">Save assignment</button>
      ${c ? '<button class="btn btn-danger btn-sm" id="unassign-btn">Unassign</button>' : ""}</div>`);
    try {
      const options = await api("/counsellors/options/");
      $("#assign-select").innerHTML = `<option value="">Select a counsellor…</option>` + options.map((o) =>
        `<option value="${esc(o.id)}" ${o.id === doc.counsellor_id ? "selected" : ""} ${o.workload.available === 0 && o.id !== doc.counsellor_id ? "disabled" : ""}>
          ${esc(o.name)} — ${o.workload.assigned}/${o.workload.capacity}${o.region ? " · " + esc(o.region) : ""}</option>`).join("");
    } catch (err) { toast(err.message, "error"); }
    const assign = async (counsellorId) => {
      try {
        doc = await api(`/students/${encodeURIComponent(doc.id)}/assign-counsellor/`, { method: "POST", body: { counsellor_id: counsellorId } });
        toast(counsellorId ? `Assigned to ${doc.counsellor.name}` : "Counsellor unassigned");
        renderSide();
      } catch (err) { toast(err.message, "error"); }
    };
    $("#assign-btn").addEventListener("click", () => { const v = $("#assign-select").value; if (v) assign(v); else toast("Choose a counsellor first.", "error"); });
    $("#unassign-btn")?.addEventListener("click", () => assign(null));
  }

  // ------------------------------------------------------------ tabs & save
  function showTab(name) {
    $$(".section-tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
    $$("form[data-section]").forEach((f) => { f.hidden = f.dataset.section !== name; });
  }
  $$(".section-tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

  $$("form[data-section]").forEach((form) => {
    $$(".chips", form).forEach(setupChips);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const section = form.dataset.section;
      const btn = $("button[type=submit]", form);
      const status = $(".status", form);
      const body = { [section]: collect(form)[section], rev: doc.rev };
      btn.disabled = true; status.textContent = "Saving…";
      try {
        doc = await api(endpoint, { method: "PATCH", body });
        showFieldErrors(form, null);
        renderSide();
        status.textContent = "Saved ✓";
        toast("Profile saved");
        if (!studentId && section === "personal") {
          const u = AEC.session.user; u.full_name = doc.full_name; AEC.session.save(AEC.session.token, u);
        }
      } catch (err) {
        status.textContent = "";
        if (err.status === 400) { showFieldErrors(form, err.data); toast("Please fix the highlighted fields.", "error"); }
        else if (err.status === 409) toast("This profile was changed elsewhere. Reload the page to get the latest version.", "error");
        else toast(err.message, "error");
      } finally { btn.disabled = false; }
    });
  });

  // ------------------------------------------------------------ load
  Promise.all([api(endpoint), api("/universities/countries/").catch(() => [])]).then(([data, countries]) => {
    doc = data;
    $("#country-options").innerHTML = countries.map((c) => `<option value="${esc(c.country)}">`).join("");
    if (studentId) {
      $("#title").textContent = doc.full_name || "Student profile";
      $("#crumb-text").innerHTML = `<a href="/students/">Students</a> / ${esc(doc.full_name)}`;
    } else {
      $("#title").textContent = "My profile";
      if (new URLSearchParams(location.search).get("welcome")) $("#welcome").classList.remove("hidden");
    }
    $$("form[data-section]").forEach(fill);
    renderSide();
    $("#loading").remove();
    $("#profile-layout").hidden = false;
  }).catch((err) => {
    $("#loading").outerHTML = `<div class="alert alert-error">${esc(err.status === 403 ? "You do not have access to this student." : err.message)}</div>`;
  });
})();
