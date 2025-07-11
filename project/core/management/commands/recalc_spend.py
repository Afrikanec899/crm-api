import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models.core import AdAccountDayStat, UserAccountDayStat, User, UserCampaignDayStat, UserAdAccountDayStat
from core.utils import dateperiod


class Command(BaseCommand):
    help = ''

    # def add_arguments(self, parser):
    #     parser.add_argument("-s", "--start", action="store", dest="start_date", type=int, help="Date from")
    #     parser.add_argument("-e", "--end", action="store", dest="end_date", type=int, help="Date to")

    def handle(self, *args, **options):
        user = User.objects.get(id=112)
        start = datetime.date(2021, 3, 1)
        end = datetime.date(2021, 3, 31)
        user_campaign_stats = UserCampaignDayStat.objects.filter(user=user, date__range=(start, end))
        # user_account_stats = UserAdAccountDayStat.objects(user=user, date__range=(start, end))
        with transaction.atomic():
            for stat in user_campaign_stats:
                campaign = stat.campaign
                diff = {
                    'leads': stat.leads,
                    'clicks': stat.clicks,
                    'visits': stat.visits,
                    'revenue': stat.revenue,
                    'cost': stat.cost,
                }
                if not UserAccountDayStat.objects.filter(user=user, date=stat.date, campaign=campaign).exists():
                    UserAccountDayStat.upsert(
                        date=stat.date,
                        account_id=campaign.get_account().id if campaign.get_account() else None,
                        user_id=user.id,
                        campaign_id=campaign.id,
                        clicks=diff['clicks'],
                        visits=diff['visits'],
                        leads=diff['leads'],
                        cost=diff['cost'],
                        revenue=diff['revenue'],
                        profit=Decimal('0.00'),
                        funds=Decimal('0.00'),
                        spend=Decimal('0.00'),
                        payment=Decimal('0.00'),
                    )
