"""
Realistic, fully linked sample dataset in the SRS document shapes (section 6).

Every document written here carries `"source": "seed"` so it is always separable
from data people enter through the app: `seed_dataset --remove` deletes exactly
these documents (plus audit entries about them) and nothing else. People are
created through the same services the API uses, so passwords are PBKDF2-hashed,
profile completion is computed and counsellor assignments stay in sync.
"""

import random
from datetime import datetime, timedelta, timezone

from apps.accounts import users
from apps.core import repository
from apps.core.roles import COUNSELLOR, STUDENT
from apps.counsellors import services as counsellor_services
from apps.students import services as student_services

from . import maintenance

SEED = "seed"
DEFAULT_PASSWORD = "Seed@2026"

# Catalogue country name (as in university.country) -> (ISO code, full name, currency, region)
COUNTRIES = {
    "US": ("US", "United States", "USD", "North America"),
    "UK": ("GB", "United Kingdom", "GBP", "Europe"),
    "Canada": ("CA", "Canada", "CAD", "North America"),
    "Australia": ("AU", "Australia", "AUD", "Oceania"),
    "Germany": ("DE", "Germany", "EUR", "Europe"),
    "France": ("FR", "France", "EUR", "Europe"),
    "Netherlands": ("NL", "Netherlands", "EUR", "Europe"),
    "Belgium": ("BE", "Belgium", "EUR", "Europe"),
    "Switzerland": ("CH", "Switzerland", "CHF", "Europe"),
    "Sweden": ("SE", "Sweden", "SEK", "Europe"),
    "Denmark": ("DK", "Denmark", "DKK", "Europe"),
    "Finland": ("FI", "Finland", "EUR", "Europe"),
    "Norway": ("NO", "Norway", "NOK", "Europe"),
    "China": ("CN", "China", "CNY", "Asia"),
    "Hong Kong": ("HK", "Hong Kong", "HKD", "Asia"),
    "Japan": ("JP", "Japan", "JPY", "Asia"),
    "South Korea": ("KR", "South Korea", "KRW", "Asia"),
    "Singapore": ("SG", "Singapore", "SGD", "Asia"),
    "Israel": ("IL", "Israel", "ILS", "Middle East"),
}

# name, season, year, application deadline, decision by, programme start
INTAKES = [
    ("Spring 2027", "Spring", 2027, "2026-09-30", "2026-11-30", "2027-01-18"),
    ("Fall 2027", "Fall", 2027, "2027-01-15", "2027-04-15", "2027-09-06"),
    ("Spring 2028", "Spring", 2028, "2027-09-30", "2027-11-30", "2028-01-17"),
    ("Fall 2028", "Fall", 2028, "2028-01-15", "2028-04-15", "2028-09-04"),
]

COUNSELLORS = [
    dict(name="Priya Raman", email="priya.raman@counsellors.example.org", phone="+91 98450 11223",
         specialization="UK & Ireland postgraduate admissions", region="South Asia Hub", max_students=12),
    dict(name="Daniel Brooks", email="daniel.brooks@counsellors.example.org", phone="+1 415 555 0142",
         specialization="USA STEM and research programmes", region="North America Desk", max_students=12),
    dict(name="Mei Lin Tan", email="meilin.tan@counsellors.example.org", phone="+65 6712 4410",
         specialization="Singapore, Hong Kong and East Asia", region="SE Asia Hub", max_students=10),
    dict(name="Lukas Weber", email="lukas.weber@counsellors.example.org", phone="+49 30 5557 2210",
         specialization="Germany, Switzerland and the Netherlands", region="Europe Desk", max_students=10),
    dict(name="Aisha Karim", email="aisha.karim@counsellors.example.org", phone="+971 4 555 0187",
         specialization="Australia and Canada", region="Middle East Hub", max_students=10),
]

ENG = "Engineering – "  # cluster prefix used by the course catalogue (en dash)


def _student(first, last, gender, dob, citizenship, dial, phone, city, degree, institution, cgpa, scale, grad,
             work, test, gre, countries, areas, level, intake, budget, scholarship, counsellor, stage, finals=None):
    return dict(first=first, last=last, gender=gender, dob=dob, citizenship=citizenship, dial=dial, phone=phone,
                city=city, degree=degree, institution=institution, cgpa=cgpa, scale=scale, grad=grad, work=work,
                test=test, gre=gre, countries=countries, areas=areas, level=level, intake=intake, budget=budget,
                scholarship=scholarship, counsellor=counsellor, stage=stage, finals=finals)


