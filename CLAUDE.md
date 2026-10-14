# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Abroad Education Counselling & Student Application Management System, an academic project built against an SRS (v1.0). Stack: **Django 6 + Django REST Framework + Apache CouchDB** (the only database). It has three roles: `student`, `counsellor` and `admin`. Sprint 1 (foundation) is done: auth/RBAC, student and counsellor CRUD, counsellor assignment, dashboards and a university search skeleton. Sprint 2 (workflow) is done: applications with status transitions, history and deadlines, intakes, documents with upload and verification, and counselling sessions with follow-ups and a calendar. Recommendations and notifications are the next sprints. `docs/SPRINT1_FOUNDATION.md` and `docs/SPRINT2_WORKFLOW.md` record what exists and why.

## Commands

All Django commands run from `backend/` using the venv at `backend/myenv` (Windows: `myenv\Scripts\python.exe`).

```powershell
python manage.py test tests                                   # all API tests (no CouchDB needed)
python manage.py test tests.test_students                     # one module
python manage.py test tests.test_students.StudentProfileTests.test_profile_validation   # one test
python manage.py check
python manage.py runserver                                    # UI + API on http://127.0.0.1:8000/

python manage.py init_couchdb        # create DB + Mango indexes (idempotent)
python manage.py load_universities   # load ../output/universities.json; skips existing _ids
python manage.py create_admin --email x@y.z   # admins can only be created this way
python manage.py backup_couchdb      # dump every doc to output/backups/<db>-<timestamp>.json
python manage.py purge_demo_data     # report untagged demo docs; add --apply (auto-backup) to delete them
python manage.py seed_dataset        # write the SRS sample dataset (source="seed"); --reset / --remove
```

Frontend commands run from `frontend/` (Node 18+):

```powershell
npm install          # first time / after package.json changes
npm run build        # production build -> frontend/dist (what Django serves on :8000)
npm run dev          # hot-reload dev server on http://127.0.0.1:5173 (needs runserver on :8000 for /api)
```

`.\run.ps1` (repo root, Administrator) starts CouchDB, runs `init_couchdb`, installs and builds the frontend, then runs the server.

There is no linter, formatter or test runner for the frontend, and **no migrations**: `DATABASES = {}`, and `django.contrib.auth` is not installed.

CouchDB runs as the Windows service "Apache CouchDB" (3.5, `http://127.0.0.1:5984`). Starting it needs an Administrator shell (`Start-Service "Apache CouchDB"`). Running `couchdb.cmd` directly crashes because it can't write logs under Program Files. Connection settings come from the repo-root `.env` (`COUCHDB_URL/USER/PASSWORD/NAME`, `DJANGO_SECRET_KEY`, …; see `.env.example`).

## Architecture

**Layout.** `backend/config/` holds settings and the root URL map. `backend/apps/<domain>/` holds the domain apps (`core`, `accounts`, `students`, `counsellors`, `universities`, `dashboard`, and from Sprint 2 `applications` (+ intakes), `documents`, `counselling`). `frontend/` holds the React app (Vite); it contains no Python. Imports are absolute from `backend/`: `from apps.students import services`.

**Domain app pattern.** `services.py` owns the document shape, derived fields and business rules. `serializers.py` holds plain DRF `Serializer`s used only for input validation. `views.py` holds `APIView`s that call services and the repository. Put new logic in `services.py`, not in views.

**Data access.** There is no ORM. Everything goes through `apps/core/repository.py` (`get/save/delete/find/find_one/count/paginate`, `new_id`, `now_iso`, `public`, `contains_pattern`), which calls `apps/core/db.get_db()`. That returns a cached `couchdb.Database`; tests swap it with `set_db()`.
- Every document has a `type` field (`user`, `student`, `counsellor`, `university`, `course`, `audit_log`, …). IDs look like `<type>_<12 hex>`.
- Queries are Mango `_find`. A sorted query needs a matching index from `init_couchdb.INDEXES`, **and every indexed field must appear in the selector**. That's why list views add `"created_at": {"$gt": None}` and sort on `[{"type": dir}, {"created_at": dir}]`. Add new indexes to `INDEXES`, not ad hoc.
- `repository.public()` turns `_id/_rev` into `id/rev`. Clients send `rev` back on PATCH. A stale `rev` raises `ResourceConflict`, which the exception handler maps to **409**.
- CouchDB has no transactions or unique constraints. Writes that touch two documents (user + profile creation, counsellor assignment) are done in sequence with manual cleanup, and email uniqueness is checked in the application (`accounts/users.email_taken`).

