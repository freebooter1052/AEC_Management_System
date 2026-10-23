"""
SOP and LOR writing: guided SOP drafts with Gemini, referee (LOR) tracking and referee briefs.

    {
      "_id": "statement_1a2b3c4d5e6f", "type": "statement",
      "student_id": "student_...", "application_id": "application_..." | null,   # null = a general SOP
      "counsellor_id": "counsellor_..." | null,           # the student's counsellor when created
      "reference_id": "reference_..." | null,              # set for lor_brief / lor_draft
      "kind": "sop" | "lor_brief" | "lor_draft",
      "title": "SOP - Data Science at TU Munich", "word_limit": 1000,
      "status": "Draft" | "Shared" | "Final",               # Shared/Final SOPs are visible to the student
      "answers": {"motivation": "...", "why_course": "...", ...},   # the guided interview (prompts.SOP_QUESTIONS)
      "content": "current text", "ai_assisted": true,
      "versions": [{"n": 3, "content": "...", "source": "ai_draft" | "ai_revise" | "manual" | "restore",
                    "note": "Make it more concise", "word_count": 812, "at": "...", "by": "user_..."}],   # newest last, at most MAX_VERSIONS
      "feedback": {"summary": "...", "strengths": [], "improvements": [], "missing": [], "at": "...", "version": 3} | null,
      "comments": [{"id": "c1", "text": "...", "by": "user_...", "by_role": "student", "at": "..."}],
      "created_at": "...", "updated_at": "..."
    }

    {
      "_id": "reference_1a2b3c4d5e6f", "type": "reference",
      "student_id": "student_...", "application_id": "application_..." | null, "counsellor_id": "counsellor_..." | null,
      "referee": {"name": "Dr. Priya Rao", "title": "Associate Professor", "institution": "...",
                  "email": "...", "relationship": "Final-year project supervisor"},
      "highlights": "What the referee knows about the student",
      "due_date": "2026-11-30" | null,
      "status": "Planned" | "Requested" | "Cancelled",
      "document_id": "document_...",                       # the LOR document the letter is uploaded to
      "requested_at": "..." | null, "created_at": "...", "updated_at": "..."
    }

A reference's `stage` adds "Received" and "Verified", read from its LOR document, so the upload and
verification flow in apps/documents is the only place a letter's status changes.

AI drafting is for counsellors only, and only after the student has agreed (`student.ai_consent`).
Letters themselves are written by referees: the assistant prepares a brief of talking points, and a
starting draft for the referee only when an administrator has allowed it (`setting_writing`).
"""

import json
import re

from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core import audit, lookups, repository
from apps.core.roles import ADMIN, COUNSELLOR, STUDENT
from apps.documents import services as document_services
from apps.notifications import events
from apps.students import services as student_services

from . import gemini, prompts

MAX_VERSIONS = 20
MAX_COMMENTS = 200
DEFAULT_WORD_LIMIT = 1000
STUDENT_VISIBLE = ("Shared", "Final")
SETTINGS_ID = "setting_writing"
DEFAULT_SETTINGS = {"allow_lor_drafts": False}
_WORD = re.compile(r"\S+")


def word_count(text: str) -> int:
    return len(_WORD.findall(text or ""))


def placeholders(text: str) -> int:
    """How many `[ADD: ...]` gaps are still in the text."""
    return len(re.findall(r"\[ADD:[^\]]*\]", text or ""))


# ---------------------------------------------------------------------------
# Consent (the student decides; nothing is sent to Gemini without it)
# ---------------------------------------------------------------------------
def consent_state(student: dict) -> dict:
    c = student.get("ai_consent") or {}
    return {"granted": bool(c.get("granted")), "granted_at": c.get("granted_at"), "withdrawn_at": c.get("withdrawn_at")}


def set_consent(student: dict, granted: bool, *, actor, request=None) -> dict:
    now = repository.now_iso()
    c = dict(student.get("ai_consent") or {})
    if bool(c.get("granted")) == granted:
        return student
    c["granted"] = granted
    c["granted_at" if granted else "withdrawn_at"] = now
    student["ai_consent"] = c
    student["updated_at"] = now
    repository.save(student)
    audit.record("writing.consent_granted" if granted else "writing.consent_withdrawn",
                 request=request, actor=actor, target_id=student["_id"])
    return student


# ---------------------------------------------------------------------------
# Admin settings (one document)
# ---------------------------------------------------------------------------
def get_settings() -> dict:
    doc = repository.get(SETTINGS_ID, "setting") or {}
    return {**DEFAULT_SETTINGS, **{k: doc[k] for k in DEFAULT_SETTINGS if k in doc}}


