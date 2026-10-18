"""
Rule-based recommendation engine (SRS 4.8). Pure functions: no database access, so each rule is unit
tested on its own and the same inputs always give the same scores and order.

For one student and one course the engine evaluates five weighted matching factors and four hard
eligibility rules.

Matching factors (soft; each scores m in [0, 1], or is "unknown" when data is missing on either side):
  country  - the university's country is one of the student's target countries (1) or not (0).
  course   - a preferred course area equals the course's subject cluster, directly or through
             AREA_ALIASES (1); appears in the course title (0.8); shares a significant word (0.5); else 0.
  academic - with a recorded minimum grade: how far the student's normalised grade clears it (0.7-1).
             Without one: the grade against a selectivity estimate from the university's world ranking
             (EXPECTED_GRADE), scored linearly over the 20 points below it. Reported as an estimate.
  intake   - the preferred intake is open and offered (1); only another intake is open (0.5).
  budget   - annual tuition within the student's maximum budget (1), up to 20% over (0.5), more (0).
             Compared only in the same currency: no exchange rates are stored, none are invented.

    match_score   = round(100 * sum(w_i * m_i) / sum(w_i))       over the factors with data (shown to people)
    confidence    = round(100 * sum(w_i with data) / sum(all w_i))
    ranking_score = round(100 * sum(w_i * m_i) / sum(all w_i))   (= match_score x confidence; used to rank)

An unknown factor is left out of match_score and lowers confidence instead, and the missing items are
listed in `missing_data`. Ranking and the MIN_SCORE threshold use ranking_score, which counts an unknown
factor as no match: a course is never ranked above another just because less is known about it.

Hard rules (pass / fail / unknown); a failure can never be outweighed by a high score:
  level   - the course's level, when recorded, equals the student's target degree level;
  grades  - the normalised grade is at least the course's recorded minimum (`eligibility.min_grade_pct`);
  english - the student's overall score is at least the course's minimum for that test;
  intake  - at least one intake the course is offered in is still open (deadline not passed).
eligibility = "ineligible" if any rule fails, else "insufficient_data" if any is unknown, else "eligible".
Ineligible courses are never recommended. Budget is a soft factor: the SRS says to *consider* it.

Ranking: ranking_score desc, match_score desc, world rank asc, university name, course title, course id.
At most PER_UNIVERSITY courses per university and LIMIT in total, each with ranking_score >= MIN_SCORE.
"""

import hashlib
import json
import re
from collections import Counter
from datetime import date

METHOD = "rule_based_v2"
DEFAULT_WEIGHTS = {"country": 30, "course": 30, "academic": 20, "intake": 10, "budget": 10}
FACTOR_LABELS = {"country": "Country", "course": "Course area", "academic": "Academic fit", "intake": "Intake",
                 "budget": "Budget"}
CHECK_LABELS = {"level": "Degree level", "grades": "Entry grade", "english": "English requirement", "intake": "Open intake"}
MIN_SCORE = 40
LIMIT = 15
PER_UNIVERSITY = 2
BUDGET_TOLERANCE = 0.20

# Typical minimum grade (percent of the scale) by world-ranking band: (best rank in band, grade).
EXPECTED_GRADE = ((25, 90.0), (50, 80.0), (100, 72.0))
FALLBACK_EXPECTED_GRADE = 65.0
ACADEMIC_SPREAD = 20.0

# Free-text course areas people type, mapped to the catalogue's subject clusters (compared lowercase).
AREA_ALIASES = {
    "computer science": "cs & ai", "cs": "cs & ai", "ai": "cs & ai", "ai/ml": "cs & ai", "ml": "cs & ai",
    "artificial intelligence": "cs & ai", "machine learning": "cs & ai", "data science": "cs & ai",
    "computing": "cs & ai", "bioinformatics": "computational biology & bioinformatics",
    "computational biology": "computational biology & bioinformatics", "physics": "physics & astronomy",
    "astronomy": "physics & astronomy", "astrophysics": "physics & astronomy", "maths": "mathematics",
    "math": "mathematics", "statistics": "mathematics", "earth science": "earth & environmental sciences",
    "environmental science": "earth & environmental sciences", "geology": "earth & environmental sciences",
}
STOPWORDS = {"and", "of", "the", "in", "for", "with", "a", "an", "to", "engineering", "science", "sciences",
             "studies", "programme", "program", "msc", "ms", "ma", "bsc", "phd", "mba"}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("–", "-").replace("—", "-")).strip().lower()


