/* Counselling (SRS 4.7): calendar, session history and follow-ups; counsellors schedule and record sessions. */
import { Fragment, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import AppShell from "../components/Shell";
import Drawer from "../components/Drawer";
import { useAuth } from "../components/auth";
import { useToast } from "../components/Toast";
import { Field, Pager, SessionStatusBadge } from "../components/ui";
import { api } from "../lib/api";
import { formatDate, formatDateTime, formatTime } from "../lib/format";
import { fieldErrors } from "../lib/form";
import { useLoad } from "../lib/useLoad";

const MODES = ["Video call", "In person", "Phone"];
const TABS = [["calendar", "Calendar"], ["history", "History"], ["follow-ups", "Follow-ups"]];
const FOLLOW_BADGE = { overdue: ["Overdue", "badge badge-err"], due_today: ["Due today", "badge badge-warn"], pending: ["Pending", "badge badge-info"], done: ["Done", "badge badge-ok"] };

const firstOfMonth = (d) => new Date(d.getFullYear(), d.getMonth(), 1);
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const lines = (text) => text.split("\n").map((l) => l.trim()).filter(Boolean);

function FollowBadge({ state }) {
  const [t, c] = FOLLOW_BADGE[state] || ["—", "badge"];
  return <span className={c}>{t}</span>;
}

function SessionCard({ s, isStaff, onOpen }) {
  const f = s.follow_up;
  const list = (title, items) => (items && items.length ? <><div className="label-sm">{title}</div><ul>{items.map((i, k) => <li key={k}>{i}</li>)}</ul></> : null);
  return (
    <article className="session-card">
      <header><h4>{s.topic}</h4><span><SessionStatusBadge status={s.status} /></span></header>
      <div className="small muted">
        {formatDateTime(s.scheduled_at)} · {s.duration_minutes} min · {s.mode} · {isStaff ? `${s.student_name} with ${s.counsellor_name}` : `with ${s.counsellor_name}`}
      </div>
      {s.summary && <><div className="label-sm">Summary</div><p style={{ margin: ".2rem 0 .4rem", whiteSpace: "pre-wrap" }}>{s.summary}</p></>}
      {list("Recommendations", s.recommendations)}
      {list("Agreed actions", s.action_items)}
      {s.status === "Cancelled" && s.cancel_reason && <p className="small muted">Cancelled: {s.cancel_reason}</p>}
      {f && <div className="follow-box"><span><b>Follow-up:</b> {f.action} · due {formatDate(f.due_date)}</span><FollowBadge state={s.follow_up_state} /></div>}
      {onOpen && (
        <div className="toolbar" style={{ marginTop: ".7rem" }}>
          <button className="btn btn-outline btn-sm" onClick={() => onOpen(s)}>{s.can_manage && s.status === "Scheduled" ? "Manage" : "Details"}</button>
        </div>
      )}
    </article>
  );
}

function Calendar({ user, studentId, month, setMonth, version, onOpen }) {
  const toast = useToast();
  const gridStart = addDays(month, -((month.getDay() + 6) % 7)); // Monday on or before the 1st
  const { data, error } = useLoad(
    () => api("/counselling/calendar/", { query: { start: ymd(gridStart), end: ymd(addDays(gridStart, 42)), student_id: studentId } }),
    [month.getTime(), studentId, version],
  );
  useEffect(() => { if (error) toast(error.message, "error"); }, [error, toast]);

  const who = (s) => (user.role === "student" ? s.counsellor_name : s.student_name);
  const byDay = {};
  const push = (key, el) => (byDay[key] ||= []).push(el);
  (data?.sessions || []).forEach((s) => push(ymd(new Date(s.scheduled_at)), (
    <button key={s.id} className={`event ${s.needs_notes ? "notes" : s.status}`} title={`${s.topic} — ${who(s)}`} onClick={() => onOpen(s)}>
      {formatTime(s.scheduled_at)} <span className="who">{who(s)}</span>
    </button>
  )));
  (data?.follow_ups || []).forEach((f, i) => push(f.due_date, (
    <button key={`f${i}-${f.session_id}`} className={`event follow ${f.state}`} title={`Follow-up: ${f.action}`} onClick={() => onOpen({ id: f.session_id })}>
      ⚑ <span className="who">{f.action}</span>
    </button>
  )));
  const today = ymd(new Date());

  return (
    <section>
      <div className="cal-head">
        <h2>{month.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</h2>
        <div className="toolbar">
          <button className="btn btn-outline btn-sm" aria-label="Previous month" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}>‹ Prev</button>
          <button className="btn btn-outline btn-sm" onClick={() => setMonth(firstOfMonth(new Date()))}>Today</button>
          <button className="btn btn-outline btn-sm" aria-label="Next month" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}>Next ›</button>
        </div>
      </div>
      <div className="calendar">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <div className="dow" key={d}>{d}</div>)}
        {Array.from({ length: 42 }, (_, i) => {
          const d = addDays(gridStart, i);
          const key = ymd(d);
          return (
            <div key={key} className={`day ${d.getMonth() !== month.getMonth() ? "other" : ""} ${key === today ? "today" : ""}`}>
              <span className="num">{d.getDate()}</span>{byDay[key]}
            </div>
          );
        })}
      </div>
      <div className="legend">
        <span style={{ "--c": "var(--info)" }}>Scheduled</span><span style={{ "--c": "var(--warn)" }}>Needs notes</span><span style={{ "--c": "var(--ok)" }}>Completed</span>
        <span style={{ "--c": "#94a3b8" }}>Cancelled</span><span style={{ "--c": "var(--primary)" }}>Follow-up due</span><span style={{ "--c": "var(--err)" }}>Follow-up overdue</span>
      </div>
    </section>
  );
}

