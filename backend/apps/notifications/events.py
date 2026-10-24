"""
Notifications raised by business events (SRS 4.10). Each function is called by the service that made
the change, after the change is saved, and notifies everyone involved except the person who acted.

| Event                                   | Category          | Recipients                         |
|-----------------------------------------|-------------------|------------------------------------|
| application status changed              | status_change     | student; counsellor (if not actor) |
| documents added to a student's checklist| missing_document  | student (when staff added them)    |
| document rejected / expired             | missing_document  | student                            |
| follow-up agreed in a session           | follow_up         | student                            |
| counsellor assigned                     | assignment        | student and the new counsellor     |
| SOP draft shared with the student       | writing           | student                            |
| student approves / asks changes (SOP, LOR) | writing           | counsellor                         |
| comment on a shared SOP                 | writing           | the other side (student/counsellor)|
| counsellor asks for AI-writing consent  | writing           | student                            |

Time-based reminders (deadlines, outstanding documents, due follow-ups) are in `reminders.py`.
"""

from apps.core import repository
from apps.core.roles import COUNSELLOR, STUDENT

from .services import notify


def student_name(student: dict) -> str:
    p = student.get("personal") or {}
    return f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() or "A student"


def counsellor_user_id(counsellor_id: str | None) -> str | None:
    if not counsellor_id:
        return None
    counsellor = repository.get(counsellor_id, "counsellor")
    return counsellor.get("user_id") if counsellor else None


def _label(app: dict) -> str:
    snap = app.get("snapshot") or {}
    return f"{snap.get('course_title', 'Application')} at {snap.get('university_name', 'the university')}"


def application_status_changed(app: dict, student: dict | None, *, old: str, new: str, history_id: str, actor) -> None:
    if student is None:
        return
    link = f"/applications/{app['_id']}/"
    key = f"app_status:{history_id}"
    common = dict(category="status_change", event_key=key, related_id=app["_id"], related_type="application", link=link)
    if actor is None or getattr(actor, "id", None) != student.get("user_id"):
        notify(recipient_user_id=student.get("user_id"), recipient_role=STUDENT,
               title=f"Application update: {new}", message=f"{_label(app)} moved from '{old}' to '{new}'.", **common)
    coun_user = counsellor_user_id(student.get("counsellor_id"))
    if coun_user and coun_user != getattr(actor, "id", None):
        notify(recipient_user_id=coun_user, recipient_role=COUNSELLOR,
               title=f"{student_name(student)}: application {new.lower()}",
               message=f"{_label(app)} moved from '{old}' to '{new}'.", **common)


def documents_required(student: dict, documents: list[dict], *, application: dict | None, actor) -> None:
    """New `Required` documents on a student's checklist, when someone other than the student added them."""
    if not documents or getattr(actor, "id", None) == student.get("user_id"):
        return
    kinds = ", ".join(d.get("title") or d["document_type"] for d in documents)
    where = f" for {_label(application)}" if application else ""
    n = len(documents)
    notify(recipient_user_id=student.get("user_id"), recipient_role=STUDENT, category="missing_document",
           title=f"{n} document{'' if n == 1 else 's'} requested",
           message=f"Please upload{where}: {kinds}.",
           event_key="doc_required:" + ",".join(sorted(d["_id"] for d in documents)),
           related_id=application["_id"] if application else student["_id"],
           related_type="application" if application else "student", link="/documents/")


def document_reviewed(doc: dict, *, new_status: str, remarks: str) -> None:
    """A rejected or expired document has to be replaced by the student."""
    if new_status not in ("Rejected", "Expired"):
        return
    student = repository.get(doc.get("student_id"), "student")
    if student is None:
        return
    name = doc.get("title") or doc.get("document_type", "Document")
    notify(recipient_user_id=student.get("user_id"), recipient_role=STUDENT, category="missing_document",
           title=f"{name} {new_status.lower()}: please upload a new copy",
           message=remarks or f"Your {name} was marked {new_status.lower()}.",
           event_key=f"doc_review:{doc['_id']}:{len(doc.get('history') or [])}",
           related_id=doc["_id"], related_type="document", link="/documents/")


