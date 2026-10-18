"""
`counsellor` documents (SRS 4.3, 6.1).

    {
      "_id": "counsellor_9f8e7d6c5b4a", "type": "counsellor", "user_id": "user_...",
      "name": "Marcus Chen", "email": "marcus@agency.org", "phone": "+65 6712 8840",
      "specialization": "UK & Ireland postgraduate", "region": "SE Asia Hub",
      "max_students": 25, "is_active": true,
      "assigned_student_ids": ["student_..."],
      "created_at": "...", "updated_at": "..."
    }

`student.counsellor_id` is the source of truth for an assignment.
`assigned_student_ids` is a denormalised copy kept in step with it (SRS 6.1),
but workload numbers are always counted from the students themselves
(`assigned_counts`) so a stale list can never show wrong figures.
"""

from apps.core import repository

DEFAULT_MAX_STUDENTS = 25


def build_counsellor(*, user_id: str, name: str, email: str, phone: str = "", specialization: str = "",
                     region: str = "", max_students: int = DEFAULT_MAX_STUDENTS) -> dict:
    now = repository.now_iso()
    return {
        "_id": repository.new_id("counsellor"),
        "type": "counsellor",
        "user_id": user_id,
        "name": name.strip(),
        "email": email,
        "phone": phone,
        "specialization": specialization,
        "region": region,
        "max_students": max_students,
        "is_active": True,
        "assigned_student_ids": [],
        "created_at": now,
        "updated_at": now,
    }


def assigned_counts(counsellor_ids=None) -> dict[str, int]:
    """Number of students per counsellor id, counted from `student.counsellor_id` (one reduce-view request)."""
    if counsellor_ids is not None:
        wanted = [c for c in dict.fromkeys(counsellor_ids) if c]
        rows = repository.view("students_by_counsellor", keys=wanted, group=True) if wanted else []
    else:
        rows = repository.view("students_by_counsellor", group=True)
    return {r.key: r.value for r in rows if r.key}


def assigned_count(counsellor_id: str) -> int:
    return repository.count({"type": "student", "counsellor_id": counsellor_id})


def workload(doc: dict, assigned: int | None = None) -> dict:
    """Capacity summary. Pass `assigned` (from `assigned_counts`) for list views; otherwise it is counted."""
    if assigned is None:
        assigned = assigned_count(doc["_id"]) if doc.get("_id") else 0
    capacity = doc.get("max_students") or DEFAULT_MAX_STUDENTS
    return {
        "assigned": assigned,
        "capacity": capacity,
        "available": max(0, capacity - assigned),
        "utilisation_pct": round(100 * assigned / capacity) if capacity else 0,
    }


def has_capacity(doc: dict) -> bool:
    return workload(doc)["available"] > 0


def serialize(doc: dict, assigned: int | None = None) -> dict:
    data = repository.public(doc)
    data["workload"] = workload(doc, assigned)
    return data


def serialize_many(docs: list[dict]) -> list[dict]:
    """Serialize a page of counsellors with one student-count query instead of one per counsellor."""
    counts = assigned_counts(d["_id"] for d in docs)
    return [serialize(d, counts.get(d["_id"], 0)) for d in docs]


def contact_card(doc: dict | None) -> dict | None:
    """The read-only counsellor summary a student sees on their profile."""
    if doc is None:
        return None
    return {
        "id": doc["_id"],
        "name": doc.get("name", ""),
        "email": doc.get("email", ""),
        "phone": doc.get("phone", ""),
        "specialization": doc.get("specialization", ""),
        "region": doc.get("region", ""),
        "is_active": doc.get("is_active", True),
    }


def add_student(doc: dict, student_id: str) -> None:
    ids = doc.setdefault("assigned_student_ids", [])
    if student_id not in ids:
        ids.append(student_id)
    doc["updated_at"] = repository.now_iso()


def remove_student(doc: dict, student_id: str) -> None:
    doc["assigned_student_ids"] = [s for s in doc.get("assigned_student_ids", []) if s != student_id]
    doc["updated_at"] = repository.now_iso()
