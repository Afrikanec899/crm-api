import datetime
import logging
from typing import Any, Dict

from django.db import transaction
from django.db.models import Case, Count, ExpressionWrapper, F, Q, QuerySet, Sum, When
from django.db.models.fields import DateTimeField, DecimalField, DurationField, FloatField
from django.utils import timezone
from django.utils.text import capfirst

from django_filters import rest_framework as filters
from facebook_business import FacebookAdsApi
from facebook_business.adobjects.user import User as FBUser
from facebook_business.exceptions import FacebookRequestError
from faker import Faker
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter
from rest_framework.generics import CreateAPIView, GenericAPIView, ListAPIView, UpdateAPIView, get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.filters import AccountFilter, AccountLogFilter, AccountPaymentDataFilter, AccountPaymentFilter
from api.v1.serializers.accounts import (
    AccountCreateSerializer,
    AccountEditAdminSerializer,
    AccountEditFarmerSerializer,
    AccountEditFinancierSerializer,
    AccountEditManagerSerializer,
    AccountEditMediabuyerSerializer,
    AccountEditSetuperSerializer,
    AccountEditSupplierSerializer,
    AccountEditSupplierTeamleadSerializer,
    AccountEditTeamleadSerializer,
    AccountListAdminSerializer,
    AccountListFarmerSerializer,
    AccountListFinancierSerializer,
    AccountListManagerSerializer,
    AccountListMediabuyerSerializer,
    AccountListSetuperSerializer,
    AccountListSupplierSerializer,
    AccountListSupplierTeamleadSerializer,
    AccountListTeamleadSerializer,
    AccountLogSerializer,
    AccountPaymentDataSerializer,
    AccountPaymentDoneSerializer,
    AccountPaymentHistorySerializer,
    AccountPaymentHistoryTotalSerializer,
    AccountPaymentSerializer,
    AccountPaymentTotalSerializer,
    AccountRetrieveAdminSerializer,
    AccountRetrieveFarmerSerializer,
    AccountRetrieveFinancierSerializer,
    AccountRetrieveManagerSerializer,
    AccountRetrieveMediabuyerSerializer,
    AccountRetrieveSetuperSerializer,
    AccountRetrieveSupplierSerializer,
    AccountRetrieveSupplierTeamleadSerializer,
    AccountRetrieveTeamleadSerializer,
    AccountStatusDurationStatsSerializer,
    AccountStatusSerializer,
    BusinessCreateSerializer,
    FanPageCreateSerializer,
)
from api.v1.utils import Ceil, Epoch
from api.v1.views.core import DinamicFieldsListAPIView, DinamicFieldsRetrieveAPIView, TotalStatsPagination
from core.models.core import Account, AccountLog, AccountPayment, User, UserAccountDayStat
from core.tasks import get_fb_businesses
from core.tasks.helpers import create_fan_page

logger = logging.getLogger('django.request')

FacebookAdsApi.HTTP_DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/80.0.3987.87 Safari/537.36'
}


class BaseAccountView(GenericAPIView):
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = (
        Account.objects.all()
        .prefetch_related('manager')
        .prefetch_related('created_by')
        .prefetch_related('supplier')
        .prefetch_related('manager__team')
    )
    serializers: Dict[int, Any] = {}
    return_serializers: Dict[int, Any] = {}

    def get_queryset(self):
        qs = super(BaseAccountView, self).get_queryset()
        if self.request.user.role in [User.MEDIABUYER, User.FARMER, User.JUNIOR]:
            return qs.filter(manager=self.request.user)
        elif self.request.user.role == User.TEAMLEAD:
            return qs.filter(
                Q(manager__team__isnull=False, manager__team=self.request.user.team) | Q(manager=self.request.user)
            )
        elif self.request.user.role == User.SUPPLIER_TEAMLEAD:
            return qs.filter(
                Q(supplier__team__isnull=False, supplier__team=self.request.user.team) | Q(supplier=self.request.user)
            )

        elif self.request.user.role == User.SUPPLIER:
            return qs.filter(supplier=self.request.user)

        return qs

    def get_serializer_class(self):
        assert self.serializers, "'%s' should either include a `serializers` attribute," % self.__class__.__name__
        return self.serializers[self.request.user.role]

    def get_return_serializer(self, *args, **kwargs):
        serializer_class = self.get_return_serializer_class()
        kwargs['context'] = self.get_serializer_context()

        return serializer_class(*args, **kwargs)

    def get_return_serializer_class(self):
        assert self.serializers, (
            "'%s' should either include a `return_serializers` attribute," % self.__class__.__name__
        )
        return self.return_serializers[self.request.user.role]


