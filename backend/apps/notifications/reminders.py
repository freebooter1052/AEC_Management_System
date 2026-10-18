"""
Time-based reminders (SRS 4.10): application deadlines, documents a student still has to provide,
and counselling follow-ups that are due or overdue.

Windows (all dates are UTC calendar dates, like every deadline in the system):
  * application deadline - once each when 14, 7 and 1 day(s) remain, and once when it has passed
    (only for applications that can still be submitted: Planned, Shortlisted, Documents Pending);
  * documents - with each deadline window, the documents still Required/Rejected/Expired for that
    application; otherwise one weekly digest per student while any of their documents needs action;
  * follow-up - once when due today or tomorrow, once when overdue.
Nothing older than OVERDUE_GRACE_DAYS is reminded.

Every reminder's event key contains its window (and the deadline/due date it was computed from), so
running the sweep again in the same window writes nothing, while a moved deadline starts afresh.

How it runs:
  * `python manage.py send_reminders` sweeps everyone - schedule it (e.g. daily with Windows Task
    Scheduler or cron, see docs/SPRINT3_IMPLEMENTATION_REPORT.md). No scheduler is configured by default.
  * When a student or counsellor opens their dashboard or notifications, their own scope is swept, at
    most once every ON_ACCESS_INTERVAL seconds per user, so reminders also appear without a scheduler.
"""

import logging
from datetime import date, timedelta

from django.core.cache import cache

from apps.applications.services import PRE_SUBMISSION
from apps.core import repository
from apps.core.roles import COUNSELLOR, STUDENT
from apps.documents.services import ATTENTION
from apps.students import services as student_services

from .events import student_name
from .services import notify

logger = logging.getLogger("aec.notifications")

DEADLINE_WINDOWS = (1, 7, 14)  # days before the deadline
OVERDUE_GRACE_DAYS = 30
FOLLOW_UP_LOOKAHEAD_DAYS = 1
ON_ACCESS_INTERVAL = 15 * 60


def deadline_window(days_left: int) -> str | None:
    if days_left < -OVERDUE_GRACE_DAYS:
        return None
    if days_left < 0:
        return "overdue"
    for limit in DEADLINE_WINDOWS:
        if days_left <= limit:
            return f"{limit}d"
    return None


def follow_up_window(days_left: int) -> str | None:
    if days_left < -OVERDUE_GRACE_DAYS:
        return None
    if days_left < 0:
        return "overdue"
    return "due" if days_left <= FOLLOW_UP_LOOKAHEAD_DAYS else None


def _when(days_left: int) -> str:
    if days_left < 0:
        return f"passed {-days_left} day{'' if days_left == -1 else 's'} ago"
    if days_left == 0:
        return "is today"
    if days_left == 1:
        return "is tomorrow"
    return f"is in {days_left} days"


