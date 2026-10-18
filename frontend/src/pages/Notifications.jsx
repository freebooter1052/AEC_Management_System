/* All of the signed-in user's notifications (SRS 4.10): filter, page, open, mark read or unread. */
import { useNavigate } from "react-router-dom";
import AppShell from "../components/Shell";
import { useToast } from "../components/Toast";
import { ErrorAlert, Loading, Pager } from "../components/ui";
import { api } from "../lib/api";
import { formatDateTime, plural } from "../lib/format";
import { CATEGORIES, categoryLabel, safeLink, timeAgo } from "../lib/notifications";
import { useLoad } from "../lib/useLoad";
import { useQueryState } from "../lib/useQueryState";
import { useSubmit } from "../lib/useSubmit";

const LIST_STATE = {
  unread: { default: false, type: "bool" },
  category: { default: "", allowed: ["", ...CATEGORIES.map(([k]) => k)] },
  page: { default: 1, type: "page" },
};

export default function Notifications() {
  const toast = useToast();
  const navigate = useNavigate();
  const [state, update] = useQueryState(LIST_STATE);
  const { unread, category, page } = state;
  const [busy, run] = useSubmit();
  const { data, error, loading, reload, setData } = useLoad(
    () => api("/notifications/", { query: { unread: unread ? "1" : "", category, page } }), [unread, category, page]);

  const setRead = (n, read) => run(async () => {
    try {
      const updated = await api(`/notifications/${encodeURIComponent(n.id)}/read/`, { method: "POST", body: { read } });
      setData((d) => ({ ...d, unread: d.unread + (read ? -1 : 1), results: d.results.map((x) => (x.id === n.id ? updated : x)) }));
    } catch (err) { toast(err.message, "error"); }
  });

  const markAll = () => run(async () => {
    try {
      const res = await api("/notifications/read-all/", { method: "POST", body: {} });
      toast(res.updated ? `${plural(res.updated, "notification")} marked as read` : "Everything was already read", res.updated ? "success" : "info");
      reload();
    } catch (err) { toast(err.message, "error"); }
  });

  function open(n) {
    if (!n.is_read) api(`/notifications/${encodeURIComponent(n.id)}/read/`, { method: "POST", body: {} }).catch(() => { /* the link still works */ });
    const to = safeLink(n.link);
    if (to) navigate(to);
    else setRead(n, true);
  }

  return (
    <AppShell title="Notifications" crumb="Notifications">
      <div className="page-head">
        <div>
          <h1>Notifications</h1>
          <p className="muted">Application updates, documents to provide, deadlines and follow-ups. {data ? `${plural(data.unread, "unread notification")}.` : ""}</p>
        </div>
        <div className="toolbar">
          <button type="button" className="btn btn-outline" onClick={markAll} disabled={busy || !data?.unread}>Mark all as read</button>
        </div>
      </div>
      <div className="card">
        <div className="card-head">
          <div className="toolbar">
            <select aria-label="Category" value={category} onChange={(e) => update({ category: e.target.value, page: 1 })}>
              <option value="">All categories</option>
              {CATEGORIES.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
            <label className="checkbox"><input type="checkbox" checked={unread} onChange={(e) => update({ unread: e.target.checked, page: 1 })} /> Unread only</label>
          </div>
          <span className="small muted" aria-live="polite">{data && !loading ? plural(data.count, "notification") : ""}</span>
        </div>
        <div aria-busy={loading || undefined}>
          {error ? <ErrorAlert error={error} onRetry={reload}>Could not load your notifications. {error.message}</ErrorAlert>
            : !data ? <Loading text="Loading notifications…" />
            : !data.results.length ? <p className="empty">{unread || category ? "Nothing matches these filters." : "You have no notifications yet. Application updates, deadlines and reminders will appear here."}</p>
            : (
              <ul className="notif-page-list">
                {data.results.map((n) => (
                  <li key={n.id} className={n.is_read ? "" : "unread"}>
                    <div className="notif-body">
                      <span className="notif-meta"><span className="badge">{categoryLabel(n.category)}</span>
                        <time dateTime={n.created_at} title={formatDateTime(n.created_at)}>{timeAgo(n.created_at)}</time>
                        {!n.is_read && <span className="badge badge-brand">Unread</span>}</span>
                      <button type="button" className="notif-title link-like" onClick={() => open(n)}>{n.title}</button>
                      <span className="notif-msg">{n.message}</span>
                    </div>
                    <button type="button" className="btn btn-outline btn-sm" disabled={busy} onClick={() => setRead(n, !n.is_read)}
                      aria-label={`Mark "${n.title}" as ${n.is_read ? "unread" : "read"}`}>{n.is_read ? "Mark unread" : "Mark read"}</button>
                  </li>
                ))}
              </ul>
            )}
          <Pager data={data} noun="notification" onPage={(p) => update({ page: p })} />
        </div>
      </div>
    </AppShell>
  );
}
