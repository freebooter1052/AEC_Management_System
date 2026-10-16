"""University search and the health check / database-outage behaviour."""

from apps.core.db import set_db

from .base import APITestCase
from .fake_couch import UnavailableCouchDB


class UniversityAndHealthTests(APITestCase):
    def setUp(self):
        super().setUp()
        for i, (name, country, rank) in enumerate(
                [("ETH Zurich", "Switzerland", 22), ("Harvard University", "US", 1), ("Heidelberg University", "Germany", 51)]):
            self.db.save({"_id": f"university_00{i}", "type": "university", "name": name, "country": country, "rank": rank})
        self.register()
        self.student = self.as_user("stu@aec.test")

    def test_search_filter_and_sort(self):
        self.assertEqual(self.client.get("/api/universities/").status_code, 401)
        res = self.student.get("/api/universities/")
        self.assertEqual([u["name"] for u in res.data["results"]][0], "Harvard University")
        self.assertEqual(self.student.get("/api/universities/?q=heidel").data["count"], 1)
        self.assertEqual(self.student.get("/api/universities/?country=US").data["count"], 1)
        self.assertEqual(self.student.get("/api/universities/?max_rank=30").data["count"], 2)
        page = self.student.get("/api/universities/?page=2&page_size=2").data
        self.assertEqual((page["count"], page["total_pages"], len(page["results"])), (3, 2, 1))
        countries = self.student.get("/api/universities/countries/").data
        self.assertEqual([c["country"] for c in countries], ["Germany", "Switzerland", "US"])

    def test_health_and_database_outage(self):
        self.assertEqual(self.client.get("/api/health/").data["status"], "ok")
        set_db(UnavailableCouchDB())
        self.assertEqual(self.client.get("/api/health/").status_code, 503)
        res = self.client.post("/api/auth/login/", {"email": "a@b.co", "password": "x"}, format="json")
        self.assertEqual(res.status_code, 503)
        self.assertNotIn("Connection", res.data["detail"])  # no implementation details leaked


class CourseSearchTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.db.save({"_id": "university_001", "type": "university", "name": "ETH Zurich", "country": "Switzerland", "rank": 22})
        self.db.save({"_id": "university_002", "type": "university", "name": "MIT", "country": "US", "rank": 1})
        for i, (uni, title, cluster) in enumerate([("university_001", "Robotics", "CS & AI"),
                                                   ("university_002", "Robotics Engineering", "Engineering"),
                                                   ("university_002", "Data Science", "CS & AI")]):
            self.db.save({"_id": f"course_000{i}", "type": "course", "university_id": uni, "title": title,
                          "canonical_name": title, "cluster": cluster, "created_at": f"2026-01-0{i + 1}T00:00:00Z"})
        self.register()
        self.student = self.as_user("stu@aec.test")

    def test_course_search(self):
        self.assertEqual(self.client.get("/api/universities/courses/").status_code, 401)
        res = self.student.get("/api/universities/courses/?q=robotics").data
        self.assertEqual(res["count"], 2)
        self.assertEqual(res["results"][0]["university"], {"id": "university_001", "name": "ETH Zurich",
                                                           "country": "Switzerland", "rank": 22})
        self.assertEqual(self.student.get("/api/universities/courses/?q=robotics&country=US").data["count"], 1)
        self.assertEqual(self.student.get("/api/universities/courses/?q=cs ai").data["count"], 2)  # matches the cluster
        self.assertEqual(self.student.get("/api/universities/courses/?q=zzz").data["count"], 0)
        self.assertEqual(self.student.get("/api/universities/courses/").data["count"], 3)


class PageRouteTests(APITestCase):
    def test_unknown_pages_load_the_app_with_404_and_favicon_redirects(self):
        from django.conf import settings
        if not (settings.FRONTEND_DIR / "dist" / "index.html").exists():
            self.skipTest("frontend not built")
        self.assertEqual(self.client.get("/dashboard/").status_code, 200)
        self.assertEqual(self.client.get("/no-such-page/").status_code, 404)
        self.assertEqual(self.client.get("/students/x/extra/").status_code, 404)
        self.assertEqual(self.client.get("/api/no-such-endpoint/").status_code, 404)
        self.assertEqual(self.client.get("/favicon.ico")["Location"], "/static/favicon.svg")
