# Sprint 2: Applications, Documents and Counselling

**Sprint goal:** implement the counselling-to-application workflow.

**Acceptance flow:** **Student → Counsellor → University/Course → Application → Documents → Counselling → Application Status.** A student (or their counsellor) picks a course and intake from the catalogue and creates an application. The counsellor moves it through the statuses. Reaching *Documents Pending* creates the SOP and LOR requirements. The student uploads, and the counsellor verifies. Submission is refused until every relevant document is Verified. Counselling sessions record what was agreed and set follow-ups. Each status change lands in a timestamped history.

Requirement references (§) point to *SRS v1.0*. Document shapes are in [`DATA_MODEL.md`](DATA_MODEL.md).

---

## 1. What was delivered

### Application backend (`backend/apps/applications/`, SRS 4.5)
| Item | Notes |
|---|---|
| Application document | Built from the course, its university and the intake. Names are copied into `snapshot`, so lists need no joins. Starts as **Planned**. Linked from `student.application_ids`. |
| Create application API | Students apply for themselves; counsellors and admins apply for a student they can access. A duplicate application (same course and intake) is refused unless the earlier one was Rejected or Withdrawn. |
| Intake / deadline handling | `GET /api/intakes/` lists intakes with `is_open`. The deadline defaults to the intake deadline. A closed intake is refused unless the university's own later deadline is given, and the deadline must fall before the programme starts. Each application returns `deadline_info {date, days_left, state}`, where `state` is overdue, due_soon (≤ 14 days), open, submitted or closed. Admins add intakes and move their dates. |
| Status transitions | One transition map (`services.TRANSITIONS`) holds the SRS statuses from `core/vocab.py`. Students may only withdraw. Moving to **Documents Pending** creates SOP and LOR requirements. **Submitted** is blocked until every document for the application, and every general document, is Verified. |
| Application history | Every change writes an `application_history` doc with old status, new status, who made the change, role, timestamp and remarks, and appends its ID to `history_ids`. |

### Document and counselling backend (`apps/documents/`, `apps/counselling/`, SRS 4.6–4.7)
| Item | Notes |
|---|---|
| Document metadata | Checklist entries per student, either general or tied to an application, with an optional label and an embedded `history`. |
| Upload / reference handling | Files are stored as a **CouchDB attachment** on the document, so CouchDB stays the only data store. PDF, image or Word files up to 5 MB are accepted, and the content is checked against the extension. A link to an externally held copy is also accepted. Downloads go through an authenticated endpoint. |
| Document status and verification API | Required → Uploaded → Under Review → Verified / Rejected, then Verified → Expired. Rejected and Expired need remarks for the student. A rejected or expired document can be re-uploaded; a verified one cannot. Only staff review. |
| Counselling session | Records date/time, duration, mode, counsellor, student and topic. Double-booking a counsellor is refused. Completing a session records the summary, recommendations, agreed actions and an optional follow-up. Sessions can be rescheduled (with `rev`) or cancelled with a reason. |
| Follow-up | A sub-document of its session, with action, due date, Pending/Done and completed time. It has its own list endpoint and update endpoint. Students can mark their own follow-up done. |
| Counselling history | Paginated by date, upcoming or past. A student's full history is visible to their current counsellor, including sessions with earlier counsellors, but only the session's own counsellor or an admin can change it. |

