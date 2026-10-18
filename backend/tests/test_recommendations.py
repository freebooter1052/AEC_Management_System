"""Recommendation API (SRS 4.8): generation, persistence, refresh, review, access and conflicts."""

from unittest import mock

from apps.accounts import users
from apps.core import repository
from apps.recommendations import services

from .base import WorkflowTestCase

PROFILE = {
    "academic": {"cgpa": 8.5, "gpa_scale": 10, "english_test": {"test_type": "IELTS", "overall": 7.0}},
    "preferences": {"countries": ["Germany"], "course_areas": ["CS & AI"], "degree_level": "Masters",
                    "intake": "Fall Open", "budget": {"min": 0, "max": 20000, "currency": "EUR"}},
}


class RecommendationAPITests(WorkflowTestCase):
    def setUp(self):
        super().setUp()
        self.db.save({"_id": "university_002", "type": "university", "name": "McGill University", "country": "Canada", "rank": 30})
        self.db.save({"_id": "course_0003", "type": "course", "university_id": "university_002", "title": "Chemistry",
                      "cluster": "Chemistry"})
        res = self.student.patch("/api/students/me/", PROFILE, format="json")
        self.assertEqual(res.status_code, 200, res.data)

    def generate(self, client=None, **body):
        return (client or self.student).post("/api/recommendations/generate/", body, format="json")

    def recs(self):
        return {d["course_id"]: d for d in self.db.of_type("recommendation") if d["student_id"] == self.student_id}

    def test_generate_persists_explainable_results(self):
        res = self.generate()
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["count"], 2)
        self.assertEqual({r["course_id"] for r in res.data["results"]}, {"course_0001", "course_0002"})  # not Chemistry
        for r in res.data["results"]:
            self.assertEqual((r["method"], r["origin"], r["status"], r["intake_id"]), ("rule_based_v2", "engine", "Suggested", "intake_open"))
            self.assertIn(r["eligibility"], ("eligible", "insufficient_data"))
            self.assertTrue(r["reasons"])
            self.assertEqual([f["key"] for f in r["factors"]], ["country", "course", "academic", "intake", "budget"])
            self.assertEqual(r["factors"][4]["status"], "unknown")                       # no tuition in the catalogue
            self.assertIn({"source": "catalogue", "item": "Tuition"}, r["missing_data"])
            self.assertTrue(r["generated_at"])
            self.assertNotIn("inputs_hash", r)
        self.assertEqual(res.data["run"]["stats"]["recommended"], 2)
        self.assertEqual(res.data["freshness"]["state"], "current")
        stored = self.recs()
        self.assertEqual(set(stored), {"course_0001", "course_0002"})
        for course_id, doc in stored.items():
            self.assertEqual(doc["_id"], services.recommendation_id(self.student_id, course_id))   # deterministic
        self.assertEqual(len(self.db.of_type("recommendation_run")), 1)
        self.assertTrue(any(a["action"] == "recommendations.generated" for a in self.db.of_type("audit_log")))

    def test_refresh_is_idempotent_and_deterministic(self):
        first = self.generate().data["results"]
        second = self.generate(self.coun_a, student_id=self.student_id).data["results"]
        third = self.generate(self.admin, student_id=self.student_id).data["results"]
        key = lambda rows: [(r["id"], r["match_score"], r["ranking_score"], r["confidence"]) for r in rows]  # noqa: E731
        self.assertEqual(key(first), key(second))
        self.assertEqual(key(first), key(third))
        self.assertEqual(len(self.db.of_type("recommendation")), 2)
        self.assertEqual(len(self.db.of_type("recommendation_run")), 1)

    def test_hard_rules_exclude_and_cannot_be_overridden(self):
        self.generate()
        rec_b = self.recs()["course_0002"]
        res = self.admin.patch("/api/universities/courses/course_0002/", {"level": "PhD"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        data = self.generate().data
        self.assertEqual([r["course_id"] for r in data["results"]], ["course_0001"])
        self.assertEqual(data["run"]["stats"]["ineligible_by_rule"], {"level": 1})
        self.assertIsNone(self.db.get(rec_b["_id"]))  # an undecided suggestion that no longer qualifies is removed
        res = self.coun_a.post("/api/recommendations/", {"student_id": self.student_id, "course_id": "course_0002"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("hard eligibility", str(res.data))

    def test_decisions_survive_refresh_and_ineligible_cannot_be_accepted(self):
        self.generate()
        rec = self.coun_a.get(f"/api/recommendations/?student_id={self.student_id}").data["results"][1]
        res = self.coun_a.patch(f"/api/recommendations/{rec['id']}/", {"status": "Accepted", "remarks": "Good fit", "rev": rec["rev"]}, format="json")
        self.assertEqual((res.status_code, res.data["status"], res.data["reviewed_by_name"]), (200, "Accepted", "Counsellor A"))
        self.admin.patch(f"/api/universities/courses/{rec['course_id']}/", {"level": "PhD"}, format="json")
        self.generate()
        kept = self.db.get(rec["id"])
        self.assertEqual((kept["status"], kept["remarks"], kept["eligibility"], kept["in_latest_run"]),
                         ("Accepted", "Good fit", "ineligible", False))
        self.coun_a.patch(f"/api/recommendations/{rec['id']}/", {"status": "Rejected"}, format="json")
        res = self.coun_a.patch(f"/api/recommendations/{rec['id']}/", {"status": "Accepted"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.coun_a.patch(f"/api/recommendations/{rec['id']}/", {}, format="json").status_code, 400)
        self.assertEqual(self.coun_a.patch(f"/api/recommendations/{rec['id']}/", {"status": "Maybe"}, format="json").status_code, 400)

    def test_counsellor_adds_and_tier_override_survives_refresh(self):
        self.db.save({"_id": "course_0004", "type": "course", "university_id": "university_002", "title": "Polymer Science",
                      "cluster": "Chemistry"})
        res = self.coun_a.post("/api/recommendations/", {"student_id": self.student_id, "course_id": "course_0004",
                                                         "remarks": "Scholarship available"}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual((res.data["origin"], res.data["status"], res.data["created_by_name"]), ("counsellor", "Accepted", "Counsellor A"))
        self.assertTrue(res.data["reasons"])
        dup = self.coun_a.post("/api/recommendations/", {"student_id": self.student_id, "course_id": "course_0004"}, format="json")
        self.assertEqual(dup.status_code, 400)
        missing = self.coun_a.post("/api/recommendations/", {"student_id": self.student_id, "course_id": "course_9999"}, format="json")
        self.assertEqual(missing.status_code, 400)
        res = self.coun_a.patch(f"/api/recommendations/{res.data['id']}/", {"tier": "Reach"}, format="json")
        self.assertEqual(res.data["tier"], "Reach")
        self.generate()
        self.assertEqual(self.db.get(res.data["id"])["tier"], "Reach")       # counsellor's tier kept
        self.assertEqual(self.db.get(res.data["id"])["origin"], "counsellor")  # not deleted by the refresh

    def test_catalogue_cache_sees_new_and_edited_courses(self):
        first = {r["course_id"] for r in self.generate().data["results"]}
        res = self.admin.post("/api/universities/university_001/courses/", {"title": "Computer Vision", "cluster": "CS & AI"},
                              format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.admin.patch("/api/universities/courses/course_0001/", {"is_active": False}, format="json")
        second = {r["course_id"] for r in self.generate().data["results"]}
        self.assertIn(res.data["id"], second)          # added course is evaluated
        self.assertIn("course_0001", first)
        self.assertNotIn("course_0001", second)        # deactivated course is gone

    def test_staleness(self):
        self.generate()
        url = f"/api/recommendations/?student_id={self.student_id}"
        self.assertEqual(self.student.get(url).data["freshness"]["state"], "current")
        self.student.patch("/api/students/me/", {"personal": {"gender": "Female"}}, format="json")
        self.assertEqual(self.student.get(url).data["freshness"]["state"], "current")   # irrelevant field
        self.student.patch("/api/students/me/", {"preferences": {"countries": ["Germany", "Canada"]}}, format="json")
        fresh = self.student.get(url).data["freshness"]
        self.assertEqual(fresh["state"], "stale")
        self.assertIn("profile", fresh["reasons"][0])
        self.generate()
        self.assertEqual(self.student.get(url).data["freshness"]["state"], "current")
        self.admin.patch("/api/universities/courses/course_0001/", {"tuition": {"amount_per_year": 5000, "currency": "EUR"}}, format="json")
        fresh = self.student.get(url).data["freshness"]
        self.assertEqual(fresh["state"], "stale")
        self.assertIn("catalogue", fresh["reasons"][0])

    def test_access_rules(self):
        self.generate()
        rec = next(iter(self.recs().values()))
        url = f"/api/recommendations/{rec['_id']}/"
        self.register(email="other@aec.test")
        other = self.as_user("other@aec.test")
        self.assertEqual(other.get(url).status_code, 403)
        # a student's student_id parameter is ignored: they always get their own (empty) list
        self.assertEqual(other.get(f"/api/recommendations/?student_id={self.student_id}").data["count"], 0)
        self.assertEqual(self.coun_b.get(url).status_code, 403)
        self.assertEqual(self.coun_b.get(f"/api/recommendations/?student_id={self.student_id}").status_code, 403)
        self.assertEqual(self.generate(self.coun_b, student_id=self.student_id).status_code, 403)
        self.assertEqual(self.coun_b.patch(url, {"status": "Rejected"}, format="json").status_code, 403)
        self.assertEqual(self.coun_a.get(url).status_code, 200)
        self.assertEqual(self.admin.get(url).status_code, 200)
        self.assertEqual(self.student.patch(url, {"status": "Accepted"}, format="json").status_code, 403)
        self.assertEqual(self.student.post("/api/recommendations/", {"student_id": self.student_id, "course_id": "course_0001"},
                                           format="json").status_code, 403)
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.post("/api/recommendations/generate/", {}, format="json").status_code, 401)
        self.assertEqual(self.admin.get("/api/recommendations/").status_code, 400)          # staff must name a student
        self.assertEqual(self.admin.get("/api/recommendations/recommendation_nope/").status_code, 404)
        self.assertEqual(self.student.get("/api/recommendations/?status=Maybe").status_code, 400)

    def test_stale_rev_is_a_conflict(self):
        self.generate()
        rec = self.coun_a.get(f"/api/recommendations/?student_id={self.student_id}").data["results"][0]
        url = f"/api/recommendations/{rec['id']}/"
        self.assertEqual(self.coun_a.patch(url, {"remarks": "one", "rev": rec["rev"]}, format="json").status_code, 200)
        res = self.coun_a.patch(url, {"remarks": "two", "rev": rec["rev"]}, format="json")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(self.db.get(rec["id"])["remarks"], "one")  # the failed update changed nothing

    def test_concurrent_edit_during_refresh_is_preserved(self):
        self.generate()
        rec_id = services.recommendation_id(self.student_id, "course_0001")
        real_bulk = repository.bulk_save

        def racing_bulk(docs):
            # A counsellor accepts the recommendation between the refresh's read and its write.
            current = self.db.get(rec_id)
            current.update(status="Accepted", remarks="Accepted meanwhile")
            self.db.save(current)
            return real_bulk(docs)

        with mock.patch.object(repository, "bulk_save", side_effect=racing_bulk):
            res = self.generate()
        self.assertEqual(res.status_code, 200, res.data)
        doc = self.db.get(rec_id)
        self.assertEqual((doc["status"], doc["remarks"]), ("Accepted", "Accepted meanwhile"))  # concurrent change kept
        self.assertEqual(doc["method"], "rule_based_v2")                                       # engine fields re-applied
        self.assertEqual(len(self.db.of_type("recommendation")), 2)

    def test_empty_catalogue_and_incomplete_profile(self):
        self.register(email="new@aec.test")
        res = self.generate(self.as_user("new@aec.test"))
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data["count"], res.data["run"]["status"]), (0, "insufficient_profile"))
        for c in self.db.of_type("course"):
            self.db.delete(c)
        res = self.generate()
        self.assertEqual((res.status_code, res.data["count"], res.data["run"]["status"]), (200, 0, "ok"))
        self.assertTrue(res.data["run"]["message"])

    def test_pagination(self):
        self.generate()
        page = self.student.get("/api/recommendations/?page_size=1").data
        self.assertEqual((page["count"], page["total_pages"], len(page["results"])), (2, 2, 1))
        page2 = self.student.get("/api/recommendations/?page_size=1&page=2").data
        self.assertNotEqual(page["results"][0]["id"], page2["results"][0]["id"])
        self.assertEqual(self.student.get("/api/recommendations/?page=99").data["results"], [])
        self.assertEqual(self.student.get("/api/recommendations/?page_size=100000").data["page_size"], 100)

    def test_seed_v1_document_is_read_and_upgraded_in_place(self):
        self.db.save({"_id": "recommendation_seedabc12345", "type": "recommendation", "student_id": self.student_id,
                      "university_id": "university_001", "course_id": "course_0001", "created_by": self.counsellor_a["id"],
                      "method": "rule_based_v1", "match_score": 88, "tier": "Target", "status": "Accepted", "remarks": "",
                      "match_factors": {"country_match": True, "course_match": True, "academic_fit": 20,
                                        "intake_available": True, "budget_fit": None},
                      "reasons": ["Seed reason"], "snapshot": {"course_title": "Robotics"}, "source": "seed",
                      "created_at": "2026-09-01T00:00:00Z"})
        row = self.student.get("/api/recommendations/").data["results"][0]
        self.assertEqual([f["status"] for f in row["factors"]], ["match", "match", "match", "match", "unknown"])
        self.assertIsNone(row["eligibility"])
        self.assertNotIn("source", row)
        self.generate()
        doc = self.db.get("recommendation_seedabc12345")
        self.assertEqual((doc["status"], doc["method"], doc["source"]), ("Accepted", "rule_based_v2", "seed"))
        self.assertIn("weight", doc["match_factors"]["country"])
        self.assertEqual(len([d for d in self.db.of_type("recommendation") if d["course_id"] == "course_0001"]), 1)

    def test_deleting_the_student_removes_recommendations_and_notifications(self):
        self.generate()
        user_id = users.get_by_email("stu@aec.test")["_id"]
        self.assertTrue([n for n in self.db.of_type("notification") if n["recipient_user_id"] == user_id])  # assignment
        self.assertEqual(self.admin.delete(f"/api/students/{self.student_id}/").status_code, 204)
        self.assertEqual(self.db.of_type("recommendation"), [])
        self.assertEqual(self.db.of_type("recommendation_run"), [])
        self.assertEqual([n for n in self.db.of_type("notification") if n["recipient_user_id"] == user_id], [])
