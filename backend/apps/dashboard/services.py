"""
Role-specific dashboards (SRS 4.9). Every figure is computed from stored documents on each request;
nothing is cached or estimated.

Scope of each figure:
  * Student - only their own records.
  * Counsellor - students whose `counsellor_id` is theirs (the source of truth); sessions they run.
  * Admin - everyone. `counsellor_id` narrows every figure to that counsellor's current students;
    `country` and `intake_id` narrow the application figures (pipeline, deadlines, reports) only,
    because documents and sessions belong to a student rather than to one application.
Totals count every stored record of a type, including inactive counsellors and courses; the
active subsets are reported next to them.

Cost: student and counsellor figures read only that caseload (multi-key view lookups, see
repository). Agency-wide figures come from the `aec_stats` reduce views (apps/core/couch_views.py), so
the admin dashboard does not load every application or document; a country/intake filter reads one
compact view row per matching application. The workload table lists the WORKLOAD_ROWS busiest
counsellors (all of them are on the Counsellors page).
"""

from collections import Counter
from datetime import datetime, timedelta, timezone

from apps.applications import services as application_services
from apps.core import repository
from apps.core.roles import ADMIN, COUNSELLOR, STUDENT
from apps.counselling import services as counselling_services
from apps.counsellors import services as counsellor_services
from apps.documents import services as document_services
from apps.notifications import services as notification_services
from apps.recommendations import services as recommendation_services
from apps.students import services as student_services

APP_FIELDS = ["_id", "student_id", "status", "deadline", "intake_id", "university_id", "snapshot", "created_at"]
UPCOMING_SESSIONS = 5
WORKLOAD_ROWS = 10
LIST_SIZE = 6
ACTIVITY_DAYS = 30
OFFER_STATUSES = ("Offer Received", "Completed")


def parse_filters(params, user) -> dict:
    """?country=&intake_id= for staff, plus ?counsellor_id= for admins. Unknown values just match nothing."""
    if user.role == STUDENT:
        return {}
    keys = ("country", "intake_id", "counsellor_id") if user.role == ADMIN else ("country", "intake_id")
    return {k: params.get(k, "").strip()[:64] for k in keys if params.get(k, "").strip()}


def _application_selector(student_ids, filters: dict) -> dict:
    selector = {"type": "application"}
    if student_ids is not None:
        selector["student_id"] = {"$in": list(student_ids)}
    if filters.get("intake_id"):
        selector["intake_id"] = filters["intake_id"]
    if filters.get("country"):
        selector["snapshot.country"] = filters["country"]
    return selector


def _scope(student_ids) -> dict:
    return {} if student_ids is None else {"student_id": {"$in": list(student_ids)}}


def _workflow(user, student_ids, *, session_selector: dict, filters: dict) -> dict:
    """Applications, documents, sessions and follow-ups for a set of students (None = everyone)."""
    apps = repository.find(_application_selector(student_ids, filters), fields=APP_FIELDS)
    docs = repository.find({"type": "document", **_scope(student_ids)}, fields=["status"])
    return {
        "applications": application_services.summary(apps),
        "documents": document_services.summary(docs),
        **_sessions(user, session_selector),
    }, apps


def _sessions(user, session_selector: dict) -> dict:
    """Upcoming sessions and pending follow-ups of one counsellor or student (index-backed, bounded)."""
    selector = {**session_selector, "status": "Scheduled", "scheduled_at": {"$gte": repository.now_iso()}}
    upcoming = repository.find(selector, sort=counselling_services.session_sort(selector), limit=UPCOMING_SESSIONS)
    follow_ups = counselling_services.follow_up_rows(
        repository.find({**session_selector, "follow_up.status": "Pending"}, limit=500))
    return {"upcoming_sessions": counselling_services.serialize_page(upcoming, user),
            "follow_ups": {"pending": len(follow_ups), "overdue": sum(1 for f in follow_ups if f["state"] == "overdue"),
                           "next": follow_ups[:5]}}


def _notifications(user) -> dict:
    return {"unread": notification_services.unread_summary(user)["unread"],
            "latest": notification_services.latest(user, 5)}


# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------
def student_dashboard(user) -> dict:
    doc = repository.get(user.profile_id, "student") or {}
    sid = doc.get("_id")
    counsellor = repository.get(doc["counsellor_id"], "counsellor") if doc.get("counsellor_id") else None
    workflow, apps = _workflow(user, [sid] if sid else [], filters={},
                               session_selector={"type": "counselling_session", "student_id": sid})

    # Open applications first (nearest deadline first), then decided/closed ones.
    def app_order(a):
        info = application_services.deadline_info(a)
        return (a.get("status") in application_services.TERMINAL, info["days_left"] if info["days_left"] is not None else 10**6)
    app_rows = application_services.serialize_page(sorted(apps, key=app_order)[:LIST_SIZE]) if apps else []

    attention = repository.find({"type": "document", "student_id": sid, "status": {"$in": list(document_services.ATTENTION)}}) if sid else []
    attention.sort(key=lambda d: (d.get("status") == "Required", d.get("document_type", "")))  # rejected/expired first

    recs, rec_total, run, fresh = [], 0, None, {"state": "never", "reasons": []}
    if sid:
        all_recs = [r for r in recommendation_services.for_student(sid) if r.get("status") != "Rejected"]
        recs = recommendation_services.serialize_page(all_recs[:3])
        run, fresh = recommendation_services.run_summary(doc)
        rec_total = len(all_recs)
    return {
        "role": STUDENT,
        "student_id": sid,
        "full_name": student_services.full_name(doc) if doc else user.full_name,
        "profile_completion": doc.get("profile_completion", {}),
        "onboarding_status": doc.get("onboarding_status"),
        "counsellor": counsellor_services.contact_card(counsellor),
        "preferences": doc.get("preferences", {}),
        **workflow,
        "application_list": app_rows,
        "documents_attention": document_services.serialize_page(attention[:LIST_SIZE]),
        "recommendations": {"top": recs, "total": rec_total, "run": run, "freshness": fresh},
        "notifications": _notifications(user),
    }


# ---------------------------------------------------------------------------
# Counsellor
# ---------------------------------------------------------------------------
def counsellor_dashboard(user, filters: dict) -> dict:
    doc = repository.get(user.profile_id, "counsellor") or {}
    students = repository.find(
        {"type": "student", "counsellor_id": user.profile_id},
        fields=["_id", "personal", "preferences", "profile_completion", "onboarding_status", "counsellor_id",
                "created_at", "updated_at"])
    ids = [s["_id"] for s in students]
    by_status = Counter(s.get("onboarding_status", "registered") for s in students)
    workflow, apps = _workflow(user, ids, filters=filters,
                               session_selector={"type": "counselling_session", "counsellor_id": user.profile_id})

    docs = repository.find({"type": "document", "student_id": {"$in": ids}},
                           fields=["_id", "student_id", "status", "uploaded_at"]) if ids else []
    outstanding = Counter(d["student_id"] for d in docs if d.get("status") in document_services.ATTENTION)
    open_apps = Counter(a["student_id"] for a in apps if a.get("status") not in application_services.TERMINAL)
    queue_ids = [d["_id"] for d in sorted((d for d in docs if d.get("status") in document_services.AWAITING_REVIEW),
                                          key=lambda d: d.get("uploaded_at") or "")[:5]]
    queue = repository.find({"type": "document", "_id": {"$in": queue_ids}}) if queue_ids else []
    queue.sort(key=lambda d: d.get("uploaded_at") or "")

    # Who needs attention: most outstanding documents first, then the least complete profile.
    ranked = sorted(students, key=lambda s: (-outstanding[s["_id"]], s.get("profile_completion", {}).get("overall", 0)))
    needs_attention = student_services.summary_page(ranked[:LIST_SIZE])
    for row in needs_attention:
        row["documents_outstanding"] = outstanding[row["id"]]
        row["open_applications"] = open_apps[row["id"]]

    with_runs = {r["student_id"] for r in repository.find(
        {"type": "recommendation_run", "student_id": {"$in": ids}}, fields=["student_id"])} if ids else set()
    return {
        "role": COUNSELLOR,
        "counsellor_id": doc.get("_id"),
        "name": doc.get("name", user.full_name),
        "filters": filters,
        "workload": counsellor_services.workload(doc, len(students)) if doc else None,
        "students_by_status": dict(by_status),
        "needs_attention": needs_attention,
        "review_queue": document_services.serialize_page(queue),
        "students_without_recommendations": len(set(ids) - with_runs),
        **workflow,
        "notifications": _notifications(user),
    }


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
_status_counts = repository.status_counts


