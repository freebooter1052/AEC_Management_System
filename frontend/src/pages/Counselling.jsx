/* Counselling (SRS 4.7): calendar, session history and follow-ups; counsellors schedule and record sessions. */
import { useState } from "react";
import { Link } from "react-router-dom";
import AppShell from "../components/Shell";
import { ConfirmDialog } from "../components/Dialog";
import Drawer from "../components/Drawer";
import StudentPicker from "../components/StudentPicker";
import { TabList, tabPanel } from "../components/Tabs";
import { useAuth } from "../components/auth";
import { useToast } from "../components/Toast";
import { ErrorAlert, Field, Loading, Pager, SessionStatusBadge, recordError } from "../components/ui";
import { api } from "../lib/api";
import { formatDate, formatDateTime, formatTime, parseDate, plural, ymd } from "../lib/format";
import { fieldErrors, saveErrorMessage } from "../lib/form";
import { useLoad } from "../lib/useLoad";
import { useQueryState } from "../lib/useQueryState";
import { useSubmit } from "../lib/useSubmit";
import { ID_PATTERN } from "./Applications";

const MODES = ["Video call", "In person", "Phone"];
const TABS = [["calendar", "Calendar"], ["history", "History"], ["follow-ups", "Follow-ups"]];
const FOLLOW_BADGE = { overdue: ["Overdue", "badge badge-err"], due_today: ["Due today", "badge badge-warn"], pending: ["Pending", "badge badge-info"], done: ["Done", "badge badge-ok"] };
const PER_DAY = 3; // calendar entries shown in a day cell before "+N more"
const LIST_STATE = {
  tab: { default: "calendar", allowed: TABS.map(([k]) => k) },
  student_id: { default: "", pattern: ID_PATTERN },
  month: { default: "", pattern: /^\d{4}-(0[1-9]|1[0-2])$/ },
  history_status: { default: "", allowed: ["", "Scheduled", "Completed", "Cancelled"] },
  history_page: { default: 1, type: "page" },
  follow_status: { default: "Pending", allowed: ["Pending", "Done", "all"] },
};

const firstOfMonth = (d) => new Date(d.getFullYear(), d.getMonth(), 1);
const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const monthKey = (d) => ymd(d).slice(0, 7);
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
        {formatDateTime(s.scheduled_at)} · {s.duration_minutes} min · {s.mode} · {isStaff ? `${s.student_name} with ${s.counsellor_name || "a former counsellor"}` : `with ${s.counsellor_name || "your counsellor"}`}
      </div>
      {s.summary && <><div className="label-sm">Summary</div><p style={{ margin: ".2rem 0 .4rem", whiteSpace: "pre-wrap" }}>{s.summary}</p></>}
      {list("Recommendations", s.recommendations)}
      {list("Agreed actions", s.action_items)}
      {s.status === "Cancelled" && s.cancel_reason && <p className="small muted">Cancelled: {s.cancel_reason}</p>}
      {f && <div className="follow-box"><span><b>Follow-up:</b> {f.action} · due {formatDate(f.due_date)}</span><FollowBadge state={s.follow_up_state} /></div>}
      {onOpen && (
        <div className="toolbar" style={{ marginTop: ".7rem" }}>
          <button type="button" className="btn btn-outline btn-sm" onClick={() => onOpen(s)}>{s.can_manage && s.status === "Scheduled" ? "Manage" : "Details"}<span className="sr-only">: {s.topic}</span></button>
        </div>
      )}
    </article>
  );
}

/** Calendar entries (sessions and follow-ups) for one day, as buttons. */
function entriesByDay(data, who) {
  const byDay = {};
  const push = (key, item) => (byDay[key] ||= []).push(item);
  (data?.sessions || []).forEach((s) => push(ymd(parseDate(s.scheduled_at)), {
    key: s.id, open: s, cls: `event ${s.needs_notes ? "notes" : s.status}`,
    text: <>{formatTime(s.scheduled_at)} <span className="who">{who(s)}</span></>,
    label: `${formatTime(s.scheduled_at)} ${s.topic} with ${who(s)}${s.status !== "Scheduled" ? ` (${s.status.toLowerCase()})` : s.needs_notes ? " (needs notes)" : ""}`,
  }));
  (data?.follow_ups || []).forEach((f, i) => push(f.due_date, {
    key: `f${i}-${f.session_id}`, open: { id: f.session_id }, cls: `event follow ${f.state}`,
    text: <><span aria-hidden="true">⚑</span> <span className="who">{f.action}</span></>,
    label: `Follow-up${f.state === "overdue" ? " (overdue)" : f.state === "done" ? " (done)" : ""}: ${f.action}`,
  }));
  return byDay;
}

