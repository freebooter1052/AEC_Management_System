"""SOP and LOR writing (apps/writing): consent, guided drafts with a fake Gemini, sharing, referees."""

import json
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.core import repository
from apps.writing import gemini

from .base import WorkflowTestCase

ANSWERS = {"motivation": "Built a line-following robot in second year.", "why_course": "Robotics modules on control.",
           "goals": "Work on warehouse automation."}


class FakeGemini:
    def __init__(self, text="Dear committee, this is a draft.", error=None):
        self.text, self.error, self.calls = text, error, []

    def generate(self, *, system, prompt, json_output=False, temperature=0.7):
        self.calls.append({"system": system, "prompt": prompt, "json_output": json_output})
        if self.error:
            raise self.error
        return gemini.Result(text=self.text, model="fake-model", usage={"prompt": 10, "output": 20, "total": 30})


class WritingTestCase(WorkflowTestCase):
    def setUp(self):
        super().setUp()
        self.ai = FakeGemini()
        gemini.set_client(self.ai)

    def tearDown(self):
        gemini.set_client(None)
        super().tearDown()

    def consent(self, granted=True):
        res = self.student.put("/api/writing/consent/", {"granted": granted}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        return res.data

    def new_sop(self, client=None, **extra):
        return (client or self.coun_a).post("/api/writing/statements/", {"student_id": self.student_id, **extra}, format="json")

    def sop(self, answers=ANSWERS):
        res = self.new_sop()
        self.assertEqual(res.status_code, 201, res.data)
        if answers:
            res = self.coun_a.patch(f"/api/writing/statements/{res.data['id']}/", {"answers": answers}, format="json")
            self.assertEqual(res.status_code, 200, res.data)
        return res.data

    def act(self, statement_id, action, body=None, client=None):
        return (client or self.coun_a).post(f"/api/writing/statements/{statement_id}/{action}/", body or {}, format="json")


class ConsentTests(WritingTestCase):
    def test_student_controls_consent(self):
        self.assertFalse(self.student.get("/api/writing/consent/").data["granted"])
        self.assertTrue(self.consent()["granted"])
        withdrawn = self.consent(False)
        self.assertFalse(withdrawn["granted"])
        self.assertIsNotNone(withdrawn["withdrawn_at"])
        self.assertEqual(self.coun_a.put("/api/writing/consent/", {"granted": True}, format="json").status_code, 403)

    def test_profile_update_cannot_set_consent(self):
        self.student.patch("/api/students/me/", {"ai_consent": {"granted": True}}, format="json")
        self.assertNotIn("ai_consent", repository.get(self.student_id))

    def test_counsellor_asks_once_a_day(self):
        first = self.coun_a.post("/api/writing/consent/request/", {"student_id": self.student_id}, format="json")
        self.assertTrue(first.data["sent"])
        self.assertFalse(self.coun_a.post("/api/writing/consent/request/", {"student_id": self.student_id}, format="json").data["sent"])
        notes = self.student.get("/api/notifications/", {"category": "writing"}).data["results"]
        self.assertEqual(len(notes), 1)
        self.assertEqual(self.coun_b.post("/api/writing/consent/request/", {"student_id": self.student_id},
                                          format="json").status_code, 403)

    def test_ai_needs_consent(self):
        st = self.sop()
        res = self.act(st["id"], "generate")
        self.assertEqual(res.status_code, 403)
        self.assertIn("agreed", res.data["detail"])
        self.assertEqual(self.ai.calls, [])


class StatementTests(WritingTestCase):
    def setUp(self):
        super().setUp()
        self.consent()

    def test_only_the_students_counsellor_writes(self):
        self.assertEqual(self.new_sop().status_code, 201)
        self.assertEqual(self.new_sop(self.coun_b).status_code, 403)
        self.assertEqual(self.new_sop(self.student).status_code, 403)
        self.assertEqual(self.new_sop(self.admin).status_code, 403)

    def test_title_from_application(self):
        app = self.apply().data
        res = self.new_sop(application_id=app["id"])
        self.assertEqual(res.data["title"], "SOP - Robotics at Technical University of Munich")
        self.assertEqual(self.new_sop(application_id="application_nope").status_code, 400)

    def test_generate_draft_from_answers(self):
        st = self.sop(answers={"motivation": "Robots."})
        self.assertEqual(self.act(st["id"], "generate").status_code, 400)  # why_course and goals are required
        st = self.sop()
        res = self.act(st["id"], "generate")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["content"], self.ai.text)
        self.assertTrue(res.data["ai_assisted"])
        self.assertEqual([v["source"] for v in res.data["versions"]], ["ai_draft"])
        prompt = self.ai.calls[0]["prompt"]
        self.assertIn("line-following robot", prompt)
        self.assertIn("First name: Asha", prompt)
        self.assertNotIn("stu@aec.test", prompt)  # contact details never leave the system
        audit = repository.find({"type": "audit_log", "action": "writing.ai_draft"})
        self.assertEqual(audit[0]["details"]["tokens"]["total"], 30)
        self.assertNotIn("line-following", json.dumps(audit[0]))

    def test_revise_restore_and_manual_versions(self):
        st = self.sop()
        self.act(st["id"], "generate")
        self.ai.text = "A shorter draft."
        res = self.act(st["id"], "revise", {"instruction": "Make it more concise"})
        self.assertEqual(res.data["content"], "A shorter draft.")
        self.assertEqual(res.data["versions"][-1]["note"], "Make it more concise")
        res = self.coun_a.patch(f"/api/writing/statements/{st['id']}/", {"content": "Hand edited text."}, format="json")
        self.assertEqual([v["source"] for v in res.data["versions"]], ["ai_draft", "ai_revise", "manual"])
        res = self.act(st["id"], "restore", {"version": 1})
        self.assertEqual(res.data["content"], "Dear committee, this is a draft.")
        self.assertEqual(len(res.data["versions"]), 4)

    def test_review_returns_structured_feedback(self):
        st = self.sop()
        self.coun_a.patch(f"/api/writing/statements/{st['id']}/", {"content": "word " * 80}, format="json")
        self.ai.text = json.dumps({"summary": "Solid start.", "strengths": ["Clear goals"],
                                   "improvements": ["Add a project"], "missing": ["Thesis title"]})
        res = self.act(st["id"], "review")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["feedback"]["improvements"], ["Add a project"])
        self.assertTrue(self.ai.calls[-1]["json_output"])
        self.assertEqual(res.data["content"], "word " * 80)  # a review never changes the text

    def test_gemini_failures_are_friendly(self):
        st = self.sop()
        self.ai.error = gemini.AssistantUnavailable()
        res = self.act(st["id"], "generate")
        self.assertEqual(res.status_code, 503)
        self.assertIn("writing assistant", res.data["detail"])
        self.ai.error = gemini.AssistantRefused()
        self.assertEqual(self.act(st["id"], "generate").status_code, 422)
        self.assertEqual(repository.get(st["id"])["versions"], [])

    @override_settings(GEMINI_API_KEY="")
    def test_no_key_switches_ai_off(self):
        gemini.set_client(None)
        st = self.sop()
        self.assertFalse(self.coun_a.get("/api/writing/", {"student_id": self.student_id}).data["ai_available"])
        res = self.act(st["id"], "generate")
        self.assertEqual(res.status_code, 503)
        self.assertIn("Gemini API key", res.data["detail"])
        # writing by hand still works
        ok = self.coun_a.patch(f"/api/writing/statements/{st['id']}/", {"content": "By hand."}, format="json")
        self.assertEqual(ok.status_code, 200)

    def test_sharing_comments_and_student_view(self):
        st = self.sop()
        self.act(st["id"], "generate")
        self.assertEqual(self.student.get(f"/api/writing/statements/{st['id']}/").status_code, 403)
        self.assertEqual(self.student.get("/api/writing/").data["statements"], [])
        self.assertEqual(self.act(st["id"], "status", {"status": "Shared"}).status_code, 200)

        seen = self.student.get(f"/api/writing/statements/{st['id']}/")
        self.assertEqual(seen.status_code, 200)
        self.assertNotIn("versions", seen.data)
        self.assertNotIn("answers", seen.data)
        self.assertEqual(len(self.student.get("/api/writing/").data["statements"]), 1)
        self.assertEqual(self.student.patch(f"/api/writing/statements/{st['id']}/", {"content": "x"}, format="json").status_code, 403)

        res = self.act(st["id"], "comments", {"text": "Please mention my internship."}, client=self.student)
        self.assertEqual(res.data["comments"][0]["by_name"], "Asha Nair")
        coun_notes = self.coun_a.get("/api/notifications/", {"category": "writing"}).data["results"]
        self.assertEqual(coun_notes[0]["title"], "Asha Nair commented on their SOP")
        stu_notes = self.student.get("/api/notifications/", {"category": "writing"}).data["results"]
        self.assertEqual(stu_notes[0]["link"], f"/writing/statements/{st['id']}/")

        self.assertEqual(self.act(st["id"], "status", {"status": "Final"}).status_code, 200)
        locked = self.coun_a.patch(f"/api/writing/statements/{st['id']}/", {"content": "x"}, format="json")
        self.assertEqual(locked.status_code, 400)

    def test_other_counsellor_and_admin(self):
        st = self.sop()
        self.assertEqual(self.coun_b.get(f"/api/writing/statements/{st['id']}/").status_code, 403)
        self.assertEqual(self.admin.get(f"/api/writing/statements/{st['id']}/").status_code, 200)
        self.assertEqual(self.admin.patch(f"/api/writing/statements/{st['id']}/", {"title": "x"}, format="json").status_code, 403)
        self.assertEqual(self.coun_b.get("/api/writing/", {"student_id": self.student_id}).status_code, 403)

    def test_empty_draft_cannot_be_shared(self):
        st = self.sop()
        self.assertEqual(self.act(st["id"], "status", {"status": "Shared"}).status_code, 400)


