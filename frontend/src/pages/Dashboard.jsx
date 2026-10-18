import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppShell from "../components/Shell";
import { AppStatusBadge, DeadlineBadge, DocStatusBadge, ErrorAlert, Kpi, Loading, ProgressBar, StatusBadge } from "../components/ui";
import { api } from "../lib/api";
import { formatDate, formatDateTime, initials, plural } from "../lib/format";
import { studentNextStep } from "../lib/nextStep";
import { categoryLabel, safeLink, timeAgo } from "../lib/notifications";
import { eligibilityInfo } from "../lib/recommendations";
import { useLoad } from "../lib/useLoad";
import { useQueryState } from "../lib/useQueryState";
import { ID_PATTERN } from "./Applications";

const FILTER_STATE = {
  country: { default: "" },
  intake_id: { default: "", pattern: ID_PATTERN },
  counsellor_id: { default: "", pattern: ID_PATTERN },
};
const DOC_STATUSES = ["Required", "Uploaded", "Under Review", "Verified", "Rejected", "Expired"];

const Overdue = ({ n }) => <b style={{ color: "var(--err)" }}>{n} overdue</b>;
const Empty = ({ children }) => <p className="muted" style={{ margin: 0 }}>{children}</p>;
const Sub = ({ children }) => <span className="small muted" style={{ display: "block" }}>{children}</span>;

function DeadlinesCard({ apps, showStudent }) {
  const list = apps.upcoming_deadlines || [];
  return (
    <div className="card">
      <div className="card-head"><h3>Upcoming deadlines</h3><Link className="small" to="/applications/?sort=deadline&open=1">Applications →</Link></div>
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
      <div className="card-head"><h3>Application pipeline</h3><Link className="small" to="/applications/">Applications →</Link></div>
      {rows.length ? (
        <ul className="list-plain">{rows.map(([s, n]) => (
          <li key={s}><Link to={`/applications/?status=${encodeURIComponent(s)}`}><AppStatusBadge status={s} /></Link><b>{n}</b></li>
        ))}</ul>
      ) : <Empty>No applications yet.</Empty>}
    </div>
  );
}

function DocumentStatusCard({ docs }) {
  const rows = DOC_STATUSES.map((s) => [s, docs.by_status?.[s] || 0]).filter(([, n]) => n);
  return (
    <div className="card">
      <div className="card-head"><h3>Document status</h3><Link className="small" to="/documents/?status=all">Documents →</Link></div>
      {rows.length ? <ul className="list-plain">{rows.map(([s, n]) => <li key={s}><DocStatusBadge status={s} /><b>{n}</b></li>)}</ul>
        : <Empty>No documents yet.</Empty>}
    </div>
  );
}

function NotificationsCard({ n }) {
  return (
    <div className="card">
      <div className="card-head"><h3>Notifications{n.unread ? <span className="badge badge-brand" style={{ marginLeft: ".5rem" }}>{n.unread} unread</span> : null}</h3>
        <Link className="small" to="/notifications/">All →</Link></div>
      {n.latest.length ? (
        <ul className="list-plain">
          {n.latest.map((x) => (
            <li key={x.id}>
              <span style={{ minWidth: 0 }}>
                {safeLink(x.link) ? <Link className="name" to={safeLink(x.link)}>{x.title}</Link> : <span className="name">{x.title}</span>}
                <Sub>{categoryLabel(x.category)} · {timeAgo(x.created_at)}</Sub>
              </span>
              {!x.is_read && <span className="badge badge-brand">New</span>}
            </li>
          ))}
        </ul>
      ) : <Empty>No notifications yet. Application updates and reminders will appear here.</Empty>}
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
        <dt>Region</dt><dd>{c.region || "—"}</dd>
      </dl>
    </div>
  );
}

function Head({ eyebrow, title, subtitle, children }) {
  return (
    <div className="page-head">
      <div>{eyebrow && <p className="page-eyebrow">{eyebrow}</p>}<h1>{title}</h1>{subtitle && <p className="muted">{subtitle}</p>}</div>
      <div className="toolbar">{children}</div>
    </div>
  );
}

