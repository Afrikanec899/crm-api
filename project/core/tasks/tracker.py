import datetime
import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.db.models import Sum
from django.template.loader import render_to_string
from django.utils import timezone

import pytz
from redis import Redis
from telebot import types

from core.models.core import (
    Account,
    AccountLog,
    Campaign,
    Config,
    Domain,
    Flow,
    FlowDayStat,
    Notification,
    User,
    UserAccountDayStat,
)
from core.tasks.helpers import process_campaign_stat
from core.utils import dateperiod, get_tracker_auth
from project.celery_app import app

redis = Redis(host='redis', db=0, decode_responses=True)
logger = logging.getLogger('celery.task')


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 2, 'countdown': 5})
def update_tracker_costs(self, account_id=None, days: int = 1):
    range_start = timezone.now().date() - datetime.timedelta(days=days)
    range_end = timezone.now().date()

    tracker_login = Config.get_value('tracker_login')
    tracker_password = Config.get_value('tracker_password')
    session = get_tracker_auth(tracker_login, tracker_password)
    if session is not None:
        for date in reversed(dateperiod(range_start, range_end)):
            day_stats = UserAccountDayStat.objects.filter(account__isnull=False, campaign__isnull=False, date=date)
            if account_id:
                day_stats = day_stats.filter(account_id=account_id)

            campaigns = day_stats.values('campaign__campaign_id').annotate(spend=Sum('spend'))
            for campaign in campaigns:
                if campaign['spend']:

                    campaign_id = campaign["campaign__campaign_id"]
                    cost_url = f'https://ap.zeustrack.io/api/campaigns/{campaign_id}/reports/daily_reports/cost'

                    data = {'cost': campaign['spend'], 'date': date.strftime('%Y-%m-%d')}
                    print(session.put(cost_url, data=data, timeout=60))
                    time.sleep(1)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def load_tracker_flows(self, days=30):
    base_url = 'https://ap.zeustrack.io/api/v2/flows.json'
    tracker_login = Config.get_value('tracker_login')
    tracker_password = Config.get_value('tracker_password')

    session = get_tracker_auth(tracker_login, tracker_password)
    if session is not None:
        range_start = timezone.now().date() - datetime.timedelta(days=days)
        range_end = timezone.now().date() + datetime.timedelta(days=1)

        day_start = datetime.datetime.combine(range_start, datetime.time.min).isoformat()
        day_end = datetime.datetime.combine(range_end, datetime.time.max).isoformat()
        try:
            params = {
                'limit': 500,
                'query': '',
                'byColumn': 0,
                'orderBy': 'flow',
                'searchQuery': '',
                'ascending': 1,
                'status': 'all',
                'day': f'{day_start} - {day_end}',
            }
            page = 1
            while True:
                params['page'] = page
                stats = session.get(base_url, params=params, timeout=60).json()
                if not stats.get('data'):
                    break
                page += 1
                for flow in stats['data']:
                    Flow.objects.update_or_create(
                        flow_id=flow['flow_id'], defaults={'flow_name': flow['title'], 'status': flow['status']}
                    )
        except Exception as e:
            print(e)
            logger.error(e, exc_info=True)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def load_tracker_flow_stats(self, days=1):
    base_url = 'https://ap.zeustrack.io/api/v2/flows.json'

    tracker_login = Config.get_value('tracker_login')
    tracker_password = Config.get_value('tracker_password')

    session = get_tracker_auth(tracker_login, tracker_password)

    if session is not None:
        range_start = timezone.now().date() - datetime.timedelta(days=days)
        range_end = timezone.now().date()

        for date in reversed(dateperiod(range_start, range_end)):
            day_start = datetime.datetime.combine(date, datetime.time.min).isoformat()
            day_end = datetime.datetime.combine(date, datetime.time.max).isoformat()

            try:
                params = {
                    'limit': 500,
                    'query': '',
                    'byColumn': 0,
                    'orderBy': 'flow',
                    'searchQuery': '',
                    'ascending': 1,
                    'status': 'with_traffic',
                    'day': f'{day_start} - {day_end}',
                }
                page = 1
                while True:
                    params['page'] = page
                    stats = session.get(base_url, params=params, timeout=60).json()
                    if not stats.get('data'):
                        break
                    page += 1
                    for flow in stats['data']:
                        flow_data = {
                            'leads': flow['conversions'],
                            'clicks': flow['clicks'],
                            'visits': flow['visits'],
                            'revenue': flow['revenue'],
                            'cost': flow['cost'],
                            'profit': flow['profit'],
                            'roi': flow['roi'],
                            'ctr': flow['ctr'],
                            'cv': flow['cv'],
                            'cr': flow['cr'],
                            'cpv': flow['cpv'],
                            'epv': flow['epv'],
                            'epc': flow['epc'],
                        }

                        flow_obj, _ = Flow.objects.update_or_create(
                            flow_id=flow['id'], defaults={'flow_name': flow['title'], 'status': flow['status']}
                        )

                        FlowDayStat.objects.update_or_create(flow=flow_obj, date=date, defaults=flow_data)
            except Exception as e:
                logger.error(e, exc_info=True)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def load_tracker_campaigns(self):
    base_url = 'https://ap.zeustrack.io/api/v2/campaigns.json'

    tracker_login = Config.get_value('tracker_login')
    tracker_password = Config.get_value('tracker_password')

    session = get_tracker_auth(tracker_login, tracker_password)
    if session is not None:
        # Попросили не дрочить их часто
        time.sleep(1)
        day_start = datetime.datetime.combine(timezone.now().date(), datetime.time.min).isoformat()
        day_end = (
            datetime.datetime.combine(timezone.now().date(), datetime.time.max).replace(microsecond=0).isoformat()
        )
        try:
            params = {
                'limit': 500,
                'query': '',
                'byColumn': 0,
                'orderBy': 'campaign',
                'searchQuery': '',
                'ascending': 1,
                'status': 'all',
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
                stats = session.get(base_url, params=params, timeout=60).json()
                if not stats.get('data'):
                    break
                page += 1
                for campaign in stats['data']:
                    campaign_data = {
                        'name': campaign['title'],
                        'symbol': campaign['symbol'],
                        'status': campaign['status'],
                        'tracking_url': campaign['trackingUrl'],
                    }
                    try:
                        campaign = Campaign.objects.get(campaign_id=campaign['id'])
                        Campaign.update(pk=campaign.id, action_verb='updated', **campaign_data)
                    except Campaign.DoesNotExist:
                        Campaign.create(campaign_id=campaign['id'], **campaign_data)
                # Попросили не дрочить их часто
                time.sleep(1)
        except Exception as e:
            logger.error(e, exc_info=True)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def load_user_tracker_campaigns(self):
    base_url = 'https://ap.zeustrack.io/api/v2/campaigns.json'

    for user in User.objects.filter(tracker_password__isnull=False, tracker_login__isnull=False):
        session = get_tracker_auth(user.tracker_login, user.tracker_password)
        if session is not None:
            # Попросили не дрочить их часто
            time.sleep(1)
            day_start = datetime.datetime.combine(timezone.now().date(), datetime.time.min).isoformat()
            day_end = datetime.datetime.combine(timezone.now().date(), datetime.time.max).isoformat()
            try:
                params = {
                    'limit': 500,
                    'query': '',
                    'byColumn': 0,
                    'orderBy': 'campaign',
                    'searchQuery': '',
                    'ascending': 1,
                    'status': 'all',
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
                    stats = session.get(base_url, params=params, timeout=60).json()
                    if not stats.get('data'):
                        break
                    page += 1
                    for campaign in stats['data']:
                        campaign_data = {
                            'name': campaign['title'],
                            'status': campaign['status'],
                            'tracking_url': campaign['trackingUrl'],
                            'symbol': campaign['symbol'],
                            'manager': user,
                        }
                        try:
                            campaign = Campaign.objects.get(campaign_id=campaign['id'])
                            Campaign.update(pk=campaign.id, action_verb='updated', **campaign_data)
                        except Campaign.DoesNotExist:
                            Campaign.create(campaign_id=campaign['id'], **campaign_data)

                    # Попросили не дрочить их часто
                    time.sleep(1)
            except Exception as e:
                logger.error(e, exc_info=True)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def archive_tracker_campaigns(self):
    tracker_login = Config.get_value('tracker_login')
    tracker_password = Config.get_value('tracker_password')
    week_ago = timezone.now() - datetime.timedelta(days=7)

    session = get_tracker_auth(tracker_login, tracker_password)
    if session is not None:
        # Попросили не дрочить их часто
        time.sleep(1)
        banned_logs = AccountLog.objects.filter(
            log_type=AccountLog.STATUS, status=Account.BANNED, start_at__lte=week_ago, end_at__isnull=True
        )

        for log in banned_logs:
            campaigns = log.account.get_all_campaigns().exclude(status='archived')
            for campaign in campaigns:
                try:
                    url = f'https://ap.zeustrack.io/api/campaigns/{campaign.campaign_id}/disable.json'
                    response = session.put(url, timeout=60)
                    if response.status_code == 200:
                        Campaign.update(pk=campaign.id, action_verb='archived', status='archived')
                    # Попросили не дрочить их часто
                    time.sleep(1)
                except Exception as e:
                    logger.error(e, exc_info=True)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def load_tracker_campaign_stats(self, days=1):
    base_url = 'https://ap.zeustrack.io/api/v2/campaigns.json'

    tracker_login = Config.get_value('tracker_login')
    tracker_password = Config.get_value('tracker_password')

    session = get_tracker_auth(tracker_login, tracker_password)
    if session is not None:
        range_start = timezone.now().date() - datetime.timedelta(days=days)
        range_end = timezone.now().date()

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
                    stats = session.get(base_url, params=params, timeout=60).json()
                    if not stats.get('data'):
                        break
                    page += 1
                    for stats_data in stats['data']:
                        process_campaign_stat(stats_data, date)
            except Exception as e:
                logger.error(e, exc_info=True)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def reload_tracker_campaign_stats(self, account_id, days):
    base_url = 'https://ap.zeustrack.io/api/v2/campaigns.json'

    tracker_login = Config.get_value('tracker_login')
    tracker_password = Config.get_value('tracker_password')

    session = get_tracker_auth(tracker_login, tracker_password)
    if session is not None:
        range_start = timezone.now().date() - datetime.timedelta(days=days)
        range_end = timezone.now().date()

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
                    stats = session.get(base_url, params=params, timeout=60).json()
                    if not stats.get('data'):
                        break
                    page += 1
                    for stats_data in stats['data']:
                        campaign = Campaign.objects.filter(campaign_id=stats_data['id']).first()
                        if campaign:
                            account = campaign.get_account()
                            if account and account.id == account_id:
                                process_campaign_stat(stats_data, date, reload=True)
            except Exception as e:
                logger.error(e, exc_info=True)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def check_tracker_offers(self):
    base_url = 'https://ap.zeustrack.io/api/v2/reports/team.json'

    tracker_login = Config.get_value('tracker_login')
    tracker_password = Config.get_value('tracker_password')

    now = timezone.now().astimezone(pytz.timezone('Europe/Kiev'))
    date = now.date()
    current_hour = now.hour

    day_start = datetime.datetime.combine(date, datetime.time.min).isoformat()
    day_end = datetime.datetime.combine(date, datetime.time.max).isoformat()
    session = get_tracker_auth(tracker_login, tracker_password)

    if session is not None:
        # Попросили не дрочить их часто
        try:
            params = {
                'limit': 50,
                'query': '',
                'byColumn': 0,
                'day': f'{day_start} - {day_end}',
                'groupBy[]': ['offer', 'hour'],
                'columns[]': ['firstColumn', 'clicks', 'cr', 'conversions'],
            }  #  , 'filterIndicators[][comparison]': '>=', 'filterIndicators[][measure]': 'clicks', 'filterIndicators[][value]': '100'}
            page = 1
            while True:
                params['page'] = page
                offers = session.get(base_url, params=params, timeout=60).json()
                if not offers.get('data'):
                    break
                page += 1
                offers = offers['data']
                offers = list(filter(lambda x: x['data']['clicks'] > 100, offers))
                for offer in offers:
                    offer_data = {}
                    for subrow in offer['subrows']:
                        hour = int(subrow['data']['firstColumn'][:2])
                        offer_data[hour] = {
                            'clicks': subrow['data']['clicks'],
                            'cr': subrow['data']['cr'],
                            'leads': subrow['data']['conversions'],
                        }

                    if not offer_data.get(current_hour):
                        continue
                    total_clicks = 0
                    total_leads = 0
                    start_hour = current_hour
                    hours = 0
                    while total_clicks < 200:
                        hours += 1
                        hourly_data = offer_data.get(start_hour, {})
                        total_clicks += hourly_data.get('clicks', 0)
                        total_leads += hourly_data.get('leads', 0)
                        start_hour -= 1
                        if start_hour < 0:
                            break

                    total_cr = total_leads / total_clicks * 100
                    total_cr = round(total_cr, 2)
                    if total_cr <= 1:
                        print(offer['data'], total_cr, hours)
                        message = render_to_string(
                            'core/offer_down.html', {'offer': offer['data'], 'cr': total_cr, 'hours': hours}
                        )
                        keyboard = types.InlineKeyboardMarkup(row_width=3)
                        mute_1h = types.InlineKeyboardButton(
                            'mute 1h', callback_data=f'mute;1;{offer["data"]["_type"]["id"]}'
                        )
                        mute_2h = types.InlineKeyboardButton(
                            'mute 2h', callback_data=f'mute;2;{offer["data"]["_type"]["id"]}'
                        )
                        mute_3h = types.InlineKeyboardButton(
                            'mute 3h', callback_data=f'mute;3;{offer["data"]["_type"]["id"]}'
                        )
                        mute_6h = types.InlineKeyboardButton(
                            'mute 6h', callback_data=f'mute;6;{offer["data"]["_type"]["id"]}'
                        )
                        mute_12h = types.InlineKeyboardButton(
                            'mute 12h', callback_data=f'mute;12;{offer["data"]["_type"]["id"]}'
                        )
                        mute_24h = types.InlineKeyboardButton(
                            'mute 24h', callback_data=f'mute;24;{offer["data"]["_type"]["id"]}'
                        )
                        keyboard.add(mute_1h, mute_2h, mute_3h, mute_6h, mute_12h, mute_24h)
                        data = {'message': message, 'keyboard': keyboard.to_json()}

                        recipients = User.get_recipients(roles=[User.ADMIN, User.TEAMLEAD])
                        for recipient in recipients:
                            key = f'mute:{recipient.id}:{offer["data"]["_type"]["id"]}'
                            if not cache.get(key):
                                Notification.create(
                                    recipient=recipient,
                                    level=Notification.CRITICAL,
                                    category=Notification.SYSTEM,
                                    data=data,
                                    sender=None,
                                )
                time.sleep(1)
        except Exception as e:
            logger.error(e, exc_info=True)


@app.task
def check_tracker_servers():
    base_url = 'https://ap.zeustrack.io/api/v2/servers.json'
    tracker_login = Config.get_value('tracker_login')
    tracker_password = Config.get_value('tracker_password')

    session = get_tracker_auth(tracker_login, tracker_password)
    if session is not None:
        # Попросили не дрочить их часто
        try:
            params = {'limit': 500, 'searchQuery': '', 'byColumn': 0, 'orderBy': 'status', 'ascending': 1}
            page = 1
            while True:
                params['page'] = page
                servers = session.get(base_url, params=params, timeout=60).json()
                if not servers.get('data'):
                    break
                page += 1
                for server in servers['data']:
                    if server['status'].lower() == 'offline':
                        redis.setnx(
                            f'server_downtime_{server["id"]}', int(timezone.now().timestamp()),
                        )
                        sent = redis.get(f'server_down_alert_{server["id"]}')

                        if not sent:
                            redis.setex(f'server_down_alert_{server["id"]}', 60 * 60, 1)
                            message = render_to_string('core/server_down.html', {'server': server,})
                            data = {'message': message}

                            recipients = User.get_recipients(roles=[User.ADMIN,])
                            for recipient in recipients:
                                Notification.create(
                                    recipient=recipient,
                                    level=Notification.CRITICAL,
                                    category=Notification.SYSTEM,
                                    data=data,
                                    sender=None,
                                )
                    else:
                        total_downtime = None
                        first_seen = redis.get(f'server_downtime_{server["id"]}')
                        if first_seen:
                            redis.delete(f'server_downtime_{server["id"]}')
                            first_seen = datetime.datetime.fromtimestamp(int(first_seen), tz=settings.TZ)
                            total_downtime = (timezone.now() - first_seen).total_seconds()
                            total_downtime = str(datetime.timedelta(seconds=total_downtime))

                        sent = redis.get(f'server_down_alert_{server["id"]}')
                        if sent:
                            redis.delete(f'server_down_alert_{server["id"]}')
                            message = render_to_string(
                                'core/server_up.html', {'server': server, 'duration': total_downtime},
                            )
                            data = {'message': message}

                            recipients = User.get_recipients(roles=[User.ADMIN,])
                            for recipient in recipients:
                                Notification.create(
                                    recipient=recipient,
                                    level=Notification.CRITICAL,
                                    category=Notification.SYSTEM,
                                    data=data,
                                    sender=None,
                                )
                time.sleep(1)
        except Exception as e:
            logger.error(e, exc_info=True)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def load_tracker_domains(self):
    base_url = 'https://ap.zeustrack.io/api/v2/domains.json'
    tracker_login = Config.get_value('tracker_login')
    tracker_password = Config.get_value('tracker_password')

    session = get_tracker_auth(tracker_login, tracker_password)
    if session is not None:
        crm_domains = Domain.objects.filter(deleted_at__isnull=True, is_internal=False)
        tracker_domains = []
        # Попросили не дрочить их часто
        time.sleep(1)
        try:
            params = {'limit': 500, 'searchQuery': '', 'byColumn': 0, 'orderBy': 'status', 'ascending': 1}
            page = 1
            to_send_up = []
            to_send_down = []
            while True:
                params['page'] = page
                domains = session.get(base_url, params=params, timeout=60).json()
                if not domains.get('data'):
                    break
                page += 1
                for domain in domains['data']:
                    tracker_domain, _ = Domain.objects.update_or_create(
                        domain_id=domain['id'], defaults={'name': domain['name'], 'deleted_at': None}
                    )
                    tracker_domains.append(tracker_domain.id)

                    if domain['status'].lower() == 'offline':
                        redis.setnx(
                            f'domain_downtime_{domain["id"]}', int(timezone.now().timestamp()),
                        )
                        sent = redis.get(f'domain_down_alert_{domain["id"]}')

                        if not sent:
                            to_send_down.append(domain)
                            redis.setex(f'domain_down_alert_{domain["id"]}', 60 * 60, 1)

                    else:
                        total_downtime = None
                        first_seen = redis.get(f'domain_downtime_{domain["id"]}')
                        if first_seen:
                            redis.delete(f'domain_downtime_{domain["id"]}')
                            first_seen = datetime.datetime.fromtimestamp(int(first_seen), tz=settings.TZ)
                            total_downtime = (timezone.now() - first_seen).total_seconds()
                            total_downtime = str(datetime.timedelta(seconds=total_downtime))

                        sent = redis.get(f'domain_down_alert_{domain["id"]}')
                        if sent:
                            to_send_up.append((domain, total_downtime))
                            redis.delete(f'domain_down_alert_{domain["id"]}')

            removed_domains = crm_domains.exclude(id__in=tracker_domains)
            if removed_domains.exists():
                removed_domains.update(deleted_at=timezone.now())

            if to_send_down:
                message = render_to_string('core/domain_down.html', {'domains': to_send_down,})
                data = {'message': message}

                recipients = User.get_recipients(roles=[User.ADMIN,])
                for recipient in recipients:
                    Notification.create(
                        recipient=recipient,
                        level=Notification.CRITICAL,
                        category=Notification.SYSTEM,
                        data=data,
                        sender=None,
                    )
            if to_send_up:
                message = render_to_string('core/domain_up.html', {'domains': to_send_up},)
                data = {'message': message}

                recipients = User.get_recipients(roles=[User.ADMIN,])
                for recipient in recipients:
                    Notification.create(
                        recipient=recipient,
                        level=Notification.CRITICAL,
                        category=Notification.SYSTEM,
                        data=data,
                        sender=None,
                    )

        except Exception as e:
            logger.error(e, exc_info=True)
