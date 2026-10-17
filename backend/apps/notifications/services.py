"""
In-app `notification` documents (SRS 4.10). No email or SMS: users read them in the app.

    {
      "_id": "notification_<12 hex>",            # derived from event_key + recipient (see notify)
      "type": "notification",
      "recipient_user_id": "user_...", "recipient_role": "student" | "counsellor" | "admin",
      "category": "status_change" | "missing_document" | "deadline" | "follow_up" | "assignment",
      "title": "Application update: Submitted", "message": "...",
      "related_id": "application_..." | null, "related_type": "application" | null,
      "link": "/applications/<id>/" | null,      # where the app takes the reader
      "event_key": "app_status:application_history_...",
      "is_read": false, "read_at": null, "created_at": "..."
    }

Idempotence: the id is a hash of (event_key, recipient), so the same event can never produce two
notifications for one person - a retried request or a second reminder sweep collides with the
existing document (409) and is skipped. Seed notifications (`source: "seed"`) have random ids and no
`event_key`; they are read and marked like any other.
"""

import logging

from couchdb.http import ResourceConflict
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.core import repository
from apps.core.vocab import NOTIFICATION_CATEGORIES

logger = logging.getLogger("aec.notifications")

READ_RETRIES = 3        # re-read + re-apply attempts when marking read hits a concurrent edit
BULK_BATCH = 200        # documents per _bulk_docs request in "mark all read"
MAX_BULK_BATCHES = 25   # bound on one "mark all read" call (5,000 notifications)
NEWEST_FIRST = [{"type": "desc"}, {"recipient_user_id": "desc"}, {"created_at": "desc"}]


def notify(*, recipient_user_id: str | None, recipient_role: str, category: str, title: str, message: str,
           event_key: str, related_id: str | None = None, related_type: str | None = None,
           link: str | None = None) -> dict | None:
    """
    Create the notification for one event and one recipient. Returns the new document, or None when it
    already existed (or there is no recipient). Never raises: the business change that triggered it is
    already saved, so a failure here is logged and must not turn that change into an error.
    """
    if category not in NOTIFICATION_CATEGORIES:
        raise ValueError(f"Unknown notification category {category!r}")  # programming error: surface it
    if not recipient_user_id:
        return None
    doc_id = repository.stable_id("notification", event_key, recipient_user_id)
    try:
        if repository.get(doc_id) is not None:
            return None
        return repository.save({
            "_id": doc_id,
            "type": "notification",
            "recipient_user_id": recipient_user_id,
            "recipient_role": recipient_role,
            "category": category,
            "title": title[:140],
            "message": message[:500],
            "related_id": related_id,
            "related_type": related_type,
            "link": link,
            "event_key": event_key,
            "is_read": False,
            "read_at": None,
            "created_at": repository.now_iso(),
        })
    except ResourceConflict:
        return None  # created by a concurrent request for the same event: still exactly one
    except Exception:  # noqa: BLE001 - see docstring; the cause is logged with its traceback
        logger.exception("Could not create notification %s for %s", event_key, recipient_user_id)
        return None


# ---------------------------------------------------------------------------
# Reading (always the caller's own notifications)
# ---------------------------------------------------------------------------
def get_own(user, notification_id: str) -> dict:
    doc = repository.get(notification_id, "notification")
    if doc is None:
        raise NotFound("Notification not found.")
    if doc.get("recipient_user_id") != user.id:
        raise PermissionDenied("You do not have access to this notification.")
    return doc


def list_selector(user, *, unread: bool = False, category: str = "") -> dict:
    selector = {"type": "notification", "recipient_user_id": user.id, "created_at": {"$gt": None}}
    if unread:
        selector["is_read"] = False
    if category:
        selector["category"] = category
    return selector


def unread_summary(user) -> dict:
    rows = repository.find({"type": "notification", "recipient_user_id": user.id, "is_read": False}, fields=["category"])
    by_category = {c: 0 for c in NOTIFICATION_CATEGORIES}
    for r in rows:
        by_category[r.get("category")] = by_category.get(r.get("category"), 0) + 1
    return {"unread": len(rows), "by_category": by_category}


def latest(user, limit: int = 5) -> list[dict]:
    docs = repository.find(list_selector(user), sort=NEWEST_FIRST, limit=limit)
    return [serialize(d) for d in docs]


def serialize(doc: dict) -> dict:
    data = repository.public(doc)
    for key, default in (("related_type", None), ("link", None), ("read_at", None), ("event_key", None)):
        data.setdefault(key, default)
    data.pop("source", None)
    return data


# ---------------------------------------------------------------------------
# Read state
# ---------------------------------------------------------------------------
def _apply_read(doc: dict, read: bool) -> None:
    doc["is_read"] = read
    doc["read_at"] = repository.now_iso() if read else None


def set_read(user, notification_id: str, read: bool = True) -> dict:
    """
    Mark one notification read or unread. Setting the flag is idempotent, so on a revision conflict the
    document is re-read and the flag applied again (bounded); a concurrent change to any other field
    survives because it is never overwritten with stale data.
    """
    for attempt in range(READ_RETRIES):
        doc = get_own(user, notification_id)
        if bool(doc.get("is_read")) == read:
            return doc
        _apply_read(doc, read)
        try:
            return repository.save(doc)
        except ResourceConflict:
            if attempt == READ_RETRIES - 1:
                raise  # -> 409: reported, never claimed as saved
    raise AssertionError("unreachable")


def mark_all_read(user) -> dict:
    """Mark every unread notification of the caller read, in `_bulk_docs` batches; conflicts are retried singly."""
    updated = conflicts = 0
    for _ in range(MAX_BULK_BATCHES):
        docs = repository.find({"type": "notification", "recipient_user_id": user.id, "is_read": False}, limit=BULK_BATCH)
        if not docs:
            break
        for d in docs:
            _apply_read(d, True)
        for ok, doc_id, _ in repository.bulk_save(docs):
            if ok:
                updated += 1
                continue
            try:
                set_read(user, doc_id, True)
                updated += 1
            except (ResourceConflict, NotFound):
                conflicts += 1
        if conflicts:
            break  # don't loop on documents that keep failing
    remaining = repository.count({"type": "notification", "recipient_user_id": user.id, "is_read": False})
    return {"updated": updated, "failed": conflicts, "remaining": remaining}
