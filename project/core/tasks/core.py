import csv
import datetime
import json
import logging
import random
import time
from decimal import Decimal
from typing import Any, Dict, List

from django.conf import settings
from django.db import transaction
from django.db.models.aggregates import Sum
from django.template.loader import render_to_string
from django.utils import timezone

import mechanicalsoup
import requests
import telebot
from facebook_business import FacebookAdsApi
from facebook_business.adobjects.user import User as FBUser
from haproxystats import HAProxyServer
from redis import Redis
from requests.exceptions import HTTPError

from core.models.contacts import UserEmail
from core.models.core import (
    Account,
    AccountPayment,
    AdAccountCreditCard,
    Card,
    Config,
    Domain,
    Notification,
    ProcessCSVTask,
    ShortifyDomain,
    User,
    UserAccountDayStat,
)
from core.tasks import helpers
from core.tasks.helpers import check_banned_urls
from core.utils import dateperiod
from project.celery_app import app

redis = Redis(host='redis', db=0, decode_responses=True)
logger = logging.getLogger('celery.task')


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def save_subscribers_data(self, user_id: int, page_id: int, email: str, phone: str) -> None:
    api_url = f'https://api.manychat.com/fb/subscriber/getInfo?subscriber_id={user_id}'
    api_key = redis.get(f'manychat_api_key_{user_id}_{page_id}')
    headers = {'Authorization': f'Bearer {api_key}'}  # type: ignore
    user_data = requests.get(api_url, headers=headers).json().get('data')
    UserEmail.objects.create(
        user_id=user_id,
        page_id=page_id,
        email=email,
        phone=phone,
        first_name=user_data.get('first_name'),
        last_name=user_data.get('last_name'),
        name=user_data.get('name'),
    )


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 10})
def create_empty_mla_profiles(self, user_id: int, count=1):
    user = User.objects.get(id=user_id)
    try:
        count = int(count)
    except:
        pass

    api_url = 'http://mla:46000/api/v2/profile'

    for _ in range(count):
        mla_template = Config.get_value('mla_profile_template')
        mla_ua_list = Config.get_value('mla_ua_list').split('\n')
        mla_resolution_list = Config.get_value('mla_resolution_list').split('\n')
        mla_font_list = Config.get_value('mla_font_list').split('\n')

        fonts = random.sample(mla_font_list, random.randint(5, 150))
        mla_template['fonts']['families'] = fonts

        profile_name = f'{user.username}: {timezone.now()}'

        mla_template['name'] = profile_name

        if mla_ua_list:
            mla_template['navigator']['userAgent'] = random.choice(mla_ua_list).strip()
            mla_template['navigator']['resolution'] = random.choice(mla_resolution_list).strip()

        mla_template['network']['proxy'] = {
            "type": "HTTP",
            "host": user.proxy_host,
            "port": user.proxy_port,
            "username": user.proxy_login,
            "password": user.proxy_password,
        }
        if user.mla_group_id:
            mla_template['group'] = str(user.mla_group_id)

        # mla_template["webRTC"] = {
        #     "mode": "FAKE",
        #     "fillBasedOnExternalIp": True,
        #     "localIps": [
        #       "172.16.1.1",
        #       "192.168.0.12"
        #     ]
        # }

        response = requests.post(api_url, json=mla_template, timeout=60)

        if response.status_code != 200:
            raise HTTPError(response.text)
        time.sleep(6)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 10})
