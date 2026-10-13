# Sprint 1: Foundation and Core Data

**Sprint goal:** build the foundation and the core data that every later module depends on.

**Acceptance flow:** a user can **log in → have their role identified → reach the dashboard for that role → create or update a student profile → have a counsellor assigned**. The API test suite and a live HTTP run both complete this flow.

Requirement references (§) point to *SRS v1.0*. "PRD" means the AEC Admissions design brief. The PRD set the look of the UI only. Scope follows the SRS.

---

## 1. What was delivered

### Backend and authentication
| Item | Where | Notes |
|---|---|---|
| Django project setup | `backend/config/` | Django 6.1. No SQL database: `DATABASES = {}`. CouchDB is the only data store (§2.5). |
| DRF setup | `settings.REST_FRAMEWORK` | JSON only. Authenticated by default. Errors go through one shared handler. |
| Authentication APIs | `backend/apps/accounts/` | Register, login, logout, me, change password. Admins can list, activate and deactivate users. |
| User/account document | `apps/accounts/users.py` | Stored as `type: "user"`, separate from the business profile (§6.2). Passwords are hashed with PBKDF2 and never stored as plain text (§5.3). |
| Tokens | `apps/accounts/tokens.py` | Signed bearer tokens, valid for 8 h. Logout or a password change increments `token_version`, which revokes every older token. |
| Role-based authorization | `apps/accounts/permissions.py` | `IsStudent`, `IsCounsellor`, `IsAdmin`, `IsStaff`, plus per-record checks. All of it runs on the backend (§5.3). |
| Protected endpoints | all `/api/*` except register, login and health | A request with no token or a bad token gets 401. A request from the wrong role gets 403. |
| Audit trail | `apps/core/audit.py` | `audit_log` documents record login success and failure, registration, password changes, activation changes, counsellor assignment, and create/delete events (§4.1, §5.3). |
| Error handling | `apps/core/exceptions.py` | A CouchDB outage returns 503 with a friendly message. An edit conflict returns 409. Internal details are never shown to users (§5.2). |

### CouchDB, students and counsellors
| Item | Where | Notes |
|---|---|---|
| CouchDB database setup | `apps/core/db.py`, `manage.py init_couchdb` | Reuses the existing `apps/core/couchdb_client.py`. Creates 7 Mango indexes. Safe to run again. |
| Data-access layer | `apps/core/repository.py` | get, save, delete, find, count and paginate over Mango `_find` (§5.1 pagination). |
| Student document | `apps/students/services.py` | Has `personal`, `academic` and `preferences` sections, as in §6.4. Profile completion (overall and per section) and the list of missing fields are recalculated on every save, which tracks onboarding status (§4.2). |
| Counsellor document | `apps/counsellors/services.py` | Profile, `max_students` capacity, `is_active`, `assigned_student_ids`, and a calculated workload (§4.3). |
| Student CRUD APIs | `apps/students/views.py` | A student edits their own profile. A counsellor edits only their assigned students. An admin has full CRUD. |
| Counsellor CRUD APIs | `apps/counsellors/views.py` | Admins have full CRUD. A counsellor can edit only their own contact fields. Deleting a counsellor is refused while students are still assigned. |
| Student ↔ counsellor assignment | `apps/students/services.assign_counsellor` | Covers assign, reassign and unassign. Checks that the counsellor exists, is active and has spare capacity. Updates both documents and writes an audit entry. |
| University data | `manage.py load_universities` | Loads the local `output/universities.json` (100 universities). Documents that already exist are skipped. |

