import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

/** Right-hand slide-over panel. Closes on Escape, backdrop click or the × button. */
export default function Drawer({ title, onClose, footer, children }) {
  const ref = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") closeRef.current(); };
    document.addEventListener("keydown", onKey);
    const t = setTimeout(() => ref.current?.querySelector(".body input, .body select, .body textarea, .body button")?.focus(), 30);
    return () => { document.removeEventListener("keydown", onKey); clearTimeout(t); };
  }, []);

  return createPortal(
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={title} ref={ref}>
        <header><h2 style={{ margin: 0 }}>{title}</h2><button className="icon-btn" aria-label="Close" onClick={onClose}>&times;</button></header>
        <div className="body">{children}</div>
        {footer && <footer>{footer}</footer>}
      </aside>
    </>,
    document.body,
  );
}
