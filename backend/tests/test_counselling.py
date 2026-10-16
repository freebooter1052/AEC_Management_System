"""Counselling sessions (SRS 4.7): scheduling, notes, follow-ups, calendar, history and access."""

from datetime import datetime, timedelta, timezone

from apps.accounts import users
from apps.core import repository

from .base import WorkflowTestCase


def at(days=0, hours=0):
    t = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(days=days, hours=hours)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


class CounsellingTests(WorkflowTestCase):
    def schedule(self, client=None, **extra):
        body = {"student_id": self.student_id, "scheduled_at": at(days=2), "duration_minutes": 60,
                "mode": "Video call", "topic": "University shortlisting", **extra}
        return (client or self.coun_a).post("/api/counselling/sessions/", body, format="json")

    def past_session(self, days=-1):
        res = self.schedule(scheduled_at=at(days=days), topic="Initial profile assessment")
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def complete(self, session, **extra):
        body = {"summary": "Reviewed academics and budget.", "recommendations": ["Target Germany", " "],
                "action_items": ["Book IELTS"], "follow_up": {"action": "Upload transcripts", "due_date": self.day(5)},
                **extra}
        return self.coun_a.post(f"/api/counselling/sessions/{session['id']}/complete/", body, format="json")

    def test_scheduling_rules(self):
        res = self.schedule()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual((res.data["status"], res.data["counsellor_name"], res.data["student_name"]),
                         ("Scheduled", "Counsellor A", "Asha Nair"))
        self.assertEqual(res.data["ends_at"], at(days=2, hours=1))
        clash = self.schedule(scheduled_at=at(days=2, hours=0), topic="Overlap")
        self.assertEqual(clash.status_code, 400)
        self.assertIn("already has a session", str(clash.data["scheduled_at"]))
        self.assertEqual(self.schedule(scheduled_at=at(days=2, hours=1)).status_code, 201)  # back-to-back is fine

        self.assertEqual(self.schedule(client=self.student).status_code, 403)
        self.assertEqual(self.schedule(client=self.coun_b).status_code, 403)
        self.assertEqual(self.schedule(duration_minutes=5).status_code, 400)
        self.assertEqual(self.schedule(mode="Carrier pigeon").status_code, 400)
        # Admins schedule with the student's counsellor; an unassigned student has none.
        res = self.schedule(client=self.admin, scheduled_at=at(days=3))
        self.assertEqual((res.status_code, res.data["counsellor_name"]), (201, "Counsellor A"))
        self.register(email="other@aec.test")
        other_id = users.get_by_email("other@aec.test")["profile_id"]
        self.assertEqual(self.schedule(client=self.admin, student_id=other_id).status_code, 400)

    def test_complete_with_summary_recommendations_actions_and_follow_up(self):
        future = self.schedule().data
        self.assertEqual(self.complete(future).status_code, 400)  # has not happened yet
        session = self.past_session()
        self.assertTrue(self.student.get(f"/api/counselling/sessions/{session['id']}/").data["needs_notes"])
        self.assertEqual(self.complete(session, follow_up={"action": "x", "due_date": self.day(-10)}).status_code, 400)
        self.assertEqual(self.coun_a.post(f"/api/counselling/sessions/{session['id']}/complete/", {},
                                          format="json").status_code, 400)  # summary required
        res = self.complete(session)
        self.assertEqual(res.status_code, 200, res.data)
        d = res.data
        self.assertEqual(d["status"], "Completed")
        self.assertEqual(d["recommendations"], ["Target Germany"])  # blanks dropped
        self.assertEqual(d["action_items"], ["Book IELTS"])
        self.assertEqual(d["follow_up"]["status"], "Pending")
        self.assertEqual(d["follow_up_state"], "pending")
        self.assertIsNotNone(d["completed_at"])
        self.assertEqual(self.complete(session).status_code, 400)  # already completed

        cancelled = self.schedule(scheduled_at=at(days=4)).data
        res = self.coun_a.post(f"/api/counselling/sessions/{cancelled['id']}/cancel/", {"reason": "Student unwell"},
                               format="json")
        self.assertEqual((res.status_code, res.data["status"], res.data["cancel_reason"]), (200, "Cancelled", "Student unwell"))
        self.assertEqual(self.coun_a.patch(f"/api/counselling/sessions/{cancelled['id']}/", {"topic": "x"},
                                           format="json").status_code, 400)

    def test_follow_ups(self):
        session = self.past_session(days=-5)
        self.complete(session, follow_up={"action": "Upload transcripts", "due_date": self.day(0)})
        rows = self.student.get("/api/counselling/follow-ups/?status=Pending").data
        self.assertEqual(rows["count"], 1)
        self.assertEqual((rows["results"][0]["action"], rows["results"][0]["state"]), ("Upload transcripts", "due_today"))
        url = f"/api/counselling/sessions/{session['id']}/follow-up/"
        self.assertEqual(self.student.patch(url, {"due_date": self.day(9)}, format="json").status_code, 403)
        self.assertEqual(self.coun_b.patch(url, {"status": "Done"}, format="json").status_code, 403)
        res = self.coun_a.patch(url, {"due_date": self.day(-3)}, format="json")
        self.assertEqual((res.status_code, res.data["follow_up_state"]), (200, "overdue"))
        res = self.student.patch(url, {"status": "Done"}, format="json")
        self.assertEqual((res.status_code, res.data["follow_up"]["status"]), (200, "Done"))
        self.assertIsNotNone(res.data["follow_up"]["completed_at"])
        self.assertEqual(self.student.get("/api/counselling/follow-ups/?status=Pending").data["count"], 0)
        self.assertEqual(self.coun_a.get("/api/counselling/follow-ups/").data["count"], 1)
        no_follow = self.past_session(days=-2)
        self.complete(no_follow, follow_up=None)
        self.assertEqual(self.coun_a.patch(f"/api/counselling/sessions/{no_follow['id']}/follow-up/",
                                           {"status": "Done"}, format="json").status_code, 400)

    def test_calendar_history_and_reassignment(self):
        upcoming = self.schedule().data
        session = self.past_session()
        self.complete(session)
        start, end = self.day(-3), self.day(10)
        cal = self.coun_a.get(f"/api/counselling/calendar/?start={start}&end={end}").data
        self.assertEqual([s["id"] for s in cal["sessions"]], [session["id"], upcoming["id"]])
        self.assertEqual([f["action"] for f in cal["follow_ups"]], ["Upload transcripts"])
        self.assertEqual(len(self.student.get(f"/api/counselling/calendar/?start={start}&end={end}").data["sessions"]), 2)
        self.assertEqual(self.coun_b.get(f"/api/counselling/calendar/?start={start}&end={end}").data["sessions"], [])
        self.assertEqual(self.coun_a.get(f"/api/counselling/calendar/?start={end}&end={start}").status_code, 400)
        self.assertEqual(self.coun_a.get("/api/counselling/calendar/?start=2026-13-01").status_code, 400)

        past = self.student.get("/api/counselling/sessions/?when=past").data
        self.assertEqual([s["id"] for s in past["results"]], [session["id"]])
        nxt = self.student.get("/api/counselling/sessions/?when=upcoming").data
        self.assertEqual([s["id"] for s in nxt["results"]], [upcoming["id"]])
        self.assertFalse(nxt["results"][0]["can_manage"])

        # After reassignment the new counsellor sees the student's full counselling history, read-only.
        self.admin.post(f"/api/students/{self.student_id}/assign-counsellor/", {"counsellor_id": self.counsellor_b["id"]},
                        format="json")
        history = self.coun_b.get(f"/api/counselling/sessions/?student_id={self.student_id}").data
        self.assertEqual(history["count"], 2)
        self.assertFalse(any(s["can_manage"] for s in history["results"]))
        self.assertEqual(self.coun_b.post(f"/api/counselling/sessions/{upcoming['id']}/cancel/", {},
                                          format="json").status_code, 403)
        self.assertEqual(self.coun_a.get(f"/api/counselling/sessions/?student_id={self.student_id}").status_code, 403)
        self.assertEqual(self.coun_a.get(f"/api/counselling/sessions/{session['id']}/").status_code, 200)  # own record

    def test_reschedule_with_conflict_detection(self):
        session = self.schedule().data
        url = f"/api/counselling/sessions/{session['id']}/"
        res = self.coun_a.patch(url, {"scheduled_at": at(days=5), "mode": "Phone", "rev": session["rev"]}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data["scheduled_at"], res.data["mode"]), (at(days=5), "Phone"))
        self.assertEqual(self.coun_a.patch(url, {"topic": "Again", "rev": session["rev"]}, format="json").status_code, 409)
        self.assertEqual(self.student.patch(url, {"topic": "Mine"}, format="json").status_code, 403)

    def test_dashboards_show_the_workflow(self):
        self.apply()
        self.schedule()
        session = self.past_session()
        self.complete(session)
        self.student.post("/api/documents/checklist/", {}, format="json")
        stu = self.student.get("/api/dashboard/").data
        self.assertEqual(stu["applications"]["total"], 1)
        self.assertEqual(stu["documents"]["needs_attention"], 5)
        self.assertEqual(len(stu["upcoming_sessions"]), 1)
        self.assertEqual(stu["follow_ups"]["pending"], 1)
        coun = self.coun_a.get("/api/dashboard/").data
        self.assertEqual((coun["applications"]["by_status"]["Planned"], coun["follow_ups"]["pending"]), (1, 1))
        self.assertEqual(self.coun_b.get("/api/dashboard/").data["applications"]["total"], 0)
        admin = self.admin.get("/api/dashboard/").data
        self.assertEqual((admin["applications"]["total"], admin["documents"]["total"]), (1, 5))
        self.assertEqual(repository.count({"type": "counselling_session"}), 2)
