from django.core.management.base import BaseCommand
from django.utils import timezone

from facebook_business import FacebookAdsApi
from facebook_business.adobjects.leadgenform import LeadgenForm

from core.tasks import (
    CreateAds,
    get_fb_adaccounts_task,
    get_fb_ads_task,
    get_fb_businesses,
    get_fb_day_stats_task,
    get_fb_pages,
    load_bills,
    load_fb_leads,
    load_payment_methods,
)


class Command(BaseCommand):
    help = ''

    def add_arguments(self, parser):
        parser.add_argument("-d", "--days", action="store", dest="days", type=int, help="Days", default=0)

    def handle(self, *args, **options):
        since = int(timezone.now().timestamp())
        FacebookAdsApi.init(
            api_version='v8.0',
            access_token="EAABsbCS1iHgBAHKYqexLDZByupao4pgvsn0GLy9ZBlFT0F5n06i9qv6ZC28fea6HKSad7mXa7OUsPfUHzw2IeFVMMBa41cQPsKQvooBwYCBydOZBxykAQ78WvWazt5KspAOZCMbLKc64IK6u7m3XHdaonIJECcJRdZBZBSPZB3n9FwZDZD",
        )
        form = LeadgenForm(fbid=180630016929251)
        params = {
            'filtering': [{'field': 'time_created', 'operator': 'GREATER_THAN_OR_EQUAL', 'value': since,}],
        }
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
        if leads:
            print(leads)

        # get_fb_pages()
        # load_fb_leads()
        # get_fb_businesses()
        # get_fb_adaccounts_task()
        # get_fb_ads_task()
        # load_payment_methods()

        # CreateAds().run(57)
        # upload_rule(account_id=3, rule_id=14)
        # get_fb_spends_task()
        # check_fb_token_task()
        # get_user_fb_spends_task()
        # get_fb_day_stats_task()
        # check_ad_comments()
        # print('CALL load bills')
        # load_bills()
