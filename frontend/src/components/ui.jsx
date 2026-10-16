import { Children, cloneElement, isValidElement, useId } from "react";
import { Link } from "react-router-dom";
import { formatDate, plural } from "../lib/format";
import { appStatusLabel, countdownText, docStatusLabel } from "../lib/labels";

export { appStatusLabel, countdownText, docStatusLabel };

// Workflow vocabularies (backend apps/core/vocab.py) -> badge styles; wording lives in lib/labels.js.
const APP_STATUS_CLASS = {
  Planned: "badge", Shortlisted: "badge badge-info", "Documents Pending": "badge badge-warn", Submitted: "badge badge-brand",
  "Under Review": "badge badge-info", "Offer Received": "badge badge-ok", Rejected: "badge badge-err", Withdrawn: "badge",
  Completed: "badge badge-ok",
};
const DOC_STATUS_CLASS = {
  Required: "badge badge-warn", Uploaded: "badge badge-info", "Under Review": "badge badge-brand", Verified: "badge badge-ok",
  Rejected: "badge badge-err", Expired: "badge badge-err",
};
const SESSION_STATUS_CLASS = { Scheduled: "badge badge-info", Completed: "badge badge-ok", Cancelled: "badge" };
const ONBOARDING = {
  registered: ["Registered", "badge"],
  in_progress: ["In progress", "badge badge-warn"],
  profile_complete: ["Profile complete", "badge badge-info"],
  ready: ["Ready", "badge badge-ok"],
};

export const AppStatusBadge = ({ status }) => <span className={APP_STATUS_CLASS[status] || "badge"}>{status ? appStatusLabel(status) : "—"}</span>;
export const DocStatusBadge = ({ status }) => <span className={DOC_STATUS_CLASS[status] || "badge"}>{status ? docStatusLabel(status) : "—"}</span>;
export const SessionStatusBadge = ({ status }) => <span className={SESSION_STATUS_CLASS[status] || "badge"}>{status || "—"}</span>;

export function StatusBadge({ status }) {
  const [label, cls] = ONBOARDING[status] || [status || "—", "badge"];
  return <span className={cls}>{label}</span>;
}

/** Deadline date plus a countdown badge, from an application's `deadline_info`. */
export function DeadlineBadge({ info }) {
  if (!info || !info.date) return <span className="muted">No deadline</span>;
  const cls = { overdue: "badge badge-err", due_soon: "badge badge-warn", submitted: "badge badge-ok" }[info.state] || "badge";
  return <span className="deadline"><span className="date">{formatDate(info.date)}</span><span className={cls}>{countdownText(info)}</span></span>;
}

export function ProgressBar({ pct, label, name = "Progress" }) {
  const p = Math.max(0, Math.min(100, Number(pct) || 0));
  return (
    <div className="bar-row">
      <div className={p >= 100 ? "bar ok" : "bar"} role="progressbar" aria-label={name} aria-valuenow={p} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${p}%` }} /></div>
      <span className="num">{label ?? `${p}%`}</span>
    </div>
  );
}

/**
 * A key figure. With `to` it is a link to the page that lets the user act on it (and looks clickable);
 * without, it is purely informational and does not react to hover.
 */
export function Kpi({ label, value, to, children }) {
  const body = <><div className="label">{label}</div><div className="value">{value}</div><div className="sub">{children}</div></>;
  return to ? <Link className="kpi kpi-link" to={to}>{body}</Link> : <div className="kpi">{body}</div>;
}

/** Pagination controls for a {count, page, page_size, total_pages} payload. */
export function Pager({ data, onPage, noun = "result" }) {
  if (!data || !data.count) return <div className="pager" />;
  const from = (data.page - 1) * data.page_size + 1;
  const to = Math.min(data.count, data.page * data.page_size);
  return (
    <nav className="pager" aria-label="Pagination">
      <span>{from}–{to} of {plural(data.count, noun)}</span>
      <span className="toolbar">
        <button type="button" className="btn btn-outline btn-sm" disabled={data.page <= 1} onClick={() => onPage(data.page - 1)}>Previous</button>
        <span className="small">Page {data.page} of {data.total_pages}</span>
        <button type="button" className="btn btn-outline btn-sm" disabled={data.page >= data.total_pages} onClick={() => onPage(data.page + 1)}>Next</button>
      </span>
    </nav>
  );
}

const NATIVE = ["input", "select", "textarea"];

/**
 * A labelled form field. The first control child (a native input/select/textarea, or a component marked
 * `isFieldControl`) gets the label's id, and its hint and error are announced with it (aria-describedby).
 */
export function Field({ label, error, hint, className = "", style, children }) {
  const autoId = useId();
  const hintId = `${autoId}-hint`;
  const errorId = `${autoId}-error`;
  let controlId;
  const content = Children.map(children, (child) => {
    if (controlId || !isValidElement(child)) return child;
    const isControl = (NATIVE.includes(child.type) && child.props.type !== "checkbox") || child.type?.isFieldControl;
    if (!isControl) return child;
    controlId = child.props.id || autoId;
    const describedBy = [child.props["aria-describedby"], hint && hintId, error && errorId].filter(Boolean).join(" ") || undefined;
    return cloneElement(child, { id: controlId, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined });
  });
  return (
    <div className={`field ${error ? "has-error " : ""}${className}`.trim()} style={style}>
      {label && <label htmlFor={controlId}>{label}</label>}
      {content}
      {hint && <span className="hint" id={hintId}>{hint}</span>}
      {error && <div className="error" id={errorId}>{error}</div>}
    </div>
  );
}

export const Loading = ({ text = "Loading…" }) => <p className="loading" role="status">{text}</p>;

/** A failed load, with a Retry button when `onRetry` is given. */
export function ErrorAlert({ error, onRetry, children }) {
  if (!error) return null;
  return (
    <div className="alert alert-error alert-row" role="alert">
      <span>{children || error.message || String(error)}</span>
      {onRetry && <button type="button" className="btn btn-outline btn-sm" onClick={onRetry}>Try again</button>}
    </div>
  );
}

/** Message for an access/missing error on a single record, without revealing anything about it. */
export function recordError(error, noun) {
  if (error?.status === 403) return `You do not have access to this ${noun}.`;
  if (error?.status === 404) return `This ${noun} could not be found. It may have been removed.`;
  return error?.message;
}
