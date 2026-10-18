"""
`counselling_session` documents (SRS 4.7) and their follow-ups.

    {
      "_id": "counselling_session_...", "type": "counselling_session",
      "student_id": "student_...", "counsellor_id": "counsellor_...",
      "scheduled_at": "2026-10-20T09:30:00Z", "duration_minutes": 45, "mode": "Video call",
      "topic": "University shortlisting", "status": "Scheduled" | "Completed" | "Cancelled",
      "summary": "", "recommendations": ["..."], "action_items": ["..."],
      "follow_up": {"action": "...", "due_date": "2026-10-27", "status": "Pending" | "Done",
                    "completed_at": null} | null,
      "completed_at": null, "cancel_reason": "",
      "created_by": "user_...", "created_at": "...", "updated_at": "..."
    }

The follow-up is a sub-document of the session it came out of, so the history of a
student's counselling reads as one list; the follow-up endpoints work on it directly.
"""

from datetime import datetime, timedelta, timezone

from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core import audit, lookups, repository
from apps.core.roles import ADMIN, COUNSELLOR, STUDENT
from apps.notifications import events
from apps.students import services as student_services

MAX_SESSION_MINUTES = 240


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Access (SRS 4.1)
# ---------------------------------------------------------------------------
def can_view(user, session: dict) -> bool:
    """Admins; the session's counsellor; the student's current counsellor; the student."""
    if user.role == ADMIN:
        return True
    if user.role == COUNSELLOR and session.get("counsellor_id") == user.profile_id:
        return True
    student = repository.get(session.get("student_id"), "student")
    return student is not None and student_services.can_access(user, student)


def can_manage(user, session: dict) -> bool:
    """Scheduling, notes and cancellation: admins and the counsellor who runs the session."""
    return user.role == ADMIN or (user.role == COUNSELLOR and session.get("counsellor_id") == user.profile_id)


def scope_selector(user, selector: dict, *, student_id: str | None = None, counsellor_id: str | None = None) -> dict:
    """
    Sessions a user may list. A student's whole history is visible to their current counsellor
    (including sessions with earlier counsellors); without a student filter a counsellor sees their own.
    """
    if student_id:
        student_services.get_accessible(user, student_id)
        selector["student_id"] = student_id
    elif user.role == STUDENT:
        selector["student_id"] = user.profile_id
    elif user.role == COUNSELLOR:
        selector["counsellor_id"] = user.profile_id
    if counsellor_id and user.role == ADMIN:
        selector["counsellor_id"] = counsellor_id
    return selector


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------
def _check_slot(counsellor_id: str, start: datetime, minutes: int, ignore_id: str | None = None) -> None:
    """A counsellor cannot hold two scheduled sessions at the same time."""
    end = start + timedelta(minutes=minutes)
    window_from = repository.to_iso(start - timedelta(minutes=MAX_SESSION_MINUTES))
    for other in repository.find({"type": "counselling_session", "counsellor_id": counsellor_id, "status": "Scheduled",
                                  "scheduled_at": {"$gte": window_from, "$lt": repository.to_iso(end)}}):
        if other["_id"] == ignore_id:
            continue
        o_start = _parse(other["scheduled_at"])
        o_end = o_start + timedelta(minutes=other.get("duration_minutes") or 0)
        if o_start < end and start < o_end:
            raise ValidationError({"scheduled_at": [
                f"The counsellor already has a session from {o_start:%H:%M} to {o_end:%H:%M} UTC that day."]})


def schedule(*, student: dict, scheduled_at: datetime, duration_minutes: int, mode: str, topic: str,
             actor, request=None) -> dict:
    if actor.role == COUNSELLOR:
        counsellor_id = actor.profile_id
    else:
        counsellor_id = student.get("counsellor_id")
        if not counsellor_id:
            raise ValidationError({"student_id": ["Assign a counsellor to this student before scheduling a session."]})
    _check_slot(counsellor_id, scheduled_at, duration_minutes)
    now = repository.now_iso()
    doc = {
        "_id": repository.new_id("counselling_session"),
        "type": "counselling_session",
        "student_id": student["_id"],
        "counsellor_id": counsellor_id,
        "scheduled_at": repository.to_iso(scheduled_at),
        "duration_minutes": duration_minutes,
        "mode": mode,
        "topic": topic.strip(),
        "status": "Scheduled",
        "summary": "",
        "recommendations": [],
        "action_items": [],
        "follow_up": None,
        "completed_at": None,
        "cancel_reason": "",
        "created_by": actor.id,
        "created_at": now,
        "updated_at": now,
    }
    repository.save(doc)
    audit.record("session.scheduled", request=request, actor=actor, target_id=doc["_id"],
                 details={"student_id": student["_id"], "scheduled_at": doc["scheduled_at"]})
    return doc


def _require_scheduled(session: dict, action: str) -> None:
    if session["status"] != "Scheduled":
        raise ValidationError({"detail": f"Only a scheduled session can be {action}; this one is {session['status']}."})


def reschedule(session: dict, changes: dict, *, actor, request=None) -> dict:
    _require_scheduled(session, "edited")
    if "scheduled_at" in changes or "duration_minutes" in changes:
        start = changes.get("scheduled_at") or _parse(session["scheduled_at"])
        minutes = changes.get("duration_minutes") or session.get("duration_minutes") or 45
        _check_slot(session["counsellor_id"], start, minutes, ignore_id=session["_id"])
    for key, value in changes.items():
        if key == "scheduled_at":
            value = repository.to_iso(value)
        session[key] = value.strip() if isinstance(value, str) else value
    session["updated_at"] = repository.now_iso()
    repository.save(session)
    audit.record("session.updated", request=request, actor=actor, target_id=session["_id"],
                 details={"fields": sorted(changes)})
    return session


