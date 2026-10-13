"""
Audit trail for security-relevant actions (SRS 5.3): login failures, account
changes, counsellor assignments... Stored as `audit_log` documents.
Audit failures are logged but never break the user-facing request.
"""

import logging

from . import repository

logger = logging.getLogger("aec.audit")


def client_ip(request) -> str | None:
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def record(action: str, *, request=None, actor=None, target_id: str | None = None, details: dict | None = None):
    actor_id = getattr(actor, "id", None) if actor is not None else None
    entry = {
        "_id": repository.new_id("audit_log"),
        "type": "audit_log",
        "action": action,
        "actor_id": actor_id,
        "actor_role": getattr(actor, "role", None) if actor is not None else None,
        "target_id": target_id,
        "details": details or {},
        "ip": client_ip(request),
        "timestamp": repository.now_iso(),
    }
    logger.info("%s actor=%s target=%s details=%s", action, actor_id, target_id, details or {})
    try:
        repository.save(entry)
    except Exception:  # noqa: BLE001 - auditing must never break the request
        logger.exception("Could not persist audit entry %s", action)