def update_settings(changes: dict, *, actor, request=None) -> dict:
    doc = repository.get(SETTINGS_ID, "setting") or {"_id": SETTINGS_ID, "type": "setting", "name": "writing",
                                                      "created_at": repository.now_iso()}
    doc.update({k: v for k, v in changes.items() if k in DEFAULT_SETTINGS})
    doc["updated_at"] = repository.now_iso()
    doc["updated_by"] = getattr(actor, "id", None)
    repository.save(doc)
    audit.record("writing.settings_updated", request=request, actor=actor, target_id=SETTINGS_ID, details=changes)
    return get_settings()


# ---------------------------------------------------------------------------
# Access (through the owning student)
# ---------------------------------------------------------------------------
def student_of(doc: dict) -> dict | None:
    return repository.get(doc.get("student_id"), "student")


def can_view(user, doc: dict, student: dict | None = None) -> bool:
    student = student or student_of(doc)
    if student is None or not student_services.can_access(user, student):
        return False
    if user.role == STUDENT and doc.get("type") == "statement":
        return doc.get("kind") == "sop" and doc.get("status") in STUDENT_VISIBLE
    return True


def can_edit(user, student: dict) -> bool:
    """Writing work is done by the student's own counsellor; admins oversee it read-only."""
    return user.role == COUNSELLOR and student_services.can_access(user, student)


def require_edit(user, student: dict) -> None:
    if not can_edit(user, student):
        raise PermissionDenied("Only the student's counsellor can change SOPs and referee letters.")


def require_ai(user, student: dict) -> None:
    require_edit(user, student)
    if not consent_state(student)["granted"]:
        raise PermissionDenied("The student has not agreed to AI-assisted writing yet. "
                               "Ask them to turn it on under SOP & LOR, or write the text by hand.")
    if not gemini.is_configured():
        raise gemini.AssistantUnavailable("AI drafting is not set up on this server. "
                                          "An administrator needs to add a Gemini API key.")


def application_for(student: dict, application_id: str | None) -> dict | None:
    if not application_id:
        return None
    app = repository.get(application_id, "application")
    if app is None or app.get("student_id") != student["_id"]:
        raise ValidationError({"application_id": ["Application not found for this student."]})
    return app


def list_for_student(doc_type: str, student_id: str) -> list[dict]:
    docs = repository.find({"type": doc_type, "student_id": {"$in": [student_id]}})
    return sorted(docs, key=lambda d: d.get("created_at") or "", reverse=True)


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------
def default_title(kind: str, application: dict | None, reference: dict | None = None) -> str:
    snap = (application or {}).get("snapshot") or {}
    target = f"{snap.get('course_title')} at {snap.get('university_name')}" if snap.get("course_title") else ""
    if kind == "sop":
        return f"SOP - {target}" if target else "SOP - general"
    name = ((reference or {}).get("referee") or {}).get("name", "referee")
    return f"{'Brief' if kind == 'lor_brief' else 'Starting draft'} for {name}"


def build_statement(*, student: dict, kind: str = "sop", application: dict | None = None, title: str = "",
                    word_limit: int = DEFAULT_WORD_LIMIT, reference: dict | None = None) -> dict:
    now = repository.now_iso()
    return {
        "_id": repository.new_id("statement"),
        "type": "statement",
        "student_id": student["_id"],
        "application_id": application["_id"] if application else None,
        "counsellor_id": student.get("counsellor_id"),
        "reference_id": reference["_id"] if reference else None,
        "kind": kind,
        "title": (title or "").strip() or default_title(kind, application, reference),
        "word_limit": word_limit,
        "status": "Draft",
        "answers": {},
        "content": "",
        "ai_assisted": False,
        "versions": [],
        "feedback": None,
        "comments": [],
        "created_at": now,
        "updated_at": now,
    }


def add_version(doc: dict, content: str, source: str, actor, note: str = "") -> None:
    versions = doc.setdefault("versions", [])
    n = (versions[-1]["n"] + 1) if versions else 1
    versions.append({"n": n, "content": content, "source": source, "note": note[:200],
                     "word_count": word_count(content), "at": repository.now_iso(), "by": getattr(actor, "id", None)})
    del versions[:-MAX_VERSIONS]
    doc["content"] = content
    if source.startswith("ai_"):
        doc["ai_assisted"] = True


