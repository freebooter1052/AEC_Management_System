/* University & course search (SRS 4.4): search universities or courses, filter by country/ranking, paginate. */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppShell from "../components/Shell";
import Drawer from "../components/Drawer";
import { TabList, tabPanel } from "../components/Tabs";
import { useAuth } from "../components/auth";
import { useToast } from "../components/Toast";
import { ErrorAlert, Loading, Pager } from "../components/ui";
import { api } from "../lib/api";
import { plural } from "../lib/format";
import { rankingText } from "../lib/labels";
import { useDebounced } from "../lib/useDebounced";
import { useLoad } from "../lib/useLoad";
import { useQueryState } from "../lib/useQueryState";

const LIST_STATE = {
  view: { default: "universities", allowed: ["universities", "courses"] },
  q: { default: "" },
  country: { default: "" },
  max_rank: { default: "", allowed: ["", "10", "25", "50", "100"] },
  sort: { default: "rank", allowed: ["rank", "name"] },
  page: { default: 1, type: "page" },
};

const planLink = (universityId, courseId) => `/applications/?new=1&university_id=${encodeURIComponent(universityId)}&course_id=${encodeURIComponent(courseId)}`;

function CoursesDrawer({ u, onClose }) {
  return (
    <Drawer title={u.name} onClose={onClose}>
      <p className="muted">{u.country} · {rankingText(u.rank)}</p>
      {u.courses.length ? (
        <>
          <p className="small muted">{plural(u.courses.length, "course")} offered</p>
          <ul className="course-list">
            {u.courses.map((c) => (
              <li key={c.id}>
                <span>{c.title || c.name || "Untitled course"}
                  {(c.cluster || c.level) && <span className="small muted" style={{ display: "block" }}>{c.cluster || c.level}</span>}
                </span>
                <Link className="btn btn-outline btn-sm" onClick={onClose} to={planLink(u.id, c.id)} aria-label={`Plan an application for ${c.title || c.name}`}>Plan application</Link>
              </li>
            ))}
          </ul>
        </>
      ) : <div className="alert alert-info">No courses are listed for this university yet.</div>}
    </Drawer>
  );
}

function ContextBar({ me, countryName }) {
  const p = me.preferences || {};
  const preferred = (p.countries || []).map(countryName);
  return (
    <div className="context-bar">
      <span>Searching for <b>{me.full_name}</b></span>
      {me.academic?.cgpa ? <span>CGPA <b>{me.academic.cgpa}</b>{me.academic.gpa_scale ? ` / ${me.academic.gpa_scale}` : ""}</span> : null}
      <span>Targets <b>{preferred.join(", ") || "not set"}</b></span>
      {p.intake && <span>Intake <b>{p.intake}</b></span>}
      {p.budget?.max ? <span>Budget <b>{`${p.budget.min ?? 0}–${p.budget.max} ${p.budget.currency}`}</b></span> : null}
      <Link to="/profile/" style={{ marginLeft: "auto" }}>Edit preferences →</Link>
    </div>
  );
}

function UniversityResults({ data, preferred, onOpen, countryName }) {
  if (!data.results.length) return <p className="empty" style={{ gridColumn: "1/-1" }}>No universities match these filters. Try another name or remove a filter.</p>;
  return data.results.map((u) => (
    <article className="card uni" key={u.id}>
      <div className={`rank${u.rank ? "" : " rank-missing"}`}>{rankingText(u.rank)}</div>
      <h3>{u.name}</h3>
      <div className="meta">
        <span className="badge">{countryName(u.country)}</span>
        {preferred.includes(String(u.country).toLowerCase()) && <span className="badge badge-brand">In your target countries</span>}
      </div>
      <div className="foot"><button type="button" className="btn btn-outline btn-sm" onClick={() => onOpen(u.id)} aria-label={`View courses at ${u.name}`}>View courses</button></div>
    </article>
  ));
}

function CourseResults({ data, preferred, onOpen, countryName }) {
  if (!data.results.length) return <p className="empty">No courses match. Try a broader subject such as “data” or “engineering”, or remove the country filter.</p>;
  return (
    <ul className="course-results">
      {data.results.map((c) => (
        <li key={c.id} className="course-result">
          <div>
            <div className="name">{c.title || c.canonical_name}</div>
            <div className="small muted">{[c.cluster, c.canonical_name && c.canonical_name !== c.title ? `also known as ${c.canonical_name}` : ""].filter(Boolean).join(" · ")}</div>
            <div className="small">
              <button type="button" className="link-btn" onClick={() => onOpen(c.university.id)}>{c.university.name || "University"}</button>
              {" · "}{countryName(c.university.country)}{" · "}{rankingText(c.university.rank)}
              {preferred.includes(String(c.university.country).toLowerCase()) && <> <span className="badge badge-brand">In your target countries</span></>}
            </div>
          </div>
          <Link className="btn btn-outline btn-sm" to={planLink(c.university.id, c.id)} aria-label={`Plan an application for ${c.title} at ${c.university.name}`}>Plan application</Link>
        </li>
      ))}
    </ul>
  );
}

