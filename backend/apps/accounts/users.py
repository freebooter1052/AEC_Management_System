"""
`user` documents - login credentials and role, kept separate from the
student/counsellor business profiles (SRS 6.2).

    {
      "_id": "user_1a2b3c4d5e6f", "type": "user",
      "email": "jane@example.com", "password_hash": "pbkdf2_sha256$...",
      "role": "student" | "counsellor" | "admin",
      "full_name": "Jane Doe", "profile_id": "student_...",
      "is_active": true, "token_version": 0, "last_login": "...",
      "created_at": "...", "updated_at": "..."
    }
"""

from django.contrib.auth.hashers import check_password, make_password

from apps.core import repository


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def get_by_email(email: str) -> dict | None:
    return repository.find_one({"type": "user", "email": normalize_email(email)})


def email_taken(email: str, exclude_id: str | None = None) -> bool:
    user = get_by_email(email)
    return user is not None and user["_id"] != exclude_id


def build_user(*, email: str, password: str, role: str, full_name: str, profile_id: str | None = None) -> dict:
    now = repository.now_iso()
    return {
        "_id": repository.new_id("user"),
        "type": "user",
        "email": normalize_email(email),
        "password_hash": make_password(password),
        "role": role,
        "full_name": full_name.strip(),
        "profile_id": profile_id,
        "is_active": True,
        "token_version": 0,
        "last_login": None,
        "created_at": now,
        "updated_at": now,
    }


def verify_password(user: dict, password: str) -> bool:
    return bool(user.get("password_hash")) and check_password(password, user["password_hash"])


def set_password(user: dict, password: str) -> None:
    user["password_hash"] = make_password(password)
    # Invalidate all previously issued tokens.
    user["token_version"] = user.get("token_version", 0) + 1
    user["updated_at"] = repository.now_iso()


def public_user(user: dict) -> dict:
    return {
        "id": user["_id"],
        "email": user["email"],
        "full_name": user.get("full_name", ""),
        "role": user["role"],
        "profile_id": user.get("profile_id"),
        "is_active": user.get("is_active", True),
        "last_login": user.get("last_login"),
        "created_at": user.get("created_at"),
    }
