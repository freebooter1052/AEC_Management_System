"""
`recommendation` and `recommendation_run` documents (SRS 4.8, 6.1). Scoring rules live in engine.py.

    {
      "_id": "recommendation_<12 hex of sha1(student_id|course_id)>", "type": "recommendation",
      "student_id": "student_...", "university_id": "university_042", "course_id": "course_0536",
      "intake_id": "intake_fall_2027" | null,       # the intake the engine suggests applying for
      "origin": "engine" | "counsellor", "method": "rule_based_v2",
      "match_score": 0-100, "confidence": 0-100, "ranking_score": 0-100,
      "eligibility": "eligible" | "insufficient_data" | "ineligible",
      "tier": "Reach" | "Target" | "Safe" | null, "tier_set_by": null | "counsellor_...",
      "match_factors": {"country": {"status", "score", "weight", "detail"}, "course": {...}, "academic": {...},
                        "intake": {...}, "budget": {...}},
      "checks": {"level": {"status", "detail"}, "grades": {...}, "english": {...}, "intake": {...}},
      "reasons": ["..."], "missing_data": [{"source": "profile" | "catalogue", "item": "..."}],
      "snapshot": {"university_name", "country", "world_rank", "course_title", "cluster", "intake_name", "intake_deadline"},
      "status": "Suggested" | "Accepted" | "Rejected", "remarks": "",
      "in_latest_run": true, "rank_position": 1, "generated_at": "...", "inputs_hash": "...",
      "created_by": "user_..." | "counsellor_...", "created_at": "...", "updated_at": "..."
    }

    {"_id": "recommendation_run_<12 hex of sha1(student_id)>", "type": "recommendation_run",
     "student_id": "...", "method": "rule_based_v2", "weights": {...}, "status": "ok" | "insufficient_profile",
     "message": "", "stats": {...counts...}, "recommended_ids": [...], "inputs_hash": "...",
     "generated_at": "...", "generated_by": "user_...", "created_at": "...", "updated_at": "..."}

Refresh strategy (`generate`): the top results are upserted under their deterministic id (a repeated
or concurrent refresh updates, never duplicates). Engine suggestions that drop out of the results and
were never decided are deleted; Accepted/Rejected decisions and counsellor additions are kept and
re-scored against current data, with `in_latest_run: false`. A run is stale when its input hash no
longer matches the student's profile and the intakes, or a course was edited after it ran.

Seed documents from `seed_dataset` use the older `rule_based_v1` shape; `serialize` reads both, and a
refresh upgrades them in place (keeping their status and seed tag).
"""

import logging
import time

from couchdb.http import ResourceConflict
from django.conf import settings
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.core import audit, lookups, repository
from apps.core.db import get_db
from apps.core.roles import ADMIN, COUNSELLOR
from apps.students import services as student_services

from . import engine

logger = logging.getLogger("aec.recommendations")

COURSE_FIELDS = ["_id", "university_id", "title", "canonical_name", "cluster", "level", "duration_months", "tuition",
                 "eligibility", "intake_ids", "is_active", "updated_at"]
UNIVERSITY_FIELDS = ["_id", "name", "country", "rank", "is_active"]
ENGINE_FIELDS = ("university_id", "course_id", "intake_id", "method", "match_score", "confidence", "ranking_score",
                 "eligibility",
                 "match_factors", "checks", "reasons", "missing_data", "snapshot")
STATUS_ORDER = {"Accepted": 0, "Suggested": 1, "Rejected": 2}
MAX_PER_STUDENT = 500   # a student never has more; keeps every per-student query bounded
SAVE_RETRIES = 3
CATALOGUE_TTL = 60      # seconds a cached catalogue may be reused even when its version looks unchanged
_catalogue_cache: dict = {}


def weights() -> dict:
    configured = getattr(settings, "RECOMMENDATION_WEIGHTS", None) or {}
    return {**engine.DEFAULT_WEIGHTS, **{k: v for k, v in configured.items() if k in engine.DEFAULT_WEIGHTS}}


