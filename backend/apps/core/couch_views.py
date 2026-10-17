"""
Map/reduce views in `_design/aec_stats` (created by `manage.py init_couchdb`).

Why: Mango `_find` loads every candidate document, and cannot use an index for `$in`. Measured on a
1,000-student database (docs/SPRINT3_TEST_REPORT.md): counting documents by status took ~1.4 s with Mango
and 13 ms from a reduce view; fetching 25 students' documents took 1.36 s with `student_id: {$in: ...}`
and 15 ms as a multi-key view lookup. Views are updated incrementally by CouchDB on read.

Each view has its JavaScript map (run by CouchDB) and a Python twin with the same rules (run by the
in-memory database in the tests). `check_indexes` compares view and Mango answers on a live database.
"""

PRE_SUBMISSION = ["Planned", "Shortlisted", "Documents Pending"]
TERMINAL = ["Rejected", "Withdrawn", "Completed"]
AWAITING_REVIEW = ["Uploaded", "Under Review"]
OFFER = ["Offer Received", "Completed"]
DESIGN_DOC = "aec_stats"

VIEWS = {
    # [type, student_id] -> status. Multi-key lookups of a set of students' records; per-student counts.
    "by_student": {
        "map": "function (doc) { if (doc.type && doc.student_id) "
               "emit([doc.type, doc.student_id], doc.status === undefined ? null : doc.status); }",
        "reduce": "_count",
    },
    # [type, status] -> student_id. Status distributions (reduce) and who is waiting on what (rows).
    "by_type_status": {
        "map": "function (doc) { if (doc.type && typeof doc.status === 'string') "
               "emit([doc.type, doc.status], doc.student_id || null); }",
        "reduce": "_count",
    },
    # [type, has created_at] -> null. Totals per type; the flag mirrors Mango's `created_at: {$gt: null}`
    # (field present and not null), so list counts with that condition are exact too.
    "by_type": {
        "map": "function (doc) { if (doc.type) emit([doc.type, doc.created_at !== undefined && doc.created_at !== null], null); }",
        "reduce": "_count",
    },
    # counsellor_id (null = unassigned) -> null, for students. Workload counts and rosters.
    "students_by_counsellor": {
        "map": "function (doc) { if (doc.type === 'student') emit(doc.counsellor_id || null, null); }",
        "reduce": "_count",
    },
    # deadline -> student_id, for applications that can still be submitted. Overdue / due-soon counts.
    "open_deadlines": {
        "map": "function (doc) { if (doc.type === 'application' && typeof doc.deadline === 'string' && "
               f"{PRE_SUBMISSION!r}.indexOf(doc.status) >= 0) emit(doc.deadline, doc.student_id || null); }}".replace("'", '"'),
        "reduce": "_count",
    },
    # [dimension, value] -> [1, is offer] for applications, summed: unfiltered reports by country, university,
    # intake. (Status is in the value, not the key, so grouping yields one row per value: 9x fewer groups.)
    "application_dims": {
        "map": "function (doc) { if (doc.type !== 'application') return; var s = doc.snapshot || {}; "
               f"var v = [1, {OFFER!r}.indexOf(doc.status) >= 0 ? 1 : 0]; "
               "emit(['country', s.country || ''], v); emit(['university', s.university_name || ''], v); "
               "emit(['intake', s.intake_name || ''], v); }".replace("'", '"'),
        "reduce": "_sum",
    },
    # student_id -> [open application, document awaiting review], summed: a few counsellors' workload.
    "student_workload": {
        "map": "function (doc) { if (!doc.student_id) return; "
               f"if (doc.type === 'application' && {TERMINAL!r}.indexOf(doc.status) < 0) emit(doc.student_id, [1, 0]); "
               f"if (doc.type === 'document' && {AWAITING_REVIEW!r}.indexOf(doc.status) >= 0) emit(doc.student_id, [0, 1]); }}"
               .replace("'", '"'),
        "reduce": "_sum",
    },
    # counsellor id -> [name, active, max_students]: every counsellor without loading the documents.
    "counsellors": {
        "map": "function (doc) { if (doc.type === 'counsellor') "
               "emit(doc._id, [doc.name || '', doc.is_active !== false, doc.max_students || null]); }",
    },
    # [dimension, value] -> compact row, for applications. Reports filtered by country or intake.
    "applications_by_dim": {
        "map": "function (doc) { if (doc.type !== 'application') return; var s = doc.snapshot || {}; "
               "var v = [doc.status, doc.deadline || null, s.country || '', s.university_name || '', "
               "s.intake_name || '', doc.intake_id || '', doc.student_id || null]; "
               "emit(['country', s.country || ''], v); emit(['intake', doc.intake_id || ''], v); }",
    },
    # [follow-up status, due date] -> counsellor_id. Pending / overdue follow-ups across the agency.
    "follow_ups_by_due": {
        "map": "function (doc) { if (doc.type === 'counselling_session' && doc.follow_up && doc.follow_up.due_date) "
               "emit([doc.follow_up.status || '', doc.follow_up.due_date], doc.counsellor_id || null); }",
        "reduce": "_count",
    },
    # counsellor_id -> [status, scheduled_at, follow-up status, follow-up due] for sessions. Activity summaries.
    "sessions_by_counsellor": {
        "map": "function (doc) { if (doc.type === 'counselling_session' && doc.counsellor_id) { var f = doc.follow_up || {}; "
               "emit(doc.counsellor_id, [doc.status, doc.scheduled_at || null, f.status || null, f.due_date || null]); } }",
    },
}


