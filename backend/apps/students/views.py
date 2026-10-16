from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import users
from apps.accounts.permissions import IsAdmin, IsStaff, IsStudent
from apps.core import audit, repository
from apps.core.roles import COUNSELLOR, STUDENT
from apps.counsellors import services as counsellor_services

from . import services
from .serializers import AssignCounsellorSerializer, StudentCreateSerializer, StudentProfileSerializer

STUDENT_SORT = [{"type": "desc"}, {"created_at": "desc"}]


def get_student_or_404(student_id: str) -> dict:
    doc = repository.get(student_id, "student")
    if doc is None:
        raise NotFound("Student not found.")
    return doc


def get_accessible_student(request, student_id: str) -> dict:
    doc = get_student_or_404(student_id)
    if not services.can_access(request.user, doc):
        raise PermissionDenied("You do not have access to this student.")
    return doc


def update_profile(request, doc: dict) -> dict:
    s = StudentProfileSerializer(data=request.data, partial=True)
    s.is_valid(raise_exception=True)
    services.apply_update(doc, s.validated_data)
    if request.data.get("rev"):  # optimistic concurrency: the client sends the revision it edited
        doc["_rev"] = request.data["rev"]
    repository.save(doc)
    return doc


def _sync_user_name(doc: dict) -> None:
    """Keep the account's display name in step with the profile name."""
    user = repository.get(doc.get("user_id"), "user")
    if user is not None and user.get("full_name") != services.full_name(doc):
        user["full_name"] = services.full_name(doc)
        user["updated_at"] = repository.now_iso()
        repository.save(user)


class StudentListCreateView(APIView):
    """
    GET  /api/students/  - admins: all students; counsellors: their assigned students.
         Filters: ?q= (name/email), ?counsellor_id=, ?unassigned=true, ?status=, ?page=, ?page_size=
    POST /api/students/  - admins create a student account + profile.
    """

    def get_permissions(self):
        return [IsAdmin()] if self.request.method == "POST" else [IsStaff()]

    def get(self, request):
        selector = {"type": "student", "created_at": {"$gt": None}}
        params = request.query_params

        if request.user.role == COUNSELLOR:
            selector["counsellor_id"] = request.user.profile_id
        elif params.get("unassigned") in ("1", "true", "yes"):
            selector["counsellor_id"] = None
        elif params.get("counsellor_id"):
            selector["counsellor_id"] = params["counsellor_id"]

        if params.get("status"):
            selector["onboarding_status"] = params["status"]
        # Every word must match the first name, last name or email, so "asha nair" finds Asha Nair.
        words = params.get("q", "").split()[:5]
        if words:
            selector["$and"] = [{"$or": [
                {"personal.first_name": {"$regex": repository.contains_pattern(w)}},
                {"personal.last_name": {"$regex": repository.contains_pattern(w)}},
                {"personal.email": {"$regex": repository.contains_pattern(w)}},
            ]} for w in words]
        return Response(repository.paginate(request, selector, sort=STUDENT_SORT, serialize_page=services.summary_page))

    def post(self, request):
        s = StudentCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        if users.email_taken(data["email"]):
            raise ValidationError({"email": ["An account with this email already exists."]})

        user = users.build_user(email=data["email"], password=data["password"], role=STUDENT,
                                full_name=f"{data['first_name'].strip()} {data['last_name'].strip()}")
        doc = services.build_student(user_id=user["_id"], email=user["email"],
                                     first_name=data["first_name"], last_name=data["last_name"])
        services.apply_update(doc, data)
        user["profile_id"] = doc["_id"]

        repository.save(doc)
        try:
            repository.save(user)
        except Exception:
            repository.delete(doc)
            raise
        audit.record("student.created", request=request, actor=request.user, target_id=doc["_id"])

        if data.get("counsellor_id"):
            services.assign_counsellor(doc, data["counsellor_id"], actor=request.user, request=request)
        return Response(services.serialize(doc), status=status.HTTP_201_CREATED)


class StudentMeView(APIView):
    """GET/PATCH /api/students/me/ - the signed-in student's own profile."""

    permission_classes = [IsStudent]

    def _doc(self, request):
        doc = repository.get(request.user.profile_id, "student")
        if doc is None or doc.get("user_id") != request.user.id:
            raise NotFound("Student profile not found.")
        return doc

    def get(self, request):
        return Response(services.serialize(self._doc(request)))

    def patch(self, request):
        doc = update_profile(request, self._doc(request))
        _sync_user_name(doc)
        return Response(services.serialize(doc))


class StudentDetailView(APIView):
    """
    GET    /api/students/<id>/ - admin, the assigned counsellor, or the student themself.
    PATCH  /api/students/<id>/ - same audience; counsellor_id cannot be changed here.
    DELETE /api/students/<id>/ - admins only; removes the profile, its login account and its
           applications, documents and counselling sessions.
    """

    def get_permissions(self):
        return [IsAdmin()] if self.request.method == "DELETE" else super().get_permissions()

    def get(self, request, student_id):
        return Response(services.serialize(get_accessible_student(request, student_id)))

    def patch(self, request, student_id):
        doc = update_profile(request, get_accessible_student(request, student_id))
        _sync_user_name(doc)
        return Response(services.serialize(doc))

    def delete(self, request, student_id):
        doc = get_student_or_404(student_id)
        if doc.get("counsellor_id"):
            services.assign_counsellor(doc, None, actor=request.user, request=request)
            doc = get_student_or_404(student_id)
        user = repository.get(doc.get("user_id"), "user")
        records = services.delete_workflow_records(student_id)
        repository.delete(doc)
        if user is not None:
            repository.delete(user)
        audit.record("student.deleted", request=request, actor=request.user, target_id=student_id,
                     details={"email": doc.get("personal", {}).get("email"), "workflow_records": records})
        return Response(status=status.HTTP_204_NO_CONTENT)


class AssignCounsellorView(APIView):
    """POST /api/students/<id>/assign-counsellor/ {"counsellor_id": "counsellor_..." | null} - admins only."""

    permission_classes = [IsAdmin]

    def post(self, request, student_id):
        s = AssignCounsellorSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        doc = get_student_or_404(student_id)
        doc = services.assign_counsellor(doc, s.validated_data["counsellor_id"] or None,
                                         actor=request.user, request=request)
        return Response(services.serialize(doc))


class StudentCounsellorView(APIView):
    """GET /api/students/me/counsellor/ - the signed-in student's assigned counsellor (read-only)."""

    permission_classes = [IsStudent]

    def get(self, request):
        doc = repository.get(request.user.profile_id, "student")
        counsellor = repository.get(doc["counsellor_id"], "counsellor") if doc and doc.get("counsellor_id") else None
        return Response({"counsellor": counsellor_services.contact_card(counsellor)})

