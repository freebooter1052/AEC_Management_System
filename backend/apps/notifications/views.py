from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import repository
from apps.core.vocab import NOTIFICATION_CATEGORIES

from . import reminders, services


class ReadSerializer(serializers.Serializer):
    read = serializers.BooleanField(default=True)


class NotificationListView(APIView):
    """
    GET /api/notifications/?unread=1&category=&page=&page_size= - the caller's own notifications,
        newest first. Every role has an inbox; nobody can list anyone else's.
    """

    def get(self, request):
        params = request.query_params
        category = params.get("category", "")
        if category and category not in NOTIFICATION_CATEGORIES:
            raise ValidationError({"category": [f"Choose one of: {', '.join(NOTIFICATION_CATEGORIES)}."]})
        reminders.sweep_for_user(request.user)
        selector = services.list_selector(request.user, unread=params.get("unread") in ("1", "true", "yes"),
                                          category=category)
        data = repository.paginate(request, selector, sort=services.NEWEST_FIRST, serialize=services.serialize)
        data["unread"] = services.unread_summary(request.user)["unread"]
        return Response(data)


class UnreadCountView(APIView):
    """GET /api/notifications/unread-count/ - {unread, by_category} for the bell in the top bar."""

    def get(self, request):
        reminders.sweep_for_user(request.user)
        return Response(services.unread_summary(request.user))


class NotificationDetailView(APIView):
    """GET /api/notifications/<id>/ - one of the caller's notifications (403 for anyone else's)."""

    def get(self, request, notification_id):
        return Response(services.serialize(services.get_own(request.user, notification_id)))


class NotificationReadView(APIView):
    """POST /api/notifications/<id>/read/ {read: true|false} - mark read (default) or unread again."""

    def post(self, request, notification_id):
        s = ReadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        doc = services.set_read(request.user, notification_id, s.validated_data["read"])
        return Response(services.serialize(doc))


class MarkAllReadView(APIView):
    """POST /api/notifications/read-all/ - mark every unread notification of the caller read."""

    def post(self, request):
        return Response(services.mark_all_read(request.user))
