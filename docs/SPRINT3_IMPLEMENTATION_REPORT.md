# Sprint 3: Recommendations, Dashboards, Notifications and Hardening

**Sprint goal:** complete the system with the SRS features left after Sprints 1 and 2: rule-based recommendations (§4.8), functional dashboards for every role (§4.9), in-app notifications (§4.10) and course maintenance (§4.4). Then measure it, and harden it against the scale and concurrency problems that measurement exposed.

Requirement references (§) point to *SRS v1.0*. Test evidence is in [`SPRINT3_TEST_REPORT.md`](SPRINT3_TEST_REPORT.md), endpoints in [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md), document shapes in [`DATA_MODEL.md`](DATA_MODEL.md), and query and consistency design in [`DATABASE_AND_SCALABILITY.md`](DATABASE_AND_SCALABILITY.md).

---

## 1. Summary

| Area | Delivered |
|---|---|
| Recommendations (§4.8) | A deterministic rule-based engine scores the catalogue on 5 weighted factors (country, course area, academic fit, intake, budget) and checks 4 hard eligibility rules (level, minimum grade, English score, open intake). Results are persisted with factor-level detail, reasons, missing data, an algorithm version and a timestamp. Refreshing is idempotent, staleness is detected, and counsellors review, accept, reject, re-tier and add recommendations. |
| Dashboards (§4.9) | Student: applications, documents needing action, deadlines, recommendations with reasons, notifications. Counsellor: review queue, students needing attention, pending follow-ups, pipeline, filters. Admin: totals, pipelines, document status, reports by country/university/intake, offer rate, counsellor workload and activity, filters by counsellor/country/intake. |
| Notifications (§4.10) | Persistent in-app notifications for the four SRS categories plus counsellor assignment. Event notifications come from status changes, document requests and rejections, and agreed follow-ups. Time-based reminders cover deadline windows, outstanding documents and due follow-ups (a management command plus a throttled on-access sweep). Deduplication is by deterministic ID. Ownership is enforced, read state is persisted, and there is a bell, a full page and mark-all-read. |
| Course maintenance (§4.4) | Admins add courses and record level, duration, tuition, entry grade, English minimums and intakes, or deactivate outdated courses. The engine uses these fields as soon as they exist. |
| Scalability (§5.1) | Benchmarks at 1,000 students showed the admin dashboard taking over 5 s. A design document of map/reduce views, transparent view routing in the repository and composite indexes brought every measured endpoint within target at 100, 1,000 and 10,000 students for single requests. Under 8 concurrent requests the admin dashboard at 10,000 students still misses the 500 ms p95 target (798 ms), limited by CouchDB view work (see the test report). |
| Verification | 136 backend tests (63 new), 28 frontend tests (9 new), 35 live HTTP acceptance checks, 52 page/interaction checks and 6 loading/empty/error/session checks in headless Chrome against real CouchDB 3.5, plus index and view verification on 4 databases (up to 278,917 documents). |

## 2. Audit before implementation

The SRS, all of Sprint 1 and 2, the live database's document shapes and the test suite were read before coding. Findings that shaped the work:

| Finding | Consequence |
|---|---|
| `recommendation` and `notification` docs existed only as seed data (59 + 111); no code read or wrote them | Built both features from scratch, kept the seed shapes readable, and upgraded seed recommendations in place on refresh |
| The imported catalogue has only `title`, `canonical_name`, `cluster` for 1,258 courses: **no tuition, level, eligibility or per-course intakes** | The engine reports these as *missing* (`insufficient_data`) and never invents them. Admin course editing (§4.4, previously missing) lets real values be recorded |
| Student `course_areas` is free text ("Computer Science, AI/ML"), while seed students use cluster names | Course matching handles exact clusters, a documented alias list, title matches and shared significant words |
| Intakes are agency-wide; Spring 2027's deadline (2026-09-30) had already passed | The intake factor checks the preferred intake and suggests the next open one; a course whose recorded intakes are all closed is ineligible |
| Sprint 2 left notification hooks for "the notifications sprint" | Hooked into `change_status`, `ensure_checklist`, `review`, `complete` and `assign_counsellor` after their primary write |
| Baseline: 73 backend + 19 frontend tests passing | Kept green throughout; final 136 + 28 |
| *(found while benchmarking)* Mango cannot use an index for `$in`, and loads every candidate document | Caseload queries, name lookups, counts and admin aggregates were orders of magnitude slower than necessary at 1,000+ students (§7) |

