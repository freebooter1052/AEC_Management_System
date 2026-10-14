"""
Password reset by one-time code (forgot password).

One `password_reset` document per user:

    {
      "_id": "password_reset_1a2b3c4d5e6f", "type": "password_reset",
      "user_id": "user_...", "email": "jane@example.com",
      "code_hash": "<hmac-sha256>",        # keyed with SECRET_KEY; the 6-digit code is only ever emailed, never stored
      "attempts": 0, "created_at": "...", "expires_at": "..."
    }

Requesting a new code reuses the user's document (so a user never has more than one live code) and is
rate-limited by PASSWORD_RESET_COOLDOWN. A wrong code counts an attempt; after PASSWORD_RESET_MAX_ATTEMPTS
the code is dead and a new one must be requested. A successful reset deletes the document.
"""

import secrets
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.mail import send_mail
from django.utils.crypto import constant_time_compare, salted_hmac

from apps.core import repository

DOC_TYPE = "password_reset"


def _parse(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _hash(user_id: str, code: str) -> str:
    # A 6-digit code is guessable offline whatever the hash, so protection comes from the short expiry
    # and the attempt limit; a keyed HMAC keeps it unreadable in the database without PBKDF2's delay.
    return salted_hmac("aec.password_reset", f"{user_id}:{code}", algorithm="sha256").hexdigest()


def _find(user_id: str) -> dict | None:
    return repository.find_one({"type": DOC_TYPE, "user_id": user_id})


def issue(user: dict) -> str | None:
    """Create (or replace) the user's reset code and return it, or None while the cooldown is running."""
    now = datetime.now(timezone.utc)
    doc = _find(user["_id"])
    if doc and now - _parse(doc["created_at"]) < timedelta(seconds=settings.PASSWORD_RESET_COOLDOWN):
        return None
    code = f"{secrets.randbelow(10 ** 6):06d}"
    doc = doc or {"_id": repository.new_id(DOC_TYPE), "type": DOC_TYPE, "user_id": user["_id"]}
    doc.update(
        email=user["email"],
        code_hash=_hash(user["_id"], code),
        attempts=0,
        created_at=repository.to_iso(now),
        expires_at=repository.to_iso(now + timedelta(seconds=settings.PASSWORD_RESET_CODE_TTL)),
    )
    repository.save(doc)
    return code


def check(user: dict, code: str) -> dict | None:
    """Return the reset document if `code` is valid for this user, else None (counting a wrong attempt)."""
    doc = _find(user["_id"])
    if doc is None:
        return None
    if datetime.now(timezone.utc) >= _parse(doc["expires_at"]) or doc["attempts"] >= settings.PASSWORD_RESET_MAX_ATTEMPTS:
        return None
    if not constant_time_compare(_hash(user["_id"], code), doc["code_hash"]):
        doc["attempts"] += 1
        repository.save(doc)
        return None
    return doc


def consume(doc: dict) -> None:
    repository.delete(doc)


def send_code(user: dict, code: str) -> None:
    minutes = settings.PASSWORD_RESET_CODE_TTL // 60
    name = (user.get("full_name") or "").split(" ")[0] or "there"
    send_mail(
        subject="Your AEC Admissions password reset code",
        message=(
            f"Hi {name},\n\n"
            f"Your password reset code is: {code}\n\n"
            f"It is valid for {minutes} minutes and can be used once. "
            "If you did not ask to reset your password, you can ignore this email; your password has not changed.\n\n"
            "AEC Admissions"
        ),
        from_email=None,
        recipient_list=[user["email"]],
    )
