from django.core.management.base import BaseCommand
from django.utils.timezone import now
from datetime import timedelta
from marketdata.models import PositionSnapshot
from django.utils.timezone import make_aware
import datetime

class Command(BaseCommand):
    help = "Delete PositionSnapshot records older than specified days (default 7)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Delete positions older than this many days (default: 7)',
        )

    def handle(self, *args, **options):
        days = options['days']
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
        cutoff_date = make_aware(cutoff_date)  # Make timezone aware datetime
        
        qs = PositionSnapshot.objects.filter(ts__lt=cutoff_date)
        count, _ = qs.delete()

        self.stdout.write(self.style.SUCCESS(
            f"Deleted {count} position snapshots older than {days} days."
        ))