## 3. Requirements-to-implementation matrix

| Requirement (SRS) | Before Sprint 3 | Change | Files | Acceptance tests | Status |
|---|---|---|---|---|---|
| §4.8 Match target country | NOT IMPLEMENTED (seed only) | `country_factor` | `recommendations/engine.py` | `FactorTests.test_country`, live check "generate" | PASS |
| §4.8 Compare preferred course with available courses | NOT IMPLEMENTED | `course_factor` (cluster, alias, title, token) | engine | `test_course_area_matching` | PASS |
| §4.8 Academic eligibility | NOT IMPLEMENTED | hard rules `grades`, `english`, `level`; soft `academic_factor` | engine | `HardRuleTests`, `test_hard_failure_beats_a_perfect_preference_score` | PASS |
| §4.8 Intake information | NOT IMPLEMENTED | `intake_factor` + hard `intake` rule | engine | `test_intake` | PASS |
| §4.8 Budget vs tuition when available | NOT IMPLEMENTED | `budget_factor` (same currency only) | engine | `test_budget` | PASS (no tuition in the imported catalogue: reported as missing) |
| §4.8 Record reasons / factors | NOT IMPLEMENTED | `match_factors`, `checks`, `reasons`, `missing_data` persisted | `recommendations/services.py` | `test_generate_persists_explainable_results` | PASS |
| §4.8 Counsellors review, accept, modify, add | NOT IMPLEMENTED | `PATCH` / `POST /api/recommendations/` | `recommendations/views.py` | `test_decisions_survive_refresh…`, `test_counsellor_adds…`, live checks | PASS |
| §4.9 Student dashboard | PARTIAL (no recommendations, document list or notifications) | added sections | `dashboard/services.py`, `Dashboard.jsx` | `test_student_dashboard_shows_own_records`, browser | PASS |
| §4.9 Counsellor dashboard | PARTIAL (no review queue or filters) | review queue, attention ranking, filters | same | `test_counsellor_dashboard_is_limited_to_assigned_students` | PASS |
| §4.9 Admin dashboard + filters + reports | PARTIAL (no filters or reports) | reports, outcomes, activity, filters | same | `test_admin_aggregates_match…`, `ViewBackedDashboardTests` | PASS |
| §4.10 Status-change notifications | NOT IMPLEMENTED | `events.application_status_changed` | `notifications/events.py` | `test_status_change_notifies_everyone_but_the_actor` | PASS |
| §4.10 Missing/required documents | NOT IMPLEMENTED | events + deadline-window and weekly reminders | `events.py`, `reminders.py` | `test_document_events`, `test_outstanding_documents…` | PASS |
| §4.10 Deadline and follow-up reminders | NOT IMPLEMENTED | `send_reminders` + on-access sweep | `reminders.py` | `test_deadline_windows…`, `test_follow_up_reminders` | PASS |
| §4.10 In-app display | NOT IMPLEMENTED | bell, page, dashboard cards | `NotificationBell.jsx`, `Notifications.jsx` | browser checks | PASS |
| §4.4 Admin create/update/deactivate courses; tuition, eligibility | PARTIAL (read-only) | course `POST`/`PATCH`, editor | `universities/*`, `CourseEditor.jsx` | `CourseAdminTests` | PASS |
| §4.1 / §5.3 RBAC and record-level access on new endpoints | — | role classes + access through the owning student / recipient | all new views | `test_access_rules`, `test_ownership`, live 403 checks | PASS |
| §5.1 Dashboard ≤ 3 s, API ≤ 2 s; pagination | PARTIAL (failed at 1,000 students) | views, routing, indexes, catalogue cache | `core/couch_views.py`, `core/repository.py` | benchmarks | PASS for the SRS limits (max 947 ms / 1,246 ms); the stricter 500 ms dashboard target is PARTIAL (admin, 10,000 students, 8 concurrent: 798 ms) |
| §5.2 Graceful errors | PASS (Sprint 1) | notifications and reminders never break the triggering request; failures logged | `notifications/*` | `test_notify_is_idempotent…` (CouchDB down) | PASS |

