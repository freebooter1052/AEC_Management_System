"""
`document` metadata and files (SRS 4.6).

    {
      "_id": "document_1a2b3c4d5e6f", "type": "document",
      "student_id": "student_...", "application_id": "application_..." | null,   # null = general document
      "counsellor_id": "counsellor_..." | null,          # the student's counsellor when created
      "document_type": "Transcript", "title": "",          # optional label, e.g. "LOR - Prof. Rao"
      "status": "Required" | "Uploaded" | "Under Review" | "Verified" | "Rejected" | "Expired",
      "filename": "transcript.pdf" | null, "uploaded_at": "..." | null,
      "storage_ref": {"kind": "attachment", "name": "file", "content_type": "application/pdf", "size": 48213}
                   | {"kind": "url", "url": "https://..."} | null,
      "verified_by": "counsellor_..." | "user_..." | null, "verified_at": "..." | null,
      "remarks": "",                                       # why a document was rejected / expired
      "history": [{"status": "Uploaded", "at": "...", "by": "user_...", "by_role": "student", "remarks": ""}],
      "created_at": "...", "updated_at": "..."
    }

Files are stored as a CouchDB attachment named "file" on the document itself, so
CouchDB stays the only data store. A document can instead reference an external
location (`storage_ref.kind == "url"`), e.g. a university portal or shared drive.
"""

import re
from pathlib import PurePath

from rest_framework.exceptions import ValidationError

from apps.core import audit, lookups, repository
from apps.core.roles import ADMIN, COUNSELLOR
from apps.core.vocab import DOCUMENT_STATUSES
from apps.notifications import events
from apps.students import services as student_services

# Every student needs these general documents; applications add SOP and LOR.
CORE_DOCUMENTS = ("Transcript", "Degree Certificate", "Passport", "Resume/CV", "Test Score")
APPLICATION_DOCUMENTS = ("SOP", "LOR")

UPLOADABLE = ("Required", "Uploaded", "Rejected", "Expired")  # a (re)upload is accepted in these states
# Review decisions a counsellor or admin may record, by current status.
REVIEW_TRANSITIONS = {
    "Required": (),
    "Uploaded": ("Under Review", "Verified", "Rejected"),
    "Under Review": ("Verified", "Rejected"),
    "Verified": ("Expired",),
    "Rejected": (),
    "Expired": (),
}
NEEDS_REMARKS = ("Rejected", "Expired")
ATTENTION = ("Required", "Rejected", "Expired")  # the student has to act
AWAITING_REVIEW = ("Uploaded", "Under Review")    # the counsellor has to act

