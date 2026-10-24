from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdmin, IsCounsellor, IsStudent
from apps.core import audit, lookups, repository
from apps.core.roles import STUDENT
from apps.notifications import events
from apps.students import services as student_services

from . import gemini, prompts, services
from .serializers import (
    CommentSerializer, ConsentSerializer, DecisionSerializer, PrepareSerializer, ReferenceCreateSerializer, ReferenceUpdateSerializer,
    RestoreSerializer, ReviseSerializer, SettingsSerializer, StatementCreateSerializer, StatementUpdateSerializer,
    StatusSerializer, StudentRefSerializer,
)


def _student(request, student_id: str | None) -> dict:
    if request.user.role == STUDENT:
        student_id = request.user.profile_id
    if not student_id:
        raise ValidationError({"student_id": ["Choose a student."]})
    return student_services.get_accessible(request.user, student_id)


def _get(request, doc_type: str, doc_id: str) -> tuple[dict, dict]:
    doc = repository.get(doc_id, doc_type)
    student = services.student_of(doc) if doc else None
    if doc is None or student is None:
        raise NotFound("Not found.")
    if not services.can_view(request.user, doc, student):
        raise PermissionDenied("You do not have access to this record.")
    if request.method != "GET" and request.data.get("rev"):  # optimistic concurrency, as on profiles
        doc["_rev"] = request.data["rev"]
    return doc, student


def _statement_response(request, doc: dict, code=status.HTTP_200_OK) -> Response:
    return Response(services.serialize_statement(doc, request.user), status=code)


def _application_label(app: dict) -> str:
    snap = app.get("snapshot") or {}
    return f"{snap.get('course_title', 'Course')} - {snap.get('university_name', '')}".strip(" -")


class WorkspaceView(APIView):
    """
    GET /api/writing/?student_id= - everything the SOP & LOR page shows for one student: consent, whether AI
        drafting is available, the guided questions, the student's applications, statements and referees.
        Students always get their own (shared SOPs only); staff name the student.
    """

    def get(self, request):
        student = _student(request, request.query_params.get("student_id"))
        user = request.user
        statements = [s for s in services.list_for_student("statement", student["_id"]) if services.can_view(user, s, student)]
        refs = services.list_for_student("reference", student["_id"])
        docs = {d["_id"]: d for d in repository.get_many(r.get("document_id") for r in refs)}
        apps = sorted(repository.find({"type": "application", "student_id": {"$in": [student["_id"]]}},
                                      fields=["_id", "snapshot", "status", "created_at"]),
                      key=lambda a: a.get("created_at") or "", reverse=True)
        return Response({
            "student": {"id": student["_id"], "full_name": student_services.full_name(student),
                        "counsellor_name": lookups.names_by_id([student.get("counsellor_id")]).get(student.get("counsellor_id"))},
            "consent": services.consent_state(student),
            "can_edit": services.can_edit(user, student),
            "ai_available": gemini.is_configured(),
            "settings": services.get_settings(),
            "questions": [{"key": k, "question": q, "hint": h, "required": k in prompts.REQUIRED_SOP_KEYS}
                          for k, q, h in prompts.SOP_QUESTIONS],
            "applications": [{"id": a["_id"], "label": _application_label(a), "status": a.get("status")} for a in apps],
            "statements": [services.statement_row(s) for s in statements],
            "references": [services.serialize_reference(r, docs.get(r.get("document_id")), statements) for r in refs],
        })


class ConsentView(APIView):
    """GET/PUT /api/writing/consent/ {granted} - the signed-in student's own choice about AI-assisted writing."""

    permission_classes = [IsStudent]

    def get(self, request):
        return Response(services.consent_state(_student(request, None)))

    def put(self, request):
        s = ConsentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        student = services.set_consent(_student(request, None), s.validated_data["granted"], actor=request.user, request=request)
        return Response(services.consent_state(student))


class ConsentRequestView(APIView):
    """POST /api/writing/consent/request/ {student_id} - the counsellor asks the student (at most once a day)."""

    permission_classes = [IsCounsellor]

    def post(self, request):
        s = StudentRefSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        student = _student(request, s.validated_data["student_id"])
        if services.consent_state(student)["granted"]:
            return Response({"sent": False, "detail": "The student has already agreed."})
        sent = events.ai_consent_requested(student, repository.today().isoformat())
        if sent:
            audit.record("writing.consent_requested", request=request, actor=request.user, target_id=student["_id"])
        return Response({"sent": sent, "detail": "Request sent." if sent else "You already asked today."})


class SettingsView(APIView):
    """GET /api/writing/settings/ (anyone signed in); PATCH {allow_lor_drafts} - administrators."""

    def get_permissions(self):
        return [IsAdmin()] if self.request.method == "PATCH" else super().get_permissions()

    def get(self, request):
        return Response({**services.get_settings(), "ai_available": gemini.is_configured()})

    def patch(self, request):
        s = SettingsSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response({**services.update_settings(s.validated_data, actor=request.user, request=request),
                         "ai_available": gemini.is_configured()})


class StatementCreateView(APIView):
    """POST /api/writing/statements/ {student_id, application_id?, title?, word_limit?} - the student's counsellor."""

    permission_classes = [IsCounsellor]

    def post(self, request):
        s = StatementCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        student = _student(request, s.validated_data["student_id"])
        doc = services.create_statement(student, s.validated_data, actor=request.user, request=request)
        return _statement_response(request, doc, status.HTTP_201_CREATED)