function RecommendationsCard({ r }) {
  return (
    <div className="card">
      <div className="card-head"><h3>Recommended for you</h3><Link className="small" to="/recommendations/">All {r.total ? `${r.total} ` : ""}→</Link></div>
      {r.freshness?.state === "stale" && <div className="alert alert-warn">Your profile or the catalogue changed since these were made. <Link to="/recommendations/">Refresh them →</Link></div>}
      {r.top.length ? (
        <ul className="list-plain">
          {r.top.map((rec) => {
            const elig = eligibilityInfo(rec.eligibility);
            return (
              <li key={rec.id}>
                <span className="rec-mini" style={{ minWidth: 0 }}>
                  <span className="name">{rec.snapshot?.course_title}</span>
                  <Sub>{rec.snapshot?.university_name} · {rec.snapshot?.country}</Sub>
                  {rec.reasons?.[0] && <span className="why">{rec.reasons[0]}</span>}
                </span>
                <span style={{ textAlign: "right" }}><b>{rec.match_score}%</b><Sub>{elig.label}</Sub></span>
              </li>
            );
          })}
        </ul>
      ) : r.run?.status === "insufficient_profile"
        ? <Empty>{r.run.message} <Link to="/profile/">Update your preferences</Link>.</Empty>
        : <Empty>{r.freshness?.state === "never" ? "No recommendations yet. " : "Nothing matches your profile well enough yet. "}<Link to="/recommendations/">Open recommendations</Link> to generate them.</Empty>}
    </div>
  );
}

