"""
Role-based permissions (SRS 4.1, 5.3). These run on the backend for every
request - the frontend only hides what the API would refuse anyway.
"""

from rest_framework.permissions import BasePermission

from apps.core.roles import ADMIN, COUNSELLOR, STUDENT


class HasRole(BasePermission):
    allowed_roles: tuple = ()
    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and getattr(user, "is_authenticated", False) and user.role in self.allowed_roles)


def role_required(*roles):
    """Build a permission class allowing only the given roles: `role_required(ADMIN, COUNSELLOR)`."""
    return type(f"RoleRequired_{'_'.join(roles)}", (HasRole,), {"allowed_roles": tuple(roles)})


IsStudent = role_required(STUDENT)
IsCounsellor = role_required(COUNSELLOR)
IsAdmin = role_required(ADMIN)
IsStaff = role_required(COUNSELLOR, ADMIN)
