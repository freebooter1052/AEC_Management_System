/* Country pickers backed by the API's canonical list (/api/countries/), so every profile spells countries the same way. */
import { useEffect, useState } from "react";
import Combobox from "./Combobox";
import { api } from "../lib/api";

let cache = null;

/** The canonical list [{name, catalogue_name}], fetched once per page load. */
export function useCountries() {
  const [list, setList] = useState(cache || []);
  const [error, setError] = useState(null);
  useEffect(() => {
    if (cache) return undefined;
    let live = true;
    api("/countries/").then((rows) => { cache = rows; if (live) setList(rows); }, (err) => { if (live) setError(err); });
    return () => { live = false; };
  }, []);
  return { list, error };
}

const matches = (q) => (c) => !q || c.name.toLowerCase().includes(q.toLowerCase()) || c.catalogue_name.toLowerCase() === q.toLowerCase();
const rank = (q) => (a, b) => (b.name.toLowerCase().startsWith(q.toLowerCase()) - a.name.toLowerCase().startsWith(q.toLowerCase()));

/** One country, stored as the world name ("United States"). Values not in the list are shown so nothing is silently lost. */
export function CountryPicker({ id, value, onChange, ariaLabel = "Country", placeholder = "Search countries…", ...rest }) {
  const { list } = useCountries();
  const selected = value ? { value, label: value } : null;
  const load = (q) => ({
    options: list.filter(matches(q)).sort(rank(q)).slice(0, 60).map((c) => ({ value: c.name, label: c.name })),
    note: list.length ? "" : "Loading countries…",
  });
  return <Combobox id={id} ariaLabel={ariaLabel} placeholder={placeholder} value={selected} loadOptions={load} debounceMs={0}
    clearable clearLabel={`Clear ${ariaLabel.toLowerCase()}`} emptyText={list.length ? "No country matches." : "Loading countries…"} onChange={(opt) => onChange(opt?.value || "")} {...rest} />;
}
CountryPicker.isFieldControl = true;

/** Several countries as chips, stored with the catalogue's spelling ("US", "UK") so university matching is exact. */
export function CountryChips({ id, values, onChange, ariaLabel = "Target countries", max = 10, ...rest }) {
  const { list } = useCountries();
  const items = values || [];
  const nameOf = (v) => list.find((c) => c.catalogue_name === v)?.name || v;
  const load = (q) => ({
    options: list.filter((c) => !items.includes(c.catalogue_name)).filter(matches(q)).sort(rank(q)).slice(0, 60)
      .map((c) => ({ value: c.catalogue_name, label: c.name })),
  });
  return (
    <div className="chips">
      {items.map((v) => (
        <span className="chip" key={v}>{nameOf(v)}
          <button type="button" aria-label={`Remove ${nameOf(v)}`} onClick={() => onChange(items.filter((x) => x !== v))}>&times;</button>
        </span>
      ))}
      {items.length < max
        ? <Combobox id={id} ariaLabel={ariaLabel} placeholder={items.length ? "Add another country…" : "Search countries…"} value={null} resetOnSelect
          loadOptions={load} debounceMs={0} emptyText={list.length ? "No country matches." : "Loading countries…"} onChange={(opt) => opt && onChange([...items, opt.value])} {...rest} />
        : <span className="small muted">Up to {max} countries.</span>}
    </div>
  );
}
CountryChips.isFieldControl = true;
