"""
`application` documents (SRS 4.5), their `application_history` trail and the
`intake` master data that supplies deadlines.

    {
      "_id": "application_06289b302c18", "type": "application",
      "student_id": "student_...", "counsellor_id": "counsellor_..." | null,
      "university_id": "university_042", "course_id": "course_0536", "intake_id": "intake_fall_2027",
      "status": "Planned", "deadline": "2027-01-15", "decision_expected": "2027-04-15",
      "tier": "Reach" | "Target" | "Safe" | null, "notes": "",
      "snapshot": {"university_name": "...", "country": "Germany", "world_rank": 45,
                   "course_title": "...", "cluster": "CS & AI", "intake_name": "Fall 2027"},
      "history_ids": ["application_history_..."], "submitted_at": null,
      "created_at": "...", "updated_at": "..."
    }

    {"_id": "application_history_...", "type": "application_history", "application_id": "application_...",
     "old_status": null | "Planned", "new_status": "Shortlisted", "changed_by": "user_...",
     "changed_by_role": "counsellor", "timestamp": "...", "remarks": "..."}

Every status change appends one history document and its id to `history_ids`.
"""

from datetime import date, timedelta

from couchdb.http import ResourceConflict
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core import audit, lookups, repository
from apps.core.roles import ADMIN, STUDENT
from apps.core.vocab import APPLICATION_STATUSES
from apps.documents import services as document_services
from apps.notifications import events
from apps.students import services as student_services

# Allowed next statuses. The main path runs top to bottom; the two backward steps let a counsellor
# undo a premature move, and Withdrawn is reachable from every open state.
TRANSITIONS = {
    "Planned": ("Shortlisted", "Withdrawn"),
    "Shortlisted": ("Documents Pending", "Planned", "Withdrawn"),
    "Documents Pending": ("Submitted", "Shortlisted", "Withdrawn"),
    "Submitted": ("Under Review", "Withdrawn"),
    "Under Review": ("Offer Received", "Rejected", "Withdrawn"),
    "Offer Received": ("Completed", "Withdrawn"),
    "Rejected": (),
    "Withdrawn": (),
    "Completed": (),
}
TERMINAL = tuple(s for s, nxt in TRANSITIONS.items() if not nxt)
PRE_SUBMISSION = ("Planned", "Shortlisted", "Documents Pending")  # the deadline still matters
STUDENT_MAY_SET = ("Withdrawn",)  # a student can withdraw; their counsellor drives everything else
DUE_SOON_DAYS = 14
STATUS_REMARKS = {"Planned": "Application created."}

assert set(TRANSITIONS) == set(APPLICATION_STATUSES)


# ---------------------------------------------------------------------------
# Deadlines
# ---------------------------------------------------------------------------
def _parse_date(value) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def deadline_info(app: dict, today: date | None = None) -> dict:
    """
    Countdown for the UI. `state`: overdue | due_soon | open while the application can still be
    submitted; submitted once it has been; closed for withdrawn/rejected applications.
    """
    today = today or repository.today()
    deadline = _parse_date(app.get("deadline"))
    days_left = (deadline - today).days if deadline else None
    status = app.get("status")
    if status in ("Withdrawn", "Rejected"):
        state = "closed"
    elif status not in PRE_SUBMISSION:
        state = "submitted"
    elif days_left is None:
        state = "open"
    elif days_left < 0:
        state = "overdue"
    elif days_left <= DUE_SOON_DAYS:
        state = "due_soon"
    else:
        state = "open"
    return {"date": app.get("deadline"), "days_left": days_left, "state": state}


def validate_deadline(deadline: date, intake: dict | None, *, allow_past: bool = False) -> str:
    if not allow_past and deadline < repository.today():
        raise ValidationError({"deadline": [f"The deadline {deadline.isoformat()} has already passed."]})
    start = _parse_date((intake or {}).get("start_date"))
    if start and deadline >= start:
        raise ValidationError({"deadline": [f"The deadline must fall before the programme starts ({start.isoformat()})."]})
    return deadline.isoformat()


def intake_is_open(intake: dict) -> bool:
    deadline = _parse_date(intake.get("application_deadline"))
    return deadline is None or deadline >= repository.today()


