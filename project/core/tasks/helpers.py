import csv
import datetime
import json
import logging
import os
import random
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional, Union

from django.conf import settings
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models.aggregates import Sum
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import capfirst, slugify

import facebook
import requests
from dateutil.parser import parse
from facebook_business import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount as FBAdAccount
from facebook_business.adobjects.adsinsights import AdsInsights
from facebook_business.adobjects.business import Business
from facebook_business.adobjects.leadgenform import LeadgenForm
from facebook_business.adobjects.user import User as FBUser
from facebook_business.exceptions import FacebookRequestError
from faker import Faker
from redis import Redis
from unidecode import unidecode

from api.v1.serializers.leads import LeadgenLeadValidateSerializer
from core.models.core import (
    Account,
    AccountPayment,
    Ad,
    AdAccount,
    AdAccountCreditCard,
    AdAccountDayStat,
    AdAccountTransaction,
    BusinessManager,
    BusinessShareUrl,
    Campaign,
    CampaignDayStat,
    Country,
    Domain,
    FBPage,
    LeadgenLead,
    Link,
    LinkGroup,
    Notification,
    ShortifyDomain,
    User,
    UserAccountDayStat,
    UserAdAccountDayStat,
    UserCampaignDayStat,
    UserDayStat,
)
from core.utils import func_attempts
from XCardAPI.api import XCardAPI

redis = Redis(host='redis', db=0, decode_responses=True)
logger = logging.getLogger('celery.task')

FacebookAdsApi.HTTP_DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/80.0.3987.87 Safari/537.36'
}


# Маппинг имен полей в фейсбук лидформе в поля модели (для разных языков ФБ ставит свои имена)
FB_LEADGEN_FIELD_MAP = {
    # all
    'e-mail': 'email',
    'genre': 'gender',  # TODO: remove, это фикс залитых кривых лидформ
    # en
    'full_name': 'name',
    'phone_number': 'phone',
    # fr
    'numéro_de_téléphone': 'phone',
    'prénom_et_nom': 'name',
    # IT
    'numero_di_telefono': 'phone',
    'nome_e_cognome': 'name',
    # SE
    'telefonnummer': 'phone',
    'för-_och_efternamn': 'name',
    'e-post': 'email',
    # PT
    'número_de_telefone': 'phone',
    'nome_completo': 'name',
}

FB_LEADGEN_GENDER_MAP = {'male': 1, 'female': 0, 'männlich': 1, 'weiblich': 0}

# Маппинг стран-кодов телефонов, которые фб неправильно добавляет
FB_COUNTRY_PHONE_MAP = {
    'FR': '+330',
    'IT': '+390',
    'DK': '+450',
    'BE': '+320',
    'CZ': '+420',
    'GB': '+440',
    'ES': '+340',
    'SE': '+460',
    'US': '+10',
    'FI': '+3580',
    'PT': '+3510',
}
COUNTRY_PHONE = {
    'FR': '+33',
    'IT': '+39',
    'DK': '+45',
    'BE': '+32',
    'ES': '+34',
    'GB': '+44',
    'SE': '+46',
    'FI': '+358',
    'CZ': '+420',
    'US': '+1',
    'PT': '+351',
}


def fb_login(session, email, password):
    '''
   Attempt to login to Facebook. Returns cookies given to a user
   after they successfully log in.
   '''

    # Attempt to login to Facebook
    response = session.post(
        'https://m.facebook.com/login.php', data={'email': email, 'pass': password}, allow_redirects=False
    )

    assert response.status_code == 302
    assert 'c_user' in response.cookies
    return response.cookies


def create_card(fin_account, external_id):
    certs_path = settings.ROOT_DIR.path('.certs')
    api = XCardAPI(
        login=fin_account.params['login'],
        password=fin_account.params['login'],
        partner_id=fin_account.params['partner_id'],
        ca_certs=os.path.join(certs_path, fin_account.params['certs']['ca_certs']),
        cert_file=os.path.join(certs_path, fin_account.params['certs']['cert_file']),
        key_file=os.path.join(certs_path, fin_account.params['certs']['key_file']),
        key_password=fin_account.params['key_password'],
        is_dev=settings.DEBUG,
    )
    faker = Faker(locale='pl_PL')
    gender = random.choice(['male', 'female'])

    first_name = getattr(faker, f'first_name_{gender}')()
    last_name = getattr(faker, f'last_name_{gender}')()

    params = {
        'product_id': 'ccPurchaseCardMCUSD',
        'currency': 'USD',
        'external_id': external_id,
        'first_name': first_name,
        'last_name': last_name,
        'gender': 'M' if gender == 'male' else 'F',
        'date_of_birth': faker.date_of_birth(minimum_age=21),
        'address1': f'{faker.street_name()} {faker.building_number()}',
        'city': faker.city(),
        'post_code': faker.postcode(),
        'country_code': 'PL',
        'mobile_country': '48',
        'mobile_number': faker.phone_number().replace('+48', '').replace(' ', ''),
        'email': faker.email(),
        'name_on_card': unidecode(f'{first_name} {last_name}').upper(),
        'state': faker.region(),
    }
    response = api.create_virtual_card(**params)
    return response.data()


def attach_card(adaccount, number, cvv, exp_month, exp_year):
    account = adaccount.account
    if account.fb_access_token:
        card_url = f'https://graph.secure.facebook.com/ajax/payment/token_proxy.php?tpe=/v3.2/act_{adaccount.adaccount_id}/credit_cards'
        headers = {
            'content-type': 'application/x-www-form-urlencoded',
            'user-agent': None,
        }
        proxies = account.proxy_config
        data = {
            'creditCardNumber': number,
            'csc': cvv,
            'expiry_month': exp_month,
            'expiry_year': f'20{exp_year}',
            'auth_mode': 'support_tricky_bin',
            'payment_type': 'ads_invoice',
            'access_token': account.fb_access_token,
        }
        response = requests.post(card_url, data=data, headers=headers, proxies=proxies)
        # logger.error(
        #     'Card error', exc_info=True, extra={'code': response.status_code, 'text': response.text, 'url': card_url,}
        # )
        return response
    return None


