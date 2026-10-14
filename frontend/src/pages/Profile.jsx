/* Student profile: the student's own (/profile/) or, for staff, /students/<id>/. */
import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import AppShell from "../components/Shell";
import ChipsInput from "../components/ChipsInput";
import { useAuth } from "../components/auth";
import { useToast } from "../components/Toast";
import { Field, Loading, ProgressBar, StatusBadge } from "../components/ui";
import { api } from "../lib/api";
import { formatDate, initials } from "../lib/format";
import { getPath, setPath, useForm } from "../lib/form";

// The fields each section's form sends back, with how the value is typed.
const FIELDS = {
  personal: [["first_name"], ["last_name"], ["preferred_name"], ["phone.dial_code"], ["phone.number"], ["date_of_birth", "date"], ["gender"],
    ["citizenship"], ["address.line1"], ["address.city"], ["address.state"], ["address.country"], ["address.postal_code"]],
  academic: [["degree"], ["institution"], ["cgpa", "number"], ["gpa_scale", "number"], ["graduation_year", "number"], ["work_experience_years", "number"],
    ["english_test.test_type"], ["english_test.overall", "number"], ["gre_status"], ["english_test.listening", "number"],
    ["english_test.reading", "number"], ["english_test.writing", "number"], ["english_test.speaking", "number"]],
  preferences: [["countries", "list"], ["course_areas", "list"], ["degree_level"], ["intake"], ["budget.min", "number"], ["budget.max", "number"],
    ["budget.currency"], ["requires_scholarship", "bool"]],
};
const SECTIONS = [["personal", "Personal", "Save personal details"], ["academic", "Academic", "Save academic record"], ["preferences", "Preferences", "Save preferences"]];
const LEVELS = ["Bachelors", "Masters", "MBA", "PhD", "Diploma", "Certificate"];

function formValues(doc) {
  let v = {};
  for (const [section, fields] of Object.entries(FIELDS)) {
    for (const [f, type] of fields) {
      const path = `${section}.${f}`;
      const raw = getPath(doc, path);
      v = setPath(v, path, type === "list" ? [...(raw || [])] : type === "bool" ? !!raw : raw ?? (f === "budget.currency" ? "USD" : ""));
    }
  }
  return setPath(v, "personal.email", doc.personal?.email ?? "");
}

function sectionPayload(values, section) {
  let out = {};
  for (const [f, type] of FIELDS[section]) {
    const v = getPath(values, `${section}.${f}`);
    let clean;
    if (type === "number") clean = v === "" || v == null ? null : Number(v);
    else if (type === "date") clean = v || null;
    else if (type === "bool") clean = !!v;
    else if (type === "list") clean = v || [];
    else clean = String(v ?? "").trim();
    out = setPath(out, f, clean);
  }
  return out;
}

function CounsellorPanel({ doc, isAdmin, onChange }) {
  const toast = useToast();
  const [options, setOptions] = useState(null);
  const [choice, setChoice] = useState(doc.counsellor_id || "");
  const c = doc.counsellor;

  useEffect(() => {
    if (!isAdmin) return;
    setChoice(doc.counsellor_id || "");
    api("/counsellors/options/").then(setOptions, (err) => toast(err.message, "error"));
  }, [isAdmin, doc.counsellor_id, toast]);

  async function assign(counsellorId) {
    try {
      const updated = await api(`/students/${encodeURIComponent(doc.id)}/assign-counsellor/`, { method: "POST", body: { counsellor_id: counsellorId } });
      toast(counsellorId ? `Assigned to ${updated.counsellor.name}` : "Counsellor unassigned");
      onChange(updated);
    } catch (err) { toast(err.message, "error"); }
  }

  return (
    <div className="card counsellor-dock">
      <h3>Assigned counsellor</h3>
      {c ? (
        <>
          <div className="row"><div className="avatar">{initials(c.name)}</div>
            <div><div style={{ fontWeight: 600 }}>{c.name}</div><div className="small muted">{c.specialization || "Education counsellor"}</div></div>
          </div>
          <dl>
            <dt>Email</dt><dd><a href={`mailto:${c.email}`}>{c.email}</a></dd>
            <dt>Phone</dt><dd>{c.phone || "—"}</dd>
            <dt>Hub</dt><dd>{c.region || "—"}</dd>
            <dt>Since</dt><dd>{formatDate(doc.counsellor_assigned_at)}</dd>
          </dl>
        </>
      ) : <p className="muted" style={{ margin: 0 }}>No counsellor assigned yet.</p>}
      {isAdmin && (
        <>
          <Field label={c ? "Reassign to" : "Assign to"} style={{ margin: "1rem 0 .5rem" }}>
            <select value={choice} onChange={(e) => setChoice(e.target.value)}>
              {!options ? <option value="">Loading…</option> : <option value="">Select a counsellor…</option>}
              {(options || []).map((o) => (
                <option key={o.id} value={o.id} disabled={o.workload.available === 0 && o.id !== doc.counsellor_id}>
                  {o.name} — {o.workload.assigned}/{o.workload.capacity}{o.region ? ` · ${o.region}` : ""}
                </option>
              ))}
            </select>
          </Field>
          <div className="toolbar">
            <button className="btn btn-primary btn-sm" onClick={() => (choice ? assign(choice) : toast("Choose a counsellor first.", "error"))}>Save assignment</button>
            {c && <button className="btn btn-danger btn-sm" onClick={() => assign(null)}>Unassign</button>}
          </div>
        </>
      )}
    </div>
  );
}

