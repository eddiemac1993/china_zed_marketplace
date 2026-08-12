from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from communinity.models import Room

class Command(BaseCommand):
    help = "Delete inactive Communinity rooms older than the configured lifetime."
    def add_arguments(self, parser): parser.add_argument("--hours", type=int, default=72)
    def handle(self, *args, **options):
        count, _ = Room.objects.filter(last_activity__lt=timezone.now()-timedelta(hours=options["hours"])).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} old records."))
