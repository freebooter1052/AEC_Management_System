/* Searchable student picker for staff. Searches the API (name or email), so every student is reachable, not just the first page. */
import { useEffect, useState } from "react";
import Combobox from "./Combobox";
import { api } from "../lib/api";

const PAGE = 20;

/**
 * value     the selected student id ("" for none / "all")
 * onChange  (id, student) - student is the list row, or null when cleared
 * allLabel  when set, an extra first option with value "" (e.g. "All students") for filters
 * optionState (student) => {disabled?, hint?} to disable students that cannot be chosen, with the reason
 * The API scopes results to the signed-in user (counsellors only ever see their own students).
 */
export default function StudentPicker({ id, value, onChange, allLabel, optionState, ariaLabel = "Student", placeholder = "Search by name or email…", ...rest }) {
  const [selected, setSelected] = useState(null);

  // A preselected id (from the URL or a link) only has an id: look its name up once.
  useEffect(() => {
    if (!value) { setSelected(allLabel ? { value: "", label: allLabel } : null); return undefined; }
    if (selected?.value === value) return undefined;
    let live = true;
    api(`/students/${encodeURIComponent(value)}/`).then(
      (s) => { if (live) setSelected({ value, label: s.full_name || s.personal?.email || "Selected student" }); },
      () => { if (live) setSelected({ value, label: "Selected student" }); },
    );
    return () => { live = false; };
  }, [value]); // only when the id changes

  async function loadOptions(q, signal) {
    const data = await api("/students/", { query: { q, page_size: PAGE }, signal });
    const options = data.results.map((s) => {
      const extra = optionState ? optionState(s) || {} : {};
      return { value: s.id, label: s.full_name || s.email, hint: extra.hint ?? s.email, disabled: !!extra.disabled, student: s };
    });
    if (allLabel && !q) options.unshift({ value: "", label: allLabel });
    const note = data.count > PAGE ? `Showing ${PAGE} of ${data.count} students. Type more of a name or email to narrow the list.` : "";
    return { options, note };
  }

  return (
    <Combobox id={id} ariaLabel={ariaLabel} placeholder={placeholder} value={selected} loadOptions={loadOptions}
      emptyText="No students match. Try another name or email." clearable={!allLabel} clearLabel="Clear the selected student" {...rest}
      onChange={(opt) => {
        setSelected(opt || (allLabel ? { value: "", label: allLabel } : null));
        onChange(opt?.value || "", opt?.student || null);
      }} />
  );
}
StudentPicker.isFieldControl = true;
