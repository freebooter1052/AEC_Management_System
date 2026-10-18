"""
`course` master data maintained by administrators (SRS 4.4). The imported catalogue has only a title,
canonical name and subject cluster; these optional fields let an admin record what a university
publishes, and the recommendation engine uses them as soon as they exist:

    "level": "Masters" | "" , "duration_months": 24 | null,
    "tuition": {"amount_per_year": 18000, "currency": "EUR"} | {},
    "eligibility": {"min_grade_pct": 75.0, "min_english": {"IELTS": 6.5, "TOEFL": 90}, "notes": ""} | {},
    "intake_ids": ["intake_fall_2027"],     # empty = offered in every agency intake
    "is_active": true,                      # false = no longer offered (hidden from search, not recommended)
    "updated_at": "..."
"""

from apps.core import audit, repository

EDITABLE = ("title", "canonical_name", "cluster", "level", "duration_months", "tuition", "eligibility", "intake_ids",
            "is_active")


def _clean(changes: dict) -> dict:
    out = {k: v for k, v in changes.items() if k in EDITABLE}
    for key in ("canonical_name", "cluster"):
        if key in out:
            out[key] = out[key].strip()
    if "eligibility" in out:
        out["eligibility"] = {"min_grade_pct": out["eligibility"].get("min_grade_pct"),
                              "min_english": out["eligibility"].get("min_english") or {},
                              "notes": (out["eligibility"].get("notes") or "").strip()}
    return out


def update_course(course: dict, changes: dict, *, actor, request=None) -> dict:
    fields = _clean(changes)
    course.update(fields)
    course["updated_at"] = repository.now_iso()
    repository.save(course)  # stale `rev` -> 409
    audit.record("course.updated", request=request, actor=actor, target_id=course["_id"],
                 details={"fields": sorted(fields)})
    return course


def create_course(university: dict, data: dict, *, actor, request=None) -> dict:
    now = repository.now_iso()
    course = {"_id": repository.new_id("course"), "type": "course", "university_id": university["_id"],
              "title": "", "canonical_name": "", "cluster": "", "is_active": True, "created_at": now, "updated_at": now,
              **_clean(data)}
    repository.save(course)
    audit.record("course.created", request=request, actor=actor, target_id=course["_id"],
                 details={"university_id": university["_id"], "title": course["title"]})
    return course


def active_clause() -> dict:
    """Mango clause for courses still offered (imported courses have no `is_active` field)."""
    return {"$or": [{"is_active": {"$exists": False}}, {"is_active": True}]}
