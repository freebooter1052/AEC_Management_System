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
