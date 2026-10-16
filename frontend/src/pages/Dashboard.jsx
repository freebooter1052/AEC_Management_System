import { Link } from "react-router-dom";
import AppShell from "../components/Shell";
import { AppStatusBadge, DeadlineBadge, ErrorAlert, Kpi, Loading, ProgressBar, StatusBadge } from "../components/ui";
import { api } from "../lib/api";
import { formatDate, formatDateTime, initials } from "../lib/format";
import { useLoad } from "../lib/useLoad";

const Overdue = ({ n }) => <b style={{ color: "var(--err)" }}>{n} overdue</b>;
const Empty = ({ children }) => <p className="muted" style={{ margin: 0 }}>{children}</p>;
const Sub = ({ children }) => <span className="small muted" style={{ display: "block" }}>{children}</span>;

function DeadlinesCard({ apps, showStudent }) {
  const list = apps.upcoming_deadlines || [];
  return (
    <div className="card">
      <div className="card-head"><h3>Upcoming deadlines</h3><Link className="small" to="/applications/">Applications →</Link></div>
      {list.length ? (
        <ul className="list-plain">
          {list.map((a) => (
            <li key={a.id}>
              <span>
                <Link className="name" to={`/applications/${encodeURIComponent(a.id)}/`}>{a.snapshot.course_title}</Link>
                <Sub>{a.snapshot.university_name}{showStudent ? ` · ${a.student_name}` : ""}</Sub>
              </span>
              <DeadlineBadge info={a.deadline_info} />
            </li>
          ))}
        </ul>
      ) : <Empty>No open deadlines.</Empty>}
    </div>
  );
}

function SessionsCard({ sessions, showStudent }) {
  return (
    <div className="card">
      <div className="card-head"><h3>Upcoming sessions</h3><Link className="small" to="/counselling/">Calendar →</Link></div>
      {sessions.length ? (
        <ul className="list-plain">
          {sessions.map((s) => (
            <li key={s.id}>
              <span><span className="name">{s.topic}</span><Sub>{showStudent ? s.student_name : `with ${s.counsellor_name}`} · {s.mode}</Sub></span>
              <span className="small" style={{ textAlign: "right" }}>{formatDateTime(s.scheduled_at)}</span>
            </li>
          ))}
        </ul>
      ) : <Empty>No sessions scheduled.</Empty>}
    </div>
  );
}

function FollowUpsCard({ f, showStudent }) {
  const rows = f.next || [];
  return (
    <div className="card">
      <div className="card-head"><h3>Follow-ups</h3><Link className="small" to="/counselling/?tab=follow-ups">All →</Link></div>
      {rows.length ? (
        <ul className="list-plain">
          {rows.map((r, i) => (
            <li key={`${r.session_id || ""}-${i}`}>
              <span><span className="name">{r.action}</span>{showStudent && <Sub>{r.student_name}</Sub>}</span>
              <span className={r.state === "overdue" ? "badge badge-err" : "badge"}>{formatDate(r.due_date)}</span>
            </li>
          ))}
        </ul>
      ) : <Empty>Nothing pending.</Empty>}
    </div>
  );
}

function PipelineCard({ apps }) {
  const rows = Object.entries(apps.by_status || {}).filter(([, n]) => n);
  return (
    <div className="card">
      <div className="card-head"><h3>Application pipeline</h3><Link className="small" to="/applications/">Workspace →</Link></div>
      {rows.length ? (
        <ul className="list-plain">{rows.map(([s, n]) => <li key={s}><AppStatusBadge status={s} /><b>{n}</b></li>)}</ul>
      ) : <Empty>No applications yet.</Empty>}
    </div>
  );
}

function CounsellorCard({ c }) {
  if (!c) {
    return (
      <div className="card counsellor-dock"><h3>Your counsellor</h3>
        <p className="muted">No counsellor has been assigned yet. An administrator will match you with a counsellor once your profile is underway.</p>
      </div>
    );
  }
  return (
    <div className="card counsellor-dock"><h3>Your counsellor</h3>
      <div className="row"><div className="avatar">{initials(c.name)}</div>
        <div><div style={{ fontWeight: 600 }}>{c.name}</div><div className="small muted">{c.specialization || "Education counsellor"}</div></div>
      </div>
      <dl>
        <dt>Email</dt><dd><a href={`mailto:${c.email}`}>{c.email}</a></dd>
        <dt>Phone</dt><dd>{c.phone || "—"}</dd>
        <dt>Hub</dt><dd>{c.region || "—"}</dd>
      </dl>
    </div>
  );
}