def serialize_intake(intake: dict) -> dict:
    data = repository.public(intake)
    data["is_open"] = intake_is_open(intake)
    return data


# ---------------------------------------------------------------------------
# Access (SRS 4.1): through the owning student
# ---------------------------------------------------------------------------
def can_access(user, app: dict, student: dict | None = None) -> bool:
    if user.role == ADMIN:
        return True
    student = student or repository.get(app.get("student_id"), "student")
    return student is not None and student_services.can_access(user, student)


def allowed_transitions(app: dict, user) -> list[str]:
    nxt = TRANSITIONS.get(app.get("status"), ())
    if user.role == STUDENT:
        return [s for s in nxt if s in STUDENT_MAY_SET]
    return list(nxt)


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------
def _history_entry(app: dict, old: str | None, new: str, actor, remarks: str) -> dict:
    return {
        "_id": repository.new_id("application_history"),
        "type": "application_history",
        "application_id": app["_id"],
        "old_status": old,
        "new_status": new,
        "changed_by": getattr(actor, "id", None),
        "changed_by_role": getattr(actor, "role", None),
        "timestamp": repository.now_iso(),
        "remarks": remarks,
    }


def _update_student_links(student_id: str, app_id: str, *, add: bool) -> None:
    """Keep `student.application_ids` in step. Re-reads on a conflict (the student may be edited concurrently)."""
    for attempt in range(3):
        student = repository.get(student_id, "student")
        if student is None:
            return
        ids = student.setdefault("application_ids", [])
        if (app_id in ids) == add:
            return
        if add:
            ids.append(app_id)
        else:
            ids.remove(app_id)
        student["updated_at"] = repository.now_iso()
        try:
            repository.save(student)
            return
        except ResourceConflict:
            if attempt == 2:
                raise


def create(*, student: dict, course_id: str, intake_id: str, deadline: date | None = None, tier: str = "",
           notes: str = "", actor, request=None) -> dict:
    course = repository.get(course_id, "course")
    if course is None:
        raise ValidationError({"course_id": ["Course not found."]})
    if course.get("is_active") is False:
        raise ValidationError({"course_id": ["This course is no longer offered."]})
    university = repository.get(course.get("university_id"), "university")
    if university is None:
        raise ValidationError({"course_id": ["This course is not linked to a university in the catalogue."]})
    intake = repository.get(intake_id, "intake")
    if intake is None:
        raise ValidationError({"intake_id": ["Intake not found."]})

    if deadline is None:
        deadline = _parse_date(intake.get("application_deadline"))
        if deadline is None:
            raise ValidationError({"deadline": ["This intake has no application deadline; enter one."]})
        if deadline < repository.today():
            raise ValidationError({"intake_id": [
                f"Applications for {intake.get('name')} closed on {deadline.isoformat()}. "
                "Choose a later intake, or enter the university's own (later) deadline."]})
    deadline_iso = validate_deadline(deadline, intake)

    for other in repository.find({"type": "application", "student_id": student["_id"], "course_id": course_id},
                                 fields=["intake_id", "status"]):
        if other.get("intake_id") == intake_id and other.get("status") not in ("Withdrawn", "Rejected"):
            raise ValidationError({"course_id": [
                f"{student_services.full_name(student)} already has an application for this course "
                f"and intake ({other.get('status')})."]})

    now = repository.now_iso()
    app = {
        "_id": repository.new_id("application"),
        "type": "application",
        "student_id": student["_id"],
        "counsellor_id": student.get("counsellor_id"),
        "university_id": university["_id"],
        "course_id": course["_id"],
        "intake_id": intake["_id"],
        "status": "Planned",
        "deadline": deadline_iso,
        "decision_expected": intake.get("decision_by"),
        "tier": tier or None,
        "notes": notes.strip(),
        "snapshot": {
            "university_name": university.get("name", ""), "country": university.get("country", ""),
            "world_rank": university.get("rank"), "course_title": course.get("title") or course.get("name", ""),
            "cluster": course.get("cluster", ""), "intake_name": intake.get("name", ""),
        },
        "history_ids": [],
        "submitted_at": None,
        "created_at": now,
        "updated_at": now,
    }
    hist = _history_entry(app, None, "Planned", actor, STATUS_REMARKS["Planned"])
    app["history_ids"].append(hist["_id"])

    # No transactions in CouchDB: write in order and undo on failure.
    repository.save(app)
    try:
        repository.save(hist)
        _update_student_links(student["_id"], app["_id"], add=True)
    except Exception:
        for d in (hist, app):
            if d.get("_rev"):
                repository.delete(d)
        raise
    audit.record("application.created", request=request, actor=actor, target_id=app["_id"],
                 details={"student_id": student["_id"], "course_id": course_id, "intake_id": intake_id})
    return app


