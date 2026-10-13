"""
Process-wide CouchDB database handle.

`get_db()` lazily opens (and caches) the database configured in settings.
Tests replace it with an in-memory fake via `set_db()`.
"""

import threading

from .couchdb_client import get_couch_db

_lock = threading.Lock()
_db = None


def get_db():
    global _db
    if _db is None:
        with _lock:
            if _db is None:
                _db = get_couch_db()
    return _db


def set_db(db):
    """Override the database handle (used by tests). Pass None to reset."""
    global _db
    _db = db