function Head({ title, subtitle, children }) {
  return (
    <div className="page-head">
      <div><h1>{title}</h1><p className="muted">{subtitle}</p></div>
      <div className="toolbar">{children}</div>
    </div>
  );
}

function StudentDashboard({ d }) {
  const comp = d.profile_completion || {};
  const prefs = d.preferences || {};
  const missing = (comp.missing || []).slice(0, 8);
  const dd = { margin: 0 };
  return (
    <>
      <Head title={`Your journey abroad starts here, ${d.full_name.split(" ")[0] || "there"}`} subtitle="Build your profile, shortlist universities, and track every application and document in one place, with a counsellor guiding each step.">
        <Link className="btn btn-primary" to="/profile/">Update profile</Link>
      </Head>
      <div className="kpis">
        <Kpi label="Profile readiness" value={`${comp.overall ?? 0}%`}><StatusBadge status={d.onboarding_status} /></Kpi>
        <Kpi label="Counsellor" value={d.counsellor ? "Assigned" : "Pending"}>{d.counsellor?.name || "Awaiting assignment"}</Kpi>
        <Kpi label="Applications" value={d.applications.open}>{d.applications.total} in total{d.applications.overdue ? <> · <Overdue n={d.applications.overdue} /></> : null}</Kpi>
        <Kpi label="Documents to upload" value={d.documents.needs_attention}>{d.documents.awaiting_review} with your counsellor</Kpi>
      </div>
      <div className="cards-3">
        <DeadlinesCard apps={d.applications} />
        <SessionsCard sessions={d.upcoming_sessions} />
        <FollowUpsCard f={d.follow_ups} />
      </div>
      <div className="layout-2">
        <div className="stack">
          <div className="card">
            <div className="card-head"><h3>Profile sections</h3><Link to="/profile/" className="small">Open profile →</Link></div>
            {["personal", "academic", "preferences"].map((s) => (
              <div key={s} style={{ marginBottom: ".8rem" }}>
                <div className="small" style={{ fontWeight: 600, textTransform: "capitalize", marginBottom: ".3rem" }}>{s}</div>
                <ProgressBar pct={comp[s]} />
              </div>
            ))}
          </div>
          <div className="card">
            <h3>{missing.length ? "Still needed to reach 100%" : "Profile complete"}</h3>
            {missing.length
              ? <ul className="missing-list">{missing.map((m) => <li key={m.field}>{m.label}</li>)}</ul>
              : <p className="muted">Every required field is filled in. Your counsellor can now shortlist programmes.</p>}
          </div>
        </div>
        <div className="stack">
          <CounsellorCard c={d.counsellor} />
          <div className="card"><h3>Preferences</h3>
            <dl className="counsellor-dock" style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: ".3rem .8rem", margin: 0, fontSize: ".86rem" }}>
              <dt className="muted">Level</dt><dd style={dd}>{prefs.degree_level || "—"}</dd>
              <dt className="muted">Intake</dt><dd style={dd}>{prefs.intake || "—"}</dd>
              <dt className="muted">Courses</dt><dd style={dd}>{(prefs.course_areas || []).join(", ") || "—"}</dd>
              <dt className="muted">Budget</dt><dd style={dd}>{prefs.budget?.max ? `${prefs.budget.min ?? 0}–${prefs.budget.max} ${prefs.budget.currency}` : "—"}</dd>
            </dl>
          </div>
        </div>
      </div>
    </>
  );
}

function RosterTable({ rows }) {
  if (!rows.length) return <p className="empty">No students assigned yet.</p>;
  return (
    <div className="table-wrap"><table>
      <thead><tr><th>Student</th><th>Targets</th><th>Readiness</th><th>Status</th></tr></thead>
      <tbody>
        {rows.map((s) => (
          <tr key={s.id}>
            <td><Link className="name" to={`/students/${encodeURIComponent(s.id)}/`}>{s.full_name}</Link><div className="small muted">{s.email}</div></td>
            <td>{s.countries.join(", ") || "—"}<div className="small muted">{s.intake || ""}</div></td>
            <td style={{ minWidth: 140 }}><ProgressBar pct={s.profile_completion} /></td>
            <td><StatusBadge status={s.onboarding_status} /></td>
          </tr>
        ))}
      </tbody>
    </table></div>
  );
}

