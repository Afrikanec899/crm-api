import datetime
from decimal import Decimal

# from typing import Any, Dict
from typing import Any

from django.conf import settings
from django.db.models import Case, Count, ExpressionWrapper, F, Q, QuerySet, Sum, When
from django.db.models.aggregates import Avg, Max
from django.db.models.fields import DateTimeField, DurationField, FloatField
from django.db.models.functions import Cast, TruncDate
from django.utils import timezone

from dateutil.relativedelta import relativedelta
from django_filters import rest_framework as filters
from rest_framework import status
from rest_framework.filters import OrderingFilter
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.filters import (  # UserStatFilter,; AdAccountStatDateFilter,
    AccountStatusLogFilter,
    FlowStatDateFilter,
    LeadgenLeadStatsFilter,
    StatDateFilter,
    StatDateFilter2,
)
from api.v1.serializers.accounts import AccountStatusDurationStatsSerializer
from api.v1.serializers.stats import (
    AccountStatSerializer,
    CampaignStatSerializer,
    DateStatSerializer,
    FlowStatSerializer,
    LeadgenLeadStatsSerializer,
    TotalStatsSerializerMixin,
    UsersStatSerializer,
)
from api.v1.utils import CR, CTR, CV, EPC, PROFIT, PROFIT_V2, ROI, SPEND, Median, months_list
from api.v1.views.core import TotalStatsPagination
from core.models import User
from core.models.core import (
    Account,
    AccountLog,  # UserAdAccountDayStatNew,
    CampaignDayStat,
    FlowDayStat,
    LeadgenLead,
    UserAccountDayStat,
    UserCampaignDayStat,
    UserDayStat,
)


# TODO: Refactor
class GeoGlobalStats(APIView):
    allowed_roles = (User.ADMIN, User.FINANCIER)

    def get(self, request, *args, **kwargs):
        epc = Case(
            When(total_clicks=0, then=0),
            default=Cast(Sum('revenue'), FloatField()) / Cast(F('total_clicks'), FloatField()),
            output_field=FloatField(),
        )

        cv = Case(
            When(total_visits=0, then=0),
            default=(Cast(F('total_leads'), FloatField()) / Cast(F('total_visits'), FloatField())) * 100,
            output_field=FloatField(),
        )
        cr = Case(
            When(total_clicks=0, then=0),
            default=(Cast(F('total_leads'), FloatField()) / Cast(F('total_clicks'), FloatField())) * 100,
            output_field=FloatField(),
        )
        ctr = Case(
            When(total_visits=0, then=0),
            default=(Cast(F('total_clicks'), FloatField()) / Cast(F('total_visits'), FloatField())) * 100,
            output_field=FloatField(),
        )

        geo_stats = (
            CampaignDayStat.objects.filter(date=timezone.now().date())
            .values('campaign__country_code')
            .annotate(total_leads=Sum('leads'), total_visits=Sum('visits'), total_clicks=Sum('clicks'))
            .annotate(epc=epc, cv=cv, cr=cr, ctr=ctr)
        )

        country_geo_stats = {}
        for geo_stat in geo_stats:
            country_geo_stats[geo_stat['campaign__country_code']] = geo_stat
        data = {'stats': country_geo_stats}
        return Response(data=data, status=status.HTTP_200_OK)


