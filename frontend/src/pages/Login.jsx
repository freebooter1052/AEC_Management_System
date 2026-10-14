import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import AuthLayout from "../components/AuthLayout";
import { useAuth } from "../components/auth";
import { Field } from "../components/ui";
import { api } from "../lib/api";

const PORTALS = [["student", "Student"], ["counsellor", "Counsellor"], ["admin", "Administrator"]];

export default function Login() {
  const { user, signIn } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [portal, setPortal] = useState("student");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [alert, setAlert] = useState(params.get("expired") ? { kind: "info", text: "Your session has ended. Please sign in again." } : null);

  if (user) return <Navigate to="/dashboard/" replace />;

  async function submit(e) {
    e.preventDefault();
    if (!email.trim() || !password) { setAlert({ kind: "error", text: "Enter your email and password." }); return; }
    setBusy(true);
    try {
      const data = await api("/auth/login/", { method: "POST", body: { email: email.trim(), password, role: portal } });
      signIn(data.token, data.user);
      const next = params.get("next");
      navigate(next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard/", { replace: true });
    } catch (err) {
      setAlert({ kind: "error", text: err.message });
      setBusy(false);
    }
  }

  return (
    <AuthLayout title="Sign in">
      <div className="auth-card">
        <h2 style={{ fontSize: "1.6rem" }}>Sign in</h2>
        <p className="muted">Choose your portal. Your role is checked against your account.</p>
        <div className="portal-tabs" role="tablist" aria-label="Portal">
          {PORTALS.map(([role, label]) => (
            <button key={role} type="button" role="tab" aria-selected={portal === role} onClick={() => setPortal(role)}>{label}</button>
          ))}
        </div>
        {alert && <div className={`alert alert-${alert.kind}`} role="alert">{alert.text}</div>}
        <form onSubmit={submit} noValidate>
          <Field label="Email"><input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Field label="Password"><input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
          <button className="btn btn-primary btn-block" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
        {portal === "student"
          ? <p className="muted small" style={{ marginTop: "1.2rem" }}>New student? <Link to="/register/">Create your applicant account</Link></p>
          : <p className="muted small" style={{ marginTop: "1.2rem" }}>Counsellor and administrator accounts are created by an administrator.</p>}
      </div>
    </AuthLayout>
  );
}
