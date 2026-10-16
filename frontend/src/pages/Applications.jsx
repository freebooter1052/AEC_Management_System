/* Application workspace (SRS 4.5): pipeline, deadlines and creating applications from the catalogue. */
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import AppShell from "../components/Shell";
import Drawer from "../components/Drawer";
import { useAuth } from "../components/auth";
import { useToast } from "../components/Toast";
import { AppStatusBadge, DeadlineBadge, Field, Pager } from "../components/ui";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import { useForm } from "../lib/form";
import { useDebounced } from "../lib/useDebounced";
import { useLoad } from "../lib/useLoad";

export const STATUSES = ["Planned", "Shortlisted", "Documents Pending", "Submitted", "Under Review", "Offer Received", "Rejected", "Withdrawn", "Completed"];
const OPEN_HINT = "The application deadline defaults to the intake deadline.";
const CLOSED_HINT = "This intake's deadline has passed. Enter the university's own later deadline, or choose another intake.";

function CreateDrawer({ isStudent, students, prefill, onClose }) {
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

  async function save() {
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
      toast(err.message, "error");
    }
  }

  const uniOptions = pinned && !unis.some((u) => u.id === pinned.id) ? [pinned, ...unis] : unis;

  return (
    <Drawer title="New application" onClose={onClose} footer={<>
      <button className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button className="btn btn-primary" onClick={save}>Create application</button>
    </>}>
      <form noValidate ref={form.ref} onSubmit={(e) => { e.preventDefault(); save(); }}>
        {!isStudent && (
          <Field label="Student" error={errors.student_id}>
            <select {...bind("student_id")}>
              <option value="">Select a student…</option>
              {students.map((s) => <option key={s.id} value={s.id}>{s.full_name}{s.countries.length ? ` — ${s.countries.join(", ")}` : ""}</option>)}
            </select>
          </Field>
        )}
        <Field label="University" error={errors.university_id}>
          <input type="search" placeholder="Type to search the catalogue…" autoComplete="off" value={uniSearch} onChange={(e) => setUniSearch(e.target.value)} />
          <select size={5} style={{ marginTop: ".4rem" }} aria-label="University" value={values.university_id} onChange={(e) => e.target.value && loadCourses(e.target.value)}>
            {uniOptions.length
              ? uniOptions.map((u) => <option key={u.id} value={u.id}>{u.name} — {u.country}{u.rank ? ` · #${u.rank}` : ""}</option>)
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
  const toast = useToast();
  const [params] = useSearchParams();
  const isStudent = user.role === "student";

  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim());
  const [status, setStatus] = useState("");
  const [studentId, setStudentId] = useState(params.get("student_id") || "");
  const [sort, setSort] = useState("");
  const [openOnly, setOpenOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [students, setStudents] = useState([]);
  const [creating, setCreating] = useState(params.get("new")
    ? { university_id: params.get("university_id"), course_id: params.get("course_id"), student_id: params.get("student_id") }
    : null);

  useEffect(() => setPage(1), [q, status, studentId, sort, openOnly]);
  useEffect(() => {
    if (!isStudent) api("/students/", { query: { page_size: 100 } }).then((d) => setStudents(d.results), (err) => toast(err.message, "error"));
  }, [isStudent, toast]);

  const summary = useLoad(() => api("/applications/summary/", { query: { student_id: studentId } }), [studentId]);
  const { data, error } = useLoad(
    () => api("/applications/", { query: { page, q, status, student_id: studentId, sort, open: openOnly ? "true" : "" } }),
    [page, q, status, studentId, sort, openOnly]);

  function pickStudent(id) {
    setStudentId(id);
    window.history.replaceState(null, "", id ? `?student_id=${encodeURIComponent(id)}` : window.location.pathname);
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
        <div className="toolbar"><button className="btn btn-primary" onClick={() => setCreating({ student_id: studentId })}>New application</button></div>
      </div>

      {s?.overdue > 0 && <div className="alert alert-error"><b>{s.overdue}</b> application{s.overdue === 1 ? " is" : "s are"} past the deadline and not yet submitted.</div>}
      {s?.due_soon > 0 && <div className="alert alert-warn"><b>{s.due_soon}</b> deadline{s.due_soon === 1 ? "" : "s"} in the next 14 days. Sort by nearest deadline to see them first.</div>}

      <div className="pipeline" role="group" aria-label="Filter by status">
        {s && [["", "All", s.total], ...STATUSES.map((k) => [k, k, s.by_status[k] || 0])].map(([key, label, n]) => (
          <button key={label} type="button" aria-pressed={status === key} onClick={() => setStatus(key)}>{label}<span className="n">{n}</span></button>
        ))}
      </div>

      <div className="card">
        <div className="card-head">
          <div className="toolbar">
            <input type="search" placeholder="Search university or course…" aria-label="Search applications" value={search} onChange={(e) => setSearch(e.target.value)} />
            {!isStudent && (
              <select aria-label="Filter by student" value={studentId} onChange={(e) => pickStudent(e.target.value)}>
                <option value="">All students</option>
                {students.map((st) => <option key={st.id} value={st.id}>{st.full_name}</option>)}
              </select>
            )}
            <select aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="">Newest first</option><option value="deadline">Nearest deadline first</option>
            </select>
            <label className="checkbox"><input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> Open only</label>
          </div>
          <span className="small muted">{data ? `${data.count} application${data.count === 1 ? "" : "s"}` : ""}</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Programme</th>{!isStudent && <th>Student</th>}<th>Intake</th><th>Deadline</th><th>Status</th><th /></tr></thead>
            <tbody>
              {error ? <tr><td colSpan={cols}><div className="alert alert-error" style={{ margin: 0 }}>{error.message}</div></td></tr>
                : !data ? <tr><td colSpan={cols} className="loading">Loading…</td></tr>
                : !data.results.length ? (
                  <tr><td colSpan={cols} className="empty">{q || status || openOnly
                    ? "No applications match these filters."
                    : `No applications yet. ${isStudent ? "Find a programme under Universities, or start one here." : "Create one from a student's shortlist."}`}</td></tr>
                ) : data.results.map((a) => {
                  const snap = a.snapshot || {};
                  const href = `/applications/${encodeURIComponent(a.id)}/`;
                  return (
                    <tr key={a.id}>
                      <td className="prog">
                        <Link className="title" to={href}>{snap.course_title}</Link>
                        <div className="sub">{snap.university_name} · {snap.country}{snap.world_rank ? ` · #${snap.world_rank}` : ""}{a.tier ? ` · ${a.tier}` : ""}</div>
                      </td>
                      {!isStudent && <td>{a.student_name}<div className="small muted">{a.counsellor_name || "No counsellor"}</div></td>}
                      <td>{snap.intake_name}</td>
                      <td><DeadlineBadge info={a.deadline_info} /></td>
                      <td><AppStatusBadge status={a.status} /><div className="small muted">Updated {formatDate(a.updated_at)}</div></td>
                      <td style={{ textAlign: "right" }}><Link className="btn btn-outline btn-sm" to={href}>Open</Link></td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
        <Pager data={data} onPage={setPage} />
      </div>

      {creating && <CreateDrawer isStudent={isStudent} students={students} prefill={creating} onClose={() => setCreating(null)} />}
    </AppShell>
  );
}
