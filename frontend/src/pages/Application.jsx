/* Application status screen (SRS 4.5): status stepper, deadline, documents, actions and history. */
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import AppShell, { ROLE_LABEL } from "../components/Shell";
import Drawer from "../components/Drawer";
import { ConfirmDialog } from "../components/Dialog";
import { DocRow, useDocActions } from "../components/Documents";
import { useAuth } from "../components/auth";
import { useToast } from "../components/Toast";
import { AppStatusBadge, DeadlineBadge, ErrorAlert, Field, Loading, appStatusLabel, countdownText, docStatusLabel as docLabel, recordError } from "../components/ui";
import { api } from "../lib/api";
import { formatDate, formatDateTime } from "../lib/format";
import { fieldErrors, saveErrorMessage } from "../lib/form";
import { useLoad } from "../lib/useLoad";
import { useSubmit } from "../lib/useSubmit";

const MAIN_PATH = ["Planned", "Shortlisted", "Documents Pending", "Submitted", "Under Review", "Offer Received", "Completed"];
const ACTION_LABEL = {
  Shortlisted: "Shortlist", "Documents Pending": "Start collecting documents", Submitted: "Mark as submitted",
  "Under Review": "University is reviewing", "Offer Received": "Record offer", Rejected: "Record rejection",
  Completed: "Offer accepted — complete", Withdrawn: "Withdraw",
};
const BACKWARD = { Shortlisted: "Planned", "Documents Pending": "Shortlisted" }; // corrections, from -> to
const DANGER = ["Withdrawn", "Rejected"];

const actionLabel = (app, target) => (BACKWARD[app.status] === target ? `Back to ${appStatusLabel(target)}` : ACTION_LABEL[target] || appStatusLabel(target));

function Stepper({ app }) {
  // Show the main path; Rejected replaces "Offer Received", Withdrawn ends the path where it happened.
  const status = app.status;
  let steps = MAIN_PATH.slice();
  if (status === "Rejected") steps = [...MAIN_PATH.slice(0, 5), "Rejected"];
  if (status === "Withdrawn") {
    const last = app.history.map((h) => h.new_status).reverse().find((s) => s !== "Withdrawn") || "Planned";
    steps = [...MAIN_PATH.slice(0, MAIN_PATH.indexOf(last) + 1), "Withdrawn"];
  }
  const at = steps.indexOf(status);
  return (
    <ol className="stepper">
      {steps.map((s, i) => {
        const cls = i < at ? "done" : i === at ? (["Rejected", "Withdrawn"].includes(s) ? "bad" : status === "Completed" ? "done" : "current") : "";
        return <li key={s} className={cls} aria-current={i === at ? "step" : undefined}>{appStatusLabel(s)}</li>;
      })}
    </ol>
  );
}

function MoveDrawer({ app, status, onClose, onDone, onConflict }) {
  const toast = useToast();
  const [remarks, setRemarks] = useState("");
  const [errors, setErrors] = useState({});
  const [busy, run] = useSubmit();

  const save = () => run(async () => {
    try {
      const updated = await api(`/applications/${encodeURIComponent(app.id)}/status/`, { method: "POST", body: { status, remarks: remarks.trim(), rev: app.rev } });
      toast(`Status changed to ${appStatusLabel(status)}`);
      onDone(updated);
    } catch (err) {
      if (err.status === 409) { toast("This application changed meanwhile, so the latest version has been loaded. Check it and try again.", "warning"); onConflict(); return; }
      if (err.status === 400) setErrors(fieldErrors(err.data));
      toast(saveErrorMessage(err), "error");
    }
  });

  return (
    <Drawer title={actionLabel(app, status)} onClose={onClose} busy={busy} footer={<>
      <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button type="button" className={`btn ${DANGER.includes(status) ? "btn-danger-solid" : "btn-primary"}`} onClick={save} disabled={busy}>{busy ? "Saving…" : "Confirm"}</button>
    </>}>
      <p>Move <b>{app.snapshot.course_title}</b> from <AppStatusBadge status={app.status} /> to <AppStatusBadge status={status} />.</p>
      <form noValidate onSubmit={(e) => { e.preventDefault(); save(); }}>
        <Field label="Remarks (saved in the history)" error={errors.remarks || errors.status}>
          <textarea maxLength={500} placeholder={status === "Withdrawn" ? "Why is the application being withdrawn?" : "Optional"} value={remarks} onChange={(e) => setRemarks(e.target.value)} />
        </Field>
      </form>
    </Drawer>
  );
}

