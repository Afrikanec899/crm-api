import random
import time

from django.core.management.base import BaseCommand

from facebook_business import FacebookAdsApi
from facebook_business.adobjects.business import Business
from facebook_business.adobjects.user import User as FBUser
from faker import Faker

from core.models.core import Account
from core.tasks import share_mla_profile


class Command(BaseCommand):
    help = ''

    def handle(self, *args, **options):
        accounts = Account.objects.filter(mla_profile_id__isnull=False, manager__isnull=False).exclude(
            status=Account.BANNED
        )
        for account in accounts:
            if account.manager.mla_group_id:
                share_mla_profile.delay(account_id=account.id, shareto_id=account.manager_id)