function StudentDashboard({ d }) {
  const comp = d.profile_completion || {};
  const prefs = d.preferences || {};
  const missing = (comp.missing || []).slice(0, 8);
  const dd = { margin: 0 };
  const next = studentNextStep(d);
  return (
    <>
      <Head eyebrow={`Hello, ${d.full_name.split(" ")[0] || "there"}`} title={next.title} subtitle={next.text}>
        <Link className="btn btn-primary" to={next.to}>{next.action}</Link>
      </Head>
      <div className="kpis">
        <Kpi label="Profile readiness" value={`${comp.overall ?? 0}%`} to="/profile/"><StatusBadge status={d.onboarding_status} /></Kpi>
        <Kpi label="Open applications" value={d.applications.open} to="/applications/?open=1">{d.applications.total} in total{d.applications.overdue ? <> · <Overdue n={d.applications.overdue} /></> : null}</Kpi>
        <Kpi label="Documents to upload" value={d.documents.needs_attention} to="/documents/">{d.documents.awaiting_review} waiting to be checked</Kpi>
        <Kpi label="Recommendations" value={d.recommendations.total} to="/recommendations/">{d.recommendations.freshness?.state === "stale" ? "Out of date: refresh" : d.recommendations.total ? "Matched to your profile" : "None yet"}</Kpi>
        <Kpi label="Counsellor" value={d.counsellor ? "Assigned" : "Pending"}>{d.counsellor?.name || "Awaiting assignment"}</Kpi>
      </div>
      <div className="cards-3">
        <DeadlinesCard apps={d.applications} />
        <SessionsCard sessions={d.upcoming_sessions} />
        <FollowUpsCard f={d.follow_ups} />
      </div>
      <div className="layout-2">
        <div className="stack">
          <div className="card">
            <div className="card-head"><h3>My applications</h3><Link className="small" to="/applications/">All →</Link></div>
            {d.application_list.length ? (
              <ul className="list-plain">
                {d.application_list.map((a) => (
                  <li key={a.id}>
                    <span style={{ minWidth: 0 }}><Link className="name" to={`/applications/${encodeURIComponent(a.id)}/`}>{a.snapshot.course_title}</Link>
                      <Sub>{a.snapshot.university_name} · {a.snapshot.intake_name}</Sub></span>
                    <span style={{ display: "grid", justifyItems: "end", gap: ".25rem" }}><AppStatusBadge status={a.status} /><DeadlineBadge info={a.deadline_info} /></span>
                  </li>
                ))}
              </ul>
            ) : <Empty>No applications yet. <Link to="/recommendations/">See your recommendations</Link> or <Link to="/universities/">search the catalogue</Link>.</Empty>}
          </div>
          <div className="card">
            <div className="card-head"><h3>Documents needing action</h3><Link className="small" to="/documents/">Documents →</Link></div>
            {d.documents_attention.length ? (
              <ul className="list-plain">
                {d.documents_attention.map((doc) => (
                  <li key={doc.id}>
                    <span style={{ minWidth: 0 }}><span className="name">{doc.title || doc.document_type}</span>
                      <Sub>{doc.application_label || "General document"}{doc.remarks ? ` · ${doc.remarks}` : ""}</Sub></span>
                    <DocStatusBadge status={doc.status} />
                  </li>
                ))}
              </ul>
            ) : <Empty>Nothing to upload or replace right now.</Empty>}
          </div>
          <RecommendationsCard r={d.recommendations} />
          <div className="card">
            <div className="card-head"><h3>Profile sections</h3><Link to="/profile/" className="small">Open profile →</Link></div>
            {["personal", "academic", "preferences"].map((s) => (
              <div key={s} style={{ marginBottom: ".8rem" }}>
                <div className="small" style={{ fontWeight: 600, textTransform: "capitalize", marginBottom: ".3rem" }}>{s}</div>
                <ProgressBar pct={comp[s]} name={`${s} section completion`} />
              </div>
            ))}
            <h4 style={{ margin: "1rem 0 .4rem" }}>{missing.length ? "Still needed to reach 100%" : "Profile complete"}</h4>
            {missing.length
              ? <ul className="missing-list">{missing.map((m) => <li key={m.field}>{m.label}</li>)}</ul>
              : <p className="muted" style={{ margin: 0 }}>Every required field is filled in.</p>}
          </div>
        </div>
        <div className="stack">
          <NotificationsCard n={d.notifications} />
          <CounsellorCard c={d.counsellor} />
          <div className="card"><h3>Preferences</h3>
            <dl className="counsellor-dock" style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: ".3rem .8rem", margin: 0, fontSize: ".86rem" }}>
              <dt className="muted">Level</dt><dd style={dd}>{prefs.degree_level || "—"}</dd>
              <dt className="muted">Intake</dt><dd style={dd}>{prefs.intake || "—"}</dd>
              <dt className="muted">Countries</dt><dd style={dd}>{(prefs.countries || []).join(", ") || "—"}</dd>
              <dt className="muted">Courses</dt><dd style={dd}>{(prefs.course_areas || []).join(", ") || "—"}</dd>
              <dt className="muted">Budget</dt><dd style={dd}>{prefs.budget?.max ? `${prefs.budget.min ?? 0}–${prefs.budget.max} ${prefs.budget.currency}` : "—"}</dd>
            </dl>
          </div>
        </div>
      </div>
    </>
  );
}

