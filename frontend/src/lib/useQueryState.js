import { useCallback, useState } from "react";

/**
 * List state (filters, page, sort) kept in the URL query string, so a refresh, a shared link or
 * Back from a record restores the same view. Updates use history.replaceState: the page is not
 * remounted and no history entry is added per keystroke.
 *
 * `spec` maps each key to its default and, optionally, the values allowed:
 *   { status: { default: "", allowed: ["", "Planned"] }, page: { default: 1, type: "page" }, open: { default: false, type: "bool" } }
 * Invalid values in the URL fall back to the default. Only non-default values are written.
 */
export function readQuery(spec, search) {
  const params = new URLSearchParams(search);
  const out = {};
  for (const [key, rule] of Object.entries(spec)) {
    const raw = params.get(key);
    out[key] = parseValue(rule, raw);
  }
  return out;
}

function parseValue(rule, raw) {
  if (raw === null) return rule.default;
  if (rule.type === "page") {
    const n = Number(raw);
    return Number.isInteger(n) && n >= 1 && n <= 10000 ? n : rule.default;
  }
  if (rule.type === "bool") return raw === "1" || raw === "true";
  const value = raw.slice(0, 200);
  if (rule.allowed && !rule.allowed.includes(value)) return rule.default;
  if (rule.pattern && !rule.pattern.test(value)) return rule.default;
  return value;
}

export function writeQuery(spec, state, search) {
  const params = new URLSearchParams(search);
  for (const [key, rule] of Object.entries(spec)) {
    const v = state[key];
    if (v === rule.default || v === "" || v === null || v === undefined || v === false) params.delete(key);
    else params.set(key, rule.type === "bool" ? "1" : String(v));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function useQueryState(spec) {
  const [state, setState] = useState(() => readQuery(spec, window.location.search));
  const update = useCallback((patch) => {
    setState((prev) => {
      const next = { ...prev, ...(typeof patch === "function" ? patch(prev) : patch) };
      const qs = writeQuery(spec, next, window.location.search);
      if (qs !== window.location.search) {
        // Keep React Router's own history state (its index and key) so Back and Forward keep working.
        window.history.replaceState(window.history.state, "", window.location.pathname + qs + window.location.hash);
      }
      return next;
    });
  }, []); // `spec` is a module-level constant
  return [state, update];
}

/** Text kept per browser tab only (not in the URL) - for searches that may contain a student's name. */
export function useSessionText(key) {
  const storageKey = `aec.q.${key}`;
  const [value, setValue] = useState(() => { try { return sessionStorage.getItem(storageKey) || ""; } catch (e) { return ""; } });
  const update = useCallback((v) => {
    setValue(v);
    try { if (v) sessionStorage.setItem(storageKey, v); else sessionStorage.removeItem(storageKey); } catch (e) { /* storage blocked */ }
  }, [storageKey]);
  return [value, update];
}
