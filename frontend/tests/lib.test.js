/* Unit tests for the frontend's plain helpers: `npm test` (Node's built-in runner, no extra dependencies). */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ApiError, NETWORK_MESSAGE, errorEntries, fieldLabel, friendlyMessage } from "../src/lib/api.js";
import { formatDate, formatDateTime, parseDate, plural, ymd } from "../src/lib/format.js";
import { appStatusLabel, countdownText, docStatusLabel, rankingText, uploadMessage } from "../src/lib/labels.js";
import { studentNextStep } from "../src/lib/nextStep.js";
import { passwordProblem, validateChange } from "../src/lib/passwords.js";
import { readQuery, writeQuery } from "../src/lib/useQueryState.js";
import { singleFlight } from "../src/lib/useSubmit.js";

const ZONES = ["UTC", "Asia/Kolkata", "America/Los_Angeles", "Pacific/Auckland"];
function inZone(tz, fn) {
  const before = process.env.TZ;
  process.env.TZ = tz;
  try { return fn(); } finally { if (before === undefined) delete process.env.TZ; else process.env.TZ = before; }
}

describe("dates", () => {
  it("shows a date-only value as the same calendar date in every time zone", () => {
    for (const tz of ZONES) {
      inZone(tz, () => {
        assert.equal(formatDate("2027-01-15"), "15 Jan 2027", tz);
        assert.equal(formatDate("2026-12-31"), "31 Dec 2026", tz); // year boundary
        assert.equal(formatDate("2027-03-01"), "1 Mar 2027", tz); // month boundary
        assert.equal(formatDate("2028-02-29"), "29 Feb 2028", tz); // leap day
        assert.equal(ymd(parseDate("2027-01-01")), "2027-01-01", tz);
      });
    }
  });

  it("still converts real timestamps to local time", () => {
    // 23:30 UTC on 31 Dec is already 1 Jan in India and still 31 Dec in Los Angeles.
    assert.equal(inZone("UTC", () => formatDate("2026-12-31T23:30:00Z")), "31 Dec 2026");
    assert.equal(inZone("Asia/Kolkata", () => formatDate("2026-12-31T23:30:00Z")), "1 Jan 2027");
    assert.equal(inZone("America/Los_Angeles", () => formatDate("2026-12-31T23:30:00Z")), "31 Dec 2026");
    assert.match(inZone("Asia/Kolkata", () => formatDateTime("2026-12-31T23:30:00Z")), /05:00/);
  });

  it("handles empty and invalid values", () => {
    assert.equal(formatDate(""), "—");
    assert.equal(formatDate(null), "—");
    assert.equal(formatDate("not a date"), "not a date");
    assert.equal(parseDate("2027-13-45") instanceof Date || parseDate("2027-13-45") === null, true);
  });
});

describe("plurals and countdowns", () => {
  it("pluralises naturally", () => {
    assert.equal(plural(0, "student"), "0 students");
    assert.equal(plural(1, "student"), "1 student");
    assert.equal(plural(2, "university"), "2 universities");
    assert.equal(plural(1, "entry", "entries"), "1 entry");
    assert.equal(plural(3, "entry", "entries"), "3 entries");
  });

  it("never says '1 days' and words due-today and overdue correctly", () => {
    const t = (days_left, state = "open", long = false) => countdownText({ days_left, state }, { long });
    assert.equal(t(1), "Due tomorrow");
    assert.equal(t(1, "open", true), "Due tomorrow.");
    assert.equal(t(2, "open", true), "Due in 2 days.");
    assert.equal(t(30), "30 days left");
    assert.equal(t(0, "due_soon"), "Due today");
    assert.equal(t(-1, "overdue"), "1 day overdue");
    assert.equal(t(-1, "overdue", true), "The deadline passed 1 day ago.");
    assert.equal(t(-5, "overdue"), "5 days overdue");
    assert.equal(t(-3, "submitted"), "Submitted"); // no negative countdown once submitted
    assert.equal(t(10, "closed", true), "This application is closed.");
    for (const n of [-10, -1, 0, 1, 2, 15]) assert.doesNotMatch(t(n), /\b1 days\b|-\d/);
  });
});

