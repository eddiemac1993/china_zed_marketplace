from django.core.management.base import BaseCommand

from loans.reminders import run_reminders


class Command(BaseCommand):
    help = "Send loan due-date reminders (3 days before, 1 day before, on due, overdue)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be sent without recording or delivering anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        results = run_reminders(dry_run=dry_run)
        if not results:
            self.stdout.write("No reminders due today.")
            return
        for r in results:
            flag = "DRY-RUN" if dry_run else r["channel"]
            self.stdout.write(
                self.style.SUCCESS(
                    f"[{flag}] {r['kind']} → {r['customer']} ({r['loan']})"
                )
            )
        self.stdout.write(f"{len(results)} reminder(s) processed.")
