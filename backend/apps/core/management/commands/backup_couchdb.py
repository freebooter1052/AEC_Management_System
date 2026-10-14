from django.core.management.base import BaseCommand

from apps.core.maintenance import backup


class Command(BaseCommand):
    help = "Write every CouchDB document (design docs included) to output/backups/<db>-<timestamp>.json."

    def handle(self, *args, **options):
        path = backup()
        self.stdout.write(self.style.SUCCESS(f"Backup written to {path}"))
