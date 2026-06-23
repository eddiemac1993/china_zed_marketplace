from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Delete inactive unverified user accounts older than the selected number of days."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=14,
            help="Delete inactive accounts older than this many days. Default: 14.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many accounts would be deleted without deleting them.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        cutoff = timezone.now() - timedelta(days=days)
        User = get_user_model()
        queryset = User.objects.filter(is_active=False, date_joined__lt=cutoff)
        count = queryset.count()

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(f"{count} inactive account(s) older than {days} day(s) would be deleted.")
            )
            return

        queryset.delete()
        self.stdout.write(
            self.style.SUCCESS(f"Deleted {count} inactive account(s) older than {days} day(s).")
        )