const EventButton = ({ e, onOpen }) => (
  <button type="button" className={e.cls} title={e.label} aria-label={e.label} onClick={() => onOpen(e.open)}>{e.text}</button>
);

function Calendar({ user, studentId, month, setMonth, version, onOpen }) {
  const gridStart = addDays(month, -((month.getDay() + 6) % 7)); // Monday on or before the 1st
  const { data, error, loading, reload } = useLoad(
    () => api("/counselling/calendar/", { query: { start: ymd(gridStart), end: ymd(addDays(gridStart, 42)), student_id: studentId } }),
    [month.getTime(), studentId, version],
  );
  const [day, setDay] = useState(null);

  const who = (s) => (user.role === "student" ? s.counsellor_name || "your counsellor" : s.student_name);
  const byDay = entriesByDay(data, who);
  const today = ymd(new Date());
  const inMonth = Object.keys(byDay).filter((k) => k.startsWith(monthKey(month))).reduce((n, k) => n + byDay[k].length, 0);
  const title = month.toLocaleDateString("en-GB", { month: "long", year: "numeric" });

  return (
    <section aria-labelledby="cal-title">
      <div className="cal-head">
        <h2 id="cal-title" aria-live="polite">{title}</h2>
        <div className="toolbar">
          <button type="button" className="btn btn-outline btn-sm" aria-label="Previous month" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}>‹ Prev</button>
          <button type="button" className="btn btn-outline btn-sm" onClick={() => setMonth(firstOfMonth(new Date()))}>Today</button>
          <button type="button" className="btn btn-outline btn-sm" aria-label="Next month" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}>Next ›</button>
        </div>
      </div>
      {error && <ErrorAlert error={error} onRetry={reload}>Could not load the calendar. {error.message}</ErrorAlert>}
      <div className={`calendar${loading ? " is-loading" : ""}`} aria-busy={loading || undefined}>
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <div className="dow" key={d} aria-hidden="true">{d}</div>)}
        {Array.from({ length: 42 }, (_, i) => {
          const d = addDays(gridStart, i);
          const key = ymd(d);
          const items = byDay[key] || [];
          const hidden = items.length > PER_DAY ? items.length - (PER_DAY - 1) : 0;
          const shown = hidden ? items.slice(0, PER_DAY - 1) : items;
          return (
            <div key={key} className={`day ${d.getMonth() !== month.getMonth() ? "other" : ""} ${key === today ? "today" : ""}`}>
              <span className="num"><span className="sr-only">{d.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })}</span><span aria-hidden="true">{d.getDate()}</span></span>
              {shown.map((e) => <EventButton key={e.key} e={e} onOpen={onOpen} />)}
              {hidden > 0 && (
                <button type="button" className="event more" onClick={() => setDay({ key, date: d, items })}
                  aria-label={`${hidden} more on ${d.toLocaleDateString("en-GB", { day: "numeric", month: "long" })} — show all ${items.length}`}>+{hidden} more</button>
              )}
            </div>
          );
        })}
      </div>
      {loading && !data && <Loading text="Loading the calendar…" />}
      {!loading && !error && data && inMonth === 0 && <p className="empty small">No sessions or follow-ups in {title}.</p>}
      <div className="legend">
        <span style={{ "--c": "var(--info)" }}>Scheduled</span><span style={{ "--c": "var(--warn)" }}>Needs notes</span><span style={{ "--c": "var(--ok)" }}>Completed</span>
        <span style={{ "--c": "#94a3b8" }}>Cancelled</span><span style={{ "--c": "var(--primary)" }}>Follow-up due</span><span style={{ "--c": "var(--err)" }}>Follow-up overdue</span>
      </div>
      {day && (
        <Drawer title={day.date.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })} onClose={() => setDay(null)}>
          <p className="small muted">{plural(day.items.length, "entry", "entries")} on this day.</p>
          <ul className="day-list">
            {day.items.map((e) => <li key={e.key}><EventButton e={e} onOpen={(s) => { setDay(null); onOpen(s); }} /></li>)}
          </ul>
        </Drawer>
      )}
    </section>
  );
}

