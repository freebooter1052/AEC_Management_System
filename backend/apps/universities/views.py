"""
University & course search (SRS 4.4) - read-only skeleton for this sprint.

University documents come from the dataset already loaded into CouchDB
(`manage.py load_universities` can (re)load it):

    {"_id": "university_001", "type": "university", "name": "Aarhus University",
     "country": "Denmark", "rank": 85, "created_at": "..."}

Course documents (`type: "course"`, linked by `university_id`) are searched by
`CourseListView` and listed per university by `UniversityDetailView`.
"""

from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import countries, repository


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


def _course_page(docs: list[dict]) -> list[dict]:
    """Courses plus the name, country and rank of their university (one batched lookup)."""
    ids = sorted({d.get("university_id") for d in docs if d.get("university_id")})
    unis = {u["_id"]: u for u in repository.find({"_id": {"$in": ids}}, fields=["_id", "name", "country", "rank"])} if ids else {}
    out = []
    for d in docs:
        u = unis.get(d.get("university_id"), {})
        out.append({**repository.public(d), "university": {"id": d.get("university_id"), "name": u.get("name", ""),
                                                          "country": u.get("country", ""), "rank": u.get("rank")}})
    return out


class CourseListView(APIView):
    """
    GET /api/universities/courses/?q=&country=&page=&page_size= - search the course catalogue.
    Every word of `q` must match the course title, its canonical name or its subject cluster.
    """

    def get(self, request):
        params = request.query_params
        selector = {"type": "course", "created_at": {"$gt": None}}
        words = params.get("q", "").split()[:5]
        if words:
            selector["$and"] = [{"$or": [
                {"title": {"$regex": repository.contains_pattern(w)}},
                {"canonical_name": {"$regex": repository.contains_pattern(w)}},
                {"cluster": {"$regex": repository.contains_pattern(w)}},
            ]} for w in words]
        if params.get("country"):
            ids = [u["_id"] for u in repository.find({"type": "university", "country": params["country"]}, fields=["_id"])]
            selector["university_id"] = {"$in": ids}
        return Response(repository.paginate(request, selector, sort=[{"type": "asc"}, {"created_at": "asc"}],
                                            serialize_page=_course_page))


class CountryListView(APIView):
    """GET /api/countries/ - the canonical country list used by every country picker (public: registration needs it)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(countries.options())
