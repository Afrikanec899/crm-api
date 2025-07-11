from decimal import Decimal

from django.db.models.aggregates import Sum
from django.utils import timezone

from redis import Redis

from core.models.core import Account, UserAccountDayStat, AdAccount
from project.celery_app import app

redis = Redis(host='redis', db=0, decode_responses=True)


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5, 'countdown': 2})
def create_card_and_attach(self, adaccount_id: int) -> None:
    adaccount = AdAccount.objects.get(id=adaccount_id)
    account = Account.objects.get(id=adaccount.account_id)

    total_spend = UserAccountDayStat.objects.filter(account=account).aggregate(total_spend=Sum('spend'))
    total_spend = total_spend['total_spend'] or Decimal('0')

    spend = account.total_spends - total_spend
    if spend:
        date = timezone.now().date()
        account_manager = account.get_manager_on_date(date)
        campaign = account.get_all_campaigns().first()

        # TODO: размазать на кампании
        UserAccountDayStat.upsert(
            date=date,
            account_id=account.id,
            user_id=account_manager.id if account_manager else None,
            campaign_id=campaign.id if campaign else None,
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
