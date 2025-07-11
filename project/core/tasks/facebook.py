import datetime
import json
import logging
import random
import time
from typing import Any, Dict, List

from django.core.cache import cache
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

import pytz
import requests
from celery import Task
from dateutil import parser
from facebook_business import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount as FBAdAccount
from facebook_business.adobjects.page import Page
from facebook_business.adobjects.user import User as FBUser
from facebook_business.exceptions import FacebookRequestError
from redis import Redis

from project.celery_app import app

from ..models.core import (
    Account,
    AdAccount,
    AdAccountDayStat,
    AdsCreateTask,
    BusinessManager,
    FBPage,
    Leadgen,
    Notification,
    PageLeadgen,
    Rule,
    UploadedImage,
    UploadedVideo,
    UserAccountDayStat,
    UserAdAccountDayStat,
    UserCampaignDayStat,
)
from ..utils import func_attempts
from .helpers import (
    load_account_adaccounts,
    load_account_ads,
    load_account_businesses,
    load_account_day_stats,
    load_account_pages,
    load_account_payment_methods,
    load_account_transactions,
    load_leadgen_leads,
    load_share_urls,
    process_ad_comments,
    process_adaccount_stat,
)

redis = Redis(host='redis', db=0, decode_responses=True)
logger = logging.getLogger('celery.task')

FacebookAdsApi.HTTP_DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/80.0.3987.87 Safari/537.36'
}


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def load_account_fb_data(self, account_id: int) -> None:
    get_fb_pages.delay(account_id=account_id)
    get_fb_adaccounts_task.delay(account_id=account_id)
    load_payment_methods.delay(account_id=account_id)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def load_account_businesses_task(self, account_id: int):
    account = Account.objects.get(id=account_id)
    func_attempts(load_account_businesses, account)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def get_fb_businesses(self, account_id: int = None) -> None:
    accounts = Account.objects.filter(fb_access_token__isnull=False).exclude(
        Q(status__in=[Account.LOGOUT, Account.BANNED]) | Q(fb_access_token='')
    )
    if account_id is not None:
        accounts = accounts.filter(id=account_id)

    for account in accounts:
        load_account_businesses_task.delay(account.id)
        # Делаем небольшую паузу, чтобы разгрузить RabbitMQ
        time.sleep(0.1)
        # load_account_businesses_task(account.id)
        # pool.spawn(func_attempts, load_account_businesses, account).link_exception(exception_callback)
        # try:
        #     func_attempts(load_account_businesses, account)
        # # pool.join()
        # except Exception as e:
        #     logger.error(e, exc_info=True)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 1})
def update_share_bm_url(self, business_id: int = None) -> None:
    businesses = BusinessManager.objects.filter(
        deleted_at__isnull=True, account__fb_access_token__isnull=False
    ).exclude(Q(account__status__in=[Account.LOGOUT, Account.BANNED]) | Q(account__fb_access_token=''))

    if business_id is not None:
        businesses = businesses.filter(id=business_id)

    for business in businesses:
        load_share_urls(business)

        if not business.share_urls.filter(
            status='PENDING', role='ADMIN', expire_at__gte=timezone.now() - datetime.timedelta(days=10)
        ).exists():

            try:
                business.create_share_url()
            except FacebookRequestError as e:
                if e.api_error_code() not in [10, 100]:
                    logger.error(e, exc_info=True)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def get_fb_pages(self, account_id: int = None) -> None:
    accounts = Account.objects.filter(fb_access_token__isnull=False).exclude(
        Q(status__in=[Account.LOGOUT, Account.BANNED]) | Q(fb_access_token='')
    )
    if account_id is not None:
        accounts = accounts.filter(id=account_id)

    for account in accounts:
        try:
            func_attempts(load_account_pages, account)
        except Exception as e:
            logger.error(e, exc_info=True)


