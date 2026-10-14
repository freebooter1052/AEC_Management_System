"""Input validation for document requirements, uploads and verification decisions."""

from django.core.validators import URLValidator
from rest_framework import serializers

from apps.core.vocab import DOCUMENT_STATUSES, DOCUMENT_TYPES


class DocumentCreateSerializer(serializers.Serializer):
    """POST /api/documents/ - add a requirement to a student's checklist."""

    student_id = serializers.CharField(required=False)  # staff; students always act on themselves
    document_type = serializers.ChoiceField(choices=DOCUMENT_TYPES)
    application_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    title = serializers.CharField(max_length=120, required=False, allow_blank=True)


class ChecklistSerializer(serializers.Serializer):
    student_id = serializers.CharField(required=False)


class ReferenceSerializer(serializers.Serializer):
    """JSON body of POST /api/documents/<id>/upload/ when the file lives elsewhere."""

    reference_url = serializers.URLField(max_length=500, validators=[URLValidator(schemes=["http", "https"])])
    filename = serializers.CharField(max_length=120, required=False, allow_blank=True)


class ReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[s for s in DOCUMENT_STATUSES if s not in ("Required", "Uploaded")])
    remarks = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