def _tokens(text) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", _norm(text)) if len(t) > 1 and t not in STOPWORDS}


def _num(value) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _factor(status: str, score: float | None, detail: str) -> dict:
    return {"status": status, "score": None if score is None else round(score, 3), "detail": detail}


def _check(status: str, detail: str) -> dict:
    return {"status": status, "detail": detail}


def grade_pct(academic: dict) -> float | None:
    """CGPA as a percentage of its scale (8.5/10 -> 85.0); None without both numbers."""
    cgpa, scale = _num((academic or {}).get("cgpa")), _num((academic or {}).get("gpa_scale"))
    if cgpa is None or not scale or scale <= 0:
        return None
    return max(0.0, min(100.0, 100.0 * cgpa / scale))


def expected_grade(rank) -> float | None:
    rank = _num(rank)
    if rank is None:
        return None
    for best, grade in EXPECTED_GRADE:
        if rank <= best:
            return grade
    return FALLBACK_EXPECTED_GRADE


def intake_is_open(intake: dict, today: date) -> bool:
    deadline = _date(intake.get("application_deadline"))
    if deadline is not None:
        return deadline >= today
    start = _date(intake.get("start_date"))
    return start is None or start > today


# ---------------------------------------------------------------------------
# Factors
# ---------------------------------------------------------------------------
def country_factor(countries: list[str], university: dict) -> dict:
    country = university.get("country") or ""
    if not countries:
        return _factor("unknown", None, "No target countries in the profile.")
    if country in countries:
        return _factor("match", 1.0, f"{country} is one of the target countries.")
    return _factor("no_match", 0.0, f"{country or 'This country'} is not a target country ({', '.join(countries)}).")


def course_factor(areas: list[str], course: dict) -> dict:
    if not areas:
        return _factor("unknown", None, "No preferred course areas in the profile.")
    cluster = _norm(course.get("cluster"))
    title = _norm(course.get("title"))
    canonical = _norm(course.get("canonical_name"))
    course_words = _tokens(course.get("title")) | _tokens(course.get("canonical_name")) | _tokens(course.get("cluster"))
    best = (0.0, "")
    for area in areas:
        a = _norm(area)
        if not a:
            continue
        if cluster and (a == cluster or AREA_ALIASES.get(a) == cluster):
            score, why = 1.0, f"'{area}' matches the subject area {course.get('cluster')}."
        elif (title and (a in title or title in a)) or (canonical and (a in canonical or canonical in a)):
            score, why = 0.8, f"'{area}' matches the course title."
        elif _tokens(a) & course_words:
            score, why = 0.5, f"'{area}' is related ({', '.join(sorted(_tokens(a) & course_words))})."
        else:
            continue
        if score > best[0]:
            best = (score, why)
    if best[0] == 0:
        return _factor("no_match", 0.0, f"Subject area {course.get('cluster') or 'unknown'} is outside the preferred areas.")
    return _factor("match" if best[0] >= 0.8 else "partial", best[0], best[1])


def academic_factor(academic: dict, course: dict, university: dict) -> tuple[dict, str | None]:
    """The academic factor and a Reach / Target / Safe tier (None when grades are unknown)."""
    pct = grade_pct(academic)
    if pct is None:
        return _factor("unknown", None, "CGPA and grading scale are not in the profile."), None
    minimum = _num((course.get("eligibility") or {}).get("min_grade_pct"))
    if minimum is not None:
        if pct < minimum:
            return _factor("no_match", 0.0, f"Grade {pct:.0f}% is below the course minimum of {minimum:.0f}%."), None
        score = min(1.0, 0.7 + 0.3 * (pct - minimum) / 10.0)
        tier = "Safe" if pct >= minimum + 10 else "Target"
        return _factor("match", score, f"Grade {pct:.0f}% meets the course minimum of {minimum:.0f}%."), tier
    target = expected_grade(university.get("rank"))
    if target is None:
        return _factor("unknown", None, "No grade requirement or world ranking is recorded for this course."), None
    score = max(0.0, min(1.0, (pct - (target - ACADEMIC_SPREAD)) / ACADEMIC_SPREAD))
    status = "match" if pct >= target else ("partial" if score > 0 else "no_match")
    tier = "Reach" if pct < target - 5 else ("Safe" if pct >= target + 8 else "Target")
    rank = university.get("rank")
    return _factor(status, score, f"Estimate: grade {pct:.0f}% against about {target:.0f}% typical for a "
                                  f"university ranked #{rank} (no published requirement)."), tier