def load_account_adaccounts(account):
    try:
        crm_adaccounts = account.adaccounts.filter(deleted_at__isnull=True)

        FacebookAdsApi.init(access_token=account.fb_access_token, proxies=account.proxy_config)
        user = FBUser(fbid='me')
        adaccounts = user.get_ad_accounts(
            fields=[
                'name',
                'business{id}',
                'account_id',
                'balance',
                'amount_spent',
                'age',
                'account_status',
                'disable_reason',
                'adspixels{name,id}',
                'adtrust_dsl',
                'currency',
                'timezone_name',
                'timezone_offset_hours_utc',
                'adspaymentcycle{threshold_amount}',
            ]
        )
        fb_adaccounts = []
        for adaccount in adaccounts:
            # print(adaccount)
            fb_adaccounts.append(int(adaccount['account_id']))

            if adaccount['age']:
                age = adaccount['age'] * 24 * 60 * 60  # возраст в секундах
                created_at = timezone.now() - datetime.timedelta(milliseconds=age)
            else:
                created_at = timezone.now()

            pixels = adaccount.get('adspixels', {}).get('data')
            business: Optional[BusinessManager] = None
            if adaccount.get('business'):
                business = BusinessManager.objects.filter(business_id=adaccount['business']['id']).first()
                if not business:
                    continue
            # не через update_or_create и подобное, потому что недостаточно контроля
            payment_cycle = None
            if 'adspaymentcycle' in adaccount:
                payment_cycle = Decimal(adaccount['adspaymentcycle']['data'][0]['threshold_amount']) / Decimal('100')

            balance = (Decimal(adaccount.get('balance', '0.00')) / 100).quantize(Decimal('0.01'))
            adaccount_data = {
                'account': account,
                'manager': account.manager,
                'adaccount_id': int(adaccount['account_id']),
                'name': adaccount['name'],
                'balance': balance,
                'payment_cycle': payment_cycle,
                'amount_spent': (Decimal(adaccount['amount_spent']) / 100).quantize(Decimal('0.01')),
                'status': adaccount['account_status'],
                'disable_reason': adaccount.get('disable_reason'),
                'pixels': pixels,
                'limit': adaccount['adtrust_dsl'],
                'currency': adaccount['currency'],
                'timezone_name': adaccount['timezone_name'],
                'timezone_offset_hours_utc': adaccount['timezone_offset_hours_utc'],
            }

            if business is not None:
                adaccount_data['business_id'] = business.id
            try:
                adaccount_obj = AdAccount.objects.get(adaccount_id=int(adaccount['account_id']))
                adaccount_data['deleted_at'] = None
                AdAccount.update(pk=adaccount_obj.id, action_verb='updated adaccount', **adaccount_data)
            except AdAccount.DoesNotExist:
                AdAccount.create(created_at=created_at, **adaccount_data)

        removed_adaccounts = crm_adaccounts.exclude(adaccount_id__in=fb_adaccounts)
        if removed_adaccounts.exists():
            # for removed_adaccount in removed_adaccounts:
            #     # Шлем админу сообщение
            #     message = render_to_string(
            #         'accounts/business_removed.html', {'account': account, 'business': removed_adaccount}
            #     )
            #     data = {'message': message, 'account_id': account.id}
            #
            #     recipients = User.get_recipients(roles=[User.ADMIN, User.MANAGER, User.FINANCIER])
            #     for recipient in recipients:
            #         Notification.create(
            #             recipient=recipient,
            #             level=Notification.CRITICAL,
            #             category=Notification.ACCOUNT,
            #             data=data,
            #             sender=None,
            #         )
            removed_adaccounts.update(deleted_at=timezone.now())
    except FacebookRequestError as e:
        if e.api_error_code() == 190:
            Account.update(pk=account.id, action_verb='cleared token', fb_access_token=None)


def load_account_ads(account):
    FacebookAdsApi.init(access_token=account.fb_access_token, proxies=account.proxy_config, api_version='v9.0')
    for adaccount_obj in account.adaccounts.filter(status=AdAccount.FB_ACTIVE, deleted_at__isnull=True):
        try:
            adaccount = FBAdAccount(fbid=f'act_{adaccount_obj.adaccount_id}')
            params = {
                'fields': [
                    'account_id',
                    'name',
                    'status',
                    'created_time',
                    'effective_status',
                    'ad_review_feedback',
                    'creative_link_url',
                    'creative.fields(effective_object_story_id,object_story_spec)',
                ]
            }
            ads = adaccount.get_ads(params=params)
            for ad in ads:
                ad_url = ad.get('creative_link_url')
                ad_data = {
                    'story_id': ad.get('creative', {}).get('effective_object_story_id'),
                    'name': ad['name'].replace('"', ''),
                    'status': ad['status'],
                    'effective_status': ad['effective_status'],
                    'creative_id': int(ad['creative']['id']),
                    'ad_url': ad_url,
                    'created_at': ad['created_time'],
                }

                if 'ad_review_feedback' in ad:
                    ad_review_feedback = ad['ad_review_feedback'].export_all_data()
                    ad_data['ad_review_feedback'] = ad_review_feedback

                    ad_review_feedback_data = ad_review_feedback[list(ad_review_feedback.keys())[0]]

                    ad_data['ad_review_feedback_code'] = list(ad_review_feedback_data.keys())[0]
                    ad_data['ad_review_feedback_text'] = list(ad_review_feedback_data.values())[0]
                else:
                    ad_data['ad_review_feedback'] = None
                    ad_data['ad_review_feedback_code'] = None
                    ad_data['ad_review_feedback_text'] = None

                if ad.get('creative', {}).get('effective_object_story_id'):
                    page_id = int(ad['creative']['effective_object_story_id'].split('_')[0])
                    page = FBPage.objects.filter(page_id=page_id).first()
                    if page:
                        ad_data['page_id'] = page.id
                try:
                    ad_obj = Ad.objects.get(adaccount=adaccount_obj, ad_id=ad['id'])
                    Ad.update(pk=ad_obj.id, action_verb='updated ad', **ad_data)
                except Ad.DoesNotExist:
                    Ad.create(adaccount=adaccount_obj, ad_id=ad['id'], **ad_data)

        except FacebookRequestError as e:
            logger.error(e, exc_info=True)
            if e.api_error_code() == 190:
                Account.update(pk=account.id, action_verb='cleared token', fb_access_token=None)


