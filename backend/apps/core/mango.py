"""
In-memory evaluation of the Mango subset the app uses: selectors ($eq, $ne, $in, $nin, $gt, $gte, $lt, $lte,
$regex, $exists, $or, $and, dotted paths), sort and field projection, with CouchDB's collation order.

Used by `repository` to finish queries it answers from a view or a primary-key lookup (bounded sets that
Mango could not answer with an index), and by the in-memory CouchDB stand-in in the tests, so both
apply exactly the same rules.
"""

import re


def collate(value):
    """CouchDB collation order: null < false < true < numbers < strings < arrays < objects."""
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
    if isinstance(value, (list, tuple)):
        return (5, [collate(v) for v in value])
    return (6, str(value))


def lookup(doc, dotted):
    """(value, present) for a dotted path."""
    for part in dotted.split("."):
        if not isinstance(doc, dict) or part not in doc:
            return None, False
        doc = doc[part]
    return doc, True


def _cond(op, arg, value, present):
    if op == "$exists":
        return present == arg
    if not present:
        return False  # like Mango, every other operator needs the field to exist
    if op == "$eq":
        return value == arg
    if op == "$ne":
        return value != arg
    if op == "$in":
        return value in arg
    if op == "$nin":
        return value not in arg
    if op == "$regex":
        return isinstance(value, str) and re.search(arg, value) is not None
    compare = {"$gt": lambda a, b: a > b, "$gte": lambda a, b: a >= b,
               "$lt": lambda a, b: a < b, "$lte": lambda a, b: a <= b}
    if op not in compare:
        raise ValueError(f"Unsupported Mango operator {op}")
    return compare[op](collate(value), collate(arg))


def matches(doc, selector) -> bool:
    for key, expected in selector.items():
        if key == "$or":
            if not any(matches(doc, s) for s in expected):
                return False
            continue
        if key == "$and":
            if not all(matches(doc, s) for s in expected):
                return False
            continue
        value, present = lookup(doc, key)
        if isinstance(expected, dict) and expected and all(k.startswith("$") for k in expected):
            if not all(_cond(op, arg, value, present) for op, arg in expected.items()):
                return False
        elif not present or value != expected:
            return False
    return True


def sort_docs(docs: list[dict], sort) -> list[dict]:
    """Apply a Mango sort spec. Like a sorted Mango query, documents without a sort field are left out."""
    for spec in reversed(sort or []):
        (field, direction), = spec.items()
        docs = [d for d in docs if lookup(d, field)[1]]
        docs.sort(key=lambda d: collate(lookup(d, field)[0]), reverse=direction == "desc")
    return docs


def project(docs: list[dict], fields) -> list[dict]:
    """Keep only top-level `fields` (dotted fields keep their whole top-level object)."""
    keep = {f.split(".")[0] for f in fields}
    return [{k: v for k, v in d.items() if k in keep} for d in docs]