**Auth.** `user` documents are kept separate from the student/counsellor profile and linked by `user.profile_id` ↔ `profile.user_id`. Passwords are hashed with Django's PBKDF2 hashers.
- Tokens are `django.core.signing` payloads `{uid, v}` sent as `Authorization: Bearer …` and read by `apps/accounts/backends.CouchTokenAuthentication`.
- `v` must equal `user.token_version`. Logout, password change and deactivation bump the version, which revokes every older token.
- `request.user` is an `AuthUser` exposing `.id/.role/.profile_id/.doc`.

**Authorization** is enforced only in the API.
- Use the role classes in `apps/accounts/permissions.py` (`IsStudent/IsCounsellor/IsAdmin/IsStaff`, `role_required(...)`).
- Per-record rules live in services. For example, `students/services.can_access` gives counsellors only students where `counsellor_id == user.profile_id`.
- Only admins assign counsellors, through `students/services.assign_counsellor`. It validates that the counsellor is active and has capacity, keeps `student.counsellor_id` (the source of truth) and `counsellor.assigned_student_ids` in sync, and writes an audit entry.

**Student profile.** It has `personal`, `academic` and `preferences` sections. PATCH payloads are deep-merged (`services.apply_update`). After every change, `refresh_derived()` recalculates `profile_completion` (driven by `COMPLETION_FIELDS`) and `onboarding_status` (`registered → in_progress → profile_complete → ready`).

**Workflow (Sprint 2).**
- Access to applications, documents and sessions always goes through the owning student: use `students/services.scope_to_students` for list selectors and `get_accessible` / `can_access` for single records. Never trust a `counsellor_id` stored on a workflow doc for access.
- Application statuses move only via `applications/services.change_status`, which checks `TRANSITIONS`, writes the `application_history` doc, creates the SOP/LOR checklist on *Documents Pending*, and blocks *Submitted* until the documents are Verified.
- Document files are CouchDB attachments named `file`. After `put_attachment`, reload the doc before saving it again, or CouchDB drops the attachment.
- Names for any id are resolved in batches with `apps/core/lookups.names_by_id`.

**Cross-cutting.**
- `apps/core/audit.record()` writes `audit_log` documents. It never raises.
- `apps/core/exceptions.api_exception_handler` maps CouchDB/OSError to 503 with a generic message, `ResourceConflict` to 409, and logs every 401/403.
- List endpoints return `{count, page, page_size, total_pages, results}` from `repository.paginate`.

