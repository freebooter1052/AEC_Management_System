import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import AuthLayout from "../components/AuthLayout";
import { CountryPicker } from "../components/CountryPicker";
import { useAuth } from "../components/auth";
import { Field } from "../components/ui";
import { api } from "../lib/api";
import { saveErrorMessage, trimStrings, useForm } from "../lib/form";
import { passwordProblem } from "../lib/passwords";
import { useSubmit } from "../lib/useSubmit";

const LEVELS = ["Bachelors", "Masters", "MBA", "PhD", "Diploma", "Certificate"];

export default function Register() {
  const { user, signIn } = useAuth();
  const navigate = useNavigate();
  const form = useForm({ dial_code: "+91", intended_level: "Masters", citizenship: "", privacy_acknowledged: false });
  const { bind, errors } = form;
  const [busy, run] = useSubmit();
  const [alert, setAlert] = useState("");

  if (user) return <Navigate to="/dashboard/" replace />;

  const submit = (e) => {
    e.preventDefault();
    return run(async () => {
      setAlert("");
      const body = trimStrings(form.values);
      const problems = {};
      for (const [k, label] of [["first_name", "Enter your first name."], ["last_name", "Enter your last name."], ["email", "Enter your email address."]]) {
        if (!body[k]) problems[k] = [label];
      }
      const pw = passwordProblem(body.password);
      if (pw) problems.password = [pw];
      else if (body.password !== body.password2) problems.password2 = ["The two passwords do not match."];
      if (!body.privacy_acknowledged) problems.privacy_acknowledged = ["Tick the box to confirm you have read how your information is used."];
      if (Object.keys(problems).length) { form.showErrors(problems); setAlert("Please correct the highlighted fields."); return; }
      delete body.password2;
      try {
        const data = await api("/auth/register/", { method: "POST", body });
        signIn(data.token, data.user);
        navigate("/profile/?welcome=1", { replace: true });
      } catch (err) {
        if (err.status === 400) form.showErrors(err.data);
        setAlert(saveErrorMessage(err));
      }
    });
  };

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
            <Field label="Email address" className="span-2" error={errors.email}><input type="email" autoComplete="email" required {...bind("email")} /></Field>
            <div className={`field span-2${errors.phone || errors.dial_code ? " has-error" : ""}`}>
              <label htmlFor="phone">Mobile number</label>
              <div className="input-group">
                <input placeholder="+91" aria-label="Country dial code" {...bind("dial_code")} />
                <input id="phone" inputMode="numeric" placeholder="9876543210" autoComplete="tel-national" {...bind("phone")} />
              </div>
              {(errors.phone || errors.dial_code) && <div className="error">{errors.dial_code || errors.phone}</div>}
            </div>
            <Field label="Citizenship" error={errors.citizenship}>
              <CountryPicker ariaLabel="Citizenship" name="citizenship" value={form.values.citizenship} onChange={(v) => form.set("citizenship", v)} />
            </Field>
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
          <section className={`privacy-notice${errors.privacy_acknowledged ? " has-error" : ""}`} aria-labelledby="privacy-title">
            <h3 id="privacy-title">How your information is used</h3>
            <p>AEC Admissions stores the profile details you enter and the documents you upload, such as your passport, transcripts and
              test scores, to provide counselling and to prepare your university applications. They can be seen by you, the counsellor
              assigned to you, and AEC administrators.</p>
            <label className="checkbox">
              <input type="checkbox" name="privacy_acknowledged" required aria-describedby={errors.privacy_acknowledged ? "privacy-error" : undefined}
                aria-invalid={errors.privacy_acknowledged ? true : undefined} {...bind("privacy_acknowledged", "bool")} />
              I have read how my information will be used.
            </label>
            {errors.privacy_acknowledged && <div className="error" id="privacy-error">{errors.privacy_acknowledged}</div>}
          </section>
          <button className="btn btn-primary btn-block" type="submit" disabled={busy}>{busy ? "Creating account…" : "Create account"}</button>
        </form>
        <p className="muted small" style={{ marginTop: "1.2rem" }}>Already registered? <Link to="/login/">Sign in</Link></p>
      </div>
    </AuthLayout>
  );
}