def process_ad_comments(account, page):
    graph = facebook.GraphAPI(access_token=page.access_token, version="8.0", proxies=account.proxy_config)

    for ad in page.ads.filter(status='ACTIVE', effective_status='ACTIVE', disable_check=False, story_id__isnull=False):
        if ad.adaccount.status == AdAccount.FB_ACTIVE:
            try:
                params = {
                    'connection_name': 'comments',
                    'limit': 500,
                    'summary': True,
                    'filter': 'stream',
                    'order': 'reverse_chronological',
                    'fields': 'id,can_hide,is_hidden,from,likes',
                }

                last_check: Optional[Union[bytes, str]] = redis.get(f'last_check::{ad.story_id}')
                if last_check:
                    params['since'] = last_check
                else:
                    params['since'] = (timezone.now() - datetime.timedelta(days=1)).isoformat()
                # Ставим на 10 минут раньше, чтобы интервалы пересекались
                # на случай длинной проверки или долгих запросов
                last_check = (timezone.now() - datetime.timedelta(minutes=10)).isoformat()

                comments = graph.get_connections(id=ad.story_id, **params)

                redis.delete(f'total_fails_{ad.story_id}')
                total_count = comments.get('summary', {}).get('total_count', 0)
                ad.total_comments = total_count

                ad.save(update_fields=['total_comments'])

                last_total_count = redis.get(f'last_total_count::{ad.story_id}') or 0
                last_total_count = int(last_total_count)

                if last_total_count != total_count:
                    has_errors = False
                    if comments.get('data'):
                        for comment in comments.get('data', []):
                            likes = comment.get('likes', {}).get('data', [])
                            liked_by_page = False

                            if likes:
                                like_ids = [int(like['id']) for like in likes]
                                if page.page_id in like_ids:
                                    liked_by_page = True

                            if not likes or not liked_by_page:
                                if not comment.get('is_hidden'):
                                    if comment.get('can_hide'):
                                        try:
                                            graph.request(comment['id'], post_args={'is_hidden': True}, method='POST')
                                        except Exception as e:
                                            has_errors = True
                                            logger.error(
                                                f'Cant hide comment for acc {account.display_name}',
                                                exc_info=True,
                                                extra={
                                                    'error': e,
                                                    'comment': comment,
                                                    'account': account.display_name,
                                                    'page': page.name,
                                                    'story_id': ad.story_id,
                                                },
                                            )

                        if not has_errors:
                            redis.set(f'last_check::{ad.story_id}', last_check)
                            redis.set(f'last_total_count::{ad.story_id}', total_count)
                # else:
                #     redis.set(f'last_check::{ad.story_id}', last_check)

            except facebook.GraphAPIError as e:
                logger.error(
                    f'Cant check ads comments for acc {account.display_name}',
                    exc_info=True,
                    extra={'error': e, 'account': account.display_name, 'story_id': ad.story_id, 'page': page.name},
                )
                if e.code == 100 and e.error_subcode == 33:
                    redis.incr(f'total_fails_{ad.story_id}', 1)
                    total_fails = redis.get(f'total_fails_{ad.story_id}')
                    if total_fails and int(total_fails) > 3:
                        ad.disable_check = True
                        ad.save(update_fields=['disable_check'])
                        redis.delete(f'total_fails_{ad.story_id}')

                elif e.code == 368 and e.error_subcode == 3252001:
                    cache.set(f'comments_blocked_{account.id}_{page.id}', '1', 3600)

                elif e.code == 190:
                    Account.update(pk=account.id, action_verb='cleared token', fb_access_token=None)


def load_share_urls(business):
    try:
        FacebookAdsApi.init(
            access_token=business.account.fb_access_token, proxies=business.account.proxy_config, api_version='v8.0'
        )
        bm = Business(fbid=business.business_id)
        pending_users = bm.get_pending_users(
            fields=['email', 'invite_link', 'status', 'role', 'created_time', 'expiration_time']
        )
        for pending_user in pending_users:
            if pending_user.get('invite_link'):
                # TODO: classmethod
                BusinessShareUrl.objects.update_or_create(
                    business=business,
                    share_id=pending_user['id'],
                    defaults={
                        'url': pending_user['invite_link'],
                        'email': pending_user['email'],
                        'status': pending_user['status'],
                        'role': pending_user['role'],
                        'created_at': pending_user['created_time'],
                        'expire_at': pending_user['expiration_time'],
                    },
                )
    except FacebookRequestError as e:
        if e.api_error_code() == 190:
            Account.update(pk=business.account.id, action_verb='cleared token', fb_access_token=None)


def load_account_businesses(account):
    try:
        crm_businesses = account.businesses.filter(deleted_at__isnull=True)
        FacebookAdsApi.init(access_token=account.fb_access_token, proxies=account.proxy_config)
        user = FBUser(fbid='me')

        businesses = user.get_businesses(fields=['created_time', 'name', 'id', 'can_create_ad_account'])
        fb_businesses = []
        for business in businesses:
            fb_businesses.append(business['id'])
            business_data = {
                'account': account,
                'manager': account.manager,
                'name': business['name'],
                'created_at': parse(business['created_time']).astimezone(tz=settings.TZ),
                'can_create_ad_account': business['can_create_ad_account'],
            }

            try:
                business = BusinessManager.objects.get(business_id=business['id'])
                BusinessManager.update(pk=business.id, action_verb='updated Business Manager', **business_data)
            except BusinessManager.DoesNotExist:
                BusinessManager.create(business_id=business['id'], **business_data)

        # TODO: перенести в модель после теста
        removed_businesses = crm_businesses.exclude(business_id__in=fb_businesses)
        if removed_businesses.exists():
            for removed_business in removed_businesses:
                # Шлем админу сообщение
                message = render_to_string(
                    'accounts/business_removed.html', {'account': account, 'business': removed_business}
                )
                data = {'message': message, 'account_id': account.id}

                recipients = User.get_recipients(roles=[User.ADMIN, User.MANAGER, User.FINANCIER])
                for recipient in recipients:
                    Notification.create(
                        recipient=recipient,
                        level=Notification.CRITICAL,
                        category=Notification.ACCOUNT,
                        data=data,
                        sender=None,
                    )
                # Шлем менеджеру акка, что БМ грохнули
                if account.manager:
                    Notification.create(
                        recipient=account.manager,
                        level=Notification.CRITICAL,
                        category=Notification.ACCOUNT,
                        data=data,
                        sender=None,
                    )

            removed_businesses.update(deleted_at=timezone.now())

    except FacebookRequestError as e:
        if e.api_error_code() == 190:
            Account.update(pk=account.id, action_verb='cleared token', fb_access_token=None)
        # elif e.api_error_code() == 100 and e.api_error_subcode() == 33:
        #     pass
        # else:
        #     logger.error(e, exc_info=True)


