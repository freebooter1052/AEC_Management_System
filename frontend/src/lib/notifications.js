/* Wording for in-app notifications (SRS 4.10). Plain functions, unit tested with `node --test`. */
import { formatDate, parseDate } from "./format.js";

export const CATEGORIES = [
  ["status_change", "Application updates"],
  ["missing_document", "Documents"],
  ["deadline", "Deadlines"],
  ["follow_up", "Follow-ups"],
  ["assignment", "Counsellor"],
  ["writing", "SOP & LOR"],
];
const LABEL = Object.fromEntries(CATEGORIES);
export const categoryLabel = (c) => LABEL[c] || "Notice";

/** "just now", "5 min ago", "3 h ago", "yesterday", "4 days ago", then the date. */
export function timeAgo(value, now = Date.now()) {
  const d = parseDate(value);
  if (!d) return "";
  const s = Math.max(0, Math.round((now - d.getTime()) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  const days = Math.floor(s / 86400);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return formatDate(value);
}

/** Count for the bell badge: "" for none, "99+" for many. */
export const badgeCount = (n) => (!n ? "" : n > 99 ? "99+" : String(n));

/** Only same-site paths are followed from a notification ("/applications/x/"), never "//host" or "https://...". */
export function safeLink(link) {
  return typeof link === "string" && /^\/(?!\/)[\w\-./?=&%]*$/.test(link) ? link : null;
}
