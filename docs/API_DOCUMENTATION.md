# REST API reference

Every endpoint of the AEC Management System backend (Django REST Framework over CouchDB). Sprint 3 endpoints (recommendations, notifications, dashboards, course maintenance) are documented in full. Sprint 1 and 2 endpoints are listed with their purpose; their rules are in [`SPRINT1_FOUNDATION.md`](SPRINT1_FOUNDATION.md) and [`SPRINT2_WORKFLOW.md`](SPRINT2_WORKFLOW.md). Document shapes are in [`DATA_MODEL.md`](DATA_MODEL.md).

## Conventions

| Topic | Rule |
|---|---|
| Base URL | `/api/` on the same origin as the web app (`http://127.0.0.1:8000/api/` in development). |
| Authentication | `Authorization: Bearer <token>` on every endpoint except `health/`, `countries/`, `auth/register/`, `auth/login/` and the three forgot-password endpoints. Tokens come from `auth/login/` and expire after `AUTH_TOKEN_MAX_AGE` (8 h). Logout, a password change or a password reset revokes every older token. |
| Roles | `student`, `counsellor`, `admin`. Every rule is enforced by the API. A counsellor reaches only the students whose `counsellor_id` is theirs; a student only their own records. |
| Format | JSON in and out (`Content-Type: application/json`), except document uploads (multipart) and file downloads. |
| Lists | `?page=` (from 1) and `?page_size=` (default 20, at most 100). Response: `{count, page, page_size, total_pages, results}`. A page past the end returns `results: []`. |
| Concurrency | Records carry `rev`. Send it back on a change (`PATCH`, status changes, reviews). A stale `rev` returns **409** and changes nothing. |
| IDs | `<type>_<12 hex>`. The UI never shows them; responses carry resolved names. |

### Errors

| Status | When | Body |
|---|---|---|
| 400 | Invalid input or a business rule | `{"field": ["message"]}` or `{"detail": "message"}` |
| 401 | No token, a bad or expired token, or a revoked token | `{"detail": "..."}` |
| 403 | Wrong role, or a record outside the caller's scope (logged as a security event) | `{"detail": "You do not have access to this ..."}` |
| 404 | No such record | `{"detail": "... not found."}` |
| 409 | Stale `rev` (someone else changed the record) | `{"detail": "The record was changed by someone else. Reload and try again."}` |
| 503 | CouchDB unreachable | `{"detail": "The database is temporarily unavailable. Please try again shortly."}` |
| 500 | Unexpected error (logged with a traceback server-side) | `{"detail": "An unexpected error occurred."}` |

Messages never contain stack traces, database details or credentials.

---

## Recommendations (SRS 4.8), Sprint 3

A rule-based engine scores the course catalogue against a student's profile. Rules, weights and the formula are in `backend/apps/recommendations/engine.py` and [`SPRINT3_IMPLEMENTATION_REPORT.md`](SPRINT3_IMPLEMENTATION_REPORT.md#3-recommendation-engine).

| Method & path | Who | Purpose |
|---|---|---|
| `GET /api/recommendations/` | student (own); counsellor, admin with `?student_id=` | One student's recommendations, plus the latest run and its freshness |
| `POST /api/recommendations/generate/` | student (own); counsellor (assigned); admin | Run the engine and store the results. Repeatable: it updates and never duplicates |
| `POST /api/recommendations/` | counsellor (assigned), admin | Recommend a specific course (scored; refused if it fails a hard rule) |
| `GET /api/recommendations/<id>/` | the student, their counsellor, admin | One recommendation |
| `PATCH /api/recommendations/<id>/` | counsellor (assigned), admin | Accept, reject or reset; note; tier |

**`GET /api/recommendations/?student_id=&status=&page=&page_size=`**: a student's `student_id` is ignored (they always get their own). Staff must name a student they can access (403 otherwise; 400 if missing). `status` is one of Suggested, Accepted or Rejected (400 otherwise). Results are ordered Accepted, then Suggested, then Rejected, and within those by `ranking_score`, `match_score`, world rank, university and course.

