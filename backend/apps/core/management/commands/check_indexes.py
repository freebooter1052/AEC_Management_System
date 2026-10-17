from django.core.management.base import BaseCommand, CommandError

from apps.core import repository
from apps.core.couch_views import PRE_SUBMISSION as PRE
from apps.core.db import get_db
from apps.core.vocab import APPLICATION_STATUSES, DOCUMENT_STATUSES

from .init_couchdb import DESIGN_DOC

# Representative query patterns of the API (selector, sort, the index we expect the planner to use).
NOW, DAY, ID = "2026-10-16T00:00:00Z", "2026-10-16", "x"
PATTERNS = [
    ("counsellor's students", {"type": "student", "counsellor_id": ID}, None, "idx_type_counsellor"),
    # `student_id: {$in}` is answered by the by_student view (repository.find); _explain shows Mango's fallback,
    # used only beyond SCOPED_MAX students, which cannot use an index range for $in.
    ("a caseload's applications (fallback)", {"type": "application", "student_id": {"$in": [ID]}}, None, "idx_type"),
    ("applications by deadline", {"type": "application", "deadline": {"$gt": None}},
     [{"type": "asc"}, {"deadline": "asc"}], "idx_type_deadline"),
    ("deadline reminder window", {"type": "application", "deadline": {"$gte": DAY, "$lte": DAY}}, None, "idx_type_deadline"),
    ("course catalogue (recommendations)", {"type": "course"}, None, "idx_type"),
    ("courses edited since a run", {"type": "course", "updated_at": {"$gte": NOW}}, None, "idx_type_updated"),
    ("a student's recommendations", {"type": "recommendation", "student_id": ID}, None, "idx_type_student"),
    ("a caseload's runs (fallback)", {"type": "recommendation_run", "student_id": {"$in": [ID]}}, None, "idx_type"),
    ("notification inbox, newest first", {"type": "notification", "recipient_user_id": ID, "created_at": {"$gt": None}},
     [{"type": "desc"}, {"recipient_user_id": "desc"}, {"created_at": "desc"}], "idx_type_recipient_created"),
    ("unread count", {"type": "notification", "recipient_user_id": ID, "is_read": False}, None, "idx_type_recipient_read"),
    ("follow-ups due (reminders, calendar)", {"type": "counselling_session", "follow_up.due_date": {"$gte": DAY, "$lte": DAY}},
     None, "idx_type_follow_up_due"),
    ("document review queue (admin list)", {"type": "document", "created_at": {"$gt": None}, "status": {"$in": ["Uploaded", "Under Review"]}},
     [{"type": "desc"}, {"created_at": "desc"}], "idx_type_created"),
    ("a caseload's documents (fallback)", {"type": "document", "student_id": {"$in": [ID]}}, None, "idx_type"),
    ("one counsellor's roster by date", {"type": "student", "counsellor_id": ID, "created_at": {"$gt": None}},
     [{"type": "desc"}, {"counsellor_id": "desc"}, {"created_at": "desc"}], "idx_type_counsellor_created"),
    ("one counsellor's upcoming sessions", {"type": "counselling_session", "counsellor_id": ID, "scheduled_at": {"$gte": NOW}},
     [{"type": "asc"}, {"counsellor_id": "asc"}, {"scheduled_at": "asc"}], "idx_type_counsellor_scheduled"),
    ("upcoming sessions", {"type": "counselling_session", "scheduled_at": {"$gte": NOW}},
     [{"type": "asc"}, {"scheduled_at": "asc"}], "idx_type_scheduled"),
    ("newest applications", {"type": "application", "created_at": {"$gt": None}},
     [{"type": "desc"}, {"created_at": "desc"}], "idx_type_created"),
]