def create_mla_profile(
    self,
    account_id: int,
    custom_template: Dict[Any, Any] = None,
    custom_ua_list: List[str] = None,
    shareto_id: int = None,
) -> None:
    """
    {   "name": null,
        "notes": null,
        "browser": "mimic",
        "os": "win",
        "startUrl": null,
        "googleServices": true,
        "enableLock": true,
        "navigator": {
            "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:62.0) Gecko/20100101 Firefox/62.0",
            "resolution": "1280x720",
            "language": "ru,uk;q=0.9,en;q=0.8",
            "platform": "Win64",
            "doNotTrack": 0,
            "hardwareConcurrency": 8
        },
        "storage": {
            "local": true,
            "extensions": true,
            "bookmarks": true,
            "history": true,
            "passwords": true
        },
        "network": {
            "proxy": {
                "type": "HTTP",
                "host": "192.168.1.1",
                "port": "1080",
                "username": "username",
                "password": "password"
            },
            "dns": [
                "8.8.8.8"
            ]
        },
        "plugins": {
            "enableVulnerable": false,
            "enableFlash": false
        },
        "timezone": {
            "mode": "FAKE",
            "fillBasedOnExternalIp": true
        },
        "geolocation": {
            "mode": "PROMPT",
            "fillBasedOnExternalIp": true
        },
        "audioContext": {
            "mode": "NOISE"
        },
        "canvas": {
            "mode": "NOISE"
        },
        "fonts": {
        "mode": "FAKE",
        "maskGlyphs": true,
        "families": [
             "MS Serif",
            "Segoe UI"
        ]
        },
        "mediaDevices": {
            "mode": "FAKE",
            "videoInputs": 1,
            "audioInputs": 2,
            "audioOutputs": 3
        },
        "webRTC": {
        "mode": "FAKE",
        "fillBasedOnExternalIp": true,
        "localIps": [
          "192.168.0.12"
        ]
        },
        "webGL": {
        "mode": "NOISE"
        },
        "webGLMetadata": {
        "mode": "MASK",
        "vendor": "Google Inc.",
        "renderer": "ANGLE AMD Mobility Radeon HD 5000"
        },
        "extensions": {
        "enable": false,
        "names": null
        }
        }
    """
    account = Account.objects.get(id=account_id)

    mla_template = custom_template or Config.get_value('mla_profile_template')
    mla_ua_list = custom_ua_list or Config.get_value('mla_ua_list').split('\n')
    mla_resolution_list = Config.get_value('mla_resolution_list').split('\n')
    mla_font_list = Config.get_value('mla_font_list').split('\n')

    fonts = random.sample(mla_font_list, random.randint(5, 150))
    mla_template['fonts']['families'] = fonts

    mla_template['name'] = account.display_name
    if settings.DEBUG:
        mla_template['name'] = f'{account.display_name} local'

    if account.comment:
        mla_template['notes'] = account.comment

    tags = ', '.join(account.tags) if account.tags else ''

    mla_template['notes'] = f"{mla_template['notes']},\n{tags}"

    if mla_ua_list:
        mla_template['navigator']['userAgent'] = random.choice(mla_ua_list).strip()
        mla_template['navigator']['resolution'] = random.choice(mla_resolution_list).strip()

    mla_template['network']['proxy'] = {
        "type": "HTTP",
        "host": account.created_by.proxy_host,
        "port": account.created_by.proxy_port,
        "username": account.created_by.proxy_login,
        "password": account.created_by.proxy_password,
    }
    if shareto_id:
        user = User.objects.get(id=shareto_id)
        if user.mla_group_id:
            mla_template['group'] = str(user.mla_group_id)

    api_url = 'http://mla:46000/api/v2/profile'
    response = requests.post(api_url, json=mla_template, timeout=30)
    if response.status_code == 200:
        mla_profile_id = response.json()['uuid']
        Account.update(
            pk=account.id,
            action_verb='Created MLA profile',
            mla_profile_id=mla_profile_id,
            mla_profile_data=mla_template,
        )
        # if shareto_id:
        #     user = User.objects.get(id=shareto_id)
        #     if user.mla_group_id:
        #         share_mla_profile.delay(account.id, shareto_id=user.id)
    else:
        logger.error(
            'Error profile create', extra={'status': response.status_code, 'text': response.text}, exc_info=True
        )
        raise HTTPError(response.json().get('value'))


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 1, 'countdown': 7}, rate_limit='9/m')
def share_mla_profile(self, account_id: int, shareto_id: int, proxy_data: Dict[str, Any] = None) -> None:
    def send_share_error_message(account, shareto):
        message = render_to_string('accounts/share_mla_error.html', {'account': account, 'share_to': shareto})
        data = {'message': message, 'account_id': account_id}

        recipients = User.get_recipients(roles=[User.MANAGER])
        for recipient in recipients:
            Notification.create(
                recipient=recipient, level=Notification.WARNING, category=Notification.ACCOUNT, data=data, sender=None,
            )

    account = Account.objects.get(id=account_id)
    user = User.objects.get(id=shareto_id)

    if user.mla_group_id:
        # Local API
        # Проверяем, не запущен ли профиль
        # https://app.swaggerhub.com/apis/Multilogin/MultiloginLocalRestAPI/1.0#/Misc/ActiveGet
        # true - запущен, false - ERROR response, profile is not launched
        # response = requests.get(
        #     'http://mla:46000/api/v1/profile/active', params={'profileId': account.mla_profile_id}, timeout=60
        # )
        # if response.status_code == 200 and response.json().get('value', None) is False:
        # update proxy
        mla_template = {'group': str(user.mla_group_id)}
        update_url = f'http://mla:46000/api/v2/profile/{account.mla_profile_id}'
        if proxy_data:
            mla_template['network'] = {
                'proxy': {
                    "type": "HTTP",
                    "host": proxy_data.get('host'),
                    "port": proxy_data.get('port'),
                    "username": proxy_data.get('login'),
                    "password": proxy_data.get('password'),
                }
            }
        response = requests.post(update_url, json=mla_template, timeout=30,)
        if response.status_code != 204:
            logger.error('Share profile Error', exc_info=True, extra={'response': response.json()})
            send_share_error_message(account, user)
        # else:
        #     # Шлем менеджеру сообщение чтобы закрыл акк в мультике
        #     message = render_to_string('accounts/close_mla_profile.html', {'account': account})
        #     data = {'message': message, 'account_id': account_id}
        #
        #     recipients = User.get_recipients(roles=[User.MANAGER])
        #     for recipient in recipients:
        #         Notification.create(
        #             recipient=recipient,
        #             level=Notification.WARNING,
        #             category=Notification.ACCOUNT,
        #             data=data,
        #             sender=None,
        #         )
        #     # Перезапускаем через 5 минут
        #     self.apply_async((account_id,), countdown=5 * 60)


