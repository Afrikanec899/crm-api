from django.core.management.base import BaseCommand

from core.tasks import check_tracker_servers, load_tracker_campaign_stats, load_tracker_campaigns, load_tracker_domains


class Command(BaseCommand):
    help = ''

    def add_arguments(self, parser):
        parser.add_argument("-d", "--days", action="store", dest="days", type=int, help="Days")

    def handle(self, *args, **options):
        # load_tracker_campaigns_v2()
        # load_tracker_domains()
        load_tracker_campaigns()
        # load_tracker_flows(days=3)
        # check_tracker_servers()
        # load_tracker_campaign_stats(days=30)
        # update_tracker_costs_v2(days=1)
        # load_tracker_flow_stats(days=3)
