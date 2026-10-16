/* "Page not found" and "No access" screens. Neither reveals anything about the record or page that was asked for. */
import { Link, useLocation } from "react-router-dom";
import AppShell, { ROLE_LABEL, usePageTitle } from "../components/Shell";
import { useAuth } from "../components/auth";

function Message({ title, children }) {
  return (
    <div className="card status-page">
      <h1>{title}</h1>
      {children}
    </div>
  );
}

export function NotFound() {
  const { user } = useAuth();
  const location = useLocation();
  const body = (
    <Message title="Page not found">
      <p className="muted">There is no page at <code>{location.pathname}</code>. The link may be mistyped or out of date.</p>
      <div className="toolbar"><Link className="btn btn-primary" to={user ? "/dashboard/" : "/login/"}>{user ? "Go to your dashboard" : "Go to sign in"}</Link></div>
    </Message>
  );
  if (user) return <AppShell title="Page not found" crumb="Page not found">{body}</AppShell>;
  return <PublicFrame title="Page not found">{body}</PublicFrame>;
}

function PublicFrame({ title, children }) {
  usePageTitle(title);
  return <main className="public-status" id="main">{children}</main>;
}

/** Signed in, but this page is for another role. The API refuses the data as well; this only explains why. */
export function AccessDenied() {
  const { user } = useAuth();
  return (
    <AppShell title="No access" crumb="No access">
      <Message title="This page is not available to you">
        <p className="muted">You are signed in as {/^[AEIOU]/.test(ROLE_LABEL[user.role] || "") ? "an" : "a"} {(ROLE_LABEL[user.role] || user.role).toLowerCase()}, and this page is only for other roles.
          If you think you should have access, contact your administrator.</p>
        <div className="toolbar"><Link className="btn btn-primary" to="/dashboard/">Go to your dashboard</Link></div>
      </Message>
    </AppShell>
  );
}
