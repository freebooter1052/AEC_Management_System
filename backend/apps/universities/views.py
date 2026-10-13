"""
University & course search (SRS 4.4) - read-only skeleton for this sprint.

University documents come from the dataset already loaded into CouchDB
(`manage.py load_universities` can (re)load it):

    {"_id": "university_001", "type": "university", "name": "Aarhus University",
     "country": "Denmark", "rank": 85, "created_at": "..."}

Course documents (`type: "course"`, linked by `university_id`) are planned for
the next sprint; the courses endpoint already serves them if present.
"""

from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import repository


class UniversityListView(APIView):
    """GET /api/universities/?q=&country=&max_rank=&sort=rank|name&page=&page_size="""

    def get(self, request):
        params = request.query_params
        selector = {"type": "university"}
        if params.get("country"):
            selector["country"] = params["country"]
        if params.get("q", "").strip():
            selector["name"] = {"$regex": repository.contains_pattern(params["q"])}
        try:
            max_rank = int(params.get("max_rank", ""))
        except ValueError:
            max_rank = None

        if params.get("sort") == "name":
            selector.setdefault("name", {"$gt": None})
            sort = [{"type": "asc"}, {"name": "asc"}]
        else:
            sort = [{"type": "asc"}, {"rank": "asc"}]
        selector["rank"] = {"$gt": None, **({"$lte": max_rank} if max_rank else {})}

        return Response(repository.paginate(request, selector, sort=sort, serialize=repository.public))


class UniversityCountriesView(APIView):
    """GET /api/universities/countries/ - distinct countries with university counts, for filters."""

    def get(self, request):
        counts: dict[str, int] = {}
        for doc in repository.find({"type": "university"}, fields=["country"]):
            country = doc.get("country")
            if country:
                counts[country] = counts.get(country, 0) + 1
        return Response([{"country": c, "count": counts[c]} for c in sorted(counts)])


class UniversityDetailView(APIView):
    """GET /api/universities/<id>/ - one university plus any course documents linked to it."""

    def get(self, request, university_id):
        doc = repository.get(university_id, "university")
        if doc is None:
            raise NotFound("University not found.")
        data = repository.public(doc)
        data["courses"] = [repository.public(c) for c in repository.find({"type": "course", "university_id": university_id})]
        return Response(data)