def create_statement(student: dict, data: dict, *, actor, request=None) -> dict:
    require_edit(actor, student)
    application = application_for(student, data.get("application_id"))
    doc = build_statement(student=student, application=application, title=data.get("title", ""),
                          word_limit=data.get("word_limit") or DEFAULT_WORD_LIMIT)
    repository.save(doc)
    audit.record("writing.statement_created", request=request, actor=actor, target_id=doc["_id"],
                 details={"student_id": student["_id"], "kind": doc["kind"]})
    return doc


def update_statement(doc: dict, student: dict, data: dict, *, actor, request=None) -> dict:
    """Manual edits: title, word limit, interview answers and the text (a changed text is a new version)."""
    require_edit(actor, student)
    if doc["status"] == "Final" and "content" in data:
        raise ValidationError({"content": ["This statement is final. Move it back to draft to edit the text."]})
    for key in ("title", "word_limit"):
        if key in data:
            doc[key] = data[key]
    if "answers" in data:
        doc["answers"] = {**(doc.get("answers") or {}),
                          **{k: v.strip() for k, v in data["answers"].items() if k in prompts.SOP_KEYS}}
    if "content" in data and data["content"] != doc.get("content", ""):
        add_version(doc, data["content"], "manual", actor, data.get("note", ""))
    doc["updated_at"] = repository.now_iso()
    return repository.save(doc)


TRANSITIONS = {"Draft": ("Shared", "Final"), "Shared": ("Draft", "Final"), "Final": ("Draft",)}


def change_status(doc: dict, student: dict, new_status: str, *, actor, request=None) -> dict:
    require_edit(actor, student)
    if new_status not in TRANSITIONS.get(doc["status"], ()):
        raise ValidationError({"status": [f"A {doc['status'].lower()} statement cannot move to {new_status}."]})
    if doc["kind"] != "sop" and new_status == "Shared":
        raise ValidationError({"status": ["Referee briefs and drafts are not shared with the student."]})
    if new_status in ("Shared", "Final") and not (doc.get("content") or "").strip():
        raise ValidationError({"status": ["Write or generate the text first."]})
    old = doc["status"]
    doc["status"] = new_status
    doc["updated_at"] = repository.now_iso()
    repository.save(doc)
    audit.record("writing.statement_status", request=request, actor=actor, target_id=doc["_id"],
                 details={"from": old, "to": new_status})
    if new_status == "Shared" and doc["kind"] == "sop":
        events.statement_shared(doc, student)
    return doc


def restore_version(doc: dict, student: dict, n: int, *, actor, request=None) -> dict:
    found = next((v for v in doc.get("versions") or [] if v["n"] == n), None)
    if found is None:
        raise ValidationError({"version": ["That version is no longer kept."]})
    return update_statement(doc, student, {"content": found["content"], "note": f"Restored version {n}"},
                            actor=actor, request=request) if found["content"] != doc.get("content") else doc


def add_comment(doc: dict, student: dict, text: str, *, actor, request=None) -> dict:
    if actor.role == ADMIN:
        raise PermissionDenied("Comments are between the student and their counsellor.")
    if actor.role == STUDENT and doc.get("status") not in STUDENT_VISIBLE:
        raise PermissionDenied("You can comment once your counsellor shares the draft.")
    comments = doc.setdefault("comments", [])
    if len(comments) >= MAX_COMMENTS:
        raise ValidationError({"text": ["This statement has reached the comment limit."]})
    comment = {"id": f"c{len(comments) + 1}", "text": text.strip(), "by": actor.id, "by_role": actor.role,
               "at": repository.now_iso()}
    comments.append(comment)
    doc["updated_at"] = comment["at"]
    repository.save(doc)
    events.statement_commented(doc, student, comment)
    return doc


# ---------------------------------------------------------------------------
# AI actions
# ---------------------------------------------------------------------------
def _ask(action: str, system: str, prompt: str, *, actor, request, target_id: str, json_output: bool = False):
    result = gemini.get_client().generate(system=system, prompt=prompt, json_output=json_output)
    # The audit keeps who/what/how much, never the prompt or the reply (they hold student data).
    audit.record(f"writing.ai_{action}", request=request, actor=actor, target_id=target_id,
                 details={"model": result.model, "tokens": result.usage})
    return result


def generate_draft(doc: dict, student: dict, *, actor, request=None) -> dict:
    require_ai(actor, student)
    if doc["kind"] != "sop":
        raise ValidationError({"detail": "Use the referee panel to prepare briefs and letter drafts."})
    missing = [q for k, q, _ in prompts.SOP_QUESTIONS if k in prompts.REQUIRED_SOP_KEYS
               and not (doc.get("answers") or {}).get(k, "").strip()]
    if missing:
        raise ValidationError({"answers": [f"Answer these questions first: {'; '.join(missing)}."]})
    application = application_for(student, doc.get("application_id"))
    system, prompt = prompts.sop_draft(student, application, doc.get("answers") or {}, doc["word_limit"])
    result = _ask("draft", system, prompt, actor=actor, request=request, target_id=doc["_id"])
    add_version(doc, result.text, "ai_draft", actor, "First draft")
    if doc["status"] == "Final":
        doc["status"] = "Draft"
    doc["updated_at"] = repository.now_iso()
    return repository.save(doc)


