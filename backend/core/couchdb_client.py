"""
couchdb_client.py
-----------------
CouchDB client wrapper for the AEC Management System.

Reads connection settings from the project's .env file (or Django settings
if Django is available). Call `get_couch_db()` anywhere in the project to
obtain a ready-to-use CouchDB database handle.

Supported .env / Django settings keys:
    COUCHDB_URL      - CouchDB server URL  (default: http://127.0.0.1:5984/)
    COUCHDB_USER     - Admin username       (default: admin)
    COUCHDB_PASSWORD - Admin password       (default: adminpassword)
    COUCHDB_NAME     - Target database name (default: counselling_db)
"""

import os
import pathlib
import couchdb


def _load_env_file() -> dict:
    """Parse the nearest .env file and return its key-value pairs."""
    env_vars: dict = {}
    search_dir = pathlib.Path(__file__).resolve().parent
    for _ in range(5):
        env_path = search_dir / ".env"
        if env_path.exists():
            with open(env_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    env_vars[key] = value
            break
        search_dir = search_dir.parent
    return env_vars


def _get_setting(key: str, default: str) -> str:
    """
    Resolve a config value using priority:
      1. Django settings
      2. OS environment variable
      3. .env file
      4. Hardcoded default
    """
    try:
        import importlib
        django_conf = importlib.import_module("django.conf")
        django_settings = getattr(django_conf, "settings", None)
        if django_settings is not None:
            value = getattr(django_settings, key, None)
            if value is not None:
                return value
    except Exception:
        pass

    if key in os.environ:
        return os.environ[key]

    env_file_vars = _load_env_file()
    if key in env_file_vars:
        return env_file_vars[key]

    return default


def get_couch_server() -> couchdb.Server:
    """Return an authenticated CouchDB Server instance."""
    url      = _get_setting("COUCHDB_URL",      "http://127.0.0.1:5984/")
    user     = _get_setting("COUCHDB_USER",     "admin")
    password = _get_setting("COUCHDB_PASSWORD", "adminpassword")

    server = couchdb.Server(url)
    server.resource.credentials = (user, password)
    return server


def get_couch_db(db_name: str = None) -> couchdb.Database:
    """
    Return a CouchDB database handle, creating the DB if it does not exist.

    Parameters
    ----------
    db_name : str, optional
        Database name to open/create. Defaults to COUCHDB_NAME setting.

    Returns
    -------
    couchdb.Database

    Usage
    -----
        db = get_couch_db()

        # Save a document
        doc_id, doc_rev = db.save({"type": "student", "name": "Alice"})

        # Fetch a document
        doc = db[doc_id]

        # Update a document
        doc["name"] = "Alice Updated"
        db.save(doc)

        # Delete a document
        db.delete(db[doc_id])
    """
    server = get_couch_server()
    name   = db_name or _get_setting("COUCHDB_NAME", "counselling_db")

    if name not in server:
        print(f"[couchdb_client] Database '{name}' not found - creating it.")
        return server.create(name)

    print(f"[couchdb_client] Connected to database '{name}'.")
    return server[name]


# ---------------------------------------------------------------------------
# Quick self-test: python couchdb_client.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== CouchDB Client Self-Test ===")
    try:
        db = get_couch_db()

        # CREATE
        doc_id, doc_rev = db.save({
            "type":    "test_record",
            "message": "Hello from AEC Management System",
        })
        print(f"[CREATE] id={doc_id}  rev={doc_rev}")

        # READ
        doc = db[doc_id]
        print(f"[READ]   {dict(doc)}")

        # UPDATE
        doc["message"] = "Updated by self-test"
        db.save(doc)
        print(f"[UPDATE] message -> {db[doc_id]['message']}")

        # DELETE
        db.delete(db[doc_id])
        print(f"[DELETE] {doc_id} removed.")

        print("\nAll CRUD operations completed successfully!")
    except Exception as exc:
        print(f"\nError: {exc}")
        raise