def _clean_list(items) -> list[str]:
    return [i.strip() for i in items or [] if i and i.strip()]


def complete(session: dict, data: dict, *, actor, request=None) -> dict:
    """Record what was discussed: summary, recommendations, agreed actions and an optional follow-up."""
    _require_scheduled(session, "completed")
    started = _parse(session["scheduled_at"])
    if started > _now():
        raise ValidationError({"detail": f"This session starts at {session['scheduled_at']}; record notes once it has taken place."})
    follow = data.get("follow_up")
    if follow:
        if follow["due_date"] < started.date():
            raise ValidationError({"follow_up": {"due_date": ["The follow-up cannot be due before the session."]}})
        follow = {"action": follow["action"].strip(), "due_date": follow["due_date"].isoformat(),
                  "status": "Pending", "completed_at": None}
    now = repository.now_iso()
    session.update({
        "status": "Completed",
        "summary": data["summary"].strip(),
        "recommendations": _clean_list(data.get("recommendations")),
        "action_items": _clean_list(data.get("action_items")),
        "follow_up": follow or None,
        "completed_at": now,
        "updated_at": now,
    })
    repository.save(session)
    audit.record("session.completed", request=request, actor=actor, target_id=session["_id"],
                 details={"follow_up": bool(follow)})
    if follow:
        events.follow_up_created(session)
    return session


def cancel(session: dict, reason: str, *, actor, request=None) -> dict:
    _require_scheduled(session, "cancelled")
    session.update({"status": "Cancelled", "cancel_reason": reason.strip(), "updated_at": repository.now_iso()})
    repository.save(session)
    audit.record("session.cancelled", request=request, actor=actor, target_id=session["_id"])
    return session


def update_follow_up(session: dict, changes: dict, *, actor, request=None) -> dict:
    """Counsellors edit or close a follow-up; a student may mark their own follow-up done."""
    follow = session.get("follow_up")
    if not follow:
        raise ValidationError({"detail": "This session has no follow-up."})
    if actor.role == STUDENT and set(changes) - {"status"}:
        raise PermissionDenied("Only your counsellor can change a follow-up's action or due date.")
    if "due_date" in changes:
        if changes["due_date"] < _parse(session["scheduled_at"]).date():
            raise ValidationError({"due_date": ["The follow-up cannot be due before the session."]})
        follow["due_date"] = changes["due_date"].isoformat()
    if "action" in changes:
        follow["action"] = changes["action"].strip()
    if "status" in changes and changes["status"] != follow.get("status"):
        follow["status"] = changes["status"]
        follow["completed_at"] = repository.now_iso() if changes["status"] == "Done" else None
    session["follow_up"] = follow
    session["updated_at"] = repository.now_iso()
    repository.save(session)
    audit.record("session.follow_up_updated", request=request, actor=actor, target_id=session["_id"],
                 details={"status": follow.get("status")})
    return session


def session_sort(selector: dict, direction: str = "asc") -> list[dict]:
    """Sort by time through [type, counsellor_id|student_id, scheduled_at] when the list is one person's,
    so CouchDB reads only that person's sessions instead of everyone's in date order."""
    for field in ("counsellor_id", "student_id"):
        if isinstance(selector.get(field), str):
            return [{"type": direction}, {field: direction}, {"scheduled_at": direction}]
    return [{"type": direction}, {"scheduled_at": direction}]


# ---------------------------------------------------------------------------
# Representation
# ---------------------------------------------------------------------------
def follow_up_state(follow: dict | None, today=None) -> str | None:
    if not follow:
        return None
    if follow.get("status") == "Done":
        return "done"
    today = today or repository.today()
    due = follow.get("due_date") or ""
    return "overdue" if due < today.isoformat() else ("due_today" if due == today.isoformat() else "pending")


def serialize_page(sessions: list[dict], user=None) -> list[dict]:
    names = lookups.names_by_id([s.get("student_id") for s in sessions] + [s.get("counsellor_id") for s in sessions])
    today = repository.today()
    now = repository.now_iso()
    rows = []
    for s in sessions:
        data = repository.public(s)
        data.setdefault("action_items", [])
        data.setdefault("cancel_reason", "")
        data["student_name"] = names.get(s.get("student_id"), "")
        data["counsellor_name"] = names.get(s.get("counsellor_id"), "")
        data["ends_at"] = repository.to_iso(_parse(s["scheduled_at"]) + timedelta(minutes=s.get("duration_minutes") or 0))
        data["needs_notes"] = s.get("status") == "Scheduled" and s["scheduled_at"] <= now
        data["follow_up_state"] = follow_up_state(s.get("follow_up"), today)
        if user is not None:
            data["can_manage"] = can_manage(user, s)
        rows.append(data)
    return rows


def serialize(session: dict, user=None) -> dict:
    return serialize_page([session], user)[0]


def follow_up_rows(sessions: list[dict]) -> list[dict]:
    """Flatten sessions with a follow-up into rows, soonest due first."""
    rows = []
    for s in serialize_page([s for s in sessions if s.get("follow_up")]):
        f = s["follow_up"]
        rows.append({"session_id": s["id"], "student_id": s["student_id"], "student_name": s["student_name"],
                     "counsellor_name": s["counsellor_name"], "topic": s.get("topic", ""),
                     "session_date": s["scheduled_at"], "action": f.get("action", ""), "due_date": f.get("due_date"),
                     "status": f.get("status"), "state": s["follow_up_state"], "rev": s["rev"]})
    rows.sort(key=lambda r: (r["status"] == "Done", r["due_date"] or ""))
    return rows