class AccountCreateView(CreateAPIView):
    allowed_roles = (
        User.ADMIN,
        User.SUPPLIER,
        User.SUPPLIER_TEAMLEAD,
        User.MANAGER,
        User.MEDIABUYER,
        User.JUNIOR,
        User.FARMER,
    )
    queryset = Account.objects.all()
    serializer_class = AccountCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # TODO: проверка на флаг надо ли создание профиля
        Account.create(user=request.user, **serializer.validated_data)
        return Response(status=status.HTTP_201_CREATED)


class AccountListView(BaseAccountView, DinamicFieldsListAPIView):
    filterset_class = AccountFilter
    serializers = {
        User.ADMIN: AccountListAdminSerializer,
        User.MEDIABUYER: AccountListMediabuyerSerializer,
        User.JUNIOR: AccountListMediabuyerSerializer,
        User.TEAMLEAD: AccountListTeamleadSerializer,
        User.FARMER: AccountListFarmerSerializer,
        User.FINANCIER: AccountListFinancierSerializer,
        User.SUPPLIER: AccountListSupplierSerializer,
        User.SUPPLIER_TEAMLEAD: AccountListSupplierTeamleadSerializer,
        User.SETUPER: AccountListSetuperSerializer,
        User.MANAGER: AccountListManagerSerializer,
    }


class AccountEditView(BaseAccountView, UpdateAPIView):
    queryset = Account.objects.all()
    serializers = {
        User.ADMIN: AccountEditAdminSerializer,
        User.MEDIABUYER: AccountEditMediabuyerSerializer,
        User.JUNIOR: AccountEditMediabuyerSerializer,
        User.TEAMLEAD: AccountEditTeamleadSerializer,
        User.FARMER: AccountEditFarmerSerializer,
        User.FINANCIER: AccountEditFinancierSerializer,
        User.SUPPLIER: AccountEditSupplierSerializer,
        User.SUPPLIER_TEAMLEAD: AccountEditSupplierTeamleadSerializer,
        User.SETUPER: AccountEditSetuperSerializer,
        User.MANAGER: AccountEditManagerSerializer,
    }

    return_serializers = {
        User.ADMIN: AccountRetrieveAdminSerializer,
        User.SUPPLIER: AccountRetrieveSupplierSerializer,
        User.SUPPLIER_TEAMLEAD: AccountRetrieveSupplierTeamleadSerializer,
        User.SETUPER: AccountRetrieveSetuperSerializer,
        User.FARMER: AccountRetrieveFarmerSerializer,
        User.MEDIABUYER: AccountRetrieveMediabuyerSerializer,
        User.JUNIOR: AccountRetrieveMediabuyerSerializer,
        User.TEAMLEAD: AccountRetrieveTeamleadSerializer,
        User.FINANCIER: AccountRetrieveFinancierSerializer,
        User.MANAGER: AccountRetrieveManagerSerializer,
    }

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        account = Account.update(
            pk=instance.pk, updated_by=request.user, action_verb='updated', **serializer.validated_data
        )
        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(self.get_return_serializer(account).data)


class AccountStatusView(BaseAccountView, UpdateAPIView):
    http_method_names = ['patch']
    queryset = Account.objects.all()

    def get_serializer_class(self):
        return AccountStatusSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        account = Account.update(
            pk=instance.pk, updated_by=request.user, action_verb='updated', **serializer.validated_data
        )

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(self.get_serializer(account).data)


