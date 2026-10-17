/* Rule-based university/course recommendations (SRS 4.8): results, matching factors and reasons; staff review them. */
import { useState } from "react";
import { Link } from "react-router-dom";
import AppShell from "../components/Shell";
import Combobox from "../components/Combobox";
import Drawer from "../components/Drawer";
import StudentPicker from "../components/StudentPicker";
import { useAuth } from "../components/auth";
import { useToast } from "../components/Toast";
import { ErrorAlert, Field, Loading, Pager, recordError } from "../components/ui";
import { api } from "../lib/api";
import { formatDate, plural } from "../lib/format";
import { saveErrorMessage, useForm } from "../lib/form";
import { rankingText } from "../lib/labels";
import { eligibilityInfo, factorPoints, factorStatus, freshnessText, missingBySource, planLink, scoreText } from "../lib/recommendations";
import { useLoad } from "../lib/useLoad";
import { useQueryState } from "../lib/useQueryState";
import { useSubmit } from "../lib/useSubmit";
import { ID_PATTERN } from "./Applications";

const STATUSES = ["Suggested", "Accepted", "Rejected"];
const TIERS = ["Reach", "Target", "Safe"];
const LIST_STATE = {
  student_id: { default: "", pattern: ID_PATTERN },
  status: { default: "", allowed: ["", ...STATUSES] },
  page: { default: 1, type: "page" },
};
const STATUS_CLASS = { Suggested: "badge badge-info", Accepted: "badge badge-ok", Rejected: "badge" };
const CHECK_LABELS = { level: "Degree level", grades: "Entry grade", english: "English requirement", intake: "Open intake" };
const CHECK_STATUS = { pass: ["Met", "badge badge-ok"], fail: ["Not met", "badge badge-err"], unknown: ["Not recorded", "badge"] };

