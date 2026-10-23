import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import ChangePasswordDrawer from "./ChangePassword";
import { lockScroll } from "./Dialog";
import NotificationBell from "./NotificationBell";
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
  recommendations: <><path d="M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.4 6.8 19.1l1-5.8L3.5 9.2l5.9-.9z" /></>,
  writing: <><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="M13.5 6.5l4 4" /><path d="M14 20h6" /></>,
};

const NAV = {
  student: [["dashboard", "Dashboard", "/dashboard/"], ["profile", "My profile", "/profile/"], ["recommendations", "Recommendations", "/recommendations/"],
    ["universities", "Universities", "/universities/"], ["applications", "Applications", "/applications/"], ["writing", "SOP & LOR", "/writing/"], ["documents", "Documents", "/documents/"], ["counselling", "Counselling", "/counselling/"]],
  counsellor: [["dashboard", "Dashboard", "/dashboard/"], ["students", "My students", "/students/"], ["recommendations", "Recommendations", "/recommendations/"],
    ["applications", "Applications", "/applications/"], ["writing", "SOP & LOR", "/writing/"],
    ["documents", "Documents", "/documents/"], ["counselling", "Counselling", "/counselling/"], ["universities", "Universities", "/universities/"],
    ["counsellors", "My profile", "/counsellors/"]],
  admin: [["dashboard", "Dashboard", "/dashboard/"], ["students", "Students", "/students/"], ["counsellors", "Counsellors", "/counsellors/"],
    ["applications", "Applications", "/applications/"], ["writing", "SOP & LOR", "/writing/"], ["documents", "Documents", "/documents/"], ["counselling", "Counselling", "/counselling/"],
    ["recommendations", "Recommendations", "/recommendations/"], ["universities", "Universities", "/universities/"]],
};
const PROFILE_LINK = { student: "/profile/", counsellor: "/counsellors/" };
export const ROLE_LABEL = { student: "Student", counsellor: "Counsellor", admin: "Administrator" };

export function usePageTitle(title) {
  useEffect(() => { document.title = `${title} · AEC Admissions`; }, [title]);
}

const isNarrow = () => window.matchMedia("(max-width: 900px)").matches;

/** Account menu (WAI-ARIA menu button): arrow keys, Home/End, Escape returns focus to the avatar. */
function AccountMenu({ user, onChangePassword, onSignOut }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const buttonRef = useRef(null);
  const menuRef = useRef(null);
  const focusOnOpen = useRef("first");
  const name = user.full_name || user.email;
  const items = () => [...(menuRef.current?.querySelectorAll('[role="menuitem"]') || [])];

  useEffect(() => {
    if (!open) return undefined;
    const list = items();
    (focusOnOpen.current === "last" ? list[list.length - 1] : list[0])?.focus();
    const onDown = (e) => { if (!rootRef.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const openWith = (where) => { focusOnOpen.current = where; setOpen(true); };
  const close = (refocus = true) => { setOpen(false); if (refocus) buttonRef.current?.focus(); };

  function onButtonKey(e) {
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") { e.preventDefault(); openWith("first"); }
    else if (e.key === "ArrowUp") { e.preventDefault(); openWith("last"); }
  }
  function onMenuKey(e) {
    const list = items();
    const i = list.indexOf(document.activeElement);
    const go = (n) => { e.preventDefault(); list[(n + list.length) % list.length]?.focus(); };
    if (e.key === "ArrowDown") go(i + 1);
    else if (e.key === "ArrowUp") go(i - 1);
    else if (e.key === "Home") go(0);
    else if (e.key === "End") go(list.length - 1);
    else if (e.key === "Escape") { e.preventDefault(); close(); }
    else if (e.key === "Tab") close(false);
  }
  const pick = (fn) => () => { setOpen(false); fn(); };

  return (
    <div className="account" ref={rootRef}>
      <button ref={buttonRef} type="button" className="account-btn" id="account-button" aria-haspopup="menu" aria-expanded={open} aria-controls="account-menu"
        aria-label={`Account menu for ${name}`} onClick={() => (open ? close(false) : openWith("first"))} onKeyDown={onButtonKey}>
        <span className="avatar" aria-hidden="true">{initials(name)}</span>
        <span className="role-badge">{ROLE_LABEL[user.role] || user.role}</span>
      </button>
      {open && (
        <div className="account-menu" id="account-menu" role="menu" aria-labelledby="account-button" ref={menuRef} onKeyDown={onMenuKey}>
          <div className="account-head" role="presentation">
            <span className="avatar avatar-lg" aria-hidden="true">{initials(name)}</span>
            <div>
              <div className="account-name">{name}</div>
              <div className="small muted account-email">{user.email}</div>
              <span className="role-badge">{ROLE_LABEL[user.role] || user.role}</span>
            </div>
          </div>
          {PROFILE_LINK[user.role] && <Link role="menuitem" tabIndex={-1} className="account-item" to={PROFILE_LINK[user.role]} onClick={() => setOpen(false)}>My profile</Link>}
          <button type="button" role="menuitem" tabIndex={-1} className="account-item" onClick={pick(onChangePassword)}>Change password</button>
          <button type="button" role="menuitem" tabIndex={-1} className="account-item account-out" onClick={pick(onSignOut)}>Sign out</button>
        </div>
      )}
    </div>
  );
}

/** Signed-in page frame (sidebar + top bar). Only rendered inside RequireAuth, so `user` is always set. */
export default function AppShell({ title, crumb, children }) {
  const { user, signOut } = useAuth();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const toggleRef = useRef(null);
  usePageTitle(title);
  useEffect(() => { setMenuOpen(false); }, [location.pathname]);

  // Mobile navigation is an overlay: lock the page behind it, close on Escape and return focus to "Menu".
  useEffect(() => {
    if (!menuOpen || !isNarrow()) return undefined;
    const unlock = lockScroll();
    document.querySelector(".sidebar .nav a")?.focus();
    const onKey = (e) => { if (e.key === "Escape") { setMenuOpen(false); toggleRef.current?.focus(); } };
    document.addEventListener("keydown", onKey);
    return () => { unlock(); document.removeEventListener("keydown", onKey); };
  }, [menuOpen]);

  const here = location.pathname;
  return (
    <div className="shell">
      <a className="skip-link" href="#main">Skip to content</a>
      <aside id="sidebar" className={"sidebar" + (menuOpen ? " open" : "")} aria-label="Main navigation">
        <Link className="brand" to="/dashboard/"><span className="brand-mark" aria-hidden="true">AE</span>AEC Admissions</Link>
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
      {menuOpen && <div className="nav-backdrop" aria-hidden="true" onClick={() => { setMenuOpen(false); toggleRef.current?.focus(); }} />}
      <div className="shell-main">
        <header className="topbar">
          <button ref={toggleRef} type="button" className="btn btn-outline btn-sm menu-toggle" aria-controls="sidebar" aria-expanded={menuOpen}
            onClick={() => setMenuOpen((o) => !o)}>{menuOpen ? "Close menu" : "Menu"}</button>
          <div className="muted small" id="crumb">{crumb}</div>
          <div className="topbar-actions">
            <NotificationBell />
            <AccountMenu user={user} onChangePassword={() => setChangingPassword(true)} onSignOut={signOut} />
          </div>
        </header>
        <main className="content" id="main" tabIndex={-1}>{children}</main>
      </div>
      {changingPassword && <ChangePasswordDrawer onClose={() => { setChangingPassword(false); setTimeout(() => document.getElementById("account-button")?.focus(), 0); }} />}
    </div>
  );
}
