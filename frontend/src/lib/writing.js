/* SOP & LOR wording and arithmetic. Plain functions (no JSX), unit tested with `node --test`. */

/** Words as the backend counts them (runs of non-space characters). */
export const wordCount = (text) => ((text || "").match(/\S+/g) || []).length;

/** `[ADD: …]` gaps the assistant left for facts it did not have. */
export const placeholderCount = (text) => ((text || "").match(/\[ADD:[^\]]*\]/g) || []).length;

/** Progress against a word limit: `state` is short | ok | near | over, with a sentence to show. */
export function limitState(count, limit) {
  if (!limit) return { pct: 0, state: "ok", text: `${count} words` };
  const pct = Math.round((count / limit) * 100);
  if (count > limit) return { pct: 100, state: "over", text: `${count} / ${limit} words — ${count - limit} over the limit` };
  if (pct >= 90) return { pct, state: "near", text: `${count} / ${limit} words — close to the limit` };
  if (count && pct < 60) return { pct, state: "short", text: `${count} / ${limit} words — room for more detail` };
  return { pct, state: "ok", text: `${count} / ${limit} words` };
}

export const WORD_LIMITS = [500, 800, 1000, 1500];

/** One-click improvements offered beside the editor (the counsellor can also type their own). */
export const REVISE_PRESETS = [
  "Make it more concise",
  "Strengthen the opening paragraph",
  "Make the career goals more specific",
  "Improve flow between paragraphs",
  "Use a more formal tone",
  "Fix grammar and spelling only",
];

const STATUS_TEXT = {
  Draft: ["Draft", "badge", "Only you can see this draft."],
  Shared: ["Waiting for student approval", "badge badge-info", "The student can read this draft, comment, and approve it or ask for changes."],
  Final: ["Approved & final", "badge badge-ok", "Approved by the student. Ready to upload as their SOP."],
};
export const statementStatus = (s) => {
  const [label, className, help] = STATUS_TEXT[s] || [s || "—", "badge", ""];
  return { label, className, help };
};

const KIND = { sop: "Statement of purpose", lor_brief: "Referee brief", lor_draft: "Starting draft for referee" };
export const kindLabel = (k) => KIND[k] || "Document";

const STAGE = {
  Planned: ["Not asked yet", "badge", "Ask the referee, then mark them as requested."],
  Requested: ["Waiting for letter", "badge badge-warn", "When the letter arrives, upload it under Documents."],
  Received: ["Letter received", "badge badge-info", "Check the letter and verify it under Documents."],
  Verified: ["Letter verified", "badge badge-ok", "Done. This letter can be submitted."],
  Cancelled: ["Cancelled", "badge badge-err", "This referee is no longer writing a letter."],
};
export const refereeStage = (s) => {
  const [label, className, next] = STAGE[s] || [s || "—", "badge", ""];
  return { label, className, next };
};

/** Where an SOP is in the guided flow: 1 interview, 2 draft, 3 review and share, 4 done. */
export function sopStep(statement, questions = []) {
  if (!statement) return 1;
  if (statement.status === "Final") return 4;
  if (statement.status === "Shared") return 3;
  const answers = statement.answers || {};
  const required = questions.filter((q) => q.required);
  if (!wordCount(statement.content) && required.some((q) => !(answers[q.key] || "").trim())) return 1;
  return wordCount(statement.content) ? 3 : 2;
}

export const answeredCount = (questions, answers) => questions.filter((q) => ((answers || {})[q.key] || "").trim()).length;

/** Why the AI buttons are off, worded for the counsellor, or "" when they can be used. */
export function aiBlockReason({ consent, aiAvailable, canEdit }) {
  if (!canEdit) return "Only the student's counsellor can use the writing assistant.";
  if (!aiAvailable) return "AI drafting is not set up on this server yet. You can still write by hand.";
  if (!consent?.granted) return "The student has not agreed to AI-assisted writing yet. Ask them, or write by hand.";
  return "";
}

/** A safe file name for a downloaded draft: "SOP - Data Science at TU Munich.txt". */
export function draftFilename(title) {
  const base = (title || "draft").replace(/[\\/:*?"<>|]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 80) || "draft";
  return `${base}.txt`;
}

const SOURCE = { ai_draft: "AI draft", ai_revise: "AI edit", manual: "Edited by hand", restore: "Restored" };
export const versionSource = (s) => SOURCE[s] || "Edit";
