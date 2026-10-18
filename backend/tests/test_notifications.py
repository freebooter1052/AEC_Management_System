"""In-app notifications (SRS 4.10): events, reminders, idempotence, ownership and read state."""

import io
from datetime import timedelta
from unittest import mock

from couchdb.http import ResourceConflict
from django.core.cache import cache
from django.core.management import call_command

from apps.accounts import users
from apps.core import repository
from apps.notifications import reminders, services

from .base import WorkflowTestCase


class NotificationTests(WorkflowTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.student_user = users.get_by_email("stu@aec.test")["_id"]
        self.coun_a_user = users.get_by_email("a@aec.test")["_id"]

    def inbox(self, user_id, category=None):
        return [n for n in self.db.of_type("notification")
                if n["recipient_user_id"] == user_id and (category is None or n["category"] == category)]

    def move(self, app_id, status, client=None, **extra):
        res = (client or self.coun_a).post(f"/api/applications/{app_id}/status/", {"status": status, **extra}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        return res.data

    # -- business events --------------------------------------------------
    def test_assignment_notifies_student_and_counsellor(self):
        self.assertEqual(len(self.inbox(self.student_user, "assignment")), 1)
        self.assertEqual(len(self.inbox(self.coun_a_user, "assignment")), 1)
        self.assertEqual(self.inbox(self.student_user, "assignment")[0]["link"], "/profile/")

    def test_status_change_notifies_everyone_but_the_actor(self):
        app = self.apply().data
        self.move(app["id"], "Shortlisted")
        mine = self.inbox(self.student_user, "status_change")
        self.assertEqual(len(mine), 1)
        self.assertEqual((mine[0]["title"], mine[0]["related_id"], mine[0]["link"]),
                         ("Application update: Shortlisted", app["id"], f"/applications/{app['id']}/"))
        self.assertEqual(self.inbox(self.coun_a_user, "status_change"), [])          # the counsellor made the change
        self.move(app["id"], "Withdrawn", client=self.student)
        self.assertEqual(len(self.inbox(self.student_user, "status_change")), 1)     # the student withdrew it
        self.assertEqual(len(self.inbox(self.coun_a_user, "status_change")), 1)
        # A refused change (final status) creates nothing.
        self.coun_a.post(f"/api/applications/{app['id']}/status/", {"status": "Planned"}, format="json")
        self.assertEqual(len(self.inbox(self.student_user, "status_change")), 1)

    def test_stale_status_change_creates_no_notification(self):
        app = self.apply().data
        self.move(app["id"], "Shortlisted", rev=app["rev"])
        res = self.coun_a.post(f"/api/applications/{app['id']}/status/", {"status": "Withdrawn", "rev": app["rev"]}, format="json")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(len(self.inbox(self.student_user, "status_change")), 1)

    def test_document_events(self):
        app = self.apply().data
        self.move(app["id"], "Shortlisted")
        self.move(app["id"], "Documents Pending")   # creates SOP and LOR requirements
        required = self.inbox(self.student_user, "missing_document")
        self.assertEqual(len(required), 1)
        self.assertIn("SOP, LOR", required[0]["message"])
        self.student.post("/api/documents/checklist/", {}, format="json")    # the student's own action: no notice
        self.assertEqual(len(self.inbox(self.student_user, "missing_document")), 1)
        doc = next(d for d in self.db.of_type("document") if d["document_type"] == "Passport")
        self.student.post(f"/api/documents/{doc['_id']}/upload/", {"reference_url": "https://drive.example/p.pdf"}, format="json")
        self.coun_a.post(f"/api/documents/{doc['_id']}/verify/", {"status": "Rejected", "remarks": "Blurry scan"}, format="json")
        rejected = [n for n in self.inbox(self.student_user, "missing_document") if n["related_id"] == doc["_id"]]
        self.assertEqual((len(rejected), rejected[0]["message"]), (1, "Blurry scan"))
        self.coun_a.post("/api/documents/", {"student_id": self.student_id, "document_type": "Other", "title": "Bank statement"}, format="json")
        self.assertTrue(any("Bank statement" in n["message"] for n in self.inbox(self.student_user, "missing_document")))

    def test_follow_up_agreed_in_a_session(self):
        at = (repository.datetime.now(repository.timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:00:00Z")
        s = self.coun_a.post("/api/counselling/sessions/", {"student_id": self.student_id, "scheduled_at": at,
                                                            "duration_minutes": 30, "mode": "Phone", "topic": "Plan"}, format="json").data
        self.coun_a.post(f"/api/counselling/sessions/{s['id']}/complete/", {
            "summary": "Talked", "follow_up": {"action": "Book IELTS", "due_date": self.day(5)}}, format="json")
        rows = self.inbox(self.student_user, "follow_up")
        self.assertEqual(len(rows), 1)
        self.assertIn("Book IELTS", rows[0]["message"])

    def test_notify_is_idempotent_per_event_and_recipient(self):
        kwargs = dict(recipient_user_id=self.student_user, recipient_role="student", category="deadline",
                      title="T", message="M", event_key="test:1")
        self.assertIsNotNone(services.notify(**kwargs))
        self.assertIsNone(services.notify(**kwargs))
        self.assertIsNotNone(services.notify(**{**kwargs, "recipient_user_id": self.coun_a_user}))
        self.assertEqual(len([n for n in self.db.of_type("notification") if n.get("event_key") == "test:1"]), 2)
        self.assertIsNone(services.notify(**{**kwargs, "recipient_user_id": None}))
        with self.assertRaises(ValueError):
            services.notify(**{**kwargs, "category": "gossip"})
        with mock.patch.object(repository, "save", side_effect=ConnectionRefusedError("down")):
            self.assertIsNone(services.notify(**{**kwargs, "event_key": "test:2"}))  # logged, never raised

    # -- reminders --------------------------------------------------------
    def test_deadline_windows_are_reminded_once_each(self):
        app = self.apply(deadline=self.day(30)).data
        today = repository.today()
        self.assertEqual(reminders.sweep(today)["deadline"], 0)                            # 30 days: no window
        deadline_date = today + timedelta(days=30)
        for days_before, window in ((14, "14d"), (7, "7d"), (1, "1d"), (0, "1d"), (-1, "overdue")):
            counts = reminders.sweep(deadline_date - timedelta(days=days_before))
            expected = 0 if (days_before, window) == (0, "1d") else 2                       # student + counsellor
            self.assertEqual(counts["deadline"], expected, (days_before, window))
            self.assertEqual(reminders.sweep(deadline_date - timedelta(days=days_before))["deadline"], 0)  # repeat: none
        self.assertEqual(len(self.inbox(self.student_user, "deadline")), 4)
        self.assertEqual(reminders.sweep(deadline_date + timedelta(days=31))["deadline"], 0)  # beyond the grace period
        # Moving the deadline starts a fresh set of reminders.
        res = self.coun_a.patch(f"/api/applications/{app['id']}/", {"deadline": self.day(40)}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(reminders.sweep(today + timedelta(days=40 - 7))["deadline"], 2)
        # Submitted applications are not reminded.
        for doc in self.db.of_type("application"):
            doc["status"] = "Submitted"
            self.db.save(doc)
        self.assertEqual(reminders.sweep(today + timedelta(days=40 - 1))["deadline"], 0)

    def test_outstanding_documents_near_a_deadline_and_weekly_digest(self):
        app = self.apply(deadline=self.day(5)).data
        self.student.post("/api/documents/checklist/", {}, format="json")
        counts = reminders.sweep()
        self.assertEqual(counts["missing_document"], 2)                                    # student + counsellor
        reminder = next(n for n in self.inbox(self.student_user, "missing_document") if n["event_key"].startswith("docs_due"))
        self.assertIn("Transcript (Required)", reminder["message"])
        self.assertEqual(reminder["related_id"], app["id"])
        self.assertEqual(reminders.sweep()["missing_document"], 0)
        # Without a near deadline: one digest per week.
        for doc in self.db.of_type("application"):
            self.db.delete(doc)
        self.assertEqual(reminders.sweep()["missing_document"], 1)
        self.assertEqual(reminders.sweep()["missing_document"], 0)
        self.assertEqual(reminders.sweep(repository.today() + timedelta(days=7))["missing_document"], 1)

    def test_follow_up_reminders(self):
        at = (repository.datetime.now(repository.timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%dT%H:00:00Z")
        s = self.coun_a.post("/api/counselling/sessions/", {"student_id": self.student_id, "scheduled_at": at,
                                                            "duration_minutes": 30, "mode": "Phone", "topic": "Plan"}, format="json").data
        self.coun_a.post(f"/api/counselling/sessions/{s['id']}/complete/", {
            "summary": "Talked", "follow_up": {"action": "Send SOP draft", "due_date": self.day(1)}}, format="json")
        today = repository.today()
        self.assertEqual(reminders.sweep(today - timedelta(days=1))["follow_up"], 0)       # two days ahead: not yet
        self.assertEqual(reminders.sweep(today)["follow_up"], 2)                           # due tomorrow
        self.assertEqual(reminders.sweep(today)["follow_up"], 0)
        self.assertEqual(reminders.sweep(today + timedelta(days=2))["follow_up"], 2)       # overdue
        self.coun_a.patch(f"/api/counselling/sessions/{s['id']}/follow-up/", {"status": "Done"}, format="json")
        self.assertEqual(reminders.sweep(today + timedelta(days=9))["follow_up"], 0)       # done: no more reminders

    def test_records_with_missing_dates_do_not_break_the_sweep(self):
        self.db.save({"_id": "application_broken", "type": "application", "student_id": self.student_id, "status": "Planned",
                      "deadline": "not-a-date", "created_at": "2026-01-01T00:00:00Z"})
        self.db.save({"_id": "application_orphan", "type": "application", "student_id": "student_gone", "status": "Planned",
                      "deadline": self.day(3), "created_at": "2026-01-01T00:00:00Z"})
        self.assertEqual(reminders.sweep()["deadline"], 0)

    def test_send_reminders_command(self):
        self.apply(deadline=self.day(7))
        out = io.StringIO()
        call_command("send_reminders", stdout=out)
        self.assertIn("deadline 2", out.getvalue())
        out = io.StringIO()
        call_command("send_reminders", "--date", self.day(0), stdout=out)
        self.assertIn("0 new", out.getvalue())

    def test_on_access_sweep_is_throttled_per_user(self):
        self.apply(deadline=self.day(7))
        with mock.patch.object(reminders, "sweep", wraps=reminders.sweep) as spy:
            self.student.get("/api/dashboard/")
            self.student.get("/api/notifications/unread-count/")
            self.student.get("/api/notifications/")
            self.admin.get("/api/notifications/")                                     # admins have no reminders
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(len(self.inbox(self.student_user, "deadline")), 1)

    # -- API: ownership, listing and read state ---------------------------
    def test_list_count_and_read_state(self):
        for i in range(3):
            services.notify(recipient_user_id=self.student_user, recipient_role="student", category="deadline",
                            title=f"Reminder {i}", message="m", event_key=f"k{i}")
        data = self.student.get("/api/notifications/?page_size=2").data
        self.assertEqual((data["count"], data["total_pages"], len(data["results"])), (4, 2, 2))   # + assignment
        times = [r["created_at"] for r in data["results"]]
        self.assertEqual(times, sorted(times, reverse=True))
        self.assertEqual(self.student.get("/api/notifications/?category=deadline").data["count"], 3)
        self.assertEqual(self.student.get("/api/notifications/?category=spam").status_code, 400)
        count = self.student.get("/api/notifications/unread-count/").data
        self.assertEqual((count["unread"], count["by_category"]["deadline"]), (4, 3))

        nid = data["results"][0]["id"]
        res = self.student.post(f"/api/notifications/{nid}/read/", {}, format="json")
        self.assertEqual((res.status_code, res.data["is_read"]), (200, True))
        self.assertIsNotNone(self.db.get(nid)["read_at"])                                   # persisted
        self.assertEqual(self.student.post(f"/api/notifications/{nid}/read/", {}, format="json").status_code, 200)  # idempotent
        self.assertEqual(self.student.get("/api/notifications/unread-count/").data["unread"], 3)
        self.assertEqual(self.student.get("/api/notifications/?unread=1").data["count"], 3)
        res = self.student.post(f"/api/notifications/{nid}/read/", {"read": False}, format="json")
        self.assertEqual((res.data["is_read"], res.data["read_at"]), (False, None))
        res = self.student.post("/api/notifications/read-all/", {}, format="json")
        self.assertEqual((res.data["updated"], res.data["remaining"]), (4, 0))
        self.assertEqual(self.student.get("/api/notifications/unread-count/").data["unread"], 0)
        self.assertTrue(all(n["is_read"] for n in self.inbox(self.student_user)))

    def test_ownership(self):
        nid = self.inbox(self.student_user)[0]["_id"]
        for client in (self.coun_a, self.coun_b, self.admin):
            self.assertEqual(client.get(f"/api/notifications/{nid}/").status_code, 403)
            self.assertEqual(client.post(f"/api/notifications/{nid}/read/", {}, format="json").status_code, 403)
        self.assertFalse(self.db.get(nid)["is_read"])
        self.assertEqual(self.student.get(f"/api/notifications/{nid}/").status_code, 200)
        self.assertEqual(self.student.get("/api/notifications/notification_missing/").status_code, 404)
        self.assertNotIn(nid, [n["id"] for n in self.coun_a.get("/api/notifications/").data["results"]])
        # recipient fields cannot be changed through the API
        self.student.post(f"/api/notifications/{nid}/read/", {"recipient_user_id": self.coun_a_user}, format="json")
        self.assertEqual(self.db.get(nid)["recipient_user_id"], self.student_user)
        self.assertEqual(self.client.get("/api/notifications/").status_code, 401)
        self.assertEqual(self.client.post("/api/notifications/read-all/", {}).status_code, 401)

    def test_read_conflict_is_retried_then_reported(self):
        nid = self.inbox(self.student_user)[0]["_id"]
        real_save = repository.save
        calls = {"n": 0}

        def flaky(doc):
            calls["n"] += 1
            if calls["n"] == 1:   # someone else updated the notification first
                raise ResourceConflict(("conflict", "Document update conflict."))
            return real_save(doc)

        with mock.patch.object(repository, "save", side_effect=flaky):
            res = self.student.post(f"/api/notifications/{nid}/read/", {}, format="json")
        self.assertEqual((res.status_code, calls["n"]), (200, 2))
        self.assertTrue(self.db.get(nid)["is_read"])
        with mock.patch.object(repository, "save", side_effect=ResourceConflict(("conflict", "x"))):
            res = self.student.post(f"/api/notifications/{nid}/read/", {"read": False}, format="json")
        self.assertEqual(res.status_code, 409)                 # never reported as saved
        self.assertTrue(self.db.get(nid)["is_read"])

    def test_mark_all_read_handles_per_document_conflicts(self):
        for i in range(3):
            services.notify(recipient_user_id=self.student_user, recipient_role="student", category="deadline",
                            title="t", message="m", event_key=f"bulk{i}")
        real_update = self.db.update

        def partial(docs):
            stale = docs[0]
            current = self.db.get(stale["_id"])
            self.db.save(current)   # bump its revision so the bulk write of that one document conflicts
            return real_update(docs)

        with mock.patch.object(self.db, "update", side_effect=partial):
            res = self.student.post("/api/notifications/read-all/", {}, format="json")
        self.assertEqual((res.status_code, res.data["updated"], res.data["failed"], res.data["remaining"]), (200, 4, 0, 0))
