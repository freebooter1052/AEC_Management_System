from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsStaff
from apps.core import audit, repository
from apps.core.roles import STUDENT
from apps.students import services as student_services

from . import services
from .serializers import ChecklistSerializer, DocumentCreateSerializer, ReferenceSerializer, ReviewSerializer

DOCUMENT_SORT = [{"type": "desc"}, {"created_at": "desc"}]


def get_accessible_document(request, document_id: str) -> dict:
    doc = repository.get(document_id, "document")
    if doc is None:
        raise NotFound("Document not found.")
    if not services.can_access(request.user, doc):
        raise PermissionDenied("You do not have access to this document.")
    return doc


def target_student(request, student_id: str | None) -> dict:
    """Students always act on their own profile; staff name the student."""
    if request.user.role == STUDENT:
        student_id = request.user.profile_id
    if not student_id:
        raise ValidationError({"student_id": ["Choose a student."]})
    return student_services.get_accessible(request.user, student_id)


class DocumentListCreateView(APIView):
    """
    GET  /api/documents/ - documents the caller may see. Filters: ?student_id=, ?application_id=
         (`none` = general documents only), ?status= (comma-separated), ?document_type=, ?page=, ?page_size=
    POST /api/documents/ - add a `Required` document to a student's checklist.
    """

    def get(self, request):
        params = request.query_params
        selector = student_services.scope_to_students(
            request.user, {"type": "document", "created_at": {"$gt": None}}, params.get("student_id"))
        if params.get("application_id") == "none":
            selector["application_id"] = None
        elif params.get("application_id"):
            selector["application_id"] = params["application_id"]
        if params.get("status"):
            selector["status"] = {"$in": [s.strip() for s in params["status"].split(",") if s.strip()]}
        if params.get("document_type"):
            selector["document_type"] = params["document_type"]
        return Response(repository.paginate(request, selector, sort=DOCUMENT_SORT,
                                            serialize_page=services.serialize_page))

    def post(self, request):
        s = DocumentCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        student = target_student(request, data.get("student_id"))
        application = None
        if data.get("application_id"):
            application = repository.get(data["application_id"], "application")
            if application is None or application.get("student_id") != student["_id"]:
                raise ValidationError({"application_id": ["Application not found for this student."]})
        doc = services.build_document(student=student, document_type=data["document_type"],
                                      application=application, title=data.get("title", ""))
        services.add_event(doc, "Required", request.user)
        repository.save(doc)
        audit.record("document.created", request=request, actor=request.user, target_id=doc["_id"],
                     details={"student_id": student["_id"], "document_type": doc["document_type"]})
        return Response(services.serialize(doc), status=status.HTTP_201_CREATED)


class DocumentChecklistView(APIView):
    """POST /api/documents/checklist/ {student_id} - create the standard general-document checklist."""

    def post(self, request):
        s = ChecklistSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        student = target_student(request, s.validated_data.get("student_id"))
        created = services.ensure_checklist(student, services.CORE_DOCUMENTS, actor=request.user, request=request)
        return Response({"created": len(created), "results": services.serialize_page(created)},
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class DocumentSummaryView(APIView):
    """GET /api/documents/summary/?student_id= - counts by status for the caller's scope."""

    def get(self, request):
        selector = student_services.scope_to_students(request.user, {"type": "document"},
                                                      request.query_params.get("student_id"))
        return Response(services.summary(repository.find(selector, fields=["status"])))


class DocumentDetailView(APIView):
    """
    GET    /api/documents/<id>/ - anyone who can see the student.
    DELETE /api/documents/<id>/ - counsellors and admins remove a requirement (and its file).
    """

    def get_permissions(self):
        return [IsStaff()] if self.request.method == "DELETE" else super().get_permissions()

    def get(self, request, document_id):
        return Response(services.serialize(get_accessible_document(request, document_id)))

    def delete(self, request, document_id):
        doc = get_accessible_document(request, document_id)
        if doc["status"] == "Verified":
            raise ValidationError({"detail": "A verified document cannot be deleted. Mark it Expired instead."})
        repository.delete(doc)
        audit.record("document.deleted", request=request, actor=request.user, target_id=document_id,
                     details={"student_id": doc.get("student_id"), "document_type": doc.get("document_type")})
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentUploadView(APIView):
    """
    POST /api/documents/<id>/upload/ - multipart `file` (PDF, image or Word, max 5 MB), or JSON
         {"reference_url": "https://...", "filename": "..."} for a file kept elsewhere.
         The student or their counsellor/admin; sets the status to Uploaded.
    """

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, document_id):
        doc = get_accessible_document(request, document_id)
        upload = request.FILES.get("file")
        if upload is not None:
            doc = services.attach_file(doc, upload, actor=request.user, request=request)
        else:
            s = ReferenceSerializer(data=request.data)
            if not s.is_valid():
                raise ValidationError({"file": ["Choose a file to upload or give a link to it."], **s.errors})
            doc = services.attach_reference(doc, s.validated_data["reference_url"],
                                            s.validated_data.get("filename", ""), actor=request.user, request=request)
        return Response(services.serialize(doc))


class DocumentReviewView(APIView):
    """POST /api/documents/<id>/verify/ {status: Under Review|Verified|Rejected|Expired, remarks} - staff."""

    permission_classes = [IsStaff]

    def post(self, request, document_id):
        s = ReviewSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        doc = get_accessible_document(request, document_id)
        if request.data.get("rev"):
            doc["_rev"] = request.data["rev"]
        doc = services.review(doc, s.validated_data["status"], s.validated_data["remarks"],
                              actor=request.user, request=request)
        return Response(services.serialize(doc))


class DocumentFileView(APIView):
    """GET /api/documents/<id>/file/ - download the stored file (same audience as the document)."""

    def get(self, request, document_id):
        doc = get_accessible_document(request, document_id)
        found = services.file_content(doc)
        if found is None:
            raise NotFound("No file has been uploaded for this document.")
        content, content_type = found
        response = HttpResponse(content, content_type=content_type)
        disposition = "inline" if request.query_params.get("inline") else "attachment"
        response["Content-Disposition"] = f'{disposition}; filename="{services.clean_filename(doc.get("filename") or "document")}"'
        response["X-Content-Type-Options"] = "nosniff"
        return response