def change_status(app: dict, new_status: str, *, remarks: str = "", actor, request=None) -> dict:
    old = app["status"]
    if new_status == old:
        raise ValidationError({"status": [f"The application is already '{old}'."]})
    nxt = TRANSITIONS.get(old, ())
    if new_status not in nxt:
        hint = f"Allowed next: {', '.join(nxt)}." if nxt else f"'{old}' is a final status."
        raise ValidationError({"status": [f"Cannot move an application from '{old}' to '{new_status}'. {hint}"]})
    if actor.role == STUDENT and new_status not in STUDENT_MAY_SET:
        raise PermissionDenied("Only your counsellor can change this application's status. You can withdraw it.")

    if new_status == "Submitted":
        blockers = document_services.blocking_documents(app)
        if blockers:
            listed = ", ".join(f"{d.get('title') or d['document_type']} ({d['status']})" for d in blockers)
            raise ValidationError({"status": [f"Every document must be Verified before submission. Outstanding: {listed}."]})

    student = repository.get(app["student_id"], "student")
    hist = _history_entry(app, old, new_status, actor, remarks.strip())
    app["status"] = new_status
    app["history_ids"] = [*app.get("history_ids", []), hist["_id"]]
    app["updated_at"] = hist["timestamp"]
    if student is not None:
        app["counsellor_id"] = student.get("counsellor_id")
    if new_status == "Submitted":
        app["submitted_at"] = hist["timestamp"]
    repository.save(app)  # a stale rev raises ResourceConflict (409) before anything else is written
    repository.save(hist)

    if new_status == "Documents Pending" and student is not None:
        document_services.ensure_checklist(student, document_services.APPLICATION_DOCUMENTS, application=app,
                                           actor=actor, request=request)
    audit.record("application.status_changed", request=request, actor=actor, target_id=app["_id"],
                 details={"from": old, "to": new_status})
    events.application_status_changed(app, student, old=old, new=new_status, history_id=hist["_id"], actor=actor)
    return app


def delete(app: dict, *, actor, request=None) -> None:
    """Only a Planned application can be deleted (later ones are withdrawn, so their history stays)."""
    if app["status"] != "Planned":
        raise ValidationError({"detail": "Only a Planned application can be deleted. Withdraw it instead."})
    docs = repository.find({"type": "document", "application_id": app["_id"]})
    if any(d.get("status") != "Required" for d in docs):
        raise ValidationError({"detail": "Files have been uploaded for this application. Withdraw it instead."})
    for d in docs + repository.find({"type": "application_history", "application_id": app["_id"]}):
        repository.delete(d)
    repository.delete(app)
    _update_student_links(app["student_id"], app["_id"], add=False)
    audit.record("application.deleted", request=request, actor=actor, target_id=app["_id"],
                 details={"student_id": app["student_id"], "course": app.get("snapshot", {}).get("course_title")})


# ---------------------------------------------------------------------------
# Representation
# ---------------------------------------------------------------------------
def serialize_page(apps: list[dict]) -> list[dict]:
    """Rows with student and (current) counsellor names, resolved in two batched lookups."""
    student_ids = sorted({a["student_id"] for a in apps if a.get("student_id")})
    students = {}
    if student_ids:
        students = {s["_id"]: s for s in repository.find({"type": "student", "_id": {"$in": student_ids}},
                                                         fields=["_id", "personal", "counsellor_id"])}
    counsellors = lookups.names_by_id(s.get("counsellor_id") for s in students.values())
    today = repository.today()
    rows = []
    for a in apps:
        s = students.get(a.get("student_id"), {})
        data = repository.public(a)
        data["student_name"] = student_services.full_name(s) if s else ""
        data["counsellor_name"] = counsellors.get(s.get("counsellor_id")) if s.get("counsellor_id") else None
        data["deadline_info"] = deadline_info(a, today)
        data["is_terminal"] = a.get("status") in TERMINAL
        data.setdefault("notes", "")
        rows.append(data)
    return rows


