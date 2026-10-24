/* SOP & LOR workspace: one student's statements of purpose and referees, AI consent, and the admin setting. */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AppShell from "../components/Shell";
import ApprovalBox from "../components/Approval";
import Drawer from "../components/Drawer";
import { ConfirmDialog } from "../components/Dialog";
import StudentPicker from "../components/StudentPicker";
import { TabList, tabPanel } from "../components/Tabs";
import { useAuth } from "../components/auth";
import { useToast } from "../components/Toast";
import { ErrorAlert, Field, Loading } from "../components/ui";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import { saveErrorMessage, useForm } from "../lib/form";
import { useLoad } from "../lib/useLoad";
import { useQueryState } from "../lib/useQueryState";
import { useSubmit } from "../lib/useSubmit";
import { aiBlockReason, limitState, refereeStage, statementStatus, WORD_LIMITS } from "../lib/writing";
import { ID_PATTERN } from "./Applications";

const STATE = {
  student_id: { default: "", pattern: ID_PATTERN },
  tab: { default: "sop", allowed: ["sop", "lor"] },
};

/* What the student is agreeing to, shown on their consent card and to staff. */
function ConsentText() {
  return (
    <ul className="list-plain writing-consent-list">
      <li>Your counsellor can use Google Gemini to draft and improve your SOP and to prepare briefs for your referees.</li>
      <li>Only what a statement needs is sent: your first name, academic record, English test score, target course and the answers you give your counsellor. Never your email, phone, date of birth, address or documents.</li>
      <li>Your counsellor reviews every draft, and nothing is sent to a university by the assistant. You can turn this off at any time.</li>
    </ul>
  );
}

function StudentConsent({ consent, onChange }) {
  const toast = useToast();
  const [busy, run] = useSubmit();
  const set = (granted) => run(async () => {
    try {
      await api("/writing/consent/", { method: "PUT", body: { granted } });
      toast(granted ? "Thanks — your counsellor can now use the writing assistant" : "AI-assisted writing turned off", granted ? "success" : "info");
      onChange();
    } catch (err) { toast(saveErrorMessage(err), "error"); }
  });
  return (
    <div className={`card writing-consent ${consent.granted ? "is-on" : ""}`}>
      <div className="card-head">
        <h3>AI-assisted writing</h3>
        <span className={consent.granted ? "badge badge-ok" : "badge"}>{consent.granted ? "Allowed" : "Not allowed"}</span>
      </div>
      <ConsentText />
      <div className="toolbar">
        {consent.granted
          ? <button type="button" className="btn btn-outline" onClick={() => set(false)} disabled={busy}>{busy ? "Saving…" : "Turn off"}</button>
          : <button type="button" className="btn btn-primary" onClick={() => set(true)} disabled={busy}>{busy ? "Saving…" : "I agree — allow AI-assisted writing"}</button>}
        {consent.granted && consent.granted_at && <span className="small muted">Allowed on {formatDate(consent.granted_at)}</span>}
      </div>
    </div>
  );
}

/* What is waiting for the student's OK, with the optional AI setting tucked underneath. */
function StudentReview({ data }) {
  const waitingSops = data.statements.filter((s) => s.kind === "sop" && s.status === "Shared" && !s.approved).length;
  const waitingLors = data.references.filter((r) => ["Received", "Verified"].includes(r.stage) && r.student_approval?.decision !== "Approved").length;
  const waiting = waitingSops + waitingLors;
  return (
    <>
      <div className={`alert ${waiting ? "alert-warn" : "alert-info"}`} role="status">
        {waiting
          ? <>Your counsellor has prepared {waiting === 1 ? "a document" : `${waiting} documents`} for you to review. Open {waiting === 1 ? "it" : "each one"} and approve it, or ask for changes.</>
          : "When your counsellor finishes your SOP or a recommendation letter arrives, you will be asked to review it here and approve it."}
      </div>
      <details className="card" style={{ marginTop: ".75rem" }}>
        <summary className="small muted">Counsellor AI assistance: {data.consent.granted ? "allowed" : "not allowed"}</summary>
        <StudentConsent consent={data.consent} onChange={() => window.location.reload()} />
      </details>
    </>
  );
}

