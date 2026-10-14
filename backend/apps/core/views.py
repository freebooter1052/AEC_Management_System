from django.conf import settings
from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .db import get_db


def frontend_app(request, **kwargs):
    """Serve the built React app (frontend/dist/index.html); React Router renders the page for the URL."""
    try:
        html = (settings.FRONTEND_DIR / "dist" / "index.html").read_text(encoding="utf-8")
    except FileNotFoundError:
        return HttpResponse("The frontend has not been built. Run `npm install` and `npm run build` in frontend/.",
                            status=503, content_type="text/plain")
    response = HttpResponse(html)
    response["Cache-Control"] = "no-cache"  # always revalidate, so a new build is picked up straight away
    return response


class HealthView(APIView):
    """GET /api/health/ - is the API up and can it reach CouchDB? (public)"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        try:
            info = get_db().info()
            return Response({"status": "ok", "database": info.get("db_name"), "documents": info.get("doc_count")})
        except Exception:  # noqa: BLE001
            return Response({"status": "degraded", "database": None}, status=503)