function History({ studentId, version, isStaff, onOpen }) {
  const toast = useToast();
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [studentId, status]);
  const { data, error } = useLoad(
    () => api("/counselling/sessions/", { query: { student_id: studentId, status, page, page_size: 10 } }), [studentId, status, page, version]);
  useEffect(() => { if (error) toast(error.message, "error"); }, [error, toast]);

  return (
    <section>
      <div className="toolbar" style={{ marginBottom: "1rem" }}>
        <select aria-label="Session status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All sessions</option><option>Scheduled</option><option>Completed</option><option>Cancelled</option>
        </select>
      </div>
      {data && (data.results.length
        ? data.results.map((s) => <SessionCard key={s.id} s={s} isStaff={isStaff} onOpen={onOpen} />)
        : <p className="empty">No counselling sessions yet.</p>)}
      <Pager data={data} onPage={setPage} />
    </section>
  );
}

function FollowUps({ studentId, version, isStaff, onOpen, onMark }) {
  const toast = useToast();
  const [status, setStatus] = useState("Pending");
  const { data, error } = useLoad(() => api("/counselling/follow-ups/", { query: { student_id: studentId, status } }), [studentId, status, version]);
  useEffect(() => { if (error) toast(error.message, "error"); }, [error, toast]);
  const cols = isStaff ? 6 : 5;

  return (
    <section>
      <div className="toolbar" style={{ marginBottom: "1rem" }}>
        <select aria-label="Follow-up status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="Pending">Pending</option><option value="Done">Done</option><option value="">All</option>
        </select>
      </div>
      <div className="table-wrap"><table>
        <thead><tr><th>Due</th><th>Action</th>{isStaff && <th>Student</th>}<th>From session</th><th>Status</th><th /></tr></thead>
        <tbody>
          {data && (data.results.length ? data.results.map((f, i) => (
            <tr key={`${f.session_id}-${i}`}>
              <td style={{ whiteSpace: "nowrap" }}>{formatDate(f.due_date)}</td>
              <td className="name">{f.action}</td>
              {isStaff && <td>{f.student_name}</td>}
              <td><a href="#" onClick={(e) => { e.preventDefault(); onOpen({ id: f.session_id }); }}>{f.topic}</a><div className="small muted">{formatDate(f.session_date)}</div></td>
              <td><FollowBadge state={f.state} /></td>
              <td style={{ textAlign: "right" }}>{f.status === "Pending" && <button className="btn btn-outline btn-sm" onClick={() => onMark(f.session_id, f.rev)}>Mark done</button>}</td>
            </tr>
          )) : <tr><td colSpan={cols} className="empty">No {status ? `${status.toLowerCase()} ` : ""}follow-ups.</td></tr>)}
        </tbody>
      </table></div>
    </section>
  );
}