function StaffStatus({ data }) {
  const toast = useToast();
  const [busy, run] = useSubmit();
  const blocked = aiBlockReason({ consent: data.consent, aiAvailable: data.ai_available, canEdit: data.can_edit });
  const ask = () => run(async () => {
    try {
      const res = await api("/writing/consent/request/", { method: "POST", body: { student_id: data.student.id } });
      toast(res.sent ? `We asked ${data.student.full_name} in the app` : res.detail, res.sent ? "success" : "info");
    } catch (err) { toast(saveErrorMessage(err), "error"); }
  });
  return (
    <div className={`alert ${blocked ? "alert-info" : "alert-success"} alert-row`}>
      <span>
        {blocked
          ? <>{blocked}</>
          : <><b>Writing assistant ready.</b> {data.student.full_name} has agreed to AI-assisted writing.</>}
      </span>
      {data.can_edit && data.ai_available && !data.consent.granted && (
        <button type="button" className="btn btn-outline btn-sm" onClick={ask} disabled={busy}>{busy ? "Sending…" : "Ask the student"}</button>
      )}
    </div>
  );
}

function HowItWorks() {
  return (
    <ol className="writing-how">
      <li><b>Interview</b><span>Answer a few guided questions with the student — motivation, experience, goals.</span></li>
      <li><b>Draft</b><span>Write the SOP yourself, or let the assistant write a first draft from the answers.</span></li>
      <li><b>Review &amp; share</b><span>Get AI feedback, polish it, then share it with the student for comments.</span></li>
    </ol>
  );
}

