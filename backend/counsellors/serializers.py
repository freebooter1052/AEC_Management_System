from rest_framework import serializers

from authentication.serializers import validate_password_strength

TEXT = {"required": False, "allow_blank": True}


class CounsellorSelfUpdateSerializer(serializers.Serializer):
    """Fields a counsellor may change on their own profile."""

    name = serializers.CharField(max_length=120, required=False)
    phone = serializers.RegexField(r"^(\+?[\d\s-]{6,20})?$", **TEXT)
    specialization = serializers.CharField(max_length=160, **TEXT)
    region = serializers.CharField(max_length=120, **TEXT)


class CounsellorAdminUpdateSerializer(CounsellorSelfUpdateSerializer):
    """Administrators can additionally set capacity and active status."""

    max_students = serializers.IntegerField(min_value=1, max_value=500, required=False)
    is_active = serializers.BooleanField(required=False)


class CounsellorCreateSerializer(CounsellorAdminUpdateSerializer):
    name = serializers.CharField(max_length=120)
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, validators=[validate_password_strength])
