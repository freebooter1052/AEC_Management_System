"""Input validation for SOP drafts, referees, consent and the writing settings."""

from rest_framework import serializers

from apps.core.vocab import REFERENCE_STATUSES, STATEMENT_STATUSES

from .prompts import SOP_KEYS


class StatementCreateSerializer(serializers.Serializer):
    student_id = serializers.CharField()
    application_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    title = serializers.CharField(max_length=160, required=False, allow_blank=True)
    word_limit = serializers.IntegerField(min_value=150, max_value=2000, required=False)


class AnswersSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected the interview answers as an object.")
        out, errors = {}, {}
        for key, value in data.items():
            if key not in SOP_KEYS:
                continue
            if not isinstance(value, str):
                errors[key] = ["Enter text."]
            elif len(value) > 2000:
                errors[key] = ["Keep this answer under 2,000 characters."]
            else:
                out[key] = value
        if errors:
            raise serializers.ValidationError(errors)
        return out


class StatementUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=160, required=False)
    word_limit = serializers.IntegerField(min_value=150, max_value=2000, required=False)
    answers = AnswersSerializer(required=False)
    content = serializers.CharField(max_length=20000, required=False, allow_blank=True, trim_whitespace=False)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)


class ReviseSerializer(serializers.Serializer):
    instruction = serializers.CharField(max_length=300)


class StatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=STATEMENT_STATUSES)


class DecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["Approved", "Changes requested"])
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class RestoreSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


class CommentSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=1000)


class RefereeSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    title = serializers.CharField(max_length=120, required=False, allow_blank=True)
    institution = serializers.CharField(max_length=160, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    relationship = serializers.CharField(max_length=200, required=False, allow_blank=True)


class RefereePatchSerializer(RefereeSerializer):
    name = serializers.CharField(max_length=120, required=False)


class ReferenceCreateSerializer(serializers.Serializer):
    student_id = serializers.CharField()
    application_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    referee = RefereeSerializer()
    highlights = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    due_date = serializers.DateField(required=False, allow_null=True)


class ReferenceUpdateSerializer(serializers.Serializer):
    referee = RefereePatchSerializer(required=False)
    highlights = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=REFERENCE_STATUSES, required=False)


class PrepareSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=("lor_brief", "lor_draft"), default="lor_brief")


class ConsentSerializer(serializers.Serializer):
    granted = serializers.BooleanField()


class StudentRefSerializer(serializers.Serializer):
    student_id = serializers.CharField()


class SettingsSerializer(serializers.Serializer):
    allow_lor_drafts = serializers.BooleanField()