# TODO: Refactor
class GeoUserStats(APIView):
    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.FINANCIER, User.TEAMLEAD, User.JUNIOR)

    def get(self, request, *args, **kwargs):
        user = request.user
        epc = Case(
            When(total_clicks=0, then=0),
            default=Cast(Sum('revenue'), FloatField()) / Cast(F('total_clicks'), FloatField()),
            output_field=FloatField(),
        )

        cv = Case(
            When(total_visits=0, then=0),
            default=(Cast(F('total_leads'), FloatField()) / Cast(F('total_visits'), FloatField())) * 100,
            output_field=FloatField(),
        )
        cr = Case(
            When(total_clicks=0, then=0),
            default=(Cast(F('total_leads'), FloatField()) / Cast(F('total_clicks'), FloatField())) * 100,
            output_field=FloatField(),
        )
        ctr = Case(
            When(total_visits=0, then=0),
            default=(Cast(F('total_clicks'), FloatField()) / Cast(F('total_visits'), FloatField())) * 100,
            output_field=FloatField(),
        )

        user_stats = (
            UserCampaignDayStat.objects.filter(date=timezone.now().date(), user=user)
            .values('campaign__country_code')
            .annotate(total_leads=Sum('leads'), total_visits=Sum('visits'), total_clicks=Sum('clicks'))
            .annotate(epc=epc, cv=cv, cr=cr, ctr=ctr)
        )

        country_team_stats = {}
        if user.team:
            team_stats = (
                UserCampaignDayStat.objects.filter(
                    date=timezone.now().date(), user__role__in=[User.TEAMLEAD, User.MEDIABUYER, User.JUNIOR]
                )  # user__team=user.team)
                .values('campaign__country_code')
                .annotate(total_leads=Sum('leads'), total_visits=Sum('visits'), total_clicks=Sum('clicks'))
                .annotate(epc=epc, cv=cv, cr=cr, ctr=ctr)
            )

            for team_stat in team_stats:
                country_team_stats[team_stat['campaign__country_code']] = team_stat

        country_user_stats = {}
        for user_stat in user_stats:
            country_user_stats[user_stat['campaign__country_code']] = user_stat
        data = {'user_stats': country_user_stats, 'team_stats': country_team_stats}
        return Response(data=data, status=status.HTTP_200_OK)


class UserBaseStats(APIView):
    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.FINANCIER, User.TEAMLEAD, User.JUNIOR)

    def get(self, request, *args, **kwargs):
        user = request.user
        today = timezone.now().date()
        yesterday = today - datetime.timedelta(days=1)
        month_start = today.replace(day=1)

        # FIXME
        banned_filter = {'updated_at__gte': month_start, 'status': Account.BANNED}

        active_filter = {'status': Account.ACTIVE}
        onverify_filter = {'status': Account.ON_VERIFY}

        user_stats_filter = {}

        if request.user.role in [User.MEDIABUYER, User.JUNIOR]:
            banned_filter['manager'] = user
            active_filter['manager'] = user
            onverify_filter['manager'] = user

            user_stats_filter['user'] = user

        data = {
            'banned': Account.objects.filter(**banned_filter).count(),
            'active': Account.objects.filter(**active_filter).count(),
            'onverify': Account.objects.filter(**onverify_filter).count(),
        }

        today_leads = Sum(F('leads'), filter=Q(date=today))

        day_profit = Sum((F('revenue') - F('total_spend')), filter=Q(date=yesterday))
        month_profit = Sum((F('revenue') - F('total_spend')), filter=Q(date__gte=month_start, date__lte=yesterday))

        user_profit = (
            UserAccountDayStat.objects.filter(**user_stats_filter)
            .exclude(campaign__name__icontains='youtube')
            .annotate(total_spend=SPEND)
            .aggregate(day_profit=day_profit, month_profit=month_profit, today_leads=today_leads,)
        )

        data.update(user_profit)
        return Response(data=data, status=status.HTTP_200_OK)


