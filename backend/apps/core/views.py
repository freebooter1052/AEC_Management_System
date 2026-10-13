from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .db import get_db


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
