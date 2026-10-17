/* Admin form for a course's published details (SRS 4.4). Rendered inside the university drawer. */
import { useEffect, useState } from "react";
import { useToast } from "./Toast";
import { Field } from "./ui";
import { api } from "../lib/api";
import { saveErrorMessage, useForm } from "../lib/form";
import { useSubmit } from "../lib/useSubmit";

const LEVELS = ["Diploma", "Bachelors", "Masters", "MBA", "PhD", "Certificate"];
const TESTS = [["IELTS", "0–9", 0.5], ["TOEFL", "0–120", 1], ["PTE", "10–90", 1]];
const num = (v) => (v === "" || v === null || v === undefined ? null : Number(v));

function initial(c) {
  const e = c?.eligibility || {};
  return {
    title: c?.title || "", cluster: c?.cluster || "", level: c?.level || "", duration_months: c?.duration_months ?? "",
    amount_per_year: c?.tuition?.amount_per_year ?? "", currency: c?.tuition?.currency || "",
    min_grade_pct: e.min_grade_pct ?? "", notes: e.notes || "",
    ...Object.fromEntries(TESTS.map(([t]) => [`eng_${t}`, e.min_english?.[t] ?? ""])),
    is_active: c ? c.is_active !== false : true,
  };
}

/** `course` null = add a new course to `universityId`. `onSaved(course)` after a successful save. */
export default function CourseEditor({ course, universityId, onCancel, onSaved }) {
  const toast = useToast();
  const form = useForm(initial(course));
  const { bind, errors, values, set } = form;
  const [intakes, setIntakes] = useState([]);
  const [chosen, setChosen] = useState(course?.intake_ids || []);
  const [busy, run] = useSubmit();

  useEffect(() => { api("/intakes/").then(setIntakes, (err) => toast(err.message, "error")); }, [toast]);

  const save = () => run(async () => {
    const english = Object.fromEntries(TESTS.map(([t]) => [t, num(values[`eng_${t}`])]).filter(([, v]) => v !== null));
    const body = {
      title: values.title.trim(), cluster: values.cluster, level: values.level, duration_months: num(values.duration_months),
      tuition: { amount_per_year: num(values.amount_per_year), ...(values.currency ? { currency: values.currency.trim().toUpperCase() } : {}) },
      eligibility: { min_grade_pct: num(values.min_grade_pct), min_english: english, notes: values.notes },
      intake_ids: chosen, is_active: values.is_active,
    };
    try {
      const saved = course
        ? await api(`/universities/courses/${encodeURIComponent(course.id)}/`, { method: "PATCH", body: { ...body, rev: course.rev } })
        : await api(`/universities/${encodeURIComponent(universityId)}/courses/`, { method: "POST", body });
      toast(course ? "Course updated" : "Course added");
      onSaved(saved);
    } catch (err) {
      if (err.status === 400) form.showErrors(err.data);
      toast(saveErrorMessage(err), "error");
    }
  });

  const tErr = errors["tuition.amount_per_year"] || errors["tuition.currency"] || errors.tuition;
  return (
    <form noValidate ref={form.ref} onSubmit={(e) => { e.preventDefault(); save(); }}>
      <Field label="Title" error={errors.title}><input maxLength={200} {...bind("title")} /></Field>
      <div className="grid grid-2">
        <Field label="Subject area" error={errors.cluster}><input maxLength={80} {...bind("cluster")} /></Field>
        <Field label="Level" error={errors.level}>
          <select {...bind("level")}><option value="">Not recorded</option>{LEVELS.map((l) => <option key={l}>{l}</option>)}</select>
        </Field>
        <Field label="Duration (months)" error={errors.duration_months}><input type="number" min={1} max={96} {...bind("duration_months")} /></Field>
        <Field label="Minimum grade (% of scale)" error={errors["eligibility.min_grade_pct"]} hint="e.g. 75 for 7.5/10 or 3.0/4">
          <input type="number" min={0} max={100} step={0.5} {...bind("min_grade_pct")} />
        </Field>
        <Field label="Tuition per year" error={tErr}><input type="number" min={0} step={100} {...bind("amount_per_year")} /></Field>
        <Field label="Currency" error={errors["tuition.currency"]} hint="3 letters, e.g. EUR"><input maxLength={3} {...bind("currency")} /></Field>
      </div>
      <fieldset className="fieldset">
        <legend>Minimum English score (overall)</legend>
        <div className="grid grid-3">
          {TESTS.map(([t, range, step]) => (
            <Field key={t} label={t} hint={range} error={errors[`eligibility.min_english`]}>
              <input type="number" min={0} step={step} {...bind(`eng_${t}`)} />
            </Field>
          ))}
        </div>
      </fieldset>
      <Field label="Requirement notes" error={errors["eligibility.notes"]}><textarea maxLength={500} {...bind("notes")} /></Field>
      <fieldset className="fieldset">
        <legend>Offered in</legend>
        <p className="small muted" style={{ marginTop: 0 }}>Leave all unticked if the course takes every intake.</p>
        {intakes.map((i) => (
          <label key={i.id} className="checkbox">
            <input type="checkbox" checked={chosen.includes(i.id)}
              onChange={(e) => setChosen((list) => (e.target.checked ? [...list, i.id] : list.filter((x) => x !== i.id)))} />
            {i.name}{i.is_open ? "" : " (closed)"}
          </label>
        ))}
      </fieldset>
      <label className="checkbox"><input type="checkbox" checked={values.is_active} onChange={(e) => set("is_active", e.target.checked)} /> Offered (untick to deactivate an outdated course)</label>
      <div className="toolbar" style={{ marginTop: "1rem" }}>
        <button type="button" className="btn btn-outline" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? "Saving…" : course ? "Save course" : "Add course"}</button>
      </div>
    </form>
  );
}