def _filtered_applications(filters: dict, scope) -> list[dict]:
    """Applications behind the admin filters, as compact rows (status, deadline, snapshot names, ...)."""
    if scope is not None:
        return repository.find(_application_selector(scope, filters), fields=APP_FIELDS)
    dim, value = ("country", filters["country"]) if filters.get("country") else ("intake", filters["intake_id"])
    apps = []
    for r in repository.view("applications_by_dim", key=[dim, value]):
        status, deadline, country, university, intake_name, intake_id, student_id = r.value
        if filters.get("intake_id") and intake_id != filters["intake_id"]:
            continue
        apps.append({"_id": r.id, "status": status, "deadline": deadline, "intake_id": intake_id, "student_id": student_id,
                     "snapshot": {"country": country, "university_name": university, "intake_name": intake_name}})
    return apps


def _agency_sessions(user, today) -> dict:
    upcoming = repository.find({"type": "counselling_session", "status": "Scheduled",
                                "scheduled_at": {"$gte": repository.now_iso()}},
                               sort=[{"type": "asc"}, {"scheduled_at": "asc"}], limit=UPCOMING_SESSIONS)
    pending = repository.view_count("follow_ups_by_due", startkey=["Pending"], endkey=["Pending", {}])
    overdue = repository.view_count("follow_ups_by_due", startkey=["Pending"], endkey=["Pending", today.isoformat()],
                                    inclusive_end=False)
    soonest = [r.id for r in repository.view("follow_ups_by_due", reduce=False, startkey=["Pending"],
                                             endkey=["Pending", {}], limit=5)]
    return {"upcoming_sessions": counselling_services.serialize_page(upcoming, user),
            "follow_ups": {"pending": pending, "overdue": overdue,
                           "next": counselling_services.follow_up_rows(repository.get_many(soonest))}}


def _report_counts(apps) -> dict:
    """{(dimension, value): [applications, offers]}: from application rows, or the reduce view when apps is None."""
    if apps is None:
        return {tuple(r.key): r.value for r in repository.view("application_dims", group_level=2)}
    counts: dict = {}
    for a in apps:
        snap = a.get("snapshot") or {}
        offer = 1 if a.get("status") in OFFER_STATUSES else 0
        for dim, value in (("country", snap.get("country")), ("university", snap.get("university_name")),
                           ("intake", snap.get("intake_name"))):
            row = counts.setdefault((dim, value or ""), [0, 0])
            row[0] += 1
            row[1] += offer
    return counts


def _top(counts: dict, dim: str, n: int = 10) -> list[dict]:
    rows = [(value, total, offers) for (d, value), (total, offers) in counts.items() if d == dim]
    return [{"name": value or "Unknown", "applications": total, "offers": offers}
            for value, total, offers in sorted(rows, key=lambda r: (-r[1], r[0] or ""))[:n]]


def _counsellor_activity(counsellor_ids: list[str]) -> dict:
    """Open applications, documents to review, recent sessions and follow-ups for a few counsellors (SRS 4.3)."""
    stats = {cid: Counter() for cid in counsellor_ids}
    if not counsellor_ids:
        return stats
    roster = {r.id: r.key for r in repository.view("students_by_counsellor", keys=counsellor_ids, reduce=False)}
    for r in (repository.view("student_workload", keys=list(roster), group=True) if roster else []):
        c = stats[roster[r.key]]
        c["open_applications"] += r.value[0]
        c["documents_to_review"] += r.value[1]
    since = repository.to_iso(datetime.now(timezone.utc) - timedelta(days=ACTIVITY_DAYS))
    today = repository.today().isoformat()
    for r in repository.view("sessions_by_counsellor", keys=counsellor_ids):
        status, at, follow_status, due = r.value
        c = stats[r.key]
        c["sessions_completed_30d"] += status == "Completed" and bool(at) and at >= since
        if follow_status == "Pending":
            c["follow_ups_pending"] += 1
            c["follow_ups_overdue"] += bool(due) and due < today
    return stats


