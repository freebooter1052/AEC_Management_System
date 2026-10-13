"""
Input validation for student documents (SRS 2.5: validate required fields
before creating or updating documents). Every field is optional so a
profile can be completed step by step; PATCH requests are merged into the
stored document.
"""

from datetime import date

from rest_framework import serializers

from apps.accounts.serializers import validate_password_strength

OPTIONAL = {"required": False}
TEXT = {"required": False, "allow_blank": True}
NUM = {"required": False, "allow_null": True}


class PhoneSerializer(serializers.Serializer):
    dial_code = serializers.RegexField(r"^(\+\d{1,4})?$", **TEXT)
    number = serializers.RegexField(r"^(\d{6,15})?$", **TEXT)


class AddressSerializer(serializers.Serializer):
    line1 = serializers.CharField(max_length=200, **TEXT)
    city = serializers.CharField(max_length=80, **TEXT)
    state = serializers.CharField(max_length=80, **TEXT)
    country = serializers.CharField(max_length=80, **TEXT)
    postal_code = serializers.CharField(max_length=20, **TEXT)


class PersonalSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=80, required=False)
    last_name = serializers.CharField(max_length=80, required=False)
    preferred_name = serializers.CharField(max_length=80, **TEXT)
    phone = PhoneSerializer(**OPTIONAL)
    date_of_birth = serializers.DateField(**NUM)
    gender = serializers.CharField(max_length=30, **TEXT)
    citizenship = serializers.CharField(max_length=60, **TEXT)
    address = AddressSerializer(**OPTIONAL)

    def validate_date_of_birth(self, value):
        if value is None:
            return None
        today = date.today()
        if value >= today or value.year < today.year - 100:
            raise serializers.ValidationError("Enter a valid date of birth.")
        return value.isoformat()  # stored as an ISO string in CouchDB


class EnglishTestSerializer(serializers.Serializer):
    test_type = serializers.ChoiceField(choices=["", "IELTS", "TOEFL", "PTE", "Duolingo", "Cambridge", "Other"], **OPTIONAL)
    overall = serializers.FloatField(min_value=0, max_value=200, **NUM)
    listening = serializers.FloatField(min_value=0, max_value=200, **NUM)
    reading = serializers.FloatField(min_value=0, max_value=200, **NUM)
    writing = serializers.FloatField(min_value=0, max_value=200, **NUM)
    speaking = serializers.FloatField(min_value=0, max_value=200, **NUM)


class AcademicSerializer(serializers.Serializer):
    degree = serializers.CharField(max_length=120, **TEXT)
    institution = serializers.CharField(max_length=160, **TEXT)
    cgpa = serializers.FloatField(min_value=0, max_value=100, **NUM)
    gpa_scale = serializers.FloatField(min_value=1, max_value=100, **NUM)
    graduation_year = serializers.IntegerField(min_value=1950, max_value=2100, **NUM)
    work_experience_years = serializers.FloatField(min_value=0, max_value=60, **NUM)
    gre_status = serializers.CharField(max_length=60, **TEXT)
    english_test = EnglishTestSerializer(**OPTIONAL)

    def validate(self, attrs):
        cgpa, scale = attrs.get("cgpa"), attrs.get("gpa_scale")
        if cgpa is not None and scale is not None and cgpa > scale:
            raise serializers.ValidationError({"cgpa": "CGPA cannot exceed the GPA scale."})
        return attrs


class BudgetSerializer(serializers.Serializer):
    min = serializers.IntegerField(min_value=0, **NUM)
    max = serializers.IntegerField(min_value=0, **NUM)
    currency = serializers.RegexField(r"^[A-Z]{3}$", required=False)

    def validate(self, attrs):
        lo, hi = attrs.get("min"), attrs.get("max")
        if lo is not None and hi is not None and lo > hi:
            raise serializers.ValidationError({"min": "Minimum budget cannot exceed the maximum."})
        return attrs


class PreferencesSerializer(serializers.Serializer):
    countries = serializers.ListField(child=serializers.CharField(max_length=60), max_length=10, **OPTIONAL)
    course_areas = serializers.ListField(child=serializers.CharField(max_length=80), max_length=10, **OPTIONAL)
    degree_level = serializers.ChoiceField(
        choices=["", "Diploma", "Bachelors", "Masters", "MBA", "PhD", "Certificate"], **OPTIONAL)
    intake = serializers.CharField(max_length=40, **TEXT)
    budget = BudgetSerializer(**OPTIONAL)
    requires_scholarship = serializers.BooleanField(**OPTIONAL)


class StudentProfileSerializer(serializers.Serializer):
    """Body of PATCH /api/students/me/ and PATCH /api/students/<id>/."""

    personal = PersonalSerializer(**OPTIONAL)
    academic = AcademicSerializer(**OPTIONAL)
    preferences = PreferencesSerializer(**OPTIONAL)


class StudentCreateSerializer(StudentProfileSerializer):
    """Body of POST /api/students/ - an administrator creates the account and profile together."""

    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80)
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, validators=[validate_password_strength])
    counsellor_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class AssignCounsellorSerializer(serializers.Serializer):
    counsellor_id = serializers.CharField(allow_null=True, allow_blank=True)