def intake_factor(preferred: str, intakes: list[dict], course: dict, today: date) -> tuple[dict, dict, dict | None]:
    """(factor, hard check, intake to apply for or None)."""
    if not intakes:
        return (_factor("unknown", None, "No intakes are recorded."), _check("unknown", "No intakes are recorded."), None)
    offered_ids = course.get("intake_ids") or []
    offered = [i for i in intakes if not offered_ids or i.get("_id") in offered_ids]
    open_ = sorted((i for i in offered if intake_is_open(i, today)), key=lambda i: (i.get("start_date") or "", i.get("_id")))
    if not open_:
        why = "None of the intakes this course is offered in is open." if offered_ids else "No intake is open for applications."
        return _factor("no_match", 0.0, why), _check("fail", why), None
    check = _check("pass", f"{len(open_)} open intake{'' if len(open_) == 1 else 's'}.")
    by_name = {i.get("name"): i for i in intakes}
    if not preferred:
        return (_factor("unknown", None, f"No preferred intake in the profile; earliest open is {open_[0].get('name')}."),
                check, open_[0])
    pref = by_name.get(preferred)
    if pref is not None and pref in open_:
        return _factor("match", 1.0, f"{preferred} is open (deadline {pref.get('application_deadline')})."), check, pref
    if pref is None:
        why = f"{preferred} is not a recorded intake"
    elif pref not in offered:
        why = f"{preferred} is not offered for this course"
    else:
        why = f"{preferred} closed on {pref.get('application_deadline')}"
    return _factor("partial", 0.5, f"{why}; next open intake is {open_[0].get('name')}."), check, open_[0]


def budget_factor(budget: dict, course: dict) -> dict:
    budget = budget or {}
    tuition = course.get("tuition") or {}
    maximum = _num(budget.get("max"))
    amount = _num(tuition.get("amount_per_year"))
    if maximum is None:
        return _factor("unknown", None, "No maximum budget in the profile.")
    if amount is None:
        return _factor("unknown", None, "Tuition is not recorded for this course.")
    b_cur, t_cur = budget.get("currency") or "", tuition.get("currency") or ""
    if not b_cur or not t_cur or b_cur != t_cur:
        return _factor("unknown", None, f"Tuition is in {t_cur or 'an unknown currency'} and the budget in "
                                        f"{b_cur or 'an unknown currency'}; no exchange rate is stored.")
    if amount <= maximum:
        return _factor("match", 1.0, f"Tuition {amount:,.0f} {t_cur}/year is within the budget of {maximum:,.0f}.")
    over = (amount - maximum) / maximum if maximum else 1.0
    if over <= BUDGET_TOLERANCE:
        return _factor("partial", 0.5, f"Tuition {amount:,.0f} {t_cur}/year is {over:.0%} over the budget of {maximum:,.0f}.")
    return _factor("no_match", 0.0, f"Tuition {amount:,.0f} {t_cur}/year is well over the budget of {maximum:,.0f}.")


# ---------------------------------------------------------------------------
# Hard rules
# ---------------------------------------------------------------------------
def level_check(target_level: str, course: dict) -> dict:
    level = course.get("level") or ""
    if not level:
        return _check("unknown", "The course level is not recorded in the catalogue.")
    if not target_level:
        return _check("unknown", "No target degree level in the profile.")
    if _norm(level) == _norm(target_level):
        return _check("pass", f"{level} programme, as targeted.")
    return _check("fail", f"This is a {level} programme; the target is {target_level}.")


def grades_check(academic: dict, course: dict) -> dict:
    minimum = _num((course.get("eligibility") or {}).get("min_grade_pct"))
    if minimum is None:
        return _check("unknown", "No minimum grade is recorded for this course.")
    pct = grade_pct(academic)
    if pct is None:
        return _check("unknown", f"The course needs {minimum:.0f}%; CGPA and scale are not in the profile.")
    if pct < minimum:
        return _check("fail", f"Grade {pct:.0f}% is below the minimum of {minimum:.0f}%.")
    return _check("pass", f"Grade {pct:.0f}% meets the minimum of {minimum:.0f}%.")


def english_check(academic: dict, course: dict) -> dict:
    required = {k: _num(v) for k, v in ((course.get("eligibility") or {}).get("min_english") or {}).items() if _num(v) is not None}
    if not required:
        return _check("unknown", "No English requirement is recorded for this course.")
    test = (academic or {}).get("english_test") or {}
    kind, score = test.get("test_type") or "", _num(test.get("overall"))
    if not kind or score is None:
        return _check("unknown", "No English test score in the profile.")
    if kind not in required:
        return _check("unknown", f"The course lists {', '.join(sorted(required))}; a {kind} score cannot be compared.")
    if score < required[kind]:
        return _check("fail", f"{kind} {score:g} is below the required {required[kind]:g}.")
    return _check("pass", f"{kind} {score:g} meets the required {required[kind]:g}.")


