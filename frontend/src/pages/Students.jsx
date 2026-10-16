/* Student roster: counsellors see their assigned students; administrators see everyone and assign counsellors. */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppShell from "../components/Shell";
import Drawer from "../components/Drawer";
import { useAuth } from "../components/auth";
import { useToast } from "../components/Toast";
import { ErrorAlert, Field, Pager, ProgressBar, StatusBadge } from "../components/ui";
import { api } from "../lib/api";
import { plural } from "../lib/format";
import { fieldErrors, saveErrorMessage, trimStrings, useForm } from "../lib/form";
import { useDebounced } from "../lib/useDebounced";
import { useLoad } from "../lib/useLoad";
import { useQueryState, useSessionText } from "../lib/useQueryState";
import { useSubmit } from "../lib/useSubmit";
import { ID_PATTERN } from "./Applications";

const counsellorLabel = (c) => `${c.name} — ${c.workload.assigned}/${c.workload.capacity}${c.region ? ` · ${c.region}` : ""}`;
const LIST_STATE = {
  status: { default: "", allowed: ["", "registered", "in_progress", "profile_complete", "ready"] },
  counsellor_id: { default: "", pattern: ID_PATTERN },
  unassigned: { default: false, type: "bool" },
  page: { default: 1, type: "page" },
};

function AssignDrawer({ student, counsellors, onClose, onDone }) {
  const toast = useToast();
  const current = student.counsellor_id || "";
  const [choice, setChoice] = useState(current);
  const [error, setError] = useState("");
  const [busy, run] = useSubmit();

  const submit = (counsellorId) => run(async () => {
    if (counsellorId !== null && !counsellorId) { setError("Choose a counsellor."); return; }
    try {
      const doc = await api(`/students/${encodeURIComponent(student.id)}/assign-counsellor/`, { method: "POST", body: { counsellor_id: counsellorId } });
      toast(counsellorId ? `${student.full_name} assigned to ${doc.counsellor.name}` : `${student.full_name} no longer has a counsellor`);
      onDone();
    } catch (err) {
      if (err.status === 400) setError(fieldErrors(err.data).counsellor_id || "");
      toast(saveErrorMessage(err), "error");
    }
  });

  return (
    <Drawer title={current ? "Reassign counsellor" : "Assign counsellor"} onClose={onClose} busy={busy} footer={<>
      {current && <button type="button" className="btn btn-danger" style={{ marginRight: "auto" }} onClick={() => submit(null)} disabled={busy}>Unassign</button>}
      <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button type="button" className="btn btn-primary" onClick={() => submit(choice)} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
    </>}>
      <p className="muted">Student: <b>{student.full_name}</b></p>
      <Field label="Counsellor" hint="Counsellors at capacity cannot be selected." error={error}>
        <select value={choice} onChange={(e) => setChoice(e.target.value)}>
          <option value="">Select…</option>
          {counsellors.map((c) => (
            <option key={c.id} value={c.id} disabled={c.workload.available === 0 && c.id !== current}>
              {counsellorLabel(c)}{c.workload.available === 0 ? " (full)" : ""}
            </option>
          ))}
        </select>
      </Field>
      {!counsellors.length && <div className="alert alert-warn">No active counsellors. <Link to="/counsellors/?new=1">Create one first</Link>.</div>}
    </Drawer>
  );
}

function CreateDrawer({ counsellors, onClose, onDone }) {
  const toast = useToast();
  const form = useForm({ counsellor_id: "" });
  const { bind, errors } = form;
  const [busy, run] = useSubmit();

  const save = () => run(async () => {
    const body = trimStrings(form.values);
    if (!body.counsellor_id) delete body.counsellor_id;
    try {
      const doc = await api("/students/", { method: "POST", body });
      toast(`${doc.full_name}'s account has been created`);
      onDone();
    } catch (err) {
      if (err.status === 400) form.showErrors(err.data);
      toast(saveErrorMessage(err), "error");
    }
  });

  return (
    <Drawer title="Add student" onClose={onClose} busy={busy} footer={<>
      <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Creating…" : "Create student"}</button>
    </>}>
      <form noValidate ref={form.ref} onSubmit={(e) => { e.preventDefault(); save(); }}>
        <div className="grid grid-2">
          <Field label="First name" error={errors.first_name}><input required {...bind("first_name")} /></Field>
          <Field label="Last name" error={errors.last_name}><input required {...bind("last_name")} /></Field>
          <Field label="Email" className="span-2" error={errors.email}><input type="email" required {...bind("email")} /></Field>
          <Field label="Initial password" className="span-2" hint="At least 8 characters, with letters and numbers. Share it with the student securely; they can change it from the account menu (Change password) after signing in." error={errors.password}>
            <input type="text" required {...bind("password")} />
          </Field>
          <Field label="Counsellor (optional)" className="span-2" error={errors.counsellor_id}>
            <select {...bind("counsellor_id")}>
              <option value="">Assign later</option>
              {counsellors.filter((c) => c.workload.available > 0).map((c) => <option key={c.id} value={c.id}>{c.name} — {c.workload.assigned}/{c.workload.capacity}</option>)}
            </select>
          </Field>
        </div>
      </form>
    </Drawer>
  );
}