```json
{
  "count": 12, "page": 1, "page_size": 20, "total_pages": 1,
  "student": {"id": "student_…", "full_name": "Linh Nguyen", "profile_completion": 100},
  "run": {"status": "ok", "message": "", "method": "rule_based_v2", "generated_at": "2026-10-16T16:20:00Z",
          "generated_by_name": "Linh Nguyen", "weights": {"country": 30, "course": 30, "academic": 20, "intake": 10, "budget": 10},
          "min_score": 40, "limit": 15,
          "stats": {"catalogue_courses": 1258, "evaluated": 276, "eligible": 0, "insufficient_data": 276, "ineligible": 0,
                    "ineligible_by_rule": {}, "below_threshold": 0, "recommended": 15, "inactive_or_unlinked": 0}},
  "freshness": {"state": "current", "reasons": []},
  "results": [{
    "id": "recommendation_3f1c…", "rev": "2-…", "student_id": "student_…", "university_id": "university_031",
    "course_id": "course_0412", "intake_id": "intake_fall_2027", "origin": "engine", "method": "rule_based_v2",
    "match_score": 100, "confidence": 90, "ranking_score": 90, "eligibility": "insufficient_data", "tier": "Safe",
    "status": "Suggested", "remarks": "", "in_latest_run": true, "rank_position": 1,
    "factors": [
      {"key": "country", "label": "Country", "status": "match", "score": 1.0, "weight": 30, "detail": "Japan is one of the target countries."},
      {"key": "budget", "label": "Budget", "status": "unknown", "score": null, "weight": 10, "detail": "Tuition is not recorded for this course."}
    ],
    "checks": {"level": {"status": "unknown", "detail": "The course level is not recorded in the catalogue."}},
    "reasons": ["Japan is one of the target countries.", "Eligibility to confirm with the university: …"],
    "missing_data": [{"source": "catalogue", "item": "Tuition"}, {"source": "catalogue", "item": "Course level"}],
    "snapshot": {"university_name": "The University of Tokyo", "country": "Japan", "world_rank": 31,
                 "course_title": "Mathematical Engineering", "cluster": "Mathematics", "intake_name": "Fall 2027",
                 "intake_deadline": "2027-01-15"},
    "created_by_name": "Linh Nguyen", "reviewed_by_name": null, "generated_at": "2026-10-16T16:20:00Z"
  }]
}
```
`freshness.state` is `never` (no run yet), `current` or `stale`, with human-readable `reasons`. `factors` is always five rows, including for seed (`rule_based_v1`) documents, whose `eligibility` is `null` until refreshed.

**`POST /api/recommendations/generate/`** with body `{"student_id": "…"}` (staff) or `{}` (student): returns the same shape as the list (first page). If the profile has neither target countries nor course areas, it returns `run.status = "insufficient_profile"` with a message and no results (not an error). An empty catalogue returns `count: 0` and a message.

**`POST /api/recommendations/`** with body `{student_id, course_id, remarks?}` returns **201** and the recommendation (`origin: "counsellor"`, `status: "Accepted"`). It returns 400 when the course is unknown, inactive, already recommended to the student, or fails a hard eligibility rule (the message names the rule).

