import logging
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db.models import QuerySet

from django_filters import rest_framework as filters
from facebook_business.exceptions import FacebookRequestError
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter
from rest_framework.generics import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.serializers.businesses import (
    BusinessActionSerializer,
    BusinessManagerLogSerializer,
    BusinessShareListSerializer,
)
from api.v1.views.core import DinamicFieldsListAPIView
from core.models import User
from core.models.core import Action, BusinessManager, BusinessManagerLog, BusinessShareUrl

logger = logging.getLogger(__name__)


class BusinessShareListView(DinamicFieldsListAPIView):
    allowed_roles = (
        User.ADMIN,
        User.FINANCIER,
        User.MANAGER,
        User.TEAMLEAD,
        User.MEDIABUYER,
        User.FARMER,
        User.JUNIOR,
    )
    queryset = BusinessShareUrl.objects.all()
    serializer_class = BusinessShareListSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)

    def get_queryset(self) -> QuerySet:
        business = get_object_or_404(BusinessManager, pk=self.kwargs['business_id'])
        qs = super(BusinessShareListView, self).get_queryset()
        qs = qs.filter(business=business)

        if self.request.user.role == User.TEAMLEAD:
            if (
                business.account.manager.team
                and business.account.manager.team != self.request.user.team
                and business.account.manager != self.request.user
            ):
                raise PermissionDenied()

        elif self.request.user.role in [User.MEDIABUYER, User.FARMER, User.JUNIOR]:
            if business.account.manager != self.request.user:
                raise PermissionDenied()

        return qs


class BusinessShareUrlCreateView(APIView):
    allowed_roles = (
        User.ADMIN,
        User.FINANCIER,
        User.MANAGER,
        User.TEAMLEAD,
        User.MEDIABUYER,
        User.FARMER,
        User.JUNIOR,
    )

    def post(self, request, *args, **kwargs):
        business = get_object_or_404(BusinessManager, pk=self.kwargs['business_id'])

        if request.user.role == User.TEAMLEAD:
            if (
                business.account.manager.team
                and business.account.manager.team != request.user.team
                and business.account.manager != request.user
            ):
                raise PermissionDenied()

        elif request.user.role in [User.MEDIABUYER, User.FARMER, User.JUNIOR]:
            if business.account.manager != request.user:
                raise PermissionDenied()

        if not business.account.fb_access_token:
            return Response(data={'error': 'Add account token before'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            business.create_share_url()
        except FacebookRequestError as e:
            logger.error(e, exc_info=True)
            return Response(
                data={'error': e.body()['error'].get('error_user_msg') or e.body()['error'].get('message')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(e, exc_info=True)
            return Response(data={'error': 'Unknown error'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_201_CREATED)


class BusinessManagerActionsLog(DinamicFieldsListAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER, User.MANAGER, User.TEAMLEAD, User.MEDIABUYER, User.JUNIOR)
    queryset = Action.objects.none()
    serializer_class = BusinessActionSerializer
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)

    def get_queryset(self) -> QuerySet:
        business = get_object_or_404(BusinessManager, pk=self.kwargs['business_id'])
        content_type = ContentType.objects.get_for_model(business)
        return Action.objects.filter(action_object_object_id=business.id, action_object_content_type=content_type)


class BusinessManagerLogListView(DinamicFieldsListAPIView):
    allowed_roles = (User.ADMIN, User.FINANCIER, User.MANAGER, User.TEAMLEAD, User.MEDIABUYER, User.JUNIOR)
    queryset = BusinessManagerLog.objects.all().prefetch_related('account')
    filter_backends = (filters.DjangoFilterBackend, OrderingFilter)
    serializer_class = BusinessManagerLogSerializer

    def get_queryset(self) -> QuerySet:
        business = get_object_or_404(BusinessManager, pk=self.kwargs['business_id'])
        if self.request.user.role == User.TEAMLEAD:
            if (
                business.account.manager.team
                and business.account.manager.team != self.request.user.team
                and business.account.manager != self.request.user
            ):
                raise PermissionDenied()

        elif self.request.user.role in [User.MEDIABUYER, User.FARMER, User.SETUPER, User.JUNIOR]:
            if business.account.manager != self.request.user and business.account.supplier != self.request.user:
                raise PermissionDenied()

        qs = super(BusinessManagerLogListView, self).get_queryset().filter(business=business)
        return qs
