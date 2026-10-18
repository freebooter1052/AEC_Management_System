# Sprint 3 test report

Evidence for [`SPRINT3_IMPLEMENTATION_REPORT.md`](SPRINT3_IMPLEMENTATION_REPORT.md). Every number below comes from a run on 16–17 October 2026; nothing is estimated.

## 1. Environment

| Item | Value |
|---|---|
| Machine | AMD Ryzen 9 7940HS (8 cores / 16 threads), 15.3 GB RAM, Windows 11 Home |
| Database | Apache CouchDB 3.5 (Windows service, single node, default configuration) |
| Backend | Python 3.12, Django 6.1.2, DRF 3.18.3, CouchDB-Python 1.2 |
| Frontend | Node 22.12, Vite 5.4, React 18.3; Chrome (headless) for browser checks |
| Server under test | `manage.py runserver` (Django's single-process development server), `DJANGO_DEBUG=false` for the benchmarks |

These are **local development measurements**, not production-equivalent: one machine runs the client, the server and CouchDB, and the server is Django's development server.

## 2. Commands executed

```powershell
cd backend
python manage.py test tests                     # automated backend suite
cd ..\frontend; npm test; npm run build         # frontend unit tests and production build
cd ..\backend
python manage.py check_indexes                  # on the scratch, bench and live databases
# live acceptance and browser checks: scratch database aec_sprint3_check (copy of the catalogue + seed_dataset)
# benchmarks: bench_seed --students 100 | 1000 | 10000, then bench_run (see §5)
```

## 3. Results summary

| Suite | Passed | Failed | Skipped / blocked |
|---|---|---|---|
| Backend automated tests (`manage.py test tests`) | **136** | 0 | 0 |
| Frontend unit tests (`npm test`) | **28** | 0 | 0 |
| Live HTTP acceptance on real CouchDB (35 checks, re-run 34 after later changes) | **35 / 35**, then **34 / 34** | 0 | 1 on the re-run: no uploaded document was left to reject |
| Headless-browser pages and interactions (3 roles, 1366 px and 390 px) | **52 / 52** | 0 | 0 |
| Headless-browser loading / empty / error / session states | **8 / 8** | 0 | 0 |
| Index check (`_explain`, 17 patterns) on 5 databases | **all use an index** | 0 full scans | — |
| View vs Mango consistency (37 answers) on 5 databases | **37 / 37 each** | 0 | — |
| Regression: Sprint 1 and 2 tests (73 at the start) | **73 / 73** | 0 | 0 |

No test was skipped or disabled. Failures met during the sprint and how each was resolved:
- **Engine test (`test_course_area_matching`):** the expectation was wrong. A title contained in the area text is a title match by design, so the test was corrected and a genuine token-only case added.
- **Fast count test:** this found a **real bug**. `created_at > null` counts assumed every document has `created_at` (31 counted vs 30 actual). The `by_type` view was changed to carry that flag, so counts are exact.
- **Staleness test:** this found a **real bug**. Course edits in the same second as a run were missed, so the comparison changed from `>` to `>=`.
- **Browser, bell panel at 390 px:** a **real layout bug**. The panel overflowed 37 px off the left edge. It is now pinned to the viewport on phones.
- **Browser, "Why this course?" and "Try again":** the test selector or timing was wrong. The screenshots showed both working, and the checks were corrected.
- **Live re-run, "stale after profile change" and "18 students":** these were state left by the previous run, and the checks were made state-independent.

## 4. Coverage by area

| Area | Tests (file) | What is covered |
|---|---|---|
| Recommendation factors and rules | `test_recommendation_engine.py` (16) | Each factor's match/partial/no-match/unknown; grade and budget **boundaries** (exactly at the minimum, exactly 20% over); intake open/closed/not offered/none; level, grade and English rules; exact weighted score; **a hard failure beats a perfect score**; **missing data never ranks higher**; pool, inactive and unlinked courses; per-university cap; deterministic order whatever the input order; empty catalogue and empty profile; the fingerprint tracks only relevant inputs |
| Recommendation API | `test_recommendations.py` (14) | Persisted factors, reasons, missing data and run; deterministic IDs; **idempotent, deterministic refresh** by 3 roles; hard rules exclude, block adding and block accepting; decisions and counsellor tiers survive refresh; staleness (profile, intake, catalogue); catalogue cache invalidation; **RBAC** (other student, other counsellor, anonymous, wrong role, staff without a student); 404/400; **stale `rev` → 409 with nothing changed**; **concurrent edit during refresh preserved** (simulated race); empty catalogue; incomplete profile; pagination bounds; seed v1 documents read and upgraded; cascade on student deletion |
| Notifications | `test_notifications.py` (16) | Every event (assignment, status change except to the actor, a refused or stale change creates nothing, document requests and rejection, agreed follow-up); `notify` **idempotent** per event and recipient, never raises (CouchDB down); deadline windows 14/7/1/overdue each once, the grace limit, a **moved deadline** starts afresh, submitted applications skipped; outstanding documents and weekly digest; follow-up due and overdue, done stops reminders; broken records don't crash the sweep; command output; on-access sweep **throttled**; list, filters, pagination, unread counts **equal stored state**; read/unread persisted; mark-all; **ownership** (other roles 403, no recipient change, anonymous 401); read conflict retried then 409; bulk mark-all with a per-document conflict |
| Dashboards and courses | `test_dashboard.py` (8) | Student, counsellor and admin sections from stored records; empty states; counsellor scope and filters; admin aggregates equal stored records, filters, no student emails in reports; course edit, 409, **validation** (9 invalid payloads), RBAC, deactivation hides the course and blocks applying, create course |
| Data layer | `test_repository.py` (7) | View-routed `find` equals Mango for 7 selector shapes (sort, skip, limit, fields, empty `$in`); `_id` lookups equal Mango; fast counts equal Mango; view-backed admin dashboard, filtered dashboards and summary endpoints equal **direct counts over the seeded dataset**; the full reminder sweep |
| Seeding | `test_seeding.py` (+2) | The seeder writes only tagged documents; removal also takes records the app created for seed people |
| Frontend helpers | `frontend/tests/sprint3.test.js` (9) | Score and eligibility wording, factor points, missing-data grouping, freshness text, plan link; relative times, badge cap, **only same-site notification links are followed** (`//host`, `https:`, `javascript:` rejected) |
| Browser | headless Chrome over the DevTools protocol | Every page of every role at 1366 and 390 px: no JavaScript errors, no horizontal overflow, no error banner. Refresh recommendations; open the explanation (5 factor rows); bell panel, notification opens its link, mark all read; review drawer focus and Escape; admin course editor; **loading** indicator; **empty** states; **503** shows a friendly message and Try again recovers; **network failure** shows a toast; **expired token** redirects to sign in |

Security tests (RBAC, ownership, mass assignment, anonymous access) are part of the files above. Passing them shows that the tested rules hold. It does not prove the application is free of security defects.

## 5. Performance

### 5.1 Method
- **Data:** `bench_seed` generated three databases with the real 1,258-course catalogue, using seeded random proportions: per student about 2 applications (with history), 7 documents, 3 sessions and 6 notifications, and one counsellor per 25 students.

| Students | Documents in the database |
|---|---|
| 100 | 4,156 |
| 1,000 | 30,019 |
| 10,000 | 278,917 |

- **Load:** `bench_run` signs in as 8 students, 8 counsellors (4 at 100 students) and 1 admin, then warms each scenario with one request per account (`first` below). It then sends 100 requests per scenario at concurrency 1 and again at concurrency 8, round-robin over the accounts. Latency is measured at the HTTP client over loopback. It includes the server and CouchDB, not browser rendering.
- **Configuration:** one development-server process with `DEBUG=false`. A second run used **4 processes** behind client-side round-robin at concurrency 8 (200 requests per scenario).
- Raw results are saved as JSON in `output/benchmarks/` (git-ignored).

### 5.2 Before and after the data-layer work (1,000 students, concurrency 1)

| Endpoint | Before (Mango only) | After |
|---|---|---|
| Admin dashboard | > 5 s per request (a 50-request probe did not finish in 10 minutes) | p50 209 ms, p95 243 ms |
| Counsellor dashboard | not completed in the probe | p50 147 ms, p95 170 ms |
| 25 students' documents (single query) | 1,357 ms | 15 ms |
| Document status counts (single query) | 1,415 ms | 13 ms |

### 5.3 Results: p50 / p95 in ms (requests per second)

| Scenario | 100 students c=1 | 100 c=8 | 1,000 c=1 | 1,000 c=8 | 10,000 c=1 | 10,000 c=8 | 10,000 c=8, 4 processes |
|---|---|---|---|---|---|---|---|
| Dashboard: admin | 125 / 152 (7.7) | 226 / 285 (34) | 209 / 243 (4.5) | 463 / 499 (17) | 294 / 318 (3.3) | 692 / **798** (11) | 679 / **725** (12) |
| Dashboard: counsellor | 135 / 170 (6.9) | 263 / 330 (29) | 147 / 170 (6.7) | 292 / **947** (21) | 164 / 187 (5.8) | 328 / 385 (24) | 304 / **735** (23) |
| Dashboard: student | 53 / 71 (18) | 100 / 117 (79) | 68 / 89 (14) | 124 / 142 (63) | 75 / 99 (13) | 128 / 171 (59) | 95 / 113 (83) |
| Students list: counsellor | 21 / 43 (40) | 42 / 54 (183) | 21 / 45 (37) | 42 / 53 (184) | 26 / 46 (33) | 43 / 56 (180) | 31 / 38 (249) |
| Applications list: admin | 26 / 49 (31) | 53 / 67 (146) | 28 / 49 (30) | 56 / 75 (134) | 32 / 71 (22) | 65 / 80 (119) | 54 / 64 (143) |
| Applications list: counsellor | 51 / 74 (18) | 98 / 115 (81) | 54 / 78 (18) | 107 / 124 (74) | 55 / 78 (17) | 116 / 154 (66) | 102 / 115 (77) |
| Applications summary: admin | 26 / 49 (32) | 52 / 63 (148) | 29 / 50 (29) | 53 / 73 (143) | 32 / 52 (28) | 56 / 75 (136) | 47 / 54 (166) |
| Documents summary: admin | 10 / 32 (58) | 23 / 59 (296) | 15 / 36 (47) | 22 / 38 (330) | 16 / 37 (46) | 25 / 44 (269) | 26 / 30 (297) |
| Document review queue: counsellor | 86 / 116 (10) | 188 / 228 (42) | 95 / 120 (9.4) | 192 / 241 (41) | 113 / 138 (8.7) | 232 / 325 (33) | 220 / 270 (35) |
| Notifications list: student | 18 / 32 (48) | 33 / 48 (229) | 19 / 44 (42) | 34 / 43 (227) | 21 / 78 (33) | 37 / 66 (201) | 25 / 36 (306) |
| Unread count: student | 11 / 32 (56) | 21 / 30 (355) | 11 / 33 (60) | 21 / 31 (358) | 11 / 32 (65) | 22 / 28 (340) | 13 / 17 (594) |
| Recommendations list: student | 13 / 35 (51) | 28 / 38 (268) | 31 / 52 (29) | 66 / 100 (115) | 31 / 52 (28) | 68 / 80 (117) | 43 / 60 (179) |
| Recommendations generate (~280 of 1,258 courses evaluated) | 245 / 288 (4.0) | 879 / 932 (9.0) | 255 / 316 (3.8) | 912 / 970 (8.6) | 262 / 301 (3.7) | 927 / 970 (8.6) | 574 / 1,246 (13) |

**Errors:** 0 HTTP 5xx and 0 failed requests out of 10,400 measured requests (error rate 0%). Every request returned 2xx.

**First request** after start (index warm-up and the throttled reminder sweep) was 8–539 ms. The largest was the counsellor dashboard at 100 students (539 ms), whose first call runs the counsellor's reminder sweep.

**Memory:** the server interpreter used 53 MB at start and 70–72 MB after each run, with no growth between 100 and 10,000 students. CouchDB's working set was 151–157 MB after the runs; its 737 MB peak occurred during view builds before the runs.

### 5.4 Against the targets

| Target | Result | Status |
|---|---|---|
| Dashboard API p95 ≤ 500 ms | Met at concurrency 1 for every role at every size (max 318 ms). At concurrency 8 met at 100 and 1,000 students for admin (499 ms), and at every size for students. **Missed** for admin at 10,000 (798 ms; 725 ms with 4 processes). The counsellor dashboard had one 947 ms p95 at 1,000 students, c=8, against 385 ms at 10,000 | **Partial** |
| Paginated list p95 ≤ 500 ms | Max 325 ms (review queue, 10,000 students, c=8) | Met |
| Notification list p95 ≤ 500 ms | Max 78 ms | Met |
| Recommendation generation p95 ≤ 2 s (~280 courses evaluated per student, 1,258 in the catalogue) | Max 1,246 ms (c=8, 4 processes); 970 ms at c=8, 1 process; ≤ 316 ms at c=1 | Met |
| HTTP 5xx < 1% | 0% | Met |
| SRS 5.1: dashboard ~3 s, API ~2 s | Max dashboard 947 ms; max API 1,246 ms | Met |

**Bottleneck analysis for the missed target.** At 10,000 students one admin dashboard costs about 300 ms of CouchDB view work (profiled: about 30 view and Mango calls). Spreading eight concurrent admins over four server processes barely changed throughput (11.2 → 11.7 requests/s) or p95 (798 → 725 ms). So the limit is CouchDB's view work per request on a single local node, not Python. Two optimisation rounds were made and measured:
1. View routing, reduce views and composite indexes took it from more than 5 s to 713 ms at c=1.
2. `_sum` views with fewer groups and compact counsellor rows took it from 713 to 318 ms at c=1, and from 1,833 to 798 ms at c=8.

The next step would be a short-lived cache of the agency-wide aggregates (for example 30 s), or a multi-node CouchDB. It was not added, because every dashboard figure is currently read live and an agency rarely has eight administrators loading the dashboard at the same moment. The target is reported as missed for that workload.

## 6. How to reproduce

The Benchmarks section of the README has the exact commands: `bench_seed` into an `aec_bench*` database, `check_indexes`, `runserver`, then `bench_run --concurrency 1 8` (and several `--base-url`s for the multi-process run). The benchmark databases were deleted after the runs; regenerating the 10,000-student dataset takes about 3 minutes plus the first view build.
