"""
Stateless signed bearer tokens.

The token carries the user id and the user's `token_version`; it is signed
with SECRET_KEY and expires after AUTH_TOKEN_MAX_AGE seconds. Logging out (or
changing the password) bumps `token_version` on the user document, which
revokes every token issued before.
"""

from django.conf import settings
from django.core import signing

_SALT = "aec.auth.token"


def issue_token(user: dict) -> str:
    return signing.dumps({"uid": user["_id"], "v": user.get("token_version", 0)}, salt=_SALT, compress=True)


def read_token(token: str) -> dict | None:
    """Return the token payload, or None if it is malformed, tampered with or expired."""
    try:
        payload = signing.loads(token, salt=_SALT, max_age=settings.AUTH_TOKEN_MAX_AGE)
    except signing.BadSignature:  # includes SignatureExpired
        return None
    if not isinstance(payload, dict) or "uid" not in payload:
        return None
    return payload
