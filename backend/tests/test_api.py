"""
End-to-end API tests for the foundation sprint, run against the in-memory
CouchDB stand-in:  python manage.py test tests
"""

import logging

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from authentication import users
from core import repository
from core.db import set_db
from core.roles import ADMIN

from .fake_couch import FakeCouchDB, UnavailableCouchDB

PASSWORD = "Secret123"


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class APITestCase(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        logging.disable(logging.CRITICAL)  # expected 401/403/503 paths would otherwise flood the output

    @classmethod
    def tearDownClass(cls):
        logging.disable(logging.NOTSET)
        super().tearDownClass()

    def setUp(self):
        self.db = FakeCouchDB()
        set_db(self.db)
        self.client = APIClient()
        admin = users.build_user(email="admin@aec.test", password=PASSWORD, role=ADMIN, full_name="Admin")
        repository.save(admin)

    def tearDown(self):
        set_db(None)

    # -- helpers -----------------------------------------------------------
    def login(self, email, password=PASSWORD, **extra):
        return self.client.post("/api/auth/login/", {"email": email, "password": password, **extra}, format="json")

    def as_user(self, email):
        res = self.login(email)
        self.assertEqual(res.status_code, 200, res.data)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['token']}")
        return client

    def register(self, email="stu@aec.test", **extra):
        body = {"first_name": "Asha", "last_name": "Nair", "email": email, "password": PASSWORD, **extra}
        return self.client.post("/api/auth/register/", body, format="json")

    def create_counsellor(self, admin, email="coun@aec.test", **extra):
        body = {"name": "Marcus Chen", "email": email, "password": PASSWORD, "max_students": 2, **extra}
        res = admin.post("/api/counsellors/", body, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        return res.data


class AuthTests(APITestCase):
    def test_register_creates_user_and_student_documents(self):
        res = self.register(dial_code="+91", phone="9876543210", citizenship="India")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["user"]["role"], "student")
        self.assertTrue(res.data["token"])

        user = self.db.get(res.data["user"]["id"])
        self.assertNotIn(PASSWORD, user["password_hash"])  # never stored in plain text
        student = self.db.get(user["profile_id"])
        self.assertEqual(student["type"], "student")
        self.assertEqual(student["user_id"], user["_id"])
        self.assertEqual(student["personal"]["phone"], {"dial_code": "+91", "number": "9876543210"})

    def test_register_rejects_duplicate_email_and_weak_password(self):
        self.register()
        self.assertEqual(self.register(email="STU@aec.test").status_code, 400)
        res = self.client.post("/api/auth/register/", {"first_name": "A", "last_name": "B",
                                                        "email": "x@aec.test", "password": "short"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("password", res.data)

    def test_login_identifies_role_and_logs_failures(self):
        self.register()
        res = self.login("stu@aec.test")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["user"]["role"], "student")

        self.assertEqual(self.login("stu@aec.test", "WrongPass1").status_code, 401)
        self.assertEqual(self.login("nobody@aec.test").status_code, 401)
        failures = [d for d in self.db.of_type("audit_log") if d["action"] == "auth.login_failed"]
        self.assertEqual(len(failures), 2)

    def test_login_with_wrong_portal_is_refused(self):
        self.register()
        res = self.login("stu@aec.test", role="admin")
        self.assertEqual(res.status_code, 403)

    def test_protected_endpoints_require_valid_token(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_logout_revokes_token(self):
        self.register()
        client = self.as_user("stu@aec.test")
        self.assertEqual(client.get("/api/auth/me/").status_code, 200)
        self.assertEqual(client.post("/api/auth/logout/").status_code, 204)
        self.assertEqual(client.get("/api/auth/me/").status_code, 401)

    def test_change_password(self):
        self.register()
        client = self.as_user("stu@aec.test")
        res = client.post("/api/auth/change-password/",
                          {"current_password": PASSWORD, "new_password": "NewSecret456"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(client.get("/api/auth/me/").status_code, 401)  # old token revoked
        self.assertEqual(self.login("stu@aec.test", "NewSecret456").status_code, 200)

    def test_admin_user_management(self):
        self.register()
        admin = self.as_user("admin@aec.test")
        res = admin.get("/api/auth/users/?role=student")
        self.assertEqual(res.data["count"], 1)
        user_id = res.data["results"][0]["id"]
        self.assertEqual(admin.patch(f"/api/auth/users/{user_id}/", {"is_active": False}, format="json").status_code, 200)
        self.assertEqual(self.login("stu@aec.test").status_code, 401)

        self.assertEqual(self.client.get("/api/auth/users/").status_code, 401)
        self.register(email="s2@aec.test")
        self.assertEqual(self.as_user("s2@aec.test").get("/api/auth/users/").status_code, 403)


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


class CounsellorAssignmentTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.as_user("admin@aec.test")
        self.counsellor = self.create_counsellor(self.admin)
        self.register()
        self.student_id = users.get_by_email("stu@aec.test")["profile_id"]

    def assign(self, counsellor_id, student_id=None):
        return self.admin.post(f"/api/students/{student_id or self.student_id}/assign-counsellor/",
                               {"counsellor_id": counsellor_id}, format="json")

    def test_full_sprint_flow(self):
        """Login -> role -> dashboard -> update profile -> admin assigns counsellor -> counsellor sees student."""
        student = self.as_user("stu@aec.test")
        self.assertEqual(student.get("/api/dashboard/").data["role"], "student")
        student.patch("/api/students/me/", {"academic": {"degree": "BSc"}}, format="json")

        res = self.assign(self.counsellor["id"])
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["counsellor"]["name"], "Marcus Chen")
        self.assertIn(self.student_id, self.db.get(self.counsellor["id"])["assigned_student_ids"])
        self.assertEqual(student.get("/api/students/me/counsellor/").data["counsellor"]["id"], self.counsellor["id"])

        counsellor = self.as_user("coun@aec.test")
        roster = counsellor.get("/api/students/").data
        self.assertEqual([r["id"] for r in roster["results"]], [self.student_id])
        res = counsellor.patch(f"/api/students/{self.student_id}/", {"academic": {"institution": "MIT"}}, format="json")
        self.assertEqual(res.status_code, 200)
        dash = counsellor.get("/api/dashboard/").data
        self.assertEqual(dash["workload"]["assigned"], 1)

    def test_counsellor_cannot_access_unassigned_student(self):
        counsellor = self.as_user("coun@aec.test")
        self.assertEqual(counsellor.get(f"/api/students/{self.student_id}/").status_code, 403)
        self.assertEqual(counsellor.get("/api/students/").data["count"], 0)
        self.assertEqual(counsellor.get("/api/counsellors/").status_code, 403)
        self.assertEqual(self.assign(None).status_code, 200)  # admin may unassign (no-op)

    def test_reassignment_updates_both_counsellors(self):
        other = self.create_counsellor(self.admin, email="c2@aec.test", name="Anika")
        self.assign(self.counsellor["id"])
        self.assign(other["id"])
        self.assertNotIn(self.student_id, self.db.get(self.counsellor["id"])["assigned_student_ids"])
        self.assertIn(self.student_id, self.db.get(other["id"])["assigned_student_ids"])
        actions = [d["action"] for d in self.db.of_type("audit_log")]
        self.assertEqual(actions.count("student.counsellor_assigned"), 2)

    def test_capacity_and_unknown_counsellor(self):
        self.assertEqual(self.assign("counsellor_missing").status_code, 400)
        for email in ("a@aec.test", "b@aec.test"):
            self.register(email=email)
            self.assertEqual(self.assign(self.counsellor["id"], users.get_by_email(email)["profile_id"]).status_code, 200)
        res = self.assign(self.counsellor["id"])
        self.assertEqual(res.status_code, 400)
        self.assertIn("capacity", str(res.data))

    def test_counsellor_crud(self):
        cid = self.counsellor["id"]
        counsellor = self.as_user("coun@aec.test")
        self.assertEqual(counsellor.get("/api/counsellors/me/").data["id"], cid)
        res = counsellor.patch("/api/counsellors/me/", {"specialization": "UK PG", "max_students": 99}, format="json")
        self.assertEqual(res.data["specialization"], "UK PG")
        self.assertEqual(res.data["max_students"], 2)  # counsellors cannot change their own capacity

        res = self.admin.patch(f"/api/counsellors/{cid}/", {"max_students": 10}, format="json")
        self.assertEqual(res.data["workload"]["capacity"], 10)
        self.assertEqual(self.admin.get("/api/counsellors/?q=marcus").data["count"], 1)

        self.assign(cid)
        self.assertEqual(self.admin.delete(f"/api/counsellors/{cid}/").status_code, 400)
        self.assign(None)
        self.assertEqual(self.admin.delete(f"/api/counsellors/{cid}/").status_code, 204)
        self.assertIsNone(users.get_by_email("coun@aec.test"))

    def test_admin_student_crud(self):
        res = self.admin.post("/api/students/", {
            "first_name": "Ravi", "last_name": "K", "email": "ravi@aec.test", "password": PASSWORD,
            "counsellor_id": self.counsellor["id"], "preferences": {"countries": ["UK"]},
        }, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        new_id = res.data["id"]
        self.assertEqual(res.data["counsellor"]["id"], self.counsellor["id"])
        self.assertEqual(self.login("ravi@aec.test").status_code, 200)

        self.assertEqual(self.admin.get("/api/students/?q=ravi").data["count"], 1)
        self.assertEqual(self.admin.get("/api/students/?unassigned=true").data["count"], 1)

        self.assertEqual(self.admin.delete(f"/api/students/{new_id}/").status_code, 204)
        self.assertIsNone(self.db.get(new_id))
        self.assertEqual(self.db.get(self.counsellor["id"])["assigned_student_ids"], [])
        self.assertEqual(self.login("ravi@aec.test").status_code, 401)

    def test_admin_dashboard(self):
        data = self.admin.get("/api/dashboard/").data
        self.assertEqual(data["totals"]["students"], 1)
        self.assertEqual(data["totals"]["unassigned_students"], 1)
        self.assertEqual(data["totals"]["counsellors"], 1)


class UniversityAndHealthTests(APITestCase):
    def setUp(self):
        super().setUp()
        for i, (name, country, rank) in enumerate(
                [("ETH Zurich", "Switzerland", 22), ("Harvard University", "US", 1), ("Heidelberg University", "Germany", 51)]):
            self.db.save({"_id": f"university_00{i}", "type": "university", "name": name, "country": country, "rank": rank})
        self.register()
        self.student = self.as_user("stu@aec.test")

    def test_search_filter_and_sort(self):
        self.assertEqual(self.client.get("/api/universities/").status_code, 401)
        res = self.student.get("/api/universities/")
        self.assertEqual([u["name"] for u in res.data["results"]][0], "Harvard University")
        self.assertEqual(self.student.get("/api/universities/?q=heidel").data["count"], 1)
        self.assertEqual(self.student.get("/api/universities/?country=US").data["count"], 1)
        self.assertEqual(self.student.get("/api/universities/?max_rank=30").data["count"], 2)
        page = self.student.get("/api/universities/?page=2&page_size=2").data
        self.assertEqual((page["count"], page["total_pages"], len(page["results"])), (3, 2, 1))
        countries = self.student.get("/api/universities/countries/").data
        self.assertEqual([c["country"] for c in countries], ["Germany", "Switzerland", "US"])

    def test_health_and_database_outage(self):
        self.assertEqual(self.client.get("/api/health/").data["status"], "ok")
        set_db(UnavailableCouchDB())
        self.assertEqual(self.client.get("/api/health/").status_code, 503)
        res = self.client.post("/api/auth/login/", {"email": "a@b.co", "password": "x"}, format="json")
        self.assertEqual(res.status_code, 503)
        self.assertNotIn("Connection", res.data["detail"])  # no implementation details leaked
