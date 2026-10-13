from django.conf import settings
from rest_framework import serializers

from apps.core.roles import ALL_ROLES


def validate_password_strength(value: str) -> str:
    if len(value) < settings.AUTH_MIN_PASSWORD_LENGTH:
        raise serializers.ValidationError(f"Password must be at least {settings.AUTH_MIN_PASSWORD_LENGTH} characters.")
    if value.isdigit() or value.isalpha():
        raise serializers.ValidationError("Password must contain both letters and numbers.")
    return value


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)
    # Optional: the portal the user chose to sign in to. If given, it must match the account role.
    role = serializers.ChoiceField(choices=ALL_ROLES, required=False, allow_null=True)


class RegisterSerializer(serializers.Serializer):
    """Student self-registration (SRS 3.1). Counsellor/admin accounts are created by administrators."""

    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80)
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, validators=[validate_password_strength])
    dial_code = serializers.RegexField(r"^\+\d{1,4}$", required=False, allow_blank=True)
    phone = serializers.RegexField(r"^\d{6,15}$", required=False, allow_blank=True)
    citizenship = serializers.CharField(max_length=60, required=False, allow_blank=True)
    intended_level = serializers.CharField(max_length=60, required=False, allow_blank=True)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False, validators=[validate_password_strength])


class UserAdminUpdateSerializer(serializers.Serializer):
    is_active = serializers.BooleanField(required=False)
    full_name = serializers.CharField(max_length=160, required=False)