function CounsellorDashboard({ d }) {
  const w = d.workload || { assigned: 0, capacity: 0, available: 0, utilisation_pct: 0 };
  return (
    <>
      <Head title={`Help your students get there, ${d.name.split(" ")[0]}`} subtitle="See who needs you first: upcoming sessions, pending documents and applications nearing their deadlines.">
        <Link className="btn btn-primary" to="/students/">Open roster</Link>
      </Head>
      <div className="kpis">
        <Kpi label="Assigned students" value={w.assigned}>of {w.capacity} capacity</Kpi>
        <Kpi label="Open applications" value={d.applications.open}>{d.applications.due_soon} due in 14 days{d.applications.overdue ? <> · <Overdue n={d.applications.overdue} /></> : null}</Kpi>
        <Kpi label="Documents to review" value={d.documents.awaiting_review}><Link to="/documents/">Open review queue →</Link></Kpi>
        <Kpi label="Follow-ups" value={d.follow_ups.pending}>{d.follow_ups.overdue ? <Overdue n={d.follow_ups.overdue} /> : "None overdue"}</Kpi>
        <Kpi label="Open slots" value={w.available}><ProgressBar pct={w.utilisation_pct} label={`${w.utilisation_pct}% used`} /></Kpi>
      </div>
      <div className="cards-3">
        <SessionsCard sessions={d.upcoming_sessions} showStudent />
        <DeadlinesCard apps={d.applications} showStudent />
        <FollowUpsCard f={d.follow_ups} showStudent />
      </div>
      <div className="card">
        <div className="card-head"><h3>Needs attention — lowest profile readiness</h3><Link className="small" to="/students/">All students →</Link></div>
        <RosterTable rows={d.needs_attention} />
      </div>
    </>
  );
}

function AdminDashboard({ d }) {
  const t = d.totals;
  const rows = d.counsellor_workload;
  return (
    <>
      <Head title="Run your admissions agency with clarity" subtitle="Agency-wide applications, student onboarding and counsellor workload, so no student goes unassigned.">
        <Link className="btn btn-outline" to="/students/?unassigned=1">Assign students</Link>
        <Link className="btn btn-primary" to="/counsellors/?new=1">Add counsellor</Link>
      </Head>
      <div className="kpis">
        <Kpi label="Students" value={t.students}>{t.unassigned_students} awaiting a counsellor</Kpi>
        <Kpi label="Counsellors" value={t.counsellors}>{t.active_counsellors} active</Kpi>
        <Kpi label="Open applications" value={d.applications.open}>{d.applications.total} in total · {d.applications.overdue} overdue</Kpi>
        <Kpi label="Documents to review" value={d.documents.awaiting_review}>{d.documents.needs_attention} waiting on students</Kpi>
      </div>
      {t.unassigned_students > 0 && (
        <div className="alert alert-warn">{t.unassigned_students} student(s) have no counsellor. <Link to="/students/?unassigned=1">Assign them now →</Link></div>
      )}
      <div className="cards-3">
        <PipelineCard apps={d.applications} />
        <DeadlinesCard apps={d.applications} showStudent />
        <SessionsCard sessions={d.upcoming_sessions} showStudent />
      </div>
      <div className="card">
        <div className="card-head"><h3>Counsellor workload</h3><Link className="small" to="/counsellors/">Manage counsellors →</Link></div>
        {rows.length ? (
          <div className="table-wrap"><table>
            <thead><tr><th>Counsellor</th><th>Assigned</th><th style={{ width: "40%" }}>Utilisation</th></tr></thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id || c.name}><td className="name">{c.name}</td><td>{c.assigned} / {c.capacity}</td><td><ProgressBar pct={c.utilisation_pct} /></td></tr>
              ))}
            </tbody>
          </table></div>
        ) : <p className="empty">No counsellors yet. <Link to="/counsellors/?new=1">Add the first one</Link>.</p>}
      </div>
    </>
  );
}

export default function Dashboard() {
  const { data, error } = useLoad(() => api("/dashboard/"), []);
  let body;
  if (error) body = <><Head title="Dashboard" /><ErrorAlert error={error} /></>;
  else if (!data) body = <><Head title="Dashboard" /><Loading /></>;
  else if (data.role === "student") body = <StudentDashboard d={data} />;
  else if (data.role === "counsellor") body = <CounsellorDashboard d={data} />;
  else body = <AdminDashboard d={data} />;
  return <AppShell title="Dashboard" crumb="Dashboard">{body}</AppShell>;
}
