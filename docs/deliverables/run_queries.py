"""
Runs the report's 20 CouchDB queries (Mango _find + map/reduce views) and prints each one with its result,
ready to screenshot. READ-ONLY: it never writes to the database.

    cd backend
    myenv\\Scripts\\python.exe ..\\docs\\deliverables\\run_queries.py            # all queries
    myenv\\Scripts\\python.exe ..\\docs\\deliverables\\run_queries.py 7          # only Q7
    myenv\\Scripts\\python.exe ..\\docs\\deliverables\\run_queries.py --explain  # Mango _explain (index used) for Q1-Q13

Connection settings come from the repo-root .env (COUCHDB_URL/USER/PASSWORD/NAME).
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
TODAY = date.today().isoformat()
SOON = (date.today() + timedelta(days=60)).isoformat()


def load_env():
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def sub(obj):
    """Replace the {TODAY}/{SOON} placeholders so the printed query shows real dates."""
    return json.loads(json.dumps(obj).replace("{TODAY}", TODAY).replace("{SOON}", SOON))


# kind "find": POST /_find with `body`.  kind "view": GET /_design/aec_stats/_view/<view> with `params`.
QUERIES = [
    {"id": 1, "title": "Top 10 universities by world rank", "kind": "find",
     "purpose": "Sorted query served by the composite index idx_type_rank [type, rank].",
     "body": {"selector": {"type": "university", "rank": {"$gt": 0}},
              "sort": [{"type": "asc"}, {"rank": "asc"}],
              "fields": ["name", "country", "rank"], "limit": 10}},
    {"id": 2, "title": "Universities in the UK or Germany ranked within the top 150", "kind": "find",
     "purpose": "Combines $and, $or and $lte on two fields.",
     "body": {"selector": {"$and": [{"type": "university"},
                                    {"$or": [{"country": "UK"}, {"country": "Germany"}]},
                                    {"rank": {"$lte": 150}}]},
              "fields": ["name", "country", "rank"], "limit": 15}},
    {"id": 3, "title": "Courses whose title matches a pattern (Data or Machine Learning)", "kind": "find",
     "purpose": "Regular-expression search with $regex over the 1,258-course catalogue.",
     "body": {"selector": {"type": "course", "title": {"$regex": "(?i)data|machine learning"}},
              "fields": ["title", "cluster", "university_id"], "limit": 10}},
    {"id": 4, "title": "Students with a CGPA of 3.0 or more who want to study in the UK", "kind": "find",
     "purpose": "Nested field (academic.cgpa) plus $elemMatch on the preferences.countries array.",
     "body": {"selector": {"type": "student", "academic.cgpa": {"$gte": 3.0},
                           "preferences.countries": {"$elemMatch": {"$eq": "UK"}}},
              "fields": ["personal.first_name", "personal.last_name", "academic.cgpa", "academic.gpa_scale",
                         "preferences.countries"], "limit": 10}},
    {"id": 5, "title": "Students not yet assigned to a counsellor", "kind": "find",
     "purpose": "Null match on counsellor_id; the same condition the admin 'unassigned' filter uses.",
     "body": {"selector": {"type": "student", "counsellor_id": {"$eq": None}},
              "fields": ["personal.first_name", "personal.last_name", "onboarding_status", "profile_completion.overall"],
              "limit": 10}},
    {"id": 6, "title": "Applications that reached an offer (Offer Received or Completed)", "kind": "find",
     "purpose": "$in over workflow statuses; uses the snapshot sub-document so no join is needed.",
     "body": {"selector": {"type": "application", "status": {"$in": ["Offer Received", "Completed"]}},
              "fields": ["status", "snapshot.university_name", "snapshot.country", "snapshot.course_title",
                         "snapshot.intake_name"], "limit": 10}},
    {"id": 7, "title": "Overdue applications still open (deadline passed, not submitted)", "kind": "find",
     "purpose": "Status $in plus a date comparison against today's date.",
     "body": {"selector": {"type": "application",
                           "status": {"$in": ["Planned", "Shortlisted", "Documents Pending"]},
                           "deadline": {"$lt": "{TODAY}"}},
              "fields": ["status", "deadline", "snapshot.university_name", "snapshot.country"], "limit": 10}},
    {"id": 8, "title": "Application deadlines in the next 60 days, earliest first", "kind": "find",
     "purpose": "Range query plus sort, served by index idx_type_deadline [type, deadline].",
     "body": {"selector": {"type": "application", "deadline": {"$gte": "{TODAY}", "$lte": "{SOON}"}},
              "sort": [{"type": "asc"}, {"deadline": "asc"}],
              "fields": ["deadline", "status", "snapshot.university_name", "snapshot.intake_name"], "limit": 10}},
    {"id": 9, "title": "Documents waiting for counsellor review", "kind": "find",
     "purpose": "The counsellor review queue: $in on document status, nested storage_ref.",
     "body": {"selector": {"type": "document", "status": {"$in": ["Uploaded", "Under Review"]}},
              "fields": ["document_type", "status", "filename", "uploaded_at"], "limit": 10}},
    {"id": 10, "title": "Upcoming video-call counselling sessions in time order", "kind": "find",
     "purpose": "Equality filters plus sort on scheduled_at, served by idx_type_scheduled.",
     "body": {"selector": {"type": "counselling_session", "status": "Scheduled", "mode": "Video call",
                           "scheduled_at": {"$gt": ""}},
              "sort": [{"type": "asc"}, {"scheduled_at": "asc"}],
              "fields": ["scheduled_at", "duration_minutes", "topic", "mode"], "limit": 10}},
    {"id": 11, "title": "Pending follow-ups due by today (nested sub-document)", "kind": "find",
     "purpose": "Filters on follow_up.status and follow_up.due_date inside the session document.",
     "body": {"selector": {"type": "counselling_session", "follow_up.status": "Pending",
                           "follow_up.due_date": {"$lte": "{SOON}"}},
              "fields": ["topic", "follow_up.action", "follow_up.due_date", "follow_up.status"], "limit": 10}},
    {"id": 12, "title": "Strongest eligible recommendations in the Target tier", "kind": "find",
     "purpose": "Combines eligibility, tier and a score threshold on the rule-based recommendation documents.",
     "body": {"selector": {"type": "recommendation", "tier": "Target", "ranking_score": {"$gte": 40}},
              "fields": ["tier", "match_score", "confidence", "ranking_score", "status", "snapshot.university_name",
                         "snapshot.course_title"], "limit": 10}},
    {"id": 13, "title": "Unread notifications by category", "kind": "find",
     "purpose": "Boolean filter plus $in over the five notification categories.",
     "body": {"selector": {"type": "notification", "is_read": False,
                           "category": {"$in": ["status_change", "deadline", "missing_document", "follow_up"]}},
              "fields": ["category", "title", "created_at"], "limit": 10}},
    {"id": 14, "title": "Number of applications in each status (reduce view, group_level=2)", "kind": "view",
     "purpose": "Aggregation: GROUP BY status using _count over view by_type_status.",
     "view": "by_type_status",
     "params": {"reduce": True, "group_level": 2, "startkey": ["application"], "endkey": ["application", {}]}},
    {"id": 15, "title": "Applications and offers per destination country (_sum reduce)", "kind": "view",
     "purpose": "Aggregation with a two-number value [applications, offers], summed per country.",
     "view": "application_dims",
     "params": {"reduce": True, "group_level": 2, "startkey": ["country"], "endkey": ["country", {}]}},
    {"id": 16, "title": "Applications and offers per intake", "kind": "view",
     "purpose": "Same view, different dimension: intake name.",
     "view": "application_dims",
     "params": {"reduce": True, "group_level": 2, "startkey": ["intake"], "endkey": ["intake", {}]}},
    {"id": 17, "title": "Students per counsellor (workload)", "kind": "view",
     "purpose": "GROUP BY counsellor_id; the null row is the unassigned students.",
     "view": "students_by_counsellor", "params": {"reduce": True, "group": True}},
    {"id": 18, "title": "Open applications and documents awaiting review per student", "kind": "view",
     "purpose": "Per-student workload as [open applications, documents to review].",
     "view": "student_workload", "params": {"reduce": True, "group": True, "limit": 10}},
    {"id": 19, "title": "Document status distribution", "kind": "view",
     "purpose": "GROUP BY document status across the agency in one view read.",
     "view": "by_type_status",
     "params": {"reduce": True, "group_level": 2, "startkey": ["document"], "endkey": ["document", {}]}},
    {"id": 20, "title": "Follow-ups per status (Pending / Done)", "kind": "view",
     "purpose": "Counts follow-ups by status using the compound key [status, due_date].",
     "view": "follow_ups_by_due", "params": {"reduce": True, "group_level": 1}},
]


def run(q, cfg, session, explain=False):
    base = f"{cfg['COUCHDB_URL'].rstrip('/')}/{cfg['COUCHDB_NAME']}"
    print("=" * 100)
    print(f"Q{q['id']}. {q['title']}")
    print(f"Purpose: {q['purpose']}")
    if q["kind"] == "find":
        body = sub(q["body"])
        url = base + ("/_explain" if explain else "/_find")
        print(f"POST /{cfg['COUCHDB_NAME']}/{'_explain' if explain else '_find'}")
        print(json.dumps(body, indent=2))
        r = session.post(url, json=body)
    else:
        params = {k: json.dumps(v) if isinstance(v, (list, dict, bool)) else v for k, v in q["params"].items()}
        print(f"GET /{cfg['COUCHDB_NAME']}/_design/aec_stats/_view/{q['view']}")
        print(json.dumps(q["params"]))
        r = session.get(f"{base}/_design/aec_stats/_view/{q['view']}", params=params)
    data = r.json()
    print("-" * 100)
    if explain:
        print("index used:", data.get("index", {}).get("name"), "| def:", json.dumps(data.get("index", {}).get("def")))
        print("warning:", data.get("warning", "none"))
    elif "docs" in data:
        print(f"Result: {len(data['docs'])} document(s) returned (limit {q['body'].get('limit')})")
        if data.get("warning"):
            print("warning:", data["warning"])
        print(json.dumps(data["docs"][:5], indent=2, ensure_ascii=False))
        if len(data["docs"]) > 5:
            print(f"... {len(data['docs']) - 5} more row(s) not shown")
    else:
        rows = data.get("rows", [])
        print(f"Result: {len(rows)} row(s)")
        for row in rows[:12]:
            print(f"  key={json.dumps(row['key'], ensure_ascii=False)}  value={json.dumps(row['value'])}")
    print()


def main():
    args = sys.argv[1:]
    explain = "--explain" in args
    wanted = {int(a) for a in args if a.isdigit()}
    cfg = load_env()
    cfg.setdefault("COUCHDB_NAME", "counselling_db")
    session = requests.Session()
    session.auth = (cfg["COUCHDB_USER"], cfg["COUCHDB_PASSWORD"])
    info = session.get(f"{cfg['COUCHDB_URL'].rstrip('/')}/{cfg['COUCHDB_NAME']}").json()
    print(f"Database: {info['db_name']}  documents: {info['doc_count']}  date: {TODAY}\n")
    for q in QUERIES:
        if wanted and q["id"] not in wanted:
            continue
        if explain and q["kind"] != "find":
            continue
        run(q, cfg, session, explain)


if __name__ == "__main__":
    main()
