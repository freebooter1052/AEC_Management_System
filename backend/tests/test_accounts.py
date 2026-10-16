"""Registration, login, tokens and account administration."""

import re
from datetime import datetime, timedelta, timezone

from django.core import mail
from django.test import override_settings

from apps.accounts import users
from apps.core import repository

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

    def test_change_password_keeps_the_new_session_and_validates(self):
        self.register()
        client = self.as_user("stu@aec.test")
        url = "/api/auth/change-password/"

        wrong = client.post(url, {"current_password": "Wrong999", "new_password": "NewSecret456"}, format="json")
        self.assertEqual(wrong.status_code, 400)
        self.assertIn("current_password", wrong.data)
        weak = client.post(url, {"current_password": PASSWORD, "new_password": "short"}, format="json")
        self.assertIn("new_password", weak.data)
        letters = client.post(url, {"current_password": PASSWORD, "new_password": "onlyletters"}, format="json")
        self.assertIn("new_password", letters.data)
        same = client.post(url, {"current_password": PASSWORD, "new_password": PASSWORD}, format="json")
        self.assertIn("new_password", same.data)
        self.assertEqual(client.post(url, {}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"current_password": PASSWORD, "new_password": "NewSecret456"},
                                          format="json").status_code, 401)  # signed out
        self.assertEqual(self.login("stu@aec.test").status_code, 200)  # nothing changed so far

        res = client.post(url, {"current_password": PASSWORD, "new_password": "NewSecret456"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("password_hash", res.data["user"])
        client.credentials(HTTP_AUTHORIZATION="Bearer " + res.data["token"])
        self.assertEqual(client.get("/api/auth/me/").status_code, 200)  # the returned token keeps the user signed in

    def test_change_password_only_affects_the_signed_in_user(self):
        self.register()
        self.register(email="other@aec.test")
        client = self.as_user("stu@aec.test")
        other_id = users.get_by_email("other@aec.test")["_id"]
        res = client.post("/api/auth/change-password/", {"current_password": PASSWORD, "new_password": "NewSecret456",
                                                         "user_id": other_id, "email": "other@aec.test"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.login("other@aec.test").status_code, 200)  # untouched
        self.assertEqual(self.login("other@aec.test", "NewSecret456").status_code, 401)
        self.assertEqual(self.login("stu@aec.test", "NewSecret456").status_code, 200)

    def test_register_requires_privacy_acknowledgement(self):
        res = self.register(privacy_acknowledged=False)
        self.assertEqual(res.status_code, 400)
        self.assertIn("privacy_acknowledged", res.data)
        body = {"first_name": "A", "last_name": "B", "email": "x@aec.test", "password": PASSWORD}
        self.assertIn("privacy_acknowledged", self.client.post("/api/auth/register/", body, format="json").data)
        self.assertIsNone(users.get_by_email("x@aec.test"))

        res = self.register(citizenship="usa")
        self.assertEqual(res.status_code, 201, res.data)
        user = self.db.get(res.data["user"]["id"])
        self.assertTrue(user["privacy_acknowledged_at"])
        self.assertEqual(self.db.get(user["profile_id"])["personal"]["citizenship"], "United States")
        self.assertIn("citizenship", self.register(email="y@aec.test", citizenship="Atlantis").data)

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


class ForgotPasswordTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.register()  # stu@aec.test
        mail.outbox.clear()

    def forgot(self, email="stu@aec.test"):
        return self.client.post("/api/auth/forgot-password/", {"email": email}, format="json")

    def sent_code(self):
        self.assertEqual(len(mail.outbox), 1)
        return re.search(r"code is: (\d{6})", mail.outbox[0].body).group(1)

    def verify(self, code, email="stu@aec.test"):
        return self.client.post("/api/auth/verify-reset-code/", {"email": email, "code": code}, format="json")

    def reset(self, code, password="Brand-new1", email="stu@aec.test"):
        return self.client.post("/api/auth/reset-password/",
                                {"email": email, "code": code, "new_password": password}, format="json")

    def test_full_flow_changes_password_and_revokes_sessions(self):
        old_client = self.as_user("stu@aec.test")
        self.assertEqual(self.forgot().status_code, 200)
        code = self.sent_code()
        self.assertEqual(mail.outbox[0].to, ["stu@aec.test"])
        self.assertEqual(self.verify(code).status_code, 200)
        self.assertEqual(self.reset(code).status_code, 200)

        self.assertEqual(self.login("stu@aec.test").status_code, 401)  # old password no longer works
        self.assertEqual(self.login("stu@aec.test", "Brand-new1").status_code, 200)
        self.assertEqual(old_client.get("/api/auth/me/").status_code, 401)  # existing sessions revoked
        self.assertEqual(self.reset(code, "Another-pw2").status_code, 400)  # a code works once

    def test_code_is_never_stored_in_plain_text(self):
        self.forgot()
        code = self.sent_code()
        doc = repository.find_one({"type": "password_reset"})
        self.assertNotIn(code, str(doc))

    def test_same_answer_for_unknown_email_and_no_mail_sent(self):
        known = self.forgot()
        mail.outbox.clear()
        unknown = self.forgot("nobody@aec.test")
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(unknown.data, known.data)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(self.verify("123456", "nobody@aec.test").status_code, 400)

    def test_inactive_account_gets_no_code(self):
        user = users.get_by_email("stu@aec.test")
        user["is_active"] = False
        repository.save(user)
        self.assertEqual(self.forgot().status_code, 200)
        self.assertEqual(mail.outbox, [])

    def test_wrong_code_is_rejected_and_locks_after_five_attempts(self):
        self.forgot()
        code = self.sent_code()
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            self.assertEqual(self.verify(wrong).status_code, 400)
        self.assertEqual(self.verify(code).status_code, 400)  # even the right code is dead now
        self.assertEqual(self.reset(code).status_code, 400)
        self.assertEqual(self.login("stu@aec.test").status_code, 200)  # password untouched

    def test_expired_code_is_rejected(self):
        self.forgot()
        code = self.sent_code()
        doc = repository.find_one({"type": "password_reset"})
        doc["expires_at"] = repository.to_iso(datetime.now(timezone.utc) - timedelta(seconds=1))
        repository.save(doc)
        self.assertEqual(self.verify(code).status_code, 400)
        self.assertEqual(self.reset(code).status_code, 400)

    def test_cooldown_then_new_code_replaces_the_old_one(self):
        self.forgot()
        first = self.sent_code()
        mail.outbox.clear()
        self.forgot()  # inside the cooldown: same answer, no second email
        self.assertEqual(mail.outbox, [])

        with override_settings(PASSWORD_RESET_COOLDOWN=0):
            for _ in range(50):  # a fresh code differs from the old one (almost always); retry on the 1-in-a-million tie
                mail.outbox.clear()
                self.forgot()
                second = self.sent_code()
                if second != first:
                    break
        self.assertEqual(repository.count({"type": "password_reset"}), 1)  # one live code per user
        self.assertEqual(self.verify(first).status_code, 400)
        self.assertEqual(self.verify(second).status_code, 200)

    def test_new_password_must_be_strong_and_code_well_formed(self):
        self.forgot()
        code = self.sent_code()
        res = self.reset(code, "weak")
        self.assertEqual(res.status_code, 400)
        self.assertIn("new_password", res.data)
        self.assertEqual(self.login("stu@aec.test").status_code, 200)
        self.assertIn("code", self.verify("12ab").data)  # not 6 digits

    def test_works_for_counsellor_and_admin_accounts(self):
        admin = self.as_user("admin@aec.test")
        self.create_counsellor(admin)
        for email in ("coun@aec.test", "admin@aec.test"):
            mail.outbox.clear()
            self.forgot(email)
            self.assertEqual(self.reset(self.sent_code(), "Brand-new1", email).status_code, 200)
            self.assertEqual(self.login(email, "Brand-new1").status_code, 200)

    def test_mail_failure_does_not_change_the_response(self):
        with override_settings(MAILERS={"default": {"BACKEND": "tests.test_accounts.BrokenMailBackend"}}):
            self.assertEqual(self.forgot().status_code, 200)


from django.core.mail.backends.base import BaseEmailBackend  # noqa: E402


class BrokenMailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        raise OSError("SMTP down")