class AccountDetailView(BaseAccountView, DinamicFieldsRetrieveAPIView):
    serializers = {
        User.ADMIN: AccountRetrieveAdminSerializer,
        User.SUPPLIER: AccountRetrieveSupplierSerializer,
        User.SUPPLIER_TEAMLEAD: AccountRetrieveSupplierTeamleadSerializer,
        User.SETUPER: AccountRetrieveSetuperSerializer,
        User.FARMER: AccountRetrieveFarmerSerializer,
        User.MEDIABUYER: AccountRetrieveMediabuyerSerializer,
        User.JUNIOR: AccountRetrieveMediabuyerSerializer,
        User.TEAMLEAD: AccountRetrieveTeamleadSerializer,
        User.FINANCIER: AccountRetrieveFinancierSerializer,
        User.MANAGER: AccountRetrieveManagerSerializer,
    }


class AccountDetailViewFB(AccountDetailView):
    lookup_field = 'fb_id'
    lookup_url_kwarg = 'fb_id'


#
# class AccountsQueueView(ListAPIView):
#     allowed_roles = (User.FARMER, User.ADMIN, User.MANAGER)
#     queryset = Account.objects.filter(manager__isnull=True, status=Account.NEW)
#     filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
#
#     serializers = {
#         User.ADMIN: AccountListAdminSerializer,
#         User.FARMER: AccountListFarmerSerializer,
#         User.MANAGER: AccountListManagerSerializer,
#     }
#
#     def get_serializer_class(self):
#         return self.serializers[self.request.user.role]
#

#
#
# class AccountsTakeView(APIView):
#     allowed_roles = (User.FARMER, User.ADMIN, User.MANAGER)
#
#     def patch(self, request, *args, **kwargs):
#         account_id = request.data.get('account_id')
#         if account_id:
#             try:
#                 Account.update(
#                     pk=account_id,
#                     updated_by=request.user,
#                     action_verb='started surfing',
#                     status=Account.SURFING,
#                     manager=request.user,
#                 )
#             except Exception as e:
#                 logger.error(e, exc_info=True)
#                 return Response(status=status.HTTP_400_BAD_REQUEST)
#             return Response(status=status.HTTP_200_OK)
#         return Response(status=status.HTTP_400_BAD_REQUEST)
#
#
# class AccountsReturnView(APIView):
#     allowed_roles = (User.FARMER, User.ADMIN, User.MANAGER)
#
#     def patch(self, request, *args, **kwargs):
#         account_id = request.data.get('account_id')
#         if account_id:
#             try:
#                 Account.update(
#                     pk=account_id,
#                     updated_by=request.user,
#                     action_verb='return from surfing',
#                     status=Account.NEW,
#                     manager=None,
#                 )
#             except Exception as e:
#                 logger.error(e, exc_info=True)
#                 return Response(status=status.HTTP_400_BAD_REQUEST)
#             return Response(status=status.HTTP_200_OK)
#         return Response(status=status.HTTP_400_BAD_REQUEST)
#


class AccountLogListView(DinamicFieldsListAPIView):
    queryset = AccountLog.objects.all().prefetch_related('changed_by').prefetch_related('manager')
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = AccountLogFilter
    serializer_class = AccountLogSerializer

    def get_queryset(self) -> QuerySet:
        account = get_object_or_404(Account, pk=self.kwargs['account_id'])
        if self.request.user.role == User.TEAMLEAD:
            if (
                account.manager.team
                and account.manager.team != self.request.user.team
                and account.manager != self.request.user
            ):
                raise PermissionDenied()

        elif self.request.user.role in [User.MEDIABUYER, User.FARMER, User.SETUPER, User.JUNIOR]:
            if account.manager != self.request.user and account.supplier != self.request.user:
                raise PermissionDenied()
        # TODO: TEAMLEAD
        elif self.request.user.role == User.SUPPLIER:
            if account.supplier != self.request.user:
                raise PermissionDenied()
        # if (
        #     account.manager != self.request.user
        #     and account.supplier != self.request.user
        #     and self.request.user.role not in [User.ADMIN, User.FINANCIER, User.MANAGER]
        # ) or (self.request.user.role == User.TEAMLEAD and account.manager.team != self.request.user.team):
        #     raise NotFound()
        qs = super(AccountLogListView, self).get_queryset().filter(account=account)
        return qs