class StatementDetailView(APIView):
    """
    GET    /api/writing/statements/<id>/ - the counsellor/admin; the student once it is shared.
    PATCH  {title?, word_limit?, answers?, content?, note?, rev} - the counsellor; a changed text is a new version.
    DELETE - the counsellor.
    """

    def get(self, request, statement_id):
        doc, _ = _get(request, "statement", statement_id)
        return _statement_response(request, doc)

    def patch(self, request, statement_id):
        doc, student = _get(request, "statement", statement_id)
        s = StatementUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        doc = services.update_statement(doc, student, s.validated_data, actor=request.user, request=request)
        return _statement_response(request, doc)

    def delete(self, request, statement_id):
        doc, student = _get(request, "statement", statement_id)
        services.require_edit(request.user, student)
        repository.delete(doc)
        audit.record("writing.statement_deleted", request=request, actor=request.user, target_id=statement_id,
                     details={"student_id": student["_id"], "kind": doc.get("kind")})
        return Response(status=status.HTTP_204_NO_CONTENT)


class StatementActionView(APIView):
    """
    POST /api/writing/statements/<id>/<action>/ - the student's counsellor (comments: the student too).
        generate  write a first draft from the guided answers (Gemini)
        revise    {instruction} improve the current text (Gemini)
        review    feedback on strengths, improvements and missing facts (Gemini; the text is not changed)
        status    {status: Draft|Shared|Final}
        restore   {version}
        comments  {text}
    """

    def post(self, request, statement_id, action):
        doc, student = _get(request, "statement", statement_id)
        actor = request.user
        if action == "generate":
            doc = services.generate_draft(doc, student, actor=actor, request=request)
        elif action == "revise":
            s = ReviseSerializer(data=request.data)
            s.is_valid(raise_exception=True)
            doc = services.revise(doc, student, s.validated_data["instruction"], actor=actor, request=request)
        elif action == "review":
            doc = services.critique(doc, student, actor=actor, request=request)
        elif action == "status":
            s = StatusSerializer(data=request.data)
            s.is_valid(raise_exception=True)
            doc = services.change_status(doc, student, s.validated_data["status"], actor=actor, request=request)
        elif action == "restore":
            s = RestoreSerializer(data=request.data)
            s.is_valid(raise_exception=True)
            services.require_edit(actor, student)
            doc = services.restore_version(doc, student, s.validated_data["version"], actor=actor, request=request)
        elif action == "decision":
            s = DecisionSerializer(data=request.data)
            s.is_valid(raise_exception=True)
            doc = services.decide_statement(doc, student, s.validated_data["decision"], s.validated_data.get("note", ""),
                                            actor=actor, request=request)
        elif action == "comments":
            s = CommentSerializer(data=request.data)
            s.is_valid(raise_exception=True)
            doc = services.add_comment(doc, student, s.validated_data["text"], actor=actor, request=request)
        else:
            raise NotFound("Unknown action.")
        return _statement_response(request, doc)


def _reference_response(ref: dict, student: dict, user, code=status.HTTP_200_OK) -> Response:
    statements = [s for s in services.list_for_student("statement", student["_id"]) if services.can_view(user, s, student)]
    doc = repository.get(ref.get("document_id"), "document") if ref.get("document_id") else None
    return Response(services.serialize_reference(ref, doc, statements), status=code)


class ReferenceCreateView(APIView):
    """POST /api/writing/references/ {student_id, application_id?, referee{name,...}, highlights?, due_date?}
    - the student's counsellor; also adds (or claims) the LOR document the letter will be uploaded to."""

    permission_classes = [IsCounsellor]

    def post(self, request):
        s = ReferenceCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        student = _student(request, s.validated_data["student_id"])
        ref = services.create_reference(student, s.validated_data, actor=request.user, request=request)
        return _reference_response(ref, student, request.user, status.HTTP_201_CREATED)


class ReferenceDetailView(APIView):
    """GET /api/writing/references/<id>/; PATCH {referee?, highlights?, due_date?, status?, rev} - the counsellor."""

    def get(self, request, reference_id):
        ref, student = _get(request, "reference", reference_id)
        return _reference_response(ref, student, request.user)

    def patch(self, request, reference_id):
        ref, student = _get(request, "reference", reference_id)
        s = ReferenceUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        ref = services.update_reference(ref, student, s.validated_data, actor=request.user, request=request)
        return _reference_response(ref, student, request.user)


class ReferenceDecisionView(APIView):
    """POST /api/writing/references/<id>/decision/ {decision: Approved|Changes requested, note?} - the student."""

    permission_classes = [IsStudent]

    def post(self, request, reference_id):
        ref, student = _get(request, "reference", reference_id)
        s = DecisionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        ref = services.decide_reference(ref, student, s.validated_data["decision"], s.validated_data.get("note", ""),
                                        actor=request.user, request=request)
        return _reference_response(ref, student, request.user)


class ReferencePrepareView(APIView):
    """POST /api/writing/references/<id>/prepare/ {kind: lor_brief|lor_draft} - Gemini writes the referee brief
    (or, when allowed, a starting draft for the referee). Returns the statement holding it."""

    permission_classes = [IsCounsellor]

    def post(self, request, reference_id):
        ref, student = _get(request, "reference", reference_id)
        s = PrepareSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        doc = services.prepare_for_referee(ref, student, s.validated_data["kind"], actor=request.user, request=request)
        return _statement_response(request, doc)
