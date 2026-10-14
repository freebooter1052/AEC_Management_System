/* Counsellors: administrators manage all counsellors; a counsellor edits their own profile. */
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import AppShell from "../components/Shell";
import Drawer from "../components/Drawer";
import { useAuth } from "../components/auth";
import { useToast } from "../components/Toast";
import { ErrorAlert, Field, Loading, Pager, ProgressBar } from "../components/ui";
import { api } from "../lib/api";
import { initials } from "../lib/format";
import { useForm } from "../lib/form";
import { useDebounced } from "../lib/useDebounced";
import { useLoad } from "../lib/useLoad";

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
      <Field label="Hub / region" error={errors.region}><input placeholder="South Asia Hub" {...bind("region")} /></Field>
      <Field label="Specialization" className="span-2" error={errors.specialization}><input placeholder="UK & Ireland postgraduate" {...bind("specialization")} /></Field>
      {admin && <>
        <Field label="Student capacity" error={errors.max_students}><input type="number" min="1" max="500" {...bind("max_students", "number")} /></Field>
        {!create && <div className="field" style={{ justifyContent: "flex-end" }}><label className="checkbox"><input type="checkbox" {...bind("is_active", "bool")} /> Active</label></div>}
      </>}
    </div>
  );
}

function SelfView() {
  const toast = useToast();
  const { data: c, error } = useLoad(() => api("/counsellors/me/"), []);
  const form = useForm({});
  const { setValues } = form;
  const [saved, setSaved] = useState("");
  useEffect(() => { if (c) setValues({ name: c.name || "", phone: c.phone || "", region: c.region || "", specialization: c.specialization || "" }); }, [c, setValues]);

  if (error) return <ErrorAlert error={error} />;
  if (!c) return <Loading />;
  const w = c.workload;

  async function save(e) {
    e.preventDefault();
    try {
      await api("/counsellors/me/", { method: "PATCH", body: readForm(form.values, {}) });
      form.clearErrors();
      setSaved("Saved ✓");
      toast("Profile saved");
    } catch (err) {
      if (err.status === 400) form.showErrors(err.data);
      toast(err.message, "error");
    }
  }

  return (
    <div className="layout-2">
      <div className="card"><h3>Profile</h3>
        <form noValidate onSubmit={save} ref={form.ref}>
          <ProfileFields form={form} />
          <Field label="Email (sign-in)"><input value={c.email} readOnly /></Field>
          <div className="form-actions"><span className="status">{saved}</span><button className="btn btn-primary" type="submit">Save profile</button></div>
        </form>
      </div>
      <div className="stack">
        <div className="card counsellor-dock">
          <div className="row"><div className="avatar">{initials(c.name)}</div>
            <div><div style={{ fontWeight: 600 }}>{c.name}</div><div className="small muted">{c.region || ""}</div></div>
          </div>
          <h3>Workload</h3>
          <ProgressBar pct={w.utilisation_pct} label={`${w.assigned}/${w.capacity}`} />
          <p className="small muted" style={{ marginTop: ".6rem" }}>{w.available} open slot(s). Capacity is set by an administrator.</p>
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

  async function save() {
    try {
      const saved = await api(create ? "/counsellors/" : `/counsellors/${encodeURIComponent(c.id)}/`,
        { method: create ? "POST" : "PATCH", body: readForm(form.values, { admin: true, create }) });
      toast(create ? `${saved.name} can now sign in to the counsellor portal` : "Counsellor updated");
      onDone();
    } catch (err) {
      if (err.status === 400) form.showErrors(err.data);
      toast(err.message, "error");
    }
  }

  async function remove() {
    if (!window.confirm(`Delete ${c.name} and their sign-in account? This cannot be undone.`)) return;
    try {
      await api(`/counsellors/${encodeURIComponent(c.id)}/`, { method: "DELETE" });
      toast("Counsellor deleted");
      onDone();
    } catch (err) { toast(err.message, "error"); }
  }

  return (
    <Drawer title={create ? "Add counsellor" : `Edit ${c.name}`} onClose={onClose} footer={<>
      {!create && <button className="btn btn-danger" style={{ marginRight: "auto" }} onClick={remove}>Delete</button>}
      <button className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button className="btn btn-primary" onClick={save}>{create ? "Create counsellor" : "Save changes"}</button>
    </>}>
      <form noValidate ref={form.ref} onSubmit={(e) => { e.preventDefault(); save(); }}>
        <ProfileFields form={form} admin create={create} />
      </form>
      {!create && <p className="small muted">Sign-in email: {c.email} · {c.workload.assigned} student(s) assigned</p>}
    </Drawer>
  );
}

function AdminView() {
  const [params] = useSearchParams();
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim());
  const [active, setActive] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState(params.get("new") ? { counsellor: null } : null);
  useEffect(() => setPage(1), [q, active]);

  const { data, error, reload } = useLoad(() => api("/counsellors/", { query: { page, q, active } }), [page, q, active]);

  return (
    <>
      <div className="page-head">
        <div><h1>Counsellors</h1><p className="muted">Create counsellor accounts, set capacity and watch workload.</p></div>
        <div className="toolbar"><button className="btn btn-primary" onClick={() => setEditing({ counsellor: null })}>Add counsellor</button></div>
      </div>
      <div className="card">
        <div className="card-head">
          <div className="toolbar">
            <input type="search" placeholder="Search name, email, region…" aria-label="Search counsellors" value={search} onChange={(e) => setSearch(e.target.value)} />
            <select aria-label="Filter by status" value={active} onChange={(e) => setActive(e.target.value)}>
              <option value="">All</option><option value="true">Active</option><option value="false">Inactive</option>
            </select>
          </div>
          <span className="small muted">{data ? `${data.count} counsellor${data.count === 1 ? "" : "s"}` : ""}</span>
        </div>
        <div className="table-wrap"><table>
          <thead><tr><th>Counsellor</th><th>Specialization</th><th>Region</th><th style={{ width: "22%" }}>Workload</th><th>Status</th><th /></tr></thead>
          <tbody>
            {error ? <tr><td colSpan={6}><div className="alert alert-error" style={{ margin: 0 }}>{error.message}</div></td></tr>
              : !data ? <tr><td colSpan={6} className="loading">Loading…</td></tr>
              : !data.results.length ? <tr><td colSpan={6} className="empty">{q || active ? "No counsellors match." : "No counsellors yet — add the first one."}</td></tr>
              : data.results.map((c) => (
                <tr key={c.id}>
                  <td><span className="name">{c.name}</span><div className="small muted">{c.email}</div></td>
                  <td>{c.specialization || "—"}</td><td>{c.region || "—"}</td>
                  <td><ProgressBar pct={c.workload.utilisation_pct} label={`${c.workload.assigned}/${c.workload.capacity}`} /></td>
                  <td>{c.is_active ? <span className="badge badge-ok">Active</span> : <span className="badge">Inactive</span>}</td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <Link className="btn btn-outline btn-sm" to={`/students/?counsellor_id=${encodeURIComponent(c.id)}`}>Students</Link>{" "}
                    <button className="btn btn-outline btn-sm" onClick={() => setEditing({ counsellor: c })}>Edit</button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table></div>
        <Pager data={data} onPage={setPage} />
      </div>
      {editing && <EditorDrawer counsellor={editing.counsellor} onClose={() => setEditing(null)} onDone={() => { setEditing(null); reload(); }} />}
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
