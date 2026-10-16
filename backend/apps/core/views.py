from django.conf import settings
from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .db import get_db


def frontend_app(request, status=200, **kwargs):
    """Serve the built React app (frontend/dist/index.html); React Router renders the page for the URL."""
    try:
        html = (settings.FRONTEND_DIR / "dist" / "index.html").read_text(encoding="utf-8")
    except FileNotFoundError:
        return HttpResponse("The application is temporarily unavailable.",
                            status=503, content_type="text/plain")
    response = HttpResponse(html, status=status)
    response["Cache-Control"] = "no-cache"  # always revalidate, so a new build is picked up straight away
    return response


def frontend_not_found(request):
    """Unknown page URLs still load the app (which shows "page not found"), but answer 404."""
    return frontend_app(request, status=404)


class HealthView(APIView):
    """GET /api/health/ - is the API up and can it reach CouchDB? (public)"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        try:
            get_db().info()
            return Response({"status": "ok"})
        except Exception:  # noqa: BLE001
            return Response({"status": "degraded"}, status=503)