class AccountStatusDurationStatsView(APIView):
    def get(self, request, *args, **kwargs):
        account = get_object_or_404(Account, pk=self.kwargs['account_id'])

        if self.request.user.role == User.TEAMLEAD:
            if (
                account.manager.team
                and account.manager.team != self.request.user.team
                and account.manager != self.request.user
            ):
                raise PermissionDenied()

        elif self.request.user.role in [User.MEDIABUYER, User.JUNIOR, User.FARMER, User.SETUPER]:
            if account.manager != self.request.user and account.supplier != self.request.user:
                raise PermissionDenied()
        # TODO: TEAMLEAD
        elif self.request.user.role == User.SUPPLIER:
            if account.supplier != self.request.user:
                raise PermissionDenied()

        end_at = Case(
            When(end_at__isnull=True, then=timezone.now()), default=F('end_at'), output_field=DateTimeField()
        )
        duration = ExpressionWrapper(end_at - F('start_at'), output_field=DurationField())  # type: ignore

        log = (
            AccountLog.objects.filter(account=account, log_type=AccountLog.STATUS)
            .exclude(status__in=[Account.NEW, Account.BANNED])
            .values('status')
            .annotate(duration=Sum(duration))
            .order_by('-duration')
        )

        return Response(AccountStatusDurationStatsSerializer(log, many=True).data)


