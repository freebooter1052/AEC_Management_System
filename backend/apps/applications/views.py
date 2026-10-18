from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdmin, IsStaff
from apps.core import audit, repository
from apps.core.roles import STUDENT
from apps.students import services as student_services

from . import services
from .serializers import (
    ApplicationCreateSerializer, ApplicationUpdateSerializer, IntakeSerializer, StatusChangeSerializer,
)

NEWEST_FIRST = [{"type": "desc"}, {"created_at": "desc"}]
DEADLINE_FIRST = [{"type": "asc"}, {"deadline": "asc"}]


def get_accessible_application(request, application_id: str) -> dict:
    app = repository.get(application_id, "application")
    if app is None:
        raise NotFound("Application not found.")
    if not services.can_access(request.user, app):
        raise PermissionDenied("You do not have access to this application.")
    return app


def application_selector(request) -> dict:
    """Shared filters: ?student_id=, ?status= (comma-separated), ?open=true, ?q= (university or course)."""
    params = request.query_params
    selector = student_services.scope_to_students(request.user, {"type": "application"}, params.get("student_id"))
    statuses = [s.strip() for s in params.get("status", "").split(",") if s.strip()]
    if statuses:
        selector["status"] = {"$in": statuses}
    elif params.get("open") in ("1", "true", "yes"):
        selector["status"] = {"$in": [s for s in services.TRANSITIONS if s not in services.TERMINAL]}
    if params.get("q", "").strip():
        pattern = repository.contains_pattern(params["q"])
        selector["$or"] = [{"snapshot.university_name": {"$regex": pattern}},
                           {"snapshot.course_title": {"$regex": pattern}}]
    return selector


class ApplicationListCreateView(APIView):
    """
    GET  /api/applications/ - applications the caller may see (student: own; counsellor: assigned
         students; admin: all). Filters as in `application_selector`; ?sort=deadline for nearest first.
    POST /api/applications/ - {course_id, intake_id, deadline?, tier?, notes?, student_id (staff)}.
    """

    def get(self, request):
        selector = application_selector(request)
        if request.query_params.get("sort") == "deadline":
            selector["deadline"] = {"$gt": None}
            sort = DEADLINE_FIRST
        else:
            selector["created_at"] = {"$gt": None}
            sort = NEWEST_FIRST
        return Response(repository.paginate(request, selector, sort=sort, serialize_page=services.serialize_page))

    def post(self, request):
        s = ApplicationCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        student_id = request.user.profile_id if request.user.role == STUDENT else data.get("student_id")
        if not student_id:
            raise ValidationError({"student_id": ["Choose a student."]})
        student = student_services.get_accessible(request.user, student_id)
        app = services.create(student=student, course_id=data["course_id"], intake_id=data["intake_id"],
                              deadline=data.get("deadline"), tier=data["tier"], notes=data["notes"],
                              actor=request.user, request=request)
        return Response(services.detail(app, request.user), status=status.HTTP_201_CREATED)


class ApplicationSummaryView(APIView):
    """GET /api/applications/summary/?student_id= - pipeline counts and nearest deadlines."""

    def get(self, request):
        selector = student_services.scope_to_students(request.user, {"type": "application"},
                                                      request.query_params.get("student_id"))
        if "student_id" not in selector:  # an admin's agency-wide view: reduce views, not every application
            return Response(services.agency_summary())
        return Response(services.summary(repository.find(selector)))