def _parse(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def sweep(today: date | None = None, *, student_ids=None) -> dict:
    """Create every reminder that is due (for all students, or only `student_ids`). Returns counts by category."""
    today = today or repository.today()
    scope = {} if student_ids is None else {"student_id": {"$in": list(student_ids)}}
    earliest = (today - timedelta(days=OVERDUE_GRACE_DAYS)).isoformat()
    counts = {"deadline": 0, "missing_document": 0, "follow_up": 0}

    apps = [a for a in repository.find(
        {"type": "application", **scope,
         "deadline": {"$gte": earliest, "$lte": (today + timedelta(days=max(DEADLINE_WINDOWS))).isoformat()}},
        fields=["_id", "student_id", "status", "deadline", "snapshot"]) if a.get("status") in PRE_SUBMISSION]
    sessions = [s for s in repository.find(
        {"type": "counselling_session", **scope,
         "follow_up.due_date": {"$gte": earliest, "$lte": (today + timedelta(days=FOLLOW_UP_LOOKAHEAD_DAYS)).isoformat()}},
        fields=["_id", "student_id", "counsellor_id", "follow_up"]) if (s.get("follow_up") or {}).get("status") == "Pending"]
    if student_ids is None:  # everyone: keyed view lookup of [document, status] instead of scanning all documents
        attention = [r.doc for r in repository.view("by_type_status", keys=[["document", s] for s in ATTENTION],
                                                     reduce=False, include_docs=True) if r.doc]
    else:
        attention = repository.find({"type": "document", **scope, "status": {"$in": list(ATTENTION)}},
                                    fields=["_id", "student_id", "application_id", "document_type", "title", "status"])

    ids = {a["student_id"] for a in apps} | {s["student_id"] for s in sessions} | {d["student_id"] for d in attention}
    students = {s["_id"]: s for s in repository.find(
        {"type": "student", "_id": {"$in": sorted(i for i in ids if i)}},
        fields=["_id", "user_id", "counsellor_id", "personal"])} if ids else {}
    counsellor_ids = {s.get("counsellor_id") for s in students.values()} | {s.get("counsellor_id") for s in sessions}
    counsellor_users = {c["_id"]: c.get("user_id") for c in repository.find(
        {"type": "counsellor", "_id": {"$in": sorted(i for i in counsellor_ids if i)}}, fields=["_id", "user_id"])} \
        if any(counsellor_ids) else {}
    docs_by_student: dict[str, list[dict]] = {}
    for d in attention:
        docs_by_student.setdefault(d["student_id"], []).append(d)

    def send(category, student, *, title_student, title_counsellor, message, key, related_id, related_type,
             link_student, link_counsellor, counsellor_id=None):
        coun_user = counsellor_users.get(counsellor_id or student.get("counsellor_id"))
        made = notify(recipient_user_id=student.get("user_id"), recipient_role=STUDENT, category=category,
                      title=title_student, message=message, event_key=key, related_id=related_id,
                      related_type=related_type, link=link_student)
        made_c = coun_user and title_counsellor and notify(
            recipient_user_id=coun_user, recipient_role=COUNSELLOR, category=category, title=title_counsellor,
            message=message, event_key=key, related_id=related_id, related_type=related_type, link=link_counsellor)
        counts[category] += bool(made) + bool(made_c)

    reminded_docs: set[str] = set()
    for app in apps:
        deadline = _parse(app.get("deadline"))
        student = students.get(app["student_id"])
        if deadline is None or student is None:
            continue
        days_left = (deadline - today).days
        window = deadline_window(days_left)
        if window is None:
            continue
        snap = app.get("snapshot") or {}
        uni = snap.get("university_name", "the university")
        name = student_name(student)
        link = f"/applications/{app['_id']}/"
        send("deadline", student,
             title_student=f"Deadline {_when(days_left)}: {uni}",
             title_counsellor=f"{name}: {uni} deadline {_when(days_left)}",
             message=f"{snap.get('course_title', 'Application')} at {uni} - deadline {deadline.isoformat()} ({app['status']}).",
             key=f"deadline:{app['_id']}:{deadline.isoformat()}:{window}", related_id=app["_id"],
             related_type="application", link_student=link, link_counsellor=link)
        outstanding = [d for d in docs_by_student.get(app["student_id"], []) if d.get("application_id") in (None, app["_id"])]
        if outstanding:
            listed = ", ".join(f"{d.get('title') or d['document_type']} ({d['status']})" for d in outstanding)
            n = len(outstanding)
            send("missing_document", student,
                 title_student=f"{n} document{'' if n == 1 else 's'} still needed for {uni}",
                 title_counsellor=f"{name}: {n} document{'' if n == 1 else 's'} outstanding for {uni}",
                 message=f"Before the {deadline.isoformat()} deadline: {listed}.",
                 key=f"docs_due:{app['_id']}:{deadline.isoformat()}:{window}", related_id=app["_id"],
                 related_type="application", link_student="/documents/",
                 link_counsellor=f"/documents/?student_id={app['student_id']}&status=all")
            reminded_docs.add(app["student_id"])

    year, week, _ = today.isocalendar()
    for student_id, docs in docs_by_student.items():
        student = students.get(student_id)
        if student is None or student_id in reminded_docs:
            continue
        n = len(docs)
        kinds = ", ".join(sorted({d.get("title") or d["document_type"] for d in docs}))
        counts["missing_document"] += bool(notify(
            recipient_user_id=student.get("user_id"), recipient_role=STUDENT, category="missing_document",
            title=f"{n} document{'' if n == 1 else 's'} {'needs' if n == 1 else 'need'} your attention",
            message=f"Please upload or replace: {kinds}.", event_key=f"docs_weekly:{student_id}:{year}-W{week:02d}",
            related_id=student_id, related_type="student", link="/documents/"))

    for s in sessions:
        follow = s["follow_up"]
        due = _parse(follow.get("due_date"))
        student = students.get(s["student_id"])
        if due is None or student is None:
            continue
        days_left = (due - today).days
        window = follow_up_window(days_left)
        if window is None:
            continue
        verb = "was due" if days_left < 0 else "is due"
        when = due.isoformat() if days_left < 0 else ("today" if days_left == 0 else "tomorrow")
        send("follow_up", student, counsellor_id=s.get("counsellor_id"),
             title_student=f"Follow-up {'overdue' if days_left < 0 else 'due ' + when}",
             title_counsellor=f"{student_name(student)}: follow-up {'overdue' if days_left < 0 else 'due ' + when}",
             message=f"{follow.get('action', 'Follow-up')} {verb} {when}.",
             key=f"follow_up:{s['_id']}:{due.isoformat()}:{window}", related_id=s["_id"],
             related_type="counselling_session", link_student="/counselling/?tab=follow-ups",
             link_counsellor="/counselling/?tab=follow-ups")
    return counts


def sweep_for_user(user) -> None:
    """On-access sweep of a student's or counsellor's own scope, throttled per user. Failures are logged only."""
    if user.role not in (STUDENT, COUNSELLOR):
        return
    if not cache.add(f"aec:reminders:{user.id}", 1, ON_ACCESS_INTERVAL):
        return
    try:
        ids = student_services.accessible_student_ids(user)
        if ids:
            sweep(student_ids=ids)
    except Exception:  # noqa: BLE001 - reminders must not break the page that triggered them
        logger.exception("Reminder sweep failed for user %s", user.id)
        cache.delete(f"aec:reminders:{user.id}")
