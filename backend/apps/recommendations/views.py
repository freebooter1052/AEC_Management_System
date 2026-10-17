from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsStaff
from apps.core import repository
from apps.core.roles import STUDENT
from apps.core.vocab import RECOMMENDATION_STATUSES, RECOMMENDATION_TIERS
from apps.students import services as student_services

from . import services


class GenerateSerializer(serializers.Serializer):
    student_id = serializers.CharField(required=False, allow_blank=True, max_length=64)


class AddSerializer(serializers.Serializer):
    student_id = serializers.CharField(max_length=64)
    course_id = serializers.CharField(max_length=64)
    remarks = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class UpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=RECOMMENDATION_STATUSES, required=False)
    remarks = serializers.CharField(required=False, allow_blank=True, max_length=500)
    tier = serializers.ChoiceField(choices=["", *RECOMMENDATION_TIERS], required=False)
    rev = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not {"status", "remarks", "tier"} & set(attrs):
            raise ValidationError({"detail": "Nothing to change: send status, remarks or tier."})
        return attrs


def target_student(request, student_id: str | None) -> dict:
    """Students always act on their own profile; staff name a student they can access."""
    if request.user.role == STUDENT:
        student_id = request.user.profile_id
    if not student_id:
        raise ValidationError({"student_id": ["Choose a student."]})
    return student_services.get_accessible(request.user, student_id)


class RecommendationListView(APIView):
    """
    GET  /api/recommendations/?student_id=&status=&page=&page_size= - one student's recommendations
         (students: their own), Accepted first then by score; with the latest run and its freshness.
    POST /api/recommendations/ {student_id, course_id, remarks?} - staff add a course (scored, and refused
         when it fails a hard eligibility rule).
    """

    def get_permissions(self):
        return [IsStaff()] if self.request.method == "POST" else super().get_permissions()

    def get(self, request):
        params = request.query_params
        status_filter = params.get("status", "")
        if status_filter and status_filter not in RECOMMENDATION_STATUSES:
            raise ValidationError({"status": [f"Choose one of: {', '.join(RECOMMENDATION_STATUSES)}."]})
        student = target_student(request, params.get("student_id"))
        docs = services.for_student(student["_id"], status_filter)
        page, page_size = repository.page_params(request)
        start = (page - 1) * page_size
        run, fresh = services.run_summary(student)
        return Response({
            "count": len(docs), "page": page, "page_size": page_size,
            "total_pages": max(1, -(-len(docs) // page_size)),
            "results": services.serialize_page(docs[start:start + page_size]),
            "student": {"id": student["_id"], "full_name": student_services.full_name(student),
                        "profile_completion": (student.get("profile_completion") or {}).get("overall", 0)},
            "run": run, "freshness": fresh,
        })

    def post(self, request):
        s = AddSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        student = student_services.get_accessible(request.user, s.validated_data["student_id"])
        doc = services.add(student, s.validated_data["course_id"], remarks=s.validated_data["remarks"],
                           actor=request.user, request=request)
        return Response(services.serialize_page([doc])[0], status=status.HTTP_201_CREATED)


class RecommendationGenerateView(APIView):
    """
    POST /api/recommendations/generate/ {student_id?} - run the engine and store the results. Students
         refresh their own; counsellors their assigned students; admins anyone. Repeatable: it updates,
         never duplicates.
    """

    def post(self, request):
        s = GenerateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        student = target_student(request, s.validated_data.get("student_id"))
        services.generate(student, actor=request.user, request=request)
        docs = services.for_student(student["_id"])
        run, fresh = services.run_summary(student)
        page_size = repository.page_params(request)[1]
        return Response({"count": len(docs), "page": 1, "page_size": page_size,
                         "total_pages": max(1, -(-len(docs) // page_size)),
                         "results": services.serialize_page(docs[:page_size]), "run": run, "freshness": fresh})


class RecommendationDetailView(APIView):
    """
    GET   /api/recommendations/<id>/ - the student, their counsellor or an admin.
    PATCH /api/recommendations/<id>/ {status?, remarks?, tier?, rev?} - counsellors/admins review it.
    """

    def get_permissions(self):
        return [IsStaff()] if self.request.method == "PATCH" else super().get_permissions()

    def get(self, request, recommendation_id):
        return Response(services.serialize_page([services.get_accessible(request.user, recommendation_id)])[0])

    def patch(self, request, recommendation_id):
        s = UpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        doc = services.get_accessible(request.user, recommendation_id)
        if s.validated_data.get("rev"):
            doc["_rev"] = s.validated_data["rev"]
        doc = services.update(doc, s.validated_data, actor=request.user, request=request)
        return Response(services.serialize_page([doc])[0])
