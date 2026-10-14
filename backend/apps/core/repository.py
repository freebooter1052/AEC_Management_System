"""
Thin data-access layer over CouchDB.

Every business document carries a `type` field (student, counsellor, user,
university, audit_log, ...) - the same convention used by the university
dataset already loaded into CouchDB. Queries use Mango (`_find`) selectors
backed by the indexes created by `manage.py init_couchdb`.
"""

import re
import uuid
from datetime import datetime, timezone

from django.conf import settings

from .db import get_db

# Upper bound for "fetch everything" queries (counts, small master lists).
_SCAN_LIMIT = 100_000


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(doc_type: str) -> str:
    return f"{doc_type}_{uuid.uuid4().hex[:12]}"


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


def delete(doc: dict) -> None:
    get_db().delete(doc)


def find(selector: dict, *, fields=None, sort=None, limit: int = _SCAN_LIMIT, skip: int = 0) -> list[dict]:
    query = {"selector": selector, "limit": limit, "skip": skip}
    if fields:
        query["fields"] = list(fields)
    if sort:
        query["sort"] = sort
    return [dict(d) for d in get_db().find(query)]


def find_one(selector: dict) -> dict | None:
    docs = find(selector, limit=1)
    return docs[0] if docs else None


def count(selector: dict) -> int:
    return len(find(selector, fields=["_id"]))


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
    """Expose `_id` as `id` and `_rev` as `rev` (clients echo `rev` back for conflict detection)."""
    out = {k: v for k, v in doc.items() if k not in ("_id", "_rev")}
    return {"id": doc.get("_id"), "rev": doc.get("_rev"), **out}
