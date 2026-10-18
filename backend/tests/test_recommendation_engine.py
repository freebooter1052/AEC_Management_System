"""Unit tests for the rule-based recommendation engine (SRS 4.8): every factor, hard rule and boundary."""

from datetime import date

from django.test import SimpleTestCase

from apps.recommendations import engine

TODAY = date(2026, 10, 16)
INTAKES = [
    {"_id": "intake_spring_2027", "name": "Spring 2027", "application_deadline": "2026-09-30", "start_date": "2027-02-01"},
    {"_id": "intake_fall_2027", "name": "Fall 2027", "application_deadline": "2027-01-15", "start_date": "2027-09-06"},
    {"_id": "intake_fall_2028", "name": "Fall 2028", "application_deadline": "2028-01-15", "start_date": "2028-09-04"},
]
UNI = {"_id": "university_001", "name": "Technical University of Munich", "country": "Germany", "rank": 45}


def student(**prefs_and_academic):
    academic = {"cgpa": 8.5, "gpa_scale": 10, "english_test": {"test_type": "IELTS", "overall": 7.0}}
    prefs = {"countries": ["Germany"], "course_areas": ["CS & AI"], "degree_level": "Masters", "intake": "Fall 2027",
             "budget": {"min": 0, "max": 20000, "currency": "EUR"}}
    for key, value in prefs_and_academic.items():
        (academic if key in ("cgpa", "gpa_scale", "english_test") else prefs)[key] = value
    return {"_id": "student_x", "academic": academic, "preferences": prefs}


def course(**extra):
    return {"_id": "course_0001", "university_id": "university_001", "title": "Robotics", "canonical_name": "Robotics",
            "cluster": "CS & AI", **extra}


FULL = dict(level="Masters", tuition={"amount_per_year": 15000, "currency": "EUR"},
            eligibility={"min_grade_pct": 75, "min_english": {"IELTS": 6.5}})


