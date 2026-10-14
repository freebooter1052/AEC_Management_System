"""
In-memory stand-in for a couchdb.Database, so the API can be tested without a
running CouchDB server. Implements the subset the app uses: get/save/delete
with revision conflicts, Mango `find` (selectors, sort, skip, limit, fields),
index() and info().
"""

import copy
import re
import uuid
from types import SimpleNamespace

from couchdb.http import ResourceConflict


def _collate(value):
    """Approximate CouchDB collation order: null < false < true < numbers < strings < arrays < objects."""
    if value is None:
        return (0,)
    if value is False:
        return (1,)
    if value is True:
        return (2,)
    if isinstance(value, (int, float)):
        return (3, value)
    if isinstance(value, str):
        return (4, value)
    if isinstance(value, list):
        return (5, [_collate(v) for v in value])
    return (6, str(value))


def _lookup(doc, dotted):
    for part in dotted.split("."):
        if not isinstance(doc, dict) or part not in doc:
            return None, False
        doc = doc[part]
    return doc, True


def _cond(op, arg, value, present):
    if op == "$exists":
        return present == arg
    if not present:
        return False
    if op == "$eq":
        return value == arg
    if op == "$ne":
        return value != arg
    if op == "$in":
        return value in arg
    if op == "$regex":
        return isinstance(value, str) and re.search(arg, value) is not None
    cmp = {"$gt": lambda a, b: a > b, "$gte": lambda a, b: a >= b,
           "$lt": lambda a, b: a < b, "$lte": lambda a, b: a <= b}[op]
    return cmp(_collate(value), _collate(arg))


def matches(doc, selector):
    for key, expected in selector.items():
        if key == "$or":
            if not any(matches(doc, s) for s in expected):
                return False
            continue
        if key == "$and":
            if not all(matches(doc, s) for s in expected):
                return False
            continue
        value, present = _lookup(doc, key)
        if isinstance(expected, dict) and expected and all(k.startswith("$") for k in expected):
            if not all(_cond(op, arg, value, present) for op, arg in expected.items()):
                return False
        elif not present or value != expected:
            return False
    return True


class FakeCouchDB:
    name = "fake_counselling_db"

    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.indexes: dict = {}

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

    def delete(self, doc):
        current = self.docs.get(doc["_id"])
        if current is None or current["_rev"] != doc.get("_rev"):
            raise ResourceConflict(("conflict", "Document update conflict."))
        del self.docs[doc["_id"]]

    def find(self, query):
        selector = query.get("selector", {})
        docs = [d for d in self.docs.values() if matches(d, selector)]
        for spec in reversed(query.get("sort", [])):
            (field, direction), = spec.items()
            docs = [d for d in docs if _lookup(d, field)[1]]  # CouchDB's index skips docs without the field
            docs.sort(key=lambda d: _collate(_lookup(d, field)[0]), reverse=direction == "desc")
        skip, limit = query.get("skip", 0), query.get("limit", 25)
        docs = docs[skip:skip + limit]
        if query.get("fields"):
            docs = [{f: d[f] for f in query["fields"] if f in d} for d in docs]
        return iter(copy.deepcopy(docs))

    def view(self, name, include_docs=False):
        """Only `_all_docs` is supported."""
        assert name == "_all_docs", name
        return [SimpleNamespace(id=k, doc=copy.deepcopy(v) if include_docs else None) for k, v in sorted(self.docs.items())]

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

    get = save = delete = find = info = _down
