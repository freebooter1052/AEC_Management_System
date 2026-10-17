"""
Shared test base: every API test runs against the in-memory CouchDB stand-in
(tests/fake_couch.py), so no CouchDB server is needed.

    python manage.py test tests
"""

import logging
from datetime import timedelta

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts import users
from apps.core import repository
from apps.core.db import set_db
from apps.core.roles import ADMIN
from apps.recommendations import services as recommendation_services

from .fake_couch import FakeCouchDB

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
        recommendation_services._catalogue_cache.clear()  # per-process cache; every test has its own database
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
        body = {"first_name": "Asha", "last_name": "Nair", "email": email, "password": PASSWORD,
                "privacy_acknowledged": True, **extra}
        return self.client.post("/api/auth/register/", body, format="json")

    def create_counsellor(self, admin, email="coun@aec.test", **extra):
        body = {"name": "Marcus Chen", "email": email, "password": PASSWORD, "max_students": 2, **extra}
        res = admin.post("/api/counsellors/", body, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        return res.data


class WorkflowTestCase(APITestCase):
    """
    A catalogue (one university, two courses), an open and a closed intake, a student assigned to
    counsellor A, and counsellor B with no students - for the Sprint 2 workflow tests.
    """

    def setUp(self):
        super().setUp()
        day = self.day
        self.db.save({"_id": "university_001", "type": "university", "name": "Technical University of Munich",
                      "country": "Germany", "rank": 45})
        for cid, title in (("course_0001", "Robotics"), ("course_0002", "Data Science")):
            self.db.save({"_id": cid, "type": "course", "university_id": "university_001", "title": title,
                          "cluster": "CS & AI", "created_at": "2026-10-10T09:09:28Z"})
        self.db.save({"_id": "intake_open", "type": "intake", "name": "Fall Open", "season": "Fall", "year": 2099,
                      "application_deadline": day(60), "decision_by": day(120), "start_date": day(200)})
        self.db.save({"_id": "intake_closed", "type": "intake", "name": "Spring Closed", "season": "Spring",
                      "year": 2098, "application_deadline": day(-5), "decision_by": day(30), "start_date": day(90)})

        self.admin = self.as_user("admin@aec.test")
        self.counsellor_a = self.create_counsellor(self.admin, email="a@aec.test", name="Counsellor A")
        self.counsellor_b = self.create_counsellor(self.admin, email="b@aec.test", name="Counsellor B")
        self.register()
        self.student_id = users.get_by_email("stu@aec.test")["profile_id"]
        res = self.admin.post(f"/api/students/{self.student_id}/assign-counsellor/",
                              {"counsellor_id": self.counsellor_a["id"]}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.student = self.as_user("stu@aec.test")
        self.coun_a = self.as_user("a@aec.test")
        self.coun_b = self.as_user("b@aec.test")

    @staticmethod
    def day(offset: int) -> str:
        """ISO date `offset` days from today."""
        return (repository.today() + timedelta(days=offset)).isoformat()

    def apply(self, client=None, **extra):
        body = {"course_id": "course_0001", "intake_id": "intake_open", "student_id": self.student_id, **extra}
        return (client or self.student).post("/api/applications/", body, format="json")