## 4. Recommendation engine

**Where:** the scoring is in `backend/apps/recommendations/engine.py` (pure functions, no database). Persistence, refresh and review are in `services.py`.

### 4.1 Factors and weights
Weights are configurable in `settings.RECOMMENDATION_WEIGHTS` (defaults below). The SRS defines no weights, so these were chosen to make the target country and the subject the main drivers.

| Factor | Weight | Score m (0–1) | Unknown when |
|---|---|---|---|
| Country | 30 | 1 if the university's country is a target country, else 0 | the student has no target countries |
| Course area | 30 | 1 cluster match (directly or via `AREA_ALIASES`), 0.8 title match, 0.5 shared significant word, 0 none | no preferred areas |
| Academic fit | 20 | With a recorded minimum grade: 0.7 + 0.3·(grade − min)/10, capped at 1. Otherwise an **estimate**: linear over the 20 points below a typical grade for the world-ranking band (90% top 25, 80% top 50, 72% top 100, 65% beyond) | no CGPA/scale, or no requirement and no ranking |
| Intake | 10 | 1 if the preferred intake is open and offered; 0.5 if only another intake is | no preferred intake; no intakes recorded |
| Budget | 10 | 1 if annual tuition ≤ max budget; 0.5 if ≤ 20% over; 0 otherwise. Compared only in the same currency | no max budget; no tuition; different currencies (no exchange rates are stored or invented) |

```
match_score   = round(100 · Σ wᵢ·mᵢ / Σ wᵢ)      over the factors with data   (shown: "86% match")
confidence    = round(100 · Σ wᵢ(with data) / Σ wᵢ)                          (shown: "90% assessed")
ranking_score = round(100 · Σ wᵢ·mᵢ / Σ all wᵢ)    = match_score × confidence (used to rank and to cut off)
```
**Missing data is never a match.** An unknown factor drops out of `match_score` and lowers `confidence`. Ranking uses `ranking_score`, where unknown counts as 0, so a course is never ranked above another merely because less is known about it. An earlier draft ranked by `match_score` and failed this test: a course with one known matching factor scored 100 and outranked a fully assessed 95 (`test_missing_data_is_never_a_match`). Missing inputs are listed by source (`profile` or `catalogue`), so the UI can say what to add.

### 4.2 Hard eligibility rules
| Rule | Fails when | Unknown when |
|---|---|---|
| Degree level | the course's recorded level ≠ the student's target level | no course level, or no target level |
| Entry grade | the normalised grade (CGPA/scale·100) < the recorded `min_grade_pct` | no requirement, or no grade |
| English | the overall score < the recorded minimum **for that test** | no requirement, no score, or a test the course does not list |
| Open intake | none of the intakes the course is offered in (all intakes if not recorded) is open | no intakes recorded |

`eligibility` is `ineligible` if any rule fails, else `insufficient_data` if any is unknown, else `eligible`. **Ineligible courses are never recommended**, cannot be added by a counsellor (400) and cannot be accepted (400), whatever their score. The SRS asks only to *consider* the budget (§4.8), so budget is a soft factor and over-budget courses are ranked lower, not excluded. With today's catalogue every course is `insufficient_data` because no requirements are recorded. The UI says "Eligibility to confirm with the university" instead of implying eligibility.

### 4.3 Candidates, ranking and limits
- **Candidates:** every active course at an active university that is in a target country, or elsewhere with a strong subject match (course factor ≥ 0.8). If a profile has neither countries nor areas, the result is `insufficient_profile` with a message, not an error.
- **Order:** `ranking_score` desc, `match_score` desc, world rank asc, university name, course title, course ID. This is fully deterministic: the same inputs give the same order (`test_ranking_pool_exclusions_and_determinism`, live idempotence check).
- **Limits:** `ranking_score ≥ MIN_SCORE` (40), at most `PER_UNIVERSITY` (2) per university for variety, and `LIMIT` (15) in total.

