# import csv
import logging
from decimal import Decimal
from typing import Any

from django.conf import settings

from django_filters import rest_framework as filters
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.filters import OrderingFilter
from rest_framework.generics import CreateAPIView, UpdateAPIView, get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.filters import LeadgenBroadcastFilter, LeadgenLeadFilter
from api.v1.serializers.leads import (
    LanderDataSerializer,
    LeadgenLeadListSerializer,
    LeadgenLeadPostbackSerializer,
    LinkGroupCreateSerializer,
    LinkGroupEditSerializer,
    LinkGroupListSerializer,
)
from api.v1.views.core import DinamicFieldsListAPIView

# from core.admin import PseudoBuffer
from core.models import User
from core.models.core import Campaign, LeadgenLead, LeadgenLeadConversion, LinkGroup
from core.pagination import CachedCountLimitOffsetPagination
from core.tasks.links import create_links, process_click_stats, process_lander_data

# from django.db import transaction
# from django.http import StreamingHttpResponse
# from django.utils import timezone


logger = logging.getLogger(__name__)


class LeadgenLeadViewSet(DinamicFieldsListAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER, User.TEAMLEAD)
    queryset = (
        LeadgenLead.objects.all().prefetch_related('account').prefetch_related('user').prefetch_related('country')
    )
    serializer_class = LeadgenLeadListSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = LeadgenLeadFilter
    pagination_class = CachedCountLimitOffsetPagination


#
# class LeadgenLeadExportView(LeadgenLeadViewSet):
#     def iter_write(self, items, now):
#         pseudo_buffer = PseudoBuffer()
#         writer = csv.writer(pseudo_buffer, delimiter=';', quoting=csv.QUOTE_ALL)
#         yield writer.writerow(['date', 'uuid', 'name', 'email', 'phone', 'offer'])
#         for item in items:
#             yield writer.writerow([item.created_at, item.uuid, item.name, item.email, item.phone, item.offer])
#             item.exported_at = now
#             item.save(
#                 update_fields=['exported_at',]
#             )
#
#     @transaction.atomic
#     def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
#         now = timezone.now()
#         leads = self.filter_queryset(self.get_queryset())
#         response = StreamingHttpResponse(
#             (self.iter_write(leads, now)), content_type="text/event-stream", charset='utf-8'
#         )
#         response['Content-Disposition'] = f'attachment; filename="leads-{now}.csv"'
#         response['Access-Control-Expose-Headers'] = 'Content-Disposition'
#         response['X-Content-Type-Options'] = 'nosniff'
#         return response


class LeadgenLeadPostbackView(APIView):
    permission_classes = ()

    @swagger_auto_schema(query_serializer=LeadgenLeadPostbackSerializer)
    def get(self, request, **kwargs):
        serializer = LeadgenLeadPostbackSerializer(data=request.GET)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

        leadgen_lead = LeadgenLead.objects.filter(uuid=serializer.validated_data.pop('lead_id')).first()
        campaign = Campaign.objects.filter(symbol=serializer.validated_data.pop('campaign_id')).first()
        if not leadgen_lead or not campaign:
            logger.error('Lead or campaign not found', exc_info=True)
            return Response(status=status.HTTP_200_OK)

        payout = serializer.validated_data.pop('payout', Decimal('0.00'))
        payout = payout.quantize(Decimal('.01'))

        LeadgenLeadConversion.objects.create(
            lead=leadgen_lead, campaign=campaign, user=campaign.user, payout=payout, **serializer.validated_data
        )

        return Response(status=status.HTTP_200_OK)


class LeadgenLanderPostbackView(APIView):
    permission_classes = ()

    def post(self, request, *args, **kwargs):
        serializer = LanderDataSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # print(request.data)
        process_lander_data.delay(serializer.validated_data)
        return Response(data={'status': 'OK'}, status=status.HTTP_200_OK)


class LeadgenClickPostbackView(APIView):
    permission_classes = ()

    def post(self, request, *args, **kwargs):
        # print(request.data)
        if request.headers.get('X-API-Key') != settings.SHORTIFY_API_KEY:
            return Response(status=status.HTTP_403_FORBIDDEN)
        process_click_stats.delay(request.data)
        return Response(status=status.HTTP_200_OK)


# TODO: переписать нормально
class LeadgenBroadcastCreateView(CreateAPIView):
    allowed_roles = (User.ADMIN, User.TEAMLEAD)
    queryset = LinkGroup.objects.all()
    serializer_class = LinkGroupCreateSerializer

    def perform_create(self, serializer):
        group = serializer.save(user=self.request.user, filter_data=self.filter_data)
        return group.id

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.filter_data = request.GET.dict()
        group_id = self.perform_create(serializer)

        # create_links(group_id)
        create_links.delay(group_id)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class LeadgenBroadcastRecreateView(APIView):
    allowed_roles = (User.ADMIN, User.TEAMLEAD)

    def post(self, request, *args, **kwargs):
        group = get_object_or_404(LinkGroup, pk=self.kwargs['pk'])
        if group.user != request.user:
            if request.user.role not in [User.ADMIN, User.TEAMLEAD]:
                raise PermissionError()

            elif request.user.role == User.TEAMLEAD and group.user.team and group.user.team != request.user.team:
                raise PermissionError()

        create_links.delay(group.id)

        return Response(status=status.HTTP_200_OK)


class LeadgenBroadcastListView(DinamicFieldsListAPIView):
    allowed_roles = (User.ADMIN, User.TEAMLEAD)
    queryset = LinkGroup.objects.all()
    serializer_class = LinkGroupListSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    filterset_class = LeadgenBroadcastFilter


class LeadgenBroadcastEditView(UpdateAPIView):
    allowed_roles = (User.ADMIN, User.TEAMLEAD)
    queryset = LinkGroup.objects.all()
    serializer_class = LinkGroupEditSerializer