def load_leadgen_leads(leadgen, since=None):
    # int(leadgen.last_load.timestamp())
    try:
        country_code = leadgen.leadgen.name.split('|')[0].strip()
        try:
            offer = leadgen.leadgen.name.split('|')[1].strip()
        except IndexError:
            offer = None
        country_code = country_code.upper()
        country, _ = Country.objects.get_or_create(code=country_code[:2], defaults={'name': country_code})
    except ValueError as e:
        logger.error(e, exc_info=True)
        country_code = None
        country = None
        offer = None

    if leadgen.page.account.fb_access_token:
        # 9.0 не работает - отдает пустой ответ
        FacebookAdsApi.init(
            api_version='v8.0',
            access_token=leadgen.page.account.fb_access_token,
            proxies=leadgen.page.account.proxy_config,
        )
        form = LeadgenForm(fbid=leadgen.leadform_id)
        last_load = timezone.now()
        if since is not None:
            params = {
                'filtering': [{'field': 'time_created', 'operator': 'GREATER_THAN_OR_EQUAL', 'value': since,}],
            }
        else:
            params = {}
        try:
            print(params)
            leads = form.get_leads(
                params=params,
                fields=[
                    'created_time',
                    'field_data',
                    'id',
                    'ad_id',
                    'ad_name',
                    'adset_id',
                    'adset_name',
                    'campaign_id',
                    'campaign_name',
                    'custom_disclaimer_responses',
                    'partner_name',
                    'form_id',
                    'is_organic',
                    'platform',
                ],
            )
            print(leads)
            if leads:
                for lead in leads:
                    data = {}
                    for field in lead['field_data']:
                        data[FB_LEADGEN_FIELD_MAP.get(field['name'], field['name'])] = field['values'][0]

                    if data.get('phone'):
                        data['phone'] = data['phone'].replace(' ', '')

                    if 'gender' in data:
                        data['gender'] = FB_LEADGEN_GENDER_MAP.get(data['gender'].lower())

                    # FB сам дописывает номера телефонов, надо заменить лишнее
                    fb_country_phone = FB_COUNTRY_PHONE_MAP.get(country_code)
                    if fb_country_phone:
                        if data.get('phone', '').startswith(fb_country_phone):
                            country_phone = COUNTRY_PHONE.get(country_code)
                            data['phone'] = data['phone'].replace(fb_country_phone, country_phone)

                    if data.get('phone'):
                        prefix = COUNTRY_PHONE[country.code]
                        if not data['phone'].startswith(prefix):
                            if data['phone'].startswith(f'00{prefix[1:]}') or data['phone'].startswith(
                                f'0{prefix[1:]}0'
                            ):
                                data['phone'] = data['phone'][4:]
                                data['phone'] = f"{prefix}{data['phone']}"
                            elif data['phone'].startswith('+0'):
                                data['phone'] = data['phone'][2:]
                                data['phone'] = f"{prefix}{data['phone']}"
                            elif data['phone'].startswith('0') or data['phone'].startswith('1'):
                                data['phone'] = data['phone'][1:]
                                data['phone'] = f"{prefix}{data['phone']}"
                            elif data['phone'].startswith(prefix[1:]):
                                data['phone'] = f"+{data['phone']}"
                            elif data['phone'].startswith('+'):
                                pass
                            else:
                                data['phone'] = f"{prefix}{data['phone']}"
                        elif data['phone'].startswith(f'{prefix}0'):
                            data['phone'] = data['phone'].replace(f'{prefix}0', f'{prefix}')

                    # if data.get('phone', '').startswith('0'):
                    #     country_phone = COUNTRY_PHONE.get(country_code)
                    #     data['phone'] = data['phone'].replace(data['phone'][0], country_phone, 1)

                    lead_created_time = parse(lead['created_time']).astimezone(tz=settings.TZ)

                    defaults = {
                        'created_at': lead_created_time,
                        'raw_data': lead.export_all_data(),
                        'country': country,
                        'country_code': country_code,
                        'offer': offer,
                        **data,
                    }
                    updated = LeadgenLead.objects.filter(
                        lead_id=lead['id'],
                        page=leadgen.page,
                        account=leadgen.page.account,
                        leadgen=leadgen.leadgen,
                        user=leadgen.page.account.get_manager_on_date(lead_created_time.date()),
                        leadform_id=lead['form_id'],
                    ).update(**defaults)

                    if not updated:
                        LeadgenLead.objects.create(
                            lead_id=lead['id'],
                            page=leadgen.page,
                            account=leadgen.page.account,
                            leadgen=leadgen.leadgen,
                            user=leadgen.page.account.get_manager_on_date(lead_created_time.date()),
                            leadform_id=lead['form_id'],
                            **defaults,
                        )
                leadgen.last_load = last_load
                leadgen.save(update_fields=['last_load'])

        except FacebookRequestError as e:
            if e.api_error_code() == 190:
                Account.update(pk=leadgen.page.account.id, action_verb='cleared token', fb_access_token=None)


def load_account_pages(account):
    try:
        graph = facebook.GraphAPI(access_token=account.fb_access_token, version="8.0", proxies=account.proxy_config)
        pages = graph.get_object(id='me', fields="accounts{access_token,id,name,is_published}")
        crm_pages = account.fbpage_set.filter(deleted_at__isnull=True)
        fb_pages = []
        if pages and pages.get('accounts'):
            pages_list = pages["accounts"]["data"]
            for page in pages_list:
                fb_pages.append(page['id'])
                page_data = {
                    "access_token": page["access_token"],
                    "name": page["name"],
                    'is_published': page['is_published'],
                    'deleted_at': None,
                }
                try:
                    page_obj = FBPage.objects.get(account=account, page_id=page['id'])
                    FBPage.update(pk=page_obj.id, action_verb='Page updated', **page_data)
                except FBPage.DoesNotExist:
                    FBPage.create(account=account, page_id=page['id'], **page_data)

        removed_pages = crm_pages.exclude(page_id__in=fb_pages)
        if removed_pages.exists():
            removed_pages.update(deleted_at=timezone.now())

    except facebook.GraphAPIError as e:
        if e.code == 190:
            Account.update(pk=account.id, action_verb='cleared token', fb_access_token=None)


def load_account_day_stats(account, range_start, range_end, reload=False):
    FacebookAdsApi.init(access_token=account.fb_access_token, proxies=account.proxy_config)
    adaccounts = AdAccount.objects.filter(account=account, deleted_at__isnull=True)
    for adaccount_obj in adaccounts:
        try:
            adaccount = FBAdAccount(fbid=f'act_{adaccount_obj.adaccount_id}')
            params = {
                'time_range': {'since': range_start.strftime('%Y-%m-%d'), 'until': range_end.strftime('%Y-%m-%d')},
                'limit': 100,
                'level': 'account',
                'fields': ['spend', 'clicks'],
                'time_increment': 1,
            }
            stats = adaccount.get_insights(params=params)
            for stat in stats:
                process_adaccount_stat_v2(account, adaccount_obj, stat, reload)
        except FacebookRequestError as e:
            if e.api_error_code() == 190:
                Account.update(pk=account.id, action_verb='cleared token', fb_access_token=None)