export default function Students() {
  const { user } = useAuth();
  const toast = useToast();
  const isAdmin = user.role === "admin";

  // Filters and page live in the URL; the name search stays out of it (it may hold a student's name).
  const [state, update] = useQueryState(LIST_STATE);
  const { status, page } = state;
  const counsellor = state.unassigned ? "__none__" : state.counsellor_id;
  const [search, setSearch] = useSessionText("students");
  const q = useDebounced(search.trim());
  const [counsellors, setCounsellors] = useState([]);
  const [drawer, setDrawer] = useState(null);
  const [lastQ, setLastQ] = useState(q);

  useEffect(() => { if (q !== lastQ) { setLastQ(q); update({ page: 1 }); } }, [q]); // a new search starts at page 1
  const pickCounsellor = (v) => update({ unassigned: v === "__none__", counsellor_id: v === "__none__" ? "" : v, page: 1 });

  const loadCounsellors = useCallback(() => (isAdmin ? api("/counsellors/options/").then(setCounsellors) : Promise.resolve()), [isAdmin]);
  useEffect(() => { loadCounsellors().catch((err) => toast(err.message, "error")); }, [loadCounsellors, toast]);

  const { data, error, reload } = useLoad(() => {
    const query = { page, q, status };
    if (counsellor === "__none__") query.unassigned = "true";
    else if (counsellor) query.counsellor_id = counsellor;
    return api("/students/", { query });
  }, [page, q, status, counsellor]);

  const done = () => { setDrawer(null); loadCounsellors(); reload(); };
  const cols = isAdmin ? 6 : 5;
  const filtered = q || status || counsellor;

  return (
    <AppShell title="Students" crumb="Students">
      <div className="page-head">
        <div>
          <h1>{isAdmin ? "Students" : "My students"}</h1>
          <p className="muted">{isAdmin ? "Every registered student. Assign or reassign counsellors from here." : "Students assigned to you. Open a profile to review or update it."}</p>
        </div>
        <div className="toolbar">{isAdmin && <button type="button" className="btn btn-primary" onClick={() => setDrawer({ type: "create" })}>Add student</button>}</div>
      </div>

      <div className="card">
        <div className="card-head">
          <div className="toolbar">
            <input type="search" placeholder="Search name or email…" aria-label="Search students" value={search} onChange={(e) => setSearch(e.target.value)} />
            <select aria-label="Filter by status" value={status} onChange={(e) => update({ status: e.target.value, page: 1 })}>
              <option value="">All statuses</option><option value="registered">Registered</option><option value="in_progress">In progress</option>
              <option value="profile_complete">Profile complete</option><option value="ready">Ready</option>
            </select>
            {isAdmin && (
              <select aria-label="Filter by counsellor" value={counsellor} onChange={(e) => pickCounsellor(e.target.value)}>
                <option value="">All counsellors</option><option value="__none__">Unassigned only</option>
                {counsellors.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            )}
          </div>
          <span className="small muted" aria-live="polite">{data ? plural(data.count, "student") : ""}</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Student</th><th>Targets</th><th>Readiness</th><th>Status</th>{isAdmin && <th>Counsellor</th>}<th /></tr></thead>
            <tbody>
              {error ? <tr><td colSpan={cols}><ErrorAlert error={error} onRetry={reload} /></td></tr>
                : !data ? <tr><td colSpan={cols} className="loading" role="status">Loading students…</td></tr>
                : !data.results.length ? <tr><td colSpan={cols} className="empty">{filtered ? "No students match these filters." : isAdmin ? "No students yet." : "No students are assigned to you yet."}</td></tr>
                : data.results.map((s) => (
                  <tr key={s.id}>
                    <td><Link className="name" to={`/students/${encodeURIComponent(s.id)}/`}>{s.full_name || "(no name)"}</Link><div className="small muted">{s.email}</div></td>
                    <td>{s.countries.join(", ") || "—"}<div className="small muted">{[s.degree_level, s.intake].filter(Boolean).join(" · ")}</div></td>
                    <td style={{ minWidth: 140 }}><ProgressBar pct={s.profile_completion} /></td>
                    <td><StatusBadge status={s.onboarding_status} /></td>
                    {isAdmin && <td>{s.counsellor_id ? s.counsellor_name || "Unknown counsellor" : <span className="badge badge-warn">Unassigned</span>}</td>}
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {isAdmin && <button type="button" className="btn btn-outline btn-sm" onClick={() => setDrawer({ type: "assign", student: s })} aria-label={`${s.counsellor_id ? "Reassign" : "Assign"} a counsellor for ${s.full_name}`}>{s.counsellor_id ? "Reassign" : "Assign"}</button>}{" "}
                      <Link className="btn btn-outline btn-sm" to={`/students/${encodeURIComponent(s.id)}/`} aria-label={`Open ${s.full_name}'s profile`}>Open</Link>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
        <Pager data={data} onPage={(p) => update({ page: p })} noun="student" />
      </div>

      {drawer?.type === "assign" && <AssignDrawer student={drawer.student} counsellors={counsellors} onClose={() => setDrawer(null)} onDone={done} />}
      {drawer?.type === "create" && <CreateDrawer counsellors={counsellors} onClose={() => setDrawer(null)} onDone={done} />}
    </AppShell>
  );
}