class FanPageCreateView(CreateAPIView):
    allowed_roles = (User.ADMIN, User.MANAGER, User.MEDIABUYER, User.JUNIOR, User.TEAMLEAD, User.FARMER)
    queryset = Account.objects.all()
    serializer_class = FanPageCreateSerializer

    def create(self, request, *args, **kwargs):
        account = self.get_object()

        if not account.fb_access_token:
            return Response(data={'error': 'Add account token before'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            create_fan_page(account, serializer.validated_data)
        except Exception as e:
            logger.error(e, exc_info=True)
            return Response(data={'error': 'Can\'t create Page'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_201_CREATED)


class BusinessCreateView(CreateAPIView):
    allowed_roles = (User.ADMIN, User.MANAGER, User.MEDIABUYER, User.JUNIOR, User.TEAMLEAD)
    queryset = Account.objects.all()
    serializer_class = BusinessCreateSerializer

    def create(self, request, *args, **kwargs):
        account = self.get_object()

        if not account.fb_access_token:
            return Response(data={'error': 'Add account token before'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        faker = Faker()

        params = {
            'name': capfirst(serializer.validated_data['name']),
            'vertical': 'OTHER',
            'email': faker.email(),
        }

        FacebookAdsApi.init(access_token=account.fb_access_token, proxies=account.proxy_config)
        user = FBUser(fbid='me')

        try:
            user.create_business(params=params)
        except FacebookRequestError as e:
            logger.error(e, exc_info=True)
            return Response(
                data={'error': e.body()['error'].get('error_user_msg') or e.body()['error'].get('message')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(e, exc_info=True)
            return Response(data={'error': 'Unknown error'}, status=status.HTTP_400_BAD_REQUEST)

        get_fb_businesses.delay(account_id=account.id)

        return Response(status=status.HTTP_201_CREATED)


class AccountPaymentsListView(ListAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER, User.MANAGER)
    serializer_class = AccountPaymentSerializer
    queryset = AccountPayment.objects.all()
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)

    # filterset_class = AccountLogFilter

    def get_queryset(self) -> QuerySet:
        qs = super(AccountPaymentsListView, self).get_queryset()
        qs = qs.filter(account_id=self.kwargs['account_id'])
        return qs


class AccountPaymentData(ListAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER, User.MANAGER, User.SUPPLIER, User.SUPPLIER_TEAMLEAD)
    queryset = Account.objects.all()
    serializer_class = AccountPaymentDataSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = AccountPaymentDataFilter
    pagination_class = TotalStatsPagination

    def get_paginated_response_with_total(self, data, total):
        """
        Return a paginated style `Response` object for the given output data.
        """
        assert self.paginator is not None
        return self.paginator.get_paginated_response(data, total)

    def prepare_response(self, queryset):
        account_ids = [obj['account_id'] for obj in queryset]
        accounts = Account.objects.filter(id__in=account_ids)

        accounts_dict = {}
        for account in accounts:
            accounts_dict[account.id] = account

        for obj in queryset:
            account = accounts_dict.get(obj['account_id'])
            if account:
                obj['account'] = account
                obj['supplier'] = account.supplier
                obj['paid_till'] = account.paid_till

    def get_total_log(self, log):
        total = log.aggregate(total_accounts=Count('account_id'), total_payments=Sum('payment'))
        return AccountPaymentTotalSerializer(total).data

    def get_queryset(self) -> QuerySet:
        qs = super(AccountPaymentData, self).get_queryset()
        # TODO: TEAMLEAD
        if self.request.user.role == User.SUPPLIER:
            qs = qs.filter(supplier=self.request.user)
        return qs

    def list(self, request, *args, **kwargs) -> Response:
        accounts = self.filter_queryset(self.get_queryset())
        # По дефолту конец оплаты - вчерашний полный день
        end = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # TODO: придумать получше
        if 'pay_till' in request.GET:
            pay_till = request.GET['pay_till']
            # В интерфейсе в календаре конец оплаты - дата, мы получаем эту дату
            # и докидываем 1 день, чтобы покрыть весь день
            # Например: выбрана дата 2020-08-15, оплачено по 2020-08-15 включительно,
            # значит до 2020-08-16 00:00:00
            try:
                end = datetime.datetime.strptime(pay_till, '%Y-%m-%d') + datetime.timedelta(days=1)
            except TypeError:
                return Response(status=status.HTTP_400_BAD_REQUEST)

        paid_to = Case(
            When(paid_till__isnull=True, then=F('created_at')), default=F('paid_till'), output_field=DateTimeField()
        )
        accounts = accounts.exclude(price=0)

        accounts = (
            accounts.annotate(paid_to=paid_to)
            .exclude(status=Account.BANNED, status_changed_at__lte=paid_to)
            .values_list('id', flat=True)
        )

        start = Case(
            When(account__paid_till__isnull=True, then=F('account__created_at')),
            default=F('account__paid_till'),
            output_field=DateTimeField(),
        )
        end_at = Case(
            When(Q(end_at__isnull=True) | Q(end_at__gte=end), then=end),
            default=F('end_at'),
            output_field=DateTimeField(),
        )
        start_at = Case(When(start_at__lte=start, then=start), default=F('start_at'), output_field=DateTimeField())
        duration = ExpressionWrapper(end_at - start_at, output_field=DurationField())
        day_price = ExpressionWrapper(F('account__price') / 7, output_field=FloatField())
        day_duration = ExpressionWrapper(Epoch(F('duration')) / 60 / 60 / 24, output_field=FloatField())
        payment = ExpressionWrapper(F('day_duration') * F('day_price'), output_field=DecimalField())

        log = (
            AccountLog.objects.filter(log_type=AccountLog.STATUS, account_id__in=accounts)
            .exclude(
                Q(end_at__lte=start)
                | Q(start_at__gte=end)
                | Q(status=Account.BANNED)
                | Q(status=Account.LOGOUT, end_at__isnull=True)
                # | Q(status__in=(Account.LOGOUT, Account.ON_VERIFY), end_at__isnull=True)
            )
            .annotate(duration=duration, day_price=day_price)
            .exclude(status__in=(Account.LOGOUT, Account.ON_VERIFY), duration__gt=datetime.timedelta(hours=24))
            .values('account_id')
            .annotate(duration=Sum('duration'))
            .exclude(duration__lt=datetime.timedelta(hours=24))
            .annotate(day_duration=Ceil(day_duration))
            .annotate(day_price=F('day_price'), payment=payment, week_price=F('account__price'))
            .order_by('-account_id')
        )

        total_stats = self.get_total_log(log)

        page = self.paginate_queryset(log)

        if page is not None:
            self.prepare_response(page)
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response_with_total(serializer.data, total_stats)

        serializer = self.get_serializer(log, many=True)
        return Response(serializer.data)


class AccountPaymentDone(APIView):
    allowed_roles = (User.ADMIN, User.FINANCIER, User.MANAGER)

    def post(self, request, *args, **kwargs):
        serializer = AccountPaymentDoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        end = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        pay_till = serializer.validated_data.get('pay_till')
        if pay_till:
            pay_to = datetime.datetime.combine(pay_till, datetime.time.min) + datetime.timedelta(days=1)
        else:
            pay_to = end
        # Переводим в часовой пояс по Киеву
        # tz = pytz.timezone('Europe/Kiev')
        # end = tz.localize(end.replace(tzinfo=None))
        date = timezone.now().date()
        currency_rate = serializer.validated_data['currency_rate']
        for account_data in serializer.validated_data['accounts']:
            pay_till = pay_to
            account = get_object_or_404(Account, id=account_data['id'])

            last_status = AccountLog.objects.filter(
                Q(end_at__gte=pay_till) | Q(end_at__isnull=True),
                start_at__lte=pay_till,
                log_type=AccountLog.STATUS,
                account_id=account,
                status__in=[Account.ON_VERIFY, Account.LOGOUT],
            ).first()
            if last_status:
                pay_till = last_status.start_at
                while True:
                    last_status = AccountLog.objects.filter(
                        end_at=pay_till,
                        start_at__gte=account.paid_till,
                        log_type=AccountLog.STATUS,
                        account_id=account,
                        status__in=[Account.ON_VERIFY, Account.LOGOUT],
                    ).first()
                    if last_status:
                        pay_till = last_status.start_at
                    else:
                        break
            # TODO: Засунуть в модель

            with transaction.atomic():
                amount = account_data['amount'] / currency_rate

                AccountPayment.objects.update_or_create(
                    account=account,
                    date=date,
                    defaults={'amount': amount, 'user': request.user, 'amount_uah': account_data['amount']},
                )
                total_paid = AccountPayment.objects.filter(account=account).aggregate(total_paid=Sum('amount'))
                account = Account.objects.select_for_update().get(pk=account.id)
                account.total_paid = total_paid['total_paid']
                account.paid_till = pay_till
                account.save()

                account_manager = account.get_manager_on_date(date)
                campaign = account.get_all_campaigns().first()

                UserAccountDayStat.objects.update_or_create(
                    date=date,
                    account_id=account.id,
                    user_id=account_manager.id if account_manager else None,
                    campaign_id=campaign.id if campaign else None,
                    defaults={'payment': amount},
                )

        return Response(status=status.HTTP_200_OK)


class PaymentHystoryView(ListAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER, User.MANAGER)
    queryset = AccountPayment.objects.all()
    serializer_class = AccountPaymentHistorySerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = AccountPaymentFilter
    pagination_class = TotalStatsPagination

    def get_queryset(self) -> QuerySet:
        qs = super(PaymentHystoryView, self).get_queryset()
        qs = qs.values('date').annotate(amount_usd=Sum('amount'), amount_uah=Sum('amount_uah'), accounts=Count('*'))
        return qs

    def get_paginated_response_with_total(self, data, total):
        """
        Return a paginated style `Response` object for the given output data.
        """
        assert self.paginator is not None
        return self.paginator.get_paginated_response(data, total)

    def get_total_stats(self, stats: QuerySet):
        return AccountPaymentHistoryTotalSerializer(
            stats.aggregate(total_amount_usd=Sum('amount_usd'), total_amount_uah=Sum('amount_uah'))
        ).data

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        total_stats = self.get_total_stats(queryset)

        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response_with_total(serializer.data, total_stats)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
