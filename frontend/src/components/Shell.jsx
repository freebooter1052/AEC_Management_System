import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import { initials } from "../lib/format";

const ICONS = {
  dashboard: <path d="M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z" />,
  profile: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  students: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><circle cx="17.5" cy="9" r="2.5" /><path d="M16 14.2a5 5 0 0 1 6 4.8" /></>,
  counsellors: <><path d="M4 5h16v11H8l-4 4z" /><path d="M8 9h8M8 12h5" /></>,
  universities: <><path d="M3 9l9-5 9 5-9 5z" /><path d="M7 11.5V16c0 1.5 2.2 3 5 3s5-1.5 5-3v-4.5" /></>,
  applications: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 8h6M9 12h6M9 16h3" /></>,
  documents: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /><path d="M9.5 14.5l2 2 3.5-4" /></>,
  counselling: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /><path d="M8 14h3" /></>,
};

const NAV = {
  student: [["dashboard", "Dashboard", "/dashboard/"], ["profile", "My profile", "/profile/"], ["universities", "Universities", "/universities/"],
    ["applications", "Applications", "/applications/"], ["documents", "Documents", "/documents/"], ["counselling", "Counselling", "/counselling/"]],
  counsellor: [["dashboard", "Dashboard", "/dashboard/"], ["students", "My students", "/students/"], ["applications", "Applications", "/applications/"],
    ["documents", "Documents", "/documents/"], ["counselling", "Counselling", "/counselling/"], ["universities", "Universities", "/universities/"],
    ["counsellors", "My profile", "/counsellors/"]],
  admin: [["dashboard", "Dashboard", "/dashboard/"], ["students", "Students", "/students/"], ["counsellors", "Counsellors", "/counsellors/"],
    ["applications", "Applications", "/applications/"], ["documents", "Documents", "/documents/"], ["counselling", "Counselling", "/counselling/"],
    ["universities", "Universities", "/universities/"]],
};
export const ROLE_LABEL = { student: "Student", counsellor: "Counsellor", admin: "Administrator" };

export function usePageTitle(title) {
  useEffect(() => { document.title = `${title} · AEC Admissions`; }, [title]);
}

/** Signed-in page frame (sidebar + top bar). Only rendered inside RequireAuth, so `user` is always set. */
export default function AppShell({ title, crumb, children }) {
  const { user, signOut } = useAuth();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  usePageTitle(title);
  useEffect(() => setMenuOpen(false), [location.pathname]);

  const here = location.pathname;
  const name = user.full_name || user.email;
  return (
    <div className="shell">
      <aside className={"sidebar" + (menuOpen ? " open" : "")} aria-label="Main navigation">
        <Link className="brand" to="/dashboard/"><span className="brand-mark">AE</span>AEC Admissions</Link>
        <nav className="nav">
          {(NAV[user.role] || []).map(([icon, label, href]) => {
            const active = here === href || (href !== "/dashboard/" && here.startsWith(href));
            return (
              <Link key={href} to={href} className={active ? "active" : ""} aria-current={active ? "page" : undefined}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICONS[icon]}</svg>
                {label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div>
        <header className="topbar">
          <button className="btn btn-outline btn-sm menu-toggle" aria-label="Toggle navigation" onClick={() => setMenuOpen((o) => !o)}>Menu</button>
          <div className="muted small" id="crumb">{crumb}</div>
          <div className="who">
            <div className="meta" style={{ textAlign: "right" }}>
              <div style={{ fontWeight: 600 }}>{name}</div>
              <div className="small muted">{user.email}</div>
            </div>
            <span className="role-badge">{ROLE_LABEL[user.role] || user.role}</span>
            <div className="avatar" aria-hidden="true">{initials(name)}</div>
            <button className="btn btn-outline btn-sm" onClick={signOut}>Sign out</button>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