@app.task
def check_ad_comments(account_id: int = None) -> None:
    accounts = (
        Account.objects.filter(fb_access_token__isnull=False, status=Account.ACTIVE)
        .exclude(Q(status__in=[Account.LOGOUT, Account.BANNED]) | Q(fb_access_token=''))
        .exclude(manager_id__in=[38, 39])
    )
    if account_id is not None:
        accounts = accounts.filter(id=account_id)

    for account in accounts:
        for page in account.fbpage_set.filter(is_published=True, deleted_at__isnull=True):
            if not cache.get(f'comments_blocked_{account.id}_{page.id}'):
                check_account_page_comments.delay(account.id, page.id)
                # Делаем небольшую паузу, чтобы разгрузить RabbitMQ
                time.sleep(0.2)
        #     try:
        #         func_attempts(process_ad_comments, account, page)
        #     except Exception as e:
        #         logger.error(e, exc_info=True)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def check_account_page_comments(self, account_id, page_id) -> None:
    account = Account.objects.get(id=account_id)
    page = FBPage.objects.get(id=page_id)
    process_ad_comments(account, page)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 1, 'countdown': 5})
def get_fb_ads_task(self, account_id: int = None) -> None:
    accounts = Account.objects.filter(fb_access_token__isnull=False).exclude(
        Q(status__in=[Account.LOGOUT, Account.BANNED]) | Q(fb_access_token='')
    )
    if account_id is not None:
        accounts = accounts.filter(id=account_id)

    for account in accounts:
        get_accounts_ads_task.delay(account.id)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 1, 'countdown': 5})
def get_accounts_ads_task(self, account_id: int = None) -> None:
    account = Account.objects.get(id=account_id)
    load_account_ads(account)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 1, 'countdown': 5})
def get_fb_adaccounts_task(self, account_id: int = None) -> None:
    accounts = Account.objects.filter(fb_access_token__isnull=False).exclude(
        Q(status__in=[Account.LOGOUT, Account.BANNED]) | Q(fb_access_token='')
    )
    if account_id is not None:
        accounts = accounts.filter(id=account_id)

    for account in accounts:
        get_account_adaccounts_task.delay(account.id)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 1, 'countdown': 5})
def get_account_adaccounts_task(self, account_id):
    account = Account.objects.get(id=account_id)
    load_account_adaccounts(account)


@app.task
def get_fb_day_stats_task(account_id: int = None, days: int = 1) -> None:
    accounts = Account.objects.filter(fb_access_token__isnull=False).exclude(
        Q(status__in=[Account.LOGOUT, Account.BANNED]) | Q(fb_access_token='')
    )
    if account_id is not None:
        accounts = accounts.filter(id=account_id)

    # range_start = timezone.now().date() - datetime.timedelta(days=days)
    # range_end = timezone.now().date()

    for account in accounts:
        get_fb_account_day_stats_task.delay(account.id, days)
        # Делаем небольшую паузу, чтобы разгрузить RabbitMQ
        time.sleep(0.1)
        # if range_start < account.created_at.date():
        #     range_start = account.created_at.date()
        # try:
        #     load_account_day_stats(account, range_start, range_end)
        #     # Пересчитываем стату
        #     account.recalc_spends()
        # except Exception as e:
        #     logger.error(e, exc_info=True)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 5})
