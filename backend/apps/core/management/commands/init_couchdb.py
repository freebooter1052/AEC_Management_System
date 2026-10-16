from django.core.management.base import BaseCommand

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
]
DESIGN_DOC = "aec_indexes"


class Command(BaseCommand):
    help = "Create the CouchDB database (if missing) and the Mango indexes used by the API. Safe to re-run."

    def handle(self, *args, **options):
        db = get_db()
        indexes = db.index()
        for name, fields in INDEXES:
            indexes[DESIGN_DOC, name] = [{f: "asc"} for f in fields]
            self.stdout.write(f"  index {name}: {fields}")
        info = db.info()
        self.stdout.write(self.style.SUCCESS(
            f"CouchDB database '{info.get('db_name')}' ready ({info.get('doc_count')} documents, {len(INDEXES)} indexes)."
        ))
