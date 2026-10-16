/* Modal behaviour shared by drawers and dialogs, plus an application-native confirmation dialog. */
import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
const stack = []; // open modals, top-most last: only the top one reacts to Escape and Tab
let locks = 0;

export function lockScroll() {
  if (locks++ === 0) document.body.style.overflow = "hidden";
  return () => { if (--locks === 0) document.body.style.overflow = ""; };
}

/**
 * Makes `ref` a modal: focus moves inside on open (first field, else `initialFocus`, else the panel),
 * Tab and Shift+Tab stay inside, Escape calls `onClose`, the page behind does not scroll, and focus
 * returns to the control that opened it when it closes.
 */
export function useModal(ref, onClose, { initialFocus = "field" } = {}) {
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const opener = document.activeElement;
    const token = {};
    stack.push(token);
    const unlock = lockScroll();
    const focusables = () => [...(ref.current?.querySelectorAll(FOCUSABLE) || [])].filter((el) => el.offsetParent !== null || el === document.activeElement);

    const t = setTimeout(() => {
      const panel = ref.current;
      if (!panel || panel.contains(document.activeElement)) return;
      const target = (initialFocus === "field" && panel.querySelector(":is(.body, .dialog-body) :is(input:not([type=hidden]):not([disabled]), select, textarea)"))
        || panel.querySelector("[data-autofocus]") || panel.querySelector("h2[tabindex]") || panel;
      target.focus();
    }, 30);

    const onKey = (e) => {
      if (stack[stack.length - 1] !== token) return;
      if (e.key === "Escape") { e.stopPropagation(); closeRef.current?.(); return; }
      if (e.key !== "Tab") return;
      const list = focusables();
      if (!list.length) { e.preventDefault(); return; }
      const first = list[0];
      const last = list[list.length - 1];
      if (e.shiftKey && (document.activeElement === first || !ref.current.contains(document.activeElement))) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && (document.activeElement === last || !ref.current.contains(document.activeElement))) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(t);
      document.removeEventListener("keydown", onKey);
      stack.splice(stack.indexOf(token), 1);
      unlock();
      if (opener && opener.isConnected && typeof opener.focus === "function") setTimeout(() => opener.focus(), 0);
    };
  }, []); // runs once per open modal
}

/**
 * Confirmation for destructive or consequential actions. `children` explains the consequence;
 * `busy` disables both buttons while the request runs; `error` stays visible inside the dialog.
 */
export function ConfirmDialog({ title, children, confirmLabel = "Confirm", busyLabel = "Working…", cancelLabel = "Cancel",
  danger = false, busy = false, error = "", confirmDisabled = false, initialFocus = "button", extraAction = null, onConfirm, onCancel }) {
  const ref = useRef(null);
  const titleId = useId();
  const descId = useId();
  useModal(ref, () => { if (!busy) onCancel(); }, { initialFocus });

  return createPortal(
    <>
      <div className="dialog-backdrop" onClick={() => { if (!busy) onCancel(); }} />
      <div className="dialog" role="alertdialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={descId} aria-busy={busy || undefined} ref={ref}>
        <h2 id={titleId}>{title}</h2>
        <div id={descId} className="dialog-body">{children}</div>
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        <div className="dialog-actions">
          {extraAction && <button type="button" className="btn btn-outline" style={{ marginRight: "auto" }} onClick={extraAction.onClick} disabled={busy}>{extraAction.label}</button>}
          <button type="button" className="btn btn-outline" onClick={onCancel} disabled={busy} data-autofocus>{cancelLabel}</button>
          <button type="button" className={`btn ${danger ? "btn-danger-solid" : "btn-primary"}`} onClick={onConfirm} disabled={busy || confirmDisabled}>
            {busy ? busyLabel : confirmLabel}
          </button>
        </div>
      </div>
    </>,
    document.body,
  );
}