function History({ studentId, version, isStaff, onOpen, status, page, update }) {
  const { data, error, loading, reload } = useLoad(
    () => api("/counselling/sessions/", { query: { student_id: studentId, status, page, page_size: 10 } }), [studentId, status, page, version]);

  return (
    <section>
      <div className="toolbar" style={{ marginBottom: "1rem" }}>
        <select aria-label="Session status" value={status} onChange={(e) => update({ history_status: e.target.value, history_page: 1 })}>
          <option value="">All sessions</option><option>Scheduled</option><option>Completed</option><option>Cancelled</option>
        </select>
      </div>
      {error ? <ErrorAlert error={error} onRetry={reload}>Could not load the session history. {error.message}</ErrorAlert>
        : !data ? <Loading text="Loading sessions…" />
        : data.results.length
          ? <div aria-busy={loading || undefined}>{data.results.map((s) => <SessionCard key={s.id} s={s} isStaff={isStaff} onOpen={onOpen} />)}</div>
          : <p className="empty">{status ? `No ${status.toLowerCase()} sessions.` : "No counselling sessions yet."}</p>}
      <Pager data={data} onPage={(p) => update({ history_page: p })} noun="session" />
    </section>
  );
}

function FollowUps({ studentId, version, isStaff, onOpen, onMark, marking, status, update }) {
  const { data, error, loading, reload } = useLoad(
    () => api("/counselling/follow-ups/", { query: { student_id: studentId, status: status === "all" ? "" : status } }), [studentId, status, version]);
  const cols = isStaff ? 6 : 5;

  return (
    <section>
      <div className="toolbar" style={{ marginBottom: "1rem" }}>
        <select aria-label="Follow-up status" value={status} onChange={(e) => update({ follow_status: e.target.value })}>
          <option value="Pending">Pending</option><option value="Done">Done</option><option value="all">All</option>
        </select>
      </div>
      {error ? <ErrorAlert error={error} onRetry={reload}>Could not load the follow-ups. {error.message}</ErrorAlert> : (
        <div className="table-wrap"><table aria-busy={loading || undefined}>
          <thead><tr><th>Due</th><th>Action</th>{isStaff && <th>Student</th>}<th>From session</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>
            {!data ? <tr><td colSpan={cols} className="loading" role="status">Loading follow-ups…</td></tr>
              : data.results.length ? data.results.map((f, i) => (
                <tr key={`${f.session_id}-${i}`}>
                  <td style={{ whiteSpace: "nowrap" }}>{formatDate(f.due_date)}</td>
                  <td className="name">{f.action}</td>
                  {isStaff && <td>{f.student_name}</td>}
                  <td><button type="button" className="link-btn" onClick={() => onOpen({ id: f.session_id })}>{f.topic}</button><div className="small muted">{formatDate(f.session_date)}</div></td>
                  <td><FollowBadge state={f.state} /></td>
                  <td style={{ textAlign: "right" }}>{f.status === "Pending" && (
                    <button type="button" className="btn btn-outline btn-sm" disabled={marking} onClick={() => onMark(f.session_id, f.rev)} aria-label={`Mark "${f.action}" done`}>Mark done</button>
                  )}</td>
                </tr>
              )) : <tr><td colSpan={cols} className="empty">No {status === "all" ? "" : `${status.toLowerCase()} `}follow-ups.</td></tr>}
          </tbody>
        </table></div>
      )}
    </section>
  );
}

