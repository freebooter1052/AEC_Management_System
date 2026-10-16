/* Document upload & status (SRS 4.6): a student's checklist; for staff, a review queue and per-student view. */
import { useEffect, useState } from "react";
import AppShell from "../components/Shell";
import Drawer from "../components/Drawer";
import { DocRow, isStaff as staffRole, useDocActions } from "../components/Documents";
import StudentPicker from "../components/StudentPicker";
import { useAuth } from "../components/auth";
import { useToast } from "../components/Toast";
import { ErrorAlert, Field, Kpi, Pager, docStatusLabel, recordError } from "../components/ui";
import { api } from "../lib/api";
import { plural } from "../lib/format";
import { saveErrorMessage, useForm } from "../lib/form";
import { useLoad } from "../lib/useLoad";
import { useQueryState } from "../lib/useQueryState";
import { useSubmit } from "../lib/useSubmit";
import { ID_PATTERN } from "./Applications";

const TYPES = ["Transcript", "Degree Certificate", "Passport", "SOP", "LOR", "Resume/CV", "Test Score", "Other"];
const DOC_STATUSES = ["Required", "Uploaded", "Under Review", "Verified", "Rejected", "Expired"];
const AWAITING = "Uploaded,Under Review";
const WAITING_ON_STUDENT = "Required,Rejected,Expired";
const LIST_STATE = {
  student_id: { default: "", pattern: ID_PATTERN },
  status: { default: AWAITING, allowed: [AWAITING, WAITING_ON_STUDENT, "all", ...DOC_STATUSES] },
  page: { default: 1, type: "page" },
};

function AddDrawer({ studentId, staff, onClose, onDone }) {
  const toast = useToast();
  const [apps, setApps] = useState([]);
  const form = useForm({ document_type: TYPES[0], title: "", application_id: "" });
  const { bind, errors } = form;
  const [busy, run] = useSubmit();

  useEffect(() => {
    api("/applications/", { query: { student_id: studentId, page_size: 100, open: "true" } }).then((d) => setApps(d.results), (err) => toast(err.message, "error"));
  }, [studentId, toast]);

  const save = () => run(async () => {
    const body = { ...form.values };
    if (staff) body.student_id = studentId;
    try {
      await api("/documents/", { method: "POST", body });
      toast("Document added to the checklist");
      onDone();
    } catch (err) {
      if (err.status === 400) form.showErrors(err.data);
      toast(saveErrorMessage(err), "error");
    }
  });

  return (
    <Drawer title="Add a document" onClose={onClose} busy={busy} footer={<>
      <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Adding…" : "Add"}</button>
    </>}>
      <form noValidate ref={form.ref} onSubmit={(e) => { e.preventDefault(); save(); }}>
        <Field label="Document type" error={errors.document_type}><select {...bind("document_type")}>{TYPES.map((t) => <option key={t}>{t}</option>)}</select></Field>
        <Field label="Label (optional)" error={errors.title}><input maxLength={120} placeholder="e.g. LOR — Prof. Rao" {...bind("title")} /></Field>
        <Field label="For" error={errors.application_id}>
          <select {...bind("application_id")}>
            <option value="">General (all applications)</option>
            {apps.map((a) => <option key={a.id} value={a.id}>{a.snapshot.course_title} — {a.snapshot.university_name}</option>)}
          </select>
        </Field>
      </form>
    </Drawer>
  );
}

/** Student-centred view: general documents first, then one group per application. */
function Grouped({ docs, user, actions }) {
  const groups = new Map([["", []]]);
  docs.forEach((d) => {
    const key = d.application_label || "";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(d);
  });
  return [...groups].filter(([, list]) => list.length).map(([key, list]) => (
    <section className="doc-group" key={key || "general"}>
      <h3>{key || "General documents"}<span className="badge">{list.filter((d) => d.status === "Verified").length}/{list.length} verified</span></h3>
      {[...list].sort((a, b) => a.document_type.localeCompare(b.document_type)).map((d) => <DocRow key={d.id} d={d} user={user} actions={actions} />)}
    </section>
  ));
}