def create_fan_page(account: Account, data):
    FacebookAdsApi.init(access_token=account.fb_access_token, proxies=account.proxy_config)
    user = FBUser(fbid='me').api_get()

    query_params = {
        "input": {
            "name": capfirst(data['name']),
            "category": data['category'],
            "client_mutation_id": "345345345345345",
            "actor_id": user['id'],
        }
    }

    request_data = {
        'access_token': account.fb_access_token,
        'oss_response_format': 1,
        'oss_request_format': 1,
        'query_id': 1505614726115470,
        'locale': 'ru_RU',
        'strip_nulls': 1,
        'strip_defaults': 1,
        'query_params': json.dumps(query_params),
    }

    url = 'https://graph.facebook.com/graphql'
    headers = {'content-type': 'application/x-www-form-urlencoded'}
    page_data = requests.post(url, data=request_data, headers=headers, proxies=account.proxy_config)
    if page_data.status_code != 200:
        raise FacebookRequestError(
            'Facebook Error',
            request_context={},
            http_status=page_data.status_code,
            http_headers=headers,
            body=request_data,
        )

    page = page_data.json().get('data', {}).get('page_create', {}).get('page')
    if page and 'id' in page:
        from .facebook import upload_page_avatar

        upload_page_avatar.delay(
            image_id=data['image'][0].id,
            page_token=page['admin_info']['access_token'],
            page_id=page['id'],
            account_id=account.id,
        )
        #
        # image = UploadedImage.objects.get(id=data['image'][0].id)
        # FacebookAdsApi.init(access_token=page['admin_info']['access_token'], proxies=account.proxy_config)
        #
        # fb_page = Page(fbid=page['id'])
        # try:
        #     fb_page.create_picture(params={'filename': image.file.path})
        # except FacebookRequestError as e:
        #     if e.api_error_code() != 100:
        #         raise e
    else:
        raise Exception('Can\'t create Page')


def load_adaccount_payment_methods(adaccount: AdAccount):
    FacebookAdsApi.init(access_token=adaccount.account.fb_access_token, proxies=adaccount.account.proxy_config)
    try:
        fb_adaccount = FBAdAccount(fbid=f'act_{adaccount.adaccount_id}').api_get(
            fields=[
                "all_payment_methods{pm_credit_card{credential_id,credit_card_address,credit_card_type,"
                "display_string,exp_month,exp_year,first_name,is_verified,last_name,middle_name,time_created}}"
            ]
        )
        if fb_adaccount.get('all_payment_methods'):
            card_data = fb_adaccount.get('all_payment_methods', {}).get('pm_credit_card', {}).get('data', [])[0]
            if card_data:
                payment_method_data = {
                    'display_string': card_data['display_string'].replace(' ', ''),
                    'created_at': parse(card_data['time_created']).astimezone(tz=settings.TZ),
                    'credential_id': int(card_data['credential_id']),
                }

                adaaccount_credit_card = AdAccountCreditCard.objects.filter(
                    credential_id=card_data['credential_id'], adaccount=adaccount
                ).first()
                if not adaaccount_credit_card:
                    adaaccount_credit_card = AdAccountCreditCard.create(adaccount=adaccount, **payment_method_data,)
                return adaaccount_credit_card
        return None

    except FacebookRequestError as e:
        if e.api_error_code() == 190:
            Account.update(pk=adaccount.account.id, action_verb='cleared token', fb_access_token=None)
        # elif e.api_error_code() == 100 and e.api_error_subcode() == 33:
        #     pass
        else:
            logger.error(e, exc_info=True)

    return None


def load_account_payment_methods(account):
    FacebookAdsApi.init(access_token=account.fb_access_token, proxies=account.proxy_config)
    for adaccount_obj in account.adaccounts.filter(deleted_at__isnull=True):
        try:
            adaccount = FBAdAccount(fbid=f'act_{adaccount_obj.adaccount_id}').api_get(
                fields=[
                    "all_payment_methods{pm_credit_card{credential_id,credit_card_address,credit_card_type,"
                    "display_string,exp_month,exp_year,first_name,is_verified,last_name,middle_name,time_created}}"
                ]
            )
            if adaccount.get('all_payment_methods'):
                card_data = adaccount.get('all_payment_methods', {}).get('pm_credit_card', {}).get('data', [])[0]
                if card_data:
                    payment_method_data = {
                        'display_string': card_data['display_string'].replace(' ', ''),
                        'created_at': parse(card_data['time_created']).astimezone(tz=settings.TZ),
                        'credential_id': int(card_data['credential_id']),
                    }

                    if not AdAccountCreditCard.objects.filter(
                        credential_id=card_data['credential_id'], adaccount=adaccount_obj
                    ).exists():
                        AdAccountCreditCard.create(
                            adaccount=adaccount_obj, **payment_method_data,
                        )

        except FacebookRequestError as e:
            if e.api_error_code() == 190:
                Account.update(pk=account.id, action_verb='cleared token', fb_access_token=None)
            # elif e.api_error_code() == 100 and e.api_error_subcode() == 33:
            #     pass
            else:
                logger.error(e, exc_info=True)


def load_account_transactions(account):
    FacebookAdsApi.init(access_token=account.fb_access_token, proxies=account.proxy_config)
    adaccounts = account.adaccounts.filter(deleted_at__isnull=True)

    for adaccount_obj in adaccounts:
        try:
            bills_load_at = timezone.now()
            adaccount = FBAdAccount(fbid=f'act_{adaccount_obj.adaccount_id}')
            params = {}
            if adaccount_obj.billed_to is not None:
                params['time_start'] = adaccount_obj.billed_to

            for fb_transaction in adaccount.get_transactions(params=params):
                details = adaccount.get_transaction_details(
                    fields=['metadata'],
                    params={'transaction_keys': [f'{fb_transaction["id"]}_{fb_transaction["tx_type"]}']},
                )[0]['metadata']
                # print(details)
                adaccount_card = AdAccountCreditCard.objects.filter(
                    adaccount=adaccount_obj, credential_id=details.get('payment_method_id')
                ).first()
                # print(adaccount_card)
                if adaccount_card:
                    _, created = AdAccountTransaction.objects.update_or_create(
                        adaccount=adaccount_obj,
                        transaction_id=fb_transaction['id'],
                        defaults={
                            'adaccount_card': adaccount_card,
                            'card': adaccount_card.card,
                            'tx_type': fb_transaction['tx_type'],
                            'amount': Decimal(fb_transaction['amount']['total_amount_in_hundredths']) / Decimal('100'),
                            'currency': fb_transaction['amount']['currency'],
                            'start_at': datetime.datetime.fromtimestamp(
                                fb_transaction['billing_start_time'], tz=settings.TZ
                            ),
                            'end_at': datetime.datetime.fromtimestamp(
                                fb_transaction['billing_end_time'], tz=settings.TZ
                            ),
                            'start_at_ts': fb_transaction['billing_start_time'],
                            'end_at_ts': fb_transaction['billing_end_time'],
                            'billed_at': datetime.datetime.fromtimestamp(fb_transaction['time'], tz=settings.TZ),
                            'reason': fb_transaction.get('billing_reason'),
                            'charge_type': fb_transaction['charge_type'],
                            'product_type': fb_transaction.get('product_type'),
                            'payment_option': fb_transaction['payment_option'],
                            'status': fb_transaction['status'],
                            'tracking_id': fb_transaction.get('tracking_id'),
                            'transaction_type': fb_transaction.get('transaction_type'),
                            'vat_invoice_id': fb_transaction.get('vat_invoice_id'),
                            'data': fb_transaction.export_all_data(),
                        },
                    )

                    if created:
                        adaccount_card.recalc_spends()
                        if adaccount_card.card is not None:
                            adaccount_card.card.recalc_spends()

            AdAccount.update(pk=adaccount_obj.id, action_verb='Success load bills', bills_load_at=bills_load_at)
        except FacebookRequestError as e:
            if e.api_error_code() == 190:
                Account.update(pk=account.id, action_verb='cleared token', fb_access_token=None)
            # elif e.api_error_code() == 100 and e.api_error_subcode() == 33:
            #     pass
            # else:
            #     logger.error(e, exc_info=True)


