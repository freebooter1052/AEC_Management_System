"""Input validation for applications, status changes and intakes."""

from rest_framework import serializers

from apps.core.vocab import APPLICATION_STATUSES, RECOMMENDATION_TIERS

TIERS = ["", *RECOMMENDATION_TIERS]


class ApplicationCreateSerializer(serializers.Serializer):
    student_id = serializers.CharField(required=False)  # staff; students always apply for themselves
    course_id = serializers.CharField()
    intake_id = serializers.CharField()
    deadline = serializers.DateField(required=False, allow_null=True)  # defaults to the intake deadline
    tier = serializers.ChoiceField(choices=TIERS, required=False, default="")
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class ApplicationUpdateSerializer(serializers.Serializer):
    """PATCH /api/applications/<id>/ - counsellors and admins; status changes use the status endpoint."""

    deadline = serializers.DateField(required=False)
    decision_expected = serializers.DateField(required=False, allow_null=True)
    tier = serializers.ChoiceField(choices=TIERS, required=False)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=APPLICATION_STATUSES)
    remarks = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class IntakeSerializer(serializers.Serializer):
    season = serializers.ChoiceField(choices=["Spring", "Summer", "Fall", "Winter"])
    year = serializers.IntegerField(min_value=2000, max_value=2100)
    application_deadline = serializers.DateField()
    decision_by = serializers.DateField(required=False, allow_null=True)
    start_date = serializers.DateField()

    def validate(self, attrs):
        deadline, start = attrs.get("application_deadline"), attrs.get("start_date")
        decision = attrs.get("decision_by")
        if deadline and start and deadline >= start:
            raise serializers.ValidationError({"application_deadline": "The deadline must be before the start date."})
        if decision and ((deadline and decision < deadline) or (start and decision > start)):
            raise serializers.ValidationError({"decision_by": "Decisions fall between the deadline and the start date."})
        return attrs