def revise(doc: dict, student: dict, instruction: str, *, actor, request=None) -> dict:
    require_ai(actor, student)
    if not (doc.get("content") or "").strip():
        raise ValidationError({"detail": "There is no text to improve yet."})
    if doc["status"] == "Final":
        raise ValidationError({"detail": "This statement is final. Move it back to draft to change it."})
    system, prompt = prompts.revise(doc["content"], instruction, doc["word_limit"])
    result = _ask("revise", system, prompt, actor=actor, request=request, target_id=doc["_id"])
    add_version(doc, result.text, "ai_revise", actor, instruction)
    doc["updated_at"] = repository.now_iso()
    return repository.save(doc)


def _str_list(value) -> list[str]:
    return [str(v).strip()[:400] for v in value if str(v).strip()][:5] if isinstance(value, list) else []


def critique(doc: dict, student: dict, *, actor, request=None) -> dict:
    require_ai(actor, student)
    if word_count(doc.get("content")) < 50:
        raise ValidationError({"detail": "Write at least 50 words before asking for a review."})
    label = "Statement of Purpose" if doc["kind"] == "sop" else "recommendation letter brief"
    system, prompt = prompts.critique(doc["content"], doc["word_limit"], label)
    result = _ask("review", system, prompt, actor=actor, request=request, target_id=doc["_id"], json_output=True)
    try:
        data = json.loads(result.text.strip().removeprefix("```json").removesuffix("```"))
    except ValueError:
        data = {"summary": result.text[:600]}
    if not isinstance(data, dict):
        data = {}
    versions = doc.get("versions") or []
    doc["feedback"] = {"summary": str(data.get("summary", "")).strip()[:600],
                       "strengths": _str_list(data.get("strengths")), "improvements": _str_list(data.get("improvements")),
                       "missing": _str_list(data.get("missing")), "at": repository.now_iso(),
                       "version": versions[-1]["n"] if versions else None}
    doc["updated_at"] = repository.now_iso()
    return repository.save(doc)


# ---------------------------------------------------------------------------
# Referees (LOR)
# ---------------------------------------------------------------------------
def _claimable_lor(student: dict, application: dict | None) -> dict | None:
    """An untitled `Required` LOR from the application checklist that no referee has claimed yet."""
    claimed = {r.get("document_id") for r in list_for_student("reference", student["_id"])}
    for d in repository.find({"type": "document", "student_id": student["_id"], "document_type": "LOR",
                              "application_id": application["_id"] if application else None}):
        if d["_id"] not in claimed and d.get("status") == "Required" and not d.get("title"):
            return d
    return None


def create_reference(student: dict, data: dict, *, actor, request=None) -> dict:
    require_edit(actor, student)
    application = application_for(student, data.get("application_id"))
    now = repository.now_iso()
    ref = {
        "_id": repository.new_id("reference"),
        "type": "reference",
        "student_id": student["_id"],
        "application_id": application["_id"] if application else None,
        "counsellor_id": student.get("counsellor_id"),
        "referee": {k: (data["referee"].get(k) or "").strip() for k in ("name", "title", "institution", "email", "relationship")},
        "highlights": (data.get("highlights") or "").strip(),
        "due_date": data.get("due_date").isoformat() if data.get("due_date") else None,
        "status": "Planned",
        "document_id": None,
        "requested_at": None,
        "created_at": now,
        "updated_at": now,
    }
    title = f"LOR - {ref['referee']['name']}"[:120]
    doc = _claimable_lor(student, application)
    if doc is not None:
        doc["title"] = title
        doc["updated_at"] = now
        repository.save(doc)
    else:
        doc = document_services.build_document(student=student, document_type="LOR", application=application, title=title)
        document_services.add_event(doc, "Required", actor)
        repository.save(doc)
    ref["document_id"] = doc["_id"]
    repository.save(ref)
    audit.record("writing.reference_created", request=request, actor=actor, target_id=ref["_id"],
                 details={"student_id": student["_id"], "document_id": doc["_id"]})
    return ref