def process_campaign_stat(stats_data: Dict[str, Any], date: datetime.date, reload=False):
    campaign = Campaign.objects.filter(campaign_id=stats_data['id']).first()
    print(campaign)
    if campaign:
        stats = {
            'leads': stats_data['conversions'],
            'clicks': stats_data['clicks'],
            'visits': stats_data['visits'],
            'revenue': stats_data['revenue'],
            'cost': stats_data['cost'],
            'profit': stats_data['profit'],
        }
        if not reload:
            # Получаем стату с предыдущей проверки
            prev_stats = redis.get(f'campaign_day_stats_{campaign.id}_{date}')
            if prev_stats is None:
                prev_stats = defaultdict(lambda: '0')
            else:
                prev_stats = json.loads(prev_stats)
        else:
            prev_stats = defaultdict(lambda: '0')

        # считаем разницу статы для записи в базу
        diff = {
            'leads': stats['leads'] - int(prev_stats['leads']),
            'clicks': stats['clicks'] - int(prev_stats['clicks']),
            'visits': stats['visits'] - int(prev_stats['visits']),
            'revenue': Decimal(stats['revenue']) - Decimal(prev_stats['revenue']),
            'cost': Decimal(stats['cost']) - Decimal(prev_stats['cost']),
            'profit': Decimal(stats['profit']) - Decimal(prev_stats['profit']),
        }
        print(diff)
        if any(diff.values()):
            manager = campaign.get_manager_on_date(date)
            with transaction.atomic():
                # Записываем сырые данные из трекера
                CampaignDayStat.objects.update_or_create(campaign=campaign, date=date, defaults=stats)

                UserCampaignDayStat.upsert(
                    date=date,
                    campaign_id=campaign.id,
                    user_id=manager.id if manager else None,
                    clicks=diff['clicks'],
                    visits=diff['visits'],
                    leads=diff['leads'],
                    revenue=diff['revenue'],
                    cost=diff['cost'],
                    profit=diff['profit'],
                )

                UserAccountDayStat.upsert(
                    date=date,
                    account_id=campaign.get_account().id if campaign.get_account() else None,
                    user_id=manager.id if manager else None,
                    campaign_id=campaign.id,
                    clicks=diff['clicks'],
                    visits=diff['visits'],
                    leads=diff['leads'],
                    cost=diff['cost'],
                    revenue=diff['revenue'],
                    profit=diff['profit'],
                    funds=Decimal('0.00'),
                    spend=Decimal('0.00'),
                    payment=Decimal('0.00'),
                )
                UserDayStat.upsert(
                    date=date,
                    account_id=campaign.adaccounts.all().first().account_id
                    if campaign.adaccounts.all().exists()
                    else None,
                    adaccount_id=None,
                    user_id=manager.id if manager else None,
                    campaign_id=campaign.id,
                    clicks=diff['clicks'],
                    visits=diff['visits'],
                    leads=diff['leads'],
                    cost=diff['cost'],
                    revenue=diff['revenue'],
                    profit=diff['profit'],
                    funds=Decimal('0.00'),
                    spend=Decimal('0.00'),
                    payment=Decimal('0.00'),
                )
            # Обновляем предыдущую стату в кеше
            redis.set(f'campaign_day_stats_{campaign.id}_{date}', json.dumps(stats, cls=DjangoJSONEncoder))