function Explanation({ rec, isStudent }) {
  const missing = missingBySource(rec.missing_data);
  const checks = Object.entries(rec.checks || {});
  return (
    <details className="rec-why">
      <summary>Why this course? Matching factors and entry rules</summary>
      <table className="factor-table">
        <caption className="sr-only">Matching factors for {rec.snapshot?.course_title}</caption>
        <thead><tr><th scope="col">Factor</th><th scope="col">Result</th><th scope="col">Points</th><th scope="col">Detail</th></tr></thead>
        <tbody>
          {rec.factors.map((f) => {
            const s = factorStatus(f.status);
            return (
              <tr key={f.key}>
                <th scope="row">{f.label}</th>
                <td><span className={`badge${s.tone ? ` badge-${s.tone}` : ""}`}><span aria-hidden="true">{s.icon} </span>{s.label}</span></td>
                <td className="num">{factorPoints(f) ?? "—"}</td>
                <td className="small">{f.detail || "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {checks.length > 0 && (
        <>
          <h4>Entry rules</h4>
          <ul className="list-plain">
            {checks.map(([k, c]) => {
              const [label, cls] = CHECK_STATUS[c.status] || CHECK_STATUS.unknown;
              return <li key={k}><span><b>{CHECK_LABELS[k] || k}</b><span className="small muted" style={{ display: "block" }}>{c.detail}</span></span><span className={cls}>{label}</span></li>;
            })}
          </ul>
        </>
      )}
      {rec.reasons?.length > 0 && <><h4>Reasons</h4><ul className="reason-list">{rec.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul></>}
      {(missing.profile.length > 0 || missing.catalogue.length > 0) && (
        <div className="alert alert-info" style={{ marginTop: ".8rem" }}>
          {missing.profile.length > 0 && <p style={{ margin: 0 }}>Adding {missing.profile.join(", ").toLowerCase()} to {isStudent ? <Link to="/profile/">your profile</Link> : "the profile"} would make this assessment more complete.</p>}
          {missing.catalogue.length > 0 && <p style={{ margin: missing.profile.length ? ".4rem 0 0" : 0 }}>Not recorded in the catalogue for this course: {missing.catalogue.join(", ").toLowerCase()}.</p>}
        </div>
      )}
    </details>
  );
}

function RecCard({ rec, staff, studentId, onReview }) {
  const snap = rec.snapshot || {};
  const elig = eligibilityInfo(rec.eligibility);
  return (
    <article className="card rec-card" aria-labelledby={`rec-${rec.id}`}>
      <div className="rec-head">
        <div style={{ minWidth: 0 }}>
          <h3 id={`rec-${rec.id}`}>{snap.course_title || "Course"}</h3>
          <p className="muted small" style={{ margin: 0 }}>{snap.university_name} · {snap.country} · {rankingText(snap.world_rank)}{snap.cluster ? ` · ${snap.cluster}` : ""}</p>
        </div>
        <div className="rec-score" aria-label={scoreText(rec)}>
          <span className="value">{rec.match_score ?? 0}<small>%</small></span>
          <span className="small muted">{rec.confidence !== null && rec.confidence !== undefined && rec.confidence < 100 ? `${rec.confidence}% assessed` : "match"}</span>
        </div>
      </div>
      <div className="meta rec-badges">
        <span className={STATUS_CLASS[rec.status] || "badge"}>{rec.status}</span>
        <span className={`badge${elig.tone ? ` badge-${elig.tone}` : ""}`} title={elig.text}>{elig.label}</span>
        {rec.tier && <span className="badge">{rec.tier}</span>}
        {rec.origin === "counsellor" && <span className="badge badge-brand">Added by {rec.created_by_name || "counsellor"}</span>}
        {rec.in_latest_run === false && rec.origin !== "counsellor" && <span className="badge">Not in the latest results</span>}
      </div>
      {snap.intake_name && <p className="small" style={{ margin: ".6rem 0 0" }}>Suggested intake: <b>{snap.intake_name}</b>{snap.intake_deadline ? ` · apply by ${formatDate(snap.intake_deadline)}` : ""}</p>}
      {rec.eligibility === "ineligible" && <div className="alert alert-error" style={{ margin: ".7rem 0 0" }}>{elig.text}</div>}
      {rec.remarks && <p className="small rec-remarks"><b>Counsellor note:</b> {rec.remarks}</p>}
      <Explanation rec={rec} isStudent={!staff} />
      <div className="toolbar rec-actions">
        {rec.status !== "Rejected" && rec.eligibility !== "ineligible" && (
          <Link className="btn btn-outline btn-sm" to={planLink(rec, staff ? studentId : "")}>Plan application</Link>
        )}
        {staff && <button type="button" className="btn btn-outline btn-sm" onClick={() => onReview(rec)}>Review</button>}
      </div>
    </article>
  );
}

function ReviewDrawer({ rec, onClose, onSaved }) {
  const toast = useToast();
  const form = useForm({ status: rec.status, tier: rec.tier || "", remarks: rec.remarks || "" });
  const { bind, errors } = form;
  const [busy, run] = useSubmit();
  const save = () => run(async () => {
    try {
      const updated = await api(`/recommendations/${encodeURIComponent(rec.id)}/`, { method: "PATCH", body: { ...form.values, rev: rec.rev } });
      toast("Recommendation updated");
      onSaved(updated);
    } catch (err) {
      if (err.status === 400) form.showErrors(err.data);
      toast(saveErrorMessage(err), "error");
    }
  });
  return (
    <Drawer title="Review recommendation" onClose={onClose} busy={busy} footer={<>
      <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
    </>}>
      <p className="muted">{rec.snapshot?.course_title} · {rec.snapshot?.university_name}</p>
      <form noValidate ref={form.ref} onSubmit={(e) => { e.preventDefault(); save(); }}>
        <Field label="Decision" error={errors.status} hint={rec.eligibility === "ineligible" ? "This course fails an entry rule, so it cannot be accepted." : undefined}>
          <select {...bind("status")}>{STATUSES.map((s) => <option key={s} disabled={s === "Accepted" && rec.eligibility === "ineligible"}>{s}</option>)}</select>
        </Field>
        <Field label="Tier" error={errors.tier} hint="Overrides the engine's estimate; kept when the recommendations are refreshed.">
          <select {...bind("tier")}><option value="">Engine estimate</option>{TIERS.map((t) => <option key={t}>{t}</option>)}</select>
        </Field>
        <Field label="Note for the student" error={errors.remarks}><textarea maxLength={500} {...bind("remarks")} /></Field>
      </form>
    </Drawer>
  );
}

function AddDrawer({ studentId, onClose, onSaved }) {
  const toast = useToast();
  const [course, setCourse] = useState(null);
  const [remarks, setRemarks] = useState("");
  const [error, setError] = useState("");
  const [busy, run] = useSubmit();

  async function loadOptions(q, signal) {
    const data = await api("/universities/courses/", { query: { q, page_size: 20 }, signal });
    return {
      options: data.results.map((c) => ({ value: c.id, label: c.title || c.canonical_name, hint: `${c.university.name} · ${c.university.country}` })),
      note: data.count > 20 ? `Showing 20 of ${data.count} courses. Type more to narrow the list.` : "",
    };
  }

  const save = () => run(async () => {
    if (!course) { setError("Choose a course."); return; }
    try {
      await api("/recommendations/", { method: "POST", body: { student_id: studentId, course_id: course.value, remarks } });
      toast("Course added to the recommendations");
      onSaved();
    } catch (err) {
      setError(err.data?.course_id?.join(" ") || "");
      toast(saveErrorMessage(err), "error");
    }
  });

  return (
    <Drawer title="Recommend a course" onClose={onClose} busy={busy} footer={<>
      <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Adding…" : "Add recommendation"}</button>
    </>}>
      <p className="muted small">The course is scored with the same rules as the engine's suggestions. A course that fails a recorded entry rule cannot be added.</p>
      <Field label="Course" error={error}>
        <Combobox ariaLabel="Course" placeholder="Search courses or subjects…" value={course} loadOptions={loadOptions}
          emptyText="No courses match." onChange={(opt) => { setCourse(opt); setError(""); }} />
      </Field>
      <Field label="Note for the student (optional)"><textarea maxLength={500} value={remarks} onChange={(e) => setRemarks(e.target.value)} /></Field>
    </Drawer>
  );
}

export default function Recommendations() {
  const { user } = useAuth();
  const toast = useToast();
  const staff = user.role !== "student";
  const [state, update] = useQueryState(LIST_STATE);
  const studentId = staff ? state.student_id : "";
  const { status, page } = state;
  const [reviewing, setReviewing] = useState(null);
  const [adding, setAdding] = useState(false);
  const [busy, run] = useSubmit();
  const ready = !staff || !!studentId;

  const { data, error, loading, reload, setData } = useLoad(
    () => (ready ? api("/recommendations/", { query: { student_id: studentId, status, page, page_size: 10 } }) : Promise.resolve(null)),
    [ready, studentId, status, page]);

  const generate = () => run(async () => {
    try {
      await api("/recommendations/generate/", { method: "POST", body: staff ? { student_id: studentId } : {} });
      toast("Recommendations updated");
      if (page !== 1) update({ page: 1 }); else reload();
    } catch (err) { toast(err.message, "error"); }
  });

  const run_ = data?.run;
  const fresh = data?.freshness;
  const stats = run_?.stats || {};
  const excluded = stats.ineligible || 0;

  return (
    <AppShell title="Recommendations" crumb="Recommendations">
      <div className="page-head">
        <div>
          <h1>{staff ? "Recommendations" : "Recommended for you"}</h1>
          <p className="muted">Courses matched to {staff ? "the student's" : "your"} target countries, course areas, grades, preferred intake and budget, with the reasons for each match. Courses that fail a recorded entry rule are never recommended.</p>
        </div>
        <div className="toolbar">
          {staff && <div className="toolbar-picker"><StudentPicker value={studentId} onChange={(id) => update({ student_id: id, page: 1, status: "" })} ariaLabel="Student" /></div>}
          {ready && data && <button type="button" className="btn btn-primary" onClick={generate} disabled={busy}>
            {busy ? "Working…" : fresh?.state === "never" ? "Generate recommendations" : "Refresh"}</button>}
          {staff && ready && data && <button type="button" className="btn btn-outline" onClick={() => setAdding(true)}>Add a course</button>}
        </div>
      </div>

      {!ready ? <div className="card"><p className="empty">Choose a student to see and review their recommendations.</p></div>
        : error ? <ErrorAlert error={error} onRetry={reload}>{recordError(error, "student") || "Could not load the recommendations."}</ErrorAlert>
        : !data ? <Loading text="Loading recommendations…" />
        : (
          <>
            {run_?.status === "insufficient_profile" ? (
              <div className="alert alert-warn">{run_.message} {staff
                ? <Link to={`/students/${encodeURIComponent(studentId)}/`}>Open the profile →</Link>
                : <Link to="/profile/">Complete your preferences →</Link>}</div>
            ) : (
              <div className={`alert ${fresh?.state === "stale" ? "alert-warn" : "alert-info"} alert-row`} role="status">
                <span>{freshnessText(fresh, run_)}{run_ && stats.evaluated !== undefined && <> Evaluated {plural(stats.evaluated, "course")}{excluded ? `; ${excluded} excluded by entry rules` : ""}.</>}</span>
              </div>
            )}
            <div className="card-head">
              <div className="toolbar">
                <select aria-label="Status" value={status} onChange={(e) => update({ status: e.target.value, page: 1 })}>
                  <option value="">All statuses</option>{STATUSES.map((s) => <option key={s}>{s}</option>)}
                </select>
              </div>
              <span className="small muted" aria-live="polite">{loading ? "" : plural(data.count, "recommendation")}</span>
            </div>
            <div aria-busy={loading || undefined}>
              {!data.results.length ? (
                <div className="card"><p className="empty">{status ? "No recommendations with this status." : fresh?.state === "never"
                  ? `No recommendations yet. Choose "Generate recommendations" to match ${staff ? "the student's" : "your"} profile against the catalogue.`
                  : run_?.message || "No course matches the profile well enough yet. Broaden the target countries or course areas."}</p></div>
              ) : data.results.map((r) => <RecCard key={r.id} rec={r} staff={staff} studentId={studentId} onReview={setReviewing} />)}
              <Pager data={data} noun="recommendation" onPage={(p) => { update({ page: p }); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
            </div>
          </>
        )}
      {reviewing && <ReviewDrawer rec={reviewing} onClose={() => setReviewing(null)}
        onSaved={(u) => { setReviewing(null); setData((d) => ({ ...d, results: d.results.map((x) => (x.id === u.id ? u : x)) })); }} />}
      {adding && <AddDrawer studentId={studentId} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); reload(); }} />}
    </AppShell>
  );
}