function NewSopDrawer({ data, onClose }) {
  const toast = useToast();
  const navigate = useNavigate();
  const form = useForm({ application_id: data.applications[0]?.id || "", word_limit: "1000", title: "" });
  const { bind, errors } = form;
  const [busy, run] = useSubmit();
  const save = () => run(async () => {
    const v = form.values;
    try {
      const st = await api("/writing/statements/", { method: "POST", body: {
        student_id: data.student.id, application_id: v.application_id || null, word_limit: Number(v.word_limit) || 1000, title: v.title.trim() } });
      toast("SOP created — start with the interview questions");
      navigate(`/writing/statements/${encodeURIComponent(st.id)}/`);
    } catch (err) {
      if (err.status === 400) form.showErrors(err.data);
      toast(saveErrorMessage(err), "error");
    }
  });
  return (
    <Drawer title="New statement of purpose" onClose={onClose} busy={busy} footer={<>
      <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Creating…" : "Create and continue"}</button>
    </>}>
      <form noValidate ref={form.ref} onSubmit={(e) => { e.preventDefault(); save(); }}>
        <Field label="Which application is it for?" error={errors.application_id} hint="An SOP written for one course reads far better than a general one.">
          <select {...bind("application_id")}>
            {data.applications.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
            <option value="">General SOP (not for one application)</option>
          </select>
        </Field>
        <Field label="Word limit" error={errors.word_limit} hint="Use the limit the university gives. 800–1,000 words is typical.">
          <select {...bind("word_limit")}>{WORD_LIMITS.map((n) => <option key={n} value={n}>{n.toLocaleString()} words</option>)}</select>
        </Field>
        <Field label="Title (optional)" error={errors.title} hint="Leave empty to name it after the course.">
          <input maxLength={160} {...bind("title")} />
        </Field>
      </form>
    </Drawer>
  );
}

function SopList({ data, isStudent, onNew }) {
  const sops = data.statements.filter((s) => s.kind === "sop");
  if (!sops.length) {
    return (
      <div className="empty">
        {data.can_edit ? (
          <>
            <p><b>No SOPs yet.</b> Create one for an application and the page will guide you through it.</p>
            <HowItWorks />
            <button type="button" className="btn btn-primary" onClick={onNew}>New SOP</button>
          </>
        ) : <p>{isStudent ? "Your counsellor has not shared an SOP draft with you yet. You will get a notification when they do." : "No SOPs yet. The student's counsellor creates them here."}</p>}
      </div>
    );
  }
  return (
    <div className="stack">
      {sops.map((s) => {
        const st = statementStatus(s.status);
        const limit = limitState(s.word_count, s.word_limit);
        return (
          <Link key={s.id} className="card writing-row" to={`/writing/statements/${encodeURIComponent(s.id)}/`}>
            <div className="writing-row-main">
              <h3>{s.title}</h3>
              <div className="small muted">{limit.text}{s.placeholders ? ` · ${s.placeholders} gap${s.placeholders === 1 ? "" : "s"} to fill` : ""}{s.comment_count ? ` · ${s.comment_count} comment${s.comment_count === 1 ? "" : "s"}` : ""} · updated {formatDate(s.updated_at)}</div>
            </div>
            <div className="toolbar">
              {s.ai_assisted && <span className="badge badge-brand">AI-assisted</span>}
              <span className={st.className}>{st.label}</span>
              {isStudent && s.status === "Shared" && !s.approved && <span className="badge badge-warn">Needs your review</span>}
              <span aria-hidden="true" className="writing-chevron">›</span>
            </div>
          </Link>
        );
      })}
    </div>
  );
}

function RefereeDrawer({ data, reference, onClose, onDone }) {
  const toast = useToast();
  const r = reference?.referee || {};
  const form = useForm({
    application_id: reference ? reference.application_id || "" : data.applications[0]?.id || "",
    name: r.name || "", title: r.title || "", institution: r.institution || "", email: r.email || "", relationship: r.relationship || "",
    highlights: reference?.highlights || "", due_date: reference?.due_date || "",
  });
  const { bind, errors } = form;
  const [busy, run] = useSubmit();
  const save = () => run(async () => {
    const v = form.values;
    const referee = { name: v.name.trim(), title: v.title.trim(), institution: v.institution.trim(), email: v.email.trim(), relationship: v.relationship.trim() };
    const body = { referee, highlights: v.highlights.trim(), due_date: v.due_date || null };
    try {
      if (reference) await api(`/writing/references/${encodeURIComponent(reference.id)}/`, { method: "PATCH", body: { ...body, rev: reference.rev } });
      else await api("/writing/references/", { method: "POST", body: { ...body, student_id: data.student.id, application_id: v.application_id || null } });
      toast(reference ? "Referee updated" : `${referee.name} added — an LOR slot was added to the documents checklist`);
      onDone();
    } catch (err) {
      if (err.status === 400) form.showErrors(err.data?.referee ? { ...err.data, ...err.data.referee } : err.data);
      toast(saveErrorMessage(err), "error");
    }
  });
  return (
    <Drawer title={reference ? "Edit referee" : "Add a referee"} onClose={onClose} busy={busy} footer={<>
      <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : reference ? "Save" : "Add referee"}</button>
    </>}>
      <form noValidate ref={form.ref} onSubmit={(e) => { e.preventDefault(); save(); }}>
        {!reference && (
          <Field label="For" error={errors.application_id}>
            <select {...bind("application_id")}>
              {data.applications.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
              <option value="">General (all applications)</option>
            </select>
          </Field>
        )}
        <Field label="Referee's name" error={errors.name}><input maxLength={120} placeholder="e.g. Dr. Priya Rao" {...bind("name")} /></Field>
        <div className="grid grid-2">
          <Field label="Job title" error={errors.title}><input maxLength={120} placeholder="Associate Professor" {...bind("title")} /></Field>
          <Field label="Institution or employer" error={errors.institution}><input maxLength={160} {...bind("institution")} /></Field>
        </div>
        <div className="grid grid-2">
          <Field label="Email (optional)" error={errors.email}><input type="email" maxLength={200} {...bind("email")} /></Field>
          <Field label="Letter needed by" error={errors.due_date}><input type="date" {...bind("due_date")} /></Field>
        </div>
        <Field label="How do they know the student?" error={errors.relationship}><input maxLength={200} placeholder="Final-year project supervisor, taught Control Systems" {...bind("relationship")} /></Field>
        <Field label="What can they speak to?" error={errors.highlights} hint="Projects, grades in their subject, qualities they saw. The brief uses only this and the student's profile.">
          <textarea maxLength={3000} rows={5} {...bind("highlights")} />
        </Field>
      </form>
    </Drawer>
  );
}

function RefereeCard({ data, r, onEdit, onChanged }) {
  const toast = useToast();
  const navigate = useNavigate();
  const [busy, run] = useSubmit();
  const [cancelling, setCancelling] = useState(false);
  const stage = refereeStage(r.stage);
  const blocked = aiBlockReason({ consent: data.consent, aiAvailable: data.ai_available, canEdit: data.can_edit });
  const brief = r.statements.find((s) => s.kind === "lor_brief");
  const draft = r.statements.find((s) => s.kind === "lor_draft");
  const open = (id) => navigate(`/writing/statements/${encodeURIComponent(id)}/`);
  const active = r.stage !== "Cancelled";

  const prepare = (kind) => run(async () => {
    try {
      toast(kind === "lor_brief" ? "Preparing the brief…" : "Preparing a starting draft…", "info");
      const st = await api(`/writing/references/${encodeURIComponent(r.id)}/prepare/`, { method: "POST", body: { kind } });
      open(st.id);
    } catch (err) { toast(saveErrorMessage(err), "error"); }
  });
  const setStatus = (status) => run(async () => {
    try {
      await api(`/writing/references/${encodeURIComponent(r.id)}/`, { method: "PATCH", body: { status, rev: r.rev } });
      toast(status === "Requested" ? `Marked as requested from ${r.referee.name}` : `${r.referee.name} cancelled`);
      setCancelling(false);
      onChanged();
    } catch (err) { toast(saveErrorMessage(err), "error"); }
  });

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h3 style={{ margin: 0 }}>{r.referee.name}</h3>
          <div className="small muted">{[r.referee.title, r.referee.institution].filter(Boolean).join(", ") || "—"}{r.referee.relationship ? ` · ${r.referee.relationship}` : ""}</div>
        </div>
        <span className={stage.className}>{stage.label}</span>
      </div>
      <p className="small" style={{ margin: ".2rem 0 .8rem" }}>{stage.next}{r.due_date ? ` Needed by ${formatDate(r.due_date)}.` : ""}</p>
      {data.can_edit && active && (
        <div className="toolbar">
          {brief
            ? <button type="button" className="btn btn-outline btn-sm" onClick={() => open(brief.id)}>Open brief</button>
            : <button type="button" className="btn btn-primary btn-sm" onClick={() => prepare("lor_brief")} disabled={busy || !!blocked} title={blocked || undefined}>✨ Prepare brief for referee</button>}
          {data.settings.allow_lor_drafts && (draft
            ? <button type="button" className="btn btn-outline btn-sm" onClick={() => open(draft.id)}>Open starting draft</button>
            : <button type="button" className="btn btn-outline btn-sm" onClick={() => prepare("lor_draft")} disabled={busy || !!blocked} title={blocked || undefined}>Starting draft for referee</button>)}
          {r.stage === "Planned" && <button type="button" className="btn btn-outline btn-sm" onClick={() => setStatus("Requested")} disabled={busy}>Mark as requested</button>}
          {["Requested", "Received"].includes(r.stage) && <Link className="btn btn-outline btn-sm" to={`/documents/?student_id=${encodeURIComponent(data.student.id)}`}>{r.stage === "Received" ? "Check letter" : "Upload letter"}</Link>}
          <button type="button" className="btn btn-outline btn-sm" onClick={onEdit}>Edit</button>
          {r.stage !== "Verified" && <button type="button" className="btn btn-danger btn-sm" onClick={() => setCancelling(true)}>Cancel</button>}
        </div>
      )}
      {!data.can_edit && ["Received", "Verified"].includes(r.stage) && (
        <ApprovalBox approval={r.student_approval} noun="letter" url={`/writing/references/${encodeURIComponent(r.id)}/decision/`} onDone={onChanged}
          intro={<>Your counsellor has received this letter. Check it under <Link to="/documents/">Documents</Link>, then tell us if it is OK.</>} />
      )}
      {data.can_edit && r.student_approval && (
        <p className="small" style={{ margin: ".6rem 0 0" }}>{r.student_approval.decision === "Approved" ? "The student approved this letter." : `The student asked for changes: “${r.student_approval.note}”`}</p>
      )}
      {cancelling && (
        <ConfirmDialog title={`Cancel ${r.referee.name}?`} danger confirmLabel="Cancel referee" busyLabel="Cancelling…" cancelLabel="Keep" busy={busy}
          onConfirm={() => setStatus("Cancelled")} onCancel={() => setCancelling(false)}>
          <p>{r.document_status === "Required" ? "Their empty LOR slot will be removed from the documents checklist." : "Any letter already uploaded stays under Documents."} This cannot be undone; add them again if needed.</p>
        </ConfirmDialog>
      )}
    </div>
  );
}

