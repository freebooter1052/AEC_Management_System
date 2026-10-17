/* Top-bar bell (SRS 4.10): unread count, the latest notifications, mark read, and a link to the full list. */
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { badgeCount, categoryLabel, safeLink, timeAgo } from "../lib/notifications";
import { useSubmit } from "../lib/useSubmit";

const POLL_MS = 60_000;
const LATEST = 6;

export default function NotificationBell() {
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [busy, run] = useSubmit();
  const rootRef = useRef(null);
  const buttonRef = useRef(null);
  const location = useLocation();
  const navigate = useNavigate();

  const refreshCount = useCallback(() => {
    api("/notifications/unread-count/").then((d) => setUnread(d.unread), () => { /* the bell stays as it was; pages report errors */ });
  }, []);

  // Poll while the tab is visible, and after every navigation (an action elsewhere may have created one).
  useEffect(() => {
    refreshCount();
    const tick = () => { if (document.visibilityState === "visible") refreshCount(); };
    const id = setInterval(tick, POLL_MS);
    document.addEventListener("visibilitychange", tick);
    return () => { clearInterval(id); document.removeEventListener("visibilitychange", tick); };
  }, [refreshCount, location.pathname]);

  const load = useCallback(() => {
    setError(null);
    api("/notifications/", { query: { page_size: LATEST } }).then((d) => { setItems(d.results); setUnread(d.unread); }, setError);
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    load();
    const onDown = (e) => { if (!rootRef.current?.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === "Escape") { setOpen(false); buttonRef.current?.focus(); } };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open, load]);

  async function openItem(n) {
    setOpen(false);
    if (!n.is_read) {
      setUnread((u) => Math.max(0, u - 1));
      api(`/notifications/${encodeURIComponent(n.id)}/read/`, { method: "POST", body: {} }).catch(refreshCount);
    }
    const to = safeLink(n.link);
    navigate(to || "/notifications/");
  }

  const markAll = () => run(async () => {
    try {
      await api("/notifications/read-all/", { method: "POST", body: {} });
      load();
    } catch (err) { setError(err); }
  });

  const label = unread ? `Notifications, ${unread} unread` : "Notifications";
  return (
    <div className="bell" ref={rootRef}>
      <button ref={buttonRef} type="button" className="bell-btn" aria-label={label} aria-haspopup="dialog" aria-expanded={open}
        aria-controls="notification-panel" onClick={() => setOpen((o) => !o)}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
        </svg>
        {unread > 0 && <span className="bell-count" aria-hidden="true">{badgeCount(unread)}</span>}
      </button>
      {open && (
        <div className="notif-panel" id="notification-panel" role="dialog" aria-label="Recent notifications">
          <div className="notif-head">
            <strong>Notifications</strong>
            <button type="button" className="link-btn small" onClick={markAll} disabled={busy || !unread}>{busy ? "Marking…" : "Mark all read"}</button>
          </div>
          {error ? (
            <div className="notif-empty"><p>{error.message}</p><button type="button" className="btn btn-outline btn-sm" onClick={load}>Try again</button></div>
          ) : !items ? <p className="notif-empty" role="status">Loading…</p>
            : !items.length ? <p className="notif-empty">You have no notifications yet.</p> : (
              <ul className="notif-list">
                {items.map((n) => (
                  <li key={n.id}>
                    <button type="button" className={`notif-item${n.is_read ? "" : " unread"}`} onClick={() => openItem(n)}>
                      <span className="notif-meta"><span>{categoryLabel(n.category)}</span><span>{timeAgo(n.created_at)}</span></span>
                      <span className="notif-title">{!n.is_read && <span className="sr-only">Unread: </span>}{n.title}</span>
                      <span className="notif-msg">{n.message}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          <Link className="notif-all" to="/notifications/" onClick={() => setOpen(false)}>View all notifications</Link>
        </div>
      )}
    </div>
  );
}