class BaseStatViewMixin(GenericAPIView):
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = StatDateFilter
    pagination_class = TotalStatsPagination

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        stats = self.get_stats()
        total_stats = self.get_total_stats(stats)

        page = self.paginate_queryset(stats)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response_with_total(serializer.data, total_stats)

        serializer = self.get_serializer(stats, many=True)
        return Response(serializer.data)

    def get_queryset(self) -> QuerySet:
        queryset = self.filter_queryset(super(BaseStatViewMixin, self).get_queryset())
        date_from = datetime.date(2020, 3, 1)
        date_from = datetime.datetime.combine(date_from, datetime.time.min).astimezone(settings.TZ)
        queryset = queryset.filter(date__gte=date_from)

        if self.request.user.role not in [User.ADMIN, User.FINANCIER]:
            if self.request.user.role == User.TEAMLEAD:
                queryset = queryset.filter(
                    Q(user=self.request.user) | Q(user__team=self.request.user.team, user__team__isnull=False)
                )
            else:
                queryset = queryset.filter(user=self.request.user)

        return queryset

    def get_stats(self):
        queryset = self.get_queryset()
        queryset = queryset.annotate(
            leads=Sum('leads'),
            visits=Sum('visits'),
            clicks=Sum('clicks'),
            revenue=Sum('revenue'),
            spend=Sum(SPEND),
            payment=Sum('payment'),
        ).annotate(epc=EPC, cv=CV, cr=CR, ctr=CTR, roi=ROI, profit=PROFIT)
        ordering = OrderingFilter()
        return ordering.filter_queryset(request=self.request, queryset=queryset, view=self)

    def get_total_stats(self, stats: QuerySet):
        # TODO: придумать красивее
        total_stats = stats.aggregate(
            total_leads=Sum('leads'),
            total_visits=Sum('visits'),
            total_clicks=Sum('clicks'),
            total_revenue=Sum('revenue'),
            total_spend=Sum('spend'),
            total_profit=Sum('profit'),
            total_payment=Sum('payment'),
        )
        total_stats.update(
            {
                'epc': Decimal('0.00'),
                'cr': Decimal('0.00'),
                'cv': Decimal('0.00'),
                'ctr': Decimal('0.00'),
                'roi': Decimal('0.00'),
            }
        )
        if total_stats['total_clicks']:
            total_stats['epc'] = total_stats['total_revenue'] / total_stats['total_clicks']
            total_stats['cr'] = (total_stats['total_leads'] / total_stats['total_clicks']) * 100

        if total_stats['total_visits']:
            total_stats['cv'] = (total_stats['total_leads'] / total_stats['total_visits']) * 100
            total_stats['ctr'] = (total_stats['total_clicks'] / total_stats['total_visits']) * 100

        if total_stats['total_spend']:
            total_stats['roi'] = (
                (total_stats['total_revenue'] - total_stats['total_spend'])  # - total_stats['total_payment'])
                / (total_stats['total_spend'])  # + total_stats['total_payment'])
            ) * 100

        return TotalStatsSerializerMixin(total_stats).data

    def get_paginated_response_with_total(self, data, total):
        """
        Return a paginated style `Response` object for the given output data.
        """
        assert self.paginator is not None
        return self.paginator.get_paginated_response(data, total)


class DateStatView(BaseStatViewMixin, ListAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER, User.MEDIABUYER, User.TEAMLEAD, User.JUNIOR)
    queryset = UserAccountDayStat.objects.all().exclude(campaign__name__icontains='youtube').values('date')
    serializer_class = DateStatSerializer

    def get_queryset(self) -> QuerySet:
        queryset = super(DateStatView, self).get_queryset()
        if self.request.user.role in [User.ADMIN, User.FINANCIER]:
            return queryset.exclude(user_id__in=[38, 39])
        return queryset


class CampaignStatView(BaseStatViewMixin, ListAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER, User.MEDIABUYER, User.TEAMLEAD, User.JUNIOR)
    queryset = (
        UserAccountDayStat.objects.filter(campaign__isnull=False)
        .exclude(campaign__name__icontains='youtube')
        .values('campaign_id')
    )
    serializer_class = CampaignStatSerializer


class AccountsStatView(BaseStatViewMixin, ListAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER, User.MEDIABUYER, User.TEAMLEAD, User.JUNIOR)
    queryset = (
        UserAccountDayStat.objects.filter(account__isnull=False)
        .exclude(campaign__name__icontains='youtube')
        .values('account_id')
    )
    serializer_class = AccountStatSerializer


