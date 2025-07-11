import csv
import json
import logging
from collections import OrderedDict

from django.core.cache import cache
from django.db.models import Q, QuerySet
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.utils.datastructures import MultiValueDictKeyError
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters import rest_framework as filters
from drf_yasg.utils import swagger_auto_schema
from faker import Faker
from haproxystats import HAProxyServer
from rest_framework import mixins, status
from rest_framework.filters import OrderingFilter
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.parsers import FileUploadParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet, ReadOnlyModelViewSet

from api.v1.filters import (
    CampaignFilter,
    CountryFilter,
    DomainFilter,
    FBPageFilter,
    KPIFilter,
    PageCategoryFilter,
    TagFilter,
)
from api.v1.serializers.accounts import ImportCSVTaskSerializer, TagSerializer
from api.v1.serializers.campaigns import CampaignListSerializer
from api.v1.serializers.core import (
    CountrySerializer,
    FBPageSerializer,
    KPISerializer,
    PageCategorySerializer,
    ShortifyDomainSerializer,
    CountSerializer,
)
from core.admin import PseudoBuffer
from core.models.core import (
    Account,
    AdAccount,
    Campaign,
    Config,
    Country,
    FBPage,
    PageCategory,
    ShortifyDomain,
    Tag,
    User,
    UserKPI,
)
from core.tasks import process_csv_file
from core.tasks.core import create_empty_mla_profiles, process_telegram_webhook
from core.tasks.facebook import stop_all_ads
from core.utils import EXPAND_PARAM, FIELDS_PARAM, OMIT_PARAM, generate_xcard

logger = logging.getLogger(__name__)


class TotalStatsPagination(LimitOffsetPagination):
    def get_paginated_response(self, data, total=None):
        return Response(
            OrderedDict(
                [
                    ('count', self.count),
                    ('next', self.get_next_link()),
                    ('previous', self.get_previous_link()),
                    ('results', data),
                    ('total', total if total is not None else dict()),
                ]
            )
        )


class DinamicFieldsListAPIView(ListAPIView):
    @swagger_auto_schema(manual_parameters=[FIELDS_PARAM, EXPAND_PARAM, OMIT_PARAM])
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class DinamicFieldsRetrieveAPIView(RetrieveAPIView):
    @swagger_auto_schema(manual_parameters=[FIELDS_PARAM, EXPAND_PARAM, OMIT_PARAM])
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class TagViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, GenericViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = TagFilter


class PageCategoriesViewSet(mixins.ListModelMixin, GenericViewSet):
    queryset = PageCategory.objects.filter(is_public=True)
    serializer_class = PageCategorySerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = PageCategoryFilter


class CountriesViewSet(mixins.ListModelMixin, GenericViewSet):
    queryset = Country.objects.filter(is_public=True)
    serializer_class = CountrySerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = CountryFilter


class ShortifyDomainsViewSet(mixins.ListModelMixin, GenericViewSet):
    queryset = ShortifyDomain.objects.filter(is_public=True, is_banned=False)
    serializer_class = ShortifyDomainSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = DomainFilter


class CampaignsViewSet(mixins.ListModelMixin, GenericViewSet):
    queryset = Campaign.objects.all()
    serializer_class = CampaignListSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = CampaignFilter

    def get_queryset(self) -> QuerySet:
        qs = super(CampaignsViewSet, self).get_queryset()
        if self.request.user.role not in [User.ADMIN, User.SETUPER]:
            if self.request.user.role == User.TEAMLEAD:
                qs = qs.filter(
                    Q(user=self.request.user)
                    | Q(user__isnull=False, user__team__isnull=False, user__team=self.request.user.team)
                )
            else:
                qs = qs.filter(user=self.request.user)
        return qs


# TODO: пермишны на разные экшны и роли
class KPIViewSet(ModelViewSet):
    allowed_roles = (User.ADMIN, User.MEDIABUYER, User.FINANCIER, User.TEAMLEAD, User.JUNIOR)
    queryset = UserKPI.objects.all()
    serializer_class = KPISerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = KPIFilter


# Fb page TODO: Вынести куда-то
class FBPageViewSet(ReadOnlyModelViewSet):
    queryset = FBPage.objects.filter(deleted_at__isnull=True)
    serializer_class = FBPageSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = FBPageFilter

    def get_queryset(self) -> QuerySet:
        queryset = super(FBPageViewSet, self).get_queryset()
        if self.request.user.role in [User.MEDIABUYER, User.JUNIOR]:
            return queryset.filter(account__manager=self.request.user)
        return queryset


class CreateMLAProfiles(APIView):
    allowed_roles = (User.ADMIN, User.MANAGER, User.SUPPLIER, User.SUPPLIER_TEAMLEAD)

    def post(self, request, *args, **kwargs):
        count = request.data.get('count')
        if not count:
            return Response(data={'Error': 'Enter count'}, status=status.HTTP_400_BAD_REQUEST)

        create_empty_mla_profiles.delay(user_id=request.user.id, count=count)
        return Response(status=status.HTTP_201_CREATED)


