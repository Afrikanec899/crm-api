from django.core.management.base import BaseCommand

from core.models.core import Account, AccountLog


class Command(BaseCommand):
    help = ''

    def handle(self, *args, **options):
        accounts = Account.objects.all()
        for account in accounts:
            account_log = AccountLog.objects.filter(log_type=0, status=account.status, account=account)
            if account_log.exists():
                if account.status in [50, 60]:  # Surfing, Warming
                    account_log = account_log.earliest('start_at')
                else:
                    account_log = account_log.latest('start_at')

                if account_log:
                    account.status_changed_at = account_log.start_at
                    account.save(update_fields=['status_changed_at'])
