/* Searchable single-choice picker (WAI-ARIA combobox + listbox). Options come from `loadOptions`, which may call the API. */
import { useEffect, useId, useRef, useState } from "react";

/**
 * Props:
 *   value        the selected option {value, label} or null - kept while the user searches
 *   onChange     called with the chosen option, or null when cleared
 *   loadOptions  (query, signal) => Promise<{options, note?}> - options are {value, label, hint?, disabled?}
 *   clearable    show a × button that clears the selection
 *   resetOnSelect  empty the box after a choice (multi-value inputs)
 */
export default function Combobox({ id, value, onChange, loadOptions, placeholder = "Type to search…", ariaLabel, clearable = false,
  clearLabel = "Clear selection", resetOnSelect = false, disabled = false, emptyText = "No matches.", debounceMs = 250, ...aria }) {
  const autoId = useId();
  const inputId = id || autoId;
  const listId = `${inputId}-list`;
  const [text, setText] = useState(value?.label || "");
  const [open, setOpen] = useState(false);
  const [state, setState] = useState({ status: "idle", options: [], note: "" });
  const [active, setActive] = useState(-1);
  const [query, setQuery] = useState(null); // null = closed; "" = open showing the default list
  const seq = useRef(0);
  const inputRef = useRef(null);

  // Show the selected label whenever the user is not typing (e.g. it loaded later, or the parent changed it).
  useEffect(() => { if (!open) setText(resetOnSelect ? "" : value?.label || ""); }, [value, open, resetOnSelect]);

  useEffect(() => {
    if (query === null) return undefined;
    const ctrl = new AbortController();
    const mine = ++seq.current;
    setState((s) => ({ ...s, status: "loading" }));
    const t = setTimeout(() => {
      Promise.resolve(loadOptions(query.trim(), ctrl.signal)).then(
        (res) => { if (mine === seq.current) { setState({ status: "ready", options: res.options || [], note: res.note || "" }); setActive(-1); } },
        (err) => { if (mine === seq.current && err?.name !== "AbortError") setState({ status: "error", options: [], note: "" }); },
      );
    }, query ? debounceMs : 0);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [query]); // not on `loadOptions`, which parents re-create on every render

  const options = state.options;
  const openList = (q) => { setOpen(true); setQuery(q); };
  const close = () => { setOpen(false); setQuery(null); setActive(-1); };
  const choose = (opt) => {
    if (!opt || opt.disabled) return;
    onChange(opt);
    close();
    setText(resetOnSelect ? "" : opt.label);
  };
  const move = (delta) => {
    if (!options.length) return;
    let i = active;
    for (let n = 0; n < options.length; n++) {
      i = (i + delta + options.length) % options.length;
      if (!options[i].disabled) break;
    }
    setActive(i);
    document.getElementById(`${listId}-${i}`)?.scrollIntoView({ block: "nearest" });
  };

  function onKeyDown(e) {
    if (e.key === "ArrowDown") { e.preventDefault(); if (!open) openList(text === value?.label ? "" : text); else move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); if (open) move(-1); }
    else if (e.key === "Home" && open && options.length) { e.preventDefault(); setActive(0); }
    else if (e.key === "End" && open && options.length) { e.preventDefault(); setActive(options.length - 1); }
    else if (e.key === "Enter" && open) {
      e.preventDefault();
      const pick = active >= 0 ? options[active] : options.filter((o) => !o.disabled).length === 1 ? options.find((o) => !o.disabled) : null;
      if (pick) choose(pick);
    } else if (e.key === "Escape" && open) { e.preventDefault(); e.stopPropagation(); close(); }
  }

  const activeId = open && active >= 0 ? `${listId}-${active}` : undefined;
  return (
    <div className={`combo${open ? " open" : ""}`}>
      <div className="combo-control">
        <input
          ref={inputRef} id={inputId} type="text" role="combobox" autoComplete="off" spellCheck={false}
          aria-label={ariaLabel} aria-autocomplete="list" aria-expanded={open} aria-controls={listId} aria-activedescendant={activeId}
          placeholder={value && resetOnSelect ? "" : placeholder} value={text} disabled={disabled} {...aria}
          onChange={(e) => { setText(e.target.value); openList(e.target.value); }}
          onFocus={(e) => e.target.select()}
          onClick={() => { if (!open) openList(""); }}
          onKeyDown={onKeyDown}
          onBlur={() => setTimeout(() => { if (!inputRef.current?.parentElement?.parentElement?.contains(document.activeElement)) close(); }, 120)}
        />
        {clearable && value && !disabled && (
          <button type="button" className="combo-clear" aria-label={clearLabel} onClick={() => { onChange(null); setText(""); inputRef.current?.focus(); }}>&times;</button>
        )}
        <span className="combo-caret" aria-hidden="true">▾</span>
      </div>
      <ul id={listId} role="listbox" className="combo-list" hidden={!open} aria-label={ariaLabel ? `${ariaLabel} options` : undefined}>
        {open && state.status === "loading" && !options.length && <li className="combo-status" role="presentation">Searching…</li>}
        {open && state.status === "error" && <li className="combo-status combo-error" role="presentation">Could not load results. Check your connection and type again to retry.</li>}
        {open && state.status === "ready" && !options.length && <li className="combo-status" role="presentation">{emptyText}</li>}
        {open && options.map((o, i) => (
          <li key={o.value || `opt-${i}`} id={`${listId}-${i}`} role="option" aria-selected={i === active} aria-disabled={o.disabled || undefined}
            className={`combo-option${i === active ? " active" : ""}${value?.value === o.value ? " selected" : ""}`}
            onMouseDown={(e) => e.preventDefault()} onClick={() => choose(o)} onMouseEnter={() => !o.disabled && setActive(i)}>
            <span>{o.label}</span>{o.hint && <span className="combo-hint">{o.hint}</span>}
          </li>
        ))}
        {open && state.note && options.length > 0 && <li className="combo-status" role="presentation">{state.note}</li>}
      </ul>
    </div>
  );
}
Combobox.isFieldControl = true;
