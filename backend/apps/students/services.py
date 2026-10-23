"""
`student` documents (SRS 4.2, 6.1, 6.4) and the student <-> counsellor assignment.

    {
      "_id": "student_1a2b3c4d5e6f", "type": "student", "user_id": "user_...",
      "personal": {
        "first_name": "...", "last_name": "...", "preferred_name": "...", "email": "...",
        "phone": {"dial_code": "+91", "number": "9876543210"},
        "date_of_birth": "2003-05-18", "gender": "", "citizenship": "India",
        "address": {"line1": "", "city": "", "state": "", "country": "", "postal_code": ""}
      },
      "academic": {
        "degree": "B.E. Computer Science", "institution": "...", "cgpa": 8.5, "gpa_scale": 10,
        "graduation_year": 2026, "work_experience_years": 0, "gre_status": "",
        "english_test": {"test_type": "IELTS", "overall": 7.5, "listening": 8, "reading": 7.5, "writing": 7, "speaking": 7}
      },
      "preferences": {
        "countries": ["Germany", "Canada"], "course_areas": ["Computer Science", "AI/ML"],
        "degree_level": "Masters", "intake": "Fall 2027",
        "budget": {"min": 15000, "max": 25000, "currency": "EUR"}, "requires_scholarship": false
      },
      "counsellor_id": "counsellor_..." | null, "counsellor_assigned_at": "...",
      "profile_completion": {"overall": 64, "personal": 80, "academic": 57, "preferences": 60, "missing": [...]},
      "onboarding_status": "registered" | "in_progress" | "profile_complete" | "ready",
      "application_ids": [], "created_at": "...", "updated_at": "..."
    }
"""

from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.core import audit, repository
from apps.core.roles import ADMIN, COUNSELLOR, STUDENT
from apps.counsellors import services as counsellor_services
from apps.notifications import events

# (section, dotted path, human label) - drives profile completion and the "missing" checklist.
COMPLETION_FIELDS = [
    ("personal", "first_name", "First name"),
    ("personal", "last_name", "Last name"),
    ("personal", "phone.number", "Phone number"),
    ("personal", "date_of_birth", "Date of birth"),
    ("personal", "citizenship", "Citizenship"),
    ("personal", "address.city", "City of residence"),
    ("academic", "degree", "Highest degree"),
    ("academic", "institution", "Institution"),
    ("academic", "cgpa", "CGPA / GPA"),
    ("academic", "gpa_scale", "GPA scale"),
    ("academic", "graduation_year", "Graduation year"),
    ("academic", "english_test.test_type", "English test type"),
    ("academic", "english_test.overall", "English test score"),
    ("preferences", "countries", "Preferred countries"),
    ("preferences", "course_areas", "Preferred course areas"),
    ("preferences", "degree_level", "Target degree level"),
    ("preferences", "intake", "Preferred intake"),
    ("preferences", "budget.max", "Budget"),
]
SECTIONS = ("personal", "academic", "preferences")


def build_student(*, user_id: str, email: str, first_name: str, last_name: str, dial_code: str = "",
                  phone: str = "", citizenship: str = "", degree_level: str = "") -> dict:
    now = repository.now_iso()
    doc = {
        "_id": repository.new_id("student"),
        "type": "student",
        "user_id": user_id,
        "personal": {
            "first_name": first_name.strip(),
            "last_name": last_name.strip(),
            "preferred_name": "",
            "email": email,
            "phone": {"dial_code": dial_code, "number": phone},
            "date_of_birth": None,
            "gender": "",
            "citizenship": citizenship,
            "address": {"line1": "", "city": "", "state": "", "country": "", "postal_code": ""},
        },
        "academic": {
            "degree": "",
            "institution": "",
            "cgpa": None,
            "gpa_scale": None,
            "graduation_year": None,
            "work_experience_years": None,
            "gre_status": "",
            "english_test": {"test_type": "", "overall": None, "listening": None, "reading": None,
                             "writing": None, "speaking": None},
        },
        "preferences": {
            "countries": [],
            "course_areas": [],
            "degree_level": degree_level,
            "intake": "",
            "budget": {"min": None, "max": None, "currency": "USD"},
            "requires_scholarship": False,
        },
        "counsellor_id": None,
        "counsellor_assigned_at": None,
        "application_ids": [],
        "created_at": now,
        "updated_at": now,
    }
    refresh_derived(doc)
    return doc