class Command(BaseCommand):
    help = ("Ask CouchDB (_explain) which index each main query pattern uses. Fails if any falls back to a "
            "full scan (_all_docs); reports, without failing, when the planner picks a different valid index.")

    def handle(self, *args, **options):
        db = get_db()
        scans, other = [], []
        for name, selector, sort, expected in PATTERNS:
            query = {"selector": selector, "limit": 25, **({"sort": sort} if sort else {})}
            index = db.explain(query).get("index") or {}
            used = index.get("name") or index.get("type") or "?"
            full_scan = index.get("type") == "special"
            mark = "FULL SCAN" if full_scan else ("ok" if used == expected else f"uses {used}")
            self.stdout.write(f"  {name:<40} {used:<28} {mark}")
            if full_scan:
                scans.append(name)
            elif used != expected or index.get("ddoc") != f"_design/{DESIGN_DOC}":
                other.append(name)
        if scans:
            raise CommandError(f"{len(scans)} query pattern(s) scan the whole database: {', '.join(scans)}. "
                               "Run `manage.py init_couchdb`.")
        msg = f"All {len(PATTERNS)} query patterns use a Mango index"
        self.stdout.write(self.style.SUCCESS(msg + (f" ({len(other)} chose a different index than listed)." if other else ".")))
        self.check_views()

    def check_views(self):
        """The views' JavaScript maps must agree with Mango (and so with their Python twins used in the tests)."""
        self.stdout.write("Comparing view answers with direct Mango counts (this reads every document once):")
        mango_count = lambda sel: len(repository.find(sel, fields=["_id"]))  # noqa: E731 - bypasses the fast paths
        today = repository.today().isoformat()
        checks = []
        for t in ("student", "counsellor", "application", "document", "counselling_session", "notification", "recommendation"):
            checks.append((f"by_type {t}", repository.view_count("by_type", startkey=[t], endkey=[t, {}]), mango_count({"type": t})))
            checks.append((f"by_type {t} with created_at", repository.view_count("by_type", key=[t, True]),
                           mango_count({"type": t, "created_at": {"$gt": None}})))
        for t, statuses in (("application", APPLICATION_STATUSES), ("document", DOCUMENT_STATUSES)):
            for st in statuses:
                checks.append((f"by_type_status {t}/{st}", repository.view_count("by_type_status", key=[t, st]),
                               mango_count({"type": t, "status": st})))
        checks.append(("students_by_counsellor unassigned", repository.view_count("students_by_counsellor", key=None),
                       mango_count({"type": "student", "counsellor_id": None})))
        checks.append(("open_deadlines overdue", repository.view_count("open_deadlines", endkey=today, inclusive_end=False),
                       mango_count({"type": "application", "deadline": {"$lt": today}, "status": {"$in": PRE}})))
        checks.append(("follow_ups_by_due pending", repository.view_count("follow_ups_by_due", startkey=["Pending"], endkey=["Pending", {}]),
                       mango_count({"type": "counselling_session", "follow_up.status": "Pending", "follow_up.due_date": {"$gt": None}})))
        dims = {tuple(r.key): r.value for r in repository.view("application_dims", group_level=1)}
        apps_total = mango_count({"type": "application"})
        offers = mango_count({"type": "application", "status": {"$in": ["Offer Received", "Completed"]}})
        for dim in ("country", "university", "intake"):
            checks.append((f"application_dims {dim} [apps, offers]", dims.get((dim,), [0, 0]), [apps_total, offers]))
        work = (repository.view("student_workload") or [type("R", (), {"value": [0, 0]})()])[0].value
        checks.append(("student_workload [open apps, docs to review]", work,
                       [mango_count({"type": "application", "status": {"$nin": ["Rejected", "Withdrawn", "Completed"]},
                                     "student_id": {"$gt": None}}),
                        mango_count({"type": "document", "status": {"$in": ["Uploaded", "Under Review"]}, "student_id": {"$gt": None}})]))
        checks.append(("counsellors rows", len(repository.view("counsellors")), mango_count({"type": "counsellor"})))
        bad = [c for c in checks if c[1] != c[2]]
        for name, from_view, from_mango in checks:
            if from_view != from_mango:
                self.stdout.write(f"  MISMATCH {name}: view {from_view}, Mango {from_mango}")
        if bad:
            raise CommandError(f"{len(bad)} view count(s) disagree with Mango; check apps/core/couch_views.py.")
        self.stdout.write(self.style.SUCCESS(f"All {len(checks)} view counts match Mango."))
