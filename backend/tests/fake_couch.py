"""
In-memory stand-in for a couchdb.Database, so the API can be tested without a
running CouchDB server. Implements the subset the app uses: get/save/delete
with revision conflicts, `_bulk_docs`, Mango `find` (selectors, sort, skip, limit,
fields - evaluated by apps.core.mango, the same code the repository uses), the
`aec_stats` map/reduce views (via their Python twins in apps.core.couch_views),
`_all_docs` (optionally by keys), index() and info().
"""

import copy
import io
import uuid
from types import SimpleNamespace

from couchdb.http import ResourceConflict

from apps.core import couch_views, mango


_collate = mango.collate
_lookup = mango.lookup
matches = mango.matches


_UNSET = object()  # `key=None` asks for the null key, so "no key given" needs its own marker


def _in_range(key, startkey, endkey, inclusive_end=True):
    k = _collate(key)
    if startkey is not None and k < _collate(startkey):
        return False
    if endkey is not None and (k > _collate(endkey) or (not inclusive_end and k == _collate(endkey))):
        return False
    return True


class FakeCouchDB:
    name = "fake_counselling_db"

    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.indexes: dict = {}
        self.attachments: dict[tuple[str, str], bytes] = {}

    def get(self, doc_id, default=None):
        doc = self.docs.get(doc_id)
        return copy.deepcopy(doc) if doc is not None else default

    def save(self, doc):
        doc_id = doc.get("_id") or uuid.uuid4().hex
        current = self.docs.get(doc_id)
        if (current is None and doc.get("_rev")) or (current is not None and current["_rev"] != doc.get("_rev")):
            raise ResourceConflict(("conflict", "Document update conflict."))
        generation = int(current["_rev"].split("-")[0]) + 1 if current else 1
        rev = f"{generation}-{uuid.uuid4().hex}"
        stored = copy.deepcopy(doc)
        stored["_id"], stored["_rev"] = doc_id, rev
        self.docs[doc_id] = stored
        doc["_id"], doc["_rev"] = doc_id, rev
        return doc_id, rev

    def update(self, documents):
        """`_bulk_docs`: each document succeeds or fails on its own, like CouchDB."""
        results = []
        for doc in documents:
            try:
                doc_id, rev = self.save(doc)
                results.append((True, doc_id, rev))
            except ResourceConflict as exc:
                results.append((False, doc.get("_id"), exc))
        return results

    def delete(self, doc):
        current = self.docs.get(doc["_id"])
        if current is None or current["_rev"] != doc.get("_rev"):
            raise ResourceConflict(("conflict", "Document update conflict."))
        del self.docs[doc["_id"]]
        for key in [k for k in self.attachments if k[0] == doc["_id"]]:
            del self.attachments[key]

    def put_attachment(self, doc, content, filename=None, content_type=None):
        """Like couchdb-python: needs the current _rev, bumps it and records a stub on the stored doc."""
        stored = copy.deepcopy(self.docs.get(doc["_id"]))
        if stored is None or stored["_rev"] != doc.get("_rev"):
            raise ResourceConflict(("conflict", "Document update conflict."))
        content = content.encode() if isinstance(content, str) else bytes(content)
        stored.setdefault("_attachments", {})[filename] = {"content_type": content_type, "length": len(content), "stub": True}
        self.save(stored)
        self.attachments[(doc["_id"], filename)] = content
        doc["_rev"] = stored["_rev"]

    def get_attachment(self, id_or_doc, filename, default=None):
        doc_id = id_or_doc["_id"] if isinstance(id_or_doc, dict) else id_or_doc
        content = self.attachments.get((doc_id, filename))
        return io.BytesIO(content) if content is not None else default

    def find(self, query):
        selector = query.get("selector", {})
        docs = mango.sort_docs([d for d in self.docs.values() if matches(d, selector)], query.get("sort", []))
        skip, limit = query.get("skip", 0), query.get("limit", 25)
        docs = docs[skip:skip + limit]
        if query.get("fields"):
            docs = [{f: d[f] for f in query["fields"] if f in d} for d in docs]
        return iter(copy.deepcopy(docs))

    def view(self, name, include_docs=False, keys=None, key=_UNSET, startkey=None, endkey=None, inclusive_end=True,
             reduce=None, group=False, group_level=None, limit=None, skip=0, descending=False, **_):
        """`_all_docs` and the `aec_stats` views, with CouchDB's key/range/reduce/group semantics."""
        if name == "_all_docs":
            ids = keys if keys is not None else sorted(self.docs)
            return [SimpleNamespace(id=k, key=k, value=None, doc=copy.deepcopy(self.docs[k]) if include_docs else None)
                    for k in ids if k in self.docs]
        design, view_name = name.split("/")
        assert design == couch_views.DESIGN_DOC, name
        emit = couch_views.PY_MAPS[view_name]
        rows = sorted(((k, v, doc_id) for doc_id, d in self.docs.items() for k, v in emit(d)),
                      key=lambda r: (_collate(r[0]), r[2]))
        if keys is not None:
            rows = [r for k in keys for r in rows if _collate(r[0]) == _collate(k)]
        elif key is not _UNSET:
            rows = [r for r in rows if _collate(r[0]) == _collate(key)]
        else:
            rows = [r for r in rows if _in_range(r[0], startkey, endkey, inclusive_end)]
        if descending:
            rows.reverse()
        reducer = couch_views.REDUCED.get(view_name) if reduce is not False else None
        if reducer:
            def combine(values):
                if reducer == "_count":
                    return len(values)
                if values and isinstance(values[0], list):  # _sum of arrays is element-wise
                    return [sum(col) for col in zip(*values)]
                return sum(values)
            if not group and group_level is None:
                return [SimpleNamespace(id=None, key=None, value=combine([v for _, v, _ in rows]), doc=None)] if rows else []
            groups = {}
            for k, v, _ in rows:
                gk = k if group or not isinstance(k, list) else k[:group_level]
                groups.setdefault(repr(gk), [gk, []])[1].append(v)
            return [SimpleNamespace(id=None, key=gk, value=combine(vs), doc=None)
                    for gk, vs in sorted(groups.values(), key=lambda g: _collate(g[0]))]
        rows = rows[skip:]
        if limit is not None:
            rows = rows[:limit]
        return [SimpleNamespace(id=doc_id, key=k, value=v, doc=copy.deepcopy(self.docs[doc_id]) if include_docs else None)
                for k, v, doc_id in rows]

    def index(self):
        return self.indexes

    def info(self):
        return {"db_name": self.name, "doc_count": len(self.docs)}

    def of_type(self, doc_type):
        return [d for d in self.docs.values() if d.get("type") == doc_type]


class UnavailableCouchDB(FakeCouchDB):
    """Simulates CouchDB being down."""

    def _down(self, *args, **kwargs):
        raise ConnectionRefusedError("CouchDB is not reachable")

    get = save = update = delete = find = view = info = _down
