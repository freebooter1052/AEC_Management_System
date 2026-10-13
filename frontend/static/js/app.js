/* Shared frontend helpers: API client, session, role-aware app shell, small UI utilities. */
(function () {
  "use strict";

  const TOKEN_KEY = "aec.token";
  const USER_KEY = "aec.user";

  // ---------------------------------------------------------------- session
  const session = {
    get token() { try { return localStorage.getItem(TOKEN_KEY); } catch (e) { return null; } },
    get user() { try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); } catch (e) { return null; } },
    save(token, user) {
      try { localStorage.setItem(TOKEN_KEY, token); localStorage.setItem(USER_KEY, JSON.stringify(user)); } catch (e) { /* private mode */ }
    },
    clear() { try { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); } catch (e) { /* ignore */ } },
  };

  // ---------------------------------------------------------------- API
  class ApiError extends Error {
    constructor(status, data) {
      super(ApiError.message(data, status));
      this.status = status;
      this.data = data || {};
    }
    static message(data, status) {
      if (data && typeof data.detail === "string") return data.detail;
      if (status === 0) return "Cannot reach the server. Is it running?";
      if (data && typeof data === "object") {
        const first = Object.entries(data)[0];
        if (first) return `${first[0]}: ${flattenErrors(first[1])[0]}`;
      }
      return `Request failed (${status}).`;
    }
  }

  function flattenErrors(v) {
    if (Array.isArray(v)) return v.flatMap(flattenErrors);
    if (v && typeof v === "object") return Object.values(v).flatMap(flattenErrors);
    return [String(v)];
  }

  async function api(path, { method = "GET", body, query } = {}) {
    let url = "/api" + path;
    if (query) {
      const qs = new URLSearchParams(Object.entries(query).filter(([, v]) => v !== "" && v !== null && v !== undefined));
      if ([...qs].length) url += "?" + qs;
    }
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (session.token) headers.Authorization = "Bearer " + session.token;

    let res;
    try {
      res = await fetch(url, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
    } catch (e) {
      throw new ApiError(0, null);
    }
    const data = res.status === 204 ? null : await res.json().catch(() => null);
    if (res.status === 401 && session.token) {
      session.clear();
      location.href = "/login/?next=" + encodeURIComponent(location.pathname + location.search) + "&expired=1";
      throw new ApiError(401, data);
    }
    if (!res.ok) throw new ApiError(res.status, data);
    return data;
  }

  // ---------------------------------------------------------------- UI helpers
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function initials(name) {
    return (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("");
  }

  function toast(message, kind = "info") {
    let host = $(".toast-host");
    if (!host) { host = document.createElement("div"); host.className = "toast-host"; host.setAttribute("role", "status"); document.body.appendChild(host); }
    const el = document.createElement("div");
    el.className = "toast" + (kind === "error" ? " error" : "");
    el.textContent = message;
    host.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  }

  function formatDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  }

  const STATUS_BADGE = {
    registered: ["Registered", "badge"],
    in_progress: ["In progress", "badge badge-warn"],
    profile_complete: ["Profile complete", "badge badge-info"],
    ready: ["Ready", "badge badge-ok"],
  };
  function statusBadge(status) {
    const [label, cls] = STATUS_BADGE[status] || [status || "—", "badge"];
    return `<span class="${cls}">${esc(label)}</span>`;
  }

  function progressBar(pct, label) {
    const p = Math.max(0, Math.min(100, Number(pct) || 0));
    const cls = p >= 100 ? "bar ok" : "bar";
    return `<div class="bar-row"><div class="${cls}" role="progressbar" aria-valuenow="${p}" aria-valuemin="0" aria-valuemax="100"><span style="width:${p}%"></span></div><span class="num">${esc(label ?? p + "%")}</span></div>`;
  }

  /** Render pagination controls for a {count,page,total_pages} payload. */
  function pager(el, data, onPage) {
    if (!data || data.count === 0) { el.innerHTML = ""; return; }
    const from = (data.page - 1) * data.page_size + 1;
    const to = Math.min(data.count, data.page * data.page_size);
    el.innerHTML = `<span>${from}–${to} of ${data.count}</span>
      <span class="toolbar"><button class="btn btn-outline btn-sm" data-p="${data.page - 1}" ${data.page <= 1 ? "disabled" : ""}>Previous</button>
      <button class="btn btn-outline btn-sm" data-p="${data.page + 1}" ${data.page >= data.total_pages ? "disabled" : ""}>Next</button></span>`;
    $$("button[data-p]", el).forEach((b) => b.addEventListener("click", () => onPage(Number(b.dataset.p))));
  }

  /** Show field errors returned by DRF next to inputs named like "academic.cgpa". */
  function showFieldErrors(form, data, prefix = "") {
    $$(".field .error", form).forEach((e) => e.remove());
    if (!data || typeof data !== "object") return;
    for (const [key, val] of Object.entries(data)) {
      const name = prefix ? `${prefix}.${key}` : key;
      if (val && typeof val === "object" && !Array.isArray(val)) { showFieldErrors(form, val, name); continue; }
      const input = form.querySelector(`[name="${CSS.escape(name)}"]`);
      if (input) {
        const err = document.createElement("div");
        err.className = "error";
        err.textContent = flattenErrors(val).join(" ");
        input.closest(".field")?.appendChild(err);
      }
    }
    // focus the first invalid field
    if (!prefix) $$(".field .error", form)[0]?.closest(".field")?.querySelector("input,select")?.focus();
  }

  function debounce(fn, ms = 300) {
    let t; return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }

  // ---------------------------------------------------------------- shell
  const ICONS = {
    dashboard: '<path d="M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z"/>',
    profile: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    students: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><circle cx="17.5" cy="9" r="2.5"/><path d="M16 14.2a5 5 0 0 1 6 4.8"/>',
    counsellors: '<path d="M4 5h16v11H8l-4 4z"/><path d="M8 9h8M8 12h5"/>',
    universities: '<path d="M3 9l9-5 9 5-9 5z"/><path d="M7 11.5V16c0 1.5 2.2 3 5 3s5-1.5 5-3v-4.5"/>',
    applications: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h3"/>',
  };
  const NAV = {
    student: [["dashboard", "Dashboard", "/dashboard/"], ["profile", "My profile", "/profile/"], ["universities", "Universities", "/universities/"], ["applications", "Applications", null]],
    counsellor: [["dashboard", "Dashboard", "/dashboard/"], ["students", "My students", "/students/"], ["counsellors", "My profile", "/counsellors/"], ["universities", "Universities", "/universities/"]],
    admin: [["dashboard", "Dashboard", "/dashboard/"], ["students", "Students", "/students/"], ["counsellors", "Counsellors", "/counsellors/"], ["universities", "Universities", "/universities/"]],
  };
  const ROLE_LABEL = { student: "Student", counsellor: "Counsellor", admin: "Administrator" };

  /** Guard a page: redirect to login if signed out, to the dashboard if the role is not allowed. */
  function requireAuth(roles) {
    const user = session.user;
    if (!session.token || !user) {
      location.replace("/login/?next=" + encodeURIComponent(location.pathname + location.search));
      return null;
    }
    if (roles && !roles.includes(user.role)) {
      location.replace("/dashboard/");
      return null;
    }
    renderShell(user);
    return user;
  }

  function renderShell(user) {
    const nav = $("#nav");
    if (nav) {
      const here = location.pathname;
      nav.innerHTML = (NAV[user.role] || []).map(([icon, label, href]) => {
        const svg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[icon]}</svg>`;
        if (!href) return `<a aria-disabled="true" title="Planned for a later sprint">${svg}${esc(label)}<span class="soon">Soon</span></a>`;
        const active = here === href || (href !== "/dashboard/" && here.startsWith(href));
        return `<a href="${href}" class="${active ? "active" : ""}" ${active ? 'aria-current="page"' : ""}>${svg}${esc(label)}</a>`;
      }).join("");
    }
    const who = $("#who");
    if (who) {
      who.innerHTML = `<div class="meta" style="text-align:right"><div style="font-weight:600">${esc(user.full_name || user.email)}</div>
        <div class="small muted">${esc(user.email)}</div></div>
        <span class="role-badge">${esc(ROLE_LABEL[user.role] || user.role)}</span>
        <div class="avatar" aria-hidden="true">${esc(initials(user.full_name || user.email))}</div>
        <button class="btn btn-outline btn-sm" id="logout">Sign out</button>`;
      $("#logout").addEventListener("click", logout);
    }
    $("#menu-toggle")?.addEventListener("click", () => $(".sidebar").classList.toggle("open"));
  }

  async function logout() {
    try { await api("/auth/logout/", { method: "POST" }); } catch (e) { /* token may already be invalid */ }
    session.clear();
    location.href = "/login/";
  }

  // ---------------------------------------------------------------- drawer
  function openDrawer({ title, body, footer }) {
    closeDrawer();
    const backdrop = document.createElement("div");
    backdrop.className = "drawer-backdrop";
    const drawer = document.createElement("aside");
    drawer.className = "drawer";
    drawer.setAttribute("role", "dialog");
    drawer.setAttribute("aria-modal", "true");
    drawer.setAttribute("aria-label", title);
    drawer.innerHTML = `<header><h2 style="margin:0">${esc(title)}</h2><button class="icon-btn" aria-label="Close">&times;</button></header>
      <div class="body">${body}</div>${footer ? `<footer>${footer}</footer>` : ""}`;
    document.body.append(backdrop, drawer);
    const close = () => closeDrawer();
    backdrop.addEventListener("click", close);
    $(".icon-btn", drawer).addEventListener("click", close);
    document.addEventListener("keydown", escClose);
    setTimeout(() => drawer.querySelector("input,select,button")?.focus(), 30);
    return drawer;
  }
  function escClose(e) { if (e.key === "Escape") closeDrawer(); }
  function closeDrawer() {
    $$(".drawer, .drawer-backdrop").forEach((el) => el.remove());
    document.removeEventListener("keydown", escClose);
  }

  /** Associate each .field label with its control so screen readers announce it (pages may omit for/id). */
  let labelSeq = 0;
  function linkLabels(root = document) {
    $$(".field", root).forEach((field) => {
      const label = field.querySelector(":scope > label");
      const control = field.querySelector("input:not([type=checkbox]), select, textarea");
      if (!label || !control || label.htmlFor || label.contains(control)) return;
      if (!control.id) control.id = "f" + ++labelSeq;
      label.htmlFor = control.id;
    });
  }
  document.addEventListener("DOMContentLoaded", () => linkLabels());
  new MutationObserver(() => linkLabels()).observe(document.documentElement, { childList: true, subtree: true });

  window.AEC = {
    api, ApiError, session, requireAuth, logout,
    $, $$, esc, initials, toast, formatDate, statusBadge, progressBar, pager, showFieldErrors, flattenErrors, debounce,
    openDrawer, closeDrawer, ROLE_LABEL,
  };
})();