### Frontend
| Screen | URL | Notes |
|---|---|---|
| Application workspace | `/applications/` | Status pipeline chips with counts (click to filter), overdue and due-soon alerts, search, student filter (staff), "nearest deadline first", open-only. "New application" drawer: student → university search → course → intake (deadline pre-filled) → tier/notes. |
| Application status screen | `/applications/<id>/` | Status stepper, deadline countdown, key dates, people. The allowed next moves are buttons, with remarks. Submission blockers are listed, the application's documents can be uploaded or reviewed in place, and the history timeline is shown. Staff can edit the deadline, tier and notes. |
| Deadline display | everywhere | Date plus a countdown badge (overdue in red, due soon in amber), also on the dashboards. |
| Document upload/status screen | `/documents/` | Students see a KPI strip and a checklist grouped into general documents and one group per application, with a drag-and-drop upload or a link, and rejection reasons in red. Staff get a review queue across their students (filter by awaiting review or waiting on the student), or a per-student checklist with "Standard checklist" and "Add document". |
| Counselling calendar | `/counselling/` | Month grid with sessions colour-coded by state ("needs notes" when a past session has no notes yet) and follow-up due dates. Session drawer: record notes, reschedule, cancel, mark follow-up done. Staff schedule from here. |
| Counselling history | `/counselling/?tab=history` | Session cards with summary, recommendations, actions and follow-up. |
| Follow-up display | `/counselling/?tab=follow-ups` | Table sorted by due date, with overdue, due-today and pending states, "Mark done", and a count badge on the tab. |
| Dashboards | `/dashboard/` | Every role now sees application, document, session and follow-up KPIs and cards. |
| Cross-links | profile, universities | The student profile links to that student's applications, documents and counselling. Every course in the university drawer has a "Plan application" button. |

The navigation now includes Applications, Documents and Counselling for every role.

### Also fixed
- **`purge_demo_data` would have deleted real workflow data.** It treated every untagged application, document or session as demo data. Now it keeps workflow docs that belong to a kept student or user (regression test in `tests/test_maintenance.py`).
- **Deleting a student** (admin) now also removes their applications with their history, documents, sessions and recommendations, so no orphans are left.

---

## 2. REST API (new in this sprint)

All endpoints require `Authorization: Bearer <token>`. List endpoints return `{count, page, page_size, total_pages, results}`. Write endpoints accept `rev` for optimistic concurrency (409 on conflict).

| Method & path | Who | Purpose |
|---|---|---|
| `GET /api/applications/` | all (scoped) | `?student_id=&status=a,b&open=true&q=&sort=deadline` |
| `POST /api/applications/` | all | `{course_id, intake_id, deadline?, tier?, notes?, student_id (staff)}` |
| `GET /api/applications/summary/` | all (scoped) | Counts by status, overdue, due soon, nearest deadlines |
| `GET /api/applications/<id>/` | owner, their counsellor, admin | With history, documents, `allowed_transitions`, `submission_blockers`, intake |
| `PATCH /api/applications/<id>/` | counsellor, admin | Deadline, decision date, tier, notes |
| `DELETE /api/applications/<id>/` | owner, their counsellor, admin | Only while Planned |
| `POST /api/applications/<id>/status/` | as above (students: withdraw only) | `{status, remarks?}` |
| `GET /api/applications/<id>/history/` | as above | Status trail |
| `GET /api/intakes/` · `POST` · `PATCH /api/intakes/<id>/` | all · admin · admin | Intakes and their dates |
| `GET /api/documents/` | all (scoped) | `?student_id=&application_id=(id\|none)&status=a,b&document_type=` |
| `POST /api/documents/` | all | Add a requirement `{document_type, title?, application_id?, student_id (staff)}` |
| `POST /api/documents/checklist/` | all | Create the standard general checklist (idempotent) |
| `GET /api/documents/summary/` | all (scoped) | Counts by status, `needs_attention`, `awaiting_review` |
| `GET` / `DELETE /api/documents/<id>/` | owner/staff · staff | Verified documents cannot be deleted |
| `POST /api/documents/<id>/upload/` | owner, staff | Multipart `file`, or JSON `{reference_url, filename?}` |
| `POST /api/documents/<id>/verify/` | counsellor, admin | `{status: Under Review\|Verified\|Rejected\|Expired, remarks}` |
| `GET /api/documents/<id>/file/` | owner, staff | Download the stored file |
| `GET /api/counselling/sessions/` | all (scoped) | `?student_id=&status=&when=upcoming\|past&counsellor_id= (admin)` |
| `POST /api/counselling/sessions/` | counsellor, admin | `{student_id, scheduled_at, duration_minutes, mode, topic}` |
| `GET` / `PATCH /api/counselling/sessions/<id>/` | viewers · session's counsellor, admin | Reschedule or edit a scheduled session |
| `POST /api/counselling/sessions/<id>/complete/` | session's counsellor, admin | `{summary, recommendations[], action_items[], follow_up?: {action, due_date}}` |
| `POST /api/counselling/sessions/<id>/cancel/` | session's counsellor, admin | `{reason?}` |
| `PATCH /api/counselling/sessions/<id>/follow-up/` | session's counsellor, admin; student: status only | `{status?, action?, due_date?}` |
| `GET /api/counselling/follow-ups/` | all (scoped) | `?status=Pending\|Done&student_id=` |
| `GET /api/counselling/calendar/` | all (scoped) | `?start=&end=` (≤ 62 days): sessions plus follow-up due dates |

