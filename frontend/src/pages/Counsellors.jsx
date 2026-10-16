/* Counsellors: administrators manage all counsellors; a counsellor edits their own profile. */
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import AppShell from "../components/Shell";
import { ConfirmDialog } from "../components/Dialog";
import Drawer from "../components/Drawer";
import { useAuth } from "../components/auth";
import { useToast } from "../components/Toast";
import { ErrorAlert, Field, Loading, Pager, ProgressBar } from "../components/ui";
import { api } from "../lib/api";
import { initials, plural } from "../lib/format";
import { saveErrorMessage, useForm } from "../lib/form";
import { useDebounced } from "../lib/useDebounced";
import { useLoad } from "../lib/useLoad";
import { useQueryState } from "../lib/useQueryState";
import { useSubmit } from "../lib/useSubmit";

const LIST_STATE = {
  q: { default: "" },
  active: { default: "", allowed: ["", "true", "false"] },
  page: { default: 1, type: "page" },
};

const PROFILE_KEYS = ["name", "phone", "region", "specialization"];

function readForm(values, { admin, create }) {
  const keys = [...PROFILE_KEYS, ...(create ? ["email", "password"] : []), ...(admin ? ["max_students"] : []), ...(admin && !create ? ["is_active"] : [])];
  const body = {};
  for (const k of keys) {
    const v = values[k];
    if (k === "is_active") body[k] = !!v;
    else if (k === "max_students") { if (v !== "" && v != null) body[k] = Number(v); }
    else body[k] = String(v ?? "").trim();
  }
  return body;
}

function ProfileFields({ form, admin = false, create = false }) {
  const { bind, errors } = form;
  return (
    <div className="grid grid-2">
      <Field label="Full name" className="span-2" error={errors.name}><input required {...bind("name")} /></Field>
      {create && <>
        <Field label="Email (sign-in)" className="span-2" error={errors.email}><input type="email" required {...bind("email")} /></Field>
        <Field label="Initial password" className="span-2" hint="At least 8 characters with letters and numbers." error={errors.password}><input type="text" required {...bind("password")} /></Field>
      </>}
      <Field label="Phone" error={errors.phone}><input placeholder="+91 98765 43210" {...bind("phone")} /></Field>
      <Field label="Region" error={errors.region}><input placeholder="South Asia" {...bind("region")} /></Field>
      <Field label="Specialisation" className="span-2" error={errors.specialization}><input placeholder="UK & Ireland postgraduate" {...bind("specialization")} /></Field>
      {admin && <>
        <Field label="Student capacity" error={errors.max_students}><input type="number" min="1" max="500" {...bind("max_students", "number")} /></Field>
        {!create && <div className="field" style={{ justifyContent: "flex-end" }}><label className="checkbox"><input type="checkbox" {...bind("is_active", "bool")} /> Active</label></div>}
      </>}
    </div>
  );
}

function SelfView() {
  const toast = useToast();
  const { data: c, error, reload } = useLoad(() => api("/counsellors/me/"), []);
  const form = useForm({});
  const { setValues } = form;
  const [saved, setSaved] = useState("");
  const [busy, run] = useSubmit();
  useEffect(() => { if (c) setValues({ name: c.name || "", phone: c.phone || "", region: c.region || "", specialization: c.specialization || "" }); }, [c, setValues]);

  if (error) return <ErrorAlert error={error} onRetry={reload} />;
  if (!c) return <Loading text="Loading your profile…" />;
  const w = c.workload;

  const save = (e) => {
    e.preventDefault();
    return run(async () => {
      setSaved("");
      try {
        await api("/counsellors/me/", { method: "PATCH", body: readForm(form.values, {}) });
        form.clearErrors();
        setSaved("Saved");
        toast("Profile saved");
      } catch (err) {
        if (err.status === 400) form.showErrors(err.data);
        toast(saveErrorMessage(err), "error");
      }
    });
  };

  return (
    <div className="layout-2">
      <div className="card"><h3>Profile</h3>
        <form noValidate onSubmit={save} ref={form.ref}>
          <ProfileFields form={form} />
          <Field label="Email (sign-in)"><input value={c.email} readOnly /></Field>
          <div className="form-actions"><span className="status" role="status">{saved}</span><button className="btn btn-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button></div>
        </form>
      </div>
      <div className="stack">
        <div className="card counsellor-dock">
          <div className="row"><div className="avatar">{initials(c.name)}</div>
            <div><div style={{ fontWeight: 600 }}>{c.name}</div><div className="small muted">{c.region || ""}</div></div>
          </div>
          <h3>Workload</h3>
          <ProgressBar pct={w.utilisation_pct} label={`${w.assigned}/${w.capacity}`} />
          <p className="small muted" style={{ marginTop: ".6rem" }}>{w.available === 0 ? "No open slots" : `${plural(w.available, "open slot")}`}. Capacity is set by an administrator.</p>
          <Link className="btn btn-outline btn-sm" to="/students/">View my students</Link>
        </div>
      </div>
    </div>
  );
}

