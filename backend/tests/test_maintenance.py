"""Backup and demo-data purge (apps/core/maintenance.py, manage.py purge_demo_data)."""

import io
import json
import tempfile
from pathlib import Path

from django.core.management import CommandError, call_command

from apps.accounts import users
from apps.core import maintenance

from .base import APITestCase


class PurgeDemoDataTests(APITestCase):
    def setUp(self):
        super().setUp()
        admin = self.as_user("admin@aec.test")
        # Real data, entered through the API.
        self.register()
        self.student_id = users.get_by_email("stu@aec.test")["profile_id"]
        self.real = self.create_counsellor(admin, email="real@aec.test", name="Real Counsellor")
        # seed_demo-style counsellor (app-shaped but @aec.demo); the real student is assigned to it.
        self.demo = self.create_counsellor(admin, email="demo@aec.demo", name="Demo Counsellor")
        admin.post(f"/api/students/{self.student_id}/assign-counsellor/", {"counsellor_id": self.demo["id"]}, format="json")
        # Legacy seed documents (no token_version, other field names).
        for doc in (
            {"_id": "user_legacy", "type": "user", "email": "x@example.org", "role": "student",
             "username": "x", "linked_profile_id": "student_001", "password_hash": "pbkdf2_sha256$1$a$b"},
            {"_id": "student_001", "type": "student", "user_id": "user_legacy",
             "personal_details": {"name": "Legacy Student"}, "counsellor_id": "counsellor_001"},
            {"_id": "counsellor_001", "type": "counsellor", "name": "Legacy Counsellor", "active_status": True},
            {"_id": "application_001", "type": "application", "student_id": "student_001"},
            {"_id": "counselling_session_001", "type": "counselling_session", "student_id": "student_001"},
            {"_id": "course_001", "doc_type": "course", "name": "Stray"},
            {"_id": "university_001", "type": "university", "name": "Kept University", "country": "UK", "rank": 1},
            {"_id": "course_0001", "type": "course", "title": "Kept Course", "university_id": "university_001"},
        ):
            self.db.save(doc)
        # A stale denormalised list on the real counsellor.
        real = self.db.get(self.real["id"])
        real["assigned_student_ids"] = ["student_gone"]
        self.db.save(real)

    def run_purge(self, *args):
        out = io.StringIO()
        call_command("purge_demo_data", *args, stdout=out)
        return out.getvalue()

    def test_dry_run_changes_nothing(self):
        before = {k: v["_rev"] for k, v in self.db.docs.items()}
        report = self.run_purge("--reassign-orphans-to", self.real["id"])
        self.assertIn("Dry run only", report)
        self.assertIn(f"Asha Nair: {self.demo['id']} -> {self.real['id']}", report)
        self.assertEqual(before, {k: v["_rev"] for k, v in self.db.docs.items()})

    def test_apply_keeps_real_data_and_removes_demo(self):
        self.run_purge("--apply", "--no-backup", "--reassign-orphans-to", self.real["id"])

        kept_users = sorted(u["email"] for u in self.db.of_type("user"))
        self.assertEqual(kept_users, ["admin@aec.test", "real@aec.test", "stu@aec.test"])
        self.assertEqual([s["_id"] for s in self.db.of_type("student")], [self.student_id])
        self.assertEqual([c["_id"] for c in self.db.of_type("counsellor")], [self.real["id"]])
        for gone in ("student_001", "counsellor_001", "application_001", "counselling_session_001", "course_001",
                     self.demo["id"]):
            self.assertIsNone(self.db.get(gone), gone)
        self.assertIsNotNone(self.db.get("university_001"))
        self.assertIsNotNone(self.db.get("course_0001"))

        # The real student moved to the real counsellor, and both sides agree.
        self.assertEqual(self.db.get(self.student_id)["counsellor_id"], self.real["id"])
        self.assertEqual(self.db.get(self.real["id"])["assigned_student_ids"], [self.student_id])

        # Every remaining audit entry concerns a kept record.
        kept_ids = set(self.db.docs)
        for entry in self.db.of_type("audit_log"):
            self.assertTrue(entry.get("actor_id") in kept_ids or entry.get("target_id") in kept_ids, entry)

        # The cleaned data shows real names and counts through the API.
        admin = self.as_user("admin@aec.test")
        row = admin.get("/api/students/").data["results"][0]
        self.assertEqual(row["counsellor_name"], "Real Counsellor")
        self.assertEqual(admin.get("/api/dashboard/").data["counsellor_workload"][0]["assigned"], 1)

    def test_workflow_records_of_real_students_are_kept(self):
        """Since Sprint 2 people create applications, documents and sessions through the app."""
        user_id = users.get_by_email("stu@aec.test")["_id"]
        for doc in (
            {"_id": "application_real", "type": "application", "student_id": self.student_id},
            {"_id": "application_history_real", "type": "application_history", "application_id": "application_real"},
            {"_id": "document_real", "type": "document", "student_id": self.student_id},
            {"_id": "counselling_session_real", "type": "counselling_session", "student_id": self.student_id},
            {"_id": "notification_real", "type": "notification", "recipient_user_id": user_id},
            {"_id": "application_history_legacy", "type": "application_history", "application_id": "application_001"},
        ):
            self.db.save(doc)
        self.run_purge("--apply", "--no-backup", "--reassign-orphans-to", self.real["id"])
        for kept in ("application_real", "application_history_real", "document_real", "counselling_session_real",
                     "notification_real"):
            self.assertIsNotNone(self.db.get(kept), kept)
        self.assertIsNone(self.db.get("application_history_legacy"))  # belongs to a demo application

    def test_without_reassign_target_students_are_unassigned(self):
        self.run_purge("--apply", "--no-backup")
        self.assertIsNone(self.db.get(self.student_id)["counsellor_id"])

    def test_reassign_target_must_be_kept(self):
        with self.assertRaises(CommandError):
            self.run_purge("--apply", "--no-backup", "--reassign-orphans-to", self.demo["id"])

    def test_backup_writes_every_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = maintenance.backup(Path(tmp))
            saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(saved), len(self.db.docs))
