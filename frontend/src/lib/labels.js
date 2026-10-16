/* Wording shown to people for stored values. Plain functions (no JSX), so they can be unit tested with `node --test`. */
import { plural } from "./format.js";

// Stored statuses never change (backend apps/core/vocab.py); only what people read does, so an application
// "Under Review" (at the university) is not confused with a document "Under Review" (with the counsellor).
const APP_STATUS_LABEL = { "Under Review": "University reviewing" };
const DOC_STATUS_LABEL = { "Under Review": "Being checked" };

export const appStatusLabel = (s) => APP_STATUS_LABEL[s] || s;
export const docStatusLabel = (s) => DOC_STATUS_LABEL[s] || s;

/** Countdown wording for an application's `deadline_info` ({state, days_left}); `long` for full sentences. */
export function countdownText(info, { long = false } = {}) {
  if (!info) return "";
  const n = info.days_left;
  if (info.state === "submitted") return long ? "Submitted — the deadline has been met." : "Submitted";
  if (info.state === "closed") return long ? "This application is closed." : "Closed";
  if (n === null || n === undefined) return long ? "No deadline set." : "";
  if (n < 0) return long ? `The deadline passed ${plural(-n, "day")} ago.` : `${plural(-n, "day")} overdue`;
  if (n === 0) return long ? "Due today." : "Due today";
  if (n === 1) return long ? "Due tomorrow." : "Due tomorrow";
  return long ? `Due in ${plural(n, "day")}.` : `${plural(n, "day")} left`;
}

/** "World ranking 12", or a neutral note when the catalogue has no ranking (never implies "unranked"). */
export const rankingText = (rank) => (rank ? `World ranking ${rank}` : "Ranking not available");

/** What happens next after an upload, worded for whoever uploaded it and the status the API returned. */
export function uploadMessage(doc, updated, user) {
  const name = doc.title || doc.document_type;
  if (updated?.status !== "Uploaded") return `${name} saved. Status: ${docStatusLabel(updated?.status || "Uploaded")}.`;
  if (user?.role === "student") return `${name} uploaded. It will be checked before your applications are submitted.`;
  return `${name} uploaded for ${doc.student_name || "the student"}. It is ready for review.`;
}