function EditDrawer({ app, onClose, onDone }) {
  const toast = useToast();
  const [v, setV] = useState({ deadline: app.deadline || "", decision_expected: app.decision_expected || "", tier: app.tier || "", notes: app.notes || "" });
  const [errors, setErrors] = useState({});
  const [busy, run] = useSubmit();
  const bind = (k) => ({ value: v[k], onChange: (e) => setV({ ...v, [k]: e.target.value }) });

  const save = () => run(async () => {
    const body = { tier: v.tier, notes: v.notes, rev: app.rev, decision_expected: v.decision_expected || null };
    if (v.deadline) body.deadline = v.deadline;
    try {
      const updated = await api(`/applications/${encodeURIComponent(app.id)}/`, { method: "PATCH", body });
      toast("Application updated");
      onDone(updated);
    } catch (err) {
      if (err.status === 400) setErrors(fieldErrors(err.data));
      toast(err.status === 409 ? "This application changed meanwhile. Close this panel, reload the page and try again." : saveErrorMessage(err), "error");
    }
  });

  return (
    <Drawer title="Edit application details" onClose={onClose} busy={busy} footer={<>
      <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
    </>}>
      <form noValidate onSubmit={(e) => { e.preventDefault(); save(); }}>
        <div className="grid grid-2">
          <Field label="Deadline" error={errors.deadline}><input type="date" {...bind("deadline")} /></Field>
          <Field label="Decision expected" error={errors.decision_expected}><input type="date" {...bind("decision_expected")} /></Field>
        </div>
        <Field label="Tier" error={errors.tier}>
          <select {...bind("tier")}>{["", "Reach", "Target", "Safe"].map((t) => <option key={t} value={t}>{t || "Not set"}</option>)}</select>
        </Field>
        <Field label="Notes" error={errors.notes}><textarea maxLength={1000} {...bind("notes")} /></Field>
      </form>
    </Drawer>
  );
}