export default function Documents() {
  const { user } = useAuth();
  const toast = useToast();
  const staff = staffRole(user);
  const [state, update] = useQueryState(LIST_STATE);
  const studentId = staff ? state.student_id : user.profile_id || "";
  const { status, page } = state;
  const [adding, setAdding] = useState(false);
  const [checklistBusy, runChecklist] = useSubmit();
  const queue = staff && !studentId;

  const summary = useLoad(() => api("/documents/summary/", { query: { student_id: staff ? studentId : "" } }), [staff, studentId]);
  const list = useLoad(
    () => api("/documents/", { query: queue ? { status: status === "all" ? "" : status, page } : { student_id: studentId, page_size: 100 } }),
    [queue, status, page, studentId]);

  const refresh = () => { summary.reload(); list.reload(); };
  const { actions, drawers } = useDocActions(refresh);

  const makeChecklist = () => runChecklist(async () => {
    try {
      const res = await api("/documents/checklist/", { method: "POST", body: staff ? { student_id: studentId } : {} });
      toast(res.created ? `${plural(res.created, "document")} added to the checklist` : "The checklist already has every standard document", res.created ? "success" : "info");
      refresh();
    } catch (err) { toast(err.message, "error"); }
  });

  const s = summary.data;
  const data = list.data;
  const err = list.error;

  return (
    <AppShell title="Documents" crumb="Documents">
      <div className="page-head">
        <div>
          <h1>{staff ? "Document review" : "My documents"}</h1>
          <p className="muted">{staff
            ? "Verify what students upload. Pick a student to see and manage their full checklist."
            : "Upload each document on your checklist. Your counsellor verifies them before your applications are submitted."}</p>
        </div>
        <div className="toolbar">
          {(!staff || studentId) && <>
            <button type="button" className="btn btn-outline" onClick={makeChecklist} disabled={checklistBusy}>{checklistBusy ? "Adding…" : "Standard checklist"}</button>
            <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>Add document</button>
          </>}
        </div>
      </div>

      <div className="kpis">
        {s && (staff ? <>
          {/* In the queue each figure opens the matching filter; for one student the whole checklist is already shown. */}
          <Kpi label="Awaiting review" value={s.awaiting_review} to={queue && status !== AWAITING ? "/documents/" : undefined}>Uploaded or being checked</Kpi>
          <Kpi label="Waiting on students" value={s.needs_attention} to={queue && status !== WAITING_ON_STUDENT ? `/documents/?status=${encodeURIComponent(WAITING_ON_STUDENT)}` : undefined}>Required, rejected or expired</Kpi>
          <Kpi label="Verified" value={s.by_status.Verified || 0} to={queue && status !== "Verified" ? "/documents/?status=Verified" : undefined}>Ready for submission</Kpi>
          <Kpi label="Total" value={s.total} to={queue && status !== "all" ? "/documents/?status=all" : undefined}>{studentId ? "For this student" : "Across your students"}</Kpi>
        </> : <>
          <Kpi label="Needs your action" value={s.needs_attention}>Upload or replace</Kpi>
          <Kpi label="Waiting to be checked" value={s.awaiting_review}>Uploaded, not yet verified</Kpi>
          <Kpi label="Verified" value={s.by_status.Verified || 0}>Done</Kpi>
          <Kpi label="Total" value={s.total}>On your checklist</Kpi>
        </>)}
      </div>

      <div className="card">
        <div className="card-head">
          {staff ? (
            <div className="toolbar">
              <div className="toolbar-picker">
                <StudentPicker ariaLabel="Student" allLabel="Review queue — all students" value={studentId} onChange={(id) => update({ student_id: id, page: 1 })} />
              </div>
              {!studentId && (
                <select aria-label="Status" value={status} onChange={(e) => update({ status: e.target.value, page: 1 })}>
                  <option value={AWAITING}>Awaiting review</option>
                  <option value={WAITING_ON_STUDENT}>Waiting on the student</option>
                  <option value="all">All statuses</option>
                  {DOC_STATUSES.map((x) => <option key={x} value={x}>{docStatusLabel(x)}</option>)}
                </select>
              )}
            </div>
          ) : <div />}
          <span className="small muted" aria-live="polite">{data ? plural(data.count, "document") : ""}</span>
        </div>

        {err ? <ErrorAlert error={err} onRetry={err.status === 403 ? undefined : refresh}>{recordError(err, "student")}</ErrorAlert>
          : !data ? <p className="loading" role="status">Loading documents…</p>
          : queue ? (
            data.results.length
              ? data.results.map((d) => <DocRow key={d.id} d={d} user={user} showStudent actions={actions} />)
              : <p className="empty">{status === AWAITING ? "Nothing is waiting for review." : "No documents match this filter."}</p>
          ) : data.results.length ? <Grouped docs={data.results} user={user} actions={actions} />
          : (
            <div className="empty">
              <p>No documents on {staff ? "this student's" : "your"} checklist yet.</p>
              <button type="button" className="btn btn-primary" onClick={makeChecklist} disabled={checklistBusy}>{checklistBusy ? "Creating…" : "Create the standard checklist"}</button>
              <p className="small muted" style={{ marginTop: ".6rem" }}>Transcript, degree certificate, passport, CV and test scores.</p>
            </div>
          )}
        {queue && <Pager data={data} onPage={(p) => update({ page: p })} noun="document" />}
      </div>

      {drawers}
      {adding && <AddDrawer studentId={studentId} staff={staff} onClose={() => setAdding(false)} onDone={() => { setAdding(false); refresh(); }} />}
    </AppShell>
  );
}
