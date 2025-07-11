import datetime

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from core.models.core import Account, AccountLog, User, UserRequest


class Command(BaseCommand):
    help = ''

    def add_arguments(self, parser):
        parser.add_argument("-d", "--days", action="store", dest="days", type=int, help="Days", default=0)

    def handle(self, *args, **options):
        date_from = timezone.now() - datetime.timedelta(days=options['days'])
        print(date_from)
        requested_data = {}
        approved_data = {}
        user_requests = UserRequest.objects.filter(
            updated_at__gte=date_from,
            request_type=UserRequest.ACCOUNTS,
            user__role=User.MEDIABUYER,
            status=UserRequest.APPROVED,
        )
        for request in user_requests:
            if request.user.team:
                if request.user.team not in requested_data:
                    requested_data[request.user.team] = 0
                if request.user.team not in approved_data:
                    approved_data[request.user.team] = 0
                requested_data[request.user.team] += int(request.request_data['quantity'])
                approved_data[request.user.team] += int(request.request_data['actual_quantity'])
        print(requested_data)
        print(approved_data)
        # accounts_log = (
        #     AccountLog.objects.filter(
        #         Q(start_at__gte=date_from) | Q(end_at__gte=date_from), log_type=AccountLog.MANAGER
        #     )
        #     .distinct('account')
        #     .values_list('account_id', flat=True)
        # )
        # accounts = Account.objects.filter(id__in=accounts_log)
        # teams_data = {}
        # for account in accounts:
        #     log = AccountLog.objects.filter(account=account, log_type=AccountLog.MANAGER, manager__role=User.MEDIABUYER).order_by('id').first()
        #     if log and log.manager != account.created_by:
        #         team = log.manager.team.name if log.manager.team else 'NONE'
        #         if team == 'NONE':
        #             print(log.manager)
        #         if team not in teams_data:
        #             teams_data[team] = []
        #         teams_data[team].append(account.id)
        #
        # for k, v in teams_data.items():
        #     print(k, len(v))