def admin_dashboard(user, filters: dict) -> dict:
    today = repository.today()
    type_counts = {r.key[0]: r.value for r in repository.view("by_type", group_level=1)}
    counsellors = [{"_id": r.id, "name": r.value[0], "is_active": r.value[1], "max_students": r.value[2]}
                   for r in repository.view("counsellors")]
    assigned = counsellor_services.assigned_counts()

    scope = None
    if filters.get("counsellor_id"):
        scope = [r.id for r in repository.view("students_by_counsellor", key=filters["counsellor_id"], reduce=False)]
    if scope is None and not (filters.get("country") or filters.get("intake_id")):
        apps = None
        applications = application_services.agency_summary()
    else:
        apps = _filtered_applications(filters, scope)
        applications = application_services.summary(apps)
    if scope is None:
        documents = document_services.summary_from_counts(_status_counts("document"))
        sessions = _agency_sessions(user, today)
        recs = _status_counts("recommendation")
    else:
        documents = document_services.summary(repository.find({"type": "document", **_scope(scope)}, fields=["status"]))
        sessions = _sessions(user, {"type": "counselling_session", "counsellor_id": filters["counsellor_id"]})
        recs = Counter(r.get("status") for r in repository.find({"type": "recommendation", **_scope(scope)}, fields=["status"]))
    counts = _report_counts(apps)
    by_status = applications["by_status"]
    decided = sum(by_status.get(s, 0) for s in (*OFFER_STATUSES, "Rejected"))
    offered = sum(by_status.get(s, 0) for s in OFFER_STATUSES)

    workload = sorted(({"id": c["_id"], "name": c.get("name", ""), "is_active": c.get("is_active", True),
                        **counsellor_services.workload(c, assigned.get(c["_id"], 0))}
                       for c in counsellors if not filters.get("counsellor_id") or c["_id"] == filters["counsellor_id"]),
                      key=lambda c: (-c["utilisation_pct"], c["name"]))[:WORKLOAD_ROWS]
    activity = _counsellor_activity([w["id"] for w in workload])
    for w in workload:
        a = activity[w["id"]]
        w.update({k: a.get(k, 0) for k in ("open_applications", "documents_to_review", "sessions_completed_30d",
                                           "follow_ups_pending", "follow_ups_overdue")})

    intakes = sorted(repository.find({"type": "intake"}, fields=["_id", "name", "start_date"]),
                     key=lambda i: i.get("start_date") or "")
    courses = type_counts.get("course", 0)
    return {
        "role": ADMIN,
        "filters": filters,
        "filter_options": {
            "counsellors": sorted(({"id": c["_id"], "name": c.get("name", "")} for c in counsellors), key=lambda c: c["name"]),
            "intakes": [{"id": i["_id"], "name": i.get("name", "")} for i in intakes],
        },
        "totals": {
            "students": type_counts.get("student", 0),
            "unassigned_students": repository.view_count("students_by_counsellor", key=None),
            "counsellors": len(counsellors),
            "active_counsellors": sum(1 for c in counsellors if c.get("is_active", True)),
            "universities": type_counts.get("university", 0),
            "courses": courses,
            "active_courses": courses - repository.count({"type": "course", "is_active": False}),
            "applications": applications["total"],
            "users": type_counts.get("user", 0),
        },
        "counsellor_workload": workload,
        "counsellor_workload_total": len(counsellors) if not filters.get("counsellor_id") else len(workload),
        "reports": {
            "by_country": _top(counts, "country"),
            "by_university": _top(counts, "university"),
            "by_intake": _top(counts, "intake"),
            "outcomes": {"decided": decided, "offers": offered,
                         "offer_rate_pct": round(100 * offered / decided) if decided else None},
            "recommendations": {"total": sum(recs.values()), "by_status": dict(recs)},
        },
        "applications": applications,
        "documents": documents,
        **sessions,
        "notifications": _notifications(user),
    }
