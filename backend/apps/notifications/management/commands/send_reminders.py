from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.notifications import reminders


class Command(BaseCommand):
    help = ("Create due reminders: application deadlines, outstanding documents and counselling follow-ups. "
            "Idempotent - run it as often as you like (e.g. daily from Task Scheduler or cron).")

    def add_arguments(self, parser):
        parser.add_argument("--date", help="Pretend today is YYYY-MM-DD (UTC), e.g. to test the windows.")

    def handle(self, *args, **options):
        today = None
        if options.get("date"):
            try:
                today = date.fromisoformat(options["date"])
            except ValueError:
                raise CommandError("--date must be YYYY-MM-DD.") from None
        counts = reminders.sweep(today)
        total = sum(counts.values())
        detail = ", ".join(f"{k} {v}" for k, v in counts.items())
        self.stdout.write(self.style.SUCCESS(f"{total} new reminder notification(s): {detail}."))
