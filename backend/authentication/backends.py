"""DRF authentication backed by CouchDB `user` documents."""

from rest_framework import authentication, exceptions

from core import repository

from .tokens import read_token


class AuthUser:
    """The authenticated principal attached to `request.user`."""

    is_authenticated = True
    is_anonymous = False

    def __init__(self, doc: dict):
        self.doc = doc
        self.id = doc["_id"]
        self.email = doc["email"]
        self.role = doc["role"]
        self.full_name = doc.get("full_name", "")
        self.profile_id = doc.get("profile_id")

    def __str__(self):
        return f"{self.email} ({self.role})"


class CouchTokenAuthentication(authentication.BaseAuthentication):
    """Reads `Authorization: Bearer <token>`."""

    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header or header[0].decode().lower() != self.keyword.lower():
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed("Invalid authorization header.")

        payload = read_token(header[1].decode())
        if payload is None:
            raise exceptions.AuthenticationFailed("Invalid or expired token. Please sign in again.")

        doc = repository.get(payload["uid"], "user")
        if doc is None or not doc.get("is_active", True):
            raise exceptions.AuthenticationFailed("Account not found or disabled.")
        if payload.get("v") != doc.get("token_version", 0):
            raise exceptions.AuthenticationFailed("Session has ended. Please sign in again.")

        return AuthUser(doc), None

    def authenticate_header(self, request):
        return self.keyword
