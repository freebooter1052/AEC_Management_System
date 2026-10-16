import { useState } from "react";

/** Tag-style multi-value text input: Enter or comma adds, Backspace on an empty input removes the last value. */
export default function ChipsInput({ id, name, values, onChange, label, max = 10, ...aria }) {
  const [text, setText] = useState("");
  const items = values || [];

  const add = () => {
    const v = text.trim().replace(/,$/, "");
    if (v && !items.some((x) => x.toLowerCase() === v.toLowerCase()) && items.length < max) onChange([...items, v]);
    setText("");
  };

  return (
    <div className="chips" data-name={name}>
      {items.map((v, i) => (
        <span className="chip" key={v}>{v}
          <button type="button" aria-label={`Remove ${v}`} onClick={() => onChange(items.filter((_, j) => j !== i))}>&times;</button>
        </span>
      ))}
      <input
        id={id}
        aria-label={label}
        value={text}
        {...aria}
        onChange={(e) => setText(e.target.value)}
        onBlur={add}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); }
          else if (e.key === "Backspace" && !text && items.length) onChange(items.slice(0, -1));
        }}
      />
    </div>
  );
}
ChipsInput.isFieldControl = true;
