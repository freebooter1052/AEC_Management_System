"""
The repository answers some selectors from views or primary-key lookups instead of Mango (see
apps/core/repository.py). These tests check that every such answer equals what Mango returns, and that
the view-backed admin dashboard equals a direct count over the stored documents.
"""

import io
from collections import Counter
from datetime import timedelta

from django.core.management import call_command

from apps.core import repository, seeding
from apps.core.couch_views import PRE_SUBMISSION

from .base import APITestCase
from .test_seeding import CLUSTERS


def mango(db, selector, **query):
    return list(db.find({"selector": selector, "limit": 100000, **query}))


class RoutingEquivalenceTests(APITestCase):
    def setUp(self):
        super().setUp()
        for i in range(30):
            self.db.save({"_id": f"document_{i:03d}", "type": "document", "student_id": f"student_{i % 7}",
                          "application_id": None if i % 3 else f"application_{i % 5}", "status": ["Required", "Uploaded", "Verified"][i % 3],
                          "document_type": ["SOP", "LOR", "Passport"][i % 3], "created_at": f"2026-10-{1 + i % 28:02d}T00:00:00Z"})
        self.db.save({"_id": "document_nodate", "type": "document", "student_id": "student_1", "status": "Required"})
        self.db.save({"_id": "application_x", "type": "application", "student_id": "student_1", "status": "Planned"})

    def test_student_scoped_selectors_match_mango(self):
        ids = ["student_1", "student_3", "student_9"]
        cases = [
            ({"type": "document", "student_id": {"$in": ids}}, {}),
            ({"type": "document", "student_id": {"$in": ids}, "status": {"$in": ["Required", "Uploaded"]}}, {}),
            ({"type": "document", "student_id": {"$in": ids}, "application_id": None}, {}),
            ({"type": "document", "student_id": {"$in": ids}, "created_at": {"$gt": None}},
             {"sort": [{"type": "desc"}, {"created_at": "desc"}], "skip": 2, "limit": 4}),
            ({"type": "document", "student_id": {"$in": ids}}, {"fields": ["status"]}),
            ({"type": "document", "student_id": {"$in": ids}}, {"fields": ["_id", "student_id", "document_type"]}),
            ({"type": "document", "student_id": {"$in": []}}, {}),
        ]
        for selector, query in cases:
            expected = mango(self.db, selector, **query)
            got = repository.find(selector, fields=query.get("fields"), sort=query.get("sort"),
                                  limit=query.get("limit", 100000), skip=query.get("skip", 0))
            key = (lambda d: d.get("_id") or repr(d)) if not query.get("sort") else None
            if key:
                expected, got = sorted(expected, key=key), sorted(got, key=key)
            self.assertEqual([{k: v for k, v in d.items() if k != "_rev"} for d in got],
                             [{k: v for k, v in d.items() if k != "_rev"} for d in expected], selector)
            self.assertEqual(repository.count(selector), len(mango(self.db, selector)), selector)

    def test_id_lookups_match_mango(self):
        ids = ["document_001", "document_002", "missing", "application_x", "_design/x"]
        for selector in ({"_id": {"$in": ids}}, {"type": "document", "_id": {"$in": ids}}):
            self.assertEqual(sorted(d["_id"] for d in repository.find(selector)),
                             sorted(d["_id"] for d in mango(self.db, selector) if not d["_id"].startswith("_")))

    def test_fast_counts_match_mango(self):
        for selector in ({"type": "document"}, {"type": "document", "created_at": {"$gt": None}},
                         {"type": "document", "status": "Uploaded"}, {"type": "document", "status": {"$in": ["Uploaded", "Verified"]}},
                         {"type": "application"}, {"type": "nothing"}):
            self.assertEqual(repository.count(selector), len(mango(self.db, selector)), selector)
        # a document without created_at is counted in the type, but not by `created_at > null`
        self.assertEqual((repository.count({"type": "document"}), repository.count({"type": "document", "created_at": {"$gt": None}})),
                         (31, 30))


