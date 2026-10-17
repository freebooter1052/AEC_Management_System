"""
Thin data-access layer over CouchDB.

Every business document carries a `type` field (student, counsellor, user,
university, audit_log, ...) - the same convention used by the university
dataset already loaded into CouchDB. Queries use Mango (`_find`) selectors
backed by the indexes created by `manage.py init_couchdb`.

Two selector shapes Mango cannot answer from an index are answered here instead, transparently:
  * `student_id: {"$in": [...]}` (a counsellor's caseload, one student's records) - one multi-key lookup
    in the `by_student` view, then the rest of the selector, the sort and the paging in memory;
  * `_id: {"$in": [...]}` (batched name lookups) - a primary-key lookup in `_all_docs`.
Both are bounded (SCOPED_MAX keys). Counts of a whole type, optionally by status, come from reduce views.
See apps/core/couch_views.py for the measurements behind this.
"""

import hashlib
import re
import uuid
from datetime import date, datetime, timezone

from django.conf import settings

from . import mango
from .couch_views import DESIGN_DOC
from .db import get_db

# Upper bound for "fetch everything" queries (counts, small master lists).
_SCAN_LIMIT = 100_000
# Largest `$in` list answered by key lookups (a counsellor's caseload is far smaller).
SCOPED_MAX = 1000
# Fields readable from a `by_student` view row without loading the document.
_ROW_FIELDS = {"_id", "type", "student_id", "status"}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_iso(value: datetime) -> str:
    """An aware datetime as the stored UTC string (`2026-10-13T18:24:04Z`)."""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> date:
    """Today's date in UTC (the server's TIME_ZONE); used for deadline arithmetic."""
    return datetime.now(timezone.utc).date()


def new_id(doc_type: str) -> str:
    return f"{doc_type}_{uuid.uuid4().hex[:12]}"


def stable_id(doc_type: str, *parts: str) -> str:
    """A deterministic `<type>_<12 hex>` id for a natural key. Writing the same key twice then collides
    (409) instead of creating a duplicate, which makes event-driven writes idempotent."""
    digest = hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]
    return f"{doc_type}_{digest}"


def get(doc_id: str, doc_type: str | None = None) -> dict | None:
    """Fetch a document by id; returns None if missing or of another type."""
    if not doc_id or doc_id.startswith("_"):
        return None
    doc = get_db().get(doc_id)
    if doc is None:
        return None
    doc = dict(doc)
    if doc_type and doc.get("type") != doc_type:
        return None
    return doc


def save(doc: dict) -> dict:
    """Create or update a document. Raises couchdb.http.ResourceConflict on a stale _rev."""
    doc_id, rev = get_db().save(doc)
    doc["_id"], doc["_rev"] = doc_id, rev
    return doc


def bulk_save(docs: list[dict]) -> list[tuple[bool, str, object]]:
    """
    Write several documents in one `_bulk_docs` request. CouchDB applies each one independently, so the
    result is per document: `(True, id, new_rev)` or `(False, id, error)`. Successful docs get their new
    `_rev`; callers must handle the failures (typically a stale-revision conflict).
    """
    if not docs:
        return []
    results = []
    for doc, (ok, doc_id, rev_or_error) in zip(docs, get_db().update(docs)):
        if ok:
            doc["_id"], doc["_rev"] = doc_id, rev_or_error
        results.append((ok, doc_id, rev_or_error))
    return results


def delete(doc: dict) -> None:
    get_db().delete(doc)


def put_attachment(doc: dict, content: bytes, name: str, content_type: str) -> dict:
    """Store a binary attachment on a saved document. Updates `doc["_rev"]` in place."""
    get_db().put_attachment(doc, content, filename=name, content_type=content_type)
    return doc


def get_attachment(doc_id: str, name: str) -> bytes | None:
    stream = get_db().get_attachment(doc_id, name)
    return stream.read() if stream is not None else None


def view(name: str, **params) -> list:
    """Rows of a view in the `aec_stats` design document (or `_all_docs`). Rows have id/key/value/doc."""
    path = name if name.startswith("_") else f"{DESIGN_DOC}/{name}"
    return list(get_db().view(path, **params))


def view_count(name: str, **params) -> int:
    """Total of a `_count` reduce over a key range or key set."""
    return sum(r.value or 0 for r in view(name, **params))


def status_counts(doc_type: str) -> dict:
    """{status: count} for every document of a type, from the `by_type_status` reduce view."""
    return {r.key[1]: r.value for r in view("by_type_status", startkey=[doc_type], endkey=[doc_type, {}], group_level=2)}