describe("labels", () => {
  it("keeps application and document review statuses apart", () => {
    assert.equal(appStatusLabel("Under Review"), "University reviewing");
    assert.equal(docStatusLabel("Under Review"), "Being checked");
    assert.notEqual(appStatusLabel("Under Review"), docStatusLabel("Under Review"));
    assert.equal(appStatusLabel("Planned"), "Planned");
  });

  it("shows a missing ranking without a malformed '#—'", () => {
    assert.equal(rankingText(12), "World ranking 12");
    assert.equal(rankingText(null), "Ranking not available");
    assert.equal(rankingText(undefined), "Ranking not available");
    assert.doesNotMatch(rankingText(null), /#|—/);
  });

  it("words the upload message for whoever uploaded", () => {
    const doc = { document_type: "Passport", student_name: "Asha Nair" };
    const student = uploadMessage(doc, { status: "Uploaded" }, { role: "student" });
    const staff = uploadMessage(doc, { status: "Uploaded" }, { role: "counsellor" });
    assert.doesNotMatch(staff, /your counsellor/i);
    assert.match(staff, /Asha Nair/);
    assert.match(student, /Passport uploaded/);
    assert.match(uploadMessage(doc, { status: "Verified" }, { role: "admin" }), /Verified/);
  });
});

describe("API error messages", () => {
  it("never shows raw field keys", () => {
    const msg = friendlyMessage(400, { email: ["Enter a valid email address."] });
    assert.equal(msg, "Email address: Enter a valid email address.");
    assert.doesNotMatch(friendlyMessage(400, { counsellor_id: ["Invalid."] }), /counsellor_id/);
    assert.equal(fieldLabel("personal.address.postal_code"), "Postal code");
    assert.equal(fieldLabel("some_new_field"), "Some new field");
  });

  it("summarises several field errors and keeps general ones", () => {
    const msg = friendlyMessage(400, { email: ["Bad."], password: ["Too short."] });
    assert.equal(msg, "Please correct these fields: Email address, Password.");
    assert.equal(friendlyMessage(400, { detail: ["Reassign this counsellor's 2 students before deleting the account."] }),
      "Reassign this counsellor's 2 students before deleting the account.");
    assert.deepEqual(errorEntries({ personal: { citizenship: ["Choose a country from the list."] } }), [["Citizenship", "Choose a country from the list."]]);
  });

  it("gives actionable messages per failure type, without server internals", () => {
    assert.equal(friendlyMessage(0, null), NETWORK_MESSAGE);
    assert.doesNotMatch(NETWORK_MESSAGE, /is it running|server/i);
    assert.equal(friendlyMessage(401, { detail: "Invalid email or password." }), "Invalid email or password.");
    assert.match(friendlyMessage(403, null), /permission/);
    assert.match(friendlyMessage(404, null), /could not find/);
    assert.match(friendlyMessage(409, null), /changed this record/);
    assert.match(friendlyMessage(500, { detail: "Traceback (most recent call last)" }), /Something went wrong on our side/);
    assert.equal(friendlyMessage(503, { detail: "The database is temporarily unavailable. Please try again shortly." }),
      "The database is temporarily unavailable. Please try again shortly.");
    const err = new ApiError(400, { email: ["Bad."] });
    assert.equal(err.hasFieldErrors, true);
    assert.equal(new ApiError(400, { detail: "x" }).hasFieldErrors, false);
  });
});

describe("double-submission guard", () => {
  it("runs one request for rapid repeated clicks", async () => {
    let calls = 0;
    const states = [];
    const run = singleFlight((b) => states.push(b));
    let release;
    const gate = new Promise((r) => { release = r; });
    const first = run(async () => { calls++; await gate; return "saved"; });
    const second = run(async () => { calls++; });
    const third = run(async () => { calls++; });
    release();
    assert.equal(await first, "saved");
    assert.equal(await second, undefined);
    assert.equal(await third, undefined);
    assert.equal(calls, 1);
    assert.deepEqual(states, [true, false]);
  });

  it("allows a retry after a failure", async () => {
    const run = singleFlight();
    await assert.rejects(run(async () => { throw new Error("network"); }));
    assert.equal(await run(async () => "retried"), "retried");
  });
});

describe("list state in the URL", () => {
  const SPEC = {
    q: { default: "" },
    status: { default: "", allowed: ["", "Planned", "Submitted"] },
    open: { default: false, type: "bool" },
    page: { default: 1, type: "page" },
  };

  it("reads valid values and falls back to defaults for invalid ones", () => {
    assert.deepEqual(readQuery(SPEC, "?q=robotics&status=Planned&open=1&page=3"), { q: "robotics", status: "Planned", open: true, page: 3 });
    assert.deepEqual(readQuery(SPEC, "?status=DROP&page=-4&open=maybe"), { q: "", status: "", open: false, page: 1 });
    assert.equal(readQuery(SPEC, "?page=2.5").page, 1);
  });

  it("writes only non-default values and keeps unrelated parameters", () => {
    assert.equal(writeQuery(SPEC, { q: "", status: "", open: false, page: 1 }, ""), "");
    assert.equal(writeQuery(SPEC, { q: "data", status: "Submitted", open: true, page: 2 }, "?student_id=s1"),
      "?student_id=s1&q=data&status=Submitted&open=1&page=2");
    const round = writeQuery(SPEC, { q: "a b", status: "Planned", open: true, page: 4 }, "");
    assert.deepEqual(readQuery(SPEC, round), { q: "a b", status: "Planned", open: true, page: 4 });
  });
});

describe("passwords", () => {
  it("matches the API's strength rules", () => {
    assert.match(passwordProblem(""), /Enter/);
    assert.match(passwordProblem("abc12"), /8 characters/);
    assert.match(passwordProblem("onlyletters"), /letters and numbers/);
    assert.match(passwordProblem("12345678"), /letters and numbers/);
    assert.equal(passwordProblem("Secret123"), "");
  });

  it("validates the change-password form", () => {
    assert.deepEqual(validateChange({ current: "Secret123", next: "NewSecret456", confirm: "NewSecret456" }), {});
    assert.ok(validateChange({ current: "", next: "NewSecret456", confirm: "NewSecret456" }).current_password);
    assert.ok(validateChange({ current: "Secret123", next: "NewSecret456", confirm: "Other456" }).confirm);
    assert.ok(validateChange({ current: "Secret123", next: "Secret123", confirm: "Secret123" }).new_password);
  });
});

describe("student dashboard next step", () => {
  const base = { profile_completion: { overall: 100 }, documents: { needs_attention: 0 }, applications: { total: 2, open: 2, overdue: 0, due_soon: 0 } };
  const step = (patch) => studentNextStep({ ...base, ...patch });

  it("follows the documented priority order", () => {
    assert.equal(step({ applications: { ...base.applications, overdue: 1 }, documents: { needs_attention: 3 } }).to, "/applications/?sort=deadline&open=1");
    assert.equal(step({ documents: { needs_attention: 3 }, profile_completion: { overall: 40 } }).to, "/documents/");
    assert.equal(step({ profile_completion: { overall: 40 } }).title, "Finish your profile — 40% done");
    assert.equal(step({ applications: { total: 0, open: 0 } }).to, "/universities/");
    assert.equal(step({ applications: { total: 1, open: 1, due_soon: 1 } }).title, "1 deadline in the next 14 days");
    assert.equal(step({}).title, "2 applications in progress");
    assert.equal(step({ applications: { total: 2, open: 0 } }).title, "You are all caught up");
  });

  it("uses natural singular and plural wording", () => {
    assert.equal(step({ documents: { needs_attention: 1 } }).title, "Upload 1 document");
    assert.equal(step({ applications: { ...base.applications, overdue: 1 } }).title, "1 application is past the deadline");
    assert.equal(step({ applications: { ...base.applications, overdue: 2 } }).title, "2 applications are past the deadline");
  });
});