class FactorTests(SimpleTestCase):
    def test_country(self):
        self.assertEqual(engine.country_factor(["Germany"], UNI)["score"], 1.0)
        self.assertEqual(engine.country_factor(["Canada"], UNI)["status"], "no_match")
        f = engine.country_factor([], UNI)
        self.assertEqual((f["status"], f["score"]), ("unknown", None))

    def test_course_area_matching(self):
        c = course(title="Machine Learning", cluster="CS & AI")
        self.assertEqual(engine.course_factor(["CS & AI"], c)["score"], 1.0)
        self.assertEqual(engine.course_factor(["cs & ai"], c)["score"], 1.0)              # case-insensitive
        self.assertEqual(engine.course_factor(["Computer Science"], c)["score"], 1.0)     # alias to the cluster
        self.assertEqual(engine.course_factor(["machine learning"], course(title="Machine Learning", cluster="Mathematics"))["score"], 0.8)
        self.assertEqual(engine.course_factor(["Robotics Engineering"], course(cluster="Mathematics"))["score"], 0.8)
        self.assertEqual(engine.course_factor(["Robotics and Automation"],
                                              course(title="Autonomous Robotics", canonical_name="", cluster="X"))["score"], 0.5)
        self.assertEqual(engine.course_factor(["Mechanical Engineering"],
                                              course(title="Electrical Engineering", canonical_name="", cluster="X"))["score"], 0.0)
        self.assertEqual(engine.course_factor(["History"], c)["status"], "no_match")
        self.assertEqual(engine.course_factor([], c)["status"], "unknown")

    def test_academic_with_recorded_minimum_boundaries(self):
        c = course(eligibility={"min_grade_pct": 85})
        at_min, _ = engine.academic_factor({"cgpa": 8.5, "gpa_scale": 10}, c, UNI)
        self.assertEqual((at_min["status"], at_min["score"]), ("match", 0.7))           # exactly the minimum passes
        below, tier = engine.academic_factor({"cgpa": 8.49, "gpa_scale": 10}, c, UNI)
        self.assertEqual((below["status"], tier), ("no_match", None))
        well_above, tier = engine.academic_factor({"cgpa": 9.6, "gpa_scale": 10}, c, UNI)
        self.assertEqual((well_above["score"], tier), (1.0, "Safe"))

    def test_academic_estimate_from_ranking(self):
        # rank 45 -> about 80% expected; linear over the 20 points below
        f, tier = engine.academic_factor({"cgpa": 8.0, "gpa_scale": 10}, course(), UNI)
        self.assertEqual((f["status"], f["score"], tier), ("match", 1.0, "Target"))
        self.assertIn("Estimate", f["detail"])
        f, tier = engine.academic_factor({"cgpa": 7.0, "gpa_scale": 10}, course(), UNI)
        self.assertEqual((f["status"], f["score"], tier), ("partial", 0.5, "Reach"))
        f, _ = engine.academic_factor({"cgpa": 5.9, "gpa_scale": 10}, course(), UNI)
        self.assertEqual((f["status"], f["score"]), ("no_match", 0.0))
        f, tier = engine.academic_factor({"cgpa": None, "gpa_scale": 10}, course(), UNI)
        self.assertEqual((f["status"], f["score"], tier), ("unknown", None, None))
        self.assertEqual(engine.grade_pct({"cgpa": 76, "gpa_scale": 100}), 76.0)
        self.assertIsNone(engine.grade_pct({"cgpa": 3.5, "gpa_scale": 0}))

    def test_budget(self):
        b = {"max": 20000, "currency": "EUR"}
        fee = lambda n, cur="EUR": course(tuition={"amount_per_year": n, "currency": cur})  # noqa: E731
        self.assertEqual(engine.budget_factor(b, fee(20000))["score"], 1.0)               # at the maximum
        self.assertEqual(engine.budget_factor(b, fee(24000))["score"], 0.5)               # 20% over
        self.assertEqual(engine.budget_factor(b, fee(24001))["score"], 0.0)
        self.assertEqual(engine.budget_factor(b, fee(15000, "USD"))["status"], "unknown")  # no FX rates invented
        self.assertEqual(engine.budget_factor(b, course())["status"], "unknown")           # no tuition recorded
        self.assertEqual(engine.budget_factor({}, fee(1000))["status"], "unknown")         # no budget

    def test_intake(self):
        f, check, chosen = engine.intake_factor("Fall 2027", INTAKES, course(), TODAY)
        self.assertEqual((f["score"], check["status"], chosen["_id"]), (1.0, "pass", "intake_fall_2027"))
        f, check, chosen = engine.intake_factor("Spring 2027", INTAKES, course(), TODAY)   # closed on 2026-09-30
        self.assertEqual((f["status"], f["score"], chosen["_id"]), ("partial", 0.5, "intake_fall_2027"))
        self.assertIn("closed", f["detail"])
        f, check, chosen = engine.intake_factor("Fall 2027", INTAKES, course(intake_ids=["intake_spring_2027"]), TODAY)
        self.assertEqual((check["status"], chosen), ("fail", None))                       # only a closed intake offered
        f, check, chosen = engine.intake_factor("", INTAKES, course(), TODAY)
        self.assertEqual((f["status"], chosen["_id"]), ("unknown", "intake_fall_2027"))
        f, check, chosen = engine.intake_factor("Fall 2027", [], course(), TODAY)
        self.assertEqual((f["status"], check["status"]), ("unknown", "unknown"))
        deadline_today = [{**INTAKES[1], "application_deadline": TODAY.isoformat()}]
        self.assertEqual(engine.intake_factor("Fall 2027", deadline_today, course(), TODAY)[1]["status"], "pass")