function RefereeList({ data, reload }) {
  const [editing, setEditing] = useState(null); // null | "new" | reference
  const active = data.references.filter((r) => r.stage !== "Cancelled");
  const cancelled = data.references.filter((r) => r.stage === "Cancelled");
  return (
    <>
      <div className="alert alert-info">
        Referees write and sign their own letters. {data.can_edit ? "Add each referee, prepare a short brief of talking points to send them, and track the letter until it is verified." : "Your counsellor tracks each letter here until it is verified."}
      </div>
      {data.can_edit && <div className="toolbar" style={{ marginBottom: "1rem" }}><button type="button" className="btn btn-primary" onClick={() => setEditing("new")}>Add referee</button></div>}
      {active.length === 0 && <p className="empty">{data.can_edit ? "No referees yet. Most universities ask for two letters." : "No referees have been added yet."}</p>}
      <div className="stack">
        {active.map((r) => <RefereeCard key={r.id} data={data} r={r} onEdit={() => setEditing(r)} onChanged={reload} />)}
      </div>
      {cancelled.length > 0 && (
        <details style={{ marginTop: "1rem" }}><summary className="small muted">{cancelled.length} cancelled</summary>
          <div className="stack" style={{ marginTop: ".6rem" }}>{cancelled.map((r) => <RefereeCard key={r.id} data={data} r={r} onEdit={() => {}} onChanged={reload} />)}</div>
        </details>
      )}
      {editing && <RefereeDrawer data={data} reference={editing === "new" ? null : editing} onClose={() => setEditing(null)} onDone={() => { setEditing(null); reload(); }} />}
    </>
  );
}