class ViewBackedDashboardTests(APITestCase):
    """The admin dashboard (reduce views) against direct counts over the SRS sample dataset."""

    def setUp(self):
        super().setUp()
        n = 0
        for country in seeding.COUNTRIES:
            for _ in range(2):  # the seeder spreads applications over at least two universities per country
                n += 1
                uid = f"university_{n:03d}"
                self.db.save({"_id": uid, "type": "university", "name": f"Uni {n}", "country": country, "rank": n})
                for k, cluster in enumerate(CLUSTERS):
                    self.db.save({"_id": f"course_{n:03d}_{k:02d}", "type": "course", "university_id": uid,
                                  "title": f"{cluster} {n}", "cluster": cluster})
        call_command("seed_dataset", stdout=io.StringIO())
        self.admin = self.as_user("admin@aec.test")

    def test_admin_figures_equal_direct_counts(self):
        d = self.admin.get("/api/dashboard/").data
        apps, docs = self.db.of_type("application"), self.db.of_type("document")
        today = repository.today()
        self.assertEqual({k: v for k, v in d["applications"]["by_status"].items() if v}, dict(Counter(a["status"] for a in apps)))
        self.assertEqual({k: v for k, v in d["documents"]["by_status"].items() if v}, dict(Counter(x["status"] for x in docs)))
        open_apps = [a for a in apps if a["status"] in PRE_SUBMISSION]
        days = [(repository.date.fromisoformat(a["deadline"]) - today).days for a in open_apps]
        self.assertEqual(d["applications"]["overdue"], sum(1 for x in days if x < 0))
        self.assertEqual(d["applications"]["due_soon"], sum(1 for x in days if 0 <= x <= 14))
        nearest = sorted(open_apps, key=lambda a: a["deadline"])[:5]
        self.assertEqual([a["deadline"] for a in d["applications"]["upcoming_deadlines"]], [a["deadline"] for a in nearest])
        pending = [s for s in self.db.of_type("counselling_session") if (s.get("follow_up") or {}).get("status") == "Pending"]
        self.assertEqual(d["follow_ups"]["pending"], len(pending))
        self.assertEqual(d["follow_ups"]["overdue"], sum(1 for s in pending if s["follow_up"]["due_date"] < today.isoformat()))
        by_country = Counter(a["snapshot"]["country"] for a in apps)
        self.assertEqual({r["name"]: r["applications"] for r in d["reports"]["by_country"]}, dict(by_country.most_common(10)))
        self.assertEqual(d["totals"]["students"], len(self.db.of_type("student")))
        self.assertEqual(d["totals"]["unassigned_students"], sum(1 for s in self.db.of_type("student") if not s.get("counsellor_id")))
        self.assertEqual(d["reports"]["recommendations"]["by_status"], dict(Counter(r["status"] for r in self.db.of_type("recommendation"))))
        counsellor = d["counsellor_workload"][0]
        mine = [s["_id"] for s in self.db.of_type("student") if s.get("counsellor_id") == counsellor["id"]]
        self.assertEqual(counsellor["assigned"], len(mine))
        self.assertEqual(counsellor["open_applications"],
                         sum(1 for a in apps if a["student_id"] in mine and a["status"] not in ("Rejected", "Withdrawn", "Completed")))
        self.assertEqual(counsellor["documents_to_review"],
                         sum(1 for x in docs if x["student_id"] in mine and x["status"] in ("Uploaded", "Under Review")))

    def test_filtered_figures_equal_direct_counts(self):
        apps = self.db.of_type("application")
        country = Counter(a["snapshot"]["country"] for a in apps).most_common(1)[0][0]
        d = self.admin.get(f"/api/dashboard/?country={country}").data
        self.assertEqual(d["applications"]["total"], sum(1 for a in apps if a["snapshot"]["country"] == country))
        intake = apps[0]["intake_id"]
        d = self.admin.get(f"/api/dashboard/?country={country}&intake_id={intake}").data
        self.assertEqual(d["applications"]["total"],
                         sum(1 for a in apps if a["snapshot"]["country"] == country and a["intake_id"] == intake))
        self.assertTrue(all(r["name"] == country for r in d["reports"]["by_country"]))
        coun = self.db.of_type("counsellor")[0]["_id"]
        mine = {s["_id"] for s in self.db.of_type("student") if s.get("counsellor_id") == coun}
        d = self.admin.get(f"/api/dashboard/?counsellor_id={coun}").data
        self.assertEqual(d["applications"]["total"], sum(1 for a in apps if a["student_id"] in mine))
        self.assertEqual(d["documents"]["total"], sum(1 for x in self.db.of_type("document") if x["student_id"] in mine))
        self.assertEqual([w["id"] for w in d["counsellor_workload"]], [coun])

    def test_agency_summary_endpoints_equal_direct_counts(self):
        apps, docs = self.db.of_type("application"), self.db.of_type("document")
        s = self.admin.get("/api/applications/summary/").data
        self.assertEqual((s["total"], {k: v for k, v in s["by_status"].items() if v}), (len(apps), dict(Counter(a["status"] for a in apps))))
        self.assertEqual(s["open"], sum(1 for a in apps if a["status"] not in ("Rejected", "Withdrawn", "Completed")))
        self.assertEqual(len(s["upcoming_deadlines"]), 5)
        d = self.admin.get("/api/documents/summary/").data
        self.assertEqual((d["total"], d["needs_attention"], d["awaiting_review"]),
                         (len(docs), sum(1 for x in docs if x["status"] in ("Required", "Rejected", "Expired")),
                          sum(1 for x in docs if x["status"] in ("Uploaded", "Under Review"))))

    def test_full_reminder_sweep_uses_keyed_lookups(self):
        from apps.notifications import reminders
        counts = reminders.sweep(repository.today() + timedelta(days=0))
        self.assertGreater(counts["missing_document"], 0)
        self.assertEqual(reminders.sweep()["missing_document"], 0)  # same week: nothing new
