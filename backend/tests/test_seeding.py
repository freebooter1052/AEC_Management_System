"""The SRS sample dataset (apps/core/seeding.py): shapes, links, and clean removal."""

import io

from django.core.management import CommandError, call_command

from apps.core import maintenance, seeding, vocab

from .base import APITestCase

CLUSTERS = sorted({a for s in seeding.STUDENTS for a in s["areas"]})


class SeedDatasetTests(APITestCase):
    def setUp(self):
        super().setUp()
        # Small catalogue: two universities per country, a course for every cluster at each.
        n = 0
        for country in seeding.COUNTRIES:
            for _ in range(2):
                n += 1
                uid = f"university_{n:03d}"
                self.db.save({"_id": uid, "type": "university", "name": f"Uni {n} {country}", "country": country, "rank": n})
                for k, cluster in enumerate(CLUSTERS):
                    self.db.save({"_id": f"course_{n:03d}_{k:02d}", "type": "course", "university_id": uid,
                                  "title": f"{cluster} programme {n}", "cluster": cluster})
        call_command("seed_dataset", stdout=io.StringIO())

    def docs(self, doc_type):
        return self.db.of_type(doc_type)

    def test_people_are_real_accounts(self):
        self.assertEqual(len(self.docs("counsellor")), len(seeding.COUNSELLORS))
        self.assertEqual(len(self.docs("student")), len(seeding.STUDENTS))
        res = self.login("ananya.iyer@students.example.org", seeding.DEFAULT_PASSWORD)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["user"]["role"], "student")
        res = self.login("priya.raman@counsellors.example.org", seeding.DEFAULT_PASSWORD)
        self.assertEqual(res.status_code, 200)

    def test_every_reference_resolves(self):
        ids = set(self.db.docs)
        for app in self.docs("application"):
            for key in ("student_id", "counsellor_id", "university_id", "course_id", "intake_id"):
                self.assertIn(app[key], ids, (key, app))
            self.assertIn(app["status"], vocab.APPLICATION_STATUSES)
            history = [self.db.get(h) for h in app["history_ids"]]
            self.assertIsNone(history[0]["old_status"])
            self.assertEqual(history[-1]["new_status"], app["status"])
            for prev, nxt in zip(history, history[1:]):
                self.assertEqual(nxt["old_status"], prev["new_status"])
                self.assertLessEqual(prev["timestamp"], nxt["timestamp"])
        for d in self.docs("document"):
            self.assertIn(d["document_type"], vocab.DOCUMENT_TYPES)
            self.assertIn(d["status"], vocab.DOCUMENT_STATUSES)
            self.assertIn(d["student_id"], ids)
            self.assertEqual(d["filename"] is None, d["status"] == "Required")
        for s in self.docs("counselling_session"):
            self.assertIn(s["status"], vocab.SESSION_STATUSES)
            self.assertIn(s["counsellor_id"], ids)
        for r in self.docs("recommendation"):
            self.assertIn(r["tier"], vocab.RECOMMENDATION_TIERS)
            self.assertIn(r["status"], vocab.RECOMMENDATION_STATUSES)
        for n in self.docs("notification"):
            self.assertIn(n["category"], vocab.NOTIFICATION_CATEGORIES)
            self.assertIn(n["recipient_user_id"], ids)

    def test_links_are_consistent(self):
        for student in self.docs("student"):
            apps = sorted(a["_id"] for a in self.docs("application") if a["student_id"] == student["_id"])
            self.assertEqual(sorted(student["application_ids"]), apps)
        for c in self.docs("counsellor"):
            mine = sorted(s["_id"] for s in self.docs("student") if s.get("counsellor_id") == c["_id"])
            self.assertEqual(sorted(c["assigned_student_ids"]), mine)
        self.assertEqual(sum(1 for s in self.docs("student") if not s.get("counsellor_id")), 2)
        self.assertTrue(all(d.get("source") == "seed" for t in ("country", "intake", "application", "document")
                            for d in self.docs(t)))

    def test_dashboards_show_seeded_data(self):
        admin = self.as_user("admin@aec.test").get("/api/dashboard/").data
        self.assertEqual(admin["totals"]["students"], len(seeding.STUDENTS))
        self.assertEqual(admin["totals"]["unassigned_students"], 2)
        row = self.as_user("admin@aec.test").get("/api/students/?counsellor_id=" + self.docs("counsellor")[0]["_id"]).data
        self.assertTrue(all(r["counsellor_name"] for r in row["results"]))

    def test_seed_is_separable(self):
        with self.assertRaises(CommandError):
            call_command("seed_dataset", stdout=io.StringIO())  # refuses to double-seed
        plan = maintenance.plan_purge(maintenance.all_docs())
        self.assertFalse([d for d in plan.delete if d.get("source") == "seed"])  # purge never touches seed
        self.assertTrue(seeding.remove_seed() > 0)
        self.assertEqual(seeding.existing_seed_ids(), set())
        self.assertEqual([u["email"] for u in self.docs("user")], ["admin@aec.test"])
        self.assertEqual(len(self.docs("university")), 2 * len(seeding.COUNTRIES))
