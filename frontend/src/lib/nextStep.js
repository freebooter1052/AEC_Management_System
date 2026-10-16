import { plural } from "./format.js";

/**
 * The one thing a student should do next, from their real dashboard data. Checked in this order, so the most
 * urgent wins: overdue applications, documents to upload, an unfinished profile, no applications yet,
 * deadlines in the next 14 days, applications in progress, and finally nothing outstanding.
 */
export function studentNextStep(d) {
  const apps = d.applications || {};
  const docs = d.documents || {};
  const pct = d.profile_completion?.overall ?? 0;
  if (apps.overdue > 0) {
    return { title: `${plural(apps.overdue, "application")} ${apps.overdue === 1 ? "is" : "are"} past the deadline`,
      text: "Check with your counsellor whether the university still accepts it, or withdraw it.", action: "Review applications", to: "/applications/?sort=deadline&open=1" };
  }
  if (docs.needs_attention > 0) {
    return { title: `Upload ${plural(docs.needs_attention, "document")}`,
      text: "Documents that are required, rejected or expired need a new upload before your applications can be submitted.", action: "Upload documents", to: "/documents/" };
  }
  if (pct < 100) {
    return { title: `Finish your profile — ${pct}% done`,
      text: "Your counsellor uses your academic record and preferences to plan applications with you.", action: "Complete your profile", to: "/profile/" };
  }
  if (!apps.total) {
    return { title: "Shortlist universities",
      text: "Your profile is complete. Search the catalogue and plan your first application.", action: "Search universities", to: "/universities/" };
  }
  if (apps.due_soon > 0) {
    return { title: `${plural(apps.due_soon, "deadline")} in the next 14 days`,
      text: "Make sure every document is uploaded and verified in time.", action: "View deadlines", to: "/applications/?sort=deadline&open=1" };
  }
  if (apps.open > 0) {
    return { title: `${plural(apps.open, "application")} in progress`,
      text: "Your counsellor moves each application through its stages. Follow its status here.", action: "Track applications", to: "/applications/?open=1" };
  }
  return { title: "You are all caught up", text: "Nothing needs your attention right now. Your sessions and follow-ups are under Counselling.",
    action: "View counselling", to: "/counselling/" };
}