/** Country / intake (and counsellor, for admins) filters, kept in the URL. */
function FilterBar({ filters, update, counsellors }) {
  const [countries, setCountries] = useState([]);
  const [intakes, setIntakes] = useState([]);
  useEffect(() => {
    api("/universities/countries/").then(setCountries, () => { /* filter options only */ });
    api("/intakes/").then(setIntakes, () => { /* filter options only */ });
  }, []);
  const active = filters.country || filters.intake_id || filters.counsellor_id;
  return (
    <div className="filter-bar" role="group" aria-label="Dashboard filters">
      {counsellors && (
        <select aria-label="Counsellor" value={filters.counsellor_id} onChange={(e) => update({ counsellor_id: e.target.value })}>
          <option value="">All counsellors</option>
          {counsellors.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      )}
      <select aria-label="Country" value={filters.country} onChange={(e) => update({ country: e.target.value })}>
        <option value="">All countries</option>
        {countries.map((c) => <option key={c.country} value={c.country}>{c.country}</option>)}
      </select>
      <select aria-label="Intake" value={filters.intake_id} onChange={(e) => update({ intake_id: e.target.value })}>
        <option value="">All intakes</option>
        {intakes.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
      </select>
      {active && <button type="button" className="btn btn-outline btn-sm" onClick={() => update({ country: "", intake_id: "", counsellor_id: "" })}>Clear filters</button>}
      {active && <span className="small muted">Country and intake filter the application figures{counsellors ? "; the counsellor filter applies to everything" : ""}.</span>}
    </div>
  );
}

function RosterTable({ rows }) {
  if (!rows.length) return <p className="empty">No students assigned yet.</p>;
  return (
    <div className="table-wrap"><table>
      <thead><tr><th>Student</th><th>Targets</th><th>Readiness</th><th>Documents to provide</th><th>Open applications</th><th>Status</th></tr></thead>
      <tbody>
        {rows.map((s) => (
          <tr key={s.id}>
            <td><Link className="name" to={`/students/${encodeURIComponent(s.id)}/`}>{s.full_name}</Link><div className="small muted">{s.email}</div></td>
            <td>{s.countries.join(", ") || "—"}<div className="small muted">{s.intake || ""}</div></td>
            <td style={{ minWidth: 140 }}><ProgressBar pct={s.profile_completion} name={`${s.full_name} profile readiness`} /></td>
            <td>{s.documents_outstanding ? <Link to={`/documents/?student_id=${encodeURIComponent(s.id)}&status=Required,Rejected,Expired`}>{s.documents_outstanding}</Link> : 0}</td>
            <td>{s.open_applications}</td>
            <td><StatusBadge status={s.onboarding_status} /></td>
          </tr>
        ))}
      </tbody>
    </table></div>
  );
}

function ReviewQueueCard({ docs }) {
  return (
    <div className="card">
      <div className="card-head"><h3>Documents to review</h3><Link className="small" to="/documents/">Review queue →</Link></div>
      {docs.length ? (
        <ul className="list-plain">
          {docs.map((d) => (
            <li key={d.id}>
              <span style={{ minWidth: 0 }}><Link className="name" to={`/documents/?student_id=${encodeURIComponent(d.student_id)}`}>{d.title || d.document_type}</Link>
                <Sub>{d.student_name} · uploaded {formatDate(d.uploaded_at)}</Sub></span>
              <DocStatusBadge status={d.status} />
            </li>
          ))}
        </ul>
      ) : <Empty>No documents are waiting for review.</Empty>}
    </div>
  );
}

function CounsellorDashboard({ d, filters, update }) {
  const w = d.workload || { assigned: 0, capacity: 0, available: 0, utilisation_pct: 0 };
  return (
    <>
      <Head eyebrow={`Hello, ${d.name.split(" ")[0]}`} title="Who needs you first" subtitle="Documents to review, follow-ups, and applications nearing their deadlines for your students.">
        <Link className="btn btn-primary" to="/students/">My students</Link>
      </Head>
      <FilterBar filters={filters} update={update} />
      <div className="kpis">
        <Kpi label="Assigned students" value={w.assigned} to="/students/">of {w.capacity} capacity{d.students_without_recommendations ? ` · ${d.students_without_recommendations} without recommendations` : ""}</Kpi>
        <Kpi label="Open applications" value={d.applications.open} to="/applications/?open=1">{d.applications.due_soon} due in 14 days{d.applications.overdue ? <> · <Overdue n={d.applications.overdue} /></> : null}</Kpi>
        <Kpi label="Documents to review" value={d.documents.awaiting_review} to="/documents/">{d.documents.needs_attention} waiting on students</Kpi>
        <Kpi label="Follow-ups" value={d.follow_ups.pending} to="/counselling/?tab=follow-ups">{d.follow_ups.overdue ? <Overdue n={d.follow_ups.overdue} /> : "None overdue"}</Kpi>
        <Kpi label="Open slots" value={w.available}><ProgressBar pct={w.utilisation_pct} label={`${w.utilisation_pct}% used`} name="Capacity used" /></Kpi>
      </div>
      <div className="cards-3">
        <ReviewQueueCard docs={d.review_queue} />
        <FollowUpsCard f={d.follow_ups} showStudent />
        <DeadlinesCard apps={d.applications} showStudent />
        <PipelineCard apps={d.applications} />
        <SessionsCard sessions={d.upcoming_sessions} showStudent />
        <NotificationsCard n={d.notifications} />
      </div>
      <div className="card">
        <div className="card-head"><h3>Students needing attention</h3><Link className="small" to="/students/">All students →</Link></div>
        <p className="small muted" style={{ marginTop: "-.5rem" }}>Most documents still to provide first, then the least complete profiles.</p>
        <RosterTable rows={d.needs_attention} />
      </div>
    </>
  );
}

function ReportTable({ title, rows, noun }) {
  const max = Math.max(1, ...rows.map((r) => r.applications));
  return (
    <div className="card">
      <h3>{title}</h3>
      {rows.length ? (
        <div className="table-wrap"><table className="report-table">
          <thead><tr><th scope="col">{noun}</th><th scope="col" className="num">Applications</th><th scope="col" className="num">Offers</th><th scope="col" aria-hidden="true" /></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.name}><th scope="row" style={{ background: "none", textTransform: "none", letterSpacing: 0, fontSize: ".9rem", color: "var(--ink)" }}>{r.name}</th>
              <td className="num">{r.applications}</td><td className="num">{r.offers}</td>
              <td style={{ width: "30%" }} aria-hidden="true"><div className="mini-bar"><span style={{ width: `${(100 * r.applications) / max}%` }} /></div></td></tr>
          ))}</tbody>
        </table></div>
      ) : <Empty>No applications match these filters.</Empty>}
    </div>
  );
}