class AdAccountsStatView(ListAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER, User.MEDIABUYER, User.TEAMLEAD, User.JUNIOR)
    queryset = UserDayStat.objects.filter(account__isnull=False).values('account_id')
    serializer_class = AccountStatSerializer
    pagination_class = TotalStatsPagination
    filterset_class = StatDateFilter2

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        stats = self.get_stats()
        total_stats = self.get_total_stats(stats)

        page = self.paginate_queryset(stats)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response_with_total(serializer.data, total_stats)

        serializer = self.get_serializer(stats, many=True)
        return Response(serializer.data)

    def get_queryset(self) -> QuerySet:
        queryset = self.filter_queryset(super(AdAccountsStatView, self).get_queryset())
        date_from = datetime.date(2020, 3, 1)
        date_from = datetime.datetime.combine(date_from, datetime.time.min).astimezone(settings.TZ)
        queryset = queryset.filter(date__gte=date_from)

        if self.request.user.role not in [User.ADMIN, User.FINANCIER]:
            if self.request.user.role == User.TEAMLEAD:
                queryset = queryset.filter(
                    Q(user=self.request.user) | Q(user__team=self.request.user.team, user__team__isnull=False)
                )
            else:
                queryset = queryset.filter(user=self.request.user)

        return queryset

    def get_stats(self):
        queryset = self.get_queryset()
        queryset = queryset.annotate(
            leads=Sum('leads'),
            visits=Sum('visits'),
            clicks=Sum('clicks'),
            revenue=Sum('revenue'),
            cost=Sum('cost'),
            spend=Sum('spend'),
            payment=Sum('payment'),
        ).annotate(epc=EPC, cv=CV, cr=CR, ctr=CTR, roi=ROI, profit=PROFIT_V2)
        ordering = OrderingFilter()
        return ordering.filter_queryset(request=self.request, queryset=queryset, view=self)

    def get_total_stats(self, stats: QuerySet):
        # TODO: придумать красивее
        total_stats = stats.aggregate(
            total_leads=Sum('leads'),
            total_visits=Sum('visits'),
            total_clicks=Sum('clicks'),
            total_revenue=Sum('revenue'),
            total_spend=Sum('spend'),
            total_profit=Sum('profit'),
            total_payment=Sum('payment'),
        )
        total_stats.update(
            {
                'epc': Decimal('0.00'),
                'cr': Decimal('0.00'),
                'cv': Decimal('0.00'),
                'ctr': Decimal('0.00'),
                'roi': Decimal('0.00'),
            }
        )
        if total_stats['total_clicks']:
            total_stats['epc'] = total_stats['total_revenue'] / total_stats['total_clicks']
            total_stats['cr'] = (total_stats['total_leads'] / total_stats['total_clicks']) * 100

        if total_stats['total_visits']:
            total_stats['cv'] = (total_stats['total_leads'] / total_stats['total_visits']) * 100
            total_stats['ctr'] = (total_stats['total_clicks'] / total_stats['total_visits']) * 100

        if total_stats['total_spend']:
            total_stats['roi'] = (
                (total_stats['total_revenue'] - total_stats['total_spend'])  # - total_stats['total_payment'])
                / (total_stats['total_spend'])  # + total_stats['total_payment'])
            ) * 100

        return TotalStatsSerializerMixin(total_stats).data

    def get_paginated_response_with_total(self, data, total):
        """
        Return a paginated style `Response` object for the given output data.
        """
        assert self.paginator is not None
        return self.paginator.get_paginated_response(data, total)


class AccountStatusStatsView(APIView):
    allowed_roles = (
        User.ADMIN,
        User.FINANCIER,
        User.MEDIABUYER,
        User.JUNIOR,
        User.SUPPLIER,
        User.SUPPLIER_TEAMLEAD,
        User.MANAGER,
        User.TEAMLEAD,
    )

    def get(self, request, *args, **kwargs):
        accounts = Account.objects.exclude(status=Account.BANNED)
        # TODO: TEAMLEAD
        if request.user.role == User.SUPPLIER:
            accounts = accounts.filter(supplier=request.user)
        elif request.user.role in [User.MEDIABUYER, User.JUNIOR]:
            accounts = accounts.filter(manager=request.user)
        elif request.user.role == User.TEAMLEAD:
            accounts = accounts.filter(
                Q(manager=request.user) | Q(manager__team=request.user.team, manager__team__isnull=False)
            )
        statuses = accounts.values('status').annotate(count=Count('id')).order_by()
        return Response(data=statuses, status=status.HTTP_200_OK)


class UsersStatView(BaseStatViewMixin, ListAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER, User.MEDIABUYER, User.TEAMLEAD)
    queryset = (
        UserAccountDayStat.objects.filter(user__isnull=False)
        .exclude(campaign__name__icontains='youtube')
        .values('user_id')
    )
    serializer_class = UsersStatSerializer

    def get_queryset(self) -> QuerySet:
        queryset = self.filter_queryset(self.queryset)
        date_from = datetime.date(2020, 3, 1)
        date_from = datetime.datetime.combine(date_from, datetime.time.min).astimezone(settings.TZ)
        queryset = queryset.filter(date__gte=date_from)
        # FIXME: для дашборда
        # if self.request.user.role in [User.MEDIABUYER, User.TEAMLEAD]:
        #     queryset = queryset.filter(user__team=self.request.user.team)

        return queryset


class FlowsStatView(BaseStatViewMixin, ListAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER)
    queryset = FlowDayStat.objects.all().values('flow_id')
    filterset_class = FlowStatDateFilter
    serializer_class = FlowStatSerializer

    def get_stats(self):
        queryset = self.get_queryset()

        return queryset.annotate(
            leads=Sum('leads'), visits=Sum('visits'), clicks=Sum('clicks'), revenue=Sum('revenue'), spend=Sum('cost')
        ).annotate(epc=EPC, cv=CV, cr=CR, ctr=CTR, roi=ROI, profit=PROFIT)


