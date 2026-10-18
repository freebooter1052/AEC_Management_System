"""
Generate a synthetic, proportional benchmark dataset (docs/SPRINT3_TEST_REPORT.md, "Benchmarks").

Only ever writes to a database whose name starts with `aec_bench` - never counselling_db:

    $env:COUCHDB_NAME = "aec_bench_1k"
    python manage.py bench_seed --students 1000 --copy-catalogue-from counselling_db

Per student, on average: 2 applications (with their status history), 5 general + 2 application documents,
3 counselling sessions (most with a follow-up) and 6 notifications; one counsellor per 25 students.
Every document is tagged "source": "bench". Accounts share one password (BENCH_PASSWORD), hashed once.
"""

import random
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError

from apps.applications.services import TRANSITIONS
from apps.core import repository
from apps.core.couchdb_client import get_couch_server
from apps.core.db import get_db
from apps.counsellors import services as counsellor_services
from apps.documents.services import CORE_DOCUMENTS
from apps.students import services as student_services

BENCH_PASSWORD = "Bench@2026"
CHUNK = 1000
PATH = ["Planned", "Shortlisted", "Documents Pending", "Submitted", "Under Review"]
FINAL_WEIGHTS = {"Planned": 15, "Shortlisted": 15, "Documents Pending": 25, "Submitted": 12, "Under Review": 12,
                 "Offer Received": 8, "Rejected": 6, "Withdrawn": 4, "Completed": 3}
DOC_STATUS_WEIGHTS = {"Required": 25, "Uploaded": 15, "Under Review": 10, "Verified": 40, "Rejected": 6, "Expired": 4}
CATEGORIES = ("status_change", "missing_document", "deadline", "follow_up", "assignment")


