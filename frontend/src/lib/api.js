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

export class ApiError extends Error {
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

function apiUrl(path, query) {
  let url = "/api" + path;
  if (query) {
    const qs = new URLSearchParams(Object.entries(query).filter(([, v]) => v !== "" && v !== null && v !== undefined));
    if ([...qs].length) url += "?" + qs;
  }
  return url;
}

async function send(path, { method = "GET", body, form, query } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json"; // FormData sets its own boundary
  if (session.token) headers.Authorization = "Bearer " + session.token;
  let res;
  try {
    res = await fetch(apiUrl(path, query), { method, headers, body: form ?? (body !== undefined ? JSON.stringify(body) : undefined) });
  } catch (e) {
    throw new ApiError(0, null);
  }
  if (res.status === 401 && session.token) {
    session.clear();
    window.location.href = "/login/?next=" + encodeURIComponent(window.location.pathname + window.location.search) + "&expired=1";
    throw new ApiError(401, await res.json().catch(() => null));
  }
  if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null));
  return res;
}

/** JSON API call. Pass `body` for JSON, or `form` (a FormData) for file uploads. */
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
