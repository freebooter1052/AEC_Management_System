import { useCallback, useRef, useState } from "react";
import { flattenErrors } from "./api";

export const getPath = (obj, path) => path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);

/** Immutable set of a dotted path. */
export function setPath(obj, path, value) {
  const [head, ...rest] = path.split(".");
  const base = obj && typeof obj === "object" ? obj : {};
  return { ...base, [head]: rest.length ? setPath(base[head], rest.join("."), value) : value };
}

/** DRF error payload -> { "academic.cgpa": "message", ... } */
export function fieldErrors(data, prefix = "", out = {}) {
  if (!data || typeof data !== "object") return out;
  for (const [key, val] of Object.entries(data)) {
    const name = prefix ? `${prefix}.${key}` : key;
    if (val && typeof val === "object" && !Array.isArray(val)) fieldErrors(val, name, out);
    else out[name] = flattenErrors(val).join(" ");
  }
  return out;
}

export function trimStrings(value) {
  if (typeof value === "string") return value.trim();
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, trimStrings(v)]));
  return value;
}

/**
 * Minimal form state: `bind(path, type)` wires an input to a dotted path in `values`;
 * `showErrors(apiData)` maps DRF errors to fields and focuses the first invalid one.
 */
export function useForm(initial = {}) {
  const [values, setValues] = useState(initial);
  const [errors, setErrors] = useState({});
  const ref = useRef(null);

  const set = useCallback((path, v) => setValues((prev) => setPath(prev, path, v)), []);

  const bind = (path, type = "text") => {
    const v = getPath(values, path);
    if (type === "bool") return { name: path, checked: !!v, onChange: (e) => set(path, e.target.checked) };
    if (type === "number") return { name: path, value: v ?? "", onChange: (e) => set(path, e.target.value === "" ? null : Number(e.target.value)) };
    if (type === "date") return { name: path, value: v ?? "", onChange: (e) => set(path, e.target.value || null) };
    return { name: path, value: v ?? "", onChange: (e) => set(path, e.target.value) };
  };

  const showErrors = (data) => {
    setErrors(fieldErrors(data));
    requestAnimationFrame(() => ref.current?.querySelector(".field .error")?.closest(".field")?.querySelector("input,select,textarea")?.focus());
  };

  return { values, setValues, set, bind, errors, setErrors, showErrors, clearErrors: () => setErrors({}), ref };
}
