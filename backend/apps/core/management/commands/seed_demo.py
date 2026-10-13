from django.core.management.base import BaseCommand

from apps.accounts import users
from apps.core import repository
from apps.core.roles import COUNSELLOR, STUDENT
from apps.counsellors import services as counsellor_services
from apps.students import services as student_services

DEMO_PASSWORD = "Demo@12345"

COUNSELLORS = [
    {"name": "Marcus Chen", "email": "marcus.chen@aec.demo", "phone": "+65 6712 8840",
     "specialization": "UK & Ireland postgraduate", "region": "SE Asia Hub", "max_students": 20},
    {"name": "Anika Sharma", "email": "anika.sharma@aec.demo", "phone": "+91 98765 43210",
     "specialization": "Germany & Netherlands STEM", "region": "South Asia Hub", "max_students": 15},
]

STUDENTS = [
    {"first_name": "Julianne", "last_name": "Sterling", "email": "julianne@aec.demo", "counsellor": 0,
     "personal": {"phone": {"dial_code": "+65", "number": "91234567"}, "date_of_birth": "2002-05-18",
                  "citizenship": "Singapore", "address": {"city": "Singapore", "country": "Singapore"}},
     "academic": {"degree": "B.Comp Computer Science", "institution": "National University of Singapore",
                  "cgpa": 3.84, "gpa_scale": 4, "graduation_year": 2024,
                  "english_test": {"test_type": "IELTS", "overall": 8.5}},
     "preferences": {"countries": ["UK", "Canada"], "course_areas": ["Human-Computer Interaction", "Data Science"],
                     "degree_level": "Masters", "intake": "Fall 2027",
                     "budget": {"min": 40000, "max": 60000, "currency": "USD"}}},
    {"first_name": "Rahul", "last_name": "Menon", "email": "rahul@aec.demo", "counsellor": 1,
     "personal": {"phone": {"dial_code": "+91", "number": "9847012345"}, "citizenship": "India"},
     "academic": {"degree": "B.Tech Mechanical", "institution": "NIT Calicut", "cgpa": 8.1, "gpa_scale": 10},
     "preferences": {"countries": ["Germany"], "course_areas": ["Mechatronics"], "degree_level": "Masters"}},
    {"first_name": "Sara", "last_name": "Okafor", "email": "sara@aec.demo", "counsellor": None,
     "personal": {"citizenship": "Nigeria"}, "academic": {}, "preferences": {"countries": ["Canada"]}},
]


class Command(BaseCommand):
    help = f"Create demo counsellors and students (password: {DEMO_PASSWORD}). Skips accounts that already exist."

    def handle(self, *args, **options):
        counsellor_ids = []
        for c in COUNSELLORS:
            existing = users.get_by_email(c["email"])
            if existing:
                counsellor_ids.append(existing["profile_id"])
                self.stdout.write(f"  exists  counsellor {c['email']}")
                continue
            user = users.build_user(email=c["email"], password=DEMO_PASSWORD, role=COUNSELLOR, full_name=c["name"])
            doc = counsellor_services.build_counsellor(user_id=user["_id"], **c)
            user["profile_id"] = doc["_id"]
            repository.save(doc)
            repository.save(user)
            counsellor_ids.append(doc["_id"])
            self.stdout.write(f"  created counsellor {c['email']}")

        for s in STUDENTS:
            if users.email_taken(s["email"]):
                self.stdout.write(f"  exists  student    {s['email']}")
                continue
            user = users.build_user(email=s["email"], password=DEMO_PASSWORD, role=STUDENT,
                                    full_name=f"{s['first_name']} {s['last_name']}")
            doc = student_services.build_student(user_id=user["_id"], email=user["email"],
                                                 first_name=s["first_name"], last_name=s["last_name"])
            student_services.apply_update(doc, {k: s[k] for k in ("personal", "academic", "preferences")})
            user["profile_id"] = doc["_id"]
            repository.save(doc)
            repository.save(user)
            if s["counsellor"] is not None:
                student_services.assign_counsellor(doc, counsellor_ids[s["counsellor"]], actor=None)
            self.stdout.write(f"  created student    {s['email']}")

        self.stdout.write(self.style.SUCCESS(f"Demo data ready. Password for all demo accounts: {DEMO_PASSWORD}"))