@app.task
def recalc_cards_spends() -> None:
    for adaccount_card in AdAccountCreditCard.objects.all():
        with transaction.atomic():
            adaccount_card.recalc_spends()
            if adaccount_card.card:
                adaccount_card.card.recalc_spends()


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 600})
def check_transactions(self) -> None:
    login_url = 'https://m0n0lith.com/login'
    browser = mechanicalsoup.StatefulBrowser(
        user_agent='Mozilla/5.0 (X11; U; Linux i686; en-US) AppleWebKit/534.7 '
        '(KHTML, like Gecko) Chrome/7.0.517.41 Safari/534.7'
    )

    browser.open(login_url)
    browser.select_form('form')
    browser['site-password-protected'] = settings.MNLTH_SITE_PASS
    browser.submit_selected()

    browser.select_form('form')
    browser['username'] = settings.MNLTH_LOGIN
    browser['password'] = settings.MNLTH_PASSWD

    browser.submit_selected()

    now = timezone.now()
    date_from = (now - datetime.timedelta(days=1)).date()
    date_to = now.date()

    params = {
        'filters[ref]': '',
        'filters[card]': '',
        'filters[dateRangeFrom]': date_from.strftime('%d/%m/%Y'),
        'filters[dateRangeTo]': date_to.strftime('%d/%m/%Y'),
        'filters[status]': '',
        'filters[perPage]': '1000',
        'page': 0,
    }
    while True:
        params['page'] += 1
        transactions = browser.open('https://m0n0lith.com/transactions', params=params)
        trs = transactions.soup.select('tbody tr')
        if not trs:
            break

        for tr in trs:
            tds = tr.findAll('td')
            if len(tds) == 6:
                card = tds[1].text.lstrip('#')
                cards = Card.objects.filter(number=card)
                # actions = (
                #     Action.objects.filter(Q(data__contains=[{'new': card}]) | Q(data__contains=[{'old': card}]))
                #     .order_by()
                #     .values('id')
                # )
                # if not actions.exists():
                if not cards.exists():
                    # Проверяем в акках, так как может в старых не быть этих данных
                    if not Account.objects.filter(card_number=card).exists():
                        message = render_to_string(
                            'core/wrong_card.html', {'card': card, 'date': date_from, 'tag': tds[4].text}
                        )
                        data = {'message': message}

                        recipients = User.get_recipients(roles=[User.ADMIN])
                        for recipient in recipients:
                            Notification.create(
                                recipient=recipient,
                                level=Notification.CRITICAL,
                                category=Notification.FINANCE,
                                data=data,
                                sender=None,
                            )


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 2})
def process_telegram_webhook(self, data):
    bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN)
    chat_id = data['message']['chat']['id']
    try:
        token = data['message']['text'].split('/limit')[1].strip()
        proxies = {'https': f'http://proxy:bpQ6K3zGnuh66TPU@proxy.holyaff.com:3128'}
        FacebookAdsApi.init(access_token=token, proxies=proxies)
        user = FBUser(fbid='me')
        adaccounts = user.get_ad_accounts(
            fields=['name', 'adtrust_dsl', 'currency', 'timezone_name', 'adspaymentcycle{threshold_amount}',]
        )
        for adaccount in adaccounts:
            if adaccount.get('adspaymentcycle'):
                adaccount.threshold_amount = Decimal(
                    adaccount['adspaymentcycle']['data'][0]['threshold_amount']
                ) / Decimal('100')
            message = render_to_string('bot/limits.html', {'adaccount': adaccount})
            bot.send_message(chat_id, message, parse_mode='HTML')

    except Exception as e:
        bot.send_message(chat_id, f'Error: {repr(e)}', parse_mode='HTML')


