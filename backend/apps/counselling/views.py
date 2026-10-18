from datetime import date, timedelta

from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsStaff
from apps.core import repository
from apps.core.roles import STUDENT
from apps.students import services as student_services

from . import services
from .serializers import (
    FollowUpUpdateSerializer, SessionCancelSerializer, SessionCompleteSerializer, SessionCreateSerializer,
    SessionUpdateSerializer,
)

MAX_CALENDAR_DAYS = 62
session_sort = services.session_sort


def get_session(request, session_id: str, *, manage: bool = False) -> dict:
    session = repository.get(session_id, "counselling_session")
    if session is None:
        raise NotFound("Session not found.")
    if not services.can_view(request.user, session):
        raise PermissionDenied("You do not have access to this session.")
    if manage and not services.can_manage(request.user, session):
        raise PermissionDenied("Only the session's counsellor or an administrator can change it.")
    if request.method != "GET" and request.data.get("rev"):  # optimistic concurrency, as on profiles
        session["_rev"] = request.data["rev"]
    return session


def _date_param(request, name: str) -> date | None:
    value = request.query_params.get(name)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError({name: ["Use the YYYY-MM-DD format."]}) from None


class SessionListCreateView(APIView):
    """
    GET  /api/counselling/sessions/ - counselling history. ?student_id=, ?status=, ?when=upcoming|past,
         ?counsellor_id= (admins). Upcoming sessions are listed soonest first, everything else newest first.
    POST /api/counselling/sessions/ - staff schedule {student_id, scheduled_at, duration_minutes, mode, topic}.
    """

    def get_permissions(self):
        return [IsStaff()] if self.request.method == "POST" else super().get_permissions()

    def get(self, request):
        params = request.query_params
        selector = services.scope_selector(request.user, {"type": "counselling_session"},
                                           student_id=params.get("student_id"), counsellor_id=params.get("counsellor_id"))
        if params.get("status"):
            selector["status"] = params["status"]
        now = repository.now_iso()
        when = params.get("when")
        if when == "upcoming":
            selector["scheduled_at"] = {"$gte": now}
        elif when == "past":
            selector["scheduled_at"] = {"$lt": now}
        else:
            selector["scheduled_at"] = {"$gt": None}
        direction = "asc" if when == "upcoming" else "desc"
        return Response(repository.paginate(
            request, selector, sort=session_sort(selector, direction),
            serialize_page=lambda docs: services.serialize_page(docs, request.user)))

    def post(self, request):
        s = SessionCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        student = student_services.get_accessible(request.user, data["student_id"])
        doc = services.schedule(student=student, scheduled_at=data["scheduled_at"], duration_minutes=data["duration_minutes"],
                                mode=data["mode"], topic=data["topic"], actor=request.user, request=request)
        return Response(services.serialize(doc, request.user), status=status.HTTP_201_CREATED)


class SessionDetailView(APIView):
    """GET /api/counselling/sessions/<id>/ · PATCH (reschedule / edit a scheduled session; send `rev`)."""

    def get(self, request, session_id):
        return Response(services.serialize(get_session(request, session_id), request.user))

    def patch(self, request, session_id):
        s = SessionUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        session = services.reschedule(get_session(request, session_id, manage=True), s.validated_data,
                                      actor=request.user, request=request)
        return Response(services.serialize(session, request.user))


class SessionCompleteView(APIView):
    """POST /api/counselling/sessions/<id>/complete/ {summary, recommendations[], action_items[], follow_up?}"""

    def post(self, request, session_id):
        s = SessionCompleteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        session = services.complete(get_session(request, session_id, manage=True), s.validated_data,
                                    actor=request.user, request=request)
        return Response(services.serialize(session, request.user))


class SessionCancelView(APIView):
    """POST /api/counselling/sessions/<id>/cancel/ {reason?}"""

    def post(self, request, session_id):
        s = SessionCancelSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        session = services.cancel(get_session(request, session_id, manage=True), s.validated_data["reason"],
                                  actor=request.user, request=request)
        return Response(services.serialize(session, request.user))


class FollowUpUpdateView(APIView):
    """PATCH /api/counselling/sessions/<id>/follow-up/ {status?, action?, due_date?}"""

    def patch(self, request, session_id):
        s = FollowUpUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        session = get_session(request, session_id)
        if request.user.role != STUDENT and not services.can_manage(request.user, session):
            raise PermissionDenied("Only the session's counsellor or an administrator can change this follow-up.")
        session = services.update_follow_up(session, s.validated_data, actor=request.user, request=request)
        return Response(services.serialize(session, request.user))


class FollowUpListView(APIView):
    """GET /api/counselling/follow-ups/?status=Pending|Done&student_id= - follow-ups, soonest due first."""

    def get(self, request):
        params = request.query_params
        selector = services.scope_selector(request.user, {"type": "counselling_session", "follow_up.due_date": {"$gt": None}},
                                           student_id=params.get("student_id"), counsellor_id=params.get("counsellor_id"))
        if params.get("status"):
            selector["follow_up.status"] = params["status"]
        rows = services.follow_up_rows(repository.find(selector, limit=500))
        return Response({"count": len(rows), "results": rows})


class CalendarView(APIView):
    """
    GET /api/counselling/calendar/?start=YYYY-MM-DD&end=YYYY-MM-DD (end exclusive, at most 62 days)
        - sessions and follow-up due dates in the range, for the calendar grid.
    """

    def get(self, request):
        today = repository.today()
        start = _date_param(request, "start") or today.replace(day=1)
        end = _date_param(request, "end") or start + timedelta(days=42)
        if end <= start or (end - start).days > MAX_CALENDAR_DAYS:
            raise ValidationError({"end": [f"Choose an end date within {MAX_CALENDAR_DAYS} days after the start."]})
        params = request.query_params
        scope = dict(student_id=params.get("student_id"), counsellor_id=params.get("counsellor_id"))

        selector = services.scope_selector(request.user, {"type": "counselling_session"}, **scope)
        selector["scheduled_at"] = {"$gte": f"{start.isoformat()}T00:00:00Z", "$lt": f"{end.isoformat()}T00:00:00Z"}
        sessions = repository.find(selector, sort=session_sort(selector), limit=1000)

        follow_selector = services.scope_selector(request.user, {"type": "counselling_session"}, **scope)
        follow_selector["follow_up.due_date"] = {"$gte": start.isoformat(), "$lt": end.isoformat()}
        follow_ups = services.follow_up_rows(repository.find(follow_selector, limit=1000))

        return Response({"start": start.isoformat(), "end": end.isoformat(),
                         "sessions": services.serialize_page(sessions, request.user), "follow_ups": follow_ups})
