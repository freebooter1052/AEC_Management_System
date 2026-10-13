"""Core package."""
from .couchdb_client import get_couch_db, get_couch_server

__all__ = ["get_couch_db", "get_couch_server"]
