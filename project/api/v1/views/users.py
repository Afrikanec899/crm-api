import datetime
import logging
from decimal import Decimal
from typing import Any, Dict, List, Type

from django.conf import settings
from django.db.models import Case, ExpressionWrapper, F, QuerySet, When
from django.db.models.aggregates import Avg, Count, Sum
from django.db.models.fields import DateTimeField, DurationField
from django.http.response import JsonResponse
from django.utils import timezone

from django_filters import rest_framework as filters
from drf_yasg.utils import swagger_auto_schema
from knox.models import AuthToken
from rest_framework import generics, mixins, status, views
from rest_framework.filters import OrderingFilter
from rest_framework.generics import (
    CreateAPIView,
    DestroyAPIView,
    GenericAPIView,
    RetrieveAPIView,
    UpdateAPIView,
    get_object_or_404,
)
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from api.v1 import utils
from api.v1.decorators import openapi_ready
from api.v1.filters import StatDateFilter, UserFilter
from api.v1.serializers.core import ActionSerializer
from api.v1.serializers.users import (
    FarmerTotalStatsSerializer,
    LoginSerializer,
    MediabuyerTotalStatsSerializer,
    NotificationSubscriptionSerializer,
    RoleSerializer,
    TeamSerializer,
    TelegramInputSerializer,
    UserChangePasswordSerializer,
    UserCreateSerializer,
    UserDayStatsSerializer,
    UserEditAdminSerializer,
    UserEditSerializer,
    UserListSerializer,
    UserProfileSerializer,
    UserRetrieveSerializer,
    UserSimpleSerializer,
)
from api.v1.utils import PROFIT, SPEND
from api.v1.views.core import DinamicFieldsListAPIView, DinamicFieldsRetrieveAPIView
from core.models import User
from core.models.core import (
    Account,
    AccountActivityLog,
    AccountLog,
    Action,
    AdAccount,
    BusinessManager,
    FieldsSetting,
    NotificationSubscription,
    Team,
    UserAccountDayStat,
)
from core.utils import DATE_FROM, DATE_TO

logger = logging.getLogger('django.request')


class LoginAPIView(generics.GenericAPIView):
    serializer_class = LoginSerializer
    permission_classes = ()
    authentication_classes = ()

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data
        return Response({"token": AuthToken.objects.create(user)[1]})  # token


class Logout(views.APIView):
    def post(self, request, format=None):
        # simply delete the token to force a login
        request.user.auth_token.delete()
        return Response(status=status.HTTP_200_OK)


class TelegramConnectView(GenericAPIView):
    serializer_class = TelegramInputSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        User.connect_telegram(
            pk=request.user.id,
            telegram_id=serializer.validated_data['id'],
            photo_url=serializer.validated_data.get('photo_url'),
        )
        return Response(status=status.HTTP_200_OK)


class TeamViewSet(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, mixins.ListModelMixin, GenericViewSet
):
    allowed_roles = (User.ADMIN, User.FINANCIER)
    queryset = Team.objects.all()
    serializer_class = TeamSerializer


class UserListView(DinamicFieldsListAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER, User.SETUPER, User.MANAGER, User.TEAMLEAD, User.SUPPLIER_TEAMLEAD)
    queryset = User.objects.all().prefetch_related('team')
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = UserFilter

    def get_queryset(self) -> QuerySet:
        qs = super(UserListView, self).get_queryset()
        if self.request.user.role in [User.TEAMLEAD, User.SUPPLIER_TEAMLEAD] and self.request.user.team is not None:
            qs = qs.filter(team=self.request.user.team)
        return qs

    def get_serializer_class(self) -> Type[BaseSerializer]:
        if self.request.user.role in [User.SETUPER, User.MANAGER, User.SUPPLIER_TEAMLEAD]:
            return UserSimpleSerializer
        return UserListSerializer


