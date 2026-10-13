import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.db import get_db

DEFAULT_FILE = settings.REPO_ROOT / "output" / "universities.json"


class Command(BaseCommand):
    help = (
        "Load university documents from a JSON array file into CouchDB. Existing documents (same _id) are "
        "left untouched, so it is safe to re-run. The dataset file is local-only and is not committed."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_FILE))

    def handle(self, *args, file, **options):
        path = Path(file)
        if not path.exists():
            raise CommandError(f"Dataset not found: {path}")
        docs = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(docs, list):
            raise CommandError("Expected a JSON array of documents.")

        db = get_db()
        created = skipped = 0
        for doc in docs:
            if doc.get("type") != "university" or "_id" not in doc:
                skipped += 1
                continue
            if db.get(doc["_id"]) is not None:
                skipped += 1
                continue
            db.save({k: v for k, v in doc.items() if k != "_rev"})
            created += 1
        self.stdout.write(self.style.SUCCESS(f"Universities: {created} created, {skipped} already present/skipped."))