class Command(BaseCommand):
    help = "Write a synthetic benchmark dataset into an aec_bench* database (refuses any other)."

    def add_arguments(self, parser):
        parser.add_argument("--students", type=int, required=True)
        parser.add_argument("--copy-catalogue-from", default="", help="Copy universities/courses from this DB (read-only).")
        parser.add_argument("--seed", type=int, default=2026)

    def handle(self, *args, **opts):
        name = settings.COUCHDB_NAME
        if not name.startswith("aec_bench"):
            raise CommandError(f"Refusing to write benchmark data into '{name}': set COUCHDB_NAME=aec_bench...")
        db = get_db()
        if opts["copy_catalogue_from"]:
            self.copy_catalogue(db, opts["copy_catalogue_from"])
        if repository.count({"type": "student"}):
            raise CommandError(f"'{name}' already has students; drop the database to regenerate.")
        self.rng = random.Random(opts["seed"])
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.buffer, self.written = [], 0
        self.run(opts["students"])
        self.flush()
        self.stdout.write(self.style.SUCCESS(f"{name}: wrote {self.written} documents for {opts['students']} students."))

    # -- helpers -----------------------------------------------------------
    def copy_catalogue(self, db, source_name):
        source = get_couch_server()[source_name]
        docs = []
        for t in ("university", "course"):
            for d in source.find({"selector": {"type": t}, "limit": 100000}):
                d = dict(d)
                d.pop("_rev", None)
                if db.get(d["_id"]) is None:
                    docs.append(d)
        for i in range(0, len(docs), CHUNK):
            db.update(docs[i:i + CHUNK])
        self.stdout.write(f"Copied {len(docs)} catalogue documents from {source_name}.")

    def at(self, days_ago: float) -> str:
        return (self.now - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def day(self, offset: int) -> str:
        return (self.now.date() + timedelta(days=offset)).isoformat()

    def pick(self, weights: dict) -> str:
        return self.rng.choices(list(weights), weights=list(weights.values()))[0]

    def add(self, doc: dict) -> dict:
        doc["source"] = "bench"
        self.buffer.append(doc)
        if len(self.buffer) >= CHUNK:
            self.flush()
        return doc

    def flush(self):
        if self.buffer:
            failed = [r for r in get_db().update(self.buffer) if not r[0]]
            if failed:
                raise CommandError(f"{len(failed)} documents failed to write, e.g. {failed[0]}")
            self.written += len(self.buffer)
            self.buffer = []

    # -- dataset -----------------------------------------------------------
    def run(self, n_students: int):
        unis = {u["_id"]: u for u in repository.find({"type": "university"}, fields=["_id", "name", "country", "rank"])}
        courses = repository.find({"type": "course"}, fields=["_id", "university_id", "title", "cluster"])
        if not unis or not courses:
            raise CommandError("No catalogue: pass --copy-catalogue-from counselling_db.")
        countries = sorted({u["country"] for u in unis.values()})
        clusters = sorted({c["cluster"] for c in courses if c.get("cluster")})
        by_country: dict[str, list[dict]] = {}
        for c in courses:
            by_country.setdefault(unis[c["university_id"]]["country"], []).append(c)

        intakes = []
        for season, year, deadline, start in (("Fall", 2027, 91, 325), ("Spring", 2028, 349, 470), ("Fall", 2028, 456, 690)):
            intakes.append(self.add({"_id": f"intake_{season.lower()}_{year}", "type": "intake", "name": f"{season} {year}",
                                     "season": season, "year": year, "application_deadline": self.day(deadline),
                                     "decision_by": self.day(deadline + 90), "start_date": self.day(start), "created_at": self.at(300)}))
        password_hash = make_password(BENCH_PASSWORD)
        self.add({"_id": repository.new_id("user"), "type": "user", "email": "admin@bench.example.org",
                  "password_hash": password_hash, "role": "admin", "full_name": "Bench Admin", "profile_id": None,
                  "is_active": True, "token_version": 0, "created_at": self.at(400), "updated_at": self.at(400)})

        counsellors = []
        for i in range(max(1, n_students // 25)):
            uid, cid = repository.new_id("user"), repository.new_id("counsellor")
            email = f"counsellor{i}@bench.example.org"
            self.add({"_id": uid, "type": "user", "email": email, "password_hash": password_hash, "role": "counsellor",
                      "full_name": f"Counsellor {i}", "profile_id": cid, "is_active": True, "token_version": 0,
                      "created_at": self.at(400), "updated_at": self.at(400)})
            doc = counsellor_services.build_counsellor(user_id=uid, name=f"Counsellor {i}", email=email, phone="",
                                                       specialization="", region="", max_students=30)
            doc.update(_id=cid, created_at=self.at(400), assigned_student_ids=[])
            counsellors.append((self.add(doc), uid))

        for i in range(n_students):
            uid = repository.new_id("user")
            email = f"student{i}@bench.example.org"
            student = student_services.build_student(user_id=uid, email=email, first_name="Student", last_name=str(i),
                                                     dial_code="+91", phone="9800000000", citizenship="India",
                                                     degree_level="Masters")
            scale = self.rng.choice([4, 10])
            student_services.apply_update(student, {
                "personal": {"date_of_birth": "2001-01-01", "address": {"city": "Pune"}},
                "academic": {"degree": "B.E.", "institution": "Bench Institute", "graduation_year": 2024,
                             "cgpa": round(self.rng.uniform(0.6, 0.98) * scale, 2), "gpa_scale": scale,
                             "english_test": {"test_type": "IELTS", "overall": self.rng.choice([6, 6.5, 7, 7.5, 8])}},
                "preferences": {"countries": self.rng.sample(countries, self.rng.randint(1, 3)),
                                "course_areas": self.rng.sample(clusters, self.rng.randint(1, 2)),
                                "intake": self.rng.choice(intakes)["name"],
                                "budget": {"min": 0, "max": self.rng.choice([15000, 25000, 40000]), "currency": "EUR"}},
            })
            coun, coun_uid = counsellors[i % len(counsellors)] if self.rng.random() < 0.95 else (None, None)
            student["counsellor_id"] = coun["_id"] if coun else None
            student_services.refresh_derived(student)
            student["created_at"] = self.at(self.rng.uniform(1, 365))
            self.add({"_id": uid, "type": "user", "email": email, "password_hash": password_hash, "role": "student",
                      "full_name": f"Student {i}", "profile_id": student["_id"], "is_active": True, "token_version": 0,
                      "created_at": student["created_at"], "updated_at": student["created_at"]})
            apps = self.applications(student, coun, by_country, unis, intakes)
            student["application_ids"] = [a["_id"] for a in apps]
            self.add(student)
            self.documents(student, apps)
            self.sessions(student, coun)
            self.notifications(uid, coun_uid, apps)

    def applications(self, student, coun, by_country, unis, intakes):
        apps = []
        pool = [c for country in student["preferences"]["countries"] for c in by_country.get(country, [])]
        for _ in range(self.rng.choice([0, 1, 2, 2, 3, 4]) if pool else 0):
            course = self.rng.choice(pool)
            uni = unis[course["university_id"]]
            intake = self.rng.choice(intakes)
            final = self.pick(FINAL_WEIGHTS)
            path = PATH[:PATH.index(final) + 1] if final in PATH else (
                PATH[:3] + ["Withdrawn"] if final == "Withdrawn" else PATH + (["Offer Received", "Completed"] if final == "Completed" else [final]))
            assert all(b in TRANSITIONS[a] for a, b in zip(path, path[1:])), path
            app = {"_id": repository.new_id("application"), "type": "application", "student_id": student["_id"],
                   "counsellor_id": coun["_id"] if coun else None, "university_id": uni["_id"], "course_id": course["_id"],
                   "intake_id": intake["_id"], "status": final, "deadline": intake["application_deadline"],
                   "decision_expected": intake["decision_by"], "tier": None, "notes": "", "history_ids": [],
                   "snapshot": {"university_name": uni["name"], "country": uni["country"], "world_rank": uni.get("rank"),
                                "course_title": course["title"], "cluster": course.get("cluster", ""), "intake_name": intake["name"]},
                   "submitted_at": None, "created_at": self.at(self.rng.uniform(10, 200)), "updated_at": self.at(self.rng.uniform(0, 9))}
            old = None
            for status in path:
                h = self.add({"_id": repository.new_id("application_history"), "type": "application_history",
                              "application_id": app["_id"], "old_status": old, "new_status": status, "changed_by": None,
                              "changed_by_role": "counsellor", "timestamp": app["created_at"], "remarks": ""})
                app["history_ids"].append(h["_id"])
                old = status
            apps.append(self.add(app))
        return apps

    def documents(self, student, apps):
        specs = [(t, None) for t in CORE_DOCUMENTS] + [(t, a) for a in apps if a["status"] not in ("Planned", "Shortlisted")
                                                       for t in ("SOP", "LOR")]
        for doc_type, app in specs:
            status = self.pick(DOC_STATUS_WEIGHTS)
            uploaded = status != "Required"
            self.add({"_id": repository.new_id("document"), "type": "document", "student_id": student["_id"],
                      "application_id": app["_id"] if app else None, "counsellor_id": student["counsellor_id"],
                      "document_type": doc_type, "title": "", "status": status,
                      "filename": f"{doc_type.lower().replace('/', '_')}.pdf" if uploaded else None,
                      "uploaded_at": self.at(self.rng.uniform(1, 60)) if uploaded else None, "storage_ref": None,
                      "verified_by": None, "verified_at": None, "remarks": "", "history": [],
                      "created_at": self.at(self.rng.uniform(60, 200)), "updated_at": self.at(self.rng.uniform(0, 59))})

    def sessions(self, student, coun):
        if coun is None:
            return
        for _ in range(self.rng.choice([1, 2, 3, 4, 5])):
            days = self.rng.uniform(-20, 120)  # some upcoming
            done = days > 0
            follow = None
            if done and self.rng.random() < 0.7:
                follow = {"action": "Upload documents", "due_date": (self.now - timedelta(days=days - 7)).date().isoformat(),
                          "status": self.rng.choice(["Pending", "Done", "Done"]), "completed_at": None}
            self.add({"_id": repository.new_id("counselling_session"), "type": "counselling_session",
                      "student_id": student["_id"], "counsellor_id": coun["_id"],
                      "scheduled_at": (self.now - timedelta(days=days)).strftime("%Y-%m-%dT%H:00:00Z"),
                      "duration_minutes": 45, "mode": "Video call", "topic": "Counselling",
                      "status": "Completed" if done else "Scheduled", "summary": "Notes" if done else "",
                      "recommendations": [], "action_items": [], "follow_up": follow,
                      "created_at": self.at(max(0, days) + 3), "updated_at": self.at(max(0, days))})

    def notifications(self, uid, coun_uid, apps):
        for k in range(self.rng.randint(2, 10)):
            recipient, role = (coun_uid, "counsellor") if coun_uid and k % 4 == 3 else (uid, "student")
            self.add({"_id": repository.new_id("notification"), "type": "notification", "recipient_user_id": recipient,
                      "recipient_role": role, "category": self.rng.choice(CATEGORIES), "title": "Bench notification",
                      "message": "Synthetic benchmark notification.", "related_id": apps[0]["_id"] if apps else None,
                      "related_type": "application" if apps else None, "link": None, "event_key": None,
                      "is_read": self.rng.random() < 0.5, "read_at": None, "created_at": self.at(self.rng.uniform(0, 90))})
