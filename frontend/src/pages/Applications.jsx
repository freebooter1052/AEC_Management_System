/* Application workspace (SRS 4.5): pipeline, deadlines and creating applications from the catalogue. */
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import AppShell from "../components/Shell";
import Drawer from "../components/Drawer";
import { useAuth } from "../components/auth";
import { useToast } from "../components/Toast";
import StudentPicker from "../components/StudentPicker";
import { AppStatusBadge, DeadlineBadge, ErrorAlert, Field, Pager, appStatusLabel } from "../components/ui";
import { api } from "../lib/api";
import { formatDate, plural } from "../lib/format";
import { saveErrorMessage, useForm } from "../lib/form";
import { useDebounced } from "../lib/useDebounced";
import { useLoad } from "../lib/useLoad";
import { useQueryState } from "../lib/useQueryState";
import { useSubmit } from "../lib/useSubmit";

export const STATUSES = ["Planned", "Shortlisted", "Documents Pending", "Submitted", "Under Review", "Offer Received", "Rejected", "Withdrawn", "Completed"];
export const ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;
const LIST_STATE = {
  q: { default: "" },
  status: { default: "", allowed: ["", ...STATUSES] },
  student_id: { default: "", pattern: ID_PATTERN },
  sort: { default: "", allowed: ["", "deadline"] },
  open: { default: false, type: "bool" },
  page: { default: 1, type: "page" },
};
const OPEN_HINT = "The application deadline defaults to the intake deadline.";
const CLOSED_HINT = "This intake's deadline has passed. Enter the university's own later deadline, or choose another intake.";

