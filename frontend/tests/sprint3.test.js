/* Unit tests for the Sprint 3 helpers: recommendations and notifications wording (`npm test`). */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { badgeCount, categoryLabel, safeLink, timeAgo } from "../src/lib/notifications.js";
import { eligibilityInfo, factorPoints, factorStatus, freshnessText, missingBySource, planLink, scoreText } from "../src/lib/recommendations.js";

describe("recommendations", () => {
  it("says how much of the weighting a score rests on", () => {
    assert.equal(scoreText({ match_score: 86, confidence: 100 }), "86% match");
    assert.equal(scoreText({ match_score: 86, confidence: 90 }), "86% match · 90% of factors assessed");
    assert.equal(scoreText({ match_score: 70 }), "70% match"); // seed v1: no confidence
    assert.equal(scoreText(null), "0% match");
  });

  it("labels eligibility, including the earlier engine version", () => {
    assert.equal(eligibilityInfo("eligible").tone, "ok");
    assert.equal(eligibilityInfo("ineligible").label, "Not eligible");
    assert.equal(eligibilityInfo("insufficient_data").label, "Eligibility to confirm");
    assert.equal(eligibilityInfo(null).label, "Not assessed");
    assert.equal(factorStatus("weird").label, "Not assessed");
  });

  it("shows factor points only when a factor was scored", () => {
    assert.equal(factorPoints({ score: 0.5, weight: 20 }), "10 of 20");
    assert.equal(factorPoints({ score: 0, weight: 30 }), "0 of 30");
    assert.equal(factorPoints({ score: null, weight: 10 }), null);
    assert.equal(factorPoints({ score: 1, weight: null }), null); // v1 rows have no weights
  });

  it("groups missing data by who can supply it, without duplicates", () => {
    const m = missingBySource([{ source: "profile", item: "Budget" }, { source: "catalogue", item: "Tuition" },
      { source: "profile", item: "Budget" }, { source: "elsewhere", item: "x" }]);
    assert.deepEqual(m, { profile: ["Budget"], catalogue: ["Tuition"] });
    assert.deepEqual(missingBySource(undefined), { profile: [], catalogue: [] });
  });

  it("explains freshness", () => {
    assert.match(freshnessText({ state: "never" }, null), /No recommendations/);
    assert.match(freshnessText({ state: "stale", reasons: ["The profile changed."] }, { generated_at: "2026-10-16T09:00:00Z" }), /The profile changed\. Refresh/);
    assert.match(freshnessText({ state: "current" }, { generated_at: "2026-10-16T09:00:00Z", generated_by_name: "Mei Lin Tan" }), /by Mei Lin Tan\. Up to date/);
  });

  it("builds the plan-application link with the suggested intake", () => {
    const rec = { university_id: "university_042", course_id: "course_0536", intake_id: "intake_fall_2027" };
    assert.equal(planLink(rec), "/applications/?new=1&university_id=university_042&course_id=course_0536&intake_id=intake_fall_2027");
    assert.match(planLink({ ...rec, intake_id: null }, "student_1"), /course_0536&student_id=student_1$/);
  });
});

describe("notifications", () => {
  it("words relative times", () => {
    const now = Date.parse("2026-10-16T12:00:00Z");
    assert.equal(timeAgo("2026-10-16T11:59:40Z", now), "just now");
    assert.equal(timeAgo("2026-10-16T11:55:00Z", now), "5 min ago");
    assert.equal(timeAgo("2026-10-16T09:00:00Z", now), "3 h ago");
    assert.equal(timeAgo("2026-10-15T09:00:00Z", now), "yesterday");
    assert.equal(timeAgo("2026-10-12T09:00:00Z", now), "4 days ago");
    assert.match(timeAgo("2026-09-01T09:00:00Z", now), /Sept? 2026/);
    assert.equal(timeAgo("2026-10-16T13:00:00Z", now), "just now"); // clock skew never shows "in the future"
    assert.equal(timeAgo("", now), "");
  });

  it("caps the badge and labels categories", () => {
    assert.equal(badgeCount(0), "");
    assert.equal(badgeCount(7), "7");
    assert.equal(badgeCount(120), "99+");
    assert.equal(categoryLabel("missing_document"), "Documents");
    assert.equal(categoryLabel("unknown"), "Notice");
  });

  it("only follows same-site links", () => {
    assert.equal(safeLink("/applications/application_1/"), "/applications/application_1/");
    assert.equal(safeLink("/counselling/?tab=follow-ups"), "/counselling/?tab=follow-ups");
    assert.equal(safeLink("//evil.example/x"), null);
    assert.equal(safeLink("https://evil.example/"), null);
    assert.equal(safeLink("javascript:alert(1)"), null);
    assert.equal(safeLink(null), null);
  });
});