export default function Profile() {
  const { studentId } = useParams();
  const [params] = useSearchParams();
  const { user, updateUser } = useAuth();
  const toast = useToast();
  const endpoint = studentId ? `/students/${encodeURIComponent(studentId)}/` : "/students/me/";

  const [doc, setDoc] = useState(null);
  const [error, setError] = useState(null);
  const [countries, setCountries] = useState([]);
  const [tab, setTab] = useState("personal");
  const [saving, setSaving] = useState("");
  const [status, setStatus] = useState({});
  const form = useForm({});
  const { bind, errors, set, values, setValues } = form;

  useEffect(() => {
    Promise.all([api(endpoint), api("/universities/countries/").catch(() => [])]).then(([data, list]) => {
      setDoc(data);
      setValues(formValues(data));
      setCountries(list);
    }, setError);
  }, [endpoint, setValues]);

  async function save(e, section) {
    e.preventDefault();
    setSaving(section);
    setStatus((s) => ({ ...s, [section]: "Saving…" }));
    try {
      const updated = await api(endpoint, { method: "PATCH", body: { [section]: sectionPayload(values, section), rev: doc.rev } });
      setDoc(updated);
      form.clearErrors();
      setStatus((s) => ({ ...s, [section]: "Saved ✓" }));
      toast("Profile saved");
      if (!studentId && section === "personal") updateUser({ ...user, full_name: updated.full_name });
    } catch (err) {
      setStatus((s) => ({ ...s, [section]: "" }));
      if (err.status === 400) { form.showErrors(err.data); toast("Please fix the highlighted fields.", "error"); }
      else if (err.status === 409) toast("This profile was changed elsewhere. Reload the page to get the latest version.", "error");
      else toast(err.message, "error");
    } finally { setSaving(""); }
  }

  function goTo(section, field) {
    setTab(section);
    setTimeout(() => (document.querySelector(`[name="${CSS.escape(field)}"]`) || document.querySelector(`[data-name="${CSS.escape(field)}"] input`))?.focus(), 0);
  }

  const title = studentId ? doc?.full_name || "Student profile" : "My profile";
  const crumb = studentId ? <><Link to="/students/">Students</Link> / {doc?.full_name || "Student profile"}</> : "Student profile";
  const comp = doc?.profile_completion || {};
  const missing = comp.missing || [];
  const q = studentId && doc ? `?student_id=${encodeURIComponent(doc.id)}` : "";
  const appCount = (doc?.application_ids || []).length;
  const err = (name) => errors[name];

  return (
    <AppShell title={studentId ? "Student profile" : "My profile"} crumb={crumb}>
      <div className="page-head">
        <div>
          <h1>{title}</h1>
          <p className="muted">Personal, academic and preference information used for counselling and university matching.</p>
        </div>
        {doc && <div className="toolbar"><StatusBadge status={doc.onboarding_status} /><span className="badge">Updated {formatDate(doc.updated_at)}</span></div>}
      </div>

      {!studentId && params.get("welcome") && doc && (
        <div className="alert alert-info">Welcome aboard! Complete the three sections below — your readiness score updates as you save.</div>
      )}

      {error && <div className="alert alert-error">{error.status === 403 ? "You do not have access to this student." : error.message}</div>}
      {!doc && !error && <Loading text="Loading profile…" />}

      {doc && (
        <div className="layout-2">
          <div className="card" ref={form.ref}>
            <div className="section-tabs" role="tablist" aria-label="Profile sections">
              {SECTIONS.map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>{label}</button>)}
            </div>

            {SECTIONS.map(([section, , saveLabel]) => (
              <form key={section} noValidate hidden={tab !== section} onSubmit={(e) => save(e, section)}>
                {section === "personal" && (
                  <div className="grid grid-2">
                    <Field label="Legal first name" error={err("personal.first_name")}><input required {...bind("personal.first_name")} /></Field>
                    <Field label="Legal last name" error={err("personal.last_name")}><input required {...bind("personal.last_name")} /></Field>
                    <Field label="Preferred name" error={err("personal.preferred_name")}><input {...bind("personal.preferred_name")} /></Field>
                    <Field label="Email (sign-in)"><input readOnly {...bind("personal.email")} /></Field>
                    <div className="field">
                      <label htmlFor="phone-number">Mobile number</label>
                      <div className="input-group">
                        <input placeholder="+91" aria-label="Dial code" {...bind("personal.phone.dial_code")} />
                        <input id="phone-number" inputMode="numeric" aria-label="Number" {...bind("personal.phone.number")} />
                      </div>
                      {(err("personal.phone.dial_code") || err("personal.phone.number")) && <div className="error">{err("personal.phone.dial_code") || err("personal.phone.number")}</div>}
                    </div>
                    <Field label="Date of birth" error={err("personal.date_of_birth")}><input type="date" {...bind("personal.date_of_birth", "date")} /></Field>
                    <Field label="Gender" error={err("personal.gender")}>
                      <select {...bind("personal.gender")}><option value="">Prefer not to say</option><option>Female</option><option>Male</option><option>Non-binary</option><option>Other</option></select>
                    </Field>
                    <Field label="Citizenship" error={err("personal.citizenship")}><input {...bind("personal.citizenship")} /></Field>
                    <Field label="Address" className="span-2" error={err("personal.address.line1")}><input placeholder="House / street" {...bind("personal.address.line1")} /></Field>
                    <Field label="City" error={err("personal.address.city")}><input {...bind("personal.address.city")} /></Field>
                    <Field label="State / region" error={err("personal.address.state")}><input {...bind("personal.address.state")} /></Field>
                    <Field label="Country" error={err("personal.address.country")}><input {...bind("personal.address.country")} /></Field>
                    <Field label="Postal code" error={err("personal.address.postal_code")}><input {...bind("personal.address.postal_code")} /></Field>
                  </div>
                )}

                {section === "academic" && (
                  <>
                    <div className="grid grid-2">
                      <Field label="Highest degree" className="span-2" error={err("academic.degree")}><input placeholder="B.E. Computer Science" {...bind("academic.degree")} /></Field>
                      <Field label="Institution" className="span-2" error={err("academic.institution")}><input {...bind("academic.institution")} /></Field>
                      <Field label="CGPA / GPA" error={err("academic.cgpa")}><input type="number" step="0.01" min="0" {...bind("academic.cgpa", "number")} /></Field>
                      <Field label="GPA scale" error={err("academic.gpa_scale")}>
                        <select {...bind("academic.gpa_scale", "number")}><option value="">Select…</option><option value="4">4.0</option><option value="5">5.0</option><option value="10">10</option><option value="100">100 (%)</option></select>
                      </Field>
                      <Field label="Graduation year" error={err("academic.graduation_year")}><input type="number" min="1950" max="2100" {...bind("academic.graduation_year", "number")} /></Field>
                      <Field label="Work experience (years)" error={err("academic.work_experience_years")}><input type="number" step="0.5" min="0" {...bind("academic.work_experience_years", "number")} /></Field>
                    </div>
                    <h3 style={{ marginTop: ".6rem" }}>English proficiency</h3>
                    <div className="grid grid-3">
                      <Field label="Test" error={err("academic.english_test.test_type")}>
                        <select {...bind("academic.english_test.test_type")}><option value="">Not taken yet</option><option>IELTS</option><option>TOEFL</option><option>PTE</option><option>Duolingo</option><option>Cambridge</option><option>Other</option></select>
                      </Field>
                      <Field label="Overall score" error={err("academic.english_test.overall")}><input type="number" step="0.5" min="0" {...bind("academic.english_test.overall", "number")} /></Field>
                      <Field label="GRE / GMAT status" error={err("academic.gre_status")}><input placeholder="e.g. GRE 320, waiver requested" {...bind("academic.gre_status")} /></Field>
                    </div>
                    <div className="grid grid-4">
                      {["listening", "reading", "writing", "speaking"].map((k) => (
                        <Field key={k} label={k[0].toUpperCase() + k.slice(1)} error={err(`academic.english_test.${k}`)}>
                          <input type="number" step="0.5" min="0" {...bind(`academic.english_test.${k}`, "number")} />
                        </Field>
                      ))}
                    </div>
                  </>
                )}

                {section === "preferences" && (
                  <div className="grid grid-2">
                    <Field label="Target countries" className="span-2" hint="Type a country and press Enter." error={err("preferences.countries")}>
                      <ChipsInput name="preferences.countries" label="Target countries" list="country-options" values={getPath(values, "preferences.countries")} onChange={(v) => set("preferences.countries", v)} />
                    </Field>
                    <Field label="Course / programme areas" className="span-2" hint="e.g. Computer Science, AI/ML, Data Science." error={err("preferences.course_areas")}>
                      <ChipsInput name="preferences.course_areas" label="Course / programme areas" values={getPath(values, "preferences.course_areas")} onChange={(v) => set("preferences.course_areas", v)} />
                    </Field>
                    <Field label="Target degree level" error={err("preferences.degree_level")}>
                      <select {...bind("preferences.degree_level")}><option value="">Select…</option>{LEVELS.map((l) => <option key={l}>{l}</option>)}</select>
                    </Field>
                    <Field label="Preferred intake" error={err("preferences.intake")}><input placeholder="Fall 2027" {...bind("preferences.intake")} /></Field>
                    <Field label="Budget from (per year)" error={err("preferences.budget.min")}><input type="number" min="0" step="500" {...bind("preferences.budget.min", "number")} /></Field>
                    <Field label="Budget up to (per year)" error={err("preferences.budget.max")}><input type="number" min="0" step="500" {...bind("preferences.budget.max", "number")} /></Field>
                    <Field label="Currency" error={err("preferences.budget.currency")}>
                      <select {...bind("preferences.budget.currency")}>{["USD", "EUR", "GBP", "CAD", "AUD", "INR", "SGD"].map((c) => <option key={c}>{c}</option>)}</select>
                    </Field>
                    <div className="field" style={{ justifyContent: "flex-end" }}>
                      <label className="checkbox"><input type="checkbox" {...bind("preferences.requires_scholarship", "bool")} /> Scholarship required</label>
                    </div>
                    <datalist id="country-options">{countries.map((c) => <option key={c.country} value={c.country} />)}</datalist>
                  </div>
                )}

                <div className="form-actions">
                  <span className="status">{status[section]}</span>
                  <button className="btn btn-primary" type="submit" disabled={saving === section}>{saveLabel}</button>
                </div>
              </form>
            ))}
          </div>

          <div className="stack">
            <div className="card" style={{ textAlign: "center" }}>
              <h3>Readiness score</h3>
              <div className="gauge" style={{ "--pct": comp.overall || 0 }}><span>{comp.overall || 0}%</span></div>
              <div style={{ textAlign: "left" }}>
                {["personal", "academic", "preferences"].map((s) => (
                  <div key={s} style={{ marginTop: ".6rem" }}>
                    <div className="small" style={{ fontWeight: 600, textTransform: "capitalize" }}>{s}</div>
                    <ProgressBar pct={comp[s]} />
                  </div>
                ))}
              </div>
            </div>
            <div className="card">
              <h3>{missing.length ? `Missing for 100% (${missing.length})` : "All required fields complete"}</h3>
              <ul className="missing-list">
                {missing.length
                  ? missing.map((m) => <li key={m.field}><a href="#" onClick={(e) => { e.preventDefault(); goTo(m.section, m.field); }}>{m.label}</a></li>)
                  : <li className="done muted">Nothing left to add.</li>}
              </ul>
            </div>
            <CounsellorPanel doc={doc} isAdmin={user.role === "admin"} onChange={setDoc} />
            <div className="card"><h3>Applications &amp; counselling</h3>
              <div className="workflow-links">
                {[[`/applications/${q}`, "Applications", `${appCount} application${appCount === 1 ? "" : "s"}`],
                  [`/documents/${q}`, "Documents", "Checklist & verification"],
                  [`/counselling/${q}`, "Counselling", "Sessions & follow-ups"]].map(([href, label, sub]) => (
                  <Link key={label} to={href}>
                    <span>{label}<span className="small muted" style={{ display: "block", fontWeight: 400 }}>{sub}</span></span>
                    <span aria-hidden="true">→</span>
                  </Link>
                ))}
              </div>
            </div>
            <details className="json"><summary>CouchDB document (JSON)</summary><pre>{JSON.stringify(doc, null, 2)}</pre></details>
          </div>
        </div>
      )}
    </AppShell>
  );
}
