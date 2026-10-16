"""
Database maintenance: full JSON backups and the one-off purge of demo/seed data.

"Real" data is what people entered through the running application:
  * `user` documents written by this codebase (they carry `token_version`)
    whose email is not a seed_demo address (`@aec.demo`);
  * the student/counsellor profiles those users link to via `profile_id`;
  * catalogue data (`university`, `course`);
  * audit entries performed by, or about, the kept records;
  * workflow documents (applications, documents, sessions, ...) that belong to
    a kept student or user - since Sprint 2 people create these through the app;
  * the intentional sample dataset (`"source": "seed"`, see seeding.py), which
    has its own removal command (`seed_dataset --remove`).
Everything else of a people/workflow type is demo data and is removed.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from . import repository
from .db import get_db

DEMO_EMAIL_SUFFIX = "@aec.demo"
PEOPLE_TYPES = {"user", "student", "counsellor"}
CATALOGUE_TYPES = {"university", "course"}
WORKFLOW_TYPES = {"application", "document", "counselling_session", "application_history",
                  "recommendation", "notification"}
# How a workflow document points at its owner: kept when that owner is kept. Ordered so an
# application is decided before its history entries.
WORKFLOW_OWNER = [
    ("application", "student_id"), ("document", "student_id"), ("counselling_session", "student_id"),
    ("recommendation", "student_id"), ("application_history", "application_id"),
    ("notification", "recipient_user_id"),
]
# Mango indexes left behind by earlier seed scripts (`doc_type`-based or test leftovers).
JUNK_INDEXES = {"foo-json-index", "doctype_status_idx", "idx_doctype_counsellor", "idx_doctype_student"}
BACKUP_DIR = settings.REPO_ROOT / "output" / "backups"


def all_docs(include_design: bool = False) -> list[dict]:
    rows = get_db().view("_all_docs", include_docs=True)
    return [dict(r.doc) for r in rows if include_design or not r.id.startswith("_design/")]


def backup(directory: Path = BACKUP_DIR) -> Path:
    """Write every document (design docs included) to a timestamped JSON file and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{settings.COUCHDB_NAME}-{stamp}.json"
    path.write_text(json.dumps(all_docs(include_design=True), indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def describe(doc: dict) -> str:
    """Human-readable label for reports."""
    t = doc.get("type") or doc.get("doc_type")
    if t == "user":
        return f"{doc.get('email')} ({doc.get('role')})"
    if t == "student":
        p = doc.get("personal") or doc.get("personal_details") or {}
        name = p.get("name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        return name or "(no name)"
    if t == "counsellor":
        return doc.get("name") or "(no name)"
    return ""


@dataclass
class PurgePlan:
    keep: list[dict] = field(default_factory=list)
    delete: list[dict] = field(default_factory=list)
    orphaned_students: list[dict] = field(default_factory=list)  # kept students whose counsellor is deleted
    unknown: list[dict] = field(default_factory=list)            # types we don't recognise: left untouched


def plan_purge(docs: list[dict]) -> PurgePlan:
    plan = PurgePlan()
    users = [d for d in docs if d.get("type") == "user"]
    kept_users = {u["_id"] for u in users
                  if "token_version" in u and not (u.get("email") or "").lower().endswith(DEMO_EMAIL_SUFFIX)}
    kept_profiles = {u.get("profile_id") for u in users if u["_id"] in kept_users and u.get("profile_id")}

    kept_ids: set[str] = set()
    pending_audit = []
    pending_workflow: dict[str, list[dict]] = {}
    for d in docs:
        t = d.get("type")
        if d.get("source") == "seed":
            plan.keep.append(d)
            kept_ids.add(d["_id"])
            continue
        if t == "user":
            keep = d["_id"] in kept_users
        elif t in ("student", "counsellor"):
            keep = d["_id"] in kept_profiles and d.get("user_id") in kept_users
        elif t in CATALOGUE_TYPES:
            keep = True
        elif t in WORKFLOW_TYPES:
            pending_workflow.setdefault(t, []).append(d)
            continue
        elif t is None and d.get("doc_type"):
            keep = False
        elif t == "audit_log":
            pending_audit.append(d)
            continue
        else:
            plan.unknown.append(d)
            continue
        (plan.keep if keep else plan.delete).append(d)
        if keep:
            kept_ids.add(d["_id"])

    for t, owner_field in WORKFLOW_OWNER:
        for d in pending_workflow.get(t, []):
            keep = d.get(owner_field) in kept_ids or d.get(owner_field) in kept_users
            (plan.keep if keep else plan.delete).append(d)
            if keep:
                kept_ids.add(d["_id"])

    for a in pending_audit:
        keep = a.get("actor_id") in kept_users or a.get("target_id") in kept_ids
        (plan.keep if keep else plan.delete).append(a)

    kept_counsellors = {d["_id"] for d in plan.keep if d.get("type") == "counsellor"}
    plan.orphaned_students = [d for d in plan.keep if d.get("type") == "student"
                              and d.get("counsellor_id") and d["counsellor_id"] not in kept_counsellors]
    return plan


def apply_purge(plan: PurgePlan, reassign_to: str | None = None) -> dict:
    """Reassign orphans, delete demo docs, rebuild counsellor lists, drop junk indexes. Returns counts."""
    from apps.students import services as student_services  # local import: students depends on core

    if reassign_to:
        target = repository.get(reassign_to, "counsellor")
        if target is None or target["_id"] not in {d["_id"] for d in plan.keep}:
            raise ValueError(f"{reassign_to} is not a counsellor that will be kept.")

    for s in plan.orphaned_students:
        student = repository.get(s["_id"], "student")
        student_services.assign_counsellor(student, reassign_to, actor=None)

    deleted = 0
    for d in plan.delete:
        current = get_db().get(d["_id"])  # fresh _rev: reassignment may have touched it
        if current is not None:
            repository.delete(dict(current))
            deleted += 1

    reconciled = 0
    students = repository.find({"type": "student"}, fields=["_id", "counsellor_id"])
    for c in repository.find({"type": "counsellor"}):
        actual = sorted(s["_id"] for s in students if s.get("counsellor_id") == c["_id"])
        if sorted(c.get("assigned_student_ids", [])) != actual:
            c["assigned_student_ids"] = actual
            c["updated_at"] = repository.now_iso()
            repository.save(c)
            reconciled += 1

    return {"deleted": deleted, "reassigned": len(plan.orphaned_students), "reconciled": reconciled,
            "indexes_dropped": drop_junk_indexes()}


def drop_junk_indexes() -> list[str]:
    db = get_db()
    if not hasattr(db, "resource"):  # in-memory test database has no HTTP resource
        return []
    _, _, data = db.resource.get_json("_index")
    dropped = []
    indexes = db.index()
    for idx in data.get("indexes", []):
        if idx.get("name") in JUNK_INDEXES and idx.get("ddoc"):
            del indexes[idx["ddoc"].removeprefix("_design/"), idx["name"]]
            dropped.append(idx["name"])
    return dropped

