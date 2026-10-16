"""
Batched display-name resolution, so API responses carry names and the UI never
has to show raw document ids.
"""

from . import repository


def display_name(doc: dict) -> str:
    t = doc.get("type")
    if t == "student":
        p = doc.get("personal") or {}
        return f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
    if t == "user":
        return doc.get("full_name") or doc.get("email", "")
    return doc.get("name") or doc.get("full_name") or ""


def names_by_id(ids) -> dict[str, str]:
    """{id: display name} for any mix of student, counsellor and user ids, in one query."""
    wanted = sorted({i for i in ids if i})
    if not wanted:
        return {}
    docs = repository.find({"_id": {"$in": wanted}}, fields=["_id", "type", "personal", "name", "full_name", "email"])
    return {d["_id"]: display_name(d) for d in docs}