class ReferenceTests(WritingTestCase):
    REFEREE = {"name": "Dr. Priya Rao", "title": "Professor", "relationship": "Project supervisor"}

    def setUp(self):
        super().setUp()
        self.consent()

    def add(self, **extra):
        res = self.coun_a.post("/api/writing/references/", {"student_id": self.student_id, "referee": self.REFEREE,
                                                             "highlights": "Led the robotics project.", **extra}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def test_referee_claims_the_checklist_lor(self):
        app = self.apply().data
        for s in ("Shortlisted", "Documents Pending"):
            self.coun_a.post(f"/api/applications/{app['id']}/status/", {"status": s}, format="json")
        lor = repository.find({"type": "document", "document_type": "LOR", "application_id": app["id"]})
        self.assertEqual(len(lor), 1)
        ref = self.add(application_id=app["id"])
        self.assertEqual(ref["document_id"], lor[0]["_id"])
        self.assertEqual(repository.get(lor[0]["_id"])["title"], "LOR - Dr. Priya Rao")
        second = self.add(application_id=app["id"])  # a second referee gets their own letter slot
        self.assertNotEqual(second["document_id"], ref["document_id"])

    def test_stage_follows_the_letter(self):
        ref = self.add()
        self.assertEqual(ref["stage"], "Planned")
        res = self.coun_a.patch(f"/api/writing/references/{ref['id']}/", {"status": "Requested"}, format="json")
        self.assertEqual(res.data["stage"], "Requested")
        self.student.post(f"/api/documents/{ref['document_id']}/upload/",
                          {"file": SimpleUploadedFile("lor.pdf", b"%PDF-1.4 lor", content_type="application/pdf")},
                          format="multipart")
        self.assertEqual(self.coun_a.get(f"/api/writing/references/{ref['id']}/").data["stage"], "Received")
        self.coun_a.post(f"/api/documents/{ref['document_id']}/verify/", {"status": "Verified"}, format="json")
        self.assertEqual(self.student.get("/api/writing/").data["references"][0]["stage"], "Verified")

    def test_cancel_removes_an_empty_letter_slot(self):
        ref = self.add()
        res = self.coun_a.patch(f"/api/writing/references/{ref['id']}/", {"status": "Cancelled"}, format="json")
        self.assertEqual(res.data["stage"], "Cancelled")
        self.assertIsNone(repository.get(ref["document_id"]))
        again = self.coun_a.patch(f"/api/writing/references/{ref['id']}/", {"status": "Planned"}, format="json")
        self.assertEqual(again.status_code, 400)

    def test_brief_and_admin_controlled_drafts(self):
        ref = self.add()
        self.ai.text = "Dear Dr. Rao, thank you for agreeing..."
        res = self.coun_a.post(f"/api/writing/references/{ref['id']}/prepare/", {"kind": "lor_brief"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["kind"], "lor_brief")
        self.assertIn("Led the robotics project.", self.ai.calls[-1]["prompt"])
        again = self.coun_a.post(f"/api/writing/references/{ref['id']}/prepare/", {"kind": "lor_brief"}, format="json")
        self.assertEqual(again.data["id"], res.data["id"])  # regenerating adds a version, not a second brief
        self.assertEqual(len(again.data["versions"]), 2)
        self.assertEqual(self.student.get(f"/api/writing/statements/{res.data['id']}/").status_code, 403)

        draft = lambda: self.coun_a.post(f"/api/writing/references/{ref['id']}/prepare/", {"kind": "lor_draft"}, format="json")
        self.assertEqual(draft().status_code, 403)
        self.assertEqual(self.coun_a.patch("/api/writing/settings/", {"allow_lor_drafts": True}, format="json").status_code, 403)
        self.assertTrue(self.admin.patch("/api/writing/settings/", {"allow_lor_drafts": True}, format="json").data["allow_lor_drafts"])
        self.assertEqual(draft().status_code, 200)

    def test_student_deletion_removes_writing_records(self):
        ref = self.add()
        st = self.coun_a.post("/api/writing/statements/", {"student_id": self.student_id}, format="json").data
        self.assertEqual(self.admin.delete(f"/api/students/{self.student_id}/").status_code, 204)
        self.assertIsNone(repository.get(ref["id"]))
        self.assertIsNone(repository.get(st["id"]))


class GeminiClientTests(WritingTestCase):
    def test_parse_response(self):
        ok = gemini.parse_response({"candidates": [{"content": {"parts": [{"text": "thinking", "thought": True},
                                                                          {"text": " Hello "}]}}],
                                    "usageMetadata": {"totalTokenCount": 5}}, "m")
        self.assertEqual(ok.text, "Hello")
        self.assertEqual(ok.usage["total"], 5)
        with self.assertRaises(gemini.AssistantRefused):
            gemini.parse_response({"promptFeedback": {"blockReason": "SAFETY"}}, "m")
        with self.assertRaises(gemini.AssistantRefused):
            gemini.parse_response({"candidates": [{"finishReason": "SAFETY"}]}, "m")
        with self.assertRaises(gemini.AssistantUnavailable):
            gemini.parse_response({}, "m")

    def test_key_is_sent_in_a_header_not_the_url(self):
        body = json.dumps({"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}).encode()
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = body
        with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
            result = gemini.GeminiClient("secret-key", "gemini-test").generate(system="s", prompt="p")
        request = urlopen.call_args[0][0]
        self.assertEqual(result.text, "ok")
        self.assertNotIn("secret-key", request.full_url)
        self.assertEqual(request.get_header("X-goog-api-key"), "secret-key")
        self.assertIn("gemini-test:generateContent", request.full_url)