def _app_row(d):
    s = d.get("snapshot") or {}
    return [d.get("status"), d.get("deadline") or None, s.get("country") or "", s.get("university_name") or "",
            s.get("intake_name") or "", d.get("intake_id") or "", d.get("student_id") or None]


def _session_row(d):
    f = d.get("follow_up") or {}
    return [d.get("status"), d.get("scheduled_at") or None, f.get("status") or None, f.get("due_date") or None]


# Python twins of the maps above: doc -> [(key, value), ...]
PY_MAPS = {
    "by_student": lambda d: [([d["type"], d["student_id"]], d.get("status"))] if d.get("type") and d.get("student_id") else [],
    "by_type_status": lambda d: [([d["type"], d["status"]], d.get("student_id") or None)]
    if d.get("type") and isinstance(d.get("status"), str) else [],
    "by_type": lambda d: [([d["type"], d.get("created_at") is not None], None)] if d.get("type") else [],
    "students_by_counsellor": lambda d: [(d.get("counsellor_id") or None, None)] if d.get("type") == "student" else [],
    "open_deadlines": lambda d: [(d["deadline"], d.get("student_id") or None)]
    if d.get("type") == "application" and isinstance(d.get("deadline"), str) and d.get("status") in PRE_SUBMISSION else [],
    "application_dims": lambda d: [
        ([dim, (d.get("snapshot") or {}).get(field) or ""], [1, 1 if d.get("status") in OFFER else 0])
        for dim, field in (("country", "country"), ("university", "university_name"), ("intake", "intake_name"))
    ] if d.get("type") == "application" else [],
    "student_workload": lambda d: (
        [(d["student_id"], [1, 0])] if d.get("type") == "application" and d.get("status") not in TERMINAL else
        [(d["student_id"], [0, 1])] if d.get("type") == "document" and d.get("status") in AWAITING_REVIEW else []
    ) if d.get("student_id") else [],
    "counsellors": lambda d: [(d["_id"], [d.get("name") or "", d.get("is_active") is not False, d.get("max_students") or None])]
    if d.get("type") == "counsellor" else [],
    "applications_by_dim": lambda d: [
        (["country", (d.get("snapshot") or {}).get("country") or ""], _app_row(d)),
        (["intake", d.get("intake_id") or ""], _app_row(d)),
    ] if d.get("type") == "application" else [],
    "follow_ups_by_due": lambda d: [([(d["follow_up"].get("status") or ""), d["follow_up"]["due_date"]], d.get("counsellor_id") or None)]
    if d.get("type") == "counselling_session" and isinstance(d.get("follow_up"), dict) and d["follow_up"].get("due_date") else [],
    "sessions_by_counsellor": lambda d: [(d["counsellor_id"], _session_row(d))]
    if d.get("type") == "counselling_session" and d.get("counsellor_id") else [],
}
REDUCED = {name: v["reduce"] for name, v in VIEWS.items() if v.get("reduce")}

assert set(PY_MAPS) == set(VIEWS)


def design_document() -> dict:
    return {"_id": f"_design/{DESIGN_DOC}", "language": "javascript", "views": VIEWS}
