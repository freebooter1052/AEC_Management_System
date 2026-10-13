import logging

from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core import audit, repository
from core.roles import ALL_ROLES, STUDENT
from students import services as student_services

from . import users
from .permissions import IsAdmin
from .serializers import ChangePasswordSerializer, LoginSerializer, RegisterSerializer, UserAdminUpdateSerializer
from .tokens import issue_token

security_logger = logging.getLogger("aec.security")


def _auth_response(user: dict, http_status=status.HTTP_200_OK) -> Response:
    return Response({"token": issue_token(user), "user": users.public_user(user)}, status=http_status)


class RegisterView(APIView):
    """POST /api/auth/register/ - student self-registration; returns a token so the student is signed in."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        if users.email_taken(data["email"]):
            raise ValidationError({"email": ["An account with this email already exists."]})

        full_name = f"{data['first_name'].strip()} {data['last_name'].strip()}"
        user = users.build_user(email=data["email"], password=data["password"], role=STUDENT, full_name=full_name)
        student = student_services.build_student(
            user_id=user["_id"],
            email=user["email"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            dial_code=data.get("dial_code", ""),
            phone=data.get("phone", ""),
            citizenship=data.get("citizenship", ""),
            degree_level=data.get("intended_level", ""),
        )
        user["profile_id"] = student["_id"]

        repository.save(student)
        try:
            repository.save(user)
        except Exception:
            repository.delete(student)  # keep the two documents consistent
            raise

        audit.record("auth.registered", request=request, target_id=user["_id"], details={"role": STUDENT})
        return _auth_response(user, status.HTTP_201_CREATED)


class LoginView(APIView):
    """POST /api/auth/login/ - email + password (+ optional portal role) -> bearer token and role."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        email, password = s.validated_data["email"], s.validated_data["password"]
        portal = s.validated_data.get("role")

        user = users.get_by_email(email)
        if user is None or not users.verify_password(user, password) or not user.get("is_active", True):
            reason = "unknown_email" if user is None else ("inactive" if not user.get("is_active", True) else "bad_password")
            security_logger.warning("Failed login for %s (%s)", users.normalize_email(email), reason)
            audit.record("auth.login_failed", request=request, target_id=user["_id"] if user else None,
                         details={"email": users.normalize_email(email), "reason": reason})
            return Response({"detail": "Invalid email or password."}, status=status.HTTP_401_UNAUTHORIZED)

        if portal and portal != user["role"]:
            audit.record("auth.login_failed", request=request, target_id=user["_id"],
                         details={"reason": "wrong_portal", "portal": portal})
            return Response(
                {"detail": f"This account is registered as {user['role']}, not {portal}. Choose the correct portal."},
                status=status.HTTP_403_FORBIDDEN,
            )

        user["last_login"] = repository.now_iso()
        repository.save(user)
        audit.record("auth.login", request=request, target_id=user["_id"])
        return _auth_response(user)


class LogoutView(APIView):
    """POST /api/auth/logout/ - revokes every token issued to this user."""

    def post(self, request):
        user = repository.get(request.user.id, "user")
        user["token_version"] = user.get("token_version", 0) + 1
        user["updated_at"] = repository.now_iso()
        repository.save(user)
        audit.record("auth.logout", request=request, actor=request.user, target_id=user["_id"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """GET /api/auth/me/ - the signed-in account and its role."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(users.public_user(request.user.doc))


class ChangePasswordView(APIView):
    def post(self, request):
        s = ChangePasswordSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = repository.get(request.user.id, "user")
        if not users.verify_password(user, s.validated_data["current_password"]):
            raise ValidationError({"current_password": ["Current password is incorrect."]})
        users.set_password(user, s.validated_data["new_password"])
        repository.save(user)
        audit.record("auth.password_changed", request=request, actor=request.user, target_id=user["_id"])
        return _auth_response(user)  # old tokens are revoked; hand back a fresh one


class UserListView(APIView):
    """GET /api/auth/users/?role=&q= - administrators only."""

    permission_classes = [IsAdmin]

    def get(self, request):
        selector = {"type": "user", "created_at": {"$gt": None}}
        role = request.query_params.get("role")
        if role in ALL_ROLES:
            selector["role"] = role
        q = (request.query_params.get("q") or "").strip()
        if q:
            pattern = repository.contains_pattern(q)
            selector["$or"] = [{"email": {"$regex": pattern}}, {"full_name": {"$regex": pattern}}]
        return Response(repository.paginate(
            request, selector, sort=[{"type": "desc"}, {"created_at": "desc"}], serialize=users.public_user,
        ))


class UserDetailView(APIView):
    """GET/PATCH /api/auth/users/<id>/ - administrators can activate/deactivate accounts."""

    permission_classes = [IsAdmin]

    def _get(self, user_id):
        user = repository.get(user_id, "user")
        if user is None:
            raise NotFound("User not found.")
        return user

    def get(self, request, user_id):
        return Response(users.public_user(self._get(user_id)))

    def patch(self, request, user_id):
        user = self._get(user_id)
        s = UserAdminUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        changes = s.validated_data
        if user["_id"] == request.user.id and changes.get("is_active") is False:
            raise ValidationError({"is_active": ["You cannot deactivate your own account."]})
        if "is_active" in changes and changes["is_active"] != user.get("is_active", True):
            user["is_active"] = changes["is_active"]
            user["token_version"] = user.get("token_version", 0) + 1
            audit.record("auth.user_activation_changed", request=request, actor=request.user,
                         target_id=user["_id"], details={"is_active": changes["is_active"]})
        if "full_name" in changes:
            user["full_name"] = changes["full_name"].strip()
        user["updated_at"] = repository.now_iso()
        repository.save(user)
        return Response(users.public_user(user))

