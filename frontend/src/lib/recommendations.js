/* Wording and small calculations for recommendations (SRS 4.8). Plain functions, unit tested with `node --test`. */
import { formatDateTime } from "./format.js";

export const FACTOR_STATUS = {
  match: { label: "Matches", tone: "ok", icon: "✓" },
  partial: { label: "Partly matches", tone: "warn", icon: "~" },
  no_match: { label: "Does not match", tone: "err", icon: "✕" },
  unknown: { label: "Not assessed", tone: "", icon: "?" },
};

const ELIGIBILITY = {
  eligible: { label: "Eligible", tone: "ok", text: "Meets every entry requirement recorded for this course." },
  insufficient_data: { label: "Eligibility to confirm", tone: "warn", text: "Some entry requirements are not recorded in the catalogue. Confirm them with the university." },
  ineligible: { label: "Not eligible", tone: "err", text: "Fails an entry requirement recorded for this course." },
};
const NOT_ASSESSED = { label: "Not assessed", tone: "", text: "Made by an earlier version of the engine. Refresh to assess eligibility." };

export const eligibilityInfo = (value) => ELIGIBILITY[value] || NOT_ASSESSED;
export const factorStatus = (value) => FACTOR_STATUS[value] || FACTOR_STATUS.unknown;

/** "86% match", plus how much of the weighting it rests on when some factors could not be assessed. */
export function scoreText(rec) {
  const score = rec?.match_score ?? 0;
  const conf = rec?.confidence;
  if (conf === null || conf === undefined || conf >= 100) return `${score}% match`;
  return `${score}% match · ${conf}% of factors assessed`;
}

/** Points a factor earned out of its weight ("27 of 30"), or null when it was not scored. */
export function factorPoints(f) {
  if (!f || f.score === null || f.score === undefined || f.weight === null || f.weight === undefined) return null;
  return `${Math.round(f.score * f.weight)} of ${f.weight}`;
}

/** Missing inputs split by who can supply them: the student's profile or the course catalogue. */
export function missingBySource(list) {
  const out = { profile: [], catalogue: [] };
  for (const m of list || []) if (out[m.source] && !out[m.source].includes(m.item)) out[m.source].push(m.item);
  return out;
}

/** One line on how current the stored recommendations are. */
export function freshnessText(freshness, run) {
  if (!run || freshness?.state === "never") return "No recommendations have been generated yet.";
  const when = run.generated_at ? `Generated ${formatDateTime(run.generated_at)}` : "Generated";
  const by = run.generated_by_name ? ` by ${run.generated_by_name}` : "";
  if (freshness?.state === "stale") return `${when}${by}. ${(freshness.reasons || []).join(" ")} Refresh to update them.`;
  return `${when}${by}. Up to date with the profile and the catalogue.`;
}

/** Link that opens the "New application" drawer with this recommendation's course and suggested intake. */
export function planLink(rec, studentId) {
  const q = new URLSearchParams({ new: "1", university_id: rec.university_id, course_id: rec.course_id });
  if (rec.intake_id) q.set("intake_id", rec.intake_id);
  if (studentId) q.set("student_id", studentId);
  return `/applications/?${q}`;
}
