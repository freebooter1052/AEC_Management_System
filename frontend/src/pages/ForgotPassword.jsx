/* Forgot password: email -> 6-digit code -> new password. Works for every role. */
import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import AuthLayout from "../components/AuthLayout";
import { useAuth } from "../components/auth";
import { Field } from "../components/ui";
import { api } from "../lib/api";
import { fieldErrors } from "../lib/form";
import { passwordProblem } from "../lib/passwords";
import { useSubmit } from "../lib/useSubmit";

const RESEND_SECONDS = 60;

export default function ForgotPassword() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState("email"); // email -> code -> password
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState({});
  const [notice, setNotice] = useState(null);
  const [busy, run] = useSubmit();
  const [wait, setWait] = useState(0);

  useEffect(() => {
    if (wait <= 0) return undefined;
    const t = setTimeout(() => setWait(wait - 1), 1000);
    return () => clearTimeout(t);
  }, [wait]);

  if (user) return <Navigate to="/dashboard/" replace />;

  async function call(path, body) {
    setErrors({});
    try {
      return await api(path, { method: "POST", body });
    } catch (err) {
      setErrors(err.status === 400 ? fieldErrors(err.data) : { form: err.message });
      return null;
    }
  }

  const sendCode = (e) => {
    e?.preventDefault();
    return run(async () => {
      if (!email.trim()) { setErrors({ email: "Enter the email address of your account." }); return; }
      const res = await call("/auth/forgot-password/", { email: email.trim() });
      if (!res) return;
      setWait(RESEND_SECONDS);
      setCode("");
      setNotice(`We sent a 6-digit code to ${email.trim()} if an account exists for it. It is valid for 10 minutes.`);
      setStep("code");
    });
  };

  const verifyCode = (e) => {
    e.preventDefault();
    return run(async () => {
      if (code.length !== 6) { setErrors({ code: "Enter the 6-digit code from the email." }); return; }
      const res = await call("/auth/verify-reset-code/", { email: email.trim(), code });
      if (!res) return;
      setNotice(null);
      setStep("password");
    });
  };

  const resetPassword = (e) => {
    e.preventDefault();
    return run(async () => {
      const problem = passwordProblem(password);
      if (problem) { setErrors({ new_password: problem }); return; }
      if (password !== confirm) { setErrors({ confirm: "The two passwords do not match." }); return; }
      setErrors({});
      try {
        await api("/auth/reset-password/", { method: "POST", body: { email: email.trim(), code, new_password: password } });
        navigate("/login/?reset=1", { replace: true });
      } catch (err) {
        const fields = err.status === 400 ? fieldErrors(err.data) : { form: err.message };
        if (fields.code) { // the code stopped being valid meanwhile: go back to ask for a new one
          setStep("code");
          setErrors({ code: fields.code });
        } else setErrors(fields);
      }
    });
  };

  return (
    <AuthLayout title="Reset password">
      <div className="auth-card">
        <h2 style={{ fontSize: "1.6rem" }}>Reset your password</h2>
        {step === "email" && <p className="muted">Enter the email address of your account and we will send you a 6-digit code.</p>}
        {step === "code" && <p className="muted">Enter the code we emailed you.</p>}
        {step === "password" && <p className="muted">Code verified. Choose a new password.</p>}

        {notice && <div className="alert alert-info" role="status">{notice}</div>}
        {errors.form && <div className="alert alert-error" role="alert">{errors.form}</div>}

        {step === "email" && (
          <form onSubmit={sendCode} noValidate>
            <Field label="Email" error={errors.email}>
              <input type="email" autoComplete="email" autoFocus required value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <button className="btn btn-primary btn-block" type="submit" disabled={busy}>{busy ? "Sending…" : "Send code"}</button>
          </form>
        )}

        {step === "code" && (
          <form onSubmit={verifyCode} noValidate>
            <Field label="6-digit code" error={errors.code}>
              <input inputMode="numeric" autoComplete="one-time-code" autoFocus maxLength={6} placeholder="123456"
                style={{ letterSpacing: ".4em", fontSize: "1.3rem", textAlign: "center" }}
                value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} />
            </Field>
            <button className="btn btn-primary btn-block" type="submit" disabled={busy}>{busy ? "Checking…" : "Verify code"}</button>
            <p className="muted small" style={{ marginTop: "1rem" }}>
              Did not get it? Check your spam folder or{" "}
              {wait > 0 ? `request a new code in ${wait}s.` : <button type="button" className="link-btn" onClick={sendCode} disabled={busy}>send a new code</button>}
              {" "}<button type="button" className="link-btn" onClick={() => { setStep("email"); setNotice(null); setErrors({}); }}>Use a different email</button>
            </p>
          </form>
        )}

        {step === "password" && (
          <form onSubmit={resetPassword} noValidate>
            <Field label="New password" hint="At least 8 characters, with letters and numbers." error={errors.new_password}>
              <input type="password" autoComplete="new-password" autoFocus required value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <Field label="Confirm new password" error={errors.confirm}>
              <input type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            </Field>
            <button className="btn btn-primary btn-block" type="submit" disabled={busy}>{busy ? "Saving…" : "Change password"}</button>
          </form>
        )}

        <p className="muted small" style={{ marginTop: "1.2rem" }}><Link to="/login/">Back to sign in</Link></p>
      </div>
    </AuthLayout>
  );
}
