/* Change password (POST /api/auth/change-password/) for any signed-in role, opened from the account menu. */
import { useState } from "react";
import Drawer from "./Drawer";
import { useAuth } from "./auth";
import { useToast } from "./Toast";
import { Field } from "./ui";
import { api } from "../lib/api";
import { fieldErrors } from "../lib/form";
import { MIN_PASSWORD, validateChange } from "../lib/passwords";
import { useSubmit } from "../lib/useSubmit";

export default function ChangePasswordDrawer({ onClose }) {
  const { refreshSession } = useAuth();
  const toast = useToast();
  const [v, setV] = useState({ current: "", next: "", confirm: "" });
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [busy, run] = useSubmit();
  const bind = (k) => ({ value: v[k], onChange: (e) => setV((s) => ({ ...s, [k]: e.target.value })) });

  const save = () => run(async () => {
    setFormError("");
    const problems = validateChange(v);
    setErrors(problems);
    if (Object.keys(problems).length) {
      document.querySelector(".drawer [aria-invalid=true]")?.focus();
      return;
    }
    try {
      // The API revokes every older token and returns a fresh one, so this browser stays signed in.
      const data = await api("/auth/change-password/", { method: "POST", body: { current_password: v.current, new_password: v.next } });
      refreshSession(data.token, data.user);
      setV({ current: "", next: "", confirm: "" });
      toast("Your password has been changed. Other devices have been signed out.");
      onClose();
    } catch (err) {
      if (err.status === 400) {
        setErrors(fieldErrors(err.data));
        if (!err.hasFieldErrors) setFormError(err.message);
      } else setFormError(err.message);
    }
  });

  return (
    <Drawer title="Change password" onClose={onClose} busy={busy} footer={<>
      <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button type="submit" form="change-password-form" className="btn btn-primary" disabled={busy}>{busy ? "Changing…" : "Change password"}</button>
    </>}>
      <p className="muted small">Changing your password signs you out on every other device. You stay signed in here.</p>
      {formError && <div className="alert alert-error" role="alert">{formError}</div>}
      <form id="change-password-form" noValidate onSubmit={(e) => { e.preventDefault(); save(); }}>
        <Field label="Current password" error={errors.current_password}>
          <input type="password" autoComplete="current-password" required {...bind("current")} />
        </Field>
        <Field label="New password" hint={`At least ${MIN_PASSWORD} characters, with letters and numbers.`} error={errors.new_password}>
          <input type="password" autoComplete="new-password" required {...bind("next")} />
        </Field>
        <Field label="Confirm new password" error={errors.confirm}>
          <input type="password" autoComplete="new-password" required {...bind("confirm")} />
        </Field>
      </form>
    </Drawer>
  );
}
