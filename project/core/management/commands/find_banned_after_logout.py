import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.tasks import Account, AccountLog


class Command(BaseCommand):
    help = 'Find banned accs after logout'

    def add_arguments(self, parser):
        parser.add_argument("-d", "--days", action="store", dest="days", type=int, help="Days", default=30)

    def handle(self, *args, **options):
        start_at = (timezone.now() - datetime.timedelta(days=options['days'])).date()
        print(f'Looking for banned accs from {start_at}')
        status_log = AccountLog.objects.filter(
            log_type=AccountLog.STATUS, status=Account.BANNED, start_at__date__gte=start_at
        )
        for log in status_log:
            if AccountLog.objects.filter(
                account=log.account, log_type=AccountLog.STATUS, status=Account.LOGOUT, end_at=log.start_at
            ).exists():
                print(log.account.display_name)

        #
        # accounts = Account.objects.filter(status=Account.BANNED, id__in=list(log), supplier_id=16, id__gte=1000)
        # total_paid = 0
        #
        # need_paid = 0
        # for account in accounts:
        #     days = account.age.days
        #     full_weeks = account.age.days // 7
        #     if account.age.days / 7 > full_weeks:
        #         x = account.age.days / 7 - full_weeks
        #         if x > 0.14:
        #             full_weeks += 1
        #     paid = full_weeks * 100
        #     total_paid += paid
        #     need_paid += days * 14.29
        #
        #     print(account)
        #     print('Current paid ', paid)
        #     print('Per day paid', days * 14.29)
        #
        # print('Total paid', total_paid)
        # print('Daily paid', need_paid)
