"""Student profile: own-profile access, validation, deep merge, conflicts."""

from apps.accounts import users
from apps.core import repository

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

    def test_countries_are_stored_in_one_spelling(self):
        res = self.student.patch("/api/students/me/", {
            "personal": {"citizenship": "india", "address": {"country": "U.S.A."}},
            "preferences": {"countries": ["United States", "usa", "United Kingdom", "Germany", "Ireland"]},
        }, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["personal"]["citizenship"], "India")
        self.assertEqual(res.data["personal"]["address"]["country"], "United States")
        # target countries use the catalogue's spelling (university.country), once each
        self.assertEqual(res.data["preferences"]["countries"], ["US", "UK", "Germany", "Ireland"])

        res = self.student.patch("/api/students/me/", {"preferences": {"countries": ["Narnia"]}}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("countries", res.data["preferences"])
        self.assertEqual(self.student.patch("/api/students/me/", {"personal": {"citizenship": ""}},
                                            format="json").status_code, 200)  # blank stays allowed

    def test_country_list_is_public_and_maps_catalogue_names(self):
        rows = self.client.get("/api/countries/").data
        by_name = {r["name"]: r["catalogue_name"] for r in rows}
        self.assertEqual((by_name["United States"], by_name["United Kingdom"], by_name["India"]), ("US", "UK", "India"))


class StudentSearchTests(APITestCase):
    """The student pickers search the server, so students beyond the first page are reachable."""

    def setUp(self):
        super().setUp()
        from apps.students import services
        self.admin = self.as_user("admin@aec.test")
        self.counsellor_id = self.create_counsellor(self.admin, max_students=200)["id"]
        for i in range(130):
            doc = services.build_student(user_id=f"user_s{i}", email=f"s{i}@aec.test",
                                         first_name=f"Pupil{i:03d}", last_name="Zed" if i == 125 else "Common")
            if i % 2:
                doc["counsellor_id"] = self.counsellor_id
            repository.save(doc)

    def test_search_reaches_students_beyond_the_first_hundred(self):
        first = self.admin.get("/api/students/?page_size=100").data
        self.assertEqual((first["count"], len(first["results"]), first["total_pages"]), (130, 100, 2))
        res = self.admin.get("/api/students/?q=pupil125 zed&page_size=20").data
        self.assertEqual([s["full_name"] for s in res["results"]], ["Pupil125 Zed"])
        self.assertEqual(self.admin.get("/api/students/?q=zed common").data["count"], 0)  # every word must match
        self.assertEqual(self.admin.get("/api/students/?q=s125@aec").data["count"], 1)

    def test_search_respects_counsellor_scope(self):
        counsellor = self.as_user("coun@aec.test")
        self.assertEqual(counsellor.get("/api/students/").data["count"], 65)
        self.assertEqual(counsellor.get("/api/students/?q=pupil125").data["count"], 1)  # odd: assigned
        self.assertEqual(counsellor.get("/api/students/?q=pupil124").data["count"], 0)  # even: not theirs
        self.assertEqual(self.as_user("admin@aec.test").get("/api/students/?q=pupil124").data["count"], 1)
