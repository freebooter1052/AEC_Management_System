"""
Shared test base: every API test runs against the in-memory CouchDB stand-in
(tests/fake_couch.py), so no CouchDB server is needed.

    python manage.py test tests
"""

import logging

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts import users
from apps.core import repository
from apps.core.db import set_db
from apps.core.roles import ADMIN

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