class HardRuleTests(SimpleTestCase):
    def test_level(self):
        self.assertEqual(engine.level_check("Masters", course(level="Masters"))["status"], "pass")
        self.assertEqual(engine.level_check("Masters", course(level="PhD"))["status"], "fail")
        self.assertEqual(engine.level_check("Masters", course())["status"], "unknown")
        self.assertEqual(engine.level_check("", course(level="PhD"))["status"], "unknown")

    def test_grades_and_english(self):
        c = course(eligibility={"min_grade_pct": 80, "min_english": {"IELTS": 6.5, "TOEFL": 90}})
        self.assertEqual(engine.grades_check({"cgpa": 8.0, "gpa_scale": 10}, c)["status"], "pass")
        self.assertEqual(engine.grades_check({"cgpa": 7.9, "gpa_scale": 10}, c)["status"], "fail")
        self.assertEqual(engine.grades_check({}, c)["status"], "unknown")
        self.assertEqual(engine.grades_check({"cgpa": 9, "gpa_scale": 10}, course())["status"], "unknown")
        ielts = lambda s: {"english_test": {"test_type": "IELTS", "overall": s}}  # noqa: E731
        self.assertEqual(engine.english_check(ielts(6.5), c)["status"], "pass")
        self.assertEqual(engine.english_check(ielts(6.0), c)["status"], "fail")
        self.assertEqual(engine.english_check({"english_test": {"test_type": "PTE", "overall": 70}}, c)["status"], "unknown")
        self.assertEqual(engine.english_check({}, c)["status"], "unknown")
        self.assertEqual(engine.english_check(ielts(9), course())["status"], "unknown")


class EvaluateTests(SimpleTestCase):
    def test_fully_known_course_is_eligible_with_exact_score(self):
        ev = engine.evaluate(student(), course(**FULL), UNI, INTAKES, TODAY)
        self.assertEqual(ev["eligibility"], "eligible")
        # country 30*1 + course 30*1 + academic 20*(0.7+0.3*1.0=1.0) + intake 10*1 + budget 10*1 = 100
        self.assertEqual((ev["match_score"], ev["confidence"], ev["ranking_score"]), (100, 100, 100))
        self.assertEqual(ev["intake_id"], "intake_fall_2027")
        self.assertEqual(ev["missing_data"], [])
        self.assertEqual(ev["method"], engine.METHOD)

    def test_weighted_score_formula(self):
        # budget 0.5 (20% over), academic estimate 0.5 (70% vs ~80%), others 1
        s = student(cgpa=7.0, budget={"max": 12500, "currency": "EUR"})
        c = course(level="Masters", tuition={"amount_per_year": 15000, "currency": "EUR"})
        ev = engine.evaluate(s, c, UNI, INTAKES, TODAY)
        expected = round(100 * (30 + 30 + 20 * 0.5 + 10 + 10 * 0.5) / 100)
        self.assertEqual(ev["match_score"], expected)
        self.assertEqual(ev["eligibility"], "insufficient_data")  # grade & English requirements not recorded

    def test_hard_failure_beats_a_perfect_preference_score(self):
        for bad in (dict(level="PhD"), dict(eligibility={"min_grade_pct": 90}),
                    dict(eligibility={"min_english": {"IELTS": 7.5}}), dict(intake_ids=["intake_spring_2027"])):
            ev = engine.evaluate(student(), course(**{**FULL, **bad}), UNI, INTAKES, TODAY)
            self.assertEqual(ev["eligibility"], "ineligible", bad)
            self.assertTrue(any(r.startswith("Not eligible") for r in ev["reasons"]), bad)

    def test_missing_data_is_never_a_match(self):
        bare = {"_id": "student_y", "academic": {}, "preferences": {"countries": ["Germany"]}}
        ev = engine.evaluate(bare, course(), UNI, INTAKES, TODAY)
        self.assertEqual((ev["match_score"], ev["confidence"]), (100, 30))  # only the country is known
        self.assertEqual(ev["ranking_score"], 30)                           # ... so it ranks as 30, not 100
        self.assertEqual(ev["eligibility"], "insufficient_data")
        sources = {(m["source"], m["item"]) for m in ev["missing_data"]}
        self.assertIn(("profile", "CGPA and grading scale"), sources)
        self.assertIn(("profile", "Maximum budget"), sources)
        self.assertIn(("catalogue", "Course level"), sources)


