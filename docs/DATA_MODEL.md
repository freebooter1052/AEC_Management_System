# CouchDB Data Model

Reference for every document type stored in `counselling_db`. The shapes implement SRS §6 (core document types, additional documents and relationships). Allowed status values live in `backend/apps/core/vocab.py`; new APIs must use them.

## Conventions

- **Every document has a `type` field** that names its kind. Query it with Mango, for example `{"type": "application", "student_id": "…"}`.
- **IDs:** `_id` is `<type>_<12 hex>`. The exceptions are master data with natural keys: `country_<ISO code>`, `intake_<season>_<year>`, and the imported `university_NNN` and `course_NNNN`.
- **Relationships** are stored as document IDs (SRS §6.3). A few summary fields are copied into the referencing document (`snapshot`) so lists don't need joins.
- **Timestamps** are ISO-8601 UTC strings (`2026-10-13T18:24:04Z`). Pure dates are `YYYY-MM-DD`.
- **`"source": "seed"`** marks the sample dataset from `manage.py seed_dataset`. Data entered through the app has no `source` field.

## Relationship overview

```
user ──profile_id──▶ student ◀──user_id── (1:1)          user ──profile_id──▶ counsellor
student.counsellor_id ──▶ counsellor   (counsellor.assigned_student_ids mirrors it)
application ──▶ student, counsellor, university, course, intake
application.history_ids ──▶ application_history (each also has application_id)
document ──▶ student, application (null for general documents), counsellor (reviewer)
counselling_session ──▶ student, counsellor
recommendation ──▶ student, university, course, created_by counsellor
notification ──▶ recipient_user_id (user), related_id (any doc)
course.university_id ──▶ university        country.catalogue_name = university.country
```

## Accounts and people

| type | Key fields |
|---|---|
| `user` | `email` (lowercase, unique), `password_hash` (PBKDF2), `role` (`student`/`counsellor`/`admin`), `full_name`, `profile_id`, `is_active`, `token_version`, `last_login`, `privacy_acknowledged_at` (self-registered students only: when they confirmed the registration privacy notice), `created_at`, `updated_at` |
| `password_reset` | `user_id`, `email`, `code_hash` (HMAC-SHA256 of the 6-digit code, never the code itself), `attempts`, `created_at`, `expires_at`. One per user; deleted after a successful reset. Not seed or demo data |
| `student` | `user_id`, `personal{first_name, last_name, preferred_name, email, phone{dial_code, number}, date_of_birth, gender, citizenship, address{line1, city, state, country, postal_code}}`, `academic{degree, institution, cgpa, gpa_scale, graduation_year, work_experience_years, gre_status, english_test{test_type, overall, listening, reading, writing, speaking}}`, `preferences{countries[], course_areas[], degree_level, intake, budget{min, max, currency}, requires_scholarship}`, `counsellor_id`, `counsellor_assigned_at`, `application_ids[]`, `profile_completion{overall, personal, academic, preferences, missing[]}`, `onboarding_status` |
| `counsellor` | `user_id`, `name`, `email`, `phone`, `specialization`, `region`, `max_students`, `is_active`, `assigned_student_ids[]` |

Notes:
- `preferences.countries` uses the catalogue's country names (`"UK"`, `"US"`, …). `personal.citizenship` and `personal.address.country` use the world name (`"United States"`). The API normalises known spellings (`"USA"` → `"US"` / `"United States"`) and rejects unknown countries; the list and aliases are in `apps/core/countries.py`, served by `GET /api/countries/`.
- `course_areas` uses course `cluster` names.
- `preferences.intake` matches an `intake.name`.

## Master data

| type | Key fields |
|---|---|
| `university` | `name`, `country`, `rank` (imported from `output/universities.json`) |
| `course` | `university_id`, `title`, `canonical_name`, `cluster` (imported catalogue; tuition, level and eligibility are not in the source data yet) |
| `country` | `code` (ISO), `name`, `catalogue_name` (value used in `university.country`), `currency`, `region`, `university_count` |
| `intake` | `name` (`"Fall 2027"`), `season`, `year`, `application_deadline`, `decision_by`, `start_date` |

## Workflow documents

### `application` (SRS 4.5)
```json
{
  "_id": "application_06289b302c18", "type": "application",
  "student_id": "student_…", "counsellor_id": "counsellor_…",
  "university_id": "university_042", "course_id": "course_0536", "intake_id": "intake_fall_2027",
  "status": "Documents Pending", "deadline": "2027-01-15", "decision_expected": "2027-04-15",
  "tier": "Target", "notes": "",
  "snapshot": {"university_name": "Technical University of Munich (TUM)", "country": "Germany", "world_rank": 45,
               "course_title": "Robotics & Autonomous Systems", "cluster": "CS & AI", "intake_name": "Fall 2027"},
  "history_ids": ["application_history_…"], "submitted_at": null,
  "created_at": "…", "updated_at": "…"
}
```
- **`status`** takes one of: Planned → Shortlisted → Documents Pending → Submitted → Under Review → Offer Received / Rejected, or Completed / Withdrawn.
- **Status changes** always append an `application_history` doc and add its ID to `history_ids`.
- **Allowed moves** (`applications/services.TRANSITIONS`): forward along the path, Under Review → Offer Received / Rejected, Offer Received → Completed, two correction steps back (Shortlisted → Planned, Documents Pending → Shortlisted), and Withdrawn from any open state. Rejected, Withdrawn and Completed are final. Students may only withdraw.
- **Deadline:** defaults to the intake's `application_deadline`; it must not have passed when the application is created and must fall before the intake's `start_date`. `notes` and `tier` are free for the counsellor.
- **Reaching Documents Pending** creates `Required` SOP and LOR documents for the application. **Submitted** is refused until every document for the application, and every general document of the student, is Verified.
- Created by the student (for themselves), their counsellor or an admin. Only a Planned application can be deleted; later ones are withdrawn so their history stays.