# ---------------------------------------------------------------------------
# One course
# ---------------------------------------------------------------------------
def evaluate(student: dict, course: dict, university: dict, intakes: list[dict], today: date,
             weights: dict | None = None) -> dict:
    weights = weights or DEFAULT_WEIGHTS
    prefs = student.get("preferences") or {}
    academic = student.get("academic") or {}

    academic_f, tier = academic_factor(academic, course, university)
    intake_f, intake_c, intake = intake_factor(prefs.get("intake") or "", intakes, course, today)
    factors = {
        "country": country_factor(prefs.get("countries") or [], university),
        "course": course_factor(prefs.get("course_areas") or [], course),
        "academic": academic_f,
        "intake": intake_f,
        "budget": budget_factor(prefs.get("budget") or {}, course),
    }
    for key, f in factors.items():
        f["weight"] = weights.get(key, 0)
    checks = {
        "level": level_check(prefs.get("degree_level") or "", course),
        "grades": grades_check(academic, course),
        "english": english_check(academic, course),
        "intake": intake_c,
    }

    total = sum(f["weight"] for f in factors.values())
    known = [f for f in factors.values() if f["score"] is not None and f["weight"]]
    known_weight = sum(f["weight"] for f in known)
    earned = sum(f["weight"] * f["score"] for f in known)
    score = round(100 * earned / known_weight) if known_weight else 0
    confidence = round(100 * known_weight / total) if total else 0
    ranking_score = round(100 * earned / total) if total else 0

    statuses = {c["status"] for c in checks.values()}
    eligibility = "ineligible" if "fail" in statuses else ("insufficient_data" if "unknown" in statuses else "eligible")

    reasons = [f["detail"] for f in factors.values() if f["status"] in ("match", "partial")]
    reasons += [f["detail"] for f in factors.values() if f["status"] == "no_match"]
    reasons += [f"Not eligible - {CHECK_LABELS[k]}: {c['detail']}" for k, c in checks.items() if c["status"] == "fail"]
    if eligibility == "insufficient_data":
        reasons.append("Eligibility to confirm with the university: some entry requirements are not recorded.")

    return {
        "course_id": course["_id"],
        "university_id": university.get("_id") or course.get("university_id"),
        "intake_id": intake.get("_id") if intake else None,
        "method": METHOD,
        "match_score": score,
        "confidence": confidence,
        "ranking_score": ranking_score,
        "eligibility": eligibility,
        "tier": tier,
        "match_factors": factors,
        "checks": checks,
        "reasons": reasons,
        "missing_data": missing_data(factors, checks),
        "snapshot": {
            "university_name": university.get("name", ""), "country": university.get("country", ""),
            "world_rank": university.get("rank"), "course_title": course.get("title") or course.get("canonical_name", ""),
            "cluster": course.get("cluster", ""), "intake_name": intake.get("name") if intake else None,
            "intake_deadline": intake.get("application_deadline") if intake else None,
        },
    }


# What to add, and where, when a factor or rule could not be evaluated.
_MISSING = {
    ("country", "No target"): ("profile", "Target countries"),
    ("course", "No preferred"): ("profile", "Preferred course areas"),
    ("academic", "CGPA"): ("profile", "CGPA and grading scale"),
    ("academic", "No grade requirement"): ("catalogue", "Grade requirement or world ranking"),
    ("intake", "No preferred"): ("profile", "Preferred intake"),
    ("intake", "No intakes"): ("catalogue", "Intakes"),
    ("budget", "No maximum"): ("profile", "Maximum budget"),
    ("budget", "Tuition is not"): ("catalogue", "Tuition"),
    ("budget", "Tuition is in"): ("catalogue", "Tuition in the budget's currency"),
}
_MISSING_CHECKS = {
    ("level", "The course level"): ("catalogue", "Course level"),
    ("level", "No target"): ("profile", "Target degree level"),
    ("grades", "No minimum"): ("catalogue", "Minimum entry grade"),
    ("grades", "The course needs"): ("profile", "CGPA and grading scale"),
    ("english", "No English requirement"): ("catalogue", "English requirement"),
    ("english", "No English test"): ("profile", "English test score"),
    ("english", "The course lists"): ("profile", "A score for one of the listed English tests"),
}


