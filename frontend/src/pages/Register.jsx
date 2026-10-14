import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import AuthLayout from "../components/AuthLayout";
import { useAuth } from "../components/auth";
import { Field } from "../components/ui";
import { api } from "../lib/api";
import { trimStrings, useForm } from "../lib/form";

const LEVELS = ["Bachelors", "Masters", "MBA", "PhD", "Diploma", "Certificate"];

export default function Register() {
  const { user, signIn } = useAuth();
  const navigate = useNavigate();
  const form = useForm({ dial_code: "+91", intended_level: "Masters" });
  const { bind, errors } = form;
  const [busy, setBusy] = useState(false);
  const [alert, setAlert] = useState("");

  if (user) return <Navigate to="/dashboard/" replace />;

  async function submit(e) {
    e.preventDefault();
    setAlert("");
    const body = trimStrings(form.values);
    if (body.password !== body.password2) { form.showErrors({ password2: ["Passwords do not match."] }); return; }
    delete body.password2;
    setBusy(true);
    try {
      const data = await api("/auth/register/", { method: "POST", body });
      signIn(data.token, data.user);
      navigate("/profile/?welcome=1", { replace: true });
    } catch (err) {
      if (err.status === 400) form.showErrors(err.data);
      setAlert(err.status === 400 ? "Please correct the highlighted fields." : err.message);
      setBusy(false);
    }
  }

  return (
    <AuthLayout title="Register">
      <div className="auth-card wide">
        <h2 style={{ fontSize: "1.6rem" }}>Register as an applicant</h2>
        <p className="muted">Create your student account. You can complete your academic profile and preferences after signing in.</p>
        {alert && <div className="alert alert-error" role="alert">{alert}</div>}
        <form onSubmit={submit} noValidate style={{ marginTop: "1.2rem" }} ref={form.ref}>
          <div className="grid grid-2">
            <Field label="Legal first name" error={errors.first_name}><input autoComplete="given-name" required {...bind("first_name")} /></Field>
            <Field label="Legal last name" error={errors.last_name}><input autoComplete="family-name" required {...bind("last_name")} /></Field>
            <Field label="Email" className="span-2" error={errors.email}><input type="email" autoComplete="email" required {...bind("email")} /></Field>
            <div className="field span-2">
              <label htmlFor="phone">Mobile number</label>
              <div className="input-group">
                <input placeholder="+91" aria-label="Country dial code" {...bind("dial_code")} />
                <input id="phone" inputMode="numeric" placeholder="9876543210" autoComplete="tel-national" {...bind("phone")} />
              </div>
              {(errors.phone || errors.dial_code) && <div className="error">{errors.dial_code || errors.phone}</div>}
            </div>
            <Field label="Citizenship" error={errors.citizenship}><input placeholder="India" autoComplete="country-name" {...bind("citizenship")} /></Field>
            <Field label="Intended study level" error={errors.intended_level}>
              <select {...bind("intended_level")}>
                <option value="">Select…</option>
                {LEVELS.map((l) => <option key={l}>{l}</option>)}
              </select>
            </Field>
            <Field label="Password" hint="At least 8 characters, with letters and numbers." error={errors.password}>
              <input type="password" autoComplete="new-password" required {...bind("password")} />
            </Field>
            <Field label="Confirm password" error={errors.password2}><input type="password" autoComplete="new-password" required {...bind("password2")} /></Field>
          </div>
          <button className="btn btn-primary btn-block" type="submit" disabled={busy}>{busy ? "Creating account…" : "Create account"}</button>
        </form>
        <p className="muted small" style={{ marginTop: "1.2rem" }}>Already registered? <Link to="/login/">Sign in</Link></p>
      </div>
    </AuthLayout>
  );
}