def recommendation_id(student_id: str, course_id: str) -> str:
    return repository.stable_id("recommendation", student_id, course_id)


def run_id(student_id: str) -> str:
    return repository.stable_id("recommendation_run", student_id)


def catalogue_version() -> tuple:
    """Changes whenever a course or university is added or removed, or a course is edited (two cheap reads)."""
    counts = {r.key[0]: r.value for r in repository.view("by_type", group_level=1)}
    latest = repository.find({"type": "course", "updated_at": {"$gt": None}}, fields=["updated_at"],
                             sort=[{"type": "desc"}, {"updated_at": "desc"}], limit=1)
    return (id(get_db()), counts.get("course", 0), counts.get("university", 0),
            latest[0]["updated_at"] if latest else None)


def load_catalogue() -> tuple[dict, list[dict], list[dict]]:
    """
    Universities by id, courses and intakes, projected to the fields the engine reads. The courses and
    universities (1,358 documents, ~290 ms to load) are cached in this process until `catalogue_version`
    changes or CATALOGUE_TTL seconds pass (the TTL covers a second edit within the same one-second
    timestamp). Intakes are always read fresh: their open/closed state is part of every result.
    """
    version = catalogue_version()
    cached = _catalogue_cache.get("entry")
    if cached is None or cached[0] != version or time.monotonic() - cached[1] > CATALOGUE_TTL:
        universities = {u["_id"]: u for u in repository.find({"type": "university"}, fields=UNIVERSITY_FIELDS)}
        courses = repository.find({"type": "course"}, fields=COURSE_FIELDS)
        cached = (version, time.monotonic(), universities, courses)
        _catalogue_cache["entry"] = cached
    intakes = repository.find({"type": "intake"})
    return cached[2], cached[3], intakes


def is_engine_doc(doc: dict) -> bool:
    return doc.get("origin", "engine") == "engine" and str(doc.get("method", "")).startswith("rule_based")


# ---------------------------------------------------------------------------
# Access (through the owning student, like every workflow record)
# ---------------------------------------------------------------------------
def get_accessible(user, recommendation_id_: str) -> dict:
    doc = repository.get(recommendation_id_, "recommendation")
    if doc is None:
        raise NotFound("Recommendation not found.")
    student = repository.get(doc.get("student_id"), "student")
    if user.role != ADMIN and (student is None or not student_services.can_access(user, student)):
        raise PermissionDenied("You do not have access to this recommendation.")
    return doc


def actor_ref(actor) -> str | None:
    """Who created a record: the counsellor profile for counsellors (as `verified_by` on documents), else the user."""
    if actor is None:
        return None
    return actor.profile_id if actor.role == COUNSELLOR else actor.id


# ---------------------------------------------------------------------------
# Generate / refresh
# ---------------------------------------------------------------------------
def _apply(doc: dict, ev: dict, *, now: str, inputs_hash: str, in_latest_run: bool, position: int | None) -> dict:
    for key in ENGINE_FIELDS:
        doc[key] = ev[key]
    if not doc.get("tier_set_by"):
        doc["tier"] = ev["tier"]
    doc.update(in_latest_run=in_latest_run, rank_position=position, generated_at=now, inputs_hash=inputs_hash,
               updated_at=now)
    doc.pop("unavailable", None)
    return doc


def _new_doc(student: dict, ev: dict, *, origin: str, status: str, actor, now: str, remarks: str = "") -> dict:
    return {"_id": recommendation_id(student["_id"], ev["course_id"]), "type": "recommendation",
            "student_id": student["_id"], "origin": origin, "status": status, "remarks": remarks,
            "tier": None, "tier_set_by": None, "created_by": actor_ref(actor), "created_at": now}