function EditorDrawer({ counsellor: c, onClose, onDone }) {
  const toast = useToast();
  const create = !c;
  const form = useForm(c
    ? { name: c.name || "", phone: c.phone || "", region: c.region || "", specialization: c.specialization || "", max_students: c.max_students || 25, is_active: c.is_active !== false }
    : { max_students: 25 });
  const [busy, run] = useSubmit();
  const [confirming, setConfirming] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [removing, runRemove] = useSubmit();
  const assigned = c?.workload.assigned || 0;

  const save = () => run(async () => {
    try {
      const saved = await api(create ? "/counsellors/" : `/counsellors/${encodeURIComponent(c.id)}/`,
        { method: create ? "POST" : "PATCH", body: readForm(form.values, { admin: true, create }) });
      toast(create ? `${saved.name} can now sign in to the counsellor portal` : "Counsellor updated");
      onDone();
    } catch (err) {
      if (err.status === 400) form.showErrors(err.data);
      toast(saveErrorMessage(err), "error");
    }
  });

  const remove = () => runRemove(async () => {
    setDeleteError("");
    try {
      await api(`/counsellors/${encodeURIComponent(c.id)}/`, { method: "DELETE" });
      toast(`${c.name}'s counsellor account has been deleted`);
      onDone();
    } catch (err) { setDeleteError(err.message); }
  });

  return (
    <Drawer title={create ? "Add counsellor" : `Edit ${c.name}`} onClose={onClose} busy={busy} footer={<>
      {!create && <button type="button" className="btn btn-danger" style={{ marginRight: "auto" }} onClick={() => { setDeleteError(""); setConfirming(true); }}>Delete</button>}
      <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : create ? "Create counsellor" : "Save changes"}</button>
    </>}>
      <form noValidate ref={form.ref} onSubmit={(e) => { e.preventDefault(); save(); }}>
        <ProfileFields form={form} admin create={create} />
      </form>
      {!create && <p className="small muted">Sign-in email: {c.email} · {assigned === 0 ? "no students assigned" : `${plural(assigned, "student")} assigned`}</p>}
      {confirming && (
        <ConfirmDialog title={`Delete ${c.name}?`} danger confirmLabel="Delete counsellor" busyLabel="Deleting…" busy={removing}
          confirmDisabled={assigned > 0} error={deleteError} onConfirm={remove} onCancel={() => setConfirming(false)}>
          {assigned > 0 ? (
            <p>{c.name} still has {plural(assigned, "student")} assigned. A counsellor with assigned students cannot be deleted:
              reassign {assigned === 1 ? "that student" : "those students"} first from <Link to={`/students/?counsellor_id=${encodeURIComponent(c.id)}`}>their student list</Link>,
              or untick <b>Active</b> to stop new assignments while keeping their history.</p>
          ) : (
            <p>This removes {c.name}'s counsellor profile and sign-in account ({c.email}); they will no longer be able to sign in.
              No students are assigned to them. Counselling sessions they ran are kept, but will no longer show their name. This cannot be undone.</p>
          )}
        </ConfirmDialog>
      )}
    </Drawer>
  );
}