**`PATCH /api/recommendations/<id>/`** takes `{status?, remarks?, tier?, rev?}` with at least one of status, remarks or tier (400 otherwise). Accepting a recommendation whose `eligibility` is `ineligible` returns 400. A stale `rev` returns 409. A tier set here is kept by later refreshes (`tier: ""` returns it to the engine's estimate).

## Notifications (SRS 4.10), Sprint 3

Every user has an inbox of their own notifications. Nobody can list, read or mark anyone else's.

| Method & path | Purpose |
|---|---|
| `GET /api/notifications/?unread=1&category=&page=&page_size=` | The caller's notifications, newest first. `category` is one of status_change, missing_document, deadline, follow_up, assignment, writing (400 otherwise). Adds `unread` (total unread) to the page |
| `GET /api/notifications/unread-count/` | `{"unread": 3, "by_category": {"status_change": 1, "missing_document": 2, "deadline": 0, "follow_up": 0, "assignment": 0}}` |
| `GET /api/notifications/<id>/` | One notification (403 if it is someone else's, 404 if missing) |
| `POST /api/notifications/<id>/read/` | Body `{"read": true}` (default) or `{"read": false}`. Idempotent. Returns the notification |
| `POST /api/notifications/read-all/` | Marks every unread notification read: `{"updated": 4, "failed": 0, "remaining": 0}` |

A notification:
```json
{"id": "notification_9a…", "rev": "1-…", "recipient_user_id": "user_…", "recipient_role": "student",
 "category": "status_change", "title": "Application update: Submitted",
 "message": "Statistics at The University of Hong Kong moved from 'Documents Pending' to 'Submitted'.",
 "related_id": "application_…", "related_type": "application", "link": "/applications/application_…/",
 "event_key": "app_status:application_history_…", "is_read": false, "read_at": null, "created_at": "2026-10-16T16:21:04Z"}
```
Listing and the unread count also run the caller's own reminder sweep, at most once every 15 minutes per user (see the implementation report). Marking read retries up to 3 times on a revision conflict (re-read, then re-apply), then returns 409. `read-all` uses `_bulk_docs` in batches of 200 and retries conflicting documents one by one.

## SOP & LOR writing

Counsellors write statements of purpose with a guided interview and Google Gemini, and track each referee's recommendation letter. AI actions need three things, checked in this order: the caller is the student's own counsellor (403), the student has agreed to AI-assisted writing (403), and `GEMINI_API_KEY` is set (503). Admins can read everything but change only the setting. Students see their shared SOPs and their referees, and can comment.

| Method & path | Who | Purpose |
|---|---|---|
| `GET /api/writing/?student_id=` | all (students: own) | Workspace: `student`, `consent`, `can_edit`, `ai_available`, `settings`, `questions[]`, `applications[]`, `statements[]` (rows), `references[]` |
| `GET` / `PUT /api/writing/consent/` | student | `{"granted": true}`; returns `{granted, granted_at, withdrawn_at}` |
| `POST /api/writing/consent/request/` | counsellor | `{student_id}`: notifies the student, at most once a day (`{"sent": false}` after that) |
| `GET` / `PATCH /api/writing/settings/` | all / admin | `{"allow_lor_drafts": false, "ai_available": true}` |
| `POST /api/writing/statements/` | counsellor | `{student_id, application_id?, title?, word_limit?}` → 201 |
| `GET` / `PATCH` / `DELETE /api/writing/statements/<id>/` | see above | PATCH `{title?, word_limit?, answers?, content?, note?, rev}`; a changed `content` is saved as a new version. Final statements reject `content` (400) |
| `POST /api/writing/statements/<id>/generate/` | counsellor | First draft from the answers (needs motivation, why_course, goals; 400 otherwise) |
| `POST …/revise/` | counsellor | `{instruction}` (≤ 300 chars), e.g. "Make it more concise" |
| `POST …/review/` | counsellor | Fills `feedback`; the text is not changed. Needs ≥ 50 words |
| `POST …/status/` | counsellor | `{status: Draft/Shared/Final}`; sharing an SOP notifies the student |
| `POST …/restore/` | counsellor | `{version}`: makes an earlier version current (as a new version) |
| `POST …/comments/` | counsellor, student (once shared) | `{text}`: notifies the other side |
| `POST /api/writing/references/` | counsellor | `{student_id, application_id?, referee{name, title?, institution?, email?, relationship?}, highlights?, due_date?}` → 201 |
| `GET` / `PATCH /api/writing/references/<id>/` | see above | PATCH `{referee?, highlights?, due_date?, status? (Planned/Requested/Cancelled), rev}` |
| `POST /api/writing/references/<id>/prepare/` | counsellor | `{kind: lor_brief}` (or `lor_draft` when the setting allows it, 403 otherwise): returns the statement holding it; repeating adds a version |

Gemini errors never leak details: the service being down, a timeout or a bad key give **503** ("The writing assistant is not available right now…"), a quota limit gives 503 with a "busy" message, and a safety refusal gives **422**. Every AI call writes an `audit_log` (`writing.ai_draft`, `writing.ai_revise`, `writing.ai_review`, `writing.ai_lor_brief`, `writing.ai_lor_draft`) with the model and token counts, never the prompt or the reply.

## Dashboards (SRS 4.9)

**`GET /api/dashboard/`** returns a role-specific summary. Staff may add `?country=` (catalogue country name) and `?intake_id=`; admins may also add `?counsellor_id=`. Unknown values match nothing. A counsellor's `counsellor_id` is ignored.

| Role | Sections |
|---|---|
| Student | `profile_completion`, `onboarding_status`, `counsellor`, `preferences`, `applications` (pipeline, overdue, due soon, nearest 5 deadlines), `application_list` (open first, up to 6), `documents` (by status), `documents_attention` (Required/Rejected/Expired, up to 6), `upcoming_sessions`, `follow_ups`, `recommendations {top (3), total, run, freshness}`, `notifications {unread, latest (5)}` |
| Counsellor | `workload`, `students_by_status`, `needs_attention` (6 students: most outstanding documents, then least complete profile, with `documents_outstanding` and `open_applications`), `review_queue` (5 oldest uploads awaiting review), `students_without_recommendations`, `applications`, `documents`, `upcoming_sessions`, `follow_ups`, `notifications`, `filters` |
| Admin | `totals {students, unassigned_students, counsellors, active_counsellors, universities, courses, active_courses, applications, users}`, `applications`, `documents`, `upcoming_sessions`, `follow_ups`, `reports {by_country, by_university, by_intake (top 10, with offers), outcomes {decided, offers, offer_rate_pct}, recommendations {total, by_status}}`, `counsellor_workload` (the 10 busiest, with open applications, documents to review, sessions in the last 30 days and pending/overdue follow-ups), `counsellor_workload_total`, `filter_options {counsellors, intakes}`, `filters`, `notifications` |

Filter scope: `counsellor_id` narrows every admin figure to that counsellor's current students. `country` and `intake_id` narrow the application figures (pipeline, deadlines, reports) only. Aggregates contain counts and names of universities, countries and counsellors, never student contact details.

## Course maintenance (SRS 4.4), Sprint 3

| Method & path | Who | Purpose |
|---|---|---|
| `GET /api/universities/courses/<id>/` | all (inactive: admin only, else 404) | A course with its university `{id, name, country, rank}` |
| `PATCH /api/universities/courses/<id>/` | admin | Edit fields; deactivate with `is_active: false`; send `rev` to detect conflicts |
| `POST /api/universities/<id>/courses/` | admin | Add a course (`title` required); returns 201 |

Body fields (all optional on PATCH): `title`, `canonical_name`, `cluster`, `level` (`""`, Diploma, Bachelors, Masters, MBA, PhD, Certificate), `duration_months` (1–96), `tuition {amount_per_year (0–10,000,000), currency (3 capital letters, required with an amount)}`, `eligibility {min_grade_pct (0–100), min_english {IELTS 0–9, TOEFL 0–120, PTE 10–90, Duolingo 10–160, Cambridge 80–230}, notes}`, `intake_ids` (existing intakes; empty = every intake), `is_active`. Fields not sent are left unchanged; `tuition` and `eligibility` are replaced as a whole when sent. Inactive courses are hidden from non-admin search and university pages, cannot be applied for (400), and are never recommended.

---

## Sprint 1 and 2 endpoints

| Method & path | Who | Purpose |
|---|---|---|
| `GET /api/health/` | public | API and CouchDB reachability (`{"status": "ok"}` or 503) |
| `GET /api/countries/` | public | Canonical country list for pickers |
| `POST /api/auth/register/` | public | Student self-registration (`privacy_acknowledged: true` required) |
| `POST /api/auth/login/` | public | `{email, password, role?}` returns `{token, user}` |
| `POST /api/auth/logout/` | any | Revokes all of the user's tokens |
| `GET /api/auth/me/` | any | Current account |
| `POST /api/auth/change-password/` | any | Returns a new token |
| `POST /api/auth/forgot-password/` · `verify-reset-code/` · `reset-password/` | public | Emailed 6-digit code flow |
| `GET /api/auth/users/` · `GET/PATCH /api/auth/users/<id>/` | admin | List, activate and deactivate accounts |
| `GET/POST /api/students/` | staff (counsellors: own) · admin | Roster (`q`, `status`, `counsellor_id`, `unassigned`); create |
| `GET/PATCH /api/students/me/` · `GET /api/students/me/counsellor/` | student | Own profile; own counsellor |
| `GET/PATCH/DELETE /api/students/<id>/` | admin, assigned counsellor, the student (DELETE: admin) | Profile (deletion cascades to workflow records and notifications) |
| `POST /api/students/<id>/assign-counsellor/` | admin | Assign, reassign or unassign (notifies the student and the counsellor) |
| `GET/POST /api/counsellors/` · `GET /api/counsellors/options/` · `GET/PATCH /api/counsellors/me/` | admin · admin · counsellor | Counsellors with workload |
| `GET/PATCH/DELETE /api/counsellors/<id>/` · `GET /api/counsellors/<id>/students/` | admin (self: read/edit) | One counsellor; their roster |
| `GET /api/universities/` · `countries/` · `courses/` · `<id>/` | any | Catalogue search |
| `GET/POST /api/applications/` · `summary/` · `<id>/` · `<id>/status/` · `<id>/history/` | scoped | Applications, status workflow (status changes notify), history |
| `GET/POST /api/intakes/` · `PATCH /api/intakes/<id>/` | any · admin | Intakes and their dates |
| `GET/POST /api/documents/` · `checklist/` · `summary/` · `<id>/` · `<id>/upload/` · `<id>/verify/` · `<id>/file/` | scoped | Documents, uploads, review (rejection/expiry and staff-added requirements notify) |
| `GET/POST /api/counselling/sessions/` · `<id>/` · `<id>/complete/` · `<id>/cancel/` · `<id>/follow-up/` | scoped | Sessions and follow-ups (an agreed follow-up notifies the student) |
| `GET /api/counselling/follow-ups/` · `calendar/` | scoped | Follow-up list; calendar range (62 days at most) |