function CancelDialog({ s, onClose, onDone }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, run] = useSubmit();
  const confirm = () => run(async () => {
    setError("");
    try {
      await api(`/counselling/sessions/${encodeURIComponent(s.id)}/cancel/`, { method: "POST", body: { reason: reason.trim(), rev: s.rev } });
      toast("Session cancelled");
      onDone();
    } catch (err) {
      setError(err.status === 409 ? "This session changed meanwhile. Close this dialog and open the session again." : saveErrorMessage(err));
    }
  });
  return (
    <ConfirmDialog title="Cancel this session?" danger confirmLabel="Cancel session" cancelLabel="Keep session" busyLabel="Cancelling…"
      busy={busy} error={error} initialFocus="field" onConfirm={confirm} onCancel={onClose}>
      <p><b>{s.topic}</b> with {s.student_name} on {formatDateTime(s.scheduled_at)} will be marked as cancelled. It stays in the history.</p>
      <div className="field">
        <label htmlFor="cancel-reason">Reason (optional, shown in the history)</label>
        <textarea id="cancel-reason" maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
    </ConfirmDialog>
  );
}

function SessionDrawer({ initial, user, isStaff, onClose, onMark, marking, onNotes, onReschedule, onChanged }) {
  const { data, error, reload } = useLoad(() => api(`/counselling/sessions/${encodeURIComponent(initial.id)}/`), [initial.id]);
  const [cancelling, setCancelling] = useState(false);
  const s = data || (initial.topic ? initial : null);

  if (!s) {
    return (
      <Drawer title={error ? "Session unavailable" : "Loading session…"} onClose={onClose} busy={!error}
        footer={<button type="button" className="btn btn-outline" onClick={onClose}>Close</button>}>
        {error ? <ErrorAlert error={error} onRetry={error.status === 403 || error.status === 404 ? undefined : reload}>{recordError(error, "session")}</ErrorAlert>
          : <Loading text="Loading session details…" />}
      </Drawer>
    );
  }
  const manage = s.can_manage && s.status === "Scheduled";
  const canClose = s.follow_up && s.follow_up.status === "Pending" && (s.can_manage || user.role === "student");

  const footer = (manage || canClose) ? <>
    {manage && <><button type="button" className="btn btn-danger" style={{ marginRight: "auto" }} onClick={() => setCancelling(true)}>Cancel session</button>
      <button type="button" className="btn btn-outline" onClick={() => onReschedule(s)}>Reschedule</button></>}
    {manage && s.needs_notes && <button type="button" className="btn btn-primary" onClick={() => onNotes(s)}>Record notes</button>}
    {canClose && <button type="button" className="btn btn-primary" disabled={marking} onClick={() => onMark(s.id, s.rev)}>{marking ? "Saving…" : "Mark follow-up done"}</button>}
  </> : <button type="button" className="btn btn-outline" onClick={onClose}>Close</button>;

  return (
    <Drawer title={s.topic} onClose={onClose} footer={footer}>
      {error && data === null && <ErrorAlert error={error} onRetry={reload}>Showing saved details; the latest version could not be loaded. {error.message}</ErrorAlert>}
      <dl className="facts">
        <dt>When</dt><dd>{formatDateTime(s.scheduled_at)} – {formatTime(s.ends_at)}</dd>
        <dt>Mode</dt><dd>{s.mode} · {s.duration_minutes} min</dd>
        <dt>Student</dt><dd>{isStaff ? <Link to={`/students/${encodeURIComponent(s.student_id)}/`}>{s.student_name}</Link> : s.student_name}</dd>
        <dt>Counsellor</dt><dd>{s.counsellor_name || "No longer with the agency"}</dd>
        <dt>Status</dt><dd><SessionStatusBadge status={s.status} />{s.needs_notes && <> <span className="badge badge-warn">Needs notes</span></>}</dd>
      </dl>
      <div style={{ marginTop: "1rem" }}>{s.status !== "Scheduled" && <SessionCard s={s} isStaff={isStaff} />}</div>
      {manage && !s.needs_notes && <p className="small muted">Notes can be recorded once the session has started.</p>}
      {cancelling && <CancelDialog s={s} onClose={() => setCancelling(false)} onDone={() => { setCancelling(false); onChanged(); }} />}
    </Drawer>
  );
}