def get_many(ids) -> list[dict]:
    """Documents by id via `_all_docs` (a primary-key lookup); missing or deleted ids are skipped."""
    wanted = list(dict.fromkeys(i for i in ids if i and not str(i).startswith("_")))
    if not wanted:
        return []
    return [dict(r.doc) for r in view("_all_docs", keys=wanted, include_docs=True) if getattr(r, "doc", None)]


def _in_list(selector: dict, field: str):
    cond = selector.get(field)
    if isinstance(cond, dict) and set(cond) == {"$in"} and isinstance(cond["$in"], (list, tuple))             and len(cond["$in"]) <= SCOPED_MAX:
        return list(cond["$in"])
    return None


def _candidates(selector: dict, fields) -> list[dict] | None:
    """Candidate documents for a selector Mango could not answer from an index, or None to use Mango."""
    doc_type = selector.get("type")
    student_ids = _in_list(selector, "student_id")
    if isinstance(doc_type, str) and student_ids is not None:
        keys = [[doc_type, s] for s in dict.fromkeys(student_ids)]
        if not keys:
            return []
        rows_only = fields and set(fields) <= _ROW_FIELDS and set(selector) <= _ROW_FIELDS
        rows = view("by_student", keys=keys, reduce=False, include_docs=not rows_only)
        if rows_only:
            return [{"_id": r.id, "type": r.key[0], "student_id": r.key[1], "status": r.value} for r in rows]
        return [dict(r.doc) for r in rows if getattr(r, "doc", None)]
    ids = _in_list(selector, "_id")
    if ids is not None:
        return get_many(ids)
    return None


def find(selector: dict, *, fields=None, sort=None, limit: int = _SCAN_LIMIT, skip: int = 0) -> list[dict]:
    candidates = _candidates(selector, fields)
    if candidates is not None:
        docs = mango.sort_docs([d for d in candidates if mango.matches(d, selector)], sort)[skip:skip + limit]
        return mango.project(docs, fields) if fields else docs
    query = {"selector": selector, "limit": limit, "skip": skip}
    if fields:
        query["fields"] = list(fields)
    if sort:
        query["sort"] = sort
    return [dict(d) for d in get_db().find(query)]


def find_one(selector: dict) -> dict | None:
    docs = find(selector, limit=1)
    return docs[0] if docs else None


def _fast_count(selector: dict) -> int | None:
    """Counts a reduce view can answer exactly: a whole type, optionally narrowed to statuses."""
    doc_type = selector.get("type")
    if not isinstance(doc_type, str):
        return None
    rest = {k: v for k, v in selector.items() if k != "type"}
    if rest == {"created_at": {"$gt": None}}:
        return view_count("by_type", key=[doc_type, True])
    if not rest:
        return view_count("by_type", startkey=[doc_type], endkey=[doc_type, {}])
    if set(rest) == {"status"}:
        status = rest["status"]
        statuses = status["$in"] if isinstance(status, dict) and set(status) == {"$in"} else [status] if isinstance(status, str) else None
        if statuses is not None:
            return view_count("by_type_status", keys=[[doc_type, s] for s in dict.fromkeys(statuses)], group=True) if statuses else 0
    return None


def count(selector: dict) -> int:
    fast = _fast_count(selector)
    return fast if fast is not None else len(find(selector, fields=["_id"]))


def page_params(request) -> tuple[int, int]:
    """Read ?page=&page_size= (1-based page), clamped to sane bounds."""
    def _int(name, default):
        try:
            return int(request.query_params.get(name, default))
        except (TypeError, ValueError):
            return default

    page = max(1, _int("page", 1))
    page_size = min(max(1, _int("page_size", settings.DEFAULT_PAGE_SIZE)), settings.MAX_PAGE_SIZE)
    return page, page_size


def paginate(request, selector: dict, *, sort=None, fields=None, serialize=None, serialize_page=None) -> dict:
    """
    Run a paginated Mango query and return {count, page, page_size, total_pages, results}.
    `serialize` maps one doc; `serialize_page` maps the whole page (for batched lookups).
    """
    page, page_size = page_params(request)
    total = count(selector)
    docs = find(selector, fields=fields, sort=sort, limit=page_size, skip=(page - 1) * page_size)
    if serialize_page:
        results = serialize_page(docs)
    else:
        results = [serialize(d) for d in docs] if serialize else docs
    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
        "results": results,
    }


def contains_pattern(text: str) -> str:
    """Case-insensitive 'contains' regex for a Mango `$regex`, with user input escaped."""
    return f"(?i){re.escape(text.strip())}"


def public(doc: dict) -> dict:
    """Expose `_id` as `id` and `_rev` as `rev` (clients echo `rev` back for conflict detection).
    Attachment stubs stay internal; files are served by their own endpoints."""
    out = {k: v for k, v in doc.items() if k not in ("_id", "_rev", "_attachments")}
    return {"id": doc.get("_id"), "rev": doc.get("_rev"), **out}