### Frontend (`frontend/`, served by Django, plain HTML/CSS/JS calling the API)
| Item | URL | Notes |
|---|---|---|
| Login | `/login/` | Student, Counsellor and Administrator tabs. The server checks that the chosen tab matches the account's role. |
| Register | `/register/` | Student self-registration. Counsellor and admin accounts are created by an administrator. |
| Role-based dashboard | `/dashboard/` | Student: readiness, counsellor, preferences. Counsellor: caseload KPIs and students who need attention. Admin: totals and counsellor workload. |
| Student profile UI | `/profile/`, `/students/<id>/` | Personal, Academic and Preferences tabs. Shows a readiness gauge, a missing-field checklist, a read-only counsellor card, and the raw CouchDB JSON. Admins also get assign and reassign controls. |
| Student roster | `/students/` | Admins see everyone, with search, filters, an Add Student button and assignment. Counsellors see only their own students. |
| Counsellor UI | `/counsellors/` | Admins create and edit counsellors and set capacity and active status. A counsellor edits their own profile here. |
| University search skeleton | `/universities/` | Search, country filter, ranking filter, sort and pagination. Students also see a bar showing their own preferences. Course details are a placeholder for now. |

The UI follows the PRD look: Space Grotesk headings, amber `#b45309` accent, `#f8f9ff` background. It was checked at 1366 px and 390 px wide with no horizontal scrolling. Labels are linked to their inputs, focus outlines are visible, and pop-out panels close with Esc.

---

## 2. How to run

> **CouchDB must be running.** On the development machine it is the Windows service **"Apache CouchDB"**. If it is stopped, start it from an **Administrator** terminal with `Start-Service "Apache CouchDB"`. Running `couchdb.cmd` directly fails because CouchDB cannot write its log under `Program Files`.

```powershell
cd backend
myenv\Scripts\activate                     # or: python -m venv myenv; pip install -r requirements.txt
python manage.py init_couchdb              # create DB + Mango indexes (safe to re-run)
python manage.py load_universities         # loads ../output/universities.json; existing docs are skipped
python manage.py create_admin --email admin@example.com   # prompts for a password
python manage.py seed_demo                 # optional: 2 counsellors + 3 students, password Demo@12345
python manage.py runserver
```
Then open http://127.0.0.1:8000/. Configuration lives in the repo-root `.env`. `.env.example` lists every key, including `DJANGO_SECRET_KEY`, which should be set before the project is shared anywhere.

**Tests** do not need CouchDB. They use an in-memory stand-in (`tests/fake_couch.py`):
```powershell
python manage.py test tests        # 21 tests
```

---

## 3. REST API

All responses are JSON. Send `Authorization: Bearer <token>`. List endpoints accept `?page=&page_size=` and return `{count, page, page_size, total_pages, results}`.

| Method & path | Who | Purpose |
|---|---|---|
| `GET /api/health/` | public | API and CouchDB reachability |
| `POST /api/auth/register/` | public | Student self-registration; returns a token |
| `POST /api/auth/login/` | public | `{email, password, role?}` → `{token, user}` |
| `POST /api/auth/logout/` | any | Revokes all of this user's tokens |
| `GET /api/auth/me/` | any | Current account and role |
| `POST /api/auth/change-password/` | any | Returns a new token |
| `GET /api/auth/users/` · `GET/PATCH /api/auth/users/<id>/` | admin | List, activate and deactivate accounts |
| `GET /api/dashboard/` | any | Summary for the caller's role |
| `GET /api/students/` | counsellor, admin | Roster. Filters: `q`, `status`, `counsellor_id`, `unassigned`. Counsellors see only their own students. |
| `POST /api/students/` | admin | Create a student account and profile, optionally with a counsellor |
| `GET/PATCH /api/students/me/` | student | Own profile. PATCH merges into the stored document. |
| `GET /api/students/me/counsellor/` | student | Assigned counsellor's contact card |
| `GET/PATCH /api/students/<id>/` | admin, assigned counsellor, the student | View or edit a profile. Send `rev` to detect edit conflicts (409). |
| `DELETE /api/students/<id>/` | admin | Remove the profile and its login account |
| `POST /api/students/<id>/assign-counsellor/` | admin | `{counsellor_id}` assigns or reassigns; `null` unassigns |
| `GET/POST /api/counsellors/` | admin | List with workload; create a counsellor |
| `GET /api/counsellors/options/` | admin | Active counsellors, for assignment pickers |
| `GET/PATCH /api/counsellors/me/` | counsellor | Own profile |
| `GET/PATCH/DELETE /api/counsellors/<id>/` | admin (counsellor: self, GET/PATCH only) | |
| `GET /api/counsellors/<id>/students/` | admin, self | That counsellor's roster |
| `GET /api/universities/` | any | `q`, `country`, `max_rank`, `sort=rank\|name` |
| `GET /api/universities/countries/` | any | Countries with university counts |
| `GET /api/universities/<id>/` | any | A university and its course documents (none loaded yet) |