### 4.4 Persistence and lifecycle
- Every result is stored as a `recommendation` with a deterministic ID (`sha1(student_id|course_id)`). A refresh, even concurrent, updates rather than duplicates. Every stored result carries its factors, checks, reasons, missing data, `method: rule_based_v2` and `generated_at`.
- **Refresh** (`POST /api/recommendations/generate/`, by the student, their counsellor or an admin) writes the results in one `_bulk_docs` request. Undecided engine suggestions that drop out are deleted. Accepted/Rejected decisions and counsellor additions are kept and re-scored (`in_latest_run: false`). A document changed by someone during the refresh keeps their status and remarks. A counsellor-set tier survives refreshes.
- **Run summary:** one `recommendation_run` per student records the stats (courses evaluated, eligible, insufficient data, ineligible by rule, below threshold, recommended), the weights and the input fingerprint.
- **Freshness:** `current`, `stale` (with the reason: profile/intake dates changed, or the catalogue was edited) or `never`. Stale results are flagged with a Refresh button and never recomputed silently on read.
- **Seed data:** the 59 seed `rule_based_v1` documents stay readable (the API normalises their factors). A refresh upgrades them in place, keeping their status and `source: "seed"` tag.

## 5. Notification lifecycle

```
business event / reminder window ──► notify(event_key, recipient) ──► notification (id = sha1(event_key|recipient))
                                                                         │  exists already → skipped (idempotent)
bell (unread count, polled 60 s) ◄── GET unread-count ◄──────────────────┤
notifications page / bell panel ◄── GET list (newest first, filters) ◄───┤
open / mark read / mark all read ──► POST read (bounded retry on 409) ───┘
```

| Category | Raised by | Recipients |
|---|---|---|
| `status_change` | `applications.change_status`, after the application and its history entry are saved | the student and their counsellor, except whoever made the change |
| `missing_document` | staff adding requirements (a checklist, *Documents Pending*, a single document); a document marked Rejected or Expired; reminders | the student (and the counsellor for deadline-window reminders) |
| `deadline` | reminders: 14, 7 and 1 day before, and once when overdue (pre-submission applications only) | student and counsellor |
| `follow_up` | a follow-up agreed when a session is completed; reminders when due today/tomorrow and when overdue | student; counsellor for reminders |
| `assignment` | `assign_counsellor` | the student and the new counsellor |

- **Idempotence:** event keys include what makes an event distinct: the history entry, the document's review count, or the application + deadline + window. A retry, a second sweep or a concurrent worker can never create a second notification. Moving a deadline starts a fresh set. A refused change (wrong transition, stale `rev`) creates nothing, because notifications are written only after the change is saved.
- **Failure policy:** `notify()` never raises. The triggering change is already saved, and a failure is logged with its traceback. The in-app notification is a convenience copy of state the app shows anyway (history, document status, deadlines).
- **Scheduling:** no scheduler is configured by default. `python manage.py send_reminders` sweeps everyone and can be run any number of times. On Windows, schedule it daily with Task Scheduler:
  ```powershell
  schtasks /Create /TN "AEC reminders" /SC DAILY /ST 07:00 /TR "D:\dbms\AEC_Management_System\backend\myenv\Scripts\python.exe D:\dbms\AEC_Management_System\backend\manage.py send_reminders"
  ```
  (On Linux: a cron entry `0 7 * * * cd …/backend && myenv/bin/python manage.py send_reminders`.) So that reminders appear even without a schedule, opening the dashboard or notifications also sweeps **the caller's own caseload**, at most once per 15 minutes per user (`ON_ACCESS_INTERVAL`, Django's local-memory cache). Admins have no reminders.
- **Privacy:** messages contain course and university names and, for counsellors, the student's name. They contain no contact details or document contents.

## 6. Dashboards

All figures are computed from stored documents on each request; nothing is cached or fabricated. Every element links to the page where the user can act on it.