# stage: 0 registered, 1 profiling, 2 shortlisting, 3 applying, 4 submitted, 5 decisions
STUDENTS = [
    _student("Ananya", "Iyer", "Female", "2001-04-12", "India", "+91", "9845012345", "Bengaluru",
             "B.E. Computer Science", "RV College of Engineering", 8.7, 10, 2023, 2, ("IELTS", 7.5, 8, 7.5, 7, 7.5),
             "GRE 321", ["UK", "Canada"], ["CS & AI"], "Masters", "Spring 2027", (30000, 45000, "GBP"), False, 0, 5,
             ["Offer Received", "Rejected", "Under Review"]),
    _student("Chinedu", "Okeke", "Male", "2000-09-03", "Nigeria", "+234", "8031234567", "Lagos",
             "B.Sc. Electrical Engineering", "University of Lagos", 4.3, 5, 2022, 3, ("IELTS", 7.0, 7.5, 7, 6.5, 7),
             "", ["US", "Canada"], [ENG + "Electrical & Computer"], "Masters", "Fall 2027", (35000, 55000, "USD"), True, 1, 4),
    _student("Linh", "Nguyen", "Female", "2002-01-25", "Vietnam", "+84", "912345678", "Hanoi",
             "B.Sc. Mathematics", "Vietnam National University, Hanoi", 3.6, 4, 2024, 0, ("IELTS", 7.0, 7, 7.5, 6.5, 7),
             "", ["Singapore", "Hong Kong"], ["Mathematics"], "Masters", "Fall 2027", (25000, 40000, "USD"), False, 2, 3),
    _student("Rafael", "Souza", "Male", "1999-11-14", "Brazil", "+55", "11987654321", "São Paulo",
             "B.Eng. Mechanical Engineering", "University of São Paulo", 8.2, 10, 2021, 4, ("TOEFL", 104, 27, 26, 25, 26),
             "", ["Germany", "Netherlands"], [ENG + "Mechanical & Aerospace"], "Masters", "Fall 2027", (10000, 20000, "EUR"), False, 3, 3),
    _student("Wanjiru", "Kamau", "Female", "2001-07-30", "Kenya", "+254", "712345678", "Nairobi",
             "B.Sc. Biochemistry", "University of Nairobi", 3.7, 4, 2023, 1, ("IELTS", 7.5, 8, 7.5, 7, 7.5),
             "", ["Australia", "Canada"], ["Computational Biology & Bioinformatics"], "Masters", "Spring 2028", (30000, 45000, "AUD"), True, 4, 2),
    _student("Tanvir", "Hasan", "Male", "2000-02-18", "Bangladesh", "+880", "1712345678", "Dhaka",
             "B.Sc. Computer Science & Engineering", "Bangladesh University of Engineering and Technology", 3.8, 4, 2022, 2,
             ("IELTS", 7.0, 7.5, 7, 6.5, 7), "GRE 318", ["US"], ["CS & AI", "Mathematics"], "PhD", "Fall 2027", (0, 20000, "USD"), True, 1, 4),
    _student("Sanduni", "Perera", "Female", "2002-06-05", "Sri Lanka", "+94", "771234567", "Colombo",
             "B.Sc. Physics", "University of Colombo", 3.5, 4, 2024, 0, ("IELTS", 6.5, 7, 6.5, 6, 6.5),
             "", ["UK"], ["Physics & Astronomy"], "Masters", "Fall 2027", (25000, 35000, "GBP"), False, 0, 2),
    _student("Aarav", "Shrestha", "Male", "2001-12-22", "Nepal", "+977", "9812345678", "Kathmandu",
             "B.E. Civil Engineering", "Tribhuvan University", 76, 100, 2023, 1, ("PTE", 68, None, None, None, None),
             "", ["Australia"], [ENG + "Civil & Environmental"], "Masters", "Spring 2028", (30000, 40000, "AUD"), False, 4, 1),
    _student("Putri", "Wulandari", "Female", "2002-03-17", "Indonesia", "+62", "81234567890", "Jakarta",
             "B.Sc. Chemistry", "Institut Teknologi Bandung", 3.4, 4, 2024, 0, ("IELTS", 6.5, 7, 6.5, 6, 6.5),
             "", ["Netherlands", "Germany"], ["Chemistry"], "Masters", "Fall 2027", (12000, 20000, "EUR"), True, 3, 2),
    _student("Omar", "Farouk", "Male", "2000-10-09", "Egypt", "+20", "1001234567", "Cairo",
             "B.Sc. Biomedical Engineering", "Cairo University", 3.3, 4, 2022, 2, ("IELTS", 7.0, 7, 7, 6.5, 7),
             "", ["Germany", "Switzerland"], [ENG + "Biomedical"], "Masters", "Spring 2027", (15000, 30000, "EUR"), False, 3, 5,
             ["Completed", "Withdrawn"]),
    _student("Ayesha", "Siddiqui", "Female", "2001-05-28", "Pakistan", "+92", "3001234567", "Lahore",
             "B.S. Data Science", "Lahore University of Management Sciences", 3.75, 4, 2023, 1, ("IELTS", 8.0, 8.5, 8, 7.5, 8),
             "GRE 325", ["US", "UK"], ["CS & AI"], "Masters", "Spring 2027", (40000, 60000, "USD"), True, 1, 5,
             ["Offer Received", "Offer Received", "Rejected"]),
    _student("Kwabena", "Asante", "Male", "2001-08-11", "Ghana", "+233", "241234567", "Accra",
             "B.Sc. Earth Science", "University of Ghana", 3.2, 4, 2023, 1, ("IELTS", 6.5, 7, 6.5, 6, 6.5),
             "", ["Canada"], ["Earth & Environmental Sciences"], "Masters", "Spring 2028", (20000, 30000, "CAD"), True, 4, 1),
    _student("Maria", "Santos", "Female", "2002-09-02", "Philippines", "+63", "9171234567", "Manila",
             "B.S. Applied Mathematics", "University of the Philippines Diliman", 3.5, 4, 2024, 0, ("IELTS", 7.0, 7.5, 7, 6.5, 7),
             "", ["Singapore", "Japan"], ["Mathematics", "CS & AI"], "Masters", "Fall 2027", (20000, 35000, "USD"), False, 2, 3),
    _student("Diego", "Hernández", "Male", "2000-04-04", "Mexico", "+52", "5512345678", "Mexico City",
             "B.Eng. Chemical Engineering", "National Autonomous University of Mexico (UNAM)", 8.9, 10, 2022, 3,
             ("TOEFL", 98, 25, 25, 24, 24), "", ["US", "Canada"], [ENG + "Chemical & Materials"], "Masters", "Fall 2027",
             (30000, 50000, "USD"), False, 1, 2),
    _student("Elif", "Yılmaz", "Female", "2001-11-19", "Turkey", "+90", "5321234567", "Istanbul",
             "B.Sc. Aerospace Engineering", "Istanbul Technical University", 3.4, 4, 2023, 1, ("IELTS", 7.0, 7, 7.5, 6.5, 7),
             "", ["Germany", "France"], [ENG + "Mechanical & Aerospace"], "Masters", "Fall 2027", (10000, 20000, "EUR"), True, 3, 4),
    _student("Joon-ho", "Park", "Male", "2001-03-08", "South Korea", "+82", "1012345678", "Seoul",
             "B.S. Computer Science", "Korea University", 3.9, 4.3, 2023, 2, ("TOEFL", 110, 29, 28, 26, 27),
             "GRE 329", ["US", "Switzerland"], ["CS & AI"], "PhD", "Fall 2027", (0, 25000, "USD"), True, 2, 4),
    # Newly registered and not yet assigned - for the administrator to assign.
    _student("Rohan", "Mehta", "Male", "2003-02-10", "India", "+91", "9820012345", "Mumbai",
             "B.Tech. Electronics (final year)", "VJTI Mumbai", 8.1, 10, 2026, 0, None,
             "", ["US"], [ENG + "Electrical & Computer"], "Masters", "Fall 2028", None, False, None, 0),
    _student("Fatima", "Al Mansoori", "Female", "2002-12-01", "United Arab Emirates", "+971", "501234567", "Dubai",
             "", "", None, None, None, None, None, "", ["UK"], [], "Masters", "", None, False, None, 0),
]