class ApplicationDetailView(APIView):
    """
    GET    /api/applications/<id>/ - with history, documents, allowed next statuses and intake.
    PATCH  /api/applications/<id>/ - counsellors/admins edit deadline, decision date, tier, notes (send `rev`).
    DELETE /api/applications/<id>/ - only while Planned; the student or their counsellor/admin.
    """

    def get_permissions(self):
        return [IsStaff()] if self.request.method == "PATCH" else super().get_permissions()

    def get(self, request, application_id):
        return Response(services.detail(get_accessible_application(request, application_id), request.user))

    def patch(self, request, application_id):
        s = ApplicationUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        app = get_accessible_application(request, application_id)
        changes = s.validated_data
        if "deadline" in changes:
            intake = repository.get(app.get("intake_id"), "intake")
            changes["deadline"] = services.validate_deadline(changes["deadline"], intake, allow_past=True)
        if changes.get("decision_expected"):
            changes["decision_expected"] = changes["decision_expected"].isoformat()
        if "tier" in changes:
            changes["tier"] = changes["tier"] or None
        if "notes" in changes:
            changes["notes"] = changes["notes"].strip()
        app.update(changes)
        app["updated_at"] = repository.now_iso()
        if request.data.get("rev"):
            app["_rev"] = request.data["rev"]
        repository.save(app)
        audit.record("application.updated", request=request, actor=request.user, target_id=app["_id"],
                     details={"fields": sorted(changes)})
        return Response(services.detail(app, request.user))

    def delete(self, request, application_id):
        services.delete(get_accessible_application(request, application_id), actor=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ApplicationStatusView(APIView):
    """POST /api/applications/<id>/status/ {status, remarks?, rev?} - one step along the workflow."""

    def post(self, request, application_id):
        s = StatusChangeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        app = get_accessible_application(request, application_id)
        if request.data.get("rev"):
            app["_rev"] = request.data["rev"]
        app = services.change_status(app, s.validated_data["status"], remarks=s.validated_data["remarks"],
                                     actor=request.user, request=request)
        return Response(services.detail(app, request.user))


class ApplicationHistoryView(APIView):
    """GET /api/applications/<id>/history/ - the timestamped status trail."""

    def get(self, request, application_id):
        return Response(services.history(get_accessible_application(request, application_id)))


# ---------------------------------------------------------------------------
# Intakes (master data that sets application deadlines)
# ---------------------------------------------------------------------------
def _intake_fields(data: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in data.items()}


class IntakeListCreateView(APIView):
    """
    GET  /api/intakes/ - every intake, soonest start first, with `is_open` (deadline not yet passed).
    POST /api/intakes/ - admins add one: {season, year, application_deadline, decision_by?, start_date}.
    """

    def get_permissions(self):
        return [IsAdmin()] if self.request.method == "POST" else super().get_permissions()

    def get(self, request):
        intakes = sorted(repository.find({"type": "intake"}), key=lambda i: i.get("start_date") or "")
        return Response([services.serialize_intake(i) for i in intakes])

    def post(self, request):
        s = IntakeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = _intake_fields(s.validated_data)
        intake_id = f"intake_{data['season'].lower()}_{data['year']}"
        if repository.get(intake_id) is not None:
            raise ValidationError({"season": [f"The {data['season']} {data['year']} intake already exists."]})
        doc = {"_id": intake_id, "type": "intake", "name": f"{data['season']} {data['year']}",
               "decision_by": None, **data, "created_at": repository.now_iso()}
        repository.save(doc)
        audit.record("intake.created", request=request, actor=request.user, target_id=intake_id)
        return Response(services.serialize_intake(doc), status=status.HTTP_201_CREATED)


class IntakeDetailView(APIView):
    """PATCH /api/intakes/<id>/ - admins move dates. Existing applications keep their own deadline."""

    permission_classes = [IsAdmin]

    def patch(self, request, intake_id):
        doc = repository.get(intake_id, "intake")
        if doc is None:
            raise NotFound("Intake not found.")
        merged = {k: doc.get(k) for k in ("season", "year", "application_deadline", "decision_by", "start_date")}
        merged.update({k: v for k, v in request.data.items() if k in ("application_deadline", "decision_by", "start_date")})
        s = IntakeSerializer(data=merged)
        s.is_valid(raise_exception=True)
        doc.update({k: v for k, v in _intake_fields(s.validated_data).items() if k not in ("season", "year")})
        doc["updated_at"] = repository.now_iso()
        repository.save(doc)
        audit.record("intake.updated", request=request, actor=request.user, target_id=intake_id)
        return Response(services.serialize_intake(doc))
