from rest_framework import serializers

from apps.core import repository
from apps.core.vocab import COURSE_LEVELS, ENGLISH_TESTS

TEXT = {"required": False, "allow_blank": True}
NUM = {"required": False, "allow_null": True}

# Plausible overall-score ranges per English test, so a typo (65 for IELTS) is caught.
ENGLISH_RANGES = {"IELTS": (0, 9), "TOEFL": (0, 120), "PTE": (10, 90), "Duolingo": (10, 160), "Cambridge": (80, 230)}


class TuitionSerializer(serializers.Serializer):
    amount_per_year = serializers.IntegerField(min_value=0, max_value=10_000_000, **NUM)
    currency = serializers.RegexField(r"^[A-Z]{3}$", required=False, error_messages={"invalid": "Use a 3-letter code such as EUR."})

    def validate(self, attrs):
        if attrs.get("amount_per_year") is not None and not attrs.get("currency"):
            raise serializers.ValidationError({"currency": ["Give the currency of the tuition fee."]})
        return attrs


class EligibilitySerializer(serializers.Serializer):
    min_grade_pct = serializers.FloatField(min_value=0, max_value=100, **NUM)
    min_english = serializers.DictField(child=serializers.FloatField(), required=False)
    notes = serializers.CharField(max_length=500, **TEXT)

    def validate_min_english(self, value):
        for test, score in value.items():
            if test not in ENGLISH_TESTS:
                raise serializers.ValidationError(f"Unknown English test '{test}'. Use: {', '.join(ENGLISH_TESTS)}.")
            lo, hi = ENGLISH_RANGES[test]
            if not lo <= score <= hi:
                raise serializers.ValidationError(f"A {test} score must be between {lo} and {hi}.")
        return value


class CourseSerializer(serializers.Serializer):
    """Admin edits of a course (SRS 4.4). Top-level fields not sent are left as they are; `tuition` and
    `eligibility`, when sent, replace the stored object."""

    title = serializers.CharField(max_length=200, required=False)
    canonical_name = serializers.CharField(max_length=200, **TEXT)
    cluster = serializers.CharField(max_length=80, **TEXT)
    level = serializers.ChoiceField(choices=["", *COURSE_LEVELS], required=False)
    duration_months = serializers.IntegerField(min_value=1, max_value=96, **NUM)
    tuition = TuitionSerializer(required=False)
    eligibility = EligibilitySerializer(required=False)
    intake_ids = serializers.ListField(child=serializers.CharField(max_length=64), max_length=20, required=False,
                                       help_text="Intakes the course is offered in; empty = every agency intake.")
    is_active = serializers.BooleanField(required=False)
    rev = serializers.CharField(required=False, allow_blank=True)

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError("Give the course a title.")
        return value.strip()

    def validate_intake_ids(self, value):
        ids = list(dict.fromkeys(value))
        if ids:
            found = {i["_id"] for i in repository.find({"type": "intake", "_id": {"$in": ids}}, fields=["_id"])}
            unknown = [i for i in ids if i not in found]
            if unknown:
                raise serializers.ValidationError("Unknown intake: choose from the recorded intakes.")
        return ids


class CourseCreateSerializer(CourseSerializer):
    title = serializers.CharField(max_length=200)
