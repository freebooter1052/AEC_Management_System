"""Input validation for counselling sessions and follow-ups."""

from rest_framework import serializers

from apps.core.vocab import FOLLOW_UP_STATUSES, SESSION_MODES

from .services import MAX_SESSION_MINUTES


def item_list():
    """A list of short free-text items (recommendations, agreed actions)."""
    return serializers.ListField(child=serializers.CharField(max_length=300, allow_blank=True), max_length=20,
                                 required=False)


class SessionCreateSerializer(serializers.Serializer):
    student_id = serializers.CharField()
    scheduled_at = serializers.DateTimeField()
    duration_minutes = serializers.IntegerField(min_value=15, max_value=MAX_SESSION_MINUTES, default=45)
    mode = serializers.ChoiceField(choices=SESSION_MODES, default="Video call")
    topic = serializers.CharField(max_length=160)


class SessionUpdateSerializer(serializers.Serializer):
    scheduled_at = serializers.DateTimeField(required=False)
    duration_minutes = serializers.IntegerField(min_value=15, max_value=MAX_SESSION_MINUTES, required=False)
    mode = serializers.ChoiceField(choices=SESSION_MODES, required=False)
    topic = serializers.CharField(max_length=160, required=False)


class FollowUpSerializer(serializers.Serializer):
    action = serializers.CharField(max_length=300)
    due_date = serializers.DateField()


class SessionCompleteSerializer(serializers.Serializer):
    summary = serializers.CharField(max_length=4000)
    recommendations = item_list()
    action_items = item_list()
    follow_up = FollowUpSerializer(required=False, allow_null=True)


class SessionCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class FollowUpUpdateSerializer(serializers.Serializer):
    action = serializers.CharField(max_length=300, required=False)
    due_date = serializers.DateField(required=False)
    status = serializers.ChoiceField(choices=FOLLOW_UP_STATUSES, required=False)