### `application_history`
| Field | Notes |
|---|---|
| `application_id` | owning application |
| `old_status` / `new_status` | `old_status` is `null` for the first entry |
| `changed_by`, `changed_by_role` | user ID and role of whoever made the change |
| `timestamp`, `remarks` | |

### `document` (SRS 4.6): metadata only
| Field | Notes |
|---|---|
| `student_id`, `application_id` | `application_id` is `null` for general documents (transcript, passport, …); set for SOP and LOR |
| `document_type` | Transcript, Degree Certificate, Passport, SOP, LOR, Resume/CV, Test Score, Other |
| `status` | Required, Uploaded, Under Review, Verified, Rejected, Expired |
| `title` | optional label, e.g. `LOR - Prof. Rao` (missing on seed docs = `""`) |
| `filename`, `uploaded_at` | `null` while the status is Required |
| `storage_ref` | `{kind: "attachment", name: "file", content_type, size}` when the file is stored as a CouchDB attachment named `file` on this document; `{kind: "url", url}` for a link to an external copy; `null` otherwise (seed docs are metadata only) |
| `verified_by`, `verified_at`, `remarks` | reviewer: counsellor ID, or the admin's user ID; `remarks` explains a Rejected or Expired status |
| `history[]` | `{status, at, by (user ID), by_role, remarks}` for every change (missing on seed docs = `[]`) |

Uploads accept PDF, PNG, JPEG, DOC and DOCX up to 5 MB; the content must match the extension. A file can be (re)uploaded while the document is Required, Uploaded, Rejected or Expired. Reviews (counsellor or admin): Uploaded → Under Review / Verified / Rejected, Under Review → Verified / Rejected, Verified → Expired. Rejected and Expired need remarks. The standard checklist (`POST /api/documents/checklist/`) is Transcript, Degree Certificate, Passport, Resume/CV and Test Score.

### `counselling_session` (SRS 4.7)
| Field | Notes |
|---|---|
| `student_id`, `counsellor_id` | |
| `scheduled_at`, `duration_minutes`, `mode` | `mode` is In person, Video call or Phone |
| `topic`, `status` | `status` is Scheduled, Completed or Cancelled |
| `summary`, `recommendations[]`, `action_items[]` | discussion summary, advice given and agreed actions (`action_items` missing on seed docs = `[]`) |
| `follow_up` | `{action, due_date, status: Pending/Done, completed_at}`, or `null`. It is a sub-document of the session it came from. |
| `completed_at`, `cancel_reason`, `created_by` | set by the API (not present on seed docs) |

A counsellor cannot hold two Scheduled sessions that overlap. Notes (summary, recommendations, actions, follow-up) are recorded when the session is completed, which is possible once it has started. A follow-up cannot be due before its session. A student's whole session history is visible to their current counsellor; only the session's own counsellor or an admin can change it. Students may mark their own follow-up done.

### `recommendation` (SRS 4.8)
| Field | Notes |
|---|---|
| `student_id`, `university_id`, `course_id`, `created_by` | `created_by` is a counsellor ID |
| `method` | `rule_based_v1` |
| `match_score` | 0–100 |
| `tier` | Reach, Target or Safe |
| `match_factors` | `{country_match, course_match, academic_fit, intake_available, budget_fit}` |
| `reasons[]` | human-readable explanation (SRS: recommendations must be transparent) |
| `status`, `remarks`, `snapshot` | `status` is Suggested, Accepted or Rejected |

### `notification` (SRS 4.10)
| Field | Notes |
|---|---|
| `recipient_user_id`, `recipient_role` | |
| `category` | status_change, missing_document, deadline, follow_up, assignment |
| `title`, `message`, `related_id`, `link`, `is_read`, `created_at` | |

### `audit_log` (SRS 5.3)
`action`, `actor_id`, `actor_role`, `target_id`, `details{}`, `ip`, `timestamp`.

## Indexes

`manage.py init_couchdb` creates the Mango indexes in `_design/aec_indexes`:

| Fields | Used for |
|---|---|
| `type` | per-type lists |
| `type`+`email` | user lookup |
| `type`+`user_id` | password-reset code lookup |
| `type`+`created_at` | sorted lists |
| `type`+`counsellor_id` | rosters |
| `type`+`rank`, `type`+`name` | university search |
| `type`+`is_active` | active filters |
| `type`+`student_id` | a student's applications, documents and sessions |
| `type`+`application_id` | an application's history and documents |
| `type`+`university_id` | courses and applications by university |
| `type`+`status` | status filters |
| `type`+`recipient_user_id` | a user's notifications |
| `type`+`deadline` | applications sorted by nearest deadline |
| `type`+`scheduled_at` | counselling history and the calendar |

## Sample dataset

```powershell
python manage.py seed_dataset            # write it (refuses if it already exists)
python manage.py seed_dataset --reset    # backup, remove, write again
python manage.py seed_dataset --remove   # backup, then delete only source="seed" docs
```

The dataset contains:
- **Master data:** 19 countries and 4 intakes.
- **Counsellors:** 5, each with a specialization and capacity.
- **Students:** 18, ranging from just registered to holding offers. 2 are unassigned so the administrator can assign them.
- **Applications:** 36, with 127 history entries.
- **Workflow:** 138 documents, 66 counselling sessions, 59 recommendations and 111 notifications.

All seeded accounts use the password `Seed@2026`:
- Students sign in as `firstname.lastname@students.example.org`, for example `ananya.iyer@students.example.org`.
- Counsellors sign in as `name@counsellors.example.org`, for example `priya.raman@counsellors.example.org`.