@app.task
def process_csv_file(task_id: int):
    import_task = ProcessCSVTask.objects.get(id=task_id)
    import_task.status = 1
    import_task.save(update_fields=['status'])
    getattr(helpers, f'import_{import_task.type}_csv')(import_task)


@app.task
def proxy_check():
    haproxy = HAProxyServer(
        Config.get_value('haproxy_stats_host'),
        user=Config.get_value('haproxy_stats_user'),
        password=Config.get_value('haproxy_stats_password'),
        timeout=30,
    )
    for backend in haproxy.backends:
        for listener in backend.listeners:
            if 'up' not in listener.status.lower() and listener.lastchg > 60 * 5:
                redis.setnx(
                    f'downtime_{listener.name}',
                    int((timezone.now() - datetime.timedelta(seconds=listener.lastchg)).timestamp()),
                )
                sent = redis.get(f'down_alert_{listener.name}')
                if not sent:
                    redis.setex(f'down_alert_{listener.name}', 60 * 60, 1)
                    message = render_to_string(
                        'core/proxy_down.html',
                        {'proxy_name': listener.name, 'duration': str(datetime.timedelta(seconds=listener.lastchg))},
                    )
                    data = {'message': message}

                    recipient = User.objects.get(id=1)
                    Notification.create(
                        recipient=recipient,
                        level=Notification.CRITICAL,
                        category=Notification.PROXY,
                        data=data,
                        sender=None,
                    )
            else:
                total_downtime = None
                first_seen = redis.get(f'downtime_{listener.name}')
                if first_seen:
                    redis.delete(f'downtime_{listener.name}')
                    first_seen = datetime.datetime.fromtimestamp(int(first_seen), tz=settings.TZ)
                    total_downtime = (
                        (timezone.now() - datetime.timedelta(seconds=listener.lastchg)) - first_seen
                    ).total_seconds()
                    total_downtime = str(datetime.timedelta(seconds=total_downtime))

                sent = redis.get(f'down_alert_{listener.name}')
                if sent:
                    redis.delete(f'down_alert_{listener.name}')
                    message = render_to_string(
                        'core/proxy_up.html', {'proxy_name': listener.name, 'duration': total_downtime},
                    )
                    data = {'message': message}

                    recipient = User.objects.get(id=1)
                    Notification.create(
                        recipient=recipient,
                        level=Notification.CRITICAL,
                        category=Notification.PROXY,
                        data=data,
                        sender=None,
                    )


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 600})
def check_banned_domains(self):
    max_domains = 500
    urls_to_check = Domain.objects.filter(deleted_at__isnull=True, is_banned=False)
    if urls_to_check.exists():
        limit = 0
        offset = 500
        while True:
            batch = urls_to_check[limit:offset]
            if not batch:
                break
            limit += max_domains
            offset += max_domains

            check_banned_urls([f'http://{domain.name}' for domain in batch], type='tracker')

    urls_to_check = ShortifyDomain.objects.filter(is_public=True, is_banned=False)
    if urls_to_check.exists():
        limit = 0
        offset = 500
        while True:
            batch = urls_to_check[limit:offset]
            if not batch:
                break
            limit += max_domains
            offset += max_domains
            check_banned_urls([f'http://{domain.domain}' for domain in batch], type='shortify')


@app.task
def recalc_account_payments(days=31):
    range_start = timezone.now().date() - datetime.timedelta(days=days)
    range_end = timezone.now().date()

    for date in reversed(dateperiod(range_start, range_end)):
        with transaction.atomic():
            UserAccountDayStat.objects.filter(date=date).update(payment=Decimal('0.00'))

            payments = AccountPayment.objects.filter(date=date)
            for payment in payments:
                total_paid = AccountPayment.objects.filter(account=payment.account).aggregate(total_paid=Sum('amount'))
                account = Account.objects.select_for_update().get(pk=payment.account.id)
                account.total_paid = total_paid['total_paid']
                account.save()

                account_manager = account.get_manager_on_date(date)
                campaign = account.get_all_campaigns().first()

                UserAccountDayStat.objects.update_or_create(
                    date=date,
                    account_id=account.id,
                    user_id=account_manager.id if account_manager else None,
                    campaign_id=campaign.id if campaign else None,
                    defaults={'payment': payment.amount},
                )