**Frontend.** A React 18 single-page app (Vite, React Router, plain JSX, no other UI libraries) in `frontend/`. `npm run build` writes `frontend/dist`; Django serves it on the same origin as the API. Every page URL in `config/urls.py` maps to `apps/core/views.frontend_app`, which returns `dist/index.html` with `Cache-Control: no-cache`, and React Router renders the page. Built assets are served under `/static/assets/` with content-hashed names, so browsers never run stale code. `dist/` and `node_modules/` are git-ignored; `run.ps1` builds before starting the server. For live editing, run `npm run dev` (http://127.0.0.1:5173, hot reload, proxies `/api` to Django on :8000).
- `src/lib/api.js`: the `api()` client (401 → clears the session and redirects to login; `form` for FormData uploads), `download()` for authenticated files, and the `session` (token in `localStorage` as `aec.token`/`aec.user`).
- `src/lib/form.js`: `useForm` (`bind(path, type)` for dotted paths, `showErrors(drfErrors)`), `fieldErrors`, `trimStrings`. `src/lib/useLoad.js` loads data when deps change and ignores stale responses.
- `src/App.jsx`: routes plus `RequireAuth(roles)`, which redirects before a page mounts. Routes are keyed by URL, so each navigation starts the page fresh. Pages update filter query strings with `window.history.replaceState`, which doesn't remount them.
- `src/components/`: `Shell.jsx` (sidebar, role-based nav, top bar), `AuthLayout.jsx`, `Drawer.jsx`, `Toast.jsx` (`useToast`), `ui.jsx` (`Field`, `Pager`, `Kpi`, `ProgressBar` and the status/deadline badges), `Documents.jsx` (`DocRow`, upload and review drawers via `useDocActions`) and `ChipsInput.jsx`.
- One component per page in `src/pages/`.
- The design tokens follow the PRD: Space Grotesk, primary `#b45309`, background `#f8f9ff`. They're CSS variables in `src/styles/app.css`, and components use its class names.

**Tests.** `backend/tests/` uses `SimpleTestCase` and DRF `APIClient` against `tests/fake_couch.FakeCouchDB`, an in-memory stand-in that supports get/save/delete with revision conflicts and a subset of Mango (`$eq/$ne/$in/$gt*/$lt*/$regex/$exists/$or/$and`, sort, skip, limit, fields). New Mango operators must be added there too. `tests/base.APITestCase` seeds an admin and provides `login/as_user/register/create_counsellor`. `tests/base.WorkflowTestCase` adds a small catalogue, intakes dated relative to today, a student assigned to counsellor A, and an unrelated counsellor B. The fake also supports `put_attachment/get_attachment`. Tests use the MD5 hasher for speed.

## Live database state

`counselling_db` holds three kinds of data:
- **Real data entered through the app:** 3 accounts (`admin@aec.local`, counsellor `ridhin@gmail.com`, student `christinjb100@gmail.com`) and their audit entries. Never modify or delete these from scripts.
- **Catalogue:** 100 `university` docs (from `output/universities.json`) and 1,258 `course` docs (`title`, `canonical_name`, `cluster` with an en dash, `university_id`; no tuition or level yet).
- **The SRS sample dataset**, written by `seed_dataset` (`apps/core/seeding.py`) and tagged `"source": "seed"`:
  - Master data: `country` and `intake` docs.
  - People: 5 counsellors and 18 students. All 23 seeded accounts can log in with password `Seed@2026`.
  - Workflow: `application` + `application_history`, `document`, `counselling_session`, `recommendation` and `notification` docs.
  - Removal: `seed_dataset --remove` deletes exactly the seed docs, and `purge_demo_data` never touches them.
- **Workflow docs created through the app** (applications, documents, sessions) are real data. `purge_demo_data` keeps any workflow doc whose student or user is kept.
- To exercise write flows against real CouchDB without touching `counselling_db`, run with `COUCHDB_NAME=<scratch db>` (env vars override `.env`), copy the catalogue in, `seed_dataset`, then delete the scratch DB.

Document shapes for every type are in `docs/DATA_MODEL.md`, and the allowed status values are in `apps/core/vocab.py`. Use those vocabularies in new APIs.

Never assume a new document type's shape; inspect real docs first.

## Repo rules

- **Apache CouchDB is the only data store.** Do not add SQLite, Postgres, Redis or any other database. Do not add Django ORM models, migrations, or `django.contrib.auth`, `sessions` or `admin`. `DATABASES` stays `{}`.
- **Every account is exactly one `user` document in CouchDB.** It holds the PBKDF2 `password_hash`, `role`, `profile_id` and `token_version`, and links to its `student`/`counsellor` profile by `profile_id` ↔ `user_id`. Credentials are never stored anywhere else.
- **No untagged demo data in `counselling_db`.** Sample data may only be created by `seed_dataset`, which tags every doc `"source": "seed"` and builds people through the same services as the API. Never hand-write demo docs, and never change real (untagged) data from scripts.
- **Never show raw document IDs in the UI.** The API resolves names (for example `counsellor_name` on student rows via `students/services.attach_counsellor_names`). Counsellor workload is always counted from `student.counsellor_id` (`counsellors/services.assigned_counts`), never from the denormalised `assigned_student_ids`.
- `output/` holds the local dataset (`universities.json`). It is git-ignored and **must never be committed**. The same goes for `.env`.
- Don't write role or permission checks only in the frontend. Every rule must be enforced by the API.
