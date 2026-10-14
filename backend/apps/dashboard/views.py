"""Role-specific dashboard summaries (SRS 4.9)."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.applications import services as application_services
from apps.core import repository
from apps.core.roles import ADMIN, COUNSELLOR, STUDENT
from apps.counselling import services as counselling_services
from apps.counsellors import services as counsellor_services
from apps.documents import services as document_services
from apps.students import services as student_services

UPCOMING_SESSIONS = 5


def _workflow(user, student_ids: list[str] | None, *, session_selector: dict) -> dict:
    """Applications, documents, sessions and follow-ups for a set of students (None = everyone)."""
    scope = {} if student_ids is None else {"student_id": {"$in": student_ids}}
    apps = repository.find({"type": "application", **scope})
    docs = repository.find({"type": "document", **scope}, fields=["status"])
    now = repository.now_iso()
    upcoming = repository.find({**session_selector, "status": "Scheduled", "scheduled_at": {"$gte": now}},
                               sort=[{"type": "asc"}, {"scheduled_at": "asc"}], limit=UPCOMING_SESSIONS)
    follow_ups = counselling_services.follow_up_rows(
        repository.find({**session_selector, "follow_up.status": "Pending"}, limit=500))
    return {
        "applications": application_services.summary(apps),
        "documents": document_services.summary(docs),
        "upcoming_sessions": counselling_services.serialize_page(upcoming, user),
        "follow_ups": {"pending": len(follow_ups), "overdue": sum(1 for f in follow_ups if f["state"] == "overdue"),
                       "next": follow_ups[:5]},
    }


class DashboardView(APIView):
    """GET /api/dashboard/ - role-specific summary (SRS 4.9)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role == STUDENT:
            return Response(self._student(user))
        if user.role == COUNSELLOR:
            return Response(self._counsellor(user))
        if user.role == ADMIN:
            return Response(self._admin(user))
        return Response({"role": user.role})

    @staticmethod
    def _student(user):
        doc = repository.get(user.profile_id, "student") or {}
        counsellor = repository.get(doc["counsellor_id"], "counsellor") if doc.get("counsellor_id") else None
        workflow = _workflow(user, [doc["_id"]] if doc else [],
                             session_selector={"type": "counselling_session", "student_id": doc.get("_id")})
        return {
            "role": STUDENT,
            "student_id": doc.get("_id"),
            "full_name": student_services.full_name(doc) if doc else user.full_name,
            "profile_completion": doc.get("profile_completion", {}),
            "onboarding_status": doc.get("onboarding_status"),
            "counsellor": counsellor_services.contact_card(counsellor),
            "preferences": doc.get("preferences", {}),
            **workflow,
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
        workflow = _workflow(user, [s["_id"] for s in students],
                             session_selector={"type": "counselling_session", "counsellor_id": user.profile_id})
        return {
            "role": COUNSELLOR,
            "counsellor_id": doc.get("_id"),
            "name": doc.get("name", user.full_name),
            "workload": counsellor_services.workload(doc, len(students)) if doc else None,
            "students_by_status": by_status,
            "needs_attention": student_services.summary_page(needs_attention),
            **workflow,
        }

    @staticmethod
    def _admin(user):
        counsellors = repository.find({"type": "counsellor"}, fields=["_id", "name", "is_active", "max_students"])
        counts = counsellor_services.assigned_counts()
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
                ({"id": c["_id"], "name": c.get("name", ""), "is_active": c.get("is_active", True),
                  **counsellor_services.workload(c, counts.get(c["_id"], 0))} for c in counsellors),
                key=lambda c: -c["utilisation_pct"],
            ),
            **_workflow(user, None, session_selector={"type": "counselling_session"}),
        }