function AdminView() {
  const [params] = useSearchParams();
  const [state, update] = useQueryState(LIST_STATE);
  const { q, active, page } = state;
  const [search, setSearch] = useState(q);
  const typed = useDebounced(search.trim());
  const [editing, setEditing] = useState(params.get("new") ? { counsellor: null } : null);
  useEffect(() => { if (typed !== q) update({ q: typed, page: 1 }); }, [typed]); // only when the debounced text changes

  const { data, error, reload } = useLoad(() => api("/counsellors/", { query: { page, q, active } }), [page, q, active]);
  const closeEditor = () => {
    setEditing(null);
    if (params.get("new")) window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search.replace(/([?&])new=1&?/, "$1").replace(/[?&]$/, ""));
  };

  return (
    <>
      <div className="page-head">
        <div><h1>Counsellors</h1><p className="muted">Create counsellor accounts, set capacity and watch workload.</p></div>
        <div className="toolbar"><button type="button" className="btn btn-primary" onClick={() => setEditing({ counsellor: null })}>Add counsellor</button></div>
      </div>
      <div className="card">
        <div className="card-head">
          <div className="toolbar">
            <input type="search" placeholder="Search name, email, region…" aria-label="Search counsellors" value={search} onChange={(e) => setSearch(e.target.value)} />
            <select aria-label="Filter by status" value={active} onChange={(e) => update({ active: e.target.value, page: 1 })}>
              <option value="">All</option><option value="true">Active</option><option value="false">Inactive</option>
            </select>
          </div>
          <span className="small muted" aria-live="polite">{data ? plural(data.count, "counsellor") : ""}</span>
        </div>
        <div className="table-wrap"><table>
          <thead><tr><th>Counsellor</th><th>Specialisation</th><th>Region</th><th style={{ width: "22%" }}>Workload</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>
            {error ? <tr><td colSpan={6}><ErrorAlert error={error} onRetry={reload} /></td></tr>
              : !data ? <tr><td colSpan={6} className="loading" role="status">Loading counsellors…</td></tr>
              : !data.results.length ? <tr><td colSpan={6} className="empty">{q || active ? "No counsellors match." : "No counsellors yet — add the first one."}</td></tr>
              : data.results.map((c) => (
                <tr key={c.id}>
                  <td><span className="name">{c.name}</span><div className="small muted">{c.email}</div></td>
                  <td>{c.specialization || "—"}</td><td>{c.region || "—"}</td>
                  <td><ProgressBar pct={c.workload.utilisation_pct} label={`${c.workload.assigned}/${c.workload.capacity}`} /></td>
                  <td>{c.is_active ? <span className="badge badge-ok">Active</span> : <span className="badge">Inactive</span>}</td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <Link className="btn btn-outline btn-sm" to={`/students/?counsellor_id=${encodeURIComponent(c.id)}`} aria-label={`Students of ${c.name}`}>Students</Link>{" "}
                    <button type="button" className="btn btn-outline btn-sm" onClick={() => setEditing({ counsellor: c })} aria-label={`Edit ${c.name}`}>Edit</button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table></div>
        <Pager data={data} onPage={(p) => update({ page: p })} noun="counsellor" />
      </div>
      {editing && <EditorDrawer counsellor={editing.counsellor} onClose={closeEditor} onDone={() => { closeEditor(); reload(); }} />}
    </>
  );
}

export default function Counsellors() {
  const { user } = useAuth();
  return (
    <AppShell title="Counsellors" crumb="Counsellors">
      {user.role === "admin" ? <AdminView /> : (
        <>
          <div className="page-head"><div><h1>My counsellor profile</h1><p className="muted">How students and administrators see you.</p></div></div>
          <SelfView />
        </>
      )}
    </AppShell>
  );
}