class UserDetailView(DinamicFieldsRetrieveAPIView):
    queryset = User.objects.all()
    serializer_class = UserRetrieveSerializer

    def get_queryset(self) -> QuerySet:
        queryset = super(UserDetailView, self).get_queryset()
        if self.request.user.role not in [User.ADMIN, User.FINANCIER, User.TEAMLEAD]:
            queryset = queryset.filter(id=self.request.user.id)
        elif self.request.user.role == User.TEAMLEAD:
            queryset = queryset.filter(team=self.request.user.team)
        return queryset


class UserCreateView(CreateAPIView):
    allowed_roles = (User.ADMIN,)
    queryset = User.objects.all()
    serializer_class = UserCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.create(
            actor=request.user,
            username=serializer.validated_data.pop('username'),
            password=serializer.validated_data.pop('password'),
            role=serializer.validated_data.pop('role'),
            **serializer.validated_data,
        )
        return Response(self.get_serializer(user).data, status=status.HTTP_201_CREATED)


class UserChangePasswordView(UpdateAPIView):
    queryset = User.objects.all()
    serializer_class = UserChangePasswordSerializer
    http_method_names = ['patch']

    def get_queryset(self) -> QuerySet:
        queryset = super(UserChangePasswordView, self).get_queryset()
        if self.request.user.role not in [User.ADMIN, User.FINANCIER]:
            queryset = queryset.filter(id=self.request.user.id)
        return queryset

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        user = User.update_password(actor=request.user, pk=instance.id, password=serializer.validated_data['password'])
        return Response(self.get_serializer(user).data)