class CreateXCards(APIView):
    allowed_roles = (User.ADMIN, User.FINANCIER)

    def iter_write(self, items):
        pseudo_buffer = PseudoBuffer()
        writer = csv.writer(pseudo_buffer, delimiter=',')
        yield writer.writerow(
            [
                'productId',
                'currency',
                'internalId',
                'internalNotes',
                'firstname',
                'lastname',
                'gender',
                'dateOfBirth',
                'addressLine1',
                'addressLine2',
                'city',
                'state',
                'postCode',
                'country',
                'mobileCountry',
                'mobileNumber',
                'email',
                'language',
                'nameOnCard',
            ]
        )
        for item in items:
            yield writer.writerow(
                [
                    item['product_id'],
                    item['currency'],
                    '',
                    '',
                    item['first_name'],
                    item['last_name'],
                    item['gender'],
                    item['date_of_birth'],
                    item['address1'],
                    '',
                    item['city'],
                    item['state'],
                    item['post_code'],
                    item['country_code'],
                    item['mobile_country'],
                    item['mobile_number'],
                    item['email'],
                    '',
                    item['name_on_card'],
                ]
            )

    def generate_cards(self, count):
        cards = []
        for _ in range(count):
            cards.append(generate_xcard())
        return cards

    def post(self, request, *args, **kwargs):
        serializer = CountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cards = self.generate_cards(serializer.validated_data['count'])
        response = StreamingHttpResponse((self.iter_write(cards)), content_type="text/event-stream", charset='utf-8')
        response['Content-Disposition'] = f'attachment; filename="cards-{timezone.now()}.csv"'
        response['Access-Control-Expose-Headers'] = 'Content-Disposition'
        response['X-Content-Type-Options'] = 'nosniff'
        return response


class StopAllAds(APIView):
    allowed_roles = (User.ADMIN, User.TEAMLEAD, User.MEDIABUYER, User.JUNIOR)

    def post(self, request, *args, **kwargs):
        accounts = Account.objects.filter(fb_access_token__isnull=False).exclude(
            fb_access_token='', status__in=[Account.BANNED, Account.NEW]
        )
        if request.user.role in [User.TEAMLEAD, User.MEDIABUYER, User.JUNIOR]:
            accounts = accounts.filter(manager=request.user)

        for account in accounts:
            for adaccount in account.adaccounts.filter(status=AdAccount.FB_ACTIVE, deleted_at__isnull=True):
                # stop_all_ads(adaccount.id)
                stop_all_ads.delay(adaccount.id)
        return Response(status=status.HTTP_200_OK)


class TelegramWebhookView(APIView):
    permission_classes = ()
    authentication_classes = ()

    def process_callback(self, callback_query):
        from_user_id = callback_query['from']['id']
        user = User.objects.filter(telegram_id=from_user_id).first()
        if user:
            callback_data = callback_query['data'].split(';')
            if callback_data[0] == 'mute':
                mute_hours, mute_offer = int(callback_data[1]), int(callback_data[2])
                key = f'mute:{user.id}:{mute_offer}'
                cache.set(key, 1, mute_hours * 60 * 60)

    def post(self, request, *args, **kwargs):
        if request.data.get('callback_query'):
            callback = request.data.get('callback_query')
            self.process_callback(callback)
        else:
            entities = request.data['message'].get('entities')
            if entities and entities[0]['type'] == 'bot_command':
                # if kwargs['token'] == settings.TELEGRAM_BOT_TOKEN:
                # process_telegram_webhook(request.data)
                process_telegram_webhook.delay(request.data)
        return Response(status=status.HTTP_200_OK)
        # return Response(status=status.HTTP_403_FORBIDDEN)


class ProxiesStatus(APIView):
    allowed_roles = (User.ADMIN,)

    @method_decorator(cache_page(60))
    def get(self, request, *args, **kwargs):
        haproxy = HAProxyServer(
            Config.get_value('haproxy_stats_host'),
            user=Config.get_value('haproxy_stats_user'),
            password=Config.get_value('haproxy_stats_password'),
            timeout=30,
        )
        return Response(json.loads(haproxy.to_json()))


class CSVUploadView(APIView):
    """
    Api endpoint for upload products csv-file
    """

    allowed_roles = (User.ADMIN, User.FINANCIER, User.MANAGER, User.TEAMLEAD, User.JUNIOR)
    parser_classes = (FileUploadParser,)

    @swagger_auto_schema(request_body=ImportCSVTaskSerializer)
    def post(self, request, **kwargs):

        if kwargs['type'] == 'leads' and request.user.role not in [User.TEAMLEAD, User.ADMIN]:
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            uploaded_file = request.data["file"]
        except MultiValueDictKeyError:
            raise MultiValueDictKeyError("Upload a file with the key 'file'")

        serializer = ImportCSVTaskSerializer(data={'file': uploaded_file, 'type': kwargs['type']})
        serializer.is_valid(raise_exception=True)
        task = serializer.save(user=self.request.user)
        process_csv_file.delay(task.id)
        # process_csv_file(task.id)

        return Response(status=status.HTTP_201_CREATED)
