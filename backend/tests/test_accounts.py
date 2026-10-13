"""Registration, login, tokens and account administration."""

from apps.accounts import users

from .base import PASSWORD, APITestCase


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
