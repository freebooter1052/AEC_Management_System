"""Counsellor CRUD, student <-> counsellor assignment, admin student CRUD, dashboards."""

from apps.accounts import users

from .base import PASSWORD, APITestCase


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


class RosterAccuracyTests(APITestCase):
    """Dashboards and rosters show real names and counts, whatever state the denormalised fields are in."""

    def setUp(self):
        super().setUp()
        self.admin = self.as_user("admin@aec.test")
        self.counsellor = self.create_counsellor(self.admin)
        self.register()
        self.student_id = users.get_by_email("stu@aec.test")["profile_id"]
        self.admin.post(f"/api/students/{self.student_id}/assign-counsellor/",
                        {"counsellor_id": self.counsellor["id"]}, format="json")

    def test_roster_shows_counsellor_name_even_when_inactive(self):
        self.admin.patch(f"/api/counsellors/{self.counsellor['id']}/", {"is_active": False}, format="json")
        row = self.admin.get("/api/students/").data["results"][0]
        self.assertEqual(row["counsellor_name"], "Marcus Chen")

    def test_workload_is_counted_from_students(self):
        doc = self.db.get(self.counsellor["id"])
        doc["assigned_student_ids"] = []  # stale denormalised copy
        self.db.save(doc)
        self.assertEqual(self.admin.get("/api/counsellors/").data["results"][0]["workload"]["assigned"], 1)
        self.assertEqual(self.admin.get("/api/dashboard/").data["counsellor_workload"][0]["assigned"], 1)
        self.assertEqual(self.as_user("coun@aec.test").get("/api/dashboard/").data["workload"]["assigned"], 1)