def missing_data(factors: dict, checks: dict) -> list[dict]:
    out, seen = [], set()
    for table, items in ((_MISSING, factors), (_MISSING_CHECKS, checks)):
        for key, item in items.items():
            if item["status"] != "unknown":
                continue
            for (k, prefix), (source, label) in table.items():
                if k == key and item["detail"].startswith(prefix) and (source, label) not in seen:
                    seen.add((source, label))
                    out.append({"source": source, "item": label})
    return out


# ---------------------------------------------------------------------------
# Whole catalogue
# ---------------------------------------------------------------------------
def sort_key(ev: dict) -> tuple:
    snap = ev["snapshot"]
    rank = snap.get("world_rank")
    return (-ev["ranking_score"], -ev["match_score"], rank if isinstance(rank, (int, float)) else float("inf"),
            snap.get("university_name") or "", snap.get("course_title") or "", ev["course_id"])


def in_pool(student: dict, course: dict, university: dict) -> bool:
    """Candidates: courses in a target country, plus courses elsewhere whose subject clearly matches."""
    prefs = student.get("preferences") or {}
    if university.get("country") in (prefs.get("countries") or []):
        return True
    return (course_factor(prefs.get("course_areas") or [], course)["score"] or 0) >= 0.8


def recommend(student: dict, courses: list[dict], universities: dict, intakes: list[dict], today: date, *,
              weights: dict | None = None, limit: int = LIMIT, min_score: int = MIN_SCORE,
              per_university: int = PER_UNIVERSITY) -> dict:
    """Evaluate the catalogue for one student. Returns {status, message, selected, evaluations, stats}."""
    prefs = student.get("preferences") or {}
    stats = Counter(catalogue_courses=len(courses))
    if not (prefs.get("countries") or prefs.get("course_areas")):
        return {"status": "insufficient_profile", "selected": [], "evaluations": {}, "stats": dict(stats),
                "message": "Add target countries or preferred course areas to the profile to get recommendations."}

    evaluations = {}
    for course in courses:
        university = universities.get(course.get("university_id"))
        if university is None or course.get("is_active") is False or university.get("is_active") is False:
            stats["inactive_or_unlinked"] += 1
            continue
        if in_pool(student, course, university):
            evaluations[course["_id"]] = evaluate(student, course, university, intakes, today, weights)

    excluded_by_rule = Counter()
    for ev in evaluations.values():
        stats[ev["eligibility"]] += 1
        for key, check in ev["checks"].items():
            if check["status"] == "fail":
                excluded_by_rule[key] += 1

    selected, per_uni = [], Counter()
    for ev in sorted((e for e in evaluations.values() if e["eligibility"] != "ineligible"), key=sort_key):
        if ev["ranking_score"] < min_score:
            stats["below_threshold"] += 1
            continue
        if per_uni[ev["university_id"]] >= per_university:
            continue
        selected.append(ev)
        per_uni[ev["university_id"]] += 1
        if len(selected) >= limit:
            break
    stats.update(evaluated=len(evaluations), recommended=len(selected))
    return {"status": "ok", "message": "" if selected else "No course in the catalogue matches the profile well enough yet.",
            "selected": selected, "evaluations": evaluations,
            "stats": {**{k: stats.get(k, 0) for k in ("catalogue_courses", "evaluated", "eligible", "insufficient_data",
                                                        "ineligible", "below_threshold", "recommended", "inactive_or_unlinked")},
                      "ineligible_by_rule": dict(excluded_by_rule)}}


def fingerprint(student: dict, intakes: list[dict], today: date, *, weights: dict | None = None) -> str:
    """Hash of every input that can change the result; a run whose hash differs is stale."""
    prefs = student.get("preferences") or {}
    academic = student.get("academic") or {}
    test = academic.get("english_test") or {}
    payload = {
        "method": METHOD, "weights": weights or DEFAULT_WEIGHTS, "limits": [MIN_SCORE, LIMIT, PER_UNIVERSITY],
        "academic": [academic.get("cgpa"), academic.get("gpa_scale"), test.get("test_type"), test.get("overall")],
        "preferences": [prefs.get("countries"), prefs.get("course_areas"), prefs.get("degree_level"),
                        prefs.get("intake"), prefs.get("budget")],
        "intakes": sorted([i.get("_id"), i.get("name"), i.get("application_deadline"), i.get("start_date"),
                           intake_is_open(i, today)] for i in intakes),
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