ATTACHMENT_NAME = "file"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# extension -> (content type, accepted leading bytes). Content is checked, not just the name.
FILE_TYPES = {
    ".pdf": ("application/pdf", (b"%PDF",)),
    ".png": ("image/png", (b"\x89PNG",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".doc": ("application/msword", (b"\xd0\xcf\x11\xe0",)),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", (b"PK\x03\x04",)),
}

assert set(REVIEW_TRANSITIONS) == set(DOCUMENT_STATUSES)


def build_document(*, student: dict, document_type: str, application: dict | None = None, title: str = "") -> dict:
    now = repository.now_iso()
    return {
        "_id": repository.new_id("document"),
        "type": "document",
        "student_id": student["_id"],
        "application_id": application["_id"] if application else None,
        "counsellor_id": student.get("counsellor_id"),
        "document_type": document_type,
        "title": title.strip(),
        "status": "Required",
        "filename": None,
        "uploaded_at": None,
        "storage_ref": None,
        "verified_by": None,
        "verified_at": None,
        "remarks": "",
        "history": [],
        "created_at": now,
        "updated_at": now,
    }


def add_event(doc: dict, status: str, actor, remarks: str = "") -> None:
    doc.setdefault("history", []).append({
        "status": status, "at": repository.now_iso(),
        "by": getattr(actor, "id", None), "by_role": getattr(actor, "role", None), "remarks": remarks,
    })


def ensure_checklist(student: dict, types, *, application: dict | None = None, actor=None, request=None) -> list[dict]:
    """Create a `Required` document for each type the student (or application) does not have yet."""
    selector = {"type": "document", "student_id": student["_id"],
                "application_id": application["_id"] if application else None}
    have = {d.get("document_type") for d in repository.find(selector, fields=["document_type"])}
    created = []
    for t in types:
        if t in have:
            continue
        doc = build_document(student=student, document_type=t, application=application)
        add_event(doc, "Required", actor)
        created.append(repository.save(doc))
    if created:
        audit.record("document.checklist_created", request=request, actor=actor, target_id=student["_id"],
                     details={"application_id": application["_id"] if application else None,
                              "types": [d["document_type"] for d in created]})
        events.documents_required(student, created, application=application, actor=actor)
    return created


def blocking_documents(application: dict) -> list[dict]:
    """
    Documents that stop an application from being submitted: every document for this application and
    every general document of the student must be Verified.
    """
    docs = repository.find({"type": "document", "student_id": application["student_id"]},
                           fields=["_id", "document_type", "title", "status", "application_id"])
    return [d for d in docs if d.get("application_id") in (None, application["_id"]) and d.get("status") != "Verified"]


# ---------------------------------------------------------------------------
# Access (SRS 4.1): through the owning student
# ---------------------------------------------------------------------------
def owning_student(doc: dict) -> dict | None:
    return repository.get(doc.get("student_id"), "student")


def can_access(user, doc: dict, student: dict | None = None) -> bool:
    if user.role == ADMIN:
        return True
    student = student or owning_student(doc)
    return student is not None and student_services.can_access(user, student)


def can_review(user) -> bool:
    return user.role in (ADMIN, COUNSELLOR)


# ---------------------------------------------------------------------------
# Upload / reference
# ---------------------------------------------------------------------------
def clean_filename(name: str) -> str:
    base = PurePath(name or "").name
    stem, dot, ext = base.rpartition(".")
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem if dot else base).strip(" ._") or "document"
    return f"{stem[:100]}{'.' + ext.lower() if dot else ''}"


def check_file(upload) -> tuple[str, str, bytes]:
    """Validate an uploaded file; returns (clean filename, content type, bytes)."""
    filename = clean_filename(upload.name)
    ext = PurePath(filename).suffix.lower()
    if ext not in FILE_TYPES:
        raise ValidationError({"file": [f"Unsupported file type. Allowed: {', '.join(sorted(FILE_TYPES))}."]})
    if upload.size > MAX_UPLOAD_BYTES:
        raise ValidationError({"file": [f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."]})
    if upload.size == 0:
        raise ValidationError({"file": ["The file is empty."]})
    content = upload.read()
    content_type, signatures = FILE_TYPES[ext]
    if not content.startswith(signatures):
        raise ValidationError({"file": [f"The file content does not match its {ext} extension."]})
    return filename, content_type, content


def _ensure_uploadable(doc: dict) -> None:
    if doc["status"] not in UPLOADABLE:
        raise ValidationError({"detail": f"A document that is '{doc['status']}' cannot be replaced. "
                                         "Ask your counsellor to mark it Expired or Rejected first."})


def _mark_uploaded(doc: dict, filename: str, actor, request, kind: str) -> dict:
    doc.update({"status": "Uploaded", "filename": filename, "uploaded_at": repository.now_iso(),
                "verified_by": None, "verified_at": None, "remarks": "", "updated_at": repository.now_iso()})
    add_event(doc, "Uploaded", actor)
    repository.save(doc)
    audit.record("document.uploaded", request=request, actor=actor, target_id=doc["_id"],
                 details={"document_type": doc["document_type"], "kind": kind})
    return doc


def attach_file(doc: dict, upload, *, actor, request=None) -> dict:
    _ensure_uploadable(doc)
    filename, content_type, content = check_file(upload)
    repository.put_attachment(doc, content, ATTACHMENT_NAME, content_type)
    # Reload: saving a copy without the new `_attachments` stub would make CouchDB drop the file.
    doc = repository.get(doc["_id"], "document")
    doc["storage_ref"] = {"kind": "attachment", "name": ATTACHMENT_NAME, "content_type": content_type,
                          "size": len(content)}
    return _mark_uploaded(doc, filename, actor, request, "file")


def attach_reference(doc: dict, url: str, filename: str = "", *, actor, request=None) -> dict:
    _ensure_uploadable(doc)
    if (doc.get("_attachments") or {}).get(ATTACHMENT_NAME):
        del doc["_attachments"][ATTACHMENT_NAME]  # the reference replaces a previously stored file
    doc["storage_ref"] = {"kind": "url", "url": url}
    name = clean_filename(filename or url.rstrip("/").rsplit("/", 1)[-1]) or "External document"
    return _mark_uploaded(doc, name, actor, request, "url")


def file_content(doc: dict) -> tuple[bytes, str] | None:
    ref = doc.get("storage_ref") or {}
    if ref.get("kind") != "attachment":
        return None
    content = repository.get_attachment(doc["_id"], ref.get("name", ATTACHMENT_NAME))
    return (content, ref.get("content_type") or "application/octet-stream") if content is not None else None


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
def review(doc: dict, new_status: str, remarks: str, *, actor, request=None) -> dict:
    current = doc["status"]
    allowed = REVIEW_TRANSITIONS.get(current, ())
    if new_status not in allowed:
        if allowed:
            hint = f" Allowed next: {', '.join(allowed)}."
        elif current == "Required":
            hint = " Nothing has been uploaded to review yet."
        else:
            hint = " The student has to upload a new file first."
        raise ValidationError({"status": [f"A document that is '{current}' cannot be marked '{new_status}'.{hint}"]})
    if new_status in NEEDS_REMARKS and not remarks.strip():
        raise ValidationError({"remarks": [f"Explain to the student why the document is {new_status.lower()}."]})

    now = repository.now_iso()
    doc["status"] = new_status
    doc["remarks"] = remarks.strip()
    doc["updated_at"] = now
    if new_status in ("Verified", "Rejected"):
        doc["verified_by"] = actor.profile_id if actor.role == COUNSELLOR else actor.id
        doc["verified_at"] = now
    add_event(doc, new_status, actor, remarks.strip())
    repository.save(doc)
    audit.record("document.reviewed", request=request, actor=actor, target_id=doc["_id"],
                 details={"from": current, "to": new_status})
    events.document_reviewed(doc, new_status=new_status, remarks=doc["remarks"])
    return doc


# ---------------------------------------------------------------------------
# Representation
# ---------------------------------------------------------------------------
def serialize_page(docs: list[dict]) -> list[dict]:
    """Documents with student, reviewer and application names resolved in batched lookups."""
    app_ids = sorted({d["application_id"] for d in docs if d.get("application_id")})
    apps = {}
    if app_ids:
        apps = {a["_id"]: a.get("snapshot", {}) for a in
                repository.find({"type": "application", "_id": {"$in": app_ids}}, fields=["_id", "snapshot"])}
    people = set()
    for d in docs:
        people.update([d.get("student_id"), d.get("verified_by")])
        people.update(e.get("by") for e in d.get("history", []))
    names = lookups.names_by_id(people)
    return [serialize(d, names, apps) for d in docs]


def serialize(doc: dict, names: dict | None = None, apps: dict | None = None) -> dict:
    if names is None:
        return serialize_page([doc])[0]
    data = repository.public(doc)
    data.setdefault("title", "")
    data["history"] = [{**e, "by_name": names.get(e.get("by"), "")} for e in doc.get("history", [])]
    data["student_name"] = names.get(doc.get("student_id"), "")
    data["verified_by_name"] = names.get(doc.get("verified_by"), "") if doc.get("verified_by") else None
    snap = (apps or {}).get(doc.get("application_id")) or {}
    data["application_label"] = (f"{snap.get('course_title', '')} - {snap.get('university_name', '')}".strip(" -")
                                 if doc.get("application_id") else None)
    ref = doc.get("storage_ref") or {}
    data["has_file"] = ref.get("kind") == "attachment"
    data["reference_url"] = ref.get("url") if ref.get("kind") == "url" else None
    data["needs_attention"] = doc.get("status") in ATTENTION
    data["awaiting_review"] = doc.get("status") in AWAITING_REVIEW
    return data


def summary(docs: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for d in docs:
        counts[d.get("status")] = counts.get(d.get("status"), 0) + 1
    return summary_from_counts(counts)


def summary_from_counts(counts: dict) -> dict:
    """The same summary from {status: count} (e.g. a reduce view), without loading the documents."""
    by_status = {s: 0 for s in DOCUMENT_STATUSES}
    for status, n in counts.items():
        by_status[status] = by_status.get(status, 0) + n
    return {"total": sum(by_status.values()), "by_status": by_status,
            "needs_attention": sum(by_status.get(s, 0) for s in ATTENTION),
            "awaiting_review": sum(by_status.get(s, 0) for s in AWAITING_REVIEW)}