class StatusDurationView(ListAPIView):
    queryset = AccountLog.objects.filter(log_type=AccountLog.STATUS).exclude(status__in=[Account.NEW, Account.BANNED])
    serializer_class = AccountStatusDurationStatsSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = AccountStatusLogFilter

    def get_queryset(self) -> QuerySet:
        queryset = super(StatusDurationView, self).get_queryset()
        end_at = Case(
            When(end_at__isnull=True, then=timezone.now()), default=F('end_at'), output_field=DateTimeField()
        )
        duration = ExpressionWrapper(end_at - F('start_at'), output_field=DurationField())  # type: ignore
        queryset = queryset.values('status').annotate(duration=Sum(duration)).order_by('-duration')
        return queryset


class TotalBannedView(APIView):
    allowed_roles = (User.ADMIN,)

    def get(self, request, *args, **kwargs):
        banned_data = []
        # Начало нашей статы
        date_from = datetime.date(2020, 3, 1)
        date_to = timezone.now().date()

        logs = (
            AccountLog.objects.filter(
                log_type=AccountLog.STATUS, start_at__gte=date_from, end_at__isnull=True, status=Account.BANNED
            )
            .values('start_at__month', 'start_at__year')
            .annotate(banned=Count('id'))
        )

        log_dict = {}
        for log in logs:
            log_dict[f'{log["start_at__month"]}_{log["start_at__year"]}'] = log['banned']

        months = months_list(date_from.month, date_from.year, date_to.month, date_to.year)
        for month_data in months:
            month, year = month_data
            data = {'month': month, 'year': year, 'banned': 0}
            banned = log_dict.get(f'{month}_{year}', 0)
            data['banned'] = banned or 0
            banned_data.append(data)
        return Response(banned_data)


class LifetimeSpendView(APIView):
    allowed_roles = (User.ADMIN,)  # User.FINANCIER, User.MEDIABUYER, User.MANAGER, User.TEAMLEAD)

    def get_stats(self, month, year):
        # Исключаем акки, которые были запущены раньше
        date_from = datetime.date(year, month, 1)
        accounts_log_exclude = AccountLog.objects.filter(
            start_at__lte=date_from, status=Account.ACTIVE, log_type=AccountLog.STATUS,
        ).values_list('account_id', flat=True)

        # Берем акки, которые запущены первый раз в данном месяце
        account_ids = (
            AccountLog.objects.filter(
                status=Account.ACTIVE, log_type=AccountLog.STATUS, start_at__month=month, start_at__year=year,
            )
            .exclude(account_id__in=list(set(accounts_log_exclude)))
            .values_list('account_id', flat=True)
        )

        stat = UserAccountDayStat.objects.filter(account_id__in=list(set(account_ids))).exclude(user_id__in=[1, 7])

        data = (
            stat.values('account_id')
            .annotate(total_spend=Sum(SPEND))
            .exclude(total_spend__lte=20.0)
            .aggregate(max_spend=Max('total_spend'), avg_spend=Avg('total_spend'), median_spend=Median('total_spend'),)
        )

        return data

    def get(self, request, *args, **kwargs):
        spend_data = []

        date_to = timezone.now().date()
        date_from = date_to - relativedelta(months=12)

        if date_from <= datetime.date(2020, 3, 1):
            date_from = datetime.date(2020, 3, 1)

        months = months_list(date_from.month, date_from.year, date_to.month, date_to.year)
        for month_data in months:
            month, year = month_data
            data = {'month': month, 'year': year, 'spend': self.get_stats(month, year)}
            spend_data.append(data)

        return Response(data=spend_data, status=status.HTTP_200_OK)


class LeadgenLeadStats(ListAPIView):
    allowed_roles = (User.ADMIN, User.TEAMLEAD, User.MEDIABUYER, User.JUNIOR)
    queryset = LeadgenLead.objects.all()
    serializer_class = LeadgenLeadStatsSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = LeadgenLeadStatsFilter

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        queryset = (
            queryset.values('created_at__date')
            .annotate(leads=Count('id'), date=TruncDate(F('created_at__date')))
            .order_by('-date')
        )
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
