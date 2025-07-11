from django.core.management.base import BaseCommand

from core.tasks import check_tracker_offers


class Command(BaseCommand):
    help = ''

    def add_arguments(self, parser):
        parser.add_argument("-d", "--days", action="store", dest="days", type=int, help="Days")

    def handle(self, *args, **options):
        check_tracker_offers()