class UserNotificationSettings(GenericAPIView):
    queryset = NotificationSubscription.objects.all()
    serializer_class = NotificationSubscriptionSerializer

    def get_user(self, request: Request, kwargs: Any) -> User:
        if self.request.user.role == User.ADMIN:
            return get_object_or_404(User, pk=kwargs['pk'])
        return request.user

    def get_settings(self, user: User):
        settings: Dict[int, List[str]] = {}
        for setting in self.queryset.filter(user=user).values('level').annotate(channel=F('channel')):
            if setting.get('level') not in settings.keys():
                settings[setting.get('level')] = []
            settings[setting.get('level')].append(setting.get('channel'))
        return settings

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        user = self.get_user(request, kwargs)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        NotificationSubscription.objects.update_or_create(
            user=user, level=serializer.validated_data['level'], channel=serializer.validated_data['channel']
        )
        settings = self.get_settings(user)
        return Response(settings)

    @swagger_auto_schema(
        operation_description="Remove notification subscription",
        request_body=NotificationSubscriptionSerializer,
        responses={404: 'Notification subscription not found', 200: NotificationSubscriptionSerializer},
    )
    def delete(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        user = self.get_user(request, kwargs)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            NotificationSubscription.objects.get(
                user=user, level=serializer.validated_data['level'], channel=serializer.validated_data['channel']
            ).delete()
        except NotificationSubscription.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        settings = self.get_settings(user)
        return Response(settings)

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        user = self.get_user(request, kwargs)
        settings = self.get_settings(user)
        return Response(settings)


class UserNotificationSubscriptionView(CreateAPIView, DestroyAPIView):
    queryset = NotificationSubscription.objects.all()
    serializer_class = NotificationSubscriptionSerializer

    def perform_create(self, serializer: BaseSerializer) -> None:
        serializer.save(user=self.request.user)

    def get_queryset(self) -> QuerySet:
        queryset = super(UserNotificationSubscriptionView, self).get_queryset()
        if self.request.user.role != User.ADMIN:
            queryset = queryset.filter(user=self.request.user)
        else:
            queryset = queryset.filter(user_id=self.kwargs['pk'])

        return queryset


class UserEditView(UpdateAPIView):
    queryset = User.objects.all()
    http_method_names = ['patch']

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        user = User.update(actor=request.user, pk=instance.id, **serializer.validated_data)
        return Response(UserRetrieveSerializer(user).data)

    def get_queryset(self):
        queryset = super(UserEditView, self).get_queryset()
        if self.request.user.role not in [User.ADMIN, User.FINANCIER, User.TEAMLEAD]:
            queryset = queryset.filter(id=self.request.user.id)
        elif self.request.user.role == User.TEAMLEAD and self.request.user.team:
            queryset = queryset.filter(team=self.request.user.team)
        return queryset

    def get_serializer_class(self):
        if self.request.user.role == User.ADMIN:
            return UserEditAdminSerializer
        return UserEditSerializer


class UserProfileViewSet(mixins.RetrieveModelMixin, GenericViewSet):
    queryset = User.objects.all()
    serializer_class = UserProfileSerializer

    def get_object(self):
        return self.request.user


class FieldsSettingsView(APIView):
    http_method_names = ['patch', 'get']
    omit_fields = ['id']

    def get_default_fields(self, slug, action, role):
        try:
            fields_data = getattr(utils, f'{slug.upper()}_FIELDS_BY_ROLE')
            fields = fields_data[role][action]
            if slug == 'account' and action == 'list':
                fields = [x for x in fields if x not in self.omit_fields]
            return fields
        except Exception as e:
            logger.error(e, exc_info=True)
        return {}

    def get(self, request, *args, **kwargs):
        default_fields = self.get_default_fields(kwargs['slug'], kwargs['action'], request.user.role)
        current_fields = default_fields

        if kwargs['action'] == 'list':
            list_fields = FieldsSetting.objects.filter(user=request.user, slug=kwargs['slug']).first()
            if list_fields:
                user_fields = list_fields.fields
                current_fields = []
                # Чтобы сохранить сортировку
                for field in user_fields:
                    if field in default_fields:
                        current_fields.append(field)

        if not current_fields:
            current_fields = default_fields

        available_fields = set(default_fields) - set(current_fields)
        response = {'fields': {'current': list(current_fields), 'available': list(available_fields)}}
        return JsonResponse(response, status=status.HTTP_200_OK)

    def patch(self, request, *args, **kwargs):
        default_fields = self.get_default_fields(kwargs['slug'], kwargs['action'], request.user.role)
        fields = request.data['fields']
        if set(fields) - set(default_fields):
            return Response(data={'error': 'Wrong fields'}, status=status.HTTP_400_BAD_REQUEST)

        user_fields, _ = FieldsSetting.objects.update_or_create(
            user=request.user, slug=kwargs['slug'], defaults={'fields': fields}
        )
        response = {
            'fields': {'current': user_fields.fields, 'available': list(set(user_fields.fields) ^ set(default_fields))}
        }
        return JsonResponse(response, status=status.HTTP_200_OK)


class UserActionsLogListView(DinamicFieldsListAPIView):
    queryset = Action.objects.all()
    serializer_class = ActionSerializer

    @openapi_ready
    def get_queryset(self) -> QuerySet:
        qs = super(UserActionsLogListView, self).get_queryset()
        if self.request.user.role != User.ADMIN:
            qs = qs.filter(actor=self.request.user)
        else:
            qs = qs.filter(actor_id=self.kwargs['pk'])
        return qs


class BaseUserStatsMixin(RetrieveAPIView):
    def get_queryset(self) -> QuerySet:
        queryset = super(BaseUserStatsMixin, self).get_queryset()
        if self.request.user.role not in [User.ADMIN, User.TEAMLEAD]:
            queryset = queryset.filter(id=self.request.user.id)
        elif self.request.user.role == User.TEAMLEAD:
            queryset = queryset.filter(team=self.request.user.team)
        return queryset


class UserTotalStatsView(BaseUserStatsMixin, DinamicFieldsRetrieveAPIView):
    queryset = User.objects.all()
    serializers = {
        User.MEDIABUYER: MediabuyerTotalStatsSerializer,
        User.JUNIOR: MediabuyerTotalStatsSerializer,
        User.TEAMLEAD: MediabuyerTotalStatsSerializer,
        User.FARMER: FarmerTotalStatsSerializer,
    }

    def get_serializer_class(self):
        assert self.serializers, "'%s' should either include a `serializers` attribute," % self.__class__.__name__
        # Тут декоратор не работает, возвращаем MediabuyerTotalStatsSerializer для сваггера
        if getattr(self, 'swagger_fake_view', False):
            return RoleSerializer

        assert self.instance.role in self.serializers.keys(), (
            "'%s' should either include a `serializers` attribute," % self.__class__.__name__
        )
        return self.serializers[self.instance.role]

    def get_mediabuyer_stats(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}

        # Раньше 1 марта не учитываем
        date_from = datetime.date(2020, 3, 1)
        date_from = datetime.datetime.combine(date_from, datetime.time.min).astimezone(settings.TZ)

        stats = (
            UserAccountDayStat.objects.filter(date__gte=date_from, user=self.instance)
            .values('user_id')
            .annotate(spend=Sum(SPEND), revenue=Sum('revenue'), leads=Sum('leads'),)
            .annotate(profit=PROFIT)
            .aggregate(
                total_spend=Sum('spend'),
                total_profit=Sum('profit'),
                total_leads=Sum('leads'),
                total_revenue=Sum('revenue'),
            )
        )
        end_at = Case(
            When(end_at__isnull=True, then=timezone.now()), default=F('end_at'), output_field=DateTimeField()
        )
        duration = ExpressionWrapper(end_at - F('start_at'), output_field=DurationField())

        status_log = (
            AccountLog.objects.filter(account__manager=self.instance, log_type=AccountLog.STATUS)
            .exclude(status__in=[Account.NEW, Account.BANNED])
            .values('account', 'status')
            .annotate(duration=duration)
            .values('account')
            .annotate(duration=Sum('duration'))
            .aggregate(avg_duration=Avg('duration'))
        )

        if status_log.get('avg_duration'):
            avg_accs_lifetime = status_log['avg_duration'] / datetime.timedelta(days=1)
        else:
            avg_accs_lifetime = 0

        data['profit'] = stats.get('total_profit', 0) or 0
        data['leads'] = stats.get('total_leads', 0) or 0
        data['spend'] = stats.get('total_spend', 0) or 0
        roi = 0
        revenue = stats.get('total_revenue', 0) or 0
        if data['spend']:
            roi = ((revenue - data['spend']) / data['spend']) * 100
        data['roi'] = roi

        data['banned_accs'] = AccountLog.objects.filter(
            log_type=AccountLog.STATUS, start_at__gte=date_from, account__manager=self.instance, status=Account.BANNED
        ).count()
        data['avg_accs_lifetime'] = round(avg_accs_lifetime, 0)

        accounts = Account.objects.filter(manager=self.instance).exclude(status__in=[Account.NEW, Account.BANNED])
        # Total BMs & Adaccounts
        data['bms'] = BusinessManager.objects.filter(account__in=accounts).count()
        data['adaccounts'] = AdAccount.objects.filter(account__in=accounts, status=AdAccount.FB_ACTIVE).count()

        # Statuses chart
        data['statuses'] = []
        statuses = accounts.values('status').annotate(count=Count('id')).order_by()

        if statuses.exists():
            data['statuses'] = statuses

        return data

    def get_farmer_stats(self) -> Dict[str, Any]:
        data = {}
        # .order_by('account_id').values('account_id') - distinct не работает без него
        manager_log = AccountLog.objects.filter(manager=self.instance).order_by('account_id').values('account_id')
        # Сейчас на фарме и не в бане
        on_farm = manager_log.filter(end_at__isnull=True).exclude(account__status=Account.BANNED).distinct().count()

        # Всего нафармленно и отдано баерам в том числе и уже забаненные
        farmed = manager_log.filter(end_at__isnull=False).distinct().count()

        # Количество забанненых акков, которые фармил данный юзер
        banned = manager_log.filter(account__status=Account.BANNED).distinct().count()

        data['on_farm'] = on_farm
        data['farmed'] = farmed
        data['banned'] = banned

        end_at = Case(
            When(end_at__isnull=True, then=timezone.now()), default=F('end_at'), output_field=DateTimeField()
        )
        duration = ExpressionWrapper(end_at - F('start_at'), output_field=DurationField())

        managed_accs = manager_log.values_list('account_id', flat=True).distinct()

        status_log = (
            AccountLog.objects.filter(account_id__in=list(managed_accs), log_type=AccountLog.STATUS)
            .exclude(status__in=[Account.NEW, Account.BANNED])
            .values('account', 'status')
            .annotate(duration=duration)
        )

        accs_age = (
            status_log.values('account').annotate(duration=Sum('duration')).aggregate(avg_duration=Avg('duration'))
        )

        if accs_age.get('avg_duration'):
            data['avg_age'] = accs_age['avg_duration']

        surfing_time = (
            status_log.filter(status=Account.SURFING)
            .values('account')
            .annotate(duration=Sum('duration'))
            .aggregate(avg_duration=Avg('duration'))
        )
        if surfing_time.get('avg_duration'):
            data['avg_surfing'] = surfing_time['avg_duration']

        stats = (
            UserAccountDayStat.objects.filter(account_id__in=list(managed_accs))
            .values('account_id')
            .annotate(spend=Sum(SPEND), revenue=Sum('revenue'))
            .annotate(profit=PROFIT)
            .aggregate(avg_spend=Avg('spend'), avg_profit=Avg('profit'))
        )
        data['avg_spend'] = stats.get('avg_spend', Decimal('0')) or Decimal('0')
        data['avg_profit'] = stats.get('avg_profit', Decimal('0')) or Decimal('0')

        # Количество сессий на акке и среднее время 1 сессии
        activity = (
            AccountActivityLog.objects.filter(account_id__in=list(managed_accs), user=self.instance)
            .exclude(end_at=F('start_at'))
            .annotate(duration=ExpressionWrapper(F('end_at') - F('start_at'), output_field=DurationField()))
            .exclude(duration__lte=datetime.timedelta(seconds=30))
            .values('account')
            .annotate(sessions=Count('id'), duration=Avg('duration'))
            .aggregate(
                avg_sessions=Avg('sessions'), total_sessions=Sum('sessions'), avg_session_duration=Avg('duration')
            )
        )

        data.update(activity)
        return data

    def get_stats(self) -> Dict[str, Any]:
        if self.instance.role in [User.MEDIABUYER, User.TEAMLEAD, User.JUNIOR]:
            return self.get_mediabuyer_stats()

        elif self.instance.role == User.FARMER:
            return self.get_farmer_stats()
        else:
            return {}

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        self.instance = self.get_object()
        data = self.get_stats()

        serializer = self.get_serializer(data)
        return Response(serializer.data)


# FIXME:
class UserDailyStatsView(BaseUserStatsMixin):
    queryset = User.objects.all()
    # TODO: разные для разных ролей
    serializer_class = UserDayStatsSerializer

    @swagger_auto_schema(manual_parameters=[DATE_FROM, DATE_TO])
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    def get_context_data(self, request, instance) -> Type[QuerySet]:
        # TODO: фармеры-сетаперы

        user_stats = (
            UserAccountDayStat.objects.filter(user=instance)
            .values('date')
            .annotate(profit=Sum('profit'), spend=Sum(SPEND), revenue=Sum('revenue'))
            .order_by('date')
        )
        return StatDateFilter(request.GET, queryset=user_stats).qs

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        data = self.get_context_data(request, instance)

        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)