def _save_retrying(doc_id: str, rebuild) -> dict | None:
    """Save `rebuild(current_doc_or_None)`; on a revision conflict re-read and rebuild (bounded)."""
    for attempt in range(SAVE_RETRIES):
        doc = rebuild(repository.get(doc_id))
        if doc is None:
            return None
        try:
            return repository.save(doc)
        except ResourceConflict:
            if attempt == SAVE_RETRIES - 1:
                raise
    return None


def generate(student: dict, *, actor, request=None) -> dict:
    """Run the engine for one student, persist the results and the run summary; returns the run document."""
    universities, courses, intakes = load_catalogue()
    today = repository.today()
    w = weights()
    result = engine.recommend(student, courses, universities, intakes, today, weights=w)
    inputs_hash = engine.fingerprint(student, intakes, today, weights=w)
    now = repository.now_iso()
    course_map = {c["_id"]: c for c in courses}

    existing = repository.find({"type": "recommendation", "student_id": student["_id"]}, limit=MAX_PER_STUDENT)
    by_course = {d.get("course_id"): d for d in existing}
    planned: list[tuple[dict, dict | None, bool, int | None]] = []  # (doc, evaluation, in_latest_run, position)
    selected_ids = set()
    for position, ev in enumerate(result["selected"], 1):
        selected_ids.add(ev["course_id"])
        doc = by_course.get(ev["course_id"]) or _new_doc(student, ev, origin="engine", status="Suggested",
                                                         actor=actor, now=now)
        planned.append((_apply(doc, ev, now=now, inputs_hash=inputs_hash, in_latest_run=True, position=position),
                        ev, True, position))

    to_delete = []
    for doc in existing:
        if doc.get("course_id") in selected_ids:
            continue
        if is_engine_doc(doc) and doc.get("status") == "Suggested":
            to_delete.append(doc)  # dropped out of the results and nobody decided on it
            continue
        course = course_map.get(doc.get("course_id"))
        university = universities.get((course or {}).get("university_id"))
        ev = result["evaluations"].get(doc.get("course_id"))
        if ev is None and course is not None and university is not None:
            ev = engine.evaluate(student, course, university, intakes, today, w)
        if ev is None:
            doc.update(in_latest_run=False, unavailable=True, updated_at=now)
        else:
            _apply(doc, ev, now=now, inputs_hash=inputs_hash, in_latest_run=False, position=None)
        planned.append((doc, ev, False, None))

    # One _bulk_docs request; each document succeeds or fails on its own. A failed one (someone edited it
    # meanwhile) is re-read and the engine fields re-applied, which keeps that person's status and remarks.
    saved_ids = []
    for (ok, doc_id, error), (doc, ev, latest, position) in zip(repository.bulk_save([p[0] for p in planned]), planned):
        if not ok:
            if not isinstance(error, ResourceConflict):
                raise error if isinstance(error, Exception) else RuntimeError(str(error))

            def rebuild(current, ev=ev, doc=doc, latest=latest, position=position):
                if current is None:
                    if doc.get("_rev"):
                        return None  # it existed and was deleted meanwhile (e.g. with its student): don't revive it
                    current = {k: v for k, v in doc.items() if k != "_rev"}
                if ev is None:
                    current.update(in_latest_run=False, unavailable=True, updated_at=now)
                    return current
                return _apply(current, ev, now=now, inputs_hash=inputs_hash, in_latest_run=latest, position=position)

            _save_retrying(doc_id, rebuild)
        if latest:
            saved_ids.append(doc_id)
    for doc in to_delete:
        try:
            repository.delete(doc)
        except ResourceConflict:
            logger.info("Kept recommendation %s: it was changed while refreshing", doc["_id"])

    rid = run_id(student["_id"])

    def build_run(current):
        run = current or {"_id": rid, "type": "recommendation_run", "student_id": student["_id"], "created_at": now}
        run.update(method=engine.METHOD, weights=w, min_score=engine.MIN_SCORE, limit=engine.LIMIT,
                   status=result["status"], message=result["message"], stats=result["stats"],
                   recommended_ids=saved_ids, inputs_hash=inputs_hash, generated_at=now,
                   generated_by=getattr(actor, "id", None), updated_at=now)
        return run

    run = _save_retrying(rid, build_run)
    audit.record("recommendations.generated", request=request, actor=actor, target_id=student["_id"],
                 details={"recommended": len(saved_ids), "evaluated": result["stats"].get("evaluated", 0)})
    return run


