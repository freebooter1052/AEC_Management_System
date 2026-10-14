from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from apps.core import maintenance


class Command(BaseCommand):
    help = (
        "Remove demo/seed data from CouchDB and keep what was entered through the application "
        "(see apps/core/maintenance.py for the exact rules). Dry run unless --apply is given; "
        "--apply writes a full backup to output/backups/ first."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Perform the changes (default: report only).")
        parser.add_argument("--reassign-orphans-to", metavar="COUNSELLOR_ID",
                            help="Move kept students whose counsellor is deleted to this kept counsellor "
                                 "(default: leave them unassigned).")
        parser.add_argument("--no-backup", action="store_true", help="Skip the automatic backup (not recommended).")

    def handle(self, *args, apply, reassign_orphans_to, no_backup, **options):
        plan = maintenance.plan_purge(maintenance.all_docs())
        out = self.stdout

        out.write(self.style.MIGRATE_HEADING("KEEP"))
        for t, n in sorted(Counter(d.get("type") for d in plan.keep).items()):
            out.write(f"  {t:<20} {n}")
        for d in plan.keep:
            if d.get("type") in maintenance.PEOPLE_TYPES:
                out.write(f"    {d['_id']:<28} {maintenance.describe(d)}")

        out.write(self.style.MIGRATE_HEADING("DELETE"))
        for t, n in sorted(Counter(d.get("type") or f"doc_type:{d.get('doc_type')}" for d in plan.delete).items()):
            out.write(f"  {t:<20} {n}")

        out.write(self.style.MIGRATE_HEADING("REASSIGN"))
        target = reassign_orphans_to or "(unassigned)"
        for s in plan.orphaned_students:
            out.write(f"  {s['_id']} {maintenance.describe(s)}: {s.get('counsellor_id')} -> {target}")
        if not plan.orphaned_students:
            out.write("  none")
        if plan.unknown:
            out.write(self.style.WARNING(f"Left untouched (unrecognised type): {len(plan.unknown)} docs"))

        if not apply:
            out.write(self.style.NOTICE("\nDry run only. Re-run with --apply to make these changes."))
            return

        if not no_backup:
            out.write(f"Backup written to {maintenance.backup()}")
        try:
            result = maintenance.apply_purge(plan, reassign_orphans_to)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        out.write(self.style.SUCCESS(
            f"Done: {result['deleted']} deleted, {result['reassigned']} reassigned, "
            f"{result['reconciled']} counsellor lists rebuilt, indexes dropped: {result['indexes_dropped'] or 'none'}."
        ))