JOINED_DAYS_AGO = {0: 3, 1: 25, 2: 50, 3: 80, 4: 115, 5: 170}
WORKFLOW = ["Planned", "Shortlisted", "Documents Pending", "Submitted", "Under Review"]
DEFAULT_FINALS = {2: ["Shortlisted", "Planned"], 3: ["Documents Pending", "Documents Pending", "Shortlisted"],
                  4: ["Submitted", "Under Review", "Documents Pending"], 5: ["Offer Received", "Rejected", "Under Review"]}
STATUS_REMARKS = {
    "Planned": "Added to the student's plan.",
    "Shortlisted": "Shortlisted after counselling review.",
    "Documents Pending": "Collecting SOP and recommendation letters.",
    "Submitted": "Application submitted on the university portal.",
    "Under Review": "University confirmed receipt; under review.",
    "Offer Received": "Offer letter received.",
    "Rejected": "University declined the application.",
    "Withdrawn": "Withdrawn by the student after accepting another offer.",
    "Completed": "Offer accepted and deposit paid.",
}


class Seeder:
    def __init__(self, password: str, log=print):
        self.password = password
        self.log = log
        self.rng = random.Random(2026)
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.counts: dict[str, int] = {}
        self.universities = {u["_id"]: u for u in repository.find({"type": "university"})}
        self.courses = repository.find({"type": "course"}, fields=["_id", "university_id", "title", "cluster"])
        if not self.universities or not self.courses:
            raise ValueError("Load the university and course catalogue first (manage.py load_universities).")

    # -- helpers -------------------------------------------------------------
    def at(self, days_ago: float = 0, hour: int | None = None) -> str:
        t = self.now - timedelta(days=days_ago)
        if hour is not None:
            t = t.replace(hour=hour, minute=0, second=0)
        return t.strftime("%Y-%m-%dT%H:%M:%SZ")

    def save(self, doc: dict) -> dict:
        doc["source"] = SEED
        self.counts[doc["type"]] = self.counts.get(doc["type"], 0) + 1
        return repository.save(doc)

    # -- master data ---------------------------------------------------------
    def seed_master_data(self):
        per_country: dict[str, int] = {}
        for u in self.universities.values():
            per_country[u["country"]] = per_country.get(u["country"], 0) + 1
        for name, (code, full, currency, region) in COUNTRIES.items():
            self.save({"_id": f"country_{code}", "type": "country", "code": code, "name": full,
                       "catalogue_name": name, "currency": currency, "region": region,
                       "university_count": per_country.get(name, 0), "created_at": self.at()})
        self.intakes = {}
        for name, season, year, deadline, decision, start in INTAKES:
            doc = {"_id": f"intake_{season.lower()}_{year}", "type": "intake", "name": name, "season": season,
                   "year": year, "application_deadline": deadline, "decision_by": decision, "start_date": start,
                   "created_at": self.at()}
            self.intakes[name] = self.save(doc)

    # -- people --------------------------------------------------------------
    def seed_counsellors(self):
        self.counsellors = []
        for spec in COUNSELLORS:
            user = users.build_user(email=spec["email"], password=self.password, role=COUNSELLOR, full_name=spec["name"])
            doc = counsellor_services.build_counsellor(user_id=user["_id"], **spec)
            doc["created_at"] = user["created_at"] = self.at(240)
            user["profile_id"] = doc["_id"]
            self.save(doc)
            self.save(user)
            self.counsellors.append((doc, user))

    def seed_students(self):
        self.students = []
        for spec in STUDENTS:
            email = f"{spec['first']}.{spec['last']}".lower().replace(" ", "").replace("-", "") + "@students.example.org"
            email = email.encode("ascii", "ignore").decode()  # drop accents from the address only
            user = users.build_user(email=email, password=self.password, role=STUDENT,
                                    full_name=f"{spec['first']} {spec['last']}")
            doc = student_services.build_student(user_id=user["_id"], email=user["email"], first_name=spec["first"],
                                                 last_name=spec["last"], dial_code=spec["dial"], phone=spec["phone"],
                                                 citizenship=spec["citizenship"], degree_level=spec["level"])
            test = spec["test"]
            budget = spec["budget"]
            student_services.apply_update(doc, {
                "personal": {"gender": spec["gender"], "date_of_birth": spec["dob"],
                             "address": {"city": spec["city"], "country": spec["citizenship"]}},
                "academic": {
                    "degree": spec["degree"], "institution": spec["institution"], "cgpa": spec["cgpa"],
                    "gpa_scale": spec["scale"], "graduation_year": spec["grad"], "work_experience_years": spec["work"],
                    "gre_status": spec["gre"],
                    "english_test": ({"test_type": test[0], "overall": test[1], "listening": test[2], "reading": test[3],
                                      "writing": test[4], "speaking": test[5]} if test else {}),
                },
                "preferences": {
                    "countries": spec["countries"], "course_areas": spec["areas"], "intake": spec["intake"],
                    "budget": ({"min": budget[0], "max": budget[1], "currency": budget[2]} if budget else {}),
                    "requires_scholarship": spec["scholarship"],
                },
            })
            joined = JOINED_DAYS_AGO[spec["stage"]]
            doc["created_at"] = user["created_at"] = self.at(joined)
            user["profile_id"] = doc["_id"]
            if spec["stage"] >= 1:
                user["last_login"] = self.at(self.rng.uniform(0.2, 6))
            self.save(doc)
            self.save(user)
            counsellor = user_c = None
            if spec["counsellor"] is not None:
                counsellor, user_c = self.counsellors[spec["counsellor"]]
                student_services.assign_counsellor(doc, counsellor["_id"], actor=None)
                doc["counsellor_assigned_at"] = self.at(joined - 1)
                repository.save(doc)
            self.students.append({"spec": spec, "doc": doc, "user": user, "counsellor": counsellor,
                                  "counsellor_user": user_c, "joined": joined, "applications": [], "documents": [],
                                  "follow_ups": []})

    # -- catalogue matching (rule-based, SRS 4.8) ----------------------------
    def gpa_norm(self, spec) -> float:
        return spec["cgpa"] / spec["scale"] if spec["cgpa"] and spec["scale"] else 0.0

    def candidates(self, spec) -> list[dict]:
        def in_country(c):
            return self.universities[c["university_id"]]["country"] in spec["countries"]
        exact = [c for c in self.courses if in_country(c) and c["cluster"] in spec["areas"]]
        pool = exact if len(exact) >= 3 else exact + [c for c in self.courses if in_country(c) and c not in exact]
        return sorted(pool, key=lambda c: (self.universities[c["university_id"]]["rank"], c["title"]))

    def tier(self, spec, rank: int) -> str:
        g = self.gpa_norm(spec)
        if rank <= 15:
            return "Target" if g >= 0.92 else "Reach"
        if rank <= 50:
            return "Target" if g >= 0.8 else "Reach"
        return "Safe" if g >= 0.75 else "Target"

    def score(self, spec, course) -> tuple[int, dict, list[str]]:
        uni = self.universities[course["university_id"]]
        country_ok = uni["country"] in spec["countries"]
        course_ok = course["cluster"] in spec["areas"]
        g = self.gpa_norm(spec)
        academic = round(25 * min(1.0, g / (0.95 if uni["rank"] <= 25 else 0.8))) if g else 10
        intake_ok = bool(spec["intake"])
        total = (35 if country_ok else 0) + (30 if course_ok else 10) + academic + (10 if intake_ok else 0)
        factors = {"country_match": country_ok, "course_match": course_ok, "academic_fit": academic,
                   "intake_available": intake_ok, "budget_fit": None}
        reasons = []
        if country_ok:
            reasons.append(f"{uni['country']} is one of the student's target countries")
        reasons.append(f"Programme area '{course['cluster']}' " + ("matches" if course_ok else "is close to")
                       + " the preferred course areas")
        if g:
            reasons.append(f"Academic profile ({spec['cgpa']}/{spec['scale']}) vs world rank #{uni['rank']}")
        reasons.append("Tuition data not yet in the catalogue - budget not scored")
        return min(total, 100), factors, reasons

    def pick_courses(self, spec, n: int) -> list[dict]:
        """One course per university, spread across reach / target / safe ranks."""
        by_uni: dict[str, list[dict]] = {}
        for c in self.candidates(spec):
            by_uni.setdefault(c["university_id"], []).append(c)
        unis = list(by_uni)
        if not unis:
            return []
        idx = sorted({0, len(unis) // 2, len(unis) - 1, 1, len(unis) // 3})
        picks = []
        for i in idx:
            if len(picks) == n:
                break
            picks.append(self.rng.choice(by_uni[unis[i]]))
        return picks

    # -- workflow ------------------------------------------------------------
    @staticmethod
    def path_to(final: str) -> list[str]:
        if final in WORKFLOW:
            return WORKFLOW[:WORKFLOW.index(final) + 1]
        if final in ("Offer Received", "Rejected"):
            return WORKFLOW + [final]
        if final == "Completed":
            return WORKFLOW + ["Offer Received", "Completed"]
        if final == "Withdrawn":
            return WORKFLOW[:3] + ["Withdrawn"]
        raise ValueError(final)

    def seed_applications(self):
        for s in self.students:
            spec = s["spec"]
            if spec["stage"] < 2 or not s["counsellor"]:
                continue
            finals = spec["finals"] or DEFAULT_FINALS[spec["stage"]]
            intake = self.intakes[spec["intake"]]
            for course, final in zip(self.pick_courses(spec, len(finals)), finals):
                uni = self.universities[course["university_id"]]
                path = self.path_to(final)
                start = s["joined"] - 10
                end = self.rng.uniform(1, 6)
                step = (start - end) / max(1, len(path) - 1)
                app = {
                    "_id": repository.new_id("application"), "type": "application",
                    "student_id": s["doc"]["_id"], "counsellor_id": s["counsellor"]["_id"],
                    "university_id": uni["_id"], "course_id": course["_id"], "intake_id": intake["_id"],
                    "status": final, "deadline": intake["application_deadline"],
                    "decision_expected": intake["decision_by"],
                    "snapshot": {"university_name": uni["name"], "country": uni["country"], "world_rank": uni["rank"],
                                 "course_title": course["title"], "cluster": course["cluster"],
                                 "intake_name": intake["name"]},
                    "tier": self.tier(spec, uni["rank"]),
                    "history_ids": [], "submitted_at": None,
                    "created_at": self.at(start), "updated_at": self.at(end),
                }
                old = None
                for i, status in enumerate(path):
                    when = self.at(start - i * step)
                    by_student = status == "Planned"
                    hist = self.save({
                        "_id": repository.new_id("application_history"), "type": "application_history",
                        "application_id": app["_id"], "old_status": old, "new_status": status,
                        "changed_by": s["user"]["_id"] if by_student else s["counsellor_user"]["_id"],
                        "changed_by_role": STUDENT if by_student else COUNSELLOR,
                        "timestamp": when, "remarks": STATUS_REMARKS[status],
                    })
                    app["history_ids"].append(hist["_id"])
                    if status == "Submitted":
                        app["submitted_at"] = when
                    old = status
                self.save(app)
                s["applications"].append(app)
            s["doc"]["application_ids"] = [a["_id"] for a in s["applications"]]
            s["doc"]["updated_at"] = self.at(1)
            repository.save(s["doc"])

    def document(self, s, doc_type, status, application=None, remarks="", days_ago=None) -> dict:
        spec = s["spec"]
        days_ago = days_ago if days_ago is not None else self.rng.uniform(5, max(6, s["joined"] - 5))
        uploaded = status != "Required"
        reviewed = status in ("Verified", "Rejected", "Expired")
        slug = doc_type.lower().replace("/", "_").replace(" ", "_")
        suffix = f"_{application['snapshot']['university_name'].split()[0].lower()}" if application else ""
        doc = {
            "_id": repository.new_id("document"), "type": "document",
            "student_id": s["doc"]["_id"], "application_id": application["_id"] if application else None,
            "counsellor_id": s["counsellor"]["_id"] if s["counsellor"] else None,
            "document_type": doc_type, "status": status,
            "filename": f"{spec['last'].lower().replace(' ', '_')}_{slug}{suffix}.pdf" if uploaded else None,
            "storage_ref": None,  # metadata only; file storage arrives with the documents module
            "uploaded_at": self.at(days_ago) if uploaded else None,
            "verified_by": s["counsellor"]["_id"] if reviewed and s["counsellor"] else None,
            "verified_at": self.at(max(0.5, days_ago - 2)) if reviewed else None,
            "remarks": remarks,
            "created_at": self.at(s["joined"]), "updated_at": self.at(max(0.5, days_ago - 2)),
        }
        self.save(doc)
        s["documents"].append(doc)
        return doc

    def seed_documents(self):
        for s in self.students:
            spec, stage = s["spec"], s["spec"]["stage"]
            core = ["Transcript", "Degree Certificate", "Passport", "Resume/CV"] + (["Test Score"] if spec["test"] else [])
            for t in core:
                if stage == 0:
                    status = "Required"
                elif stage == 1:
                    status = "Uploaded" if t in ("Transcript", "Passport") else "Required"
                elif stage == 2:
                    status = {"Transcript": "Verified", "Passport": "Verified", "Degree Certificate": "Under Review"}.get(t, "Uploaded")
                else:
                    status = "Under Review" if (stage == 3 and t == "Test Score") else "Verified"
                remarks = ""
                if spec["last"] == "Souza" and t == "Passport":
                    status, remarks = "Expired", "Passport expires before the intake start date; renewal required."
                if spec["last"] == "Wulandari" and t == "Degree Certificate":
                    status, remarks = "Rejected", "Scan is illegible; please upload a certified copy."
                self.document(s, t, status, remarks=remarks)
            for app in s["applications"]:
                if app["status"] in ("Planned", "Shortlisted"):
                    continue
                if app["status"] == "Documents Pending":
                    self.document(s, "SOP", self.rng.choice(["Uploaded", "Under Review"]), app)
                    self.document(s, "LOR", "Required", app)
                else:
                    self.document(s, "SOP", "Verified", app)
                    self.document(s, "LOR", "Verified", app)

    def seed_sessions(self):
        plans = [
            (1, "Initial profile assessment",
             "Reviewed academic record, English test plans and budget. Agreed target countries and programme areas.",
             ["Upload transcripts and passport", "Book the English test if not taken"], "Upload core documents"),
            (2, "University shortlisting",
             "Went through rule-based matches and agreed a balanced reach / target / safe shortlist.",
             ["Research the shortlisted programme curricula", "Draft a first SOP outline"], "Send SOP outline for review"),
            (3, "SOP and application review",
             "Line-by-line SOP feedback; confirmed referees and application portal accounts.",
             ["Finalise SOP", "Request two recommendation letters"], "Submit final SOP and LOR requests"),
            (4, "Submission check and interview preparation",
             "Verified every document before submission and ran a mock admissions interview.",
             ["Track portal status weekly", "Prepare for possible interviews"], "Share any university emails"),
            (5, "Offer review and next steps",
             "Compared offers on cost, funding and post-study work rights; discussed visa timelines.",
             ["Accept the preferred offer", "Start the visa document checklist"], "Confirm decision on offers"),
        ]
        for s in self.students:
            if not s["counsellor"]:
                continue
            stage = s["spec"]["stage"]
            done = [p for p in plans if p[0] <= stage]
            gap = (s["joined"] - 3) / max(1, len(done))
            for i, (_, topic, summary, recs, action) in enumerate(done):
                when = s["joined"] - 2 - i * gap
                latest = i == len(done) - 1
                follow = {"action": action, "due_date": self.at(when - 7)[:10], "status": "Pending" if latest else "Done"}
                doc = self.save({
                    "_id": repository.new_id("counselling_session"), "type": "counselling_session",
                    "student_id": s["doc"]["_id"], "counsellor_id": s["counsellor"]["_id"],
                    "scheduled_at": self.at(when, hour=self.rng.choice([5, 7, 9, 11])),
                    "duration_minutes": self.rng.choice([30, 45, 60]), "mode": self.rng.choice(["Video call", "In person", "Phone"]),
                    "topic": topic, "status": "Completed", "summary": summary, "recommendations": recs,
                    "follow_up": follow, "created_at": self.at(when + 3), "updated_at": self.at(when),
                })
                if latest:
                    s["follow_ups"].append(doc)
            nxt = plans[min(stage, len(plans) - 1)] if stage < 5 else plans[4]
            self.save({
                "_id": repository.new_id("counselling_session"), "type": "counselling_session",
                "student_id": s["doc"]["_id"], "counsellor_id": s["counsellor"]["_id"],
                "scheduled_at": self.at(-self.rng.uniform(1, 10), hour=self.rng.choice([5, 7, 9, 11])),
                "duration_minutes": 45, "mode": "Video call", "topic": nxt[1], "status": "Scheduled",
                "summary": "", "recommendations": [], "follow_up": None,
                "created_at": self.at(2), "updated_at": self.at(2),
            })

    def seed_recommendations(self):
        for s in self.students:
            spec = s["spec"]
            if spec["stage"] < 2 or not s["counsellor"]:
                continue
            applied = {a["course_id"] for a in s["applications"]}
            pool = [c for c in self.candidates(spec)]
            ranked = sorted(pool, key=lambda c: -self.score(spec, c)[0])
            chosen, seen_unis = [], set()
            for c in [c for c in pool if c["_id"] in applied] + ranked:
                if c["university_id"] in seen_unis:
                    continue
                chosen.append(c)
                seen_unis.add(c["university_id"])
                if len(chosen) == len(applied) + 2:
                    break
            for i, c in enumerate(chosen):
                uni = self.universities[c["university_id"]]
                score, factors, reasons = self.score(spec, c)
                status = "Accepted" if c["_id"] in applied else ("Rejected" if spec["stage"] >= 3 and i == len(chosen) - 1 else "Suggested")
                self.save({
                    "_id": repository.new_id("recommendation"), "type": "recommendation",
                    "student_id": s["doc"]["_id"], "university_id": uni["_id"], "course_id": c["_id"],
                    "created_by": s["counsellor"]["_id"], "method": "rule_based_v1",
                    "match_score": score, "tier": self.tier(spec, uni["rank"]), "match_factors": factors,
                    "reasons": reasons, "status": status,
                    "remarks": "Student preferred a different city." if status == "Rejected" else "",
                    "snapshot": {"university_name": uni["name"], "country": uni["country"], "world_rank": uni["rank"],
                                 "course_title": c["title"], "cluster": c["cluster"]},
                    "created_at": self.at(s["joined"] - 12), "updated_at": self.at(self.rng.uniform(2, 10)),
                })

    def notify(self, user_id, role, category, title, message, related_id=None, days_ago=1.0, link=None):
        self.save({
            "_id": repository.new_id("notification"), "type": "notification",
            "recipient_user_id": user_id, "recipient_role": role, "category": category,
            "title": title, "message": message, "related_id": related_id, "link": link,
            "is_read": days_ago > 4, "created_at": self.at(days_ago),
        })

    def seed_notifications(self):
        for s in self.students:
            uid, name = s["user"]["_id"], f"{s['spec']['first']} {s['spec']['last']}"
            if s["counsellor"]:
                self.notify(uid, STUDENT, "assignment", "Counsellor assigned",
                            f"{s['counsellor']['name']} is now your counsellor.", s["counsellor"]["_id"],
                            s["joined"] - 1, "/profile/")
                self.notify(s["counsellor_user"]["_id"], COUNSELLOR, "assignment", "New student assigned",
                            f"{name} has been assigned to you.", s["doc"]["_id"], s["joined"] - 1,
                            f"/students/{s['doc']['_id']}/")
            required = [d for d in s["documents"] if d["status"] in ("Required", "Rejected", "Expired")]
            if required:
                kinds = ", ".join(sorted({d["document_type"] for d in required}))
                self.notify(uid, STUDENT, "missing_document", f"{len(required)} document{'' if len(required) == 1 else 's'} {'needs' if len(required) == 1 else 'need'} your attention",
                            f"Please upload or replace: {kinds}.", None, self.rng.uniform(0.5, 3))
            for app in s["applications"]:
                snap = app["snapshot"]
                if app["status"] not in ("Planned",):
                    self.notify(uid, STUDENT, "status_change", f"Application update: {app['status']}",
                                f"{snap['course_title']} at {snap['university_name']} is now '{app['status']}'.",
                                app["_id"], self.rng.uniform(0.5, 8))
                if app["status"] in ("Planned", "Shortlisted", "Documents Pending"):
                    self.notify(uid, STUDENT, "deadline", "Upcoming application deadline",
                                f"{snap['university_name']} - apply by {app['deadline']} ({snap['intake_name']}).",
                                app["_id"], self.rng.uniform(0.5, 3))
            for sess in s["follow_ups"]:
                self.notify(s["counsellor_user"]["_id"], COUNSELLOR, "follow_up", "Follow-up due",
                            f"{name}: {sess['follow_up']['action']} (due {sess['follow_up']['due_date']}).",
                            sess["_id"], self.rng.uniform(0.2, 2))

    def run(self) -> dict:
        self.log("Master data (countries, intakes)...")
        self.seed_master_data()
        self.log("Counsellors...")
        self.seed_counsellors()
        self.log("Students and counsellor assignments...")
        self.seed_students()
        self.log("Applications and status history...")
        self.seed_applications()
        self.log("Documents, counselling sessions, recommendations, notifications...")
        self.seed_documents()
        self.seed_sessions()
        self.seed_recommendations()
        self.seed_notifications()
        return self.counts


def existing_seed_ids() -> set[str]:
    return {d["_id"] for d in maintenance.all_docs() if d.get("source") == SEED}


def remove_seed() -> int:
    """Delete every seed document and the audit entries about them. Real data is untouched."""
    seed_ids = existing_seed_ids()
    if not seed_ids:
        return 0
    removed = 0
    for d in maintenance.all_docs():
        is_seed_audit = d.get("type") == "audit_log" and (d.get("target_id") in seed_ids or d.get("actor_id") in seed_ids)
        if d["_id"] in seed_ids or is_seed_audit:
            repository.delete(d)
            removed += 1
    return removed
