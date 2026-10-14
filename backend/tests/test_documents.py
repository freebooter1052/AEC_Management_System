"""Documents (SRS 4.6): checklist, upload / reference, download, verification and access."""

from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.documents import services

from .base import WorkflowTestCase

PDF = b"%PDF-1.4 transcript"


def pdf(name="transcript.pdf", content=PDF):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


class DocumentTests(WorkflowTestCase):
    def setUp(self):
        super().setUp()
        res = self.student.post("/api/documents/checklist/", {}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.docs = {d["document_type"]: d for d in res.data["results"]}

    def upload(self, doc_id, file=None, client=None):
        return (client or self.student).post(f"/api/documents/{doc_id}/upload/", {"file": file or pdf()},
                                             format="multipart")

    def review(self, doc_id, status, remarks="", client=None):
        return (client or self.coun_a).post(f"/api/documents/{doc_id}/verify/", {"status": status, "remarks": remarks},
                                            format="json")

    def test_checklist_is_created_once(self):
        self.assertEqual(sorted(self.docs), sorted(services.CORE_DOCUMENTS))
        self.assertTrue(all(d["status"] == "Required" and d["needs_attention"] for d in self.docs.values()))
        again = self.coun_a.post("/api/documents/checklist/", {"student_id": self.student_id}, format="json")
        self.assertEqual((again.status_code, again.data["created"]), (200, 0))
        self.assertEqual(self.coun_b.post("/api/documents/checklist/", {"student_id": self.student_id},
                                          format="json").status_code, 403)

    def test_upload_download_and_file_checks(self):
        doc_id = self.docs["Transcript"]["id"]
        res = self.upload(doc_id, pdf("My Transcript (final).pdf"))
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data["status"], res.data["filename"], res.data["has_file"]),
                         ("Uploaded", "My Transcript _final.pdf", True))
        self.assertIsNotNone(res.data["uploaded_at"])
        self.assertNotIn("_attachments", res.data)

        for client in (self.student, self.coun_a, self.admin):
            got = client.get(f"/api/documents/{doc_id}/file/")
            self.assertEqual(got.status_code, 200)
            self.assertEqual(got.content, PDF)
            self.assertEqual(got["Content-Type"], "application/pdf")
            self.assertIn("attachment;", got["Content-Disposition"])
        self.assertEqual(self.coun_b.get(f"/api/documents/{doc_id}/file/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/documents/{doc_id}/file/").status_code, 401)
        self.assertEqual(self.student.get(f"/api/documents/{self.docs['Passport']['id']}/file/").status_code, 404)

        passport = self.docs["Passport"]["id"]
        self.assertEqual(self.upload(passport, pdf("passport.exe", b"MZ...")).status_code, 400)
        self.assertEqual(self.upload(passport, pdf("passport.pdf", b"\x89PNG not a pdf")).status_code, 400)
        self.assertEqual(self.upload(passport, pdf("passport.pdf", b"")).status_code, 400)
        with mock.patch.object(services, "MAX_UPLOAD_BYTES", 10):
            self.assertEqual(self.upload(passport).status_code, 400)
        no_file = self.student.post(f"/api/documents/{passport}/upload/", {}, format="json")
        self.assertEqual(no_file.status_code, 400)
        self.assertIn("file", no_file.data)

    def test_reference_upload(self):
        doc_id = self.docs["Resume/CV"]["id"]
        bad = self.student.post(f"/api/documents/{doc_id}/upload/", {"reference_url": "javascript:alert(1)"}, format="json")
        self.assertEqual(bad.status_code, 400)
        res = self.student.post(f"/api/documents/{doc_id}/upload/",
                                {"reference_url": "https://drive.example.org/files/cv-2026.pdf"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data["status"], res.data["filename"], res.data["has_file"]), ("Uploaded", "cv-2026.pdf", False))
        self.assertEqual(res.data["reference_url"], "https://drive.example.org/files/cv-2026.pdf")

    def test_verification_flow(self):
        doc_id = self.docs["Degree Certificate"]["id"]
        self.assertEqual(self.review(doc_id, "Verified").status_code, 400)  # nothing uploaded yet
        self.upload(doc_id)
        self.assertEqual(self.review(doc_id, "Verified", client=self.student).status_code, 403)
        self.assertEqual(self.review(doc_id, "Verified", client=self.coun_b).status_code, 403)
        self.assertEqual(self.review(doc_id, "Rejected").status_code, 400)  # remarks are required
        res = self.review(doc_id, "Under Review")
        self.assertEqual((res.status_code, res.data["awaiting_review"]), (200, True))
        res = self.review(doc_id, "Rejected", "Scan is illegible; upload a certified copy.")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data["verified_by_name"], res.data["remarks"]),
                         ("Counsellor A", "Scan is illegible; upload a certified copy."))

        res = self.upload(doc_id)  # the student replaces a rejected file
        self.assertEqual((res.data["status"], res.data["remarks"], res.data["verified_by"]), ("Uploaded", "", None))
        res = self.review(doc_id, "Verified", client=self.admin)
        self.assertEqual((res.data["status"], res.data["verified_by_name"]), ("Verified", "Admin"))
        # CouchDB drops attachments missing from a saved revision: the stub must survive every save.
        self.assertIn("file", self.db.docs[doc_id]["_attachments"])
        self.assertEqual(self.student.get(f"/api/documents/{doc_id}/file/").content, PDF)

        self.assertEqual(self.upload(doc_id).status_code, 400)  # a verified document is not replaced...
        self.assertEqual(self.review(doc_id, "Expired").status_code, 400)  # ...until it is marked Expired (with remarks)
        self.assertEqual(self.review(doc_id, "Expired", "Certified copies are valid for a year.").status_code, 200)
        self.assertEqual(self.upload(doc_id).status_code, 200)

        history = self.student.get(f"/api/documents/{doc_id}/").data["history"]
        self.assertEqual([h["status"] for h in history],
                         ["Required", "Uploaded", "Under Review", "Rejected", "Uploaded", "Verified", "Expired", "Uploaded"])
        self.assertEqual(history[3]["by_name"], "Counsellor A")

    def test_lists_filters_summary_and_delete(self):
        self.upload(self.docs["Transcript"]["id"])
        self.upload(self.docs["Passport"]["id"])
        self.review(self.docs["Passport"]["id"], "Verified")
        page = self.coun_a.get("/api/documents/?status=Uploaded,Under%20Review").data
        self.assertEqual([d["document_type"] for d in page["results"]], ["Transcript"])
        self.assertEqual(page["results"][0]["student_name"], "Asha Nair")
        self.assertEqual(self.student.get("/api/documents/?application_id=none").data["count"], 5)
        self.assertEqual(self.coun_b.get("/api/documents/").data["count"], 0)
        self.assertEqual(self.coun_b.get(f"/api/documents/?student_id={self.student_id}").status_code, 403)

        summary = self.student.get("/api/documents/summary/").data
        self.assertEqual((summary["total"], summary["needs_attention"], summary["awaiting_review"]), (5, 3, 1))
        self.assertEqual(summary["by_status"]["Verified"], 1)

        extra = self.student.post("/api/documents/", {"document_type": "LOR", "title": "LOR - Prof. Rao"}, format="json")
        self.assertEqual(extra.status_code, 201, extra.data)
        self.assertEqual(self.student.post("/api/documents/", {"document_type": "Selfie"}, format="json").status_code, 400)
        self.assertEqual(self.student.delete(f"/api/documents/{extra.data['id']}/").status_code, 403)
        self.assertEqual(self.coun_a.delete(f"/api/documents/{self.docs['Passport']['id']}/").status_code, 400)
        self.assertEqual(self.coun_a.delete(f"/api/documents/{extra.data['id']}/").status_code, 204)

    def test_application_documents_link_to_the_application(self):
        app = self.apply().data
        res = self.coun_a.post("/api/documents/", {"student_id": self.student_id, "document_type": "SOP",
                                                    "application_id": app["id"]}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["application_label"], "Robotics - Technical University of Munich")
        self.register(email="other@aec.test")
        other = self.as_user("other@aec.test")
        res = other.post("/api/documents/", {"document_type": "SOP", "application_id": app["id"]}, format="json")
        self.assertEqual(res.status_code, 400)  # not their application
