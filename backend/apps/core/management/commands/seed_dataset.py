from django.core.management.base import BaseCommand, CommandError

from apps.core import maintenance, seeding


class Command(BaseCommand):
    help = (
        "Write the realistic, linked SRS sample dataset into CouchDB (countries, intakes, counsellors, students, "
        "applications + history, documents, counselling sessions, recommendations, notifications). Every doc is "
        "tagged source='seed'. Real data is never modified."
    )

    def add_arguments(self, parser):
        parser.add_argument("--password", default=seeding.DEFAULT_PASSWORD,
                            help=f"Password for every seeded account (default {seeding.DEFAULT_PASSWORD}).")
        parser.add_argument("--reset", action="store_true", help="Remove the existing seed dataset first.")
        parser.add_argument("--remove", action="store_true", help="Only remove the seed dataset, then stop.")

    def handle(self, *args, password, reset, remove, **options):
        if remove or reset:
            self.stdout.write(f"Backup written to {maintenance.backup()}")
            self.stdout.write(f"Removed {seeding.remove_seed()} seed documents.")
            if remove:
                return
        elif seeding.existing_seed_ids():
            raise CommandError("A seed dataset already exists. Use --reset to replace it or --remove to delete it.")

        try:
            counts = seeding.Seeder(password, log=self.stdout.write).run()
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        for doc_type, n in sorted(counts.items()):
            self.stdout.write(f"  {doc_type:<22} {n}")
        self.stdout.write(self.style.SUCCESS(
            f"Seed dataset written ({sum(counts.values())} documents). All seeded accounts use password: {password}"
        ))