function AdminDashboard({ d, filters, update }) {
  const t = d.totals;
  const rows = d.counsellor_workload;
  const rep = d.reports;
  const recs = rep.recommendations;
  return (
    <>
      <Head title="Agency overview" subtitle="Applications, documents, student onboarding and counsellor workload across the agency.">
        <Link className="btn btn-outline" to="/students/?unassigned=1">Assign students</Link>
        <Link className="btn btn-primary" to="/counsellors/?new=1">Add counsellor</Link>
      </Head>
      <FilterBar filters={filters} update={update} counsellors={d.filter_options.counsellors} />
      <div className="kpis">
        <Kpi label="Students" value={t.students} to="/students/">{t.unassigned_students} awaiting a counsellor</Kpi>
        <Kpi label="Counsellors" value={t.counsellors} to="/counsellors/">{t.active_counsellors} active</Kpi>
        <Kpi label="Catalogue" value={t.universities} to="/universities/">universities · {t.active_courses} of {t.courses} courses offered</Kpi>
        <Kpi label="Applications" value={t.applications} to="/applications/">{d.applications.open} open · {d.applications.overdue} overdue</Kpi>
        <Kpi label="Documents to review" value={d.documents.awaiting_review} to="/documents/">{d.documents.needs_attention} waiting on students</Kpi>
      </div>
      {t.unassigned_students > 0 && (
        <div className="alert alert-warn">{plural(t.unassigned_students, "student")} {t.unassigned_students === 1 ? "has" : "have"} no counsellor. <Link to="/students/?unassigned=1">Assign {t.unassigned_students === 1 ? "one" : "them"} now →</Link></div>
      )}
      <div className="cards-3">
        <PipelineCard apps={d.applications} />
        <DocumentStatusCard docs={d.documents} />
        <DeadlinesCard apps={d.applications} showStudent />
        <SessionsCard sessions={d.upcoming_sessions} showStudent />
        <FollowUpsCard f={d.follow_ups} showStudent />
        <div className="card">
          <h3>Recommendations</h3>
          {recs.total ? (
            <ul className="list-plain">
              {["Suggested", "Accepted", "Rejected"].map((s) => <li key={s}><span>{s}</span><b>{recs.by_status[s] || 0}</b></li>)}
            </ul>
          ) : <Empty>No recommendations generated yet.</Empty>}
        </div>
      </div>
      <div className="cards-3">
        <ReportTable title="Applications by country" rows={rep.by_country} noun="Country" />
        <ReportTable title="Applications by intake" rows={rep.by_intake} noun="Intake" />
        <div className="card">
          <h3>Outcomes</h3>
          <div className="kpi-inline"><span className="value">{rep.outcomes.offer_rate_pct === null ? "—" : `${rep.outcomes.offer_rate_pct}%`}</span>
            <span className="small muted">offer rate</span></div>
          <p className="small muted" style={{ margin: ".4rem 0 0" }}>{rep.outcomes.offers} offers (received or accepted) of {plural(rep.outcomes.decided, "university decision")}{rep.outcomes.decided ? "" : " so far"}.</p>
        </div>
      </div>
      <ReportTable title="Top universities" rows={rep.by_university} noun="University" />
      <div className="card">
        <div className="card-head"><h3>Counsellor workload and activity</h3><Link className="small" to="/counsellors/">
          {d.counsellor_workload_total > rows.length ? `All ${d.counsellor_workload_total} counsellors →` : "Manage counsellors →"}</Link></div>
        {d.counsellor_workload_total > rows.length && <p className="small muted" style={{ marginTop: "-.5rem" }}>The {rows.length} busiest by capacity used.</p>}
        {rows.length ? (
          <div className="table-wrap"><table>
            <thead><tr><th>Counsellor</th><th>Assigned</th><th style={{ width: "22%" }}>Utilisation</th><th>Open applications</th><th>Documents to review</th>
              <th>Sessions (30 days)</th><th>Follow-ups</th></tr></thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id || c.name}>
                  <td className="name">{c.name}{!c.is_active && <span className="badge" style={{ marginLeft: ".4rem" }}>Inactive</span>}</td>
                  <td>{c.assigned} / {c.capacity}</td>
                  <td><ProgressBar pct={c.utilisation_pct} name={`${c.name} utilisation`} /></td>
                  <td>{c.open_applications}</td><td>{c.documents_to_review}</td><td>{c.sessions_completed_30d}</td>
                  <td>{c.follow_ups_pending}{c.follow_ups_overdue ? <> · <Overdue n={c.follow_ups_overdue} /></> : null}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        ) : <p className="empty">No counsellors yet. <Link to="/counsellors/?new=1">Add the first one</Link>.</p>}
      </div>
    </>
  );
}

export default function Dashboard() {
  const [filters, update] = useQueryState(FILTER_STATE);
  const { country, intake_id: intakeId, counsellor_id: counsellorId } = filters;
  const { data, error, loading, reload } = useLoad(
    () => api("/dashboard/", { query: { country, intake_id: intakeId, counsellor_id: counsellorId } }), [country, intakeId, counsellorId]);
  let body;
  if (error) body = <><Head title="Dashboard" /><ErrorAlert error={error} onRetry={reload}>Could not load your dashboard. {error.message}</ErrorAlert></>;
  else if (!data) body = <><Head title="Dashboard" /><Loading text="Loading your dashboard…" /></>;
  else if (data.role === "student") body = <StudentDashboard d={data} />;
  else if (data.role === "counsellor") body = <CounsellorDashboard d={data} filters={filters} update={update} />;
  else body = <AdminDashboard d={data} filters={filters} update={update} />;
  return <AppShell title="Dashboard" crumb="Dashboard"><div aria-busy={loading || undefined}>{body}</div></AppShell>;
}
