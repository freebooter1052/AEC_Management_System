from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from counsellors import services as counsellor_services
from students import services as student_services

from . import repository
from .db import get_db
from .roles import ADMIN, COUNSELLOR, STUDENT


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


class DashboardView(APIView):
    """GET /api/dashboard/ - role-specific summary for the dashboard skeleton (SRS 4.9)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role == STUDENT:
            return Response(self._student(user))
        if user.role == COUNSELLOR:
            return Response(self._counsellor(user))
        if user.role == ADMIN:
            return Response(self._admin())
        return Response({"role": user.role})

    @staticmethod
    def _student(user):
        doc = repository.get(user.profile_id, "student") or {}
        counsellor = repository.get(doc["counsellor_id"], "counsellor") if doc.get("counsellor_id") else None
        return {
            "role": STUDENT,
            "student_id": doc.get("_id"),
            "full_name": student_services.full_name(doc) if doc else user.full_name,
            "profile_completion": doc.get("profile_completion", {}),
            "onboarding_status": doc.get("onboarding_status"),
            "counsellor": counsellor_services.contact_card(counsellor),
            "preferences": doc.get("preferences", {}),
            "applications": {"total": len(doc.get("application_ids", []))},
        }

    @staticmethod
    def _counsellor(user):
        doc = repository.get(user.profile_id, "counsellor") or {}
        students = repository.find(
            {"type": "student", "counsellor_id": user.profile_id},
            fields=["_id", "personal", "preferences", "profile_completion", "onboarding_status", "counsellor_id",
                    "created_at", "updated_at"],
        )
        by_status: dict[str, int] = {}
        for s in students:
            key = s.get("onboarding_status", "registered")
            by_status[key] = by_status.get(key, 0) + 1
        needs_attention = sorted(students, key=lambda s: s.get("profile_completion", {}).get("overall", 0))[:5]
        return {
            "role": COUNSELLOR,
            "counsellor_id": doc.get("_id"),
            "name": doc.get("name", user.full_name),
            "workload": counsellor_services.workload(doc) if doc else None,
            "students_by_status": by_status,
            "needs_attention": [student_services.summary(s) for s in needs_attention],
        }

    @staticmethod
    def _admin():
        counsellors = repository.find({"type": "counsellor"},
                                      fields=["_id", "name", "is_active", "max_students", "assigned_student_ids"])
        return {
            "role": ADMIN,
            "totals": {
                "students": repository.count({"type": "student"}),
                "unassigned_students": repository.count({"type": "student", "counsellor_id": None}),
                "counsellors": len(counsellors),
                "active_counsellors": sum(1 for c in counsellors if c.get("is_active", True)),
                "universities": repository.count({"type": "university"}),
                "users": repository.count({"type": "user"}),
            },
            "counsellor_workload": sorted(
                ({"id": c["_id"], "name": c.get("name", ""), **counsellor_services.workload(c)} for c in counsellors),
                key=lambda c: -c["utilisation_pct"],
            ),
        }
