import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

const ToastContext = createContext(() => {});
let seq = 0;

// How long each kind stays up. Errors and warnings stay long enough to read and act on; hovering or
// focusing a toast pauses it, and every toast can be dismissed.
const DURATION = { success: 5000, info: 6000, warning: 9000, error: 12000 };
const ICON = { success: "✓", info: "i", warning: "!", error: "!" };
const KIND_LABEL = { success: "Success", info: "Information", warning: "Warning", error: "Error" };

function ToastItem({ t, onDismiss }) {
  const timer = useRef(null);
  const left = useRef(DURATION[t.kind] || DURATION.info);
  const started = useRef(0);
  const start = useCallback(() => {
    started.current = Date.now();
    timer.current = setTimeout(() => onDismiss(t.id), left.current);
  }, [onDismiss, t.id]);
  const pause = () => { clearTimeout(timer.current); left.current = Math.max(2000, left.current - (Date.now() - started.current)); };
  useEffect(() => { start(); return () => clearTimeout(timer.current); }, [start]);

  return (
    <div className={`toast toast-${t.kind}`} onMouseEnter={pause} onMouseLeave={start} onFocus={pause} onBlur={start}>
      <span className="toast-icon" aria-hidden="true">{ICON[t.kind]}</span>
      <span className="toast-msg"><span className="sr-only">{KIND_LABEL[t.kind]}: </span>{t.message}</span>
      <button type="button" className="toast-close" aria-label="Dismiss notification" onClick={() => onDismiss(t.id)}>&times;</button>
    </div>
  );
}

/**
 * Notifications at the top centre of the screen, clear of drawer footers and their Save buttons.
 * Two live regions exist from the start so screen readers announce reliably: errors and warnings
 * assertively (role="alert"), success and information politely (role="status").
 */
export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const dismiss = useCallback((id) => setItems((list) => list.filter((t) => t.id !== id)), []);
  const toast = useCallback((message, kind = "success") => {
    const id = ++seq;
    const k = DURATION[kind] ? kind : "info";
    // The same message twice in a row (e.g. a repeated failure) replaces the old one instead of stacking.
    setItems((list) => [...list.filter((t) => t.message !== message).slice(-3), { id, message: String(message), kind: k }]);
  }, []);
  const urgent = items.filter((t) => t.kind === "error" || t.kind === "warning");
  const calm = items.filter((t) => t.kind === "success" || t.kind === "info");
  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className="toast-host">
        <div role="alert" aria-live="assertive" className="toast-region">{urgent.map((t) => <ToastItem key={t.id} t={t} onDismiss={dismiss} />)}</div>
        <div role="status" aria-live="polite" className="toast-region">{calm.map((t) => <ToastItem key={t.id} t={t} onDismiss={dismiss} />)}</div>
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