def freshness(student: dict, run: dict | None) -> dict:
    """Whether the stored recommendations still reflect the student's profile, the intakes and the catalogue."""
    if run is None:
        return {"state": "never", "reasons": []}
    reasons = []
    intakes = repository.find({"type": "intake"})
    if run.get("inputs_hash") != engine.fingerprint(student, intakes, repository.today(), weights=weights()):
        reasons.append("The profile or the intake dates changed after these were generated.")
    # >= : timestamps have one-second resolution, and a false "stale" only costs a refresh, a missed edit is worse.
    if repository.find({"type": "course", "updated_at": {"$gte": run.get("generated_at") or ""}}, fields=["_id"], limit=1):
        reasons.append("The course catalogue was updated after these were generated.")
    return {"state": "stale" if reasons else "current", "reasons": reasons}


def run_summary(student: dict) -> tuple[dict | None, dict]:
    run = repository.get(run_id(student["_id"]), "recommendation_run")
    data = None
    if run is not None:
        data = {k: run.get(k) for k in ("status", "message", "stats", "method", "generated_at", "weights", "min_score", "limit")}
        data["generated_by_name"] = lookups.names_by_id([run.get("generated_by")]).get(run.get("generated_by"), "")
    return data, freshness(student, run)


# ---------------------------------------------------------------------------
# Counsellor review: accept, reject, modify, add (SRS 4.8)
# ---------------------------------------------------------------------------
def _evaluate_one(student: dict, course_id: str) -> tuple[dict, dict]:
    course = repository.get(course_id, "course")
    if course is None or course.get("is_active") is False:
        raise ValidationError({"course_id": ["Course not found in the catalogue (or no longer offered)."]})
    university = repository.get(course.get("university_id"), "university")
    if university is None or university.get("is_active") is False:
        raise ValidationError({"course_id": ["This course is not linked to an active university."]})
    intakes = repository.find({"type": "intake"})
    return course, engine.evaluate(student, course, university, intakes, repository.today(), weights())


def _ineligible_message(ev: dict) -> str:
    fails = [f"{engine.CHECK_LABELS[k]}: {c['detail']}" for k, c in ev["checks"].items() if c["status"] == "fail"]
    return "This course fails a hard eligibility rule - " + " ".join(fails)


def add(student: dict, course_id: str, *, remarks: str = "", actor, request=None) -> dict:
    """A counsellor recommends a specific course. Scored like any other; refused if a hard rule fails."""
    if repository.find_one({"type": "recommendation", "student_id": student["_id"], "course_id": course_id}):
        raise ValidationError({"course_id": ["This course is already in the student's recommendations."]})
    _, ev = _evaluate_one(student, course_id)
    if ev["eligibility"] == "ineligible":
        raise ValidationError({"course_id": [_ineligible_message(ev)]})
    now = repository.now_iso()
    doc = _new_doc(student, ev, origin="counsellor", status="Accepted", actor=actor, now=now, remarks=remarks.strip())
    _apply(doc, ev, now=now, inputs_hash="", in_latest_run=False, position=None)
    try:
        repository.save(doc)
    except ResourceConflict:
        raise ValidationError({"course_id": ["This course is already in the student's recommendations."]}) from None
    audit.record("recommendation.added", request=request, actor=actor, target_id=doc["_id"],
                 details={"student_id": student["_id"], "course_id": course_id})
    return doc


