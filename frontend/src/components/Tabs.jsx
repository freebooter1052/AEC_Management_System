/* WAI-ARIA tabs: one tab stop, arrow keys (and Home/End) move and select, each tab controls its own panel. */
import { useRef } from "react";

/** `tabs` is [[key, label], …]; `onSelect(key)` may refuse a change (e.g. to ask about unsaved edits). */
export function TabList({ id, label, tabs, selected, onSelect, className = "section-tabs", panelFor }) {
  const refs = useRef({});
  const keys = tabs.map(([k]) => k);
  function onKeyDown(e) {
    const i = keys.indexOf(selected);
    const next = { ArrowRight: i + 1, ArrowDown: i + 1, ArrowLeft: i - 1, ArrowUp: i - 1, Home: 0, End: keys.length - 1 }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    const key = keys[(next + keys.length) % keys.length];
    onSelect(key);
    refs.current[key]?.focus();
  }
  return (
    <div className={className} role="tablist" aria-label={label} onKeyDown={onKeyDown}>
      {tabs.map(([key, text]) => (
        <button key={key} type="button" role="tab" id={`${id}-tab-${key}`} ref={(el) => { refs.current[key] = el; }}
          aria-selected={selected === key} aria-controls={`${id}-panel-${panelFor ? panelFor(key) : key}`} tabIndex={selected === key ? 0 : -1}
          onClick={() => onSelect(key)}>
          {text}
        </button>
      ))}
    </div>
  );
}

/** Props for the panel of `key`; only the selected panel is shown. */
export const tabPanel = (id, key, selected) => ({
  role: "tabpanel", id: `${id}-panel-${key}`, "aria-labelledby": `${id}-tab-${key}`, hidden: selected !== key, tabIndex: 0,
});