function SessionDrawer({ initial, user, isStaff, onClose, onMark, onNotes, onReschedule, onChanged }) {
  const toast = useToast();
  const [s, setS] = useState(initial.topic ? initial : null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    api(`/counselling/sessions/${encodeURIComponent(initial.id)}/`).then(setS, (err) => { if (!initial.topic) { toast(err.message, "error"); closeRef.current(); } });
  }, [initial, toast]);

  if (!s) return null;
  const manage = s.can_manage && s.status === "Scheduled";
  const canClose = s.follow_up && s.follow_up.status === "Pending" && (s.can_manage || user.role === "student");

  async function cancelSession() {
    const reason = window.prompt("Reason for cancelling (shown in the history):", "");
    if (reason === null) return;
    try {
      await api(`/counselling/sessions/${encodeURIComponent(s.id)}/cancel/`, { method: "POST", body: { reason, rev: s.rev } });
      toast("Session cancelled");
      onChanged();
    } catch (err) { toast(err.message, "error"); }
  }

  const footer = (manage || canClose) ? <>
    {manage && <><button className="btn btn-danger" onClick={cancelSession}>Cancel session</button><button className="btn btn-outline" onClick={() => onReschedule(s)}>Reschedule</button></>}
    {manage && s.needs_notes && <button className="btn btn-primary" onClick={() => onNotes(s)}>Record notes</button>}
    {canClose && <button className="btn btn-primary" onClick={() => onMark(s.id, s.rev)}>Mark follow-up done</button>}
  </> : <button className="btn btn-outline" onClick={onClose}>Close</button>;

  return (
    <Drawer title={s.topic} onClose={onClose} footer={footer}>
      <dl className="facts">
        <dt>When</dt><dd>{formatDateTime(s.scheduled_at)} – {formatTime(s.ends_at)}</dd>
        <dt>Mode</dt><dd>{s.mode} · {s.duration_minutes} min</dd>
        <dt>Student</dt><dd>{isStaff ? <Link to={`/students/${encodeURIComponent(s.student_id)}/`}>{s.student_name}</Link> : s.student_name}</dd>
        <dt>Counsellor</dt><dd>{s.counsellor_name}</dd>
        <dt>Status</dt><dd><SessionStatusBadge status={s.status} />{s.needs_notes && <> <span className="badge badge-warn">Needs notes</span></>}</dd>
      </dl>
      <div style={{ marginTop: "1rem" }}>{s.status !== "Scheduled" && <SessionCard s={s} isStaff={isStaff} />}</div>
      {manage && !s.needs_notes && <p className="small muted">Notes can be recorded once the session has started.</p>}
    </Drawer>
  );
}

function NotesDrawer({ s, onClose, onDone }) {
  const toast = useToast();
  const [v, setV] = useState(() => ({ summary: "", recommendations: "", action_items: "", has_follow: true, follow_action: "", follow_due: ymd(addDays(new Date(), 7)) }));
  const [errors, setErrors] = useState({});
  const bind = (k) => ({ value: v[k], onChange: (e) => setV({ ...v, [k]: e.target.value }) });

  async function save() {
    const body = { summary: v.summary.trim(), recommendations: lines(v.recommendations), action_items: lines(v.action_items),
      follow_up: v.has_follow ? { action: v.follow_action.trim(), due_date: v.follow_due } : null, rev: s.rev };
    const missing = {};
    if (!body.summary) missing.summary = "Summarise what was discussed.";
    if (body.follow_up && !body.follow_up.action) missing.follow_action = "Describe the follow-up, or untick it.";
    if (Object.keys(missing).length) { setErrors(missing); return; }
    try {
      await api(`/counselling/sessions/${encodeURIComponent(s.id)}/complete/`, { method: "POST", body });
      toast("Session recorded");
      onDone();
    } catch (err) {
      if (err.status === 400) {
        const e = fieldErrors(err.data);
        setErrors({ ...e, follow_action: e["follow_up.action"], follow_due: e["follow_up.due_date"] });
      }
      toast(err.message, "error");
    }
  }

  return (
    <Drawer title={`Session notes — ${s.student_name}`} onClose={onClose} footer={<>
      <button className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button className="btn btn-primary" onClick={save}>Save notes</button>
    </>}>
      <p className="small muted">{s.topic} · {formatDateTime(s.scheduled_at)}</p>
      <form noValidate onSubmit={(e) => { e.preventDefault(); save(); }}>
        <Field label="Discussion summary" error={errors.summary}><textarea maxLength={4000} required {...bind("summary")} /></Field>
        <Field label="Recommendations" error={errors.recommendations}><textarea placeholder="One per line" {...bind("recommendations")} /></Field>
        <Field label="Agreed actions" error={errors.action_items}><textarea placeholder="One per line" {...bind("action_items")} /></Field>
        <label className="checkbox" style={{ marginBottom: ".6rem" }}>
          <input type="checkbox" checked={v.has_follow} onChange={(e) => setV({ ...v, has_follow: e.target.checked })} /> Set a follow-up
        </label>
        {v.has_follow && (
          <div className="grid grid-2">
            <Field label="Follow-up action" className="span-2" error={errors.follow_action}><input maxLength={300} placeholder="e.g. Upload transcripts" {...bind("follow_action")} /></Field>
            <Field label="Due date" error={errors.follow_due}><input type="date" {...bind("follow_due")} /></Field>
          </div>
        )}
      </form>
    </Drawer>
  );
}