| Role | What it shows | Scope |
|---|---|---|
| Student | Profile readiness and missing fields, open applications with status and deadline countdown, documents needing action (rejected/expired first, with the counsellor's remarks), upcoming deadlines and sessions, follow-ups, the top 3 recommendations with score, eligibility and first reason (with a stale warning), latest notifications | own records |
| Counsellor | Caseload KPIs, documents to review (oldest upload first), follow-ups, deadlines, pipeline, upcoming sessions, notifications, and students needing attention (most outstanding documents, then least complete profile, with open applications). Filters: country, intake | students whose `counsellor_id` is theirs |
| Admin | Totals (students and unassigned, counsellors and active, universities, courses and active, applications), pipeline, document status, deadlines, sessions, follow-ups, recommendation status, reports by country/intake/top universities with offers, offer rate, workload and activity of the 10 busiest counsellors. Filters: counsellor (all figures), country and intake (application figures) | everyone; aggregates expose no student contact details |

## 7. Measured performance problem and fix

The first benchmark on 1,000 students (27,775 documents) took **over 5 s per admin dashboard**, about 1.4 s per Mango query over a document type. Investigation (`_explain` and timing) found two Mango limits. It loads every candidate document even with a field projection. And it cannot use an index for `$in`, which every counsellor query relied on (`student_id: {"$in": caseload}`), as did every batched name lookup (`_id: {"$in": …}`).

The fix uses CouchDB's own tools, and every change is measured and verified:
1. **`_design/aec_stats`**, 11 map/reduce views, for counts, distributions and multi-key lookups. Each JavaScript map has a Python twin for the tests, and `check_indexes` verified the JavaScript against Mango on 4 databases (37/37 answers equal on each).
2. **Transparent routing in `repository.find`** of `student_id $in` (via the view) and `_id $in` (via `_all_docs`). The remaining selector is applied by `apps/core/mango.py`, the same matcher the test fake uses. Equivalence with Mango is tested (`test_repository.py`).
3. **Exact counts from reduce views** for paginated lists (whole type, `created_at > null`, status filters).
4. **Composite indexes** `[type, counsellor_id|student_id, created_at|scheduled_at]`.
5. **The agency-wide summary endpoints** (`/api/applications/summary/`, `/api/documents/summary/`), which loaded every application/document for admins, now use the same views.
6. **A second profiling round at 10,000 students** found the admin dashboard at ~590 ms in-process. Three changes brought it to ~300 ms: `_sum` views that return one row per value or per student instead of one per status (`application_dims`, `student_workload`), and compact counsellor rows. Recommendation generation spent ~290 of ~400 ms loading the catalogue. It is now cached per process with a version key (see `DATABASE_AND_SCALABILITY.md` §8), bringing it to ~150 ms.

Per-query results: counts 1,415 → 13 ms, a caseload's documents 1,357 → 15 ms. The resulting API latencies are in the test report.

## 8. Role permissions (new endpoints)

| Endpoint | Student | Counsellor | Admin |
|---|---|---|---|
| List / read recommendations | own | assigned students | all |
| Generate recommendations | own | assigned students | all |
| Add / review a recommendation | ✗ 403 | assigned students | all |
| Notifications (list, read, mark) | own only | own only | own only |
| Dashboard | own | own caseload (+ country/intake filters) | everything (+ counsellor filter) |
| Course details | read (active only) | read (active only) | read all, create, edit, deactivate |

Access to recommendations goes through the owning student (`students.services.can_access`), as for every workflow record. Notifications check `recipient_user_id == user.id`. The API ignores client-supplied owner fields: a student's `student_id` parameter, and any recipient field on a read request.

## 9. API and data changes

- **New endpoints:** `recommendations/` (list, add), `recommendations/generate/`, `recommendations/<id>/` (read, review); `notifications/`, `notifications/unread-count/`, `notifications/read-all/`, `notifications/<id>/`, `notifications/<id>/read/`; `universities/courses/<id>/` (read, edit); `universities/<id>/courses/` (create). Details are in [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md).
- **Changed endpoints:** `dashboard/` (new sections and filters); `applications/` create refuses inactive courses; `applications/summary/` and `documents/summary/` are view-backed for admins; course lists hide inactive courses from non-admins; student and counsellor deletion also remove notifications and recommendation runs.
- **New and changed document types:** `recommendation` (v2 shape), `recommendation_run`, `notification` (`event_key`, `related_type`, `read_at`), course fields. Indexes: +7 Mango indexes; views: `_design/aec_stats`. **No existing document needs migrating:** old shapes are read as they are.
- **Pages:** `/recommendations/`, `/notifications/` (and the bell); the dashboard and university pages are extended.

## 10. Files changed

| Area | Files |
|---|---|
| New apps | `backend/apps/recommendations/` (`engine.py`, `services.py`, `views.py`, `urls.py`), `backend/apps/notifications/` (`services.py`, `events.py`, `reminders.py`, `views.py`, `urls.py`, `management/commands/send_reminders.py`) |
| Data layer | `apps/core/repository.py` (view routing, `get_many`, `bulk_save`, `stable_id`, `status_counts`, fast counts), `apps/core/couch_views.py`, `apps/core/mango.py`, `apps/core/vocab.py`, `init_couchdb.py` (indexes + views), new commands `check_indexes`, `bench_seed`, `bench_run` |
| Dashboards | `apps/dashboard/services.py` (new), `views.py` |
| Hooks into Sprint 1/2 | `applications/services.py` (status-change notifications, inactive courses, agency summary), `documents/services.py`/`views.py`, `counselling/services.py`/`views.py` (follow-up notification, index-matching sorts), `students/services.py`/`views.py` (assignment notification, cascade, roster sort), `counsellors/services.py`/`views.py`, `core/seeding.py`, `core/maintenance.py` |
| Courses | `universities/serializers.py`, `services.py` (new), `views.py`, `urls.py` |
| Frontend | `pages/Recommendations.jsx`, `pages/Notifications.jsx`, `components/NotificationBell.jsx`, `components/CourseEditor.jsx`, `lib/recommendations.js`, `lib/notifications.js` (new); `Dashboard.jsx`, `Universities.jsx`, `Applications.jsx` (intake prefill), `Shell.jsx`, `App.jsx`, `app.css` |
| Tests | `test_recommendation_engine.py`, `test_recommendations.py`, `test_notifications.py`, `test_dashboard.py`, `test_repository.py` (new); `fake_couch.py` (views, bulk), `base.py`, `test_seeding.py`; `frontend/tests/sprint3.test.js` |

## 11. Deviations from the brief, and their reasons

- **`type`, not `doc_type`:** the SRS example uses `doc_type`; the project has used `type` since Sprint 1 (the imported catalogue already used it). Kept for consistency.
- **Budget is soft:** the SRS says to *consider* budget (§4.8), not to exclude by it.
- **No ML:** as the SRS allows, the engine is rule-based.
- **Reminder scheduling** is a command plus an on-access sweep; no OS scheduler was configured from code.
- **Workload table** on the admin dashboard shows the 10 busiest counsellors, with a link to all of them, so the dashboard stays bounded at any agency size.

## 12. Known limitations and outstanding issues

| Issue | Severity | Impact | Next action |
|---|---|---|---|
| The imported catalogue has no tuition, level, entry requirements or per-course intakes | Medium (data) | Budget is never scored and eligibility is always "to confirm" until admins record course details | Enter details for the courses students apply to most (the editor exists) |
| `$regex` text search reads every document of the type | Low at current size | Slow name/course search on very large student or application sets | Add a search index (Nouveau/Clouseau) if needed |
| Benchmarks ran on Django's development server on one machine | — | Not production-equivalent | Re-measure behind a WSGI server before deployment |
| Notification creation is best-effort after the primary write | Low | A CouchDB failure between the two writes loses that one notification (logged) | Acceptable for in-app convenience copies; could add an outbox if email/SMS is introduced |
| No component-level React tests (no jsdom in the toolchain) | Low | UI states are covered by the headless browser pass, not unit tests | Add a DOM test runner if the UI grows |
| First view build on a large database exceeds CouchDB's request timeout | Low (deploy step) | The first dashboard after a view change can return 503 until the build finishes | Run `check_indexes` after `init_couchdb` and before serving traffic (documented) |

| Admin dashboard p95 798 ms at 10,000 students with 8 concurrent requests (target 500 ms) | Medium (performance) | Slower agency overview under heavy simultaneous admin use; single requests take 318 ms | Short-TTL cache of agency aggregates, or more CouchDB capacity |
| A pre-existing Mango index `applications_by_student` outside `aec_indexes` exists in `counselling_db` | Info | The planner sometimes picks it (equivalent answers) | Review and remove it if it is a leftover |

No critical or high-severity defects are known to be open.
