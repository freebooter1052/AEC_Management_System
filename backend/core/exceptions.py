"""
API-wide exception handling (SRS 5.2): understandable messages for users,
full diagnostics in the server log, no implementation details leaked.
"""

import logging

from couchdb.http import HTTPError as CouchHTTPError
from couchdb.http import ResourceConflict
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("aec.api")
security_logger = logging.getLogger("aec.security")


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The record was changed by someone else. Reload and try again."
    default_code = "conflict"


def api_exception_handler(exc, context):
    request = context.get("request")
    path = getattr(request, "path", "?")

    if isinstance(exc, ResourceConflict):
        exc = Conflict()

    response = exception_handler(exc, context)
    if response is not None:
        if response.status_code in (401, 403):
            user = getattr(request, "user", None)
            security_logger.warning(
                "Denied %s %s status=%s user=%s ip=%s",
                getattr(request, "method", "?"), path, response.status_code,
                getattr(user, "id", None), request.META.get("REMOTE_ADDR") if request else None,
            )
        return response

    if isinstance(exc, (CouchHTTPError, OSError)):
        logger.exception("CouchDB error on %s", path)
        return Response(
            {"detail": "The database is temporarily unavailable. Please try again shortly."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    logger.exception("Unhandled error on %s", path)
    return Response({"detail": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
