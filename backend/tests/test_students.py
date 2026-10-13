"""Student profile: own-profile access, validation, deep merge, conflicts."""

from apps.accounts import users

from .base import APITestCase


class StudentProfileTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.register()
        self.student = self.as_user("stu@aec.test")

    def test_student_reads_and_updates_own_profile(self):
        before = self.student.get("/api/students/me/").data["profile_completion"]["overall"]
        res = self.student.patch("/api/students/me/", {
            "personal": {"date_of_birth": "2003-04-02", "address": {"city": "Kochi"}},
            "academic": {"degree": "B.Tech CSE", "institution": "CUSAT", "cgpa": 8.4, "gpa_scale": 10,
                         "graduation_year": 2025, "english_test": {"test_type": "IELTS", "overall": 7.5}},
            "preferences": {"countries": ["Germany", "Canada"], "course_areas": ["AI/ML"], "degree_level": "Masters",
                            "intake": "Fall 2027", "budget": {"min": 15000, "max": 25000, "currency": "EUR"}},
        }, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertGreater(res.data["profile_completion"]["overall"], before)
        self.assertEqual(res.data["personal"]["address"]["city"], "Kochi")
        self.assertEqual(res.data["personal"]["first_name"], "Asha")  # untouched fields are kept (deep merge)
        self.assertEqual(res.data["academic"]["english_test"]["overall"], 7.5)

    def test_profile_validation(self):
        res = self.student.patch("/api/students/me/", {"academic": {"cgpa": 9.5, "gpa_scale": 4}}, format="json")
        self.assertEqual(res.status_code, 400)
        res = self.student.patch("/api/students/me/", {"preferences": {"budget": {"min": 9, "max": 1}}}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_student_cannot_set_own_counsellor_or_see_others(self):
        res = self.student.patch("/api/students/me/", {"counsellor_id": "counsellor_x"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.data["counsellor_id"])

        self.register(email="other@aec.test")
        other_id = users.get_by_email("other@aec.test")["profile_id"]
        self.assertEqual(self.student.get(f"/api/students/{other_id}/").status_code, 403)
        self.assertEqual(self.student.get("/api/students/").status_code, 403)
        self.assertEqual(self.student.post(f"/api/students/{other_id}/assign-counsellor/",
                                           {"counsellor_id": None}, format="json").status_code, 403)

    def test_stale_revision_returns_conflict(self):
        self.student.patch("/api/students/me/", {"personal": {"gender": "F"}}, format="json")
        res = self.student.patch("/api/students/me/", {"personal": {"gender": "X"}, "rev": "1-stale"}, format="json")
        self.assertEqual(res.status_code, 409)