def get_fb_account_day_stats_task(self, account_id, days: int = 1) -> None:
    account = Account.objects.get(id=account_id)

    range_start = timezone.now().date() - datetime.timedelta(days=days)
    if range_start < account.created_at.date():
        range_start = account.created_at.date()

    range_end = timezone.now().date()
    load_account_day_stats(account, range_start, range_end)
    account.recalc_spends()


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 5})
def reload_account_fb_stats_task(self, account_id, days) -> None:
    """
    Запускается из админки и загружает и обновляет всю стату по акку
    Предварительно надо стату грохнуть руками
    """
    accounts = Account.objects.filter(id=account_id, fb_access_token__isnull=False).exclude(
        Q(status__in=[Account.LOGOUT, Account.BANNED]) | Q(fb_access_token='')
    )

    range_start = timezone.now().date() - datetime.timedelta(days=days)
    range_end = timezone.now().date()

    for account in accounts:
        if range_start < account.created_at.date():
            range_start = account.created_at.date()

        FacebookAdsApi.init(access_token=account.fb_access_token, proxies=account.proxy_config)
        adaccounts = AdAccount.objects.filter(account=account)
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
                    process_adaccount_stat(account, adaccount_obj, stat, reload=True)
            except FacebookRequestError as e:
                if e.api_error_code() == 190:
                    Account.update(pk=account.id, action_verb='cleared token', fb_access_token=None)
            except Exception as e:
                logger.error(e, exc_info=True)

        # Пересчитываем стату
        account.recalc_spends()


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 5})
def clear_account_stats_task(self, account_id) -> None:
    """
    Запускается из админки и загружает и обновляет всю стату по акку
    Предварительно надо стату грохнуть руками
    """
    account = Account.objects.get(id=account_id)
    campaigns = account.get_all_campaigns()

    AdAccountDayStat.objects.filter(account=account).delete()
    UserAdAccountDayStat.objects.filter(account=account).delete()
    UserAccountDayStat.objects.filter(account=account).delete()
    UserCampaignDayStat.objects.filter(campaign__in=campaigns).delete()
    # Пересчитываем стату
    account.recalc_spends()


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def load_account_payment_methods_task(self, account_id: int):
    account = (
        Account.objects.filter(id=account_id, fb_access_token__isnull=False)
        .exclude(Q(status__in=[Account.LOGOUT, Account.BANNED]) | Q(fb_access_token=''))
        .first()
    )
    if account:
        func_attempts(load_account_payment_methods, account)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def load_payment_methods(self, account_id: int = None) -> None:
    accounts = Account.objects.filter(fb_access_token__isnull=False).exclude(
        Q(status__in=[Account.LOGOUT, Account.BANNED]) | Q(fb_access_token='')
    )
    if account_id is not None:
        accounts = accounts.filter(id=account_id)
    # pool = Pool(20)
    for account in accounts:
        load_account_payment_methods_task.delay(account.id)
        time.sleep(0.1)

        # try:
        #     # pool.spawn(func_attempts, load_account_payment_methods, account).link_exception(exception_callback)
        #     func_attempts(load_account_payment_methods, account)
        # #     pool.join()
        # except Exception as e:
        #     logger.error(e, exc_info=True)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def load_account_transactions_task(self, account_id: int):
    account = (
        Account.objects.filter(id=account_id, fb_access_token__isnull=False)
        .exclude(Q(status__in=[Account.LOGOUT, Account.BANNED]) | Q(fb_access_token=''))
        .first()
    )
    if account:
        func_attempts(load_account_transactions, account)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def load_bills(self, account_id: int = None) -> None:
    accounts = Account.objects.filter(fb_access_token__isnull=False).exclude(
        Q(status__in=[Account.LOGOUT, Account.BANNED]) | Q(fb_access_token='')
    )
    if account_id is not None:
        accounts = accounts.filter(id=account_id)

    # pool = Pool(20)
    for account in accounts:
        load_account_transactions_task.delay(account.id)
        time.sleep(0.1)
        # pool.spawn(func_attempts, load_account_transactions, account).link_exception(exception_callback)
        # try:
        #     func_attempts(load_account_transactions, account)
        # # pool.join()
        # except Exception as e:
        #     logger.error(e, exc_info=True)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def upload_page_avatar(self, page_id, page_token, image_id, account_id):
    try:
        account = Account.objects.get(id=account_id)
        image = UploadedImage.objects.get(id=image_id)
        FacebookAdsApi.init(access_token=page_token, proxies=account.proxy_config)

        fb_page = Page(fbid=page_id)
        fb_page.create_picture(params={'filename': image.file.path})
    except FacebookRequestError as e:
        if e.api_error_code() == 100:
            pass


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def load_fb_leads(self, page_leadgen_id: int = None, is_full=False):
    leadgens = PageLeadgen.objects.filter(page__account__fb_access_token__isnull=False).exclude(
        Q(page__account__status__in=[Account.LOGOUT, Account.BANNED]) | Q(page__account__fb_access_token='')
    )
    if page_leadgen_id is not None:
        leadgens = leadgens.filter(id=page_leadgen_id)

    for leadgen in leadgens:
        since = None
        try:
            if leadgen.last_load is not None and not is_full:
                since = int(leadgen.last_load.timestamp())
            func_attempts(load_leadgen_leads, leadgen, since)
        except Exception as e:
            print(e)
            logger.error(e, exc_info=True)


