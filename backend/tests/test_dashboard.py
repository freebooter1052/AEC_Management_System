"""Dashboards (SRS 4.9) and admin course maintenance (SRS 4.4)."""

from collections import Counter

from django.core.cache import cache

from apps.core import repository

from .base import WorkflowTestCase
from .test_recommendations import PROFILE


class DashboardTests(WorkflowTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.student.patch("/api/students/me/", PROFILE, format="json")

    def test_student_dashboard_shows_own_records(self):
        app = self.apply().data
        self.student.post("/api/documents/checklist/", {}, format="json")
        self.student.post("/api/recommendations/generate/", {}, format="json")
        d = self.student.get("/api/dashboard/").data
        self.assertEqual(d["role"], "student")
        self.assertEqual(d["profile_completion"]["overall"], repository.get(self.student_id)["profile_completion"]["overall"])
        self.assertEqual([a["id"] for a in d["application_list"]], [app["id"]])
        self.assertEqual(d["application_list"][0]["deadline_info"]["state"], "open")
        self.assertEqual(len(d["documents_attention"]), 5)
        self.assertEqual(d["documents"]["by_status"]["Required"], 5)
        self.assertEqual(d["recommendations"]["total"], 2)
        self.assertEqual(len(d["recommendations"]["top"]), 2)
        self.assertTrue(d["recommendations"]["top"][0]["reasons"])
        self.assertEqual(d["recommendations"]["freshness"]["state"], "current")
        self.assertGreaterEqual(d["notifications"]["unread"], 1)        # counsellor assignment
        self.assertTrue(d["notifications"]["latest"])

    def test_empty_states(self):
        self.register(email="new@aec.test")
        d = self.as_user("new@aec.test").get("/api/dashboard/").data
        self.assertEqual((d["application_list"], d["documents_attention"], d["recommendations"]["top"]), ([], [], []))
        self.assertEqual(d["recommendations"]["freshness"]["state"], "never")
        d = self.coun_b.get("/api/dashboard/").data
        self.assertEqual((d["needs_attention"], d["review_queue"], d["applications"]["total"]), ([], [], 0))
        self.assertEqual(self.client.get("/api/dashboard/").status_code, 401)

    def test_counsellor_dashboard_is_limited_to_assigned_students(self):
        self.apply()
        self.student.post("/api/documents/checklist/", {}, format="json")
        passport = next(x for x in self.db.of_type("document") if x["document_type"] == "Passport")
        self.student.post(f"/api/documents/{passport['_id']}/upload/", {"reference_url": "https://x.example/p.pdf"}, format="json")
        d = self.coun_a.get("/api/dashboard/").data
        self.assertEqual([r["id"] for r in d["review_queue"]], [passport["_id"]])
        self.assertEqual(d["needs_attention"][0]["id"], self.student_id)
        self.assertEqual((d["needs_attention"][0]["documents_outstanding"], d["needs_attention"][0]["open_applications"]), (4, 1))
        self.assertEqual(d["students_without_recommendations"], 1)
        other = self.coun_b.get("/api/dashboard/").data
        self.assertEqual((other["review_queue"], other["documents"]["total"]), ([], 0))
        # Filters narrow the application figures.
        self.assertEqual(self.coun_a.get("/api/dashboard/?intake_id=intake_open").data["applications"]["total"], 1)
        self.assertEqual(self.coun_a.get("/api/dashboard/?intake_id=intake_closed").data["applications"]["total"], 0)
        self.assertEqual(self.coun_a.get("/api/dashboard/?country=Germany").data["applications"]["total"], 1)
        self.assertEqual(self.coun_a.get("/api/dashboard/?country=Canada").data["applications"]["total"], 0)
        # counsellor_id is an admin-only filter: ignored for counsellors
        self.assertEqual(self.coun_a.get(f"/api/dashboard/?counsellor_id={self.counsellor_b['id']}").data["applications"]["total"], 1)

    def test_admin_aggregates_match_the_stored_records(self):
        app = self.apply().data
        self.coun_a.post(f"/api/applications/{app['id']}/status/", {"status": "Shortlisted"}, format="json")
        self.apply(course_id="course_0002")
        self.student.post("/api/recommendations/generate/", {}, format="json")
        d = self.admin.get("/api/dashboard/").data
        t = d["totals"]
        self.assertEqual((t["students"], t["counsellors"], t["universities"], t["courses"], t["applications"]),
                         (len(self.db.of_type("student")), 2, 1, 2, 2))
        by_status = Counter(a["status"] for a in self.db.of_type("application"))
        self.assertEqual({k: v for k, v in d["applications"]["by_status"].items() if v}, dict(by_status))
        self.assertEqual(d["reports"]["by_country"], [{"name": "Germany", "applications": 2, "offers": 0}])
        self.assertEqual(d["reports"]["by_intake"][0]["applications"], 2)
        self.assertEqual(d["reports"]["outcomes"], {"decided": 0, "offers": 0, "offer_rate_pct": None})
        self.assertEqual(d["reports"]["recommendations"]["total"], 2)
        row = next(c for c in d["counsellor_workload"] if c["id"] == self.counsellor_a["id"])
        self.assertEqual((row["assigned"], row["open_applications"]), (1, 2))
        self.assertEqual({c["name"] for c in d["filter_options"]["counsellors"]}, {"Counsellor A", "Counsellor B"})
        # Admin filters
        only_b = self.admin.get(f"/api/dashboard/?counsellor_id={self.counsellor_b['id']}").data
        self.assertEqual((only_b["applications"]["total"], [c["id"] for c in only_b["counsellor_workload"]]),
                         (0, [self.counsellor_b["id"]]))
        self.assertEqual(self.admin.get("/api/dashboard/?country=Canada").data["totals"]["applications"], 0)
        # Aggregates never expose student personal details
        self.assertNotIn("stu@aec.test", str(d["reports"]))


class CourseAdminTests(WorkflowTestCase):
    URL = "/api/universities/courses/course_0001/"

    def test_admin_records_course_details(self):
        body = {"level": "Masters", "duration_months": 24, "tuition": {"amount_per_year": 18000, "currency": "EUR"},
                "eligibility": {"min_grade_pct": 75, "min_english": {"IELTS": 6.5, "TOEFL": 90}},
                "intake_ids": ["intake_open"]}
        res = self.admin.patch(self.URL, body, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        stored = self.db.get("course_0001")
        self.assertEqual((stored["level"], stored["tuition"]["amount_per_year"], stored["eligibility"]["min_english"]["IELTS"]),
                         ("Masters", 18000, 6.5))
        self.assertEqual((stored["title"], stored["cluster"]), ("Robotics", "CS & AI"))   # untouched fields kept
        self.assertTrue(stored["updated_at"])
        self.assertEqual(res.data["university"]["name"], "Technical University of Munich")
        self.assertEqual(self.admin.patch(self.URL, {"title": "Robotics", "rev": res.data["rev"]}, format="json").status_code, 200)
        self.assertEqual(self.admin.patch(self.URL, {"title": "Again", "rev": res.data["rev"]}, format="json").status_code, 409)

    def test_validation_and_permissions(self):
        for bad in ({"tuition": {"amount_per_year": 100, "currency": "euro"}}, {"tuition": {"amount_per_year": 100}},
                    {"eligibility": {"min_english": {"IELTS": 65}}}, {"eligibility": {"min_english": {"Klingon": 5}}},
                    {"eligibility": {"min_grade_pct": 120}}, {"level": "Postdoc"}, {"intake_ids": ["intake_nope"]},
                    {"duration_months": 0}, {"title": "  "}):
            self.assertEqual(self.admin.patch(self.URL, bad, format="json").status_code, 400, bad)
        self.assertEqual(self.coun_a.patch(self.URL, {"level": "PhD"}, format="json").status_code, 403)
        self.assertEqual(self.student.patch(self.URL, {"level": "PhD"}, format="json").status_code, 403)
        self.assertEqual(self.client.patch(self.URL, {"level": "PhD"}, format="json").status_code, 401)
        self.assertEqual(self.admin.patch("/api/universities/courses/course_9999/", {"level": "PhD"}, format="json").status_code, 404)
        self.assertNotIn("level", self.db.get("course_0001"))

    def test_deactivated_course_is_hidden_and_cannot_be_applied_for(self):
        self.assertEqual(self.admin.patch(self.URL, {"is_active": False}, format="json").status_code, 200)
        titles = [c["title"] for c in self.student.get("/api/universities/courses/").data["results"]]
        self.assertEqual(titles, ["Data Science"])
        self.assertEqual(len(self.admin.get("/api/universities/courses/").data["results"]), 2)
        self.assertEqual([c["id"] for c in self.student.get("/api/universities/university_001/").data["courses"]], ["course_0002"])
        self.assertEqual(self.student.get(self.URL).status_code, 404)
        self.assertEqual(self.admin.get(self.URL).status_code, 200)
        res = self.apply()
        self.assertEqual(res.status_code, 400)
        self.assertIn("no longer offered", str(res.data))

    def test_admin_adds_a_course(self):
        res = self.admin.post("/api/universities/university_001/courses/", {"title": "Quantum Engineering", "cluster": "Physics & Astronomy",
                                                                           "level": "Masters"}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data["id"].startswith("course_"))
        self.assertEqual(self.admin.post("/api/universities/university_001/courses/", {}, format="json").status_code, 400)
        self.assertEqual(self.admin.post("/api/universities/university_404/courses/", {"title": "x"}, format="json").status_code, 404)
        self.assertEqual(self.coun_a.post("/api/universities/university_001/courses/", {"title": "x"}, format="json").status_code, 403)
        self.assertTrue(any(a["action"] == "course.created" for a in self.db.of_type("audit_log")))