export default function Universities() {
  const { user } = useAuth();
  const toast = useToast();
  const [state, update] = useQueryState(LIST_STATE);
  const { view, q, country, max_rank: maxRank, sort, page } = state;
  const [search, setSearch] = useState(q);
  const typed = useDebounced(search.trim());
  const [countries, setCountries] = useState([]);
  const [names, setNames] = useState({});
  const [me, setMe] = useState(null);
  const [open, setOpen] = useState(null);
  const isStudent = user.role === "student";
  const courses = view === "courses";

  useEffect(() => { if (typed !== q) update({ q: typed, page: 1 }); }, [typed]); // only when the debounced text changes
  useEffect(() => {
    api("/universities/countries/").then(setCountries, (err) => toast(err.message, "error"));
    api("/countries/").then((rows) => setNames(Object.fromEntries(rows.map((r) => [r.catalogue_name, r.name]))), () => { /* names only make labels friendlier */ });
    if (isStudent) api("/students/me/").then(setMe, () => { /* context bar is optional */ });
  }, [isStudent, toast]);

  const { data: loaded, error, loading, reload } = useLoad(() => (courses
    ? api("/universities/courses/", { query: { page, page_size: 20, q, country } })
    : api("/universities/", { query: { page, page_size: 12, q, country, max_rank: maxRank, sort } })).then((d) => ({ ...d, view })), [view, page, q, country, maxRank, sort]);
  const data = loaded?.view === view ? loaded : null; // never render one view's rows with the other's layout

  const preferred = (me?.preferences?.countries || []).map((c) => c.toLowerCase());
  const countryName = (c) => names[c] || c;

  async function showCourses(id) {
    try { setOpen(await api(`/universities/${encodeURIComponent(id)}/`)); } catch (err) { toast(err.message, "error"); }
  }

  const noun = courses ? "course" : "university";
  return (
    <AppShell title="Universities" crumb="Universities & courses">
      <div className="page-head">
        <div>
          <h1>University &amp; course search</h1>
          <p className="muted">Search universities or courses in the catalogue. Open a university to see all its courses, and plan an application straight from a course.</p>
        </div>
      </div>
      {me && <ContextBar me={me} countryName={countryName} />}
      <div className="card">
        <TabList id="search-view" label="Search for" tabs={[["universities", "Universities"], ["courses", "Courses"]]} selected={view}
          onSelect={(v) => update({ view: v, page: 1 })} panelFor={() => "results"} />
        <div className="card-head">
          <div className="toolbar">
            <input type="search" placeholder={courses ? "Search courses or subjects…" : "Search universities…"} aria-label={courses ? "Search courses by title or subject" : "Search universities by name"}
              value={search} onChange={(e) => setSearch(e.target.value)} />
            <select aria-label="Country" value={country} onChange={(e) => update({ country: e.target.value, page: 1 })}>
              <option value="">All countries</option>
              {countries.map((c) => <option key={c.country} value={c.country}>{countryName(c.country)} ({plural(c.count, "university")})</option>)}
            </select>
            {!courses && <>
              <select aria-label="Ranking" value={maxRank} onChange={(e) => update({ max_rank: e.target.value, page: 1 })}>
                <option value="">Any ranking</option><option value="10">Top 10</option><option value="25">Top 25</option><option value="50">Top 50</option><option value="100">Top 100</option>
              </select>
              <select aria-label="Sort" value={sort} onChange={(e) => update({ sort: e.target.value, page: 1 })}>
                <option value="rank">Sort: ranking</option><option value="name">Sort: name A–Z</option>
              </select>
            </>}
          </div>
          <span className="small muted" aria-live="polite">{data && !loading ? plural(data.count, noun) : ""}</span>
        </div>
        <div role="tabpanel" id="search-view-panel-results" aria-labelledby={`search-view-tab-${view}`} aria-busy={loading || undefined}>
          {error ? <ErrorAlert error={error} onRetry={reload}>Could not load the {courses ? "courses" : "universities"}. {error.message}</ErrorAlert>
            : !data ? <Loading text={`Loading ${courses ? "courses" : "universities"}…`} />
            : courses ? <CourseResults data={data} preferred={preferred} onOpen={showCourses} countryName={countryName} />
            : <div className="uni-grid"><UniversityResults data={data} preferred={preferred} onOpen={showCourses} countryName={countryName} /></div>}
          <Pager data={data} noun={noun} onPage={(p) => { update({ page: p }); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
        </div>
      </div>
      {open && <CoursesDrawer u={open} onClose={() => setOpen(null)} />}
    </AppShell>
  );
}
