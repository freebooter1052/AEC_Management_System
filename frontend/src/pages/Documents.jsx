/* Document upload & status (SRS 4.6): a student's checklist; for staff, a review queue and per-student view. */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import AppShell from "../components/Shell";
import Drawer from "../components/Drawer";
import { DocRow, isStaff as staffRole, useDocActions } from "../components/Documents";
import { useAuth } from "../components/auth";
import { useToast } from "../components/Toast";
import { Field, Kpi, Pager } from "../components/ui";
import { api } from "../lib/api";
import { useForm } from "../lib/form";
import { useLoad } from "../lib/useLoad";

const TYPES = ["Transcript", "Degree Certificate", "Passport", "SOP", "LOR", "Resume/CV", "Test Score", "Other"];

function AddDrawer({ studentId, staff, onClose, onDone }) {
  const toast = useToast();
  const [apps, setApps] = useState([]);
  const form = useForm({ document_type: TYPES[0], title: "", application_id: "" });
  const { bind, errors } = form;

  useEffect(() => {
    api("/applications/", { query: { student_id: studentId, page_size: 100, open: "true" } }).then((d) => setApps(d.results), (err) => toast(err.message, "error"));
  }, [studentId, toast]);

  async function save() {
    const body = { ...form.values };
    if (staff) body.student_id = studentId;
    try {
      await api("/documents/", { method: "POST", body });
      toast("Document added to the checklist");
      onDone();
    } catch (err) {
      if (err.status === 400) form.showErrors(err.data);
      toast(err.message, "error");
    }
  }

  return (
    <Drawer title="Add a document" onClose={onClose} footer={<>
      <button className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button className="btn btn-primary" onClick={save}>Add</button>
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
  const [params] = useSearchParams();
  const staff = staffRole(user);
  const [studentId, setStudentId] = useState(staff ? params.get("student_id") || "" : user.profile_id || "");
  const [status, setStatus] = useState("Uploaded,Under Review");
  const [page, setPage] = useState(1);
  const [students, setStudents] = useState([]);
  const [adding, setAdding] = useState(false);
  const queue = staff && !studentId;

  useEffect(() => {
    if (staff) api("/students/", { query: { page_size: 100 } }).then((d) => setStudents(d.results), (err) => toast(err.message, "error"));
  }, [staff, toast]);

  const summary = useLoad(() => api("/documents/summary/", { query: { student_id: staff ? studentId : "" } }), [staff, studentId]);
  const list = useLoad(
    () => api("/documents/", { query: queue ? { status, page } : { student_id: studentId, page_size: 100 } }),
    [queue, status, page, studentId]);

  const refresh = () => { summary.reload(); list.reload(); };
  const { actions, drawers } = useDocActions(refresh);

  function pickStudent(id) {
    setStudentId(id);
    setPage(1);
    window.history.replaceState(null, "", id ? `?student_id=${encodeURIComponent(id)}` : window.location.pathname);
  }

  async function makeChecklist() {
    try {
      const res = await api("/documents/checklist/", { method: "POST", body: staff ? { student_id: studentId } : {} });
      toast(res.created ? `${res.created} document${res.created === 1 ? "" : "s"} added to the checklist` : "The checklist is already complete");
      refresh();
    } catch (err) { toast(err.message, "error"); }
  }

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
            <button className="btn btn-outline" onClick={makeChecklist}>Standard checklist</button>
            <button className="btn btn-primary" onClick={() => setAdding(true)}>Add document</button>
          </>}
        </div>
      </div>

      <div className="kpis">
        {s && (staff ? <>
          <Kpi label="Awaiting review" value={s.awaiting_review}>Uploaded or under review</Kpi>
          <Kpi label="Waiting on students" value={s.needs_attention}>Required, rejected or expired</Kpi>
          <Kpi label="Verified" value={s.by_status.Verified || 0}>Ready for submission</Kpi>
          <Kpi label="Total" value={s.total}>{studentId ? "For this student" : "Across your students"}</Kpi>
        </> : <>
          <Kpi label="Needs your action" value={s.needs_attention}>Upload or replace</Kpi>
          <Kpi label="With your counsellor" value={s.awaiting_review}>Being reviewed</Kpi>
          <Kpi label="Verified" value={s.by_status.Verified || 0}>Done</Kpi>
          <Kpi label="Total" value={s.total}>On your checklist</Kpi>
        </>)}
      </div>

      <div className="card">
        <div className="card-head">
          {staff ? (
            <div className="toolbar">
              <select aria-label="Student" value={studentId} onChange={(e) => pickStudent(e.target.value)}>
                <option value="">Review queue — all students</option>
                {students.map((st) => <option key={st.id} value={st.id}>{st.full_name}</option>)}
              </select>
              {!studentId && (
                <select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
                  <option value="Uploaded,Under Review">Awaiting review</option>
                  <option value="Required,Rejected,Expired">Waiting on the student</option>
                  <option value="">All statuses</option>
                  {["Required", "Uploaded", "Under Review", "Verified", "Rejected", "Expired"].map((x) => <option key={x}>{x}</option>)}
                </select>
              )}
            </div>
          ) : <div />}
          <span className="small muted">{data ? `${data.count} document${data.count === 1 ? "" : "s"}` : ""}</span>
        </div>

        {err ? <div className="alert alert-error">{err.status === 403 ? "You do not have access to this student." : err.message}</div>
          : !data ? <p className="loading">Loading documents…</p>
          : queue ? (
            data.results.length
              ? data.results.map((d) => <DocRow key={d.id} d={d} user={user} showStudent actions={actions} />)
              : <p className="empty">{status.startsWith("Uploaded") ? "Nothing is waiting for review. 🎉" : "No documents match this filter."}</p>
          ) : data.results.length ? <Grouped docs={data.results} user={user} actions={actions} />
          : (
            <div className="empty">
              <p>No documents on {staff ? "this student's" : "your"} checklist yet.</p>
              <button className="btn btn-primary" onClick={makeChecklist}>Create the standard checklist</button>
              <p className="small muted" style={{ marginTop: ".6rem" }}>Transcript, degree certificate, passport, CV and test scores.</p>
            </div>
          )}
        {queue && <Pager data={data} onPage={setPage} />}
      </div>

      {drawers}
      {adding && <AddDrawer studentId={studentId} staff={staff} onClose={() => setAdding(false)} onDone={() => { setAdding(false); refresh(); }} />}
    </AppShell>
  );
}