function NotesDrawer({ s, onClose, onDone }) {
  const toast = useToast();
  const [v, setV] = useState(() => ({ summary: "", recommendations: "", action_items: "", has_follow: true, follow_action: "", follow_due: ymd(addDays(new Date(), 7)) }));
  const [errors, setErrors] = useState({});
  const [busy, run] = useSubmit();
  const bind = (k) => ({ value: v[k], onChange: (e) => setV({ ...v, [k]: e.target.value }) });

  const save = () => run(async () => {
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
      toast(err.status === 409 ? "This session changed meanwhile. Close this panel and open the session again." : saveErrorMessage(err), "error");
    }
  });

  return (
    <Drawer title={`Session notes — ${s.student_name}`} onClose={onClose} busy={busy} footer={<>
      <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save notes"}</button>
    </>}>
      <p className="small muted">{s.topic} · {formatDateTime(s.scheduled_at)}</p>
      <form noValidate onSubmit={(e) => { e.preventDefault(); save(); }}>
        <Field label="Discussion summary" error={errors.summary}><textarea maxLength={4000} required {...bind("summary")} /></Field>
        <Field label="Recommendations" hint="One per line." error={errors.recommendations}><textarea {...bind("recommendations")} /></Field>
        <Field label="Agreed actions" hint="One per line." error={errors.action_items}><textarea {...bind("action_items")} /></Field>
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
function ScheduleDrawer({ existing, user, defaultStudent, onClose, onDone }) {
  const toast = useToast();
  const [v, setV] = useState(() => {
    const start = existing ? parseDate(existing.scheduled_at) : (() => { const d = new Date(); d.setDate(d.getDate() + 1); d.setHours(10, 0, 0, 0); return d; })();
    return {
      student_id: defaultStudent || "",
      scheduled_at: new Date(start.getTime() - start.getTimezoneOffset() * 60000).toISOString().slice(0, 16),
      duration_minutes: String(existing?.duration_minutes || 45),
      mode: existing?.mode || "Video call",
      topic: existing?.topic || "",
    };
  });
  const [errors, setErrors] = useState({});
  const [busy, run] = useSubmit();
  const bind = (k) => ({ value: v[k], onChange: (e) => setV({ ...v, [k]: e.target.value }) });
  // An administrator books with the student's counsellor, so students without one cannot be chosen.
  const optionState = user.role === "admin" ? (s) => (s.counsellor_id ? { hint: `with ${s.counsellor_name || "their counsellor"}` } : { disabled: true, hint: "No counsellor assigned yet" }) : undefined;

  const save = () => run(async () => {
    const when = v.scheduled_at ? new Date(v.scheduled_at) : null;
    const missing = {};
    if (!existing && !v.student_id) missing.student_id = "Choose a student.";
    if (!when || isNaN(when)) missing.scheduled_at = "Choose a date and time.";
    if (!v.topic.trim()) missing.topic = "Enter a topic for the session.";
    if (Object.keys(missing).length) { setErrors(missing); return; }
    const body = { scheduled_at: when.toISOString(), duration_minutes: Number(v.duration_minutes), mode: v.mode, topic: v.topic.trim() };
    if (!existing) body.student_id = v.student_id;
    else body.rev = existing.rev;
    try {
      await api(existing ? `/counselling/sessions/${encodeURIComponent(existing.id)}/` : "/counselling/sessions/", { method: existing ? "PATCH" : "POST", body });
      toast(existing ? "Session rescheduled" : "Session scheduled");
      onDone(when);
    } catch (err) {
      if (err.status === 400) setErrors(fieldErrors(err.data));
      toast(err.status === 409 ? "This session changed meanwhile. Close this panel and open the session again." : saveErrorMessage(err), "error");
    }
  });

  return (
    <Drawer title={existing ? "Reschedule session" : "Schedule a session"} onClose={onClose} busy={busy} footer={<>
      <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : existing ? "Save" : "Schedule"}</button>
    </>}>
      <form noValidate onSubmit={(e) => { e.preventDefault(); save(); }}>
        {existing ? <p className="muted">{existing.student_name}</p> : (
          <Field label="Student" error={errors.student_id} hint={user.role === "admin" ? "The session is booked with the student's counsellor." : undefined}>
            <StudentPicker value={v.student_id} optionState={optionState} onChange={(id) => setV((s) => ({ ...s, student_id: id }))} />
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
  const isStaff = user.role !== "student";
  const [state, update] = useQueryState(LIST_STATE);
  const { tab } = state;
  const studentId = isStaff ? state.student_id : "";
  const month = state.month ? new Date(Number(state.month.slice(0, 4)), Number(state.month.slice(5)) - 1, 1) : firstOfMonth(new Date());
  const setMonth = (d) => update({ month: monthKey(d) === monthKey(new Date()) ? "" : monthKey(d) });
  const [version, setVersion] = useState(0);
  const [drawer, setDrawer] = useState(null);
  const [marking, runMark] = useSubmit();
  const refresh = () => setVersion((n) => n + 1);

  const pending = useLoad(() => api("/counselling/follow-ups/", { query: { student_id: studentId, status: "Pending" } }), [studentId, version]);

  const markFollowUp = (sessionId, rev) => runMark(async () => {
    try {
      await api(`/counselling/sessions/${encodeURIComponent(sessionId)}/follow-up/`, { method: "PATCH", body: { status: "Done", rev } });
      toast("Follow-up marked done");
      setDrawer(null);
      refresh();
    } catch (err) {
      toast(err.status === 409 ? "This session changed meanwhile, so the list has been refreshed. Try again." : err.message, "error");
      if (err.status === 409) refresh();
    }
  });

  const openSession = (s) => setDrawer({ kind: "session", s });
  const closeDrawer = () => setDrawer(null);
  const changed = () => { setDrawer(null); refresh(); };
  const pendingCount = pending.data?.count || 0;
  const tabs = TABS.map(([key, label]) => [key, key === "follow-ups" && pendingCount > 0
    ? <>{label} <span className="badge" aria-label={`${pendingCount} pending`}>{pendingCount}</span></> : label]);

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
            <div className="toolbar-picker">
              <StudentPicker ariaLabel="Show sessions for" allLabel={user.role === "admin" ? "All students" : "All my students"} value={studentId}
                onChange={(id) => update({ student_id: id, history_page: 1 })} />
            </div>
            <button type="button" className="btn btn-primary" onClick={() => setDrawer({ kind: "schedule", existing: null })}>Schedule session</button>
          </div>
        )}
      </div>

      <div className="card">
        <TabList id="counselling" label="Counselling views" tabs={tabs} selected={tab} onSelect={(key) => update({ tab: key })} />
        <div {...tabPanel("counselling", tab, tab)}>
          {tab === "calendar" && <Calendar user={user} studentId={studentId} month={month} setMonth={setMonth} version={version} onOpen={openSession} />}
          {tab === "history" && <History studentId={studentId} version={version} isStaff={isStaff} onOpen={openSession}
            status={state.history_status} page={state.history_page} update={update} />}
          {tab === "follow-ups" && <FollowUps studentId={studentId} version={version} isStaff={isStaff} onOpen={openSession} onMark={markFollowUp}
            marking={marking} status={state.follow_status} update={update} />}
        </div>
      </div>

      {drawer?.kind === "session" && (
        <SessionDrawer initial={drawer.s} user={user} isStaff={isStaff} onClose={closeDrawer} onMark={markFollowUp} marking={marking} onChanged={changed}
          onNotes={(s) => setDrawer({ kind: "notes", s })} onReschedule={(s) => setDrawer({ kind: "schedule", existing: s })} />
      )}
      {drawer?.kind === "notes" && <NotesDrawer s={drawer.s} onClose={closeDrawer} onDone={changed} />}
      {drawer?.kind === "schedule" && (
        <ScheduleDrawer existing={drawer.existing} user={user} defaultStudent={studentId} onClose={closeDrawer}
          onDone={(when) => { if (when) setMonth(firstOfMonth(when)); changed(); }} />
      )}
    </AppShell>
  );
}