/** Schedule a new session, or reschedule `existing`. */
function ScheduleDrawer({ existing, user, students, defaultStudent, onClose, onDone }) {
  const toast = useToast();
  const [v, setV] = useState(() => {
    const start = existing ? new Date(existing.scheduled_at) : (() => { const d = new Date(); d.setDate(d.getDate() + 1); d.setHours(10, 0, 0, 0); return d; })();
    return {
      student_id: defaultStudent || "",
      scheduled_at: new Date(start.getTime() - start.getTimezoneOffset() * 60000).toISOString().slice(0, 16),
      duration_minutes: String(existing?.duration_minutes || 45),
      mode: existing?.mode || "Video call",
      topic: existing?.topic || "",
    };
  });
  const [errors, setErrors] = useState({});
  const bind = (k) => ({ value: v[k], onChange: (e) => setV({ ...v, [k]: e.target.value }) });
  const choices = students.filter((s) => user.role === "counsellor" || s.counsellor_id);

  async function save() {
    const when = v.scheduled_at ? new Date(v.scheduled_at) : null;
    const body = { scheduled_at: when ? when.toISOString() : "", duration_minutes: Number(v.duration_minutes), mode: v.mode, topic: v.topic.trim() };
    if (!existing) body.student_id = v.student_id;
    else body.rev = existing.rev;
    try {
      await api(existing ? `/counselling/sessions/${encodeURIComponent(existing.id)}/` : "/counselling/sessions/", { method: existing ? "PATCH" : "POST", body });
      toast(existing ? "Session rescheduled" : "Session scheduled");
      onDone(when);
    } catch (err) {
      if (err.status === 400) setErrors(fieldErrors(err.data));
      toast(err.message, "error");
    }
  }

  return (
    <Drawer title={existing ? "Reschedule session" : "Schedule a session"} onClose={onClose} footer={<>
      <button className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button className="btn btn-primary" onClick={save}>{existing ? "Save" : "Schedule"}</button>
    </>}>
      <form noValidate onSubmit={(e) => { e.preventDefault(); save(); }}>
        {existing ? <p className="muted">{existing.student_name}</p> : (
          <Field label="Student" error={errors.student_id} hint={user.role === "admin" ? "The session is booked with the student's counsellor." : undefined}>
            <select {...bind("student_id")}>
              <option value="">Select a student…</option>
              {choices.map((s) => <option key={s.id} value={s.id}>{s.full_name}{user.role === "admin" ? ` — ${s.counsellor_name || ""}` : ""}</option>)}
            </select>
          </Field>
        )}
        <div className="grid grid-2">
          <Field label="Date & time" error={errors.scheduled_at}><input type="datetime-local" {...bind("scheduled_at")} /></Field>
          <Field label="Duration" error={errors.duration_minutes}>
            <select {...bind("duration_minutes")}>{[30, 45, 60, 90].map((m) => <option key={m} value={String(m)}>{m} minutes</option>)}</select>
          </Field>
        </div>
        <Field label="Mode" error={errors.mode}><select {...bind("mode")}>{MODES.map((m) => <option key={m}>{m}</option>)}</select></Field>
        <Field label="Topic" error={errors.topic}><input maxLength={160} placeholder="e.g. University shortlisting" {...bind("topic")} /></Field>
      </form>
    </Drawer>
  );
}