def update(doc: dict, changes: dict, *, actor, request=None) -> dict:
    """Accept / reject / reset, remarks, tier. A course that fails a hard rule cannot be accepted."""
    if changes.get("status") == "Accepted" and doc.get("eligibility") == "ineligible":
        raise ValidationError({"status": [_ineligible_message(doc)] if doc.get("checks") else
                               ["This course fails a hard eligibility rule and cannot be accepted."]})
    if "status" in changes:
        doc["status"] = changes["status"]
    if "remarks" in changes:
        doc["remarks"] = changes["remarks"].strip()
    if "tier" in changes:
        doc["tier"] = changes["tier"] or None
        doc["tier_set_by"] = actor_ref(actor) if changes["tier"] else None
    doc["updated_at"] = repository.now_iso()
    doc["reviewed_by"] = actor_ref(actor)
    repository.save(doc)  # stale `rev` -> 409
    audit.record("recommendation.updated", request=request, actor=actor, target_id=doc["_id"],
                 details={k: changes[k] for k in ("status", "tier") if k in changes})
    return doc


# ---------------------------------------------------------------------------
# Representation
# ---------------------------------------------------------------------------
_V1_FACTORS = (("country", "country_match"), ("course", "course_match"), ("academic", "academic_fit"),
               ("intake", "intake_available"), ("budget", "budget_fit"))


def factor_list(doc: dict) -> list[dict]:
    """Matching factors as rows for display, from the current shape or the seed's rule_based_v1 shape."""
    factors = doc.get("match_factors") or {}
    rows = []
    if any(isinstance(v, dict) for v in factors.values()):
        for key, label in engine.FACTOR_LABELS.items():
            f = factors.get(key) or {}
            rows.append({"key": key, "label": label, "status": f.get("status", "unknown"), "score": f.get("score"),
                         "weight": f.get("weight"), "detail": f.get("detail", "")})
        return rows
    for key, old in _V1_FACTORS:
        value = factors.get(old)
        if value is None:
            status, score = "unknown", None
        elif isinstance(value, bool):
            status, score = ("match", 1.0) if value else ("no_match", 0.0)
        else:
            score = max(0.0, min(1.0, float(value) / 25.0))
            status = "match" if score >= 0.8 else ("partial" if score > 0 else "no_match")
        rows.append({"key": key, "label": engine.FACTOR_LABELS[key], "status": status, "score": score, "weight": None,
                     "detail": ""})
    return rows


def serialize_page(docs: list[dict]) -> list[dict]:
    names = lookups.names_by_id([d.get("created_by") for d in docs] + [d.get("reviewed_by") for d in docs])
    out = []
    for d in docs:
        data = repository.public(d)
        data.pop("source", None)
        data.pop("inputs_hash", None)
        for key, default in (("origin", "engine"), ("eligibility", None), ("confidence", None),
                             ("ranking_score", d.get("match_score")), ("checks", {}),
                             ("missing_data", []), ("in_latest_run", None), ("intake_id", None)):
            data.setdefault(key, default)
        data["factors"] = factor_list(d)
        data["created_by_name"] = names.get(d.get("created_by"), "")
        data["reviewed_by_name"] = names.get(d.get("reviewed_by")) if d.get("reviewed_by") else None
        out.append(data)
    return out


def sort_key(doc: dict) -> tuple:
    snap = doc.get("snapshot") or {}
    rank = snap.get("world_rank")
    ranking = doc.get("ranking_score", doc.get("match_score")) or 0  # seed v1 docs have only match_score
    return (STATUS_ORDER.get(doc.get("status"), 3), -ranking, -(doc.get("match_score") or 0),
            rank if isinstance(rank, (int, float)) else float("inf"), snap.get("university_name") or "",
            snap.get("course_title") or "", doc["_id"])


def for_student(student_id: str, status: str = "") -> list[dict]:
    selector = {"type": "recommendation", "student_id": student_id}
    if status:
        selector["status"] = status
    return sorted(repository.find(selector, limit=MAX_PER_STUDENT), key=sort_key)