def update_reference(ref: dict, student: dict, data: dict, *, actor, request=None) -> dict:
    require_edit(actor, student)
    if "referee" in data:
        ref["referee"] = {**ref["referee"], **{k: (v or "").strip() for k, v in data["referee"].items()}}
    if "highlights" in data:
        ref["highlights"] = data["highlights"].strip()
    if "due_date" in data:
        ref["due_date"] = data["due_date"].isoformat() if data["due_date"] else None
    if "status" in data and data["status"] != ref["status"]:
        if ref["status"] == "Cancelled":
            raise ValidationError({"status": ["This referee was cancelled. Add them again if needed."]})
        ref["status"] = data["status"]
        if data["status"] == "Requested":
            ref["requested_at"] = repository.now_iso()
        if data["status"] == "Cancelled":
            _drop_empty_lor(ref)
        audit.record("writing.reference_status", request=request, actor=actor, target_id=ref["_id"],
                     details={"to": data["status"]})
    ref["updated_at"] = repository.now_iso()
    return repository.save(ref)


def _drop_empty_lor(ref: dict) -> None:
    """A cancelled referee's letter slot is removed if nothing was uploaded, so it no longer blocks submission."""
    doc = repository.get(ref.get("document_id"), "document")
    if doc is not None and doc.get("status") == "Required":
        repository.delete(doc)
        ref["document_id"] = None


def stage(ref: dict, doc: dict | None) -> str:
    if ref["status"] == "Cancelled":
        return "Cancelled"
    status = (doc or {}).get("status")
    if status == "Verified":
        return "Verified"
    if status in ("Uploaded", "Under Review"):
        return "Received"
    return ref["status"]


def _ref_statement(ref: dict, student: dict, kind: str, application: dict | None) -> dict:
    existing = next((s for s in list_for_student("statement", student["_id"])
                     if s.get("reference_id") == ref["_id"] and s.get("kind") == kind), None)
    return existing or build_statement(student=student, kind=kind, application=application, reference=ref,
                                       word_limit=350 if kind == "lor_brief" else 500)


def prepare_for_referee(ref: dict, student: dict, kind: str, *, actor, request=None) -> dict:
    """Generate (again) the referee brief, or - when an administrator allows it - a starting draft."""
    require_ai(actor, student)
    if ref["status"] == "Cancelled":
        raise ValidationError({"detail": "This referee was cancelled."})
    if kind == "lor_draft" and not get_settings()["allow_lor_drafts"]:
        raise PermissionDenied("Letter drafts are turned off. Referees write their own letters from the brief.")
    application = application_for(student, ref.get("application_id"))
    doc = _ref_statement(ref, student, kind, application)
    builder = prompts.lor_brief if kind == "lor_brief" else prompts.lor_draft
    system, prompt = builder(student, application, ref)
    result = _ask(kind, system, prompt, actor=actor, request=request, target_id=ref["_id"])
    add_version(doc, result.text, "ai_draft", actor, "Brief" if kind == "lor_brief" else "Starting draft")
    doc["updated_at"] = repository.now_iso()
    return repository.save(doc)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def serialize_statement(doc: dict, user, names: dict | None = None) -> dict:
    data = repository.public(doc)
    names = names if names is not None else lookups.names_by_id(
        [doc.get("student_id")] + [c.get("by") for c in doc.get("comments") or []])
    data["student_name"] = names.get(doc.get("student_id"), "")
    data["word_count"] = word_count(doc.get("content"))
    data["placeholders"] = placeholders(doc.get("content"))
    data["comments"] = [{**c, "by_name": names.get(c.get("by"), "")} for c in doc.get("comments") or []]
    if user.role == STUDENT:  # the student sees the shared text and the conversation, not the working history
        for key in ("versions", "feedback", "answers"):
            data.pop(key, None)
    return data


def statement_row(doc: dict) -> dict:
    return {"id": doc["_id"], "kind": doc["kind"], "title": doc.get("title", ""), "status": doc["status"],
            "application_id": doc.get("application_id"), "reference_id": doc.get("reference_id"),
            "word_count": word_count(doc.get("content")), "word_limit": doc.get("word_limit"),
            "placeholders": placeholders(doc.get("content")), "ai_assisted": doc.get("ai_assisted", False),
            "comment_count": len(doc.get("comments") or []), "updated_at": doc.get("updated_at")}


def serialize_reference(ref: dict, doc: dict | None, statements: list[dict]) -> dict:
    data = repository.public(ref)
    data["stage"] = stage(ref, doc)
    data["document_status"] = (doc or {}).get("status")
    data["statements"] = [statement_row(s) for s in statements if s.get("reference_id") == ref["_id"]]
    return data
