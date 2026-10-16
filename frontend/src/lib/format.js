export function initials(name) {
  return (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("");
}

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * A Date for an API value. Date-only values ("2027-01-15": deadlines, birthdays, due dates) are calendar dates,
 * so they become local midnight - `new Date("2027-01-15")` would read them as UTC and show the previous day
 * west of Greenwich. Timestamps ("2027-01-15T09:30:00Z") keep their instant and display in local time.
 */
export function parseDate(value) {
  if (!value) return null;
  const m = DATE_ONLY.exec(value);
  const d = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(value);
  return isNaN(d) ? null : d;
}

export function formatDate(value) {
  if (!value) return "—";
  const d = parseDate(value);
  return d ? d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : String(value);
}

export function formatDateTime(value) {
  if (!value) return "—";
  const d = parseDate(value);
  return d ? d.toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : String(value);
}

export function formatTime(value) {
  const d = parseDate(value);
  return d ? d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : "";
}

/** Local calendar date as YYYY-MM-DD (for date inputs and calendar keys). */
export const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const IRREGULAR = { university: "universities", entry: "entries", country: "countries", copy: "copies" };

/** plural(1, "day") -> "1 day"; plural(3, "day") -> "3 days"; plural(2, "copy") -> "2 copies". */
export const plural = (n, word, many) => `${n} ${n === 1 ? word : many || IRREGULAR[word] || `${word}s`}`;