class CreateAds(Task):
    name = 'create_ads'
    acks_late = False

    def __init__(self):
        self.campaign_ids = []
        self.adset_ids = []
        self.ad_ids = []
        self.rule = None
        self.tracking_specs = None

    def get_pixel_id(self):
        if not self.adaccount.get('pixel'):
            pixels = self.fbadaccount.get_ads_pixels(fields=['id'])
            if pixels:
                return pixels[0]['id']
            else:
                return self.fbadaccount.create_ads_pixel(params={'name': f'Pixel #{random.randint(1, 100)}'})['id']
        return self.adaccount['pixel']

    def get_adset_link_clicks_params(self, adset_params, **kwargs):
        """
            No additional params for lick_clicks objective
        """
        pixel_id = self.get_pixel_id()
        self.tracking_specs = {"action.type": ["offsite_conversion"], "fb_pixel": [pixel_id]}
        return adset_params

    def get_adset_lead_generation_params(self, adset_params, **kwargs):
        pixel_id = self.get_pixel_id()
        self.tracking_specs = {"action.type": ["offsite_conversion"], "fb_pixel": [pixel_id]}

        adset_params['promoted_object'] = {'page_id': self.page.page_id}
        return adset_params

    def get_adset_page_likes_params(self, adset_params, **kwargs):
        adset_params['promoted_object'] = {'page_id': self.page.page_id}
        # Исключаем тех, кто уже лайкнул
        adset_params['targeting']["excluded_connections"] = [{"id": self.page.page_id}]
        return adset_params

    def get_adset_conversions_params(self, adset_params, custom_event_type):
        pixel_id = self.get_pixel_id()
        self.tracking_specs = {"action.type": ["offsite_conversion"], "fb_pixel": [pixel_id]}
        adset_params['attribution_spec'] = [
            {"event_type": "CLICK_THROUGH", "window_days": 1},
            {"event_type": "VIEW_THROUGH", "window_days": 1},
        ]
        adset_params['promoted_object'] = {
            'pixel_id': pixel_id,
            'custom_event_type': custom_event_type,
        }
        return adset_params

    def create_campaign(self, has_schedule=False):
        campaign_params = {
            'name': f'{self.data["name"]}|{self.adaccount_obj.name}',
            'objective': self.objective,
            'status': 'ACTIVE',
            'special_ad_categories': 'NONE',
            'bid_strategy': 'LOWEST_COST_WITHOUT_CAP',
        }
        if has_schedule:
            campaign_params['pacing_type'] = ['day_parting']

        if self.adaccount.get('daily_budget'):
            campaign_params['daily_budget'] = int(float(self.adaccount['daily_budget']) * 100)
        elif self.adaccount.get('lifetime_budget'):
            campaign_params['lifetime_budget'] = int(float(self.adaccount['lifetime_budget']) * 100)

        campaign = self.fbadaccount.create_campaign(params=campaign_params)
        self.campaign_ids.append(campaign['id'])
        return campaign['id']

    def make_fb_schedule(self, schedule: Dict[str, Any]) -> List[Dict[str, Any]]:
        adset_schedule = []
        for day, hours in schedule.items():
            for start, end in hours:
                schedule_data = {
                    'start_minute': start * 60,
                    'end_minute': (end + 1) * 60,
                    'days': [int(day)],
                }
                adset_schedule.append(schedule_data)
        return adset_schedule

    def create_adset(self, data, campaign_id):
        # print('ADSET:', data)
        data['targeting']['geo_locations']["location_types"] = ["home"]  # Те, кто живут
        data['targeting']["brand_safety_content_filter_levels"] = ["FACEBOOK_STANDARD", "AN_STANDARD"]

        adset_params = {
            'name': f'{data["name"]}|{self.adaccount_obj.name}',
            'campaign_id': campaign_id,
            'optimization_goal': data['optimization_goal'],
            'targeting': data['targeting'],
            'status': 'ACTIVE',
            'billing_event': 'IMPRESSIONS',
        }

        if data.get('start_time'):
            tz = pytz.timezone(self.timezone)
            adset_params['start_time'] = parser.parse(data['start_time']).astimezone(tz).isoformat()

        if data.get('end_time'):
            tz = pytz.timezone(self.timezone)
            adset_params['end_time'] = parser.parse(data['end_time']).astimezone(tz).isoformat()

        if data.get('schedule'):
            adset_params['adset_schedule'] = self.make_fb_schedule(data['schedule'])

        adset_params = getattr(self, f'get_adset_{self.objective.lower()}_params')(
            adset_params, custom_event_type=data.get('custom_event_type')
        )

        fb_adset = self.fbadaccount.create_ad_set(params=adset_params)

        self.adset_ids.append(fb_adset['id'])
        return fb_adset['id']

    def create_video_creative(self, ad_data, thumbnail):
        # Video креатив
        video_obj = UploadedVideo.objects.get(id=ad_data['videos'][0])

        video = self.uploaded_videos.get(video_obj.id)
        if not video:
            video = func_attempts(self.fbadaccount.create_ad_video, params={'source': video_obj.file.path})
            # Ждем, пока загрузится и обработается но не больше 30 секунд
            while True:
                step = 0
                video = func_attempts(video.api_get, fields=['status', 'id'])
                if video['status']['video_status'] == 'ready' or step >= 30:
                    self.uploaded_videos[video_obj.id] = video
                    break
                step += 1
                time.sleep(1)

        video_data = {
            'video_id': video['id'],
            'image_hash': thumbnail,
            "message": ad_data.get('message'),  # Primary Text
            "call_to_action": {'type': ad_data['call_to_action']},
        }

        if self.objective == 'PAGE_LIKES':
            video_data['call_to_action']['value'] = {'page': self.page.page_id}
        elif self.objective == 'LEAD_GENERATION':
            video_data['title'] = ad_data.get('headline')  # Headline
            video_data["link_description"] = ad_data.get('description')  # Description
            video_data['call_to_action']['value'] = {'lead_gen_form_id': self.leadgen_id}
        else:
            video_data['title'] = ad_data.get('headline')  # Headline
            video_data["link_description"] = ad_data.get('description')  # Description
            video_data['call_to_action']['value'] = {
                "link_caption": ad_data.get('caption'),
                'link': ad_data.get('link'),
                "link_format": "VIDEO_LPP",
            }

        creative_params = {
            'object_story_spec': {'page_id': self.page.page_id, 'video_data': video_data},
        }
        return creative_params

    def create_photo_creative(self, ad_data, image):
        link_data: Dict[str, Any] = {
            'image_hash': image,
            "message": ad_data.get('message'),  # Primary Text
            "attachment_style": "link",
            "call_to_action": {'type': ad_data['call_to_action']},
        }

        if self.objective == 'PAGE_LIKES':
            link_data['call_to_action']["value"] = {"page": self.page.page_id}
            # Куда ведет реклама Website url - страница
            link_data['link'] = f'https://www.facebook.com/{self.page.page_id}'

        elif self.objective == 'LEAD_GENERATION':
            link_data['call_to_action']['value'] = {'lead_gen_form_id': self.leadgen_id}
            link_data['name'] = ad_data.get('headline')  # Headline
            link_data['link'] = 'https://fb.me/'
            if ad_data.get('caption'):
                link_data["caption"] = ad_data.get('caption')  # Ссылка выводится под крео Display link
            link_data["description"] = ad_data.get('description')  # Description

        else:
            link_data['name'] = ad_data.get('headline')  # Headline
            link_data['link'] = ad_data.get('link')
            if ad_data.get('caption'):
                link_data["caption"] = ad_data.get('caption')  # Ссылка выводится под крео Display link
            link_data["description"] = ad_data.get('description')  # Description

        creative_params = {
            'object_story_spec': {'page_id': self.page.page_id, 'link_data': link_data},
        }
        return creative_params

    def create_creative(self, ad_data):
        if self.objective == 'LEAD_GENERATION':
            self.leadgen_id = self.create_leadgen(ad_data)

        image_obj = UploadedImage.objects.get(id=ad_data['images'][0])
        image = self.fbadaccount.create_ad_image(params={'filename': image_obj.file.path})
        if ad_data.get('videos'):
            creative_params = self.create_video_creative(ad_data, image['hash'])
        else:
            creative_params = self.create_photo_creative(ad_data, image['hash'])

        if 'url_tags' in ad_data:
            creative_params['url_tags'] = ad_data['url_tags']
        fb_creative = self.fbadaccount.create_ad_creative(params=creative_params)
        return fb_creative['id']

    def create_ad(self, data, adset_id):
        fb_creative_id = self.create_creative(data)

        ad_params = {
            'name': f'{data["name"]}|{self.adaccount_obj.name}',
            'adset_id': adset_id,
            'creative': {'creative_id': fb_creative_id},
            'status': 'ACTIVE',
        }
        if self.tracking_specs:
            ad_params['tracking_specs'] = self.tracking_specs

        fb_ad = self.fbadaccount.create_ad(params=ad_params)

        self.ad_ids.append(fb_ad['id'])

    def create_rule(self):
        rules = Rule.objects.filter(id__in=self.adaccount.get('rules'))
        for rule in rules:
            decimal_data = [
                'spent',
                # 'result',
                'cost_per',
                'cpm',
                'cost_per_link_click',
                'cost_per_initiate_checkout_fb',
                'link_ctr',
            ]
            for filter in rule.evaluation_spec['filters']:
                if filter['field'] in decimal_data:
                    if not isinstance(filter['value'], list):
                        value = filter['value'].replace(',', '.')
                        filter['value'] = float(value) * 100
            # Аттачим только к нужным объектам
            rule_object = {
                "operator": "IN",
            }
            if rule.entity_type == 'AD':
                rule_object['value'] = self.ad_ids
                rule_object['field'] = 'ad.id'
            elif rule.entity_type == 'ADSET':
                rule_object['value'] = self.adset_ids
                rule_object['field'] = 'adset.id'
            elif rule.entity_type == 'CAMPAIGN':
                rule_object['value'] = self.campaign_ids
                rule_object['field'] = 'campaign.id'

            rule.evaluation_spec['filters'].append(rule_object)
            rule.evaluation_spec['filters'].append(
                {"field": "attribution_window", "value": "1D_VIEW_1D_CLICK", "operator": "EQUAL"}
            )

            params = {
                'evaluation_spec': rule.evaluation_spec,
                'execution_spec': rule.execution_spec,
                'name': rule.name,
                'schedule_spec': rule.schedule_spec,
            }
            self.fbadaccount.create_ad_rules_library(params=params)

    def publish_page(self):
        FacebookAdsApi.init(access_token=self.page.access_token, proxies=self.adaccount_obj.account.proxy_config)

        fb_page = Page(fbid=self.page.page_id).api_get(fields=['is_published'])
        if not fb_page['is_published']:
            fb_page.api_update(params={'is_published': True})

    def accept_rules(self):
        try:
            FacebookAdsApi.init(
                access_token=self.adaccount_obj.account.fb_access_token,
                proxies=self.adaccount_obj.account.proxy_config,
            )
            user = FBUser(fbid='me').api_get()

            request_data = {
                'access_token': self.adaccount_obj.account.fb_access_token,
                'doc_id': '1975240642598857',
                'locale': 'ru_RU',
                'variables': json.dumps({"input": {"client_mutation_id": "1", "actor_id": user['id']}}),
            }
            url = 'https://graph.facebook.com/graphql'
            headers = {'content-type': 'application/x-www-form-urlencoded'}
            requests.post(url, data=request_data, headers=headers, proxies=self.adaccount_obj.account.proxy_config)
        except Exception as e:
            logger.error(e, exc_info=True)

    def create_leadgen(self, ad_data):
        leadgen_id = ad_data['leadform']
        form_id = self.leadgens.get(leadgen_id)
        if not form_id:
            FacebookAdsApi.init(access_token=self.page.access_token, proxies=self.adaccount_obj.account.proxy_config)
            fb_page = Page(fbid=self.page.page_id)
            page_leadgen = PageLeadgen.objects.filter(page=self.page, leadgen_id=leadgen_id).first()
            if page_leadgen:
                self.leadgens = {leadgen_id: page_leadgen.leadform_id}
                return page_leadgen.leadform_id

            leadgen = Leadgen.objects.get(id=leadgen_id)

            leadgen_params = leadgen.data
            # cover_photo = leadgen_params.pop('cover_photo', None)
            # if cover_photo:
            #     image = UploadedImage.objects.get(id=cover_photo)
            # photo = fb_page.create_photo(params={
            #     'published': True,
            #     'source': image.file.path
            # })
            #
            # photo = Photo(fbid=photo['id']).api_get(fields=['id', 'created_time'])
            # print(photo)

            # leadgen_params['cover_photo'] = image.file.path

            leadgen_params['name'] = leadgen.name
            adlink = ad_data.pop('link', leadgen_params['thank_you_page'].get('website_url'))

            leadgen_params['thank_you_page']['website_url'] = adlink
            leadgen_params['follow_up_action_url'] = adlink

            form_id = fb_page.create_lead_gen_form(params=leadgen_params)['id']
            PageLeadgen.objects.create(page=self.page, leadgen_id=leadgen_id, leadform_id=form_id)
            self.leadgens = {leadgen_id: form_id}
        return form_id

    def run(self, ads_task_id):  # adaccount, data):
        ads_task = AdsCreateTask.objects.get(id=ads_task_id)
        AdsCreateTask.update(pk=ads_task.id, status=AdsCreateTask.PROCESSING, status_comment=None)
        try:
            self.uploaded_videos = {}  # Тут в процессе залива будем хранить загруженные видео
            self.adaccount = ads_task.adaccount_data
            self.data = ads_task.campaign_data
            self.objective = self.data['objective']
            if self.objective == 'LEAD_GENERATION':
                self.leadgens = {}

            self.page = FBPage.objects.get(id=self.adaccount['page'])

            self.adaccount_obj = AdAccount.objects.get(id=self.adaccount['id'])
            self.timezone = self.adaccount_obj.timezone_name

            self.publish_page()
            self.accept_rules()

            has_schedule = True if list(filter(lambda x: x.get('schedule'), self.data['adsets'])) else False

            FacebookAdsApi.init(
                access_token=self.adaccount_obj.account.fb_access_token,
                proxies=self.adaccount_obj.account.proxy_config,
            )

            self.fbadaccount = FBAdAccount(fbid=f'act_{self.adaccount_obj.adaccount_id}')
            fb_campaign_id = self.create_campaign(has_schedule)

            for adset in self.data['adsets']:
                fb_adset_id = self.create_adset(adset, fb_campaign_id)

                for ad in adset['ads']:
                    self.create_ad(ad, fb_adset_id)

            if self.adaccount.get('rules'):
                self.create_rule()

            AdsCreateTask.update(pk=ads_task.id, status=AdsCreateTask.SUCCESS, status_comment=None)

        except FacebookRequestError as e:
            AdsCreateTask.update(
                pk=ads_task.id,
                status=AdsCreateTask.ERROR,
                status_comment=e.body()['error'].get('error_user_msg') or e.body()['error'].get('message'),
            )
            # raise e

        except Exception as e:
            logger.error(e, exc_info=True)
            AdsCreateTask.update(pk=ads_task.id, status=AdsCreateTask.ERROR, status_comment='Unknown error')
            # raise e


app.tasks.register(CreateAds())


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def stop_all_ads(self, adaccount_id: int):
    adaccount_obj = AdAccount.objects.get(id=adaccount_id)

    if not adaccount_obj.account.fb_access_token:
        return None

    FacebookAdsApi.init(
        access_token=adaccount_obj.account.fb_access_token,
        proxies=adaccount_obj.account.proxy_config,
        api_version='v9.0',
    )
    adaccount = FBAdAccount(fbid=f'act_{adaccount_obj.adaccount_id}')

    params = {'status': 'PAUSED'}

    try:
        campaigns = adaccount.get_campaigns(fields=['name'])
        for campaign in campaigns:
            campaign.api_update(params=params)

    except FacebookRequestError as e:
        logger.error(e, exc_info=True)
        if adaccount_obj.account.manager:
            # Шлем админу сообщение
            message = render_to_string(
                'ads/stop_ads_error.html', {'account': adaccount_obj.account, 'adaccount': adaccount_obj}
            )
            data = {'message': message, 'account_id': adaccount_obj.account.id, 'adaccount_id': adaccount_obj.id}
            Notification.create(
                recipient=adaccount_obj.account.manager,
                level=Notification.INFO,
                category=Notification.AD,
                data=data,
                sender=None,
            )
