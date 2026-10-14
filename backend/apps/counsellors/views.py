from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import users
from apps.accounts.permissions import IsAdmin, IsCounsellor, IsStaff
from apps.core import audit, repository
from apps.core.roles import ADMIN, COUNSELLOR
from apps.students import services as student_services

from . import services
from .serializers import CounsellorAdminUpdateSerializer, CounsellorCreateSerializer, CounsellorSelfUpdateSerializer


def get_counsellor_or_404(counsellor_id: str) -> dict:
    doc = repository.get(counsellor_id, "counsellor")
    if doc is None:
        raise NotFound("Counsellor not found.")
    return doc


def check_admin_or_self(request, doc: dict) -> None:
    if request.user.role == ADMIN:
        return
    if request.user.role == COUNSELLOR and request.user.profile_id == doc["_id"]:
        return
    raise PermissionDenied("You can only view your own counsellor profile.")


def apply_changes(request, doc: dict, serializer_class) -> dict:
    s = serializer_class(data=request.data, partial=True)
    s.is_valid(raise_exception=True)
    changes = s.validated_data
    if changes.get("max_students") is not None and changes["max_students"] < services.assigned_count(doc["_id"]):
        raise ValidationError({"max_students": ["Capacity cannot be lower than the number of assigned students."]})
    for key, value in changes.items():
        doc[key] = value.strip() if isinstance(value, str) else value
    doc["updated_at"] = repository.now_iso()
    repository.save(doc)

    # Keep the login account in step with the profile.
    user = repository.get(doc.get("user_id"), "user")
    if user is not None and ("name" in changes or "is_active" in changes):
        user["full_name"] = doc["name"]
        if "is_active" in changes and user.get("is_active", True) != changes["is_active"]:
            user["is_active"] = changes["is_active"]
            user["token_version"] = user.get("token_version", 0) + 1
        user["updated_at"] = repository.now_iso()
        repository.save(user)
    if "is_active" in changes:
        audit.record("counsellor.activation_changed", request=request, actor=request.user,
                     target_id=doc["_id"], details={"is_active": changes["is_active"]})
    return doc


class CounsellorListCreateView(APIView):
    """
    GET  /api/counsellors/ - admins: every counsellor with workload. ?q=, ?active=true|false
    POST /api/counsellors/ - admins create a counsellor account + profile.
    """

    permission_classes = [IsAdmin]

    def get(self, request):
        selector = {"type": "counsellor", "created_at": {"$gt": None}}
        active = request.query_params.get("active")
        if active in ("true", "false"):
            selector["is_active"] = active == "true"
        q = (request.query_params.get("q") or "").strip()
        if q:
            pattern = repository.contains_pattern(q)
            selector["$or"] = [
                {"name": {"$regex": pattern}},
                {"email": {"$regex": pattern}},
                {"specialization": {"$regex": pattern}},
                {"region": {"$regex": pattern}},
            ]
        return Response(repository.paginate(
            request, selector, sort=[{"type": "desc"}, {"created_at": "desc"}], serialize_page=services.serialize_many,
        ))

    def post(self, request):
        s = CounsellorCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        if users.email_taken(data["email"]):
            raise ValidationError({"email": ["An account with this email already exists."]})

        user = users.build_user(email=data["email"], password=data["password"], role=COUNSELLOR,
                                full_name=data["name"])
        doc = services.build_counsellor(
            user_id=user["_id"], name=data["name"], email=user["email"], phone=data.get("phone", ""),
            specialization=data.get("specialization", ""), region=data.get("region", ""),
            max_students=data.get("max_students") or services.DEFAULT_MAX_STUDENTS,
        )
        user["profile_id"] = doc["_id"]

        repository.save(doc)
        try:
            repository.save(user)
        except Exception:
            repository.delete(doc)
            raise
        audit.record("counsellor.created", request=request, actor=request.user, target_id=doc["_id"])
        return Response(services.serialize(doc), status=status.HTTP_201_CREATED)


class CounsellorOptionsView(APIView):
    """GET /api/counsellors/options/ - compact list of active counsellors for assignment pickers (admins)."""

    permission_classes = [IsAdmin]

    def get(self, request):
        docs = repository.find({"type": "counsellor", "is_active": True},
                               fields=["_id", "name", "region", "specialization", "max_students"])
        counts = services.assigned_counts(d["_id"] for d in docs)
        return Response([
            {"id": d["_id"], "name": d.get("name", ""), "region": d.get("region", ""),
             "specialization": d.get("specialization", ""), "workload": services.workload(d, counts.get(d["_id"], 0))}
            for d in sorted(docs, key=lambda d: d.get("name", "").lower())
        ])


class CounsellorMeView(APIView):
    """GET/PATCH /api/counsellors/me/ - the signed-in counsellor's own profile."""

    permission_classes = [IsCounsellor]

    def get(self, request):
        return Response(services.serialize(get_counsellor_or_404(request.user.profile_id)))

    def patch(self, request):
        doc = apply_changes(request, get_counsellor_or_404(request.user.profile_id), CounsellorSelfUpdateSerializer)
        return Response(services.serialize(doc))


class CounsellorDetailView(APIView):
    """
    GET    /api/counsellors/<id>/ - admins, or the counsellor themself.
    PATCH  /api/counsellors/<id>/ - admins (all fields) or self (contact fields only).
    DELETE /api/counsellors/<id>/ - admins; refused while students are still assigned.
    """

    permission_classes = [IsStaff]

    def get_permissions(self):
        return [IsAdmin()] if self.request.method == "DELETE" else super().get_permissions()

    def get(self, request, counsellor_id):
        doc = get_counsellor_or_404(counsellor_id)
        check_admin_or_self(request, doc)
        return Response(services.serialize(doc))

    def patch(self, request, counsellor_id):
        doc = get_counsellor_or_404(counsellor_id)
        check_admin_or_self(request, doc)
        serializer_class = CounsellorAdminUpdateSerializer if request.user.role == ADMIN else CounsellorSelfUpdateSerializer
        return Response(services.serialize(apply_changes(request, doc, serializer_class)))

    def delete(self, request, counsellor_id):
        doc = get_counsellor_or_404(counsellor_id)
        assigned = repository.count({"type": "student", "counsellor_id": counsellor_id})
        if assigned:
            raise ValidationError({"detail": f"Reassign this counsellor's {assigned} student(s) before deleting."})
        user = repository.get(doc.get("user_id"), "user")
        repository.delete(doc)
        if user is not None:
            repository.delete(user)
        audit.record("counsellor.deleted", request=request, actor=request.user, target_id=counsellor_id,
                     details={"email": doc.get("email")})
        return Response(status=status.HTTP_204_NO_CONTENT)


class CounsellorStudentsView(APIView):
    """GET /api/counsellors/<id>/students/ - the counsellor's assigned-student roster (admins or self)."""

    permission_classes = [IsStaff]

    def get(self, request, counsellor_id):
        doc = get_counsellor_or_404(counsellor_id)
        check_admin_or_self(request, doc)
        selector = {"type": "student", "counsellor_id": counsellor_id, "created_at": {"$gt": None}}
        page = repository.paginate(request, selector, sort=[{"type": "desc"}, {"created_at": "desc"}],
                                   serialize_page=student_services.summary_page)
        page["counsellor"] = services.serialize(doc)
        return Response(page)