function Detail({ app, user, setApp, reload }) {
  const toast = useToast();
  const navigate = useNavigate();
  const [drawer, setDrawer] = useState(null);
  const { actions, drawers } = useDocActions(reload);
  const isStaff = user.role !== "student";
  const snap = app.snapshot || {};
  const info = app.deadline_info || {};
  const intake = app.intake || {};
  const transitions = app.allowed_transitions || [];
  const isBack = (s) => BACKWARD[app.status] === s;
  const forward = transitions.filter((s) => !isBack(s) && s !== "Withdrawn");
  const secondary = transitions.filter((s) => isBack(s) || s === "Withdrawn");
  const blockers = app.submission_blockers || [];
  const countdown = info.date ? countdownText(info, { long: true }) : "No deadline has been set.";
  const done = (updated) => { setDrawer(null); setApp(updated); };
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [removing, runRemove] = useSubmit();

  const remove = () => runRemove(async () => {
    setDeleteError("");
    try {
      await api(`/applications/${encodeURIComponent(app.id)}/`, { method: "DELETE" });
      toast("Application deleted");
      navigate("/applications/");
    } catch (err) { setDeleteError(err.message); }
  });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{snap.course_title || "Application"}</h1>
          <p className="muted">{snap.university_name} · {snap.country}{snap.world_rank ? ` · World ranking ${snap.world_rank}` : ""}{snap.cluster ? ` · ${snap.cluster}` : ""}</p>
        </div>
        <div className="toolbar">
          <AppStatusBadge status={app.status} />
          {app.tier && <span className="badge badge-brand">{app.tier}</span>}
          {isStaff && <button type="button" className="btn btn-outline btn-sm" onClick={() => setDrawer({ kind: "edit" })}>Edit details</button>}
          {app.status === "Planned" && <button type="button" className="btn btn-danger btn-sm" onClick={() => { setDeleteError(""); setDeleting(true); }}>Delete</button>}
        </div>
      </div>

      <div className="card" style={{ marginBottom: "1rem" }}><Stepper app={app} /></div>
      <div className="layout-2">
        <div className="stack">
          <div className="card">
            <div className="card-head"><h3>Next step</h3><AppStatusBadge status={app.status} /></div>
            {blockers.length > 0 && (
              <div className="alert alert-warn">Before submission every document must be Verified. Outstanding:{" "}
                {blockers.map((b, i) => <span key={b.id || i}>{i ? ", " : ""}<b>{b.title || b.document_type}</b> ({docLabel(b.status)})</span>)}.
              </div>
            )}
            {transitions.length ? (
              <>
                <div className="toolbar">
                  {forward.map((s) => <button type="button" key={s} className={`btn ${DANGER.includes(s) ? "btn-danger" : "btn-primary"}`} onClick={() => setDrawer({ kind: "move", status: s })}>{actionLabel(app, s)}</button>)}
                  {secondary.map((s) => <button type="button" key={s} className={`btn ${DANGER.includes(s) ? "btn-danger" : "btn-outline"}`} onClick={() => setDrawer({ kind: "move", status: s })}>{actionLabel(app, s)}</button>)}
                </div>
                {!isStaff && <p className="small muted" style={{ margin: ".8rem 0 0" }}>Your counsellor moves the application through each stage.</p>}
              </>
            ) : (
              <p className="muted" style={{ margin: 0 }}>{app.is_terminal ? `This application is ${appStatusLabel(app.status).toLowerCase()}; no further changes.` : "Your counsellor will move this application to the next stage."}</p>
            )}
          </div>
          <div className="card">
            <div className="card-head"><h3>Documents</h3>
              <Link className="small" to={`/documents/${isStaff ? `?student_id=${encodeURIComponent(app.student_id)}` : ""}`}>All documents →</Link>
            </div>
            {app.documents.length
              ? app.documents.map((d) => <DocRow key={d.id} d={d} user={user} actions={actions} />)
              : <p className="muted" style={{ margin: 0 }}>No documents yet. SOP and LOR requirements are added when the application reaches Documents Pending.</p>}
          </div>
          <div className="card">
            <div className="card-head"><h3>SOP &amp; recommendation letters</h3>
              <Link className="small" to={isStaff ? `/writing/?student_id=${encodeURIComponent(app.student_id)}` : "/writing/"}>Open SOP &amp; LOR →</Link>
            </div>
            <p className="small muted" style={{ margin: 0 }}>{isStaff
              ? "Draft the statement of purpose with the guided interview and AI assistant, and track each referee's letter."
              : "See SOP drafts your counsellor shares with you and follow each recommendation letter."}</p>
          </div>
          <div className="card">
            <h3>Status history</h3>
            <ul className="timeline">
              {app.history.slice().reverse().map((h, i) => (
                <li key={h.id || i}>
                  <div className="when">{formatDateTime(h.timestamp)}</div>
                  <div className="what">{h.old_status ? `${appStatusLabel(h.old_status)} → ` : ""}{appStatusLabel(h.new_status)}</div>
                  <div className="note">{h.changed_by_name || "System"}{h.changed_by_role ? ` (${ROLE_LABEL[h.changed_by_role] || h.changed_by_role})` : ""}{h.remarks ? ` — ${h.remarks}` : ""}</div>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <div className="stack">
          <div className="card">
            <h3>Deadline</h3>
            <div style={{ margin: ".4rem 0 .6rem" }}><DeadlineBadge info={info} /></div>
            <p className="small muted" style={{ margin: 0 }}>{countdown}</p>
          </div>
          <div className="card">
            <h3>Key dates</h3>
            <dl className="facts">
              <dt>Intake</dt><dd>{snap.intake_name || "—"}</dd>
              <dt>Deadline</dt><dd>{formatDate(app.deadline)}</dd>
              <dt>Decision by</dt><dd>{formatDate(app.decision_expected)}</dd>
              <dt>Programme starts</dt><dd>{formatDate(intake.start_date)}</dd>
              <dt>Submitted</dt><dd>{formatDate(app.submitted_at)}</dd>
              <dt>Created</dt><dd>{formatDate(app.created_at)}</dd>
            </dl>
          </div>
          <div className="card">
            <h3>People</h3>
            <dl className="facts">
              <dt>Student</dt><dd>{isStaff ? <Link to={`/students/${encodeURIComponent(app.student_id)}/`}>{app.student_name}</Link> : app.student_name}</dd>
              <dt>Counsellor</dt><dd>{app.counsellor_name || "Not assigned"}</dd>
            </dl>
          </div>
          {app.notes && <div className="card"><h3>Notes</h3><p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{app.notes}</p></div>}
        </div>
      </div>

      {drawers}
      {drawer?.kind === "move" && <MoveDrawer app={app} status={drawer.status} onClose={() => setDrawer(null)} onDone={done} onConflict={() => { setDrawer(null); reload(); }} />}
      {drawer?.kind === "edit" && <EditDrawer app={app} onClose={() => setDrawer(null)} onDone={done} />}
      {deleting && (
        <ConfirmDialog title="Delete this application?" danger confirmLabel="Delete application" busyLabel="Deleting…" busy={removing}
          error={deleteError} onConfirm={remove} onCancel={() => setDeleting(false)}>
          <p><b>{snap.course_title}</b> at {snap.university_name} ({snap.intake_name}) for {app.student_name} will be removed, together with its status history and any document requirements that have no file yet.
            This cannot be undone.</p>
        </ConfirmDialog>
      )}
    </>
  );
}

export default function Application() {
  const { applicationId } = useParams();
  const { user } = useAuth();
  const { data: app, error, reload, setData } = useLoad(
    () => api(`/applications/${encodeURIComponent(applicationId)}/`), [applicationId]);
  const snap = app?.snapshot || {};

  return (
    <AppShell title={snap.course_title || "Application"} crumb={<><Link to="/applications/">Applications</Link> / {snap.university_name || "Application"}</>}>
      {error ? (
        <>
          <div className="page-head"><div><h1>Application</h1></div></div>
          <ErrorAlert error={error} onRetry={error.status === 403 || error.status === 404 ? undefined : reload}>{recordError(error, "application")}</ErrorAlert>
          <p><Link to="/applications/">Back to applications</Link></p>
        </>
      ) : !app ? (
        <><div className="page-head"><div><h1>Application</h1></div></div><Loading text="Loading application…" /></>
      ) : <Detail app={app} user={user} setApp={setData} reload={reload} />}
    </AppShell>
  );
}
