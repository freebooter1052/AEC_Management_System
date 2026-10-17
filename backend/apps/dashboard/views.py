"""Role-specific dashboard summaries (SRS 4.9); the figures are computed in services.py."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.roles import ADMIN, COUNSELLOR, STUDENT
from apps.notifications import reminders

from . import services


class DashboardView(APIView):
    """
    GET /api/dashboard/ - summary for the caller's role. Staff may filter with ?country=&intake_id=,
    admins also with ?counsellor_id= (see services.py for what each filter narrows).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        reminders.sweep_for_user(user)
        filters = services.parse_filters(request.query_params, user)
        if user.role == STUDENT:
            return Response(services.student_dashboard(user))
        if user.role == COUNSELLOR:
            return Response(services.counsellor_dashboard(user, filters))
        if user.role == ADMIN:
            return Response(services.admin_dashboard(user, filters))
        return Response({"role": user.role})
