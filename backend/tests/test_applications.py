"""Applications (SRS 4.5): creation, deadlines, status workflow, history, access and intakes."""

from django.core.files.uploadedfile import SimpleUploadedFile

from .base import WorkflowTestCase

PDF = b"%PDF-1.4 test document"


class ApplicationTests(WorkflowTestCase):
    def advance(self, app_id, *statuses, client=None):
        res = None
        for s in statuses:
            res = (client or self.coun_a).post(f"/api/applications/{app_id}/status/", {"status": s}, format="json")
            self.assertEqual(res.status_code, 200, (s, res.data))
        return res.data

    def verify_all(self, documents):
        for d in documents:
            pdf = SimpleUploadedFile("letter.pdf", PDF, content_type="application/pdf")
            res = self.student.post(f"/api/documents/{d['id']}/upload/", {"file": pdf}, format="multipart")
            self.assertEqual(res.status_code, 200, res.data)
            res = self.coun_a.post(f"/api/documents/{d['id']}/verify/", {"status": "Verified"}, format="json")
            self.assertEqual(res.status_code, 200, res.data)

    def test_student_creates_application_from_course_and_intake(self):
        res = self.apply(tier="Target", notes="Dream school")
        self.assertEqual(res.status_code, 201, res.data)
        app = res.data
        self.assertEqual(app["status"], "Planned")
        self.assertEqual(app["deadline"], self.day(60))  # defaults to the intake deadline
        self.assertEqual(app["decision_expected"], self.day(120))
        self.assertEqual(app["university_id"], "university_001")
        self.assertEqual(app["snapshot"]["university_name"], "Technical University of Munich")
        self.assertEqual(app["snapshot"]["course_title"], "Robotics")
        self.assertEqual(app["snapshot"]["intake_name"], "Fall Open")
        self.assertEqual(app["student_name"], "Asha Nair")
        self.assertEqual(app["counsellor_name"], "Counsellor A")
        self.assertEqual(app["deadline_info"], {"date": self.day(60), "days_left": 60, "state": "open"})
        self.assertEqual(app["allowed_transitions"], ["Withdrawn"])  # students may only withdraw
        self.assertEqual(len(app["history"]), 1)
        self.assertIsNone(app["history"][0]["old_status"])
        self.assertEqual(app["history"][0]["changed_by_name"], "Asha Nair")
        self.assertEqual(self.db.get(self.student_id)["application_ids"], [app["id"]])
        self.assertTrue(app["intake"]["is_open"])

    def test_deadline_rules_and_duplicates(self):
        res = self.apply(intake_id="intake_closed")
        self.assertEqual(res.status_code, 400)
        self.assertIn("closed on", str(res.data["intake_id"]))
        # The university's own later deadline can still be used, if it falls before the programme starts.
        self.assertEqual(self.apply(intake_id="intake_closed", deadline=self.day(10)).status_code, 201)
        self.assertEqual(self.apply(intake_id="intake_closed", course_id="course_0002",
                                    deadline=self.day(95)).status_code, 400)
        self.assertEqual(self.apply(deadline=self.day(-1)).status_code, 400)

        self.assertEqual(self.apply().status_code, 201)
        dup = self.apply()
        self.assertEqual(dup.status_code, 400)
        self.assertIn("already has an application", str(dup.data["course_id"]))
        self.assertEqual(self.apply(course_id="course_404").status_code, 400)
        self.assertEqual(self.apply(intake_id="intake_404").status_code, 400)

    def test_full_workflow_with_document_gate_and_history(self):
        app = self.apply().data
        data = self.advance(app["id"], "Shortlisted", "Documents Pending")
        # Entering Documents Pending creates the SOP and LOR requirements for this application.
        app_docs = [d for d in data["documents"] if d["application_id"] == app["id"]]
        self.assertEqual(sorted(d["document_type"] for d in app_docs), ["LOR", "SOP"])
        self.assertTrue(all(d["status"] == "Required" for d in app_docs))
        self.assertEqual(len(data["submission_blockers"]), 2)

        blocked = self.coun_a.post(f"/api/applications/{app['id']}/status/", {"status": "Submitted"}, format="json")
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("SOP (Required)", str(blocked.data["status"]))

        self.verify_all(app_docs)
        data = self.advance(app["id"], "Submitted")
        self.assertIsNotNone(data["submitted_at"])
        self.assertEqual(data["deadline_info"]["state"], "submitted")
        data = self.advance(app["id"], "Under Review", "Offer Received", "Completed")
        self.assertTrue(data["is_terminal"])
        self.assertEqual(data["allowed_transitions"], [])

        res = self.coun_a.post(f"/api/applications/{app['id']}/status/", {"status": "Withdrawn"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("final status", str(res.data["status"]))

        history = self.student.get(f"/api/applications/{app['id']}/history/").data
        self.assertEqual([h["new_status"] for h in history],
                         ["Planned", "Shortlisted", "Documents Pending", "Submitted", "Under Review",
                          "Offer Received", "Completed"])
        for prev, nxt in zip(history, history[1:]):
            self.assertEqual(nxt["old_status"], prev["new_status"])
            self.assertLessEqual(prev["timestamp"], nxt["timestamp"])
        self.assertEqual(history[1]["changed_by_name"], "Counsellor A")
        self.assertEqual(history[1]["changed_by_role"], "counsellor")
        self.assertEqual(len(self.db.get(app["id"])["history_ids"]), 7)

    def test_transition_rules_and_conflicts(self):
        app = self.apply().data
        self.assertEqual(self.student.post(f"/api/applications/{app['id']}/status/", {"status": "Shortlisted"},
                                           format="json").status_code, 403)
        skip = self.coun_a.post(f"/api/applications/{app['id']}/status/", {"status": "Submitted"}, format="json")
        self.assertEqual(skip.status_code, 400)
        self.assertEqual(self.coun_a.post(f"/api/applications/{app['id']}/status/", {"status": "Bogus"},
                                          format="json").status_code, 400)
        stale = self.coun_a.post(f"/api/applications/{app['id']}/status/", {"status": "Shortlisted", "rev": "1-old"},
                                 format="json")
        self.assertEqual(stale.status_code, 409)
        self.advance(app["id"], "Shortlisted", "Planned")  # one step back is allowed for corrections
        res = self.student.post(f"/api/applications/{app['id']}/status/",
                                {"status": "Withdrawn", "remarks": "Accepted another offer"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["deadline_info"]["state"], "closed")
        self.assertEqual(res.data["history"][-1]["remarks"], "Accepted another offer")
        # A withdrawn application no longer blocks a fresh one for the same course and intake.
        self.assertEqual(self.apply().status_code, 201)

    def test_access_is_scoped_to_the_students_counsellor(self):
        app = self.apply().data
        url = f"/api/applications/{app['id']}/"
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.coun_b.get(url).status_code, 403)
        self.assertEqual(self.coun_b.post(url + "status/", {"status": "Shortlisted"}, format="json").status_code, 403)
        self.assertEqual(self.coun_b.get("/api/applications/").data["count"], 0)
        self.assertEqual(self.coun_b.get(f"/api/applications/?student_id={self.student_id}").status_code, 403)
        self.assertEqual(self.coun_a.get("/api/applications/").data["count"], 1)
        self.assertEqual(self.admin.get("/api/applications/").data["count"], 1)

        self.register(email="other@aec.test")
        other = self.as_user("other@aec.test")
        self.assertEqual(other.get(url).status_code, 403)
        self.assertEqual(other.get("/api/applications/").data["count"], 0)
        # Staff create on behalf of a student they can access only.
        self.assertEqual(self.apply(client=self.coun_b, course_id="course_0002").status_code, 403)
        self.assertEqual(self.apply(client=self.coun_a, course_id="course_0002").status_code, 201)
        self.assertEqual(self.coun_a.post("/api/applications/", {"course_id": "course_0001", "intake_id": "intake_open"},
                                          format="json").status_code, 400)  # staff must name the student

    def test_update_delete_list_and_summary(self):
        app = self.apply().data
        url = f"/api/applications/{app['id']}/"
        self.assertEqual(self.student.patch(url, {"notes": "x"}, format="json").status_code, 403)
        res = self.coun_a.patch(url, {"deadline": self.day(30), "tier": "Reach", "notes": "Portal opens soon",
                                      "rev": app["rev"]}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data["deadline"], res.data["tier"]), (self.day(30), "Reach"))
        self.assertEqual(self.coun_a.patch(url, {"deadline": self.day(300)}, format="json").status_code, 400)
        self.assertEqual(self.coun_a.patch(url, {"tier": "Safe", "rev": app["rev"]}, format="json").status_code, 409)

        second = self.apply(course_id="course_0002", deadline=self.day(5)).data
        page = self.student.get("/api/applications/?sort=deadline").data
        self.assertEqual([a["id"] for a in page["results"]], [second["id"], app["id"]])
        self.assertEqual(page["results"][0]["deadline_info"]["state"], "due_soon")
        self.assertEqual(self.student.get("/api/applications/?q=data").data["count"], 1)
        self.assertEqual(self.student.get("/api/applications/?status=Planned,Shortlisted").data["count"], 2)

        summary = self.student.get("/api/applications/summary/").data
        self.assertEqual((summary["total"], summary["open"], summary["due_soon"]), (2, 2, 1))
        self.assertEqual(summary["by_status"]["Planned"], 2)
        self.assertEqual(summary["upcoming_deadlines"][0]["id"], second["id"])

        self.advance(app["id"], "Shortlisted")
        self.assertEqual(self.student.delete(url).status_code, 400)  # only Planned can be deleted
        self.assertEqual(self.student.delete(f"/api/applications/{second['id']}/").status_code, 204)
        self.assertIsNone(self.db.get(second["id"]))
        self.assertFalse([h for h in self.db.of_type("application_history") if h["application_id"] == second["id"]])
        self.assertEqual(self.db.get(self.student_id)["application_ids"], [app["id"]])

    def test_deleting_a_student_removes_their_workflow_records(self):
        app = self.apply().data
        self.advance(app["id"], "Shortlisted", "Documents Pending")
        self.assertEqual(self.admin.delete(f"/api/students/{self.student_id}/").status_code, 204)
        for t in ("application", "application_history", "document"):
            self.assertEqual(self.db.of_type(t), [], t)


class IntakeTests(WorkflowTestCase):
    def test_list_and_admin_management(self):
        intakes = self.student.get("/api/intakes/").data
        self.assertEqual([(i["id"], i["is_open"]) for i in intakes], [("intake_closed", False), ("intake_open", True)])

        body = {"season": "Spring", "year": 2100, "application_deadline": self.day(100), "start_date": self.day(250)}
        self.assertEqual(self.coun_a.post("/api/intakes/", body, format="json").status_code, 403)
        res = self.admin.post("/api/intakes/", body, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual((res.data["id"], res.data["name"]), ("intake_spring_2100", "Spring 2100"))
        self.assertEqual(self.admin.post("/api/intakes/", body, format="json").status_code, 400)
        bad = {**body, "year": 2101, "application_deadline": self.day(300)}
        self.assertEqual(self.admin.post("/api/intakes/", bad, format="json").status_code, 400)

        res = self.admin.patch("/api/intakes/intake_spring_2100/", {"application_deadline": self.day(120)}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["application_deadline"], self.day(120))
        self.assertEqual(self.admin.patch("/api/intakes/intake_spring_2100/", {"start_date": self.day(50)},
                                          format="json").status_code, 400)
