import { useId, useRef } from "react";
import { createPortal } from "react-dom";
import { useModal } from "./Dialog";

/**
 * Right-hand slide-over panel (a modal dialog). Focus moves to its first field, stays inside while open
 * and returns to the opener on close; Escape, the backdrop and the × button call `onClose`.
 * `busy` marks the panel as busy for assistive technology while a request runs.
 */
export default function Drawer({ title, onClose, footer, busy = false, children }) {
  const ref = useRef(null);
  const titleId = useId();
  useModal(ref, onClose);

  return createPortal(
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby={titleId} aria-busy={busy || undefined} ref={ref} tabIndex={-1}>
        <header><h2 id={titleId} tabIndex={-1} style={{ margin: 0 }}>{title}</h2><button type="button" className="icon-btn" aria-label="Close" onClick={onClose}>&times;</button></header>
        <div className="body">{children}</div>
        {footer && <footer>{footer}</footer>}
      </aside>
    </>,
    document.body,
  );
}