export default function Counselling() {
  const { user } = useAuth();
  const toast = useToast();
  const [params] = useSearchParams();
  const isStaff = user.role !== "student";
  const [tab, setTab] = useState(TABS.some(([k]) => k === params.get("tab")) ? params.get("tab") : "calendar");
  const [studentId, setStudentId] = useState(params.get("student_id") || "");
  const [month, setMonth] = useState(() => firstOfMonth(new Date()));
  const [version, setVersion] = useState(0);
  const [students, setStudents] = useState([]);
  const [drawer, setDrawer] = useState(null);
  const refresh = () => setVersion((n) => n + 1);

  useEffect(() => {
    if (isStaff) api("/students/", { query: { page_size: 100 } }).then((d) => setStudents(d.results), (err) => toast(err.message, "error"));
  }, [isStaff, toast]);

  const pending = useLoad(() => api("/counselling/follow-ups/", { query: { student_id: studentId, status: "Pending" } }), [studentId, version]);

  function pickStudent(id) {
    setStudentId(id);
    window.history.replaceState(null, "", id ? `?student_id=${encodeURIComponent(id)}` : window.location.pathname);
  }

  async function markFollowUp(sessionId, rev) {
    try {
      await api(`/counselling/sessions/${encodeURIComponent(sessionId)}/follow-up/`, { method: "PATCH", body: { status: "Done", rev } });
      toast("Follow-up marked done");
      setDrawer(null);
      refresh();
    } catch (err) { toast(err.status === 409 ? "This session changed meanwhile. Reload and try again." : err.message, "error"); }
  }

  const openSession = (s) => setDrawer({ kind: "session", s });
  const closeDrawer = () => setDrawer(null);
  const changed = () => { setDrawer(null); refresh(); };
  const pendingCount = pending.data?.count || 0;

  return (
    <AppShell title="Counselling" crumb="Counselling">
      <div className="page-head">
        <div>
          <h1>{isStaff ? "Counselling" : "My counselling"}</h1>
          <p className="muted">{!isStaff ? "Your sessions with your counsellor, what was agreed, and what to do next."
            : user.role === "admin" ? "Every counselling session and follow-up across the agency." : "Your sessions, notes and follow-ups."}</p>
        </div>
        {isStaff && (
          <div className="toolbar">
            <select aria-label="Student" value={studentId} onChange={(e) => pickStudent(e.target.value)}>
              <option value="">{user.role === "admin" ? "All students" : "All my students"}</option>
              {students.map((s) => <option key={s.id} value={s.id}>{s.full_name}</option>)}
            </select>
            <button className="btn btn-primary" onClick={() => setDrawer({ kind: "schedule", existing: null })}>Schedule session</button>
          </div>
        )}
      </div>

      <div className="card">
        <div className="section-tabs" role="tablist" aria-label="Counselling views">
          {TABS.map(([key, label]) => (
            <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>
              {label}{key === "follow-ups" && pendingCount > 0 && <Fragment> <span className="badge">{pendingCount}</span></Fragment>}
            </button>
          ))}
        </div>
        {tab === "calendar" && <Calendar user={user} studentId={studentId} month={month} setMonth={setMonth} version={version} onOpen={openSession} />}
        {tab === "history" && <History studentId={studentId} version={version} isStaff={isStaff} onOpen={openSession} />}
        {tab === "follow-ups" && <FollowUps studentId={studentId} version={version} isStaff={isStaff} onOpen={openSession} onMark={markFollowUp} />}
      </div>

      {drawer?.kind === "session" && (
        <SessionDrawer initial={drawer.s} user={user} isStaff={isStaff} onClose={closeDrawer} onMark={markFollowUp} onChanged={changed}
          onNotes={(s) => setDrawer({ kind: "notes", s })} onReschedule={(s) => setDrawer({ kind: "schedule", existing: s })} />
      )}
      {drawer?.kind === "notes" && <NotesDrawer s={drawer.s} onClose={closeDrawer} onDone={changed} />}
      {drawer?.kind === "schedule" && (
        <ScheduleDrawer existing={drawer.existing} user={user} students={students} defaultStudent={studentId} onClose={closeDrawer}
          onDone={(when) => { if (when) setMonth(firstOfMonth(when)); changed(); }} />
      )}
    </AppShell>
  );
}
