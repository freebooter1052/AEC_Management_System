/* API client and session storage. The token lives in localStorage under the same keys as before. */
const TOKEN_KEY = "aec.token";
const USER_KEY = "aec.user";

export const session = {
  get token() { try { return localStorage.getItem(TOKEN_KEY); } catch (e) { return null; } },
  get user() { try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); } catch (e) { return null; } },
  save(token, user) {
    try { localStorage.setItem(TOKEN_KEY, token); localStorage.setItem(USER_KEY, JSON.stringify(user)); } catch (e) { /* private mode */ }
  },
  clear() { try { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); } catch (e) { /* ignore */ } },
};

export function flattenErrors(v) {
  if (Array.isArray(v)) return v.flatMap(flattenErrors);
  if (v && typeof v === "object") return Object.values(v).flatMap(flattenErrors);
  return [String(v)];
}

// Readable names for API field keys, so messages never show raw keys such as "counsellor_id".
const FIELD_LABELS = {
  email: "Email address", password: "Password", new_password: "New password", current_password: "Current password",
  first_name: "First name", last_name: "Last name", dial_code: "Dial code", number: "Mobile number", phone: "Phone",
  student_id: "Student", counsellor_id: "Counsellor", course_id: "Course", intake_id: "Intake", university_id: "University",
  application_id: "Application", document_type: "Document type", reference_url: "Link", scheduled_at: "Date and time",
  duration_minutes: "Duration", due_date: "Due date", max_students: "Student capacity", is_active: "Active",
  cgpa: "CGPA", gpa_scale: "GPA scale", gre_status: "GRE / GMAT status", line1: "Address", postal_code: "Postal code",
  countries: "Target countries", course_areas: "Course areas", degree_level: "Degree level", privacy_acknowledged: "Privacy notice",
  specialization: "Specialisation", region: "Region", date_of_birth: "Date of birth", decision_expected: "Decision expected",
};

/** "personal.address.postal_code" -> "Postal code" */
export function fieldLabel(key) {
  const last = String(key).split(".").pop();
  if (FIELD_LABELS[last]) return FIELD_LABELS[last];
  const words = last.replace(/_id$/, "").replace(/_/g, " ").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : "This field";
}

const GENERAL_KEYS = ["detail", "non_field_errors"];

/** Field errors of a DRF 400 body as [label, message] pairs (general messages have no label). */
export function errorEntries(data, prefix = "") {
  if (!data || typeof data !== "object" || Array.isArray(data)) return [];
  const out = [];
  for (const [key, val] of Object.entries(data)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (val && typeof val === "object" && !Array.isArray(val)) out.push(...errorEntries(val, path));
    else out.push([GENERAL_KEYS.includes(key) ? "" : fieldLabel(path), flattenErrors(val).join(" ")]);
  }
  return out;
}

export const NETWORK_MESSAGE = "We could not connect to AEC Admissions. Check your internet connection and try again.";

/** A message a user can act on, for any API failure. Never shows raw keys, URLs or server internals. */
export function friendlyMessage(status, data) {
  const detail = data && (Array.isArray(data.detail) ? data.detail.join(" ") : data.detail);
  if (status === 0) return NETWORK_MESSAGE;
  if (status >= 500) {
    // 503 carries a safe, user-facing message from the API's exception handler.
    return status === 503 && typeof detail === "string" ? detail : "Something went wrong on our side. Please try again in a moment.";
  }
  if (typeof detail === "string" && detail) return detail;
  if (status === 401) return "Your session has ended. Please sign in again.";
  if (status === 403) return "You do not have permission to do that.";
  if (status === 404) return "We could not find that record. It may have been removed.";
  if (status === 409) return "Someone else changed this record meanwhile. Reload to get the latest version, then try again.";
  if (status === 400) {
    const entries = errorEntries(data);
    if (entries.length === 1) return entries[0][0] ? `${entries[0][0]}: ${entries[0][1]}` : entries[0][1];
    if (entries.length > 1) return `Please correct these fields: ${[...new Set(entries.map(([l]) => l || "details"))].join(", ")}.`;
  }
  if (status === 429) return "Too many attempts. Please wait a moment and try again.";
  return "The request could not be completed. Please try again.";
}

export class ApiError extends Error {
  constructor(status, data) {
    super(friendlyMessage(status, data));
    this.status = status;
    this.data = data || {};
  }
  /** True when the body is a field-by-field validation error a form can show beside its inputs. */
  get hasFieldErrors() {
    return this.status === 400 && errorEntries(this.data).some(([label]) => label);
  }
}

function apiUrl(path, query) {
  let url = "/api" + path;
  if (query) {
    const qs = new URLSearchParams(Object.entries(query).filter(([, v]) => v !== "" && v !== null && v !== undefined));
    if ([...qs].length) url += "?" + qs;
  }
  return url;
}

async function send(path, { method = "GET", body, form, query, signal } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json"; // FormData sets its own boundary
  if (session.token) headers.Authorization = "Bearer " + session.token;
  let res;
  try {
    res = await fetch(apiUrl(path, query), { method, headers, signal, body: form ?? (body !== undefined ? JSON.stringify(body) : undefined) });
  } catch (e) {
    if (e?.name === "AbortError") throw e;
    throw new ApiError(0, null);
  }
  if (res.status === 401 && session.token) {
    session.clear();
    window.location.href = "/login/?next=" + encodeURIComponent(window.location.pathname + window.location.search) + "&expired=1";
    throw new ApiError(401, await res.json().catch(() => null));
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    // Diagnostics for developers: method, path and status only - never bodies, which may hold passwords or personal data.
    if (res.status >= 500) console.warn(`API ${method} ${path} failed with ${res.status}`);
    throw new ApiError(res.status, data);
  }
  return res;
}

/** JSON API call. Pass `body` for JSON, or `form` (a FormData) for file uploads; `signal` cancels it. */
export async function api(path, options = {}) {
  const res = await send(path, options);
  return res.status === 204 ? null : res.json().catch(() => null);
}

/** Fetch a protected file with the bearer token and hand it to the browser as a download. */
export async function download(path, filename) {
  const blob = await (await send(path)).blob();
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: filename || "document" });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