def process_adaccount_stat(account: Account, adaccount: AdAccount, stat: AdsInsights, reload=False):
    date = datetime.datetime.strptime(stat['date_start'], '%Y-%m-%d').date()
    if not reload:
        prev_stats = redis.get(f'adaccount_day_stats_{adaccount.id}_{date}')

        if prev_stats is None:
            prev_stats = defaultdict(lambda: '0')
        else:
            prev_stats = json.loads(prev_stats)
    else:
        prev_stats = defaultdict(lambda: '0')

    clicks = int(stat.get('clicks', '0')) - int(prev_stats['clicks'])
    spend = Decimal(stat.get('spend', '0.00')) - Decimal(prev_stats['spend'])

    # Если есть спенд, но карты нет - шлем алерт
    if spend:
        adaccount_card = AdAccountCreditCard.objects.filter(adaccount=adaccount, card__isnull=False)
        if (
            not adaccount_card.exists()
            # or adaccount_card.filter(card__number__isnull=True).exists()
            and account.manager_id not in [38, 39]
        ):
            # and not account.card_number and not account.financial_comment and account.manager_id not in [38, 39]:
            message = render_to_string(
                'ads/unexpected_spend.html',
                {'adaccount': adaccount, 'account': account, 'spend': stat.get('spend'), 'date': date},
            )
            data = {'message': message, 'account_id': account.id, 'adaccount_id': adaccount.id}

            recipients = User.get_recipients(roles=[User.FINANCIER])
            for recipient in recipients:
                Notification.create(
                    recipient=recipient,
                    level=Notification.CRITICAL,
                    category=Notification.ADACCOUNT,
                    data=data,
                    sender=None,
                )

    if any([clicks, spend]):
        account_manager = account.get_manager_on_date(date)
        with transaction.atomic():
            # Храним сырые данные
            AdAccountDayStat.objects.update_or_create(
                account=account,
                adaccount=adaccount,
                date=date,
                defaults={'clicks': stat.get('clicks', 0), 'spend': stat.get('spend', 0.0)},
            )

            UserAdAccountDayStat.upsert(
                date=date,
                account_id=account.id,
                adaccount_id=adaccount.id,
                user_id=account_manager.id if account_manager else None,
                spend=spend,
                clicks=clicks,
            )

            UserAccountDayStat.upsert(
                date=date,
                account_id=account.id,
                user_id=account_manager.id if account_manager else None,
                campaign_id=adaccount.campaign_id if adaccount.campaign_id else account.campaign_id,
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

    stat_data = {'clicks': int(stat.get('clicks', '0')), 'spend': Decimal(stat.get('spend', '0.00'))}
    redis.set(f'adaccount_day_stats_{adaccount.id}_{date}', json.dumps(stat_data, cls=DjangoJSONEncoder))


def process_adaccount_stat_v2(account: Account, adaccount: AdAccount, stat: AdsInsights, reload=False):
    date = datetime.datetime.strptime(stat['date_start'], '%Y-%m-%d').date()
    adaccount_manager = adaccount.get_manager_on_date(date) or account.manager
    account_manager = account.get_manager_on_date(date)
    with transaction.atomic():
        stats, _ = AdAccountDayStat.objects.get_or_create(
            account=account, adaccount=adaccount, date=date, defaults={'clicks': 0, 'spend': 0}
        )

        prev_stats, current_stats = AdAccountDayStat.update(
            pk=stats.pk, clicks=int(stat.get('clicks', '0')), spend=Decimal(stat.get('spend', '0.00'))
        )

        if reload:
            clicks = current_stats.clicks
            spend = current_stats.spend
        else:
            clicks = current_stats.clicks - prev_stats.clicks
            spend = current_stats.spend - prev_stats.spend
        # print(clicks, spend)
        # Если есть спенд, но карты нет - шлем алерт
        if spend and not reload:
            adaccount_card = AdAccountCreditCard.objects.filter(adaccount=adaccount, card__isnull=False)
            if not adaccount_card.exists():
                # and not account.card_number and not account.financial_comment and account.manager_id not in [38, 39]:
                message = render_to_string(
                    'ads/unexpected_spend.html',
                    {'adaccount': adaccount, 'account': account, 'spend': stat.get('spend'), 'date': date},
                )
                data = {'message': message, 'account_id': account.id, 'adaccount_id': adaccount.id}

                recipients = User.get_recipients(roles=[User.FINANCIER])
                for recipient in recipients:
                    Notification.create(
                        recipient=recipient,
                        level=Notification.CRITICAL,
                        category=Notification.ADACCOUNT,
                        data=data,
                        sender=None,
                    )

        if any([clicks, spend]):
            UserAdAccountDayStat.upsert(
                date=date,
                account_id=account.id,
                adaccount_id=adaccount.id,
                user_id=adaccount_manager.id if adaccount_manager else None,
                spend=spend,
                clicks=clicks,
            )

            UserAccountDayStat.upsert(
                date=date,
                account_id=account.id,
                user_id=account_manager.id if account_manager else None,
                campaign_id=adaccount.campaign_id if adaccount.campaign_id else None,
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

            UserDayStat.upsert(
                date=date,
                account_id=adaccount.account.id,
                adaccount_id=adaccount.id,
                user_id=adaccount_manager.id if adaccount_manager else None,
                campaign_id=None,
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


def import_leads_csv(import_task):
    total_leads = 0
    invalid_leads = 0
    batch_size = 5000
    with open(import_task.file.path) as f:
        data = csv.DictReader(f, delimiter=',')
        try:
            batch = []
            for line in data:
                lead_data = {
                    'email': line.get('email'),
                    'first_name': line.get("first_name"),
                    'last_name': line.get("last_name"),
                    'name': line.get('name'),
                    'city': line.get('city'),
                    'zip': line.get('zip'),
                    'address': line.get('address'),
                    'offer': line.get('offer'),
                }
                if not lead_data['name'] and line.get("first_name") and line.get("last_name"):
                    lead_data['name'] = f'{line.get("first_name")} {line.get("last_name")}'

                if 'date' in line:
                    try:
                        lead_data['created_at'] = parse(line.get('date'))  # dayfirst=True
                    except Exception as e:
                        logger.error(e, exc_info=True)

                phone = line.get('phone')
                if phone:
                    phone = phone.replace(' ', '')
                    phone = phone.replace('-', '')

                if 'country' in line:
                    try:
                        country_id = cache.get(f'country_id_{line["country"].upper()}')
                        country_code = cache.get(f'country_code_{line["country"].upper()}')
                        if not country_id or not country_code:
                            country, _ = Country.objects.get_or_create(
                                code=line['country'].upper(), defaults={'name': line['country']}
                            )
                            cache.set(f'country_id_{line["country"].upper()}', country.id)
                            cache.set(f'country_code_{line["country"].upper()}', country.code)

                            lead_data['country'] = country.id
                            lead_data['country_code'] = country.code
                        else:
                            lead_data['country'] = country_id
                            lead_data['country_code'] = country_code

                        if phone:
                            prefix = COUNTRY_PHONE[lead_data['country_code']]
                            if not phone.startswith(prefix):
                                if phone.startswith(f'00{prefix[1:]}') or phone.startswith(f'0{prefix[1:]}0'):
                                    phone = phone[4:]
                                    phone = f"{prefix}{phone}"
                                elif phone.startswith('+0'):
                                    phone = phone[2:]
                                    phone = f"{prefix}{phone}"
                                elif phone.startswith('0') or phone.startswith('1'):
                                    phone = phone[1:]
                                    phone = f"{prefix}{phone}"
                                elif phone.startswith(prefix[1:]):
                                    phone = f"+{phone}"
                                elif phone.startswith('+'):
                                    pass
                                else:
                                    phone = f"{prefix}{phone}"
                            elif phone.startswith(f'{prefix}0'):
                                phone = phone.replace(f'{prefix}0', f'{prefix}')

                    except Exception as e:
                        logger.error(e, exc_info=True)

                lead_data['phone'] = str(phone)

                serializer = LeadgenLeadValidateSerializer(data=lead_data)

                if serializer.is_valid():
                    if any(list(lead_data.values())):
                        # if not LeadgenLead.objects.filter(**serializer.validated_data).exists():
                        lead = LeadgenLead(**serializer.validated_data, raw_data=line)
                        batch.append(lead)
                        total_leads += 1
                        if len(batch) >= batch_size:
                            LeadgenLead.objects.bulk_create(batch)
                            batch = []
                        # else:
                        #     invalid_leads += 1
                else:
                    logger.error(
                        'Invalid lead data', extra={'lead_data': lead_data, 'errors': serializer.errors}, exc_info=True
                    )
                    invalid_leads += 1
            if batch:
                LeadgenLead.objects.bulk_create(batch)

            import_task.status = 2
            import_task.save(update_fields=['status'])

            message = render_to_string(
                'tools/leads_import_success.html', {'total_leads': total_leads, 'invalid_leads': invalid_leads},
            )
            data = {'message': message}
            recipient = import_task.user
            Notification.create(
                recipient=recipient, level=Notification.WARNING, category=Notification.ACCOUNT, data=data, sender=None,
            )

        except Exception as e:
            message = render_to_string('tools/leads_import_error.html', {'error': repr(e)[:256]})
            data = {'message': message}

            recipient = import_task.user
            Notification.create(
                recipient=recipient, level=Notification.WARNING, category=Notification.ACCOUNT, data=data, sender=None,
            )
            logger.error('Import leads error', extra={'e': e}, exc_info=True)
            import_task.status = 3
            import_task.save(update_fields=['status'])


def import_payments_csv(import_task):
    total_accounts = 0
    total_paid_amount = Decimal('0.00')

    try:
        with open(import_task.file.path) as f:
            data = csv.DictReader(f, delimiter=',')
            for line in data:
                account_id = line.get('account_id')
                account = Account.objects.filter(id=account_id).first()
                if account:
                    total_accounts += 1
                    with transaction.atomic():
                        date = parse(line.get('date'), dayfirst=True).date()
                        amount = line.get('amount')
                        AccountPayment.objects.update_or_create(
                            account=account, date=date, defaults={'amount': amount, 'user': import_task.user,}
                        )
                        total_paid_amount += Decimal(amount)
                        total_paid = AccountPayment.objects.filter(account=account).aggregate(total_paid=Sum('amount'))
                        account = Account.objects.select_for_update().get(pk=account.id)
                        account.total_paid = total_paid['total_paid']
                        account.save()

                        account_manager = account.get_manager_on_date(date)
                        campaign = account.get_all_campaigns().first()

                        UserAccountDayStat.objects.update_or_create(
                            date=date,
                            account_id=account.id,
                            user_id=account_manager.id if account_manager else None,
                            campaign_id=campaign.id if campaign else None,
                            defaults={'payment': amount,},
                        )

        import_task.status = 2
        import_task.save(update_fields=['status'])

        message = render_to_string(
            'accounts/payments_import_success.html',
            {'total_accounts': total_accounts, 'total_paid': total_paid_amount},
        )
        data = {'message': message}

        recipient = import_task.user
        Notification.create(
            recipient=recipient, level=Notification.WARNING, category=Notification.ACCOUNT, data=data, sender=None,
        )

    except Exception as e:
        message = render_to_string('accounts/payments_import_error.html', {'error': repr(e)})
        data = {'message': message}

        recipient = import_task.user
        Notification.create(
            recipient=recipient, level=Notification.WARNING, category=Notification.ACCOUNT, data=data, sender=None,
        )
        logger.error('Import payments error', extra={'e': e}, exc_info=True)
        import_task.status = 3
        import_task.save(update_fields=['status'])


def create_broadcast_file(group):
    batch_size = 1000
    links = Link.objects.filter(group=group).prefetch_related('leadgen_lead')
    if links.exists():
        headers = {'X-API-Key': settings.SHORTIFY_API_KEY}
        filename = slugify(group.name, allow_unicode=True)
        filename = f'{filename}_{group.created_at.strftime("%d.%m.%Y_%H:%M:%S")}.csv'

        base_directory = os.path.join(settings.MEDIA_ROOT, 'broadcasts', str(group.user_id))
        Path(base_directory).mkdir(parents=True, exist_ok=True)
        full_path = os.path.join(base_directory, filename)

        with open(full_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile, delimiter=';', quoting=csv.QUOTE_ALL)
            writer.writerow(['name', 'email', 'phone', 'url', 'zip', 'city'])
            data = []
            csv_rows = []
            for link in links:
                cleared_name = unidecode(link.leadgen_lead.full_name)
                csv_rows.append(
                    [
                        cleared_name,
                        link.leadgen_lead.email,
                        link.leadgen_lead.phone,
                        link.short_url,
                        link.leadgen_lead.zip,
                        link.leadgen_lead.city,
                    ]
                )
                data.append({'key': link.key, 'url': link.url})
                if len(data) >= batch_size:
                    writer.writerows(csv_rows)
                    func_attempts(requests.post, f'{settings.SHORTIFY_URL}/update_cache', headers=headers, json=data)
                    data = []
                    csv_rows = []

            if data or csv_rows:
                writer.writerows(csv_rows)
                func_attempts(requests.post, f'{settings.SHORTIFY_URL}/update_cache', headers=headers, json=data)

        LinkGroup.objects.filter(pk=group.id).update(
            status=LinkGroup.SUCCESS,
            status_comment=None,
            total_links=links.count(),
            csv=os.path.join('broadcasts', str(group.user_id), filename),
        )
    else:
        LinkGroup.objects.filter(pk=group.id).update(
            status=LinkGroup.SUCCESS, status_comment=None, total_links=links.count()
        )


def check_banned_urls(urls, type='tracker'):
    data = {
        'client': {'clientId': 'voluumchecker', 'clientVersion': '1.0'},
        'threatInfo': {
            'platformTypes': ['ANY_PLATFORM', 'WINDOWS', 'ANDROID', 'IOS', 'CHROME', 'PLATFORM_TYPE_UNSPECIFIED'],
            'threatEntries': [{'url': url} for url in urls],
            'threatEntryTypes': ['URL'],
            'threatTypes': [
                'MALWARE',
                'SOCIAL_ENGINEERING',
                'THREAT_TYPE_UNSPECIFIED',
                'UNWANTED_SOFTWARE',
                'POTENTIALLY_HARMFUL_APPLICATION',
            ],
        },
    }
    url = 'https://safebrowsing.googleapis.com/v4/threatMatches:find?key={}'.format(settings.GOOGLE_API_KEY)

    response = func_attempts(requests.post, url, data=json.dumps(data))
    if response.status_code == 200:
        response = response.json()
        matches = response.get('matches', [])
        if matches:
            matched_urls = [x['threat']['url'] for x in matches]
            matched_urls = list(set(matched_urls))
            if matched_urls:
                domains = [url.split('//')[1].replace('/', '') for url in matched_urls]
                if type == 'tracker':
                    Domain.objects.filter(name__in=domains).update(is_banned=True)
                elif type == 'shortify':
                    ShortifyDomain.objects.filter(domain__in=domains).update(is_banned=True)
                # Шлем админу и тимлиду сообщение
                message = render_to_string('core/domain_banned.html', {'domains': domains})
                data = {'message': message}

                recipients = User.get_recipients(roles=[User.ADMIN, User.TEAMLEAD])
                for recipient in recipients:
                    Notification.create(
                        recipient=recipient,
                        level=Notification.WARNING,
                        category=Notification.SYSTEM,
                        data=data,
                        sender=None,
                    )
    else:
        raise Exception(response.status_code)