class RecommendTests(SimpleTestCase):
    def catalogue(self):
        unis = {"university_001": UNI,
                "university_002": {"_id": "university_002", "name": "ETH Zurich", "country": "Switzerland", "rank": 7},
                "university_003": {"_id": "university_003", "name": "RWTH Aachen", "country": "Germany", "rank": 90}}
        courses = [
            course(_id="course_a", title="Robotics", **FULL),
            course(_id="course_b", title="Data Science", university_id="university_003"),
            course(_id="course_c", title="AI", university_id="university_002"),                  # other country, same area
            course(_id="course_d", title="Chemistry", cluster="Chemistry", university_id="university_002"),  # not in pool
            course(_id="course_e", title="Robotics PhD", level="PhD"),                           # ineligible
            course(_id="course_f", title="Old", is_active=False),
            course(_id="course_g", title="Vision", university_id="university_404"),              # unlinked
        ]
        return courses, unis

    def test_ranking_pool_exclusions_and_determinism(self):
        courses, unis = self.catalogue()
        result = engine.recommend(student(), courses, unis, INTAKES, TODAY)
        ids = [e["course_id"] for e in result["selected"]]
        self.assertEqual(ids[0], "course_a")
        self.assertNotIn("course_d", result["evaluations"])          # outside country and area
        self.assertNotIn("course_e", ids)                            # hard rule
        self.assertNotIn("course_f", result["evaluations"])          # inactive
        self.assertEqual(result["stats"]["ineligible"], 1)
        self.assertEqual(result["stats"]["ineligible_by_rule"], {"level": 1})
        self.assertEqual(result["stats"]["inactive_or_unlinked"], 2)
        self.assertTrue(all(e["eligibility"] != "ineligible" for e in result["selected"]))
        ranks = [e["ranking_score"] for e in result["selected"]]
        self.assertEqual(ranks, sorted(ranks, reverse=True))
        again = engine.recommend(student(), list(reversed(courses)), unis, INTAKES, TODAY)  # input order irrelevant
        self.assertEqual([(e["course_id"], e["ranking_score"]) for e in again["selected"]],
                         [(e["course_id"], e["ranking_score"]) for e in result["selected"]])

    def test_limits_threshold_and_per_university_cap(self):
        courses = [course(_id=f"course_{i:02d}", title=f"Course {i}") for i in range(5)]
        result = engine.recommend(student(), courses, {"university_001": UNI}, INTAKES, TODAY)
        self.assertEqual(len(result["selected"]), engine.PER_UNIVERSITY)
        self.assertEqual([e["course_id"] for e in result["selected"]], ["course_00", "course_01"])  # title tie-break
        none = engine.recommend(student(), courses, {"university_001": UNI}, INTAKES, TODAY, min_score=101)
        self.assertEqual(none["selected"], [])
        self.assertTrue(none["message"])

    def test_empty_catalogue_and_empty_profile(self):
        self.assertEqual(engine.recommend(student(), [], {}, INTAKES, TODAY)["selected"], [])
        res = engine.recommend({"preferences": {}, "academic": {}}, [course()], {"university_001": UNI}, INTAKES, TODAY)
        self.assertEqual(res["status"], "insufficient_profile")

    def test_fingerprint_tracks_relevant_inputs_only(self):
        base = engine.fingerprint(student(), INTAKES, TODAY)
        self.assertEqual(base, engine.fingerprint(student(), list(reversed(INTAKES)), TODAY))
        self.assertNotEqual(base, engine.fingerprint(student(countries=["Canada"]), INTAKES, TODAY))
        self.assertNotEqual(base, engine.fingerprint(student(cgpa=9.0), INTAKES, TODAY))
        self.assertNotEqual(base, engine.fingerprint(student(), INTAKES, date(2027, 1, 16)))  # Fall 2027 closed
        unrelated = student()
        unrelated["personal"] = {"phone": "123"}
        self.assertEqual(base, engine.fingerprint(unrelated, INTAKES, TODAY))