# ---------------------------------------------------------------------------
# Derived fields
# ---------------------------------------------------------------------------
def _lookup(data: dict, dotted: str):
    for part in dotted.split("."):
        if not isinstance(data, dict):
            return None
        data = data.get(part)
    return data


def _is_filled(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def completion(doc: dict) -> dict:
    per_section = {s: [0, 0] for s in SECTIONS}  # [filled, total]
    missing = []
    for section, path, label in COMPLETION_FIELDS:
        per_section[section][1] += 1
        if _is_filled(_lookup(doc.get(section, {}), path)):
            per_section[section][0] += 1
        else:
            missing.append({"section": section, "field": f"{section}.{path}", "label": label})
    filled = sum(f for f, _ in per_section.values())
    result = {s: round(100 * f / t) for s, (f, t) in per_section.items()}
    result["overall"] = round(100 * filled / len(COMPLETION_FIELDS))
    result["missing"] = missing
    return result


def refresh_derived(doc: dict) -> None:
    comp = completion(doc)
    doc["profile_completion"] = comp
    if comp["overall"] == 100:
        doc["onboarding_status"] = "ready" if doc.get("counsellor_id") else "profile_complete"
    elif comp["overall"] >= 40:
        doc["onboarding_status"] = "in_progress"
    else:
        doc["onboarding_status"] = "registered"


def deep_merge(target: dict, changes: dict) -> None:
    """Merge validated partial data into a document: nested dicts merge, everything else replaces."""
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_merge(target[key], value)
        else:
            target[key] = value


def apply_update(doc: dict, changes: dict) -> dict:
    for section in SECTIONS:
        if section in changes:
            deep_merge(doc.setdefault(section, {}), changes[section])
    doc["updated_at"] = repository.now_iso()
    refresh_derived(doc)
    return doc


# ---------------------------------------------------------------------------
# Representation
# ---------------------------------------------------------------------------
def full_name(doc: dict) -> str:
    p = doc.get("personal", {})
    return f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()


def serialize(doc: dict, *, with_counsellor: bool = True) -> dict:
    data = repository.public(doc)
    data["full_name"] = full_name(doc)
    if with_counsellor:
        counsellor = repository.get(doc["counsellor_id"], "counsellor") if doc.get("counsellor_id") else None
        data["counsellor"] = counsellor_services.contact_card(counsellor)
    return data


def summary(doc: dict) -> dict:
    """Compact row for rosters and lists."""
    p, prefs = doc.get("personal", {}), doc.get("preferences", {})
    return {
        "id": doc["_id"],
        "full_name": full_name(doc),
        "email": p.get("email", ""),
        "citizenship": p.get("citizenship", ""),
        "countries": prefs.get("countries", []),
        "degree_level": prefs.get("degree_level", ""),
        "intake": prefs.get("intake", ""),
        "counsellor_id": doc.get("counsellor_id"),
        "profile_completion": doc.get("profile_completion", {}).get("overall", 0),
        "onboarding_status": doc.get("onboarding_status", "registered"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }



def attach_counsellor_names(rows: list[dict]) -> list[dict]:
    """Add `counsellor_name` to summary rows with a single lookup, so clients never show raw ids."""
    ids = sorted({r["counsellor_id"] for r in rows if r.get("counsellor_id")})
    names = {}
    if ids:
        names = {c["_id"]: c.get("name", "") for c in
                 repository.find({"type": "counsellor", "_id": {"$in": ids}}, fields=["_id", "name"])}
    for r in rows:
        r["counsellor_name"] = names.get(r.get("counsellor_id")) if r.get("counsellor_id") else None
    return rows


def summary_page(docs: list[dict]) -> list[dict]:
    """Roster rows for a page of students, with counsellor names resolved."""
    return attach_counsellor_names([summary(d) for d in docs])

# ---------------------------------------------------------------------------
# Access rules (SRS 4.1): students -> own profile; counsellors -> assigned; admins -> all
# ---------------------------------------------------------------------------
def can_access(user, doc: dict) -> bool:
    if user.role == ADMIN:
        return True
    if user.role == COUNSELLOR:
        return bool(doc.get("counsellor_id")) and doc.get("counsellor_id") == user.profile_id
    if user.role == STUDENT:
        return doc.get("user_id") == user.id
    return False


def accessible_student_ids(user) -> list[str] | None:
    """Students whose workflow records (applications, documents, sessions) the user may see; None = all."""
    if user.role == ADMIN:
        return None
    if user.role == COUNSELLOR:
        return [s["_id"] for s in repository.find({"type": "student", "counsellor_id": user.profile_id}, fields=["_id"])]
    return [user.profile_id] if user.role == STUDENT and user.profile_id else []


def scope_to_students(user, selector: dict, student_id: str | None = None) -> dict:
    """
    Restrict a workflow-record selector to the user's students. An explicit `student_id` filter
    outside that set is refused (403) rather than silently returning nothing.
    """
    allowed = accessible_student_ids(user)
    if student_id:
        if allowed is not None and student_id not in allowed:
            raise PermissionDenied("You do not have access to this student.")
        selector["student_id"] = student_id
    elif allowed is not None:
        selector["student_id"] = {"$in": allowed}
    return selector


WORKFLOW_TYPES = ("application", "document", "counselling_session", "recommendation", "recommendation_run",
                  "statement", "reference")


def delete_workflow_records(student_id: str) -> int:
    """Remove a deleted student's applications (with history), documents, sessions and recommendations."""
    removed = 0
    for doc_type in WORKFLOW_TYPES:
        for doc in repository.find({"type": doc_type, "student_id": student_id}):
            if doc_type == "application":
                for h in repository.find({"type": "application_history", "application_id": doc["_id"]}):
                    repository.delete(h)
                    removed += 1
            repository.delete(doc)
            removed += 1
    return removed


def delete_notifications(user_id: str | None) -> int:
    """Remove a deleted account's notifications, in bounded batches."""
    removed = 0
    while user_id:
        batch = repository.find({"type": "notification", "recipient_user_id": user_id}, limit=500)
        for doc in batch:
            repository.delete(doc)
        removed += len(batch)
        if len(batch) < 500:
            break
    return removed


def get_accessible(user, student_id: str) -> dict:
    """The student document, or 404 / 403."""
    doc = repository.get(student_id, "student") if student_id else None
    if doc is None:
        raise NotFound("Student not found.")
    if not can_access(user, doc):
        raise PermissionDenied("You do not have access to this student.")
    return doc


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------
def assign_counsellor(student: dict, counsellor_id: str | None, *, actor, request=None, notify: bool = True) -> dict:
    """
    Assign, reassign or (with None) unassign a counsellor, keeping both sides in step. The student and the
    new counsellor are notified (`notify=False` for the sample-data seeder, whose documents are all tagged).
    """
    old_id = student.get("counsellor_id")
    if counsellor_id == old_id:
        return student

    new_counsellor = None
    if counsellor_id:
        new_counsellor = repository.get(counsellor_id, "counsellor")
        if new_counsellor is None:
            raise ValidationError({"counsellor_id": ["Counsellor not found."]})
        if not new_counsellor.get("is_active", True):
            raise ValidationError({"counsellor_id": ["This counsellor is inactive."]})
        if not counsellor_services.has_capacity(new_counsellor):
            raise ValidationError({"counsellor_id": ["This counsellor has reached their student capacity."]})

    student["counsellor_id"] = counsellor_id
    student["counsellor_assigned_at"] = repository.now_iso() if counsellor_id else None
    student["updated_at"] = repository.now_iso()
    refresh_derived(student)
    repository.save(student)

    if old_id:
        old_counsellor = repository.get(old_id, "counsellor")
        if old_counsellor is not None:
            counsellor_services.remove_student(old_counsellor, student["_id"])
            repository.save(old_counsellor)
    if new_counsellor is not None:
        counsellor_services.add_student(new_counsellor, student["_id"])
        repository.save(new_counsellor)

    audit.record(
        "student.counsellor_assigned" if counsellor_id else "student.counsellor_unassigned",
        request=request, actor=actor, target_id=student["_id"],
        details={"from": old_id, "to": counsellor_id},
    )
    if new_counsellor is not None and notify:
        events.counsellor_assigned(student, new_counsellor)
    return student