"Scoped" means: students see their own records, counsellors see records of the students assigned to them, and admins see everything. Asking for a student outside your scope returns 403.

---

## 3. Verification

- **54 automated API tests pass** (`python manage.py test tests`), 21 of them new:
  - `test_applications.py`: creation, deadline rules, duplicates, the full workflow with the document gate and history chain, transition and role rules, 409 on a stale `rev`, access scoping, update/delete/list/summary, the cascade when a student is deleted, and intakes.
  - `test_documents.py`: checklist, upload, download, file-type, spoofed-content, size and empty-file checks, reference links, the verification flow, the attachment stub surviving later saves, filters, summary and delete.
  - `test_counselling.py`: scheduling and double-booking, completing with notes and follow-up, follow-up rules, the calendar, history after reassignment, rescheduling with conflicts, and dashboards.
  - `test_maintenance.py`: the purge keeps app-created workflow docs.
- **Live run against the real CouchDB 3.5 server.** A throwaway database (`aec_sprint2_check`) held a copy of the real catalogue plus the SRS sample dataset, and the dev server ran on it. **69/69 HTTP checks passed** across the whole acceptance flow as real seeded accounts: student Linh Nguyen and counsellor Mei Lin Tan, with Priya Raman and Ananya Iyer as the out-of-scope checks. This confirmed that the new Mango indexes serve the sorted queries, that attachments round-trip byte-for-byte after later saves, and that the server log had no 5xx errors. The scratch database was deleted afterwards. `counselling_db` received only the two new index definitions (`init_couchdb`).
- **Browser pass.** Headless Chrome loaded every new page as student, counsellor and admin at 1366 px, and the main ones at 390 px. Every run passed (80/80 on a full run): no JavaScript errors, no horizontal scrolling. The run also changed an application's status by clicking through the UI, and opened the upload, review, schedule and new-application drawers.

---

## 4. Design decisions

- **Files live in CouchDB as attachments.** This follows the "CouchDB is the only data store" rule. The service reloads the document after `put_attachment`, because saving a copy without the new `_attachments` stub would make CouchDB drop the file. A test asserts that the stub survives.
- **The follow-up is a sub-document of its session**, not a separate type. This matches the existing data model and the seed data, so a student's counselling history reads as one list. Follow-ups still get their own endpoints and screen.
- **The submission gate is per application.** It covers documents tied to this application plus the student's general documents. Another application's SOP doesn't block this one.
- **Access to workflow records always goes through the owning student** (`students/services.scope_to_students`, `can_access`), so reassigning a student moves access with them. The `counsellor_id` stored on an application is refreshed on every status change, and lists show the student's *current* counsellor.
- **Notifications are not written yet.** The status changes, verifications and follow-ups that should trigger them are in place for the notifications sprint (§4.10).

## 5. Next sprint candidates
Notifications for status changes, document decisions, deadlines and follow-ups (§4.10); rule-based recommendations and acceptance into an application (§4.8); course master data with tuition and level (§4.4); reports (§4.9).