### Access matrix (§4.1)
| | Student | Counsellor | Admin |
|---|---|---|---|
| Own student profile | read/write | — | — |
| Other students | ✗ (403) | assigned students only | all |
| Change counsellor assignment | ✗ | ✗ | ✓ |
| Counsellor records | own card (read-only) | own profile | all |
| Users and accounts | own | own | all |

---

## 4. CouchDB document model

All business documents carry a `type` field. This matches the university dataset already loaded into CouchDB, which uses `type` rather than the `doc_type` shown in the SRS example. IDs take the form `<type>_<12 hex>`.

| type | Key fields | Relationships |
|---|---|---|
| `user` | email (lowercase), password_hash, role, full_name, profile_id, is_active, token_version, last_login | `profile_id` → student or counsellor |
| `student` | personal{…}, academic{…, english_test{…}}, preferences{countries[], course_areas[], degree_level, intake, budget{min,max,currency}, requires_scholarship}, counsellor_id, profile_completion, onboarding_status, application_ids[] | `user_id` → user; `counsellor_id` → counsellor (source of truth) |
| `counsellor` | name, email, phone, specialization, region, max_students, is_active, assigned_student_ids[] | `user_id` → user; `assigned_student_ids` is a copy of the assignments, kept in sync |
| `university` | name, country, rank | From the dataset |
| `audit_log` | action, actor_id, actor_role, target_id, details, ip, timestamp | |

Onboarding status follows profile completion: `registered` (below 40%) → `in_progress` → `profile_complete` (100%) → `ready` (100% and a counsellor is assigned).

---

## 5. Verification

- **21 automated API tests pass** (`backend/tests/`, one file per domain). They cover registration, login (including failed attempts being logged), choosing the wrong portal, invalid and revoked tokens, password change, profile deep-merge and validation, edit conflicts (409), every role boundary, assign/reassign/capacity, counsellor and student CRUD, dashboards, university search and pagination, and CouchDB being down (503 with no internal details shown).
- **Live HTTP run.** The dev server ran against the in-memory database, seeded with the real `universities.json` and the demo accounts. The full acceptance flow worked over HTTP. Every page was screenshotted in headless Chrome as student, counsellor and admin at 1366 px, and at 390 px for mobile.
- **Not yet run against the real CouchDB server.** The CouchDB service was stopped during the sprint and starting it needs administrator rights. The first step on the dev machine is: start the service, then `init_couchdb` → `create_admin` → `seed_demo`, then walk through the flow in the browser.

---

## 6. Design decisions

- **No Django ORM or `django.contrib.auth`.** Accounts are CouchDB documents, so the project has one data store and no migrations, as §2.5 requires.
- **Signed stateless tokens with a per-user `token_version`.** Logout still works as a real revocation without adding a session store.
- **Email uniqueness is checked in the application** with a Mango lookup, because CouchDB has no unique constraints. Two registrations with the same email at the same instant could in theory both succeed. If that matters, a deterministic `_id` "email claim" document would close the gap.
- **Two-document updates** (assignment, user + profile creation) run one after the other, because CouchDB has no transactions. If the second write fails, the code rolls back or cleans up.
- **Counts use Mango `_find` and return only `_id`.** This is fine at academic scale. Later dashboards can switch to map/reduce views.
- **The dataset file `output/universities.json` is git-ignored** and must never be committed.

## 7. Next sprint candidates
Course, intake and country master data with admin CRUD (§4.4); applications and status history (§4.5); documents (§4.6); counselling sessions and follow-ups (§4.7); rule-based recommendations using the stored preferences (§4.8); notifications (§4.10).