function CreateDrawer({ isStudent, prefill, onClose }) {
  const toast = useToast();
  const navigate = useNavigate();
  const form = useForm({ student_id: prefill.student_id || "", university_id: "", course_id: "", intake_id: "", deadline: "", tier: "", notes: "" });
  const { bind, errors, set, values } = form;
  const [intakes, setIntakes] = useState([]);
  const [uniSearch, setUniSearch] = useState("");
  const uniQ = useDebounced(uniSearch.trim());
  const [unis, setUnis] = useState([]);
  const [pinned, setPinned] = useState(null);
  const [courses, setCourses] = useState(null);
  const [hint, setHint] = useState(OPEN_HINT);
  const [busy, run] = useSubmit();

  function pickIntake(id, list = intakes) {
    const i = list.find((x) => x.id === id);
    set("intake_id", id);
    set("deadline", i && i.is_open ? i.application_deadline || "" : "");
    setHint(i && !i.is_open ? CLOSED_HINT : OPEN_HINT);
  }

  async function loadCourses(universityId, selected = "") {
    setCourses("loading");
    set("university_id", universityId);
    set("course_id", "");
    try {
      const u = await api(`/universities/${encodeURIComponent(universityId)}/`);
      setPinned({ id: u.id, name: u.name, country: u.country });
      const sorted = [...u.courses].sort((a, b) => (a.title || "").localeCompare(b.title || ""));
      setCourses(sorted);
      set("course_id", sorted.some((c) => c.id === selected) ? selected : "");
    } catch (err) { setCourses([]); toast(err.message, "error"); }
  }

  useEffect(() => {
    api("/intakes/").then((list) => {
      setIntakes(list);
      const firstOpen = list.find((i) => i.is_open);
      if (firstOpen) pickIntake(firstOpen.id, list);
    }, (err) => toast(err.message, "error"));
    if (prefill.university_id) loadCourses(prefill.university_id, prefill.course_id);
  }, []); // once, when the drawer opens

  useEffect(() => {
    api("/universities/", { query: { q: uniQ, page_size: 30, sort: uniQ ? "name" : "rank" } }).then((d) => setUnis(d.results), (err) => toast(err.message, "error"));
  }, [uniQ, toast]);

  const save = () => run(async () => {
    const body = { ...values };
    delete body.university_id;
    if (!body.deadline) delete body.deadline;
    if (isStudent) delete body.student_id;
    const missing = {};
    if (!isStudent && !body.student_id) missing.student_id = ["Choose a student."];
    if (!body.course_id) missing.course_id = ["Choose a course."];
    if (!body.intake_id) missing.intake_id = ["Choose an intake."];
    if (Object.keys(missing).length) { form.showErrors(missing); return; }
    try {
      const app = await api("/applications/", { method: "POST", body });
      toast("Application created");
      navigate(`/applications/${encodeURIComponent(app.id)}/`);
    } catch (err) {
      if (err.status === 400) form.showErrors(err.data);
      toast(saveErrorMessage(err), "error");
    }
  });

  const uniOptions = pinned && !unis.some((u) => u.id === pinned.id) ? [pinned, ...unis] : unis;

  return (
    <Drawer title="New application" onClose={onClose} busy={busy} footer={<>
      <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Creating…" : "Create application"}</button>
    </>}>
      <form noValidate ref={form.ref} onSubmit={(e) => { e.preventDefault(); save(); }}>
        {!isStudent && (
          <Field label="Student" error={errors.student_id}>
            <StudentPicker value={values.student_id} onChange={(id) => set("student_id", id)}
              optionState={(st) => ({ hint: [st.email, st.countries.join(", ")].filter(Boolean).join(" · ") })} />
          </Field>
        )}
        <Field label="University" error={errors.university_id}>
          <input type="search" placeholder="Type to search the catalogue…" autoComplete="off" value={uniSearch} onChange={(e) => setUniSearch(e.target.value)} />
          <select size={5} style={{ marginTop: ".4rem" }} aria-label="University" value={values.university_id} onChange={(e) => e.target.value && loadCourses(e.target.value)}>
            {uniOptions.length
              ? uniOptions.map((u) => <option key={u.id} value={u.id}>{u.name} — {u.country}{u.rank ? ` · world rank ${u.rank}` : ""}</option>)
              : <option disabled>No universities match.</option>}
          </select>
        </Field>
        <Field label="Course" error={errors.course_id}>
          <select disabled={!Array.isArray(courses) || !courses.length} {...bind("course_id")}>
            {courses === null ? <option value="">Choose a university first</option>
              : courses === "loading" ? <option>Loading…</option>
              : !courses.length ? <option value="">No courses listed for this university</option>
              : <>
                <option value="">Select a course…</option>
                {courses.map((c) => <option key={c.id} value={c.id}>{c.title || c.name}{c.cluster ? ` (${c.cluster})` : ""}</option>)}
              </>}
          </select>
        </Field>
        <Field label="Intake" hint={hint} error={errors.intake_id}>
          <select name="intake_id" value={values.intake_id} onChange={(e) => pickIntake(e.target.value)}>
            <option value="">Select an intake…</option>
            {intakes.map((i) => <option key={i.id} value={i.id}>{i.name} — apply by {formatDate(i.application_deadline)}{i.is_open ? "" : " (closed)"}</option>)}
          </select>
        </Field>
        <div className="grid grid-2">
          <Field label="Deadline" error={errors.deadline}><input type="date" {...bind("deadline")} /></Field>
          <Field label="Tier" error={errors.tier}>
            <select {...bind("tier")}><option value="">Not set</option><option>Reach</option><option>Target</option><option>Safe</option></select>
          </Field>
        </div>
        <Field label="Notes" error={errors.notes}><textarea maxLength={1000} placeholder="Portal link, scholarship, anything to remember…" {...bind("notes")} /></Field>
      </form>
    </Drawer>
  );
}

