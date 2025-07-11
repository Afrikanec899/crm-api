import datetime
import time
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from facebook_business import FacebookAdsApi
from facebook_business.exceptions import FacebookRequestError

from core.models.core import (
    AdAccountDayStat,
    UserAccountDayStat,
    User,
    UserCampaignDayStat,
    UserAdAccountDayStat,
    Account,
    AdAccount,
    Campaign,
    Config,
)
from core.tasks import load_account_day_stats, FBAdAccount
from core.utils import dateperiod, get_tracker_auth


class Command(BaseCommand):
    help = ''

    # def add_arguments(self, parser):
    #     parser.add_argument("-s", "--start", action="store", dest="start_date", type=int, help="Date from")
    #     parser.add_argument("-e", "--end", action="store", dest="end_date", type=int, help="Date to")

    def handle(self, *args, **options):
        user = User.objects.get(id=55)
        range_start = datetime.date(2021, 4, 1)
        range_end = datetime.date(2021, 4, 30)
        accounts = Account.objects.filter(fb_access_token__isnull=False, manager=user).exclude(fb_access_token='')

        # range_start = timezone.now().date() - datetime.timedelta(days=days)
        # range_end = timezone.now().date()

        for account in accounts:
            print(account)
            if range_start < account.created_at.date():
                range_start = account.created_at.date()

            range_end = timezone.now().date()
            FacebookAdsApi.init(access_token=account.fb_access_token, proxies=account.proxy_config)
            adaccounts = AdAccount.objects.filter(account=account, deleted_at__isnull=True)
            for adaccount_obj in adaccounts:
                try:
                    adaccount = FBAdAccount(fbid=f'act_{adaccount_obj.adaccount_id}')
                    params = {
                        'time_range': {
                            'since': range_start.strftime('%Y-%m-%d'),
                            'until': range_end.strftime('%Y-%m-%d'),
                        },
                        'limit': 100,
                        'level': 'account',
                        'fields': ['spend', 'clicks'],
                        'time_increment': 1,
                    }
                    stats = adaccount.get_insights(params=params)
                    for stat in stats:
                        date = datetime.datetime.strptime(stat['date_start'], '%Y-%m-%d').date()
                        adaccount_manager = adaccount_obj.get_manager_on_date(date) or account.manager
                        account_manager = account.get_manager_on_date(date)
                        with transaction.atomic():
                            stats, _ = AdAccountDayStat.objects.get_or_create(
                                account=account, adaccount=adaccount, date=date, defaults={'clicks': 0, 'spend': 0}
                            )

                            prev_stats, current_stats = AdAccountDayStat.update(
                                pk=stats.pk,
                                clicks=int(stat.get('clicks', '0')),
                                spend=Decimal(stat.get('spend', '0.00')),
                            )

                            clicks = current_stats.clicks
                            spend = current_stats.spend
                            # print(clicks, spend)
                            # Если есть спенд, но карты нет - шлем алерт

                            if any([clicks, spend]):
                                UserAccountDayStat.upsert(
                                    date=date,
                                    account_id=account.id,
                                    user_id=171,
                                    campaign_id=adaccount_obj.campaign_id if adaccount_obj.campaign_id else None,
                                    spend=spend,
                                    profit=-spend,
                                    funds=Decimal('0.00'),
                                    clicks=Decimal('0.00'),
                                    visits=Decimal('0.00'),
                                    revenue=Decimal('0.00'),
                                    leads=Decimal('0.00'),
                                    cost=Decimal('0.00'),
                                    payment=Decimal('0.00'),
                                )
                except FacebookRequestError as e:
                    print(e)

        base_url = 'https://ap.zeustrack.io/api/v2/campaigns.json'

        tracker_login = user.tracker_login
        tracker_password = user.tracker_password

        session = get_tracker_auth(tracker_login, tracker_password)
        if session is not None:
            for date in reversed(dateperiod(range_start, range_end)):
                print(date)
                day_start = datetime.datetime.combine(date, datetime.time.min).isoformat()
                day_end = datetime.datetime.combine(date, datetime.time.max).isoformat()
                try:
                    params = {
                        'limit': 500,
                        'query': '',
                        'byColumn': 0,
                        'orderBy': 'campaign',
                        'searchQuery': '',
                        'ascending': 1,
                        'status': 'with_traffic',
                        'day': f'{day_start} - {day_end}',
                        'columns[]': [
                            'symbol',
                            'campaign',
                            'visits',
                            'clicks',
                            'conversions',
                            'cr',
                            'cost',
                            'revenue',
                            'profit',
                            'roi',
                            'ctr',
                            'cv',
                            'cpv',
                            'cpl',
                            'epv',
                        ],
                    }
                    page = 1
                    while True:
                        params['page'] = page
                        # Просили делать паузы
                        time.sleep(1)
                        stats = session.get(base_url, params=params).json()
                        if not stats.get('data'):
                            break
                        page += 1
                        for stats_data in stats['data']:
                            campaign = Campaign.objects.filter(campaign_id=stats_data['id'], user=user).first()
                            print(campaign)
                            if campaign:
                                UserAccountDayStat.upsert(
                                    date=date,
                                    account_id=None,
                                    user_id=171,
                                    campaign_id=campaign.id,
                                    clicks=stats_data['clicks'],
                                    visits=stats_data['visits'],
                                    leads=stats_data['conversions'],
                                    cost=stats_data['cost'],
                                    revenue=stats_data['revenue'],
                                    profit=stats_data['profit'],
                                    funds=Decimal('0.00'),
                                    spend=Decimal('0.00'),
                                    payment=Decimal('0.00'),
                                )

                except Exception as e:
                    print(e)
