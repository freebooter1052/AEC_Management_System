/* University search (SRS 4.4): search, filter by country/ranking, paginate. */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppShell from "../components/Shell";
import Drawer from "../components/Drawer";
import { useAuth } from "../components/auth";
import { useToast } from "../components/Toast";
import { Pager } from "../components/ui";
import { api } from "../lib/api";
import { useDebounced } from "../lib/useDebounced";
import { useLoad } from "../lib/useLoad";

function CoursesDrawer({ u, onClose }) {
  return (
    <Drawer title={u.name} onClose={onClose}>
      <p className="muted">{u.country} · World ranking #{u.rank ?? "—"}</p>
      {u.courses.length ? (
        <>
          <p className="small muted">{u.courses.length} course{u.courses.length === 1 ? "" : "s"} offered</p>
          <ul className="course-list">
            {u.courses.map((c) => (
              <li key={c.id}>
                <span>{c.title || c.name || "Untitled course"}
                  {(c.cluster || c.level) && <span className="small muted" style={{ display: "block" }}>{c.cluster || c.level}</span>}
                </span>
                <Link className="btn btn-outline btn-sm" onClick={onClose}
                  to={`/applications/?new=1&university_id=${encodeURIComponent(u.id)}&course_id=${encodeURIComponent(c.id)}`}>Plan application</Link>
              </li>
            ))}
          </ul>
        </>
      ) : <div className="alert alert-info">No courses are listed for this university yet.</div>}
    </Drawer>
  );
}

function ContextBar({ me }) {
  const p = me.preferences || {};
  const preferred = p.countries || [];
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

export default function Universities() {
  const { user } = useAuth();
  const toast = useToast();
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim());
  const [filters, setFilters] = useState({ country: "", max_rank: "", sort: "rank" });
  const [page, setPage] = useState(1);
  const [countries, setCountries] = useState([]);
  const [me, setMe] = useState(null);
  const [open, setOpen] = useState(null);

  useEffect(() => setPage(1), [q, filters]);
  const isStudent = user.role === "student";
  useEffect(() => {
    api("/universities/countries/").then(setCountries, (err) => toast(err.message, "error"));
    if (isStudent) api("/students/me/").then(setMe, () => { /* context bar is optional */ });
  }, [isStudent, toast]);

  const { data, error } = useLoad(() => api("/universities/", { query: { page, page_size: 12, q, ...filters } }), [page, q, filters]);

  const preferred = (me?.preferences?.countries || []).map((c) => c.toLowerCase());
  const setFilter = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }));

  async function showCourses(id) {
    try { setOpen(await api(`/universities/${encodeURIComponent(id)}/`)); } catch (err) { toast(err.message, "error"); }
  }

  return (
    <AppShell title="Universities" crumb="Universities & courses">
      <div className="page-head">
        <div>
          <h1>University &amp; course search</h1>
          <p className="muted">Search the university catalogue and open a university to see its courses. Plan an application straight from a course.</p>
        </div>
      </div>
      {me && <ContextBar me={me} />}
      <div className="card">
        <div className="card-head">
          <div className="toolbar">
            <input type="search" placeholder="Search universities…" aria-label="Search universities" value={search} onChange={(e) => setSearch(e.target.value)} />
            <select aria-label="Country" value={filters.country} onChange={setFilter("country")}>
              <option value="">All countries</option>
              {countries.map((c) => <option key={c.country} value={c.country}>{c.country} ({c.count})</option>)}
            </select>
            <select aria-label="Ranking" value={filters.max_rank} onChange={setFilter("max_rank")}>
              <option value="">Any ranking</option><option value="10">Top 10</option><option value="25">Top 25</option><option value="50">Top 50</option><option value="100">Top 100</option>
            </select>
            <select aria-label="Sort" value={filters.sort} onChange={setFilter("sort")}>
              <option value="rank">Sort: ranking</option><option value="name">Sort: name A–Z</option>
            </select>
          </div>
          <span className="small muted">{data ? `${data.count} universit${data.count === 1 ? "y" : "ies"}` : ""}</span>
        </div>
        <div className="uni-grid">
          {error ? <div className="alert alert-error" style={{ gridColumn: "1/-1" }}>{error.message}</div>
            : !data ? <p className="loading">Loading…</p>
            : !data.results.length ? <p className="empty" style={{ gridColumn: "1/-1" }}>No universities match these filters.</p>
            : data.results.map((u) => (
              <article className="card uni" key={u.id}>
                <div className="rank">#{u.rank ?? "—"} world ranking</div>
                <h3>{u.name}</h3>
                <div className="meta">
                  <span className="badge">{u.country}</span>
                  {preferred.includes(String(u.country).toLowerCase()) && <span className="badge badge-brand">In your target countries</span>}
                </div>
                <div className="foot"><button className="btn btn-outline btn-sm" onClick={() => showCourses(u.id)}>View courses</button></div>
              </article>
            ))}
        </div>
        <Pager data={data} onPage={(p) => { setPage(p); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
      </div>
      {open && <CoursesDrawer u={open} onClose={() => setOpen(null)} />}
    </AppShell>
  );
}