def serialize(app: dict) -> dict:
    return serialize_page([app])[0]


def history(app: dict) -> list[dict]:
    entries = repository.find({"type": "application_history", "application_id": app["_id"]})
    position = {hid: i for i, hid in enumerate(app.get("history_ids", []))}  # breaks same-second ties
    entries.sort(key=lambda h: (h.get("timestamp") or "", position.get(h["_id"], len(position))))
    names = lookups.names_by_id(h.get("changed_by") for h in entries)
    return [{**repository.public(h), "changed_by_name": names.get(h.get("changed_by"), "")} for h in entries]


def detail(app: dict, user) -> dict:
    data = serialize(app)
    data["history"] = history(app)
    documents = repository.find({"type": "document", "student_id": app["student_id"]})
    documents = [d for d in documents if d.get("application_id") in (None, app["_id"])]
    documents.sort(key=lambda d: (d.get("application_id") is None, d.get("document_type", "")))
    data["documents"] = document_services.serialize_page(documents)
    data["allowed_transitions"] = allowed_transitions(app, user)
    data["submission_blockers"] = [
        {"document_type": d["document_type"], "title": d.get("title", ""), "status": d["status"]}
        for d in document_services.blocking_documents(app)
    ] if app["status"] == "Documents Pending" else []
    intake = repository.get(app.get("intake_id"), "intake")
    data["intake"] = serialize_intake(intake) if intake else None
    return data


def summary(apps: list[dict]) -> dict:
    """Pipeline counts plus the nearest open deadlines, for the workspace header and dashboards."""
    today = repository.today()
    by_status: dict[str, int] = {}
    upcoming = []
    for a in apps:
        by_status[a.get("status")] = by_status.get(a.get("status"), 0) + 1
        info = deadline_info(a, today)
        if info["state"] in ("overdue", "due_soon", "open") and info["days_left"] is not None:
            upcoming.append((info["days_left"], a))
    upcoming.sort(key=lambda pair: pair[0])
    nearest = [a for _, a in upcoming[:5]]
    if any("course_title" not in (a.get("snapshot") or {}) for a in nearest):
        nearest = sorted(repository.get_many(a["_id"] for a in nearest), key=lambda a: a.get("deadline") or "")
    return summary_from_counts(by_status, overdue=sum(1 for days, _ in upcoming if days < 0),
                               due_soon=sum(1 for days, _ in upcoming if 0 <= days <= DUE_SOON_DAYS), nearest=nearest)


def agency_summary() -> dict:
    """`summary` over every application, from reduce views instead of loading them all."""
    today = repository.today()
    overdue = repository.view_count("open_deadlines", endkey=(today - timedelta(days=1)).isoformat())
    due_soon = repository.view_count("open_deadlines", startkey=today.isoformat(),
                                     endkey=(today + timedelta(days=DUE_SOON_DAYS)).isoformat())
    nearest = [r.id for r in repository.view("open_deadlines", reduce=False, limit=5)]
    docs = sorted(repository.get_many(nearest), key=lambda a: (a.get("deadline") or "", nearest.index(a["_id"])))
    return summary_from_counts(repository.status_counts("application"), overdue=overdue, due_soon=due_soon, nearest=docs)


def summary_from_counts(counts: dict, *, overdue: int, due_soon: int, nearest: list[dict]) -> dict:
    """The pipeline summary from {status: count} plus deadline figures (also used with reduce views)."""
    by_status = {s: 0 for s in APPLICATION_STATUSES}
    for status, n in counts.items():
        by_status[status] = by_status.get(status, 0) + n
    return {
        "total": sum(by_status.values()),
        "open": sum(n for s, n in by_status.items() if s not in TERMINAL),
        "by_status": by_status,
        "overdue": overdue,
        "due_soon": due_soon,
        "upcoming_deadlines": serialize_page(nearest),
    }