export default function Applications() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const isStudent = user.role === "student";

  const [state, update] = useQueryState(LIST_STATE);
  const { q, status, student_id: studentId, sort, open: openOnly, page } = state;
  const [search, setSearch] = useState(q);
  const typed = useDebounced(search.trim());
  const [creating, setCreating] = useState(params.get("new")
    ? { university_id: params.get("university_id"), course_id: params.get("course_id"), student_id: params.get("student_id") }
    : null);

  useEffect(() => { if (typed !== q) update({ q: typed, page: 1 }); }, [typed]); // only when the debounced text changes
  const filter = (patch) => update({ ...patch, page: 1 });

  const summary = useLoad(() => api("/applications/summary/", { query: { student_id: studentId } }), [studentId]);
  const { data, error, reload } = useLoad(
    () => api("/applications/", { query: { page, q, status, student_id: studentId, sort, open: openOnly ? "true" : "" } }),
    [page, q, status, studentId, sort, openOnly]);

  function closeCreate() {
    setCreating(null);
    // Drop the one-off "plan this course" parameters so a refresh does not reopen the drawer.
    const params = new URLSearchParams(window.location.search);
    ["new", "university_id", "course_id"].forEach((k) => params.delete(k));
    const qs = params.toString();
    window.history.replaceState(window.history.state, "", window.location.pathname + (qs ? `?${qs}` : ""));
  }

  const s = summary.data;
  const cols = isStudent ? 5 : 6;

  return (
    <AppShell title="Applications" crumb="Applications">
      <div className="page-head">
        <div>
          <h1>{isStudent ? "My applications" : "Applications"}</h1>
          <p className="muted">{isStudent
            ? "Track each application from planning to decision. Your counsellor moves it through the stages."
            : user.role === "admin" ? "Applications across every student." : "Applications of the students assigned to you."}</p>
        </div>
        <div className="toolbar"><button type="button" className="btn btn-primary" onClick={() => setCreating({ student_id: studentId })}>New application</button></div>
      </div>

      {s?.overdue > 0 && <div className="alert alert-error"><b>{plural(s.overdue, "application")}</b> {s.overdue === 1 ? "is" : "are"} past the deadline and not yet submitted.</div>}
      {s?.due_soon > 0 && <div className="alert alert-warn"><b>{plural(s.due_soon, "deadline")}</b> in the next 14 days. Sort by nearest deadline to see them first.</div>}

      <div className="pipeline" role="group" aria-label="Filter by status">
        {s && [["", "All", s.total], ...STATUSES.map((k) => [k, appStatusLabel(k), s.by_status[k] || 0])].map(([key, label, n]) => (
          <button key={label} type="button" aria-pressed={status === key} onClick={() => filter({ status: key })}>{label}<span className="n">{n}</span></button>
        ))}
      </div>

      <div className="card">
        <div className="card-head">
          <div className="toolbar">
            <input type="search" placeholder="Search university or course…" aria-label="Search applications by university or course" value={search} onChange={(e) => setSearch(e.target.value)} />
            {!isStudent && (
              <div className="toolbar-picker"><StudentPicker ariaLabel="Filter by student" allLabel="All students" value={studentId} onChange={(id) => filter({ student_id: id })} /></div>
            )}
            <select aria-label="Sort" value={sort} onChange={(e) => filter({ sort: e.target.value })}>
              <option value="">Newest first</option><option value="deadline">Nearest deadline first</option>
            </select>
            <label className="checkbox"><input type="checkbox" checked={openOnly} onChange={(e) => filter({ open: e.target.checked })} /> Open only</label>
          </div>
          <span className="small muted" aria-live="polite">{data ? plural(data.count, "application") : ""}</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Programme</th>{!isStudent && <th>Student</th>}<th>Intake</th><th>Deadline</th><th>Status</th><th /></tr></thead>
            <tbody>
              {error ? <tr><td colSpan={cols}><ErrorAlert error={error} onRetry={reload} /></td></tr>
                : !data ? <tr><td colSpan={cols} className="loading" role="status">Loading applications…</td></tr>
                : !data.results.length ? (
                  <tr><td colSpan={cols} className="empty">{q || status || openOnly || studentId
                    ? "No applications match these filters."
                    : `No applications yet. ${isStudent ? "Find a programme under Universities, or start one here." : "Create one from a student's shortlist."}`}</td></tr>
                ) : data.results.map((a) => {
                  const snap = a.snapshot || {};
                  const href = `/applications/${encodeURIComponent(a.id)}/`;
                  return (
                    <tr key={a.id}>
                      <td className="prog">
                        <Link className="title" to={href}>{snap.course_title}</Link>
                        <div className="sub">{snap.university_name} · {snap.country}{snap.world_rank ? ` · world rank ${snap.world_rank}` : ""}{a.tier ? ` · ${a.tier}` : ""}</div>
                      </td>
                      {!isStudent && <td>{a.student_name}<div className="small muted">{a.counsellor_name || "No counsellor"}</div></td>}
                      <td>{snap.intake_name}</td>
                      <td><DeadlineBadge info={a.deadline_info} /></td>
                      <td><AppStatusBadge status={a.status} /><div className="small muted">Updated {formatDate(a.updated_at)}</div></td>
                      <td style={{ textAlign: "right" }}><Link className="btn btn-outline btn-sm" to={href} aria-label={`Open ${snap.course_title} at ${snap.university_name}`}>Open</Link></td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
        <Pager data={data} onPage={(p) => update({ page: p })} noun="application" />
      </div>

      {creating && <CreateDrawer isStudent={isStudent} prefill={creating} onClose={closeCreate} />}
    </AppShell>
  );
}
