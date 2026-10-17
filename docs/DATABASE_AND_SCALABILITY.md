# Database and scalability

How the system stores, queries and keeps CouchDB data consistent, and what was measured to justify each choice. Document shapes are in [`DATA_MODEL.md`](DATA_MODEL.md); benchmark results are in [`SPRINT3_TEST_REPORT.md`](SPRINT3_TEST_REPORT.md#5-performance).

## 1. Schemas and references

- **One CouchDB database** (`counselling_db`). Every document has a `type`, and IDs are `<type>_<12 hex>`. There is no other data store.
- **References are document IDs** (SRS 6.3): `application.student_id`, `document.application_id`, `notification.recipient_user_id`, `recommendation.course_id`, and so on. Small `snapshot` objects copy display names into applications and recommendations so lists need no joins. They are never used for access decisions.
- **Source of truth per entity:**

| Fact | Source of truth | Copies (display only, or kept in sync) |
|---|---|---|
| A student's counsellor | `student.counsellor_id` | `counsellor.assigned_student_ids` (kept in sync); `counsellor_id` on applications and documents (stale after a reassignment, never used for access or counts) |
| An application's status | `application.status` | `application_history` (append-only trail) |
| Course and university names on an application | the `course` / `university` docs | `application.snapshot` (taken when the application is created) |
| A recommendation's scores | recomputed from the student, course, university and intake docs on refresh | the stored scores, marked stale when the inputs change |
| Whether a notification was read | `notification.is_read` | none |

## 2. Query patterns and indexes

Mango (`_find`) is used with an index for every list. Two limits of Mango shaped this sprint, measured on a 1,000-student database (27,775 documents) with CouchDB 3.5 on the development machine:

| Query | Mango | Alternative | Result |
|---|---|---|---|
| Document counts by status | 1,415 ms (loads 7,768 docs) | reduce view `by_type_status` | 13 ms |
| 25 students' documents, `student_id: {$in: […]}` | 1,357 ms (Mango cannot use an index for `$in`, so it reads every document of the type) | multi-key lookup in view `by_student` | 15 ms |
| Same, with the documents themselves | — | same lookup with `include_docs` | 26 ms |
| 7,768 document rows | 1,415 ms | view rows, no documents | 147 ms |

What changed as a result:

1. **`repository.find` answers two selector shapes itself**, transparently for every caller:
   - `student_id: {"$in": [...]}` (a counsellor's caseload, one student's records) uses one `by_student` multi-key lookup. The rest of the selector, the sort, the paging and the field projection are then applied in memory by `apps/core/mango.py`, which is the same code the test suite's in-memory CouchDB uses. If only `_id/type/student_id/status` are needed, the documents are not loaded at all.
   - `_id: {"$in": [...]}` (batched name lookups) uses a primary-key lookup in `_all_docs`.
   Both are bounded by `SCOPED_MAX` (1,000 keys). Larger sets fall back to Mango.
2. **`repository.count`** answers a whole type, `created_at > null`, or a set of statuses from the `by_type` and `by_type_status` reduce views. Before, a paginated list over 20,000 applications loaded 20,000 IDs just to count them. Other selectors still count through Mango.
3. **Agency-wide dashboard figures** (totals, pipelines, deadlines, reports, follow-ups) come from reduce views. The admin dashboard no longer loads every application and document.
4. **Composite indexes** put the equality field before the sort field (`[type, counsellor_id, created_at]`, `[type, counsellor_id|student_id, scheduled_at]`). One counsellor's roster or sessions in date order is then read directly, instead of reading everyone's in date order and filtering.

The views (`_design/aec_stats`, 11 views) and indexes (`_design/aec_indexes`, 22 indexes) are created by `manage.py init_couchdb`. The views are listed in [`DATA_MODEL.md`](DATA_MODEL.md#mapreduce-views-_designaec_stats).

**Verification.** `manage.py check_indexes` asks CouchDB (`_explain`) which index each of 17 query patterns uses. It fails if any falls back to a full scan. It then compares 37 view answers (counts, summed arrays and row counts) with direct Mango counts. Results on the scratch database and the 100, 1,000 and 10,000-student benchmark databases:
- **Indexes:** all 17 patterns use the listed index. The three `student_id: {$in}` patterns are listed as their Mango fallback (`idx_type`), because the repository answers them from the `by_student` view.
- **Views:** all 37 view answers match Mango.

**View maintenance.** CouchDB updates views incrementally when they are read. Changing a view definition makes CouchDB rebuild it. On the 10,000-student database (278,917 documents) the first build outlasted CouchDB's request timeout, so the first query returned `500 timeout` while the build continued in the background. After `init_couchdb` on a large database, run `check_indexes` (retry it if it times out) before serving traffic. `init_couchdb` rewrites the design document only when a view changed.

## 3. Pagination

Every list endpoint returns `{count, page, page_size, total_pages, results}` with `page_size` capped at 100 (`settings.MAX_PAGE_SIZE`). Lists answered from a view are paged in memory after the bounded lookup. The full-catalogue read in the recommendation engine (about 1,258 courses) and the per-student recommendation list (at most 500) are bounded by design and documented in the code. The catalogue is cached per process (§8). The notification "mark all read" works in batches of 200, up to 25 batches per call.

## 4. Revision conflicts

CouchDB rejects a write with a stale `_rev` (HTTP 409). The policy depends on whether retrying is safe:

| Write | On conflict |
|---|---|
| A user edit with `rev` (profile, application, session, recommendation review, course) | **No retry.** 409 is returned, nothing is changed, and the UI asks the user to reload |
| Application status change | The application is saved first. A stale `rev` stops everything before the history entry or any notification is written |
| Marking a notification read/unread | **Bounded retry (3):** re-read, re-apply the flag, save. The flag is idempotent, and other fields come from the fresh read, so a concurrent change survives. After 3 failures, 409 |
| "Mark all read" (`_bulk_docs`) | Per-document results. Failed documents are retried one by one as above, and the response reports `failed`/`remaining` |
| Recommendation refresh (`_bulk_docs`) | A failed document (e.g. a counsellor accepted it meanwhile) is re-read and only the engine fields are re-applied, so the counsellor's `status`/`remarks` win. A document deleted meanwhile is not re-created. An undecided suggestion that drops out of the results is deleted, unless it changed meanwhile (then it is kept) |
| Recommendation run summary | Re-read and overwrite (last writer wins: it is a summary of the latest run) |
| `student.application_ids` link | Re-read and re-apply, up to 3 times (Sprint 2) |

The "stale `rev` returns 409" and "concurrent edit during refresh is preserved" behaviours are covered by tests (`test_recommendations`, `test_notifications`, `test_applications`).

## 5. Idempotence and duplicates

CouchDB has no unique constraints. Deterministic IDs create them where duplicates would matter:
- **Recommendations:** `recommendation_<sha1(student_id|course_id)>`. Two concurrent refreshes collide on create (409), and the loser updates the existing document.
- **Recommendation runs:** one per student, `recommendation_run_<sha1(student_id)>`.
- **Notifications:** `notification_<sha1(event_key|recipient)>`. A retried request, a second reminder sweep, or two workers creating the same event all collide, and `notify()` treats the collision as "already sent". Event keys include what makes an event distinct (the history entry for a status change; the application, deadline and window for a reminder), so a moved deadline produces new reminders.

## 6. Multi-document consistency

There are no transactions, so multi-document workflows write in a fixed order and accept defined partial states:

| Workflow | Order | If a later step fails |
|---|---|---|
| Application status change | application → history → SOP/LOR checklist → notifications | The status and history are saved. A failed notification is logged (`aec.notifications`) and not retried. The status change still succeeds and the history shows it |
| Counsellor assignment | student → old counsellor → new counsellor → notifications | Unchanged from Sprint 1; the notification is best-effort as above |
| Recommendation refresh | results (`_bulk_docs`) → deletions → run summary | A failure before the run summary leaves the previous summary, so the page reports the results as stale, and refreshing again repairs it |
| Reminders | each notification independently | Re-running the sweep creates whatever is missing and nothing twice |
| Student deletion | workflow records → notifications → profile → account | Unchanged from Sprint 2, plus notifications and recommendation runs |

## 7. Recommendation freshness

A run stores a fingerprint of everything that can change its result: the scoring method and weights, the student's grades, English test and preferences, and every intake's dates and open/closed state. A later read compares that fingerprint with the current data, and checks (one indexed query) whether a course was edited at or after the run. Either difference marks the recommendations stale, with the reason, and the UI offers Refresh. Recommendations are never recomputed silently on read. Course edits are compared at one-second resolution, so a false "stale" only costs a refresh, while a missed edit would be wrong.

## 8. Caching

One cache, with a defined invalidation rule: the recommendation engine keeps the course and university catalogue (1,358 documents, ~290 ms to load from Mango at any database size) in process memory. Before each use it reads a version key - course and university counts from the `by_type` reduce view and the newest course `updated_at` (one indexed query, ~15 ms together) - and reloads when the key changes or after 60 seconds (which covers a second edit within the same one-second timestamp). Intakes are never cached. Each server process has its own copy; nothing else is cached, so every dashboard figure is read from CouchDB on each request.

## 9. Known limits

- **Text search** (`?q=` on students, applications and courses) uses Mango `$regex`, which reads every document of the type. It is fine at the catalogue's size and slow on large student/application sets. A search index (CouchDB Nouveau or Clouseau) would be the next step.
- **Admin lists filtered by status** use the `[type, created_at]` index and skip non-matching documents. That is quick when the status is common and slower for a rare one on a large database.
- **The full reminder sweep** loads every document that needs student action (by key, not by scan). That is acceptable for a scheduled job, and the on-access sweep touches only one caseload.
- **Benchmarks** ran on Django's development server (a single process) on one Windows machine; see the test report.
