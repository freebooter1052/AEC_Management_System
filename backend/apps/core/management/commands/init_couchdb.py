from django.core.management.base import BaseCommand

from apps.core import couch_views
from apps.core.db import get_db

# Mango indexes backing the queries in the API. Each is (index name, fields).
INDEXES = [
    ("idx_type", ["type"]),
    ("idx_type_email", ["type", "email"]),
    ("idx_type_created", ["type", "created_at"]),
    ("idx_type_counsellor", ["type", "counsellor_id"]),
    ("idx_type_rank", ["type", "rank"]),
    ("idx_type_name", ["type", "name"]),
    ("idx_type_active", ["type", "is_active"]),
    # SRS workflow documents (applications, documents, sessions, recommendations, notifications)
    ("idx_type_student", ["type", "student_id"]),
    ("idx_type_application", ["type", "application_id"]),
    ("idx_type_university", ["type", "university_id"]),
    ("idx_type_status", ["type", "status"]),
    ("idx_type_recipient", ["type", "recipient_user_id"]),
    # Sprint 2: application deadlines and the counselling calendar
    ("idx_type_deadline", ["type", "deadline"]),
    ("idx_type_scheduled", ["type", "scheduled_at"]),
    # forgot-password codes
    ("idx_type_user_id", ["type", "user_id"]),
    # Sprint 3: a user's notifications newest first, and their unread count
    ("idx_type_recipient_created", ["type", "recipient_user_id", "created_at"]),
    ("idx_type_recipient_read", ["type", "recipient_user_id", "is_read"]),
    # follow-ups due in a date range (reminders, calendar)
    ("idx_type_follow_up_due", ["type", "follow_up.due_date"]),
    # course edits since a student's last recommendation run (staleness check)
    ("idx_type_updated", ["type", "updated_at"]),
    # one counsellor's / one student's records in date order (rosters, upcoming sessions) without
    # scanning everyone's: the equality field sits before the sort field
    ("idx_type_counsellor_created", ["type", "counsellor_id", "created_at"]),
    ("idx_type_counsellor_scheduled", ["type", "counsellor_id", "scheduled_at"]),
    ("idx_type_student_scheduled", ["type", "student_id", "scheduled_at"]),
]
DESIGN_DOC = "aec_indexes"


class Command(BaseCommand):
    help = ("Create the CouchDB database (if missing), the Mango indexes and the map/reduce views used by the API. "
            "Safe to re-run.")

    def handle(self, *args, **options):
        db = get_db()
        indexes = db.index()
        for name, fields in INDEXES:
            indexes[DESIGN_DOC, name] = [{f: "asc"} for f in fields]
            self.stdout.write(f"  index {name}: {fields}")
        wanted = couch_views.design_document()
        current = db.get(wanted["_id"])
        if current is None or current.get("views") != wanted["views"]:
            if current is not None:
                wanted["_rev"] = current["_rev"]  # changing a view makes CouchDB rebuild it on the next read
            db.save(wanted)
            self.stdout.write(f"  views {wanted['_id']}: {', '.join(couch_views.VIEWS)} (updated)")
        else:
            self.stdout.write(f"  views {wanted['_id']}: unchanged")
        info = db.info()
        self.stdout.write(self.style.SUCCESS(
            f"CouchDB database '{info.get('db_name')}' ready ({info.get('doc_count')} documents, {len(INDEXES)} indexes, "
            f"{len(couch_views.VIEWS)} views)."
        ))