function AdminSettings() {
  const toast = useToast();
  const { data, error, reload, setData } = useLoad(() => api("/writing/settings/"), []);
  const [busy, run] = useSubmit();
  const toggle = () => run(async () => {
    try {
      setData(await api("/writing/settings/", { method: "PATCH", body: { allow_lor_drafts: !data.allow_lor_drafts } }));
      toast("Setting saved");
    } catch (err) { toast(saveErrorMessage(err), "error"); }
  });
  if (error) return <ErrorAlert error={error} onRetry={reload} />;
  if (!data) return null;
  return (
    <div className="card" style={{ marginBottom: "1rem" }}>
      <div className="card-head"><h3>Writing assistant settings</h3>
        <span className={data.ai_available ? "badge badge-ok" : "badge badge-warn"}>{data.ai_available ? "Gemini connected" : "No Gemini API key"}</span></div>
      {!data.ai_available && <p className="small">Add <code>GEMINI_API_KEY</code> to the server's <code>.env</code> file and restart it to turn on AI drafting.</p>}
      <label className="checkbox">
        <input type="checkbox" checked={data.allow_lor_drafts} onChange={toggle} disabled={busy} />
        Let counsellors generate a starting draft of a recommendation letter for the referee to rewrite
      </label>
      <p className="small muted" style={{ margin: ".4rem 0 0" }}>Off by default: referees normally write their own letters from the brief. Turn on only if your agency's policy allows it.</p>
    </div>
  );
}

export default function Writing() {
  const { user } = useAuth();
  const staff = user.role !== "student";
  const [state, update] = useQueryState(STATE);
  const studentId = staff ? state.student_id : "";
  const [newSop, setNewSop] = useState(false);
  const show = !staff || studentId;
  const { data, error, reload } = useLoad(() => (show ? api("/writing/", { query: { student_id: studentId } }) : Promise.resolve(null)), [show, studentId]);

  return (
    <AppShell title="SOP & LOR">
      <div className="page-head">
        <div>
          <h1>SOP &amp; LOR</h1>
          <p className="muted">{staff ? "Write statements of purpose with your students and track every recommendation letter." : "Your statements of purpose and recommendation letters, prepared with your counsellor."}</p>
        </div>
        {staff && <div className="toolbar toolbar-picker"><StudentPicker ariaLabel="Student" value={studentId} onChange={(id) => update({ student_id: id })} /></div>}
      </div>

      {user.role === "admin" && <AdminSettings />}

      {!show ? (
        <div className="card">
          <h3>Choose a student to begin</h3>
          <p className="muted">Pick a student above to see their SOPs and referees.</p>
          <HowItWorks />
        </div>
      ) : error ? (
        <ErrorAlert error={error} onRetry={error.status === 403 ? undefined : reload}>{error.status === 403 ? "You do not have access to this student." : error.message}</ErrorAlert>
      ) : !data ? <Loading text="Loading…" /> : (
        <>
          {staff ? <StaffStatus data={data} /> : <StudentReview data={data} />}
          <div className="card-head" style={{ marginTop: "1rem" }}>
            <TabList id="writing" label="Writing" tabs={[["sop", `Statements of purpose (${data.statements.filter((s) => s.kind === "sop").length})`], ["lor", `Recommendation letters (${data.references.filter((r) => r.stage !== "Cancelled").length})`]]}
              selected={state.tab} onSelect={(tab) => update({ tab })} />
            {state.tab === "sop" && data.can_edit && data.statements.some((s) => s.kind === "sop") && <button type="button" className="btn btn-primary btn-sm" onClick={() => setNewSop(true)}>New SOP</button>}
          </div>
          <div {...tabPanel("writing", "sop", state.tab)}><SopList data={data} isStudent={!staff} onNew={() => setNewSop(true)} /></div>
          <div {...tabPanel("writing", "lor", state.tab)}><RefereeList data={data} reload={reload} /></div>
          {newSop && <NewSopDrawer data={data} onClose={() => setNewSop(false)} />}
        </>
      )}
    </AppShell>
  );
}