def follow_up_created(session: dict) -> None:
    follow = session.get("follow_up")
    student = repository.get(session.get("student_id"), "student")
    if not follow or student is None:
        return
    notify(recipient_user_id=student.get("user_id"), recipient_role=STUDENT, category="follow_up",
           title="New follow-up from your counselling session",
           message=f"{follow['action']} (due {follow['due_date']}).",
           event_key=f"follow_up_new:{session['_id']}:{follow['due_date']}",
           related_id=session["_id"], related_type="counselling_session", link="/counselling/?tab=follow-ups")


def counsellor_assigned(student: dict, counsellor: dict) -> None:
    key = f"assign:{student['_id']}:{counsellor['_id']}:{student.get('counsellor_assigned_at')}"
    notify(recipient_user_id=student.get("user_id"), recipient_role=STUDENT, category="assignment",
           title="Counsellor assigned", message=f"{counsellor.get('name', 'A counsellor')} is now your counsellor.",
           event_key=key, related_id=counsellor["_id"], related_type="counsellor", link="/profile/")
    notify(recipient_user_id=counsellor.get("user_id"), recipient_role=COUNSELLOR, category="assignment",
           title="New student assigned", message=f"{student_name(student)} has been assigned to you.",
           event_key=key, related_id=student["_id"], related_type="student", link=f"/students/{student['_id']}/")


def statement_shared(statement: dict, student: dict) -> None:
    versions = statement.get("versions") or []
    notify(recipient_user_id=student.get("user_id"), recipient_role=STUDENT, category="writing",
           title="Your counsellor shared an SOP draft",
           message=f"{statement.get('title', 'SOP')} is ready for you to read. Add a comment with any changes.",
           event_key=f"sop_shared:{statement['_id']}:{versions[-1]['n'] if versions else 0}",
           related_id=statement["_id"], related_type="statement", link=f"/writing/statements/{statement['_id']}/")


def statement_commented(statement: dict, student: dict, comment: dict) -> None:
    link = f"/writing/statements/{statement['_id']}/"
    common = dict(category="writing", event_key=f"sop_comment:{statement['_id']}:{comment['id']}",
                  related_id=statement["_id"], related_type="statement", link=link)
    if comment.get("by_role") == STUDENT:
        notify(recipient_user_id=counsellor_user_id(student.get("counsellor_id")), recipient_role=COUNSELLOR,
               title=f"{student_name(student)} commented on their SOP", message=comment["text"][:300], **common)
    elif statement.get("status") in ("Shared", "Final"):
        notify(recipient_user_id=student.get("user_id"), recipient_role=STUDENT,
               title="New comment from your counsellor", message=comment["text"][:300], **common)


def document_decided(doc: dict, student: dict, decision: str, note: str, label: str, link: str, related_type: str) -> None:
    approved = decision == "Approved"
    notify(recipient_user_id=counsellor_user_id(student.get("counsellor_id")), recipient_role=COUNSELLOR, category="writing",
           title=f"{student_name(student)} {'approved' if approved else 'asked for changes to'} {label}",
           message="Ready to be marked final." if approved else note[:300],
           event_key=f"doc_decision:{doc['_id']}:{doc.get('student_approval', {}).get('at', '')}",
           related_id=doc["_id"], related_type=related_type, link=link)


def ai_consent_requested(student: dict, day: str) -> bool:
    """Once a day at most; True when a new request was sent."""
    return notify(recipient_user_id=student.get("user_id"), recipient_role=STUDENT, category="writing",
                  title="Your counsellor would like to use the writing assistant",
                  message="Allow AI-assisted drafting of your SOP and referee briefs? Open SOP & LOR to read what is shared and decide.",
                  event_key=f"ai_consent_request:{student['_id']}:{day}",
                  related_id=student["_id"], related_type="student", link="/writing/") is not None
