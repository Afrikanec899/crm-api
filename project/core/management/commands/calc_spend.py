import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models.core import AdAccountDayStat
from core.utils import dateperiod


class Command(BaseCommand):
    help = ''

    # def add_arguments(self, parser):
    #     parser.add_argument("-d", "--days", action="store", dest="days", type=int, help="Days", default=0)

    def handle(self, *args, **options):
        date_from = datetime.date(2021, 2, 1)
        date_to = datetime.date(2021, 2, 28)
        adaccounts = AdAccountDayStat.objects.filter(date__gte=date_from, date__lte=date_to).values_list(
            'adaccount_id', flat=True
        )
        user_spends = {}
        for date in reversed(dateperiod(date_from, date_to)):
            print(date)
            for adacc in adaccounts:
                print(adacc)
                day_user_spends = {}
                day_spends = AdAccountDayStat.objects.filter(adaccount_id=adacc, date=date)
                print(day_spends)
                if day_spends.count() > 1:
                    print(day_spends)
                    for day_spend in day_spends:
                        if day_spend.user_id not in day_user_spends:
                            day_user_spends[day_spend.user_id] = day_spend.spend
                        else:
                            if day_user_spends[day_spend.user_id] < day_spend.spend:
                                day_user_spends[day_spend.user_id] = day_spend.spend

                    for k, v in day_user_spends.items():
                        if k not in user_spends:
                            user_spends[k] = 0
                        user_spends[k] += v

        print(user_spends)

        #
        #
        # print(adaccounts_data.count())
        # spends_data = {}
        # for adacc_data in adaccounts_data:
        #     if adacc_data.adaccount_id not in spends_data.keys():
        #         spends_data[adacc_data.adaccount_id][adacc_data.date] = adacc_data.spend
        #     else:
        #         if adacc_data.date not in spends_data[adacc_data.adaccount_id]:
        #             spends_data[adacc_data.adaccount_id][adacc_data.date] = adacc_data.spend
