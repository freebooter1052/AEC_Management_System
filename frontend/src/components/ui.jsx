import { Children, cloneElement, isValidElement, useId } from "react";
import { formatDate, plural } from "../lib/format";

// Workflow vocabularies (backend apps/core/vocab.py) -> badge styles.
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

export const AppStatusBadge = ({ status }) => <span className={APP_STATUS_CLASS[status] || "badge"}>{status || "—"}</span>;
export const DocStatusBadge = ({ status }) => <span className={DOC_STATUS_CLASS[status] || "badge"}>{status || "—"}</span>;
export const SessionStatusBadge = ({ status }) => <span className={SESSION_STATUS_CLASS[status] || "badge"}>{status || "—"}</span>;

export function StatusBadge({ status }) {
  const [label, cls] = ONBOARDING[status] || [status || "—", "badge"];
  return <span className={cls}>{label}</span>;
}

/** Deadline date plus a countdown badge, from an application's `deadline_info`. */
export function DeadlineBadge({ info }) {
  if (!info || !info.date) return <span className="muted">No deadline</span>;
  const n = info.days_left;
  const text = {
    overdue: `${plural(Math.abs(n), "day")} overdue`,
    due_soon: n === 0 ? "Due today" : `${plural(n, "day")} left`,
    open: `${plural(n, "day")} left`,
    submitted: "Submitted",
    closed: "Closed",
  }[info.state] || "";
  const cls = { overdue: "badge badge-err", due_soon: "badge badge-warn", submitted: "badge badge-ok" }[info.state] || "badge";
  return <span className="deadline"><span className="date">{formatDate(info.date)}</span><span className={cls}>{text}</span></span>;
}

export function ProgressBar({ pct, label }) {
  const p = Math.max(0, Math.min(100, Number(pct) || 0));
  return (
    <div className="bar-row">
      <div className={p >= 100 ? "bar ok" : "bar"} role="progressbar" aria-valuenow={p} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${p}%` }} /></div>
      <span className="num">{label ?? `${p}%`}</span>
    </div>
  );
}

export function Kpi({ label, value, children }) {
  return <div className="kpi"><div className="label">{label}</div><div className="value">{value}</div><div className="sub">{children}</div></div>;
}

/** Pagination controls for a {count, page, page_size, total_pages} payload. */
export function Pager({ data, onPage }) {
  if (!data || !data.count) return <div className="pager" />;
  const from = (data.page - 1) * data.page_size + 1;
  const to = Math.min(data.count, data.page * data.page_size);
  return (
    <div className="pager">
      <span>{from}–{to} of {data.count}</span>
      <span className="toolbar">
        <button className="btn btn-outline btn-sm" disabled={data.page <= 1} onClick={() => onPage(data.page - 1)}>Previous</button>
        <button className="btn btn-outline btn-sm" disabled={data.page >= data.total_pages} onClick={() => onPage(data.page + 1)}>Next</button>
      </span>
    </div>
  );
}

/** A labelled form field. The first input/select/textarea child is linked to the label automatically. */
export function Field({ label, error, hint, className = "", style, children }) {
  const autoId = useId();
  let controlId;
  const content = Children.map(children, (child) => {
    if (!controlId && isValidElement(child) && ["input", "select", "textarea"].includes(child.type) && child.props.type !== "checkbox") {
      controlId = child.props.id || autoId;
      return cloneElement(child, { id: controlId });
    }
    return child;
  });
  return (
    <div className={`field ${className}`.trim()} style={style}>
      {label && <label htmlFor={controlId}>{label}</label>}
      {content}
      {hint && <span className="hint">{hint}</span>}
      {error && <div className="error">{error}</div>}
    </div>
  );
}

export const Loading = ({ text = "Loading…" }) => <p className="loading">{text}</p>;
export const ErrorAlert = ({ error }) => (error ? <div className="alert alert-error">{error.message || String(error)}</div> : null);